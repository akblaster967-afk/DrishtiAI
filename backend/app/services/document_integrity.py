from __future__ import annotations

from typing import Any


def build_integrity_screening(
    ai_analysis: dict[str, Any] | None,
    metadata: dict[str, Any] | None,
    structure: dict[str, Any] | None,
) -> dict[str, Any]:
    ai_analysis = ai_analysis or {}
    metadata = metadata or {}
    structure = structure or {}
    features = ai_analysis.get("features") or {}
    ela = features.get("ela") or {}
    texture = features.get("texture") or {}

    score = 0.0
    evidence: list[dict[str, Any]] = []

    ela_outliers = float(ela.get("ela_outlier_ratio", 0) or 0)
    ela_max_z = float(ela.get("ela_max_z", 0) or 0)
    texture_outliers = float(texture.get("texture_outlier_ratio", 0) or 0)
    noise_cv = float(texture.get("noise_cv", 0) or 0)
    texture_cv = float(texture.get("texture_cv", 0) or 0)

    if ela_outliers >= 0.08 and ela_max_z >= 6:
        score += 38
        evidence.append({"type": "ELA_LOCAL_OUTLIER", "severity": "HIGH", "message": "Some image blocks respond to recompression much more strongly than the surrounding document."})
    elif ela_outliers >= 0.04 and ela_max_z >= 5:
        score += 18
        evidence.append({"type": "ELA_LOCAL_VARIATION", "severity": "MEDIUM", "message": "Local recompression response is uneven and should be reviewed with the original source when available."})

    if texture_outliers >= 0.10 and noise_cv >= 0.75:
        score += 34
        evidence.append({"type": "LOCAL_TEXTURE_INCONSISTENCY", "severity": "HIGH", "message": "Texture/noise statistics differ substantially across document regions."})
    elif texture_outliers >= 0.05 and noise_cv >= 0.50:
        score += 16
        evidence.append({"type": "LOCAL_TEXTURE_VARIATION", "severity": "MEDIUM", "message": "Some regions have unusual texture/noise characteristics compared with the rest of the document."})

    if float(features.get("laplacianVariance", 0) or 0) >= 700 and texture_cv < 0.18 and noise_cv < 0.28:
        score += 16
        evidence.append({"type": "DIGITAL_RENDER_UNIFORMITY", "severity": "MEDIUM", "message": "The image has unusually uniform digital texture. Clean digital exports can produce the same pattern."})

    editing_markers = metadata.get("editingMarkers") or []
    if editing_markers:
        score += min(8, 2 * len(editing_markers))
        evidence.append({"type": "METADATA_EDITING_MARKER", "severity": "REVIEW", "message": "The file contains metadata fields commonly written by image-processing or export software; this is supporting evidence only."})

    if str(structure.get("status") or "").upper() == "REVIEW":
        evidence.append({"type": "LOW_CAPTURE_QUALITY", "severity": "REVIEW", "message": "Image quality limits how confidently visual edit signals can be interpreted."})

    score = round(min(100.0, score), 1)
    high_count = sum(1 for item in evidence if item.get("severity") == "HIGH")
    medium_count = sum(1 for item in evidence if item.get("severity") == "MEDIUM")

    if high_count >= 2 or (high_count >= 1 and medium_count >= 1):
        status = "POSSIBLE_EDITING"
        summary = "Multiple independent image signals are consistent with possible local editing or regeneration."
    elif high_count >= 1 or score >= 45:
        status = "REVIEW_SIGNAL"
        summary = "The image contains a forensic editing signal that needs manual review."
    elif score < 20:
        status = "NO_STRONG_EDIT_SIGNAL"
        summary = "No strong image-editing signal was detected by the current heuristic screen."
    else:
        status = "INCONCLUSIVE"
        summary = "Some weak forensic variation was detected, but it is not sufficient to classify the document as edited."

    return {
        "available": bool(ai_analysis.get("available", False)),
        "status": status,
        "score": score,
        "summary": summary,
        "evidence": evidence[:6],
        "basis": "ELA + local texture/noise + metadata supporting evidence",
        "notice": "This is a heuristic integrity screen. A clean result is not proof that a document is original, and a positive signal can also be caused by scans, re-exports, compression or legitimate edits.",
    }
