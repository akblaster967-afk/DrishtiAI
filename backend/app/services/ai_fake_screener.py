from __future__ import annotations

from pathlib import Path
from typing import Any

from app.services import (
    c2pa_checker,
    deep_learning_detector,
    exif_checker,
    forensics_ela,
    ocr_forensics,
)

VALID_VERDICTS = {
    "AUTHENTIC / REAL",
    "AI-GENERATED / TAMPERED",
}


C2PA_PENALTY_CAP = 25
EXIF_PENALTY_CAP = 20
ELA_PENALTY_CAP = 22
OCR_PENALTY_CAP = 20
DL_PENALTY_CAP = 30


def _analyze_image(file_path: str | Path) -> dict[str, Any]:
    c2pa = c2pa_checker.check_c2pa(file_path)
    exif = exif_checker.inspect_exif(file_path)
    ela = forensics_ela.compute_ela(file_path)
    ocr = ocr_forensics.analyze_ocr_forensics(file_path)
    dl = deep_learning_detector.detect_ai_generated(file_path)
    return {
        "c2pa": c2pa,
        "exif": exif,
        "ela": ela,
        "ocr_forensics": ocr,
        "deep_learning": dl,
    }


def _score_contributions(modules: dict[str, Any]) -> dict[str, Any]:
    contributions: dict[str, Any] = {}


    c2pa = modules.get("c2pa") or {}
    c2pa_points = 0
    if c2pa.get("is_ai_generated_flag"):
        c2pa_points = -C2PA_PENALTY_CAP
    elif c2pa.get("has_c2pa") and c2pa.get("issuer_name"):

        c2pa_points = +15
    contributions["c2pa"] = {
        "points": c2pa_points,
        "note": (
            "Valid signed C2PA provenance present (bonus)."
            if c2pa_points > 0
            else "Active C2PA manifest names an AI generator."
            if c2pa_points < 0
            else "No usable C2PA manifest; treated as neutral, not proof."
        ),
    }


    exif = modules.get("exif") or {}
    exif_points = 0
    exif_risk = str(exif.get("risk_level", "")).upper()
    if exif_risk == "HIGH" and exif.get("ai_software_hits"):
        exif_points = -EXIF_PENALTY_CAP
    elif exif_risk == "MEDIUM" and exif.get("editor_software_hits"):
        exif_points = -10
    elif exif.get("stripped_or_missing"):

        exif_points = 0
    contributions["exif"] = {
        "points": exif_points,
        "note": (
            "Metadata names an AI-generation tool."
            if exif_points == -EXIF_PENALTY_CAP
            else "Metadata names a photo editor (review)."
            if exif_points == -10
            else "No EXIF metadata present; neutral screening note."
        ),
    }


    ela = modules.get("ela") or {}
    ela_status = str(ela.get("risk_level", "")).upper()
    ela_points = {
        "HIGH": -ELA_PENALTY_CAP,
        "MEDIUM": -11,
    }.get(ela_status, 0)
    contributions["ela"] = {
        "points": ela_points,
        "note": (
            "ELA shows strongly non-uniform error; consistent with local editing."
            if ela_points < -18
            else "ELA shows a moderate anomaly; review the highlighted regions."
            if ela_points < 0
            else "ELA error levels are uniform."
        ),
    }


    ocr = modules.get("ocr_forensics") or {}
    ocr_points = 0
    typo_count = int(ocr.get("typo_count") or 0)
    missing = ocr.get("missing_fields") or []
    ocr_risk = str(ocr.get("risk_level", "")).upper()
    if ocr_risk == "HIGH":
        ocr_points = -OCR_PENALTY_CAP
    else:
        ocr_points = -min(8, 2 * typo_count) - min(6, 3 * len(missing))
    contributions["ocr_forensics"] = {
        "points": ocr_points,
        "note": (
            f"{typo_count} AI-hallucination/typo and {len(missing)} missing "
            "mandatory field(s) detected."
            if ocr_points < 0
            else "OCR found no suspicious text artifacts."
        ),
    }


    dl = modules.get("deep_learning") or {}
    dl_ai = dl.get("ai_score")
    dl_points = 0
    if dl_ai is not None:
        if dl_ai >= 80:
            dl_points = -DL_PENALTY_CAP
        elif dl_ai >= 60:
            dl_points = -18
        elif dl_ai >= 45:
            dl_points = -8
        elif dl_ai <= 20:
            dl_points = +10
    contributions["deep_learning"] = {
        "points": dl_points,
        "note": (
            f"Model AI probability is {dl_ai:.0f}%."
            if dl_ai is not None
            else "Deep-learning detector unavailable; no points applied."
        ),
    }

    return contributions


def _trust_score(contributions: dict[str, Any]) -> dict[str, Any]:
    points = sum(item["points"] for item in contributions.values())
    trust_score = int(max(0, min(100, 100 + points)))

    if trust_score >= 70:
        verdict = "AUTHENTIC / REAL"
        verdict_color = "green"
        explanation = "Overall weighted evidence supports an authentic original document."
    else:
        verdict = "AI-GENERATED / TAMPERED"
        verdict_color = "red"
        explanation = "Weighted evidence suggests AI-generated or edited content requiring manual review."

    return {
        "trust_score": trust_score,
        "verdict": verdict,
        "verdict_color": verdict_color,
        "explanation": explanation,
        "points": points,
    }


def run_ai_fake_document_screening(file_path: str | Path) -> dict[str, Any]:
    modules = _analyze_image(file_path)
    contributions = _score_contributions(modules)
    trust = _trust_score(contributions)

    report = {
        "banner_verdict": trust["verdict"],
        "trust_score": trust["trust_score"],
        "points": trust["points"],
        "explanation": trust["explanation"],
        "verdict_color": trust["verdict_color"],
        "modules": modules,
        "score_breakdown": {
            "c2pa": contributions.get("c2pa", {}).get("points"),
            "exif": contributions.get("exif", {}).get("points"),
            "ela": contributions.get("ela", {}).get("points"),
            "ocr_forensics": contributions.get("ocr_forensics", {}).get("points"),
            "deep_learning": contributions.get("deep_learning", {}).get("points"),
        },
        "notes": [
            contributions[key]["note"] for key in contributions if contributions[key].get("note")
        ],
        "confidence": {
            "c2pa_available": bool(modules["c2pa"].get("available")),
            "exif_available": bool(modules["exif"].get("metadata_present")) or modules["exif"].get("tag_count", 0) >= 0,
            "ela_available": bool(modules["ela"].get("heatmap_data_url")),
            "ocr_available": bool(modules["ocr_forensics"].get("available")),
            "dl_available": bool(modules["deep_learning"].get("available")),
        },
    }
    return report



analyze_ai_fake_screening = run_ai_fake_document_screening
