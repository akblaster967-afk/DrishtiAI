from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import hashlib
import re
from concurrent.futures import ThreadPoolExecutor

import cv2
import numpy as np
from PIL import Image
from app.services.pdf_images import load_pdf_page_image


PROFILES: dict[str, dict[str, Any]] = {
    "COLLEGE_ID": {
        "required": ["name", "document_number", "course", "valid_until"],
        "patterns": {
            "document_number": r"^BE\d{2}[A-Z]{2}\d{3}$",
            "valid_until": r"^(19|20)\d{2}\s*-\s*(19|20)\d{2}$",
        },
        "keywords": ["NAME", "COURSE", "VALID"],
    },
    "PAN": {
        "required": ["name", "document_number"],
        "patterns": {"document_number": r"^[A-Z]{5}\d{4}[A-Z]$"},
        "keywords": ["INCOME", "TAX", "PAN"],
    },
    "PASSPORT": {
        "required": ["name", "document_number", "nationality"],
        "patterns": {"document_number": r"^[A-Z]\d{7}$"},
        "keywords": ["PASSPORT", "NATIONALITY"],
    },
    "DRIVING_LICENSE": {
        "required": ["name", "document_number"],
        "patterns": {"document_number": r"^[A-Z0-9 ./-]{6,25}$"},
        "keywords": ["DRIVING", "LICENCE"],
    },
    "AADHAAR": {
        "required": ["name", "document_number"],
        "patterns": {"document_number": r"^\d{12}$"},
        "keywords": ["AADHAAR", "UIDAI"],
    },
}


def _load_image(file_path: str) -> np.ndarray | None:
    try:
        path = Path(file_path)
        if path.suffix.lower() == ".pdf":
            return load_pdf_page_image(path, 0)
        data = np.fromfile(str(path), dtype=np.uint8)
        return cv2.imdecode(data, cv2.IMREAD_COLOR)
    except Exception:
        return None


def _norm(value: Any) -> str:
    return " ".join(str(value or "").upper().split()).strip()




def _verhoeff_valid(number: str) -> bool:
    from app.services.checksums import verhoeff_is_valid

    return verhoeff_is_valid(number)


def _identifier_rules(fields: dict[str, Any], id_type: str, ocr_confidence: float = 0.0) -> list[dict[str, Any]]:
    normalized = str(id_type or "").strip().upper()
    results: list[dict[str, Any]] = []
    number = str(fields.get("document_number") or "").replace(" ", "").strip().upper()
    if normalized == "AADHAAR" and number:
        format_valid = bool(re.fullmatch(r"\d{12}", number))
        checksum_valid = format_valid and _verhoeff_valid(number)
        if checksum_valid:
            status = "PASS"
            message = "The extracted 12-digit identifier passes the public Verhoeff checksum."
        elif float(ocr_confidence or 0) < 70:
            status = "REVIEW"
            message = "The 12-digit OCR candidate could not be checksum-confirmed because document readability is below the verification threshold."
        else:
            status = "FAIL"
            message = "The extracted 12-digit identifier fails the public Verhoeff checksum."
        results.append({
            "rule": "AADHAAR_CHECKSUM",
            "status": status,
            "message": message,
        })
    if normalized == "PAN" and number:
        valid = bool(re.fullmatch(r"[A-Z]{5}\d{4}[A-Z]", number))
        results.append({
            "rule": "PAN_FORMAT",
            "status": "PASS" if valid else "FAIL",
            "message": "The extracted PAN follows the expected 5-4-1 alphanumeric structure." if valid else "The extracted PAN does not follow the expected 5-4-1 alphanumeric structure.",
        })
    if normalized == "COLLEGE_ID" and number:
        valid = bool(re.fullmatch(r"BE\d{2}[A-Z]{2}\d{3}", number))
        results.append({
            "rule": "COLLEGE_ROLL_FORMAT",
            "status": "PASS" if valid else "FAIL",
            "message": "The extracted college identifier follows the configured institution format." if valid else "The extracted college identifier does not follow the configured institution format.",
        })
    return results
def _field_schema(fields: dict[str, Any], id_type: str, ocr_confidence: float = 0.0) -> tuple[list[dict[str, Any]], list[str]]:
    profile = PROFILES.get(str(id_type or "").strip().upper(), {})
    required = profile.get("required", [])
    patterns = profile.get("patterns", {})
    checks: list[dict[str, Any]] = []
    reasons: list[str] = []
    for key in required:
        value = _norm(fields.get(key))
        label = key.replace("_", " ").title()
        if not value:
            checks.append({"field": key, "label": label, "status": "MISSING", "message": f"{label} was not reliably extracted."})
            reasons.append(f"{label} is missing or unreadable.")
            continue
        pattern = patterns.get(key)
        if pattern and not re.match(pattern, value):
            checks.append({"field": key, "label": label, "status": "FORMAT_REVIEW", "value": value, "message": f"{label} does not match the expected pattern for this document type."})
            reasons.append(f"{label} format needs review.")
        else:
            checks.append({"field": key, "label": label, "status": "PASS", "value": value, "message": f"{label} is present and structurally plausible."})
    identifier_checks = _identifier_rules(fields or {}, id_type, ocr_confidence)
    for check in identifier_checks:
        checks.append({"field": check["rule"], "label": check["rule"].replace("_", " ").title(), "status": check["status"], "message": check["message"]})
        if check["status"] == "FAIL":
            reasons.append(check["message"])
    return checks, reasons


def _keyword_check(ocr_text: str, id_type: str) -> dict[str, Any]:
    profile = PROFILES.get(str(id_type or "").strip().upper(), {})
    keywords = profile.get("keywords", [])
    text = _norm(ocr_text)
    hits = [word for word in keywords if word in text]
    required_hits = min(2, len(keywords)) if keywords else 0
    if not keywords:
        return {"status": "NOT_CONFIGURED", "hits": [], "message": "No document-specific template vocabulary is configured."}
    if len(hits) >= required_hits:
        return {"status": "PASS", "hits": hits, "message": "Expected document vocabulary was found in the OCR text."}
    return {"status": "REVIEW", "hits": hits, "message": "The OCR text contains fewer document-template keywords than expected; image quality or document authenticity needs review."}


def _qr_check(image: np.ndarray | None, fields: dict[str, Any]) -> dict[str, Any]:
    if image is None:
        return {"status": "UNAVAILABLE", "decoded": False, "message": "QR analysis was unavailable."}
    try:
        detector = cv2.QRCodeDetector()
        decoded = detector.detectAndDecode(image)
        data = decoded[0] if decoded else ""
        if not data:
            multi = getattr(detector, "detectAndDecodeMulti", None)
            if multi is not None:
                multi_result = multi(image)
                ok = bool(multi_result[0]) if multi_result else False
                decoded_info = multi_result[1] if len(multi_result) > 1 else []
                if ok and decoded_info:
                    data = next((item for item in decoded_info if item), "")
        if not data:
            return {"status": "NOT_DETECTED", "decoded": False, "message": "No readable QR code was detected."}

        normalized_payload = re.sub(r"\s+", "", data).upper()
        comparable = []
        for key in ("document_number", "enrollment_number"):
            value = re.sub(r"\s+", "", str(fields.get(key) or "")).upper()
            if value and len(value) >= 4:
                comparable.append((key, value))
        matches = [key for key, value in comparable if value in normalized_payload]
        mismatches = [key for key, value in comparable if value not in normalized_payload]
        if comparable and mismatches and not matches:
            return {
                "status": "MISMATCH",
                "decoded": True,
                "payloadPreview": data[:180],
                "matchedFields": matches,
                "mismatchedFields": mismatches,
                "message": "The readable QR payload does not contain the extracted document identifier.",
            }
        return {
            "status": "MATCHED" if matches else "REVIEW",
            "decoded": True,
            "payloadPreview": data[:180],
            "matchedFields": matches,
            "mismatchedFields": mismatches,
            "message": "QR content is readable. No direct contradiction with the extracted identifier was found." if matches else "QR content is readable but could not be directly tied to an extracted identifier.",
        }
    except Exception:
        return {"status": "UNAVAILABLE", "decoded": False, "message": "QR analysis could not be completed."}


def _metadata_check(file_path: str) -> dict[str, Any]:
    try:
        path = Path(file_path)
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            return {"status": "AVAILABLE", "sourceType": "PDF", "message": "PDF container accepted for forensic screening; embedded metadata is not treated as authenticity proof."}
        with Image.open(path) as image:
            info_keys = sorted(str(key) for key in image.info.keys())
            exif = image.getexif()
            editing_markers = []
            for key in ("software", "comment", "softwareVersion", "xmp"):
                value = image.info.get(key)
                if value:
                    editing_markers.append(str(value)[:120])
            return {
                "status": "AVAILABLE",
                "format": image.format,
                "width": image.width,
                "height": image.height,
                "metadataKeys": info_keys[:20],
                "exifEntries": len(exif or {}),
                "editingMarkers": editing_markers,
                "message": "Metadata is supporting evidence only because social-media/app exports and scans can remove or rewrite it.",
            }
    except Exception:
        return {"status": "UNAVAILABLE", "message": "Metadata could not be read."}


def _structure_check(image: np.ndarray | None) -> dict[str, Any]:
    if image is None:
        return {"status": "UNAVAILABLE", "message": "Image structure could not be evaluated."}
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape[:2]
    edge_ratio = float(np.mean(cv2.Canny(gray, 60, 150) > 0))
    aspect_ratio = round(w / max(h, 1), 3)


    if min(h, w) < 500:
        return {"status": "REVIEW", "width": w, "height": h, "aspectRatio": aspect_ratio, "edgeDensity": round(edge_ratio, 5), "message": "Resolution is low for reliable forensic inspection."}
    return {"status": "PASS", "width": w, "height": h, "aspectRatio": aspect_ratio, "edgeDensity": round(edge_ratio, 5), "message": "Image resolution is adequate for the current forensic modules."}


def _fabrication_screen(
    id_type: str,
    fields: dict[str, Any],
    schema_checks: list[dict[str, Any]],
    keyword_check: dict[str, Any],
    profile_check: dict[str, Any],
    qr: dict[str, Any],
    security_features: dict[str, Any],
    integrity_screening: dict[str, Any],
    ai_analysis: dict[str, Any] | None,
    visual_forgery: dict[str, Any] | None = None,
    document_consistency: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_type = str(id_type or "").strip().upper()
    number = re.sub(r"\s+", "", str((fields or {}).get("document_number") or "")).upper()
    signals: list[dict[str, Any]] = []

    placeholder_numbers = {
        "ABCDE1234F", "123456789012", "1234567890", "U1234567",
        "AAAPL1234C", "000000000000", "111111111111", "123412341234",
    }
    if number in placeholder_numbers:
        signals.append({"type": "PLACEHOLDER_IDENTIFIER", "severity": "HIGH", "message": "The extracted identifier matches a commonly used sample or placeholder value."})

    digits = re.sub(r"\D", "", number)
    if len(digits) >= 6:
        ascending = "0123456789" in (digits + digits)
        descending = "9876543210" in (digits + digits)
        repeated_digit = len(set(digits)) == 1
        if ascending or descending or repeated_digit:
            signals.append({"type": "SEQUENTIAL_OR_REPEATED_IDENTIFIER", "severity": "HIGH", "message": "The identifier is sequential or repeated in a way commonly used for fabricated samples."})

    type_sample_patterns = {
        "PASSPORT": (r"^[A-Z]1234567$", r"^[A-Z]0000000$"),
        "DRIVING_LICENSE": (r"^(?:DL)?0{4,}$", r"^[A-Z]{2}\d{2}(?:19|20)000000$"),
        "COLLEGE_ID": (r"^(?:ID|STUDENT|ROLL)?0{4,}$", r"^[A-Z]{2}\d{2}[A-Z]{2}000+$"),
        "NATIONAL_ID": (r"^0{6,}$", r"^[A-Z0-9]{2}123456+$"),
        "VISA": (r"^0{5,}$", r"^[A-Z]{2}123456+$"),
    }
    if number and any(re.fullmatch(pattern, number) for pattern in type_sample_patterns.get(normalized_type, ())):
        signals.append({"type": "DOCUMENT_TYPE_SAMPLE_IDENTIFIER", "severity": "HIGH", "message": f"The {normalized_type.replace('_', ' ').lower()} identifier matches a common fabricated/sample pattern."})

    failed_identifier_rules = [
        item for item in schema_checks
        if str(item.get("field", "")).upper() in {"AADHAAR_CHECKSUM", "PAN_FORMAT", "COLLEGE_ROLL_FORMAT"}
        and str(item.get("status", "")).upper() == "FAIL"
    ]
    if failed_identifier_rules:
        signals.append({"type": "IDENTIFIER_RULE_FAILURE", "severity": "HIGH", "message": "A document-specific identifier rule failed; a plausible-looking layout cannot override this contradiction."})

    if normalized_type == "PAN" and number and len(number) == 10:
        fourth_character = number[3]
        if fourth_character not in "PCHFATBLJ":
            signals.append({"type": "PAN_CATEGORY_CONTRADICTION", "severity": "HIGH", "message": "The PAN category character is not one of the configured holder/entity categories."})

    failed_schema = [item for item in schema_checks if item.get("status") in {"MISSING", "FORMAT_REVIEW", "FAIL"}]
    if failed_schema:
        signals.append({"type": "FIELD_CONTRADICTION", "severity": "HIGH", "message": "One or more required document fields are missing or contradict the expected document structure."})
    if keyword_check.get("status") == "REVIEW" and profile_check.get("status") in {"FAIL", "REVIEW"}:
        signals.append({"type": "TEMPLATE_CONTRADICTION", "severity": "MEDIUM", "message": "Both document vocabulary and document-specific layout evidence are weaker than expected."})
    if qr.get("status") == "MISMATCH":
        signals.append({"type": "ENCODED_DATA_MISMATCH", "severity": "HIGH", "message": "Readable encoded data contradicts the extracted document identifier."})

    security_status = str(security_features.get("overallStatus") or "").upper()
    if security_status == "HIGH":
        signals.append({"type": "SECURITY_FEATURE_CONTRADICTION", "severity": "HIGH", "message": security_features.get("summary") or "Configured security-feature checks found a strong contradiction."})
    elif security_status == "REVIEW":
        signals.append({"type": "SECURITY_FEATURE_REVIEW", "severity": "MEDIUM", "message": security_features.get("summary") or "Visible security-feature evidence requires review."})

    integrity_status = str(integrity_screening.get("status") or "").upper()
    if integrity_status == "POSSIBLE_EDITING":
        signals.append({"type": "LOCAL_EDITING_EVIDENCE", "severity": "HIGH", "message": integrity_screening.get("summary") or "Independent image signals are consistent with local editing."})
    elif integrity_status == "REVIEW_SIGNAL":
        signals.append({"type": "LOCAL_EDITING_REVIEW", "severity": "MEDIUM", "message": integrity_screening.get("summary") or "Image-integrity evidence requires review."})

    ai_band = str((ai_analysis or {}).get("band") or "").upper()
    ai_signal_count = len((ai_analysis or {}).get("signals") or [])
    if ai_band in {"HIGH", "MEDIUM"} and ai_signal_count:
        signals.append({"type": "SYNTHETIC_IMAGE_EVIDENCE", "severity": "MEDIUM", "message": "Visual screening found signals consistent with synthetic generation or heavy regeneration; this does not identify the creation tool."})

    consistency_band = str((document_consistency or {}).get("band") or "").upper()
    if consistency_band == "HIGH":
        signals.append({"type": "CROSS_FIELD_CONTRADICTION", "severity": "HIGH", "message": "Cross-field consistency checks found strong contradictions between extracted document values."})
    elif consistency_band == "MEDIUM":
        signals.append({"type": "CROSS_FIELD_REVIEW", "severity": "MEDIUM", "message": "Cross-field consistency checks found values that require manual review."})

    for signal in (visual_forgery or {}).get("signals", [])[:4]:
        signals.append({
            "type": signal.get("type", "VISUAL_FORGERY_SIGNAL"),
            "severity": signal.get("severity", "MEDIUM"),
            "message": signal.get("message", "A visual forgery signal requires review."),
        })

    high_count = sum(item["severity"] == "HIGH" for item in signals)
    medium_count = sum(item["severity"] == "MEDIUM" for item in signals)
    if high_count >= 2 or (high_count >= 1 and medium_count >= 1):
        verdict = "FABRICATED_OR_TAMPERED"
        status = "HIGH"
        summary = "Independent document contradictions or edit signals indicate the document should be treated as fabricated or tampered."
    elif high_count == 1 or medium_count >= 2:
        verdict = "SUSPICIOUS_REQUIRES_REVIEW"
        status = "REVIEW"
        summary = "The document has meaningful authenticity concerns, but the available image evidence is not conclusive."
    else:
        verdict = "NO_FABRICATION_SIGNAL"
        status = "LOW"
        summary = "No strong fabrication contradiction was found; this is not issuer proof of genuineness."

    return {
        "verdict": verdict,
        "status": status,
        "summary": summary,
        "signals": signals[:8],
        "faceVerificationUsed": False,
        "aiGenerationStatus": "EVIDENCE_PRESENT" if ai_band in {"HIGH", "MEDIUM"} and ai_signal_count else "INCONCLUSIVE",
        "notice": "Fabrication and AI-generation are separate findings. A clean image screen cannot prove issuer authenticity; issuer or QR verification is still required.",
    }


def build_document_verification(file_path: str, id_type: str, fields: dict[str, Any], ocr_confidence: float, ocr_text: str, ai_analysis: dict[str, Any] | None = None, document_consistency: dict[str, Any] | None = None) -> dict[str, Any]:
    id_type = str(id_type or "").strip().upper()
    from app.services.security_feature_analyzer import analyze_security_features
    from app.services.document_profile import check_document_profile
    image = _load_image(file_path)
    schema_checks, schema_reasons = _field_schema(fields or {}, id_type, ocr_confidence)
    keyword_check = _keyword_check(ocr_text, id_type)
    profile_check = check_document_profile(id_type, ocr_text, fields or {})
    qr = _qr_check(image, fields or {})
    metadata = _metadata_check(file_path)
    structure = _structure_check(image)
    from app.services.visual_forgery_analyzer import analyze_visual_forgery



    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="evidence") as executor:
        security_future = executor.submit(analyze_security_features, file_path, id_type, ocr_text)
        visual_future = executor.submit(analyze_visual_forgery, file_path, id_type)
        security_features = security_future.result()
        visual_forgery = visual_future.result()
    from app.services.document_integrity import build_integrity_screening
    integrity_screening = build_integrity_screening(ai_analysis, metadata, structure)
    fabrication_screening = _fabrication_screen(
        id_type,
        fields or {},
        schema_checks,
        keyword_check,
        profile_check,
        qr,
        security_features,
        integrity_screening,
        ai_analysis,
        visual_forgery,
        document_consistency,
    )

    modules = [
        {"id": "schema", "label": "Document fields", "status": "REVIEW" if schema_reasons else "PASS", "message": " and ".join(schema_reasons) if schema_reasons else "Required fields are present and structurally plausible."},
        {"id": "template", "label": "Template vocabulary", "status": keyword_check["status"], "message": keyword_check["message"]},
        {"id": "document_profile", "label": "Document type profile", "status": profile_check["status"], "message": profile_check["message"]},
        {"id": "qr", "label": "QR / encoded data", "status": qr["status"], "message": qr["message"]},
        {"id": "metadata", "label": "File metadata", "status": metadata["status"], "message": metadata["message"]},
        {"id": "structure", "label": "Image structure", "status": structure["status"], "message": structure["message"]},
        {"id": "security", "label": "Security-feature layer", "status": str(security_features.get("overallStatus") or "UNAVAILABLE").upper(), "message": security_features.get("summary") or "Visible security/design cues were evaluated."},
        {"id": "synthetic", "label": "AI / synthetic screening", "status": str((ai_analysis or {}).get("band") or "UNAVAILABLE").upper(), "message": (ai_analysis or {}).get("notice") or "Synthetic-document screening is advisory."},
        {"id": "integrity", "label": "Document integrity", "status": str(integrity_screening.get("status") or "UNAVAILABLE").upper(), "message": integrity_screening.get("summary") or "Document integrity screening was unavailable."},
        {"id": "visual_forgery", "label": "Visual forgery signals", "status": str(visual_forgery.get("status") or "UNAVAILABLE").upper(), "message": visual_forgery.get("notice") or "Visual forgery analysis was unavailable."},
        {"id": "fabrication", "label": "Fabrication assessment", "status": fabrication_screening["status"], "message": fabrication_screening["summary"]},
        {"id": "issuer", "label": "Issuer verification", "status": "NOT_CONFIGURED", "message": "No authorised issuer/API connector is configured in this build."},
    ]

    evidence_reasons: list[str] = []
    if schema_reasons:
        evidence_reasons.extend(schema_reasons)
    if keyword_check["status"] == "REVIEW":
        evidence_reasons.append(keyword_check["message"])
    if profile_check["status"] in {"FAIL", "REVIEW"}:
        evidence_reasons.append(profile_check["message"])
    if qr["status"] == "MISMATCH":
        evidence_reasons.append(qr["message"])
    if structure["status"] == "REVIEW":
        evidence_reasons.append(structure["message"])
    security_status = str(security_features.get("overallStatus") or "").upper()
    if security_status in {"HIGH", "REVIEW"}:
        evidence_reasons.append(security_features.get("summary") or "Security-feature checks require review.")
    if str((ai_analysis or {}).get("band", "")).upper() in {"HIGH", "MEDIUM"}:
        evidence_reasons.extend([item.get("message", "") for item in (ai_analysis or {}).get("signals", [])[:3]])
    if str(integrity_screening.get("status") or "").upper() in {"POSSIBLE_EDITING", "REVIEW_SIGNAL"}:
        evidence_reasons.extend([item.get("message", "") for item in integrity_screening.get("evidence", [])[:3]])

    high_count = sum(item["status"] in {"HIGH", "MISMATCH", "FAIL"} for item in modules)
    review_count = sum(item["status"] in {"REVIEW", "MEDIUM"} for item in modules)
    unavailable_count = sum(item["status"] in {"UNAVAILABLE", "NOT_CONFIGURED"} for item in modules)

    if high_count >= 2:
        overall = "HIGH"
        summary = "Multiple independent indicators require detailed verification."
    elif high_count == 1 or review_count >= 2:
        overall = "REVIEW"
        summary = "Some evidence requires manual review before authenticity is accepted."
    else:
        overall = "LOW"
        summary = "No strong contradiction was found by the configured screening modules."

    digest = None
    try:
        with open(file_path, "rb") as fh:
            digest = hashlib.sha256(fh.read()).hexdigest()
    except Exception:
        pass

    return {
        "available": True,
        "overallStatus": overall,
        "summary": summary,
        "evidenceCount": len([r for r in evidence_reasons if r]),
        "reviewCount": review_count,
        "unavailableCount": unavailable_count,
        "modules": modules,
        "schemaChecks": schema_checks,
        "templateCheck": keyword_check,
        "documentProfile": profile_check,
        "qrCheck": qr,
        "metadata": metadata,
        "structure": structure,
        "integrityScreening": integrity_screening,
        "visualForgeryScreening": visual_forgery,
        "fabricationScreening": fabrication_screening,
        "securityFeatures": security_features,
        "issuerVerification": {
            "status": "NOT_CONFIGURED",
            "message": "Issuer verification requires an authorised external service or verified registry connection."
        },
        "evidenceReasons": [r for r in evidence_reasons if r][:8],
        "sha256": digest,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "notice": "Drishti AI is a screening and verification-assistance system. Pixel-level and heuristic evidence cannot, by itself, prove legal authenticity or identify the exact tool used to create an image.",
        "ocrConfidence": round(float(ocr_confidence or 0), 2),
    }
