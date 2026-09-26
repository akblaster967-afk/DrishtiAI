from __future__ import annotations

import re
from pathlib import Path
from typing import Any

try:
    import pytesseract
except Exception:
    pytesseract = None



if pytesseract is not None:
    _TESS_CANDIDATES = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ]
    try:
        import shutil

        _tess_path = shutil.which("tesseract")
        if not _tess_path:
            _tess_path = next(
                (path for path in _TESS_CANDIDATES if Path(path).exists()),
                None,
            )
        if _tess_path:
            pytesseract.pytesseract.tesseract_cmd = _tess_path
    except Exception:
        pass






COMMON_MISSPELLINGS = {
    "filanagement": "management",
    "managment": "management",
    "requirment": "requirement",
    "requirement": None,
    "certficate": "certificate",
    "certifcate": "certificate",
    "certifiate": "certificate",
    "aadhar": "aadhaar",
    "meritnation": None,
    "nationl": "national",
    "internaton": "international",
    "goverment": "government",
    "universityy": "university",
    "semesterr": "semester",
    "rooll": "roll",
    "ernrollment": "enrollment",
    "mojor": "major",
    "bacholr": "bachelor",
    "engneering": "engineering",
}



BROKEN_GLYPH_PATTERN = re.compile(
    r"(^|[^\w])([>|<$#@&\^`~]{2,})|"
    r"(^|[A-Za-z]{1,2})(\d{1,2}[\|/\\]{1})|"
    r"[\u25a0-\u25ff\u2300-\u27bf]+",
    re.IGNORECASE,
)



MANDATORY_FIELD_PATTERNS: dict[str, dict[str, str]] = {
    "Roll Number": {
        "pattern": r"(?i)\b(roll|r\.?no\.?|std|reg|enrol(?:l)?ment(?: no)?)\s*[.:\- ]?\s*([A-Z0-9]{3,20})\b",
        "example": "Roll: 2021CS1234",
    },
    "ERP ID": {
        "pattern": r"(?i)\b(erp(?: ?id)?|employee ?id|staff ?id|sap ?id)\s*[.:\- ]?\s*([A-Z0-9]{3,20})\b",
        "example": "ERP 40012345",
    },
    "DOB": {
        "pattern": r"(?i)\b(?:d\.?o\.?b\.?|date ?of ?birth|born|birth)\s*[.:\- ]?\s*(\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4})\b",
        "example": "DOB: 12-08-2001",
    },
    "Aadhaar Number": {
        "pattern": r"\b(\d{4}[\s-]?\d{4}[\s-]?\d{4})\b",
        "example": "9876 5432 1012",
    },
    "PAN Number": {
        "pattern": r"\b([A-Z]{5}\d{4}[A-Z])\b",
        "example": "ABCDE1234F",
    },
    "Passport Number": {
        "pattern": r"\b([A-Z]\d{7})\b",
        "example": "M1234567",
    },
}


def extract_text_boxes(file_path: str | Path) -> dict[str, Any]:
    try:
        import easyocr

        reader = easyocr.Reader(["en"], gpu=False, verbose=False)
        rows = reader.readtext(str(file_path), detail=1, paragraph=False)
        boxes = [
            {
                "text": str(text),
                "confidence": round(float(conf), 3),
                "bbox": [[round(float(x), 1) for x in pt] for pt in bbox],
            }
            for bbox, text, conf in rows
        ]
        engine = "easyocr"
    except Exception as easy_error:
        if pytesseract is None:
            return {
                "available": False,
                "engine": None,
                "reason": "Neither EasyOCR nor pytesseract is installed.",
            }
        try:
            from PIL import Image, ImageOps

            with Image.open(file_path) as image:
                image = ImageOps.exif_transpose(image).convert("RGB")
            data = pytesseract.image_to_data(
                image,
                output_type=pytesseract.Output.DICT,
                config="--oem 3 --psm 6",
            )
            boxes = []
            for index in range(len(data.get("text", []))):
                text = str(data["text"][index]).strip()
                if not text:
                    continue
                boxes.append(
                    {
                        "text": text,
                        "confidence": round(
                            max(0.0, min(100.0, float(data.get("conf", [0])[index] or 0))) / 100.0,
                            3,
                        ),
                        "bbox": [
                            [float(data.get("left", [0])[index] or 0), float(data.get("top", [0])[index] or 0)],
                            [
                                float((data.get("left", [0])[index] or 0) + (data.get("width", [0])[index] or 0)),
                                float((data.get("top", [0])[index] or 0) + (data.get("height", [0])[index] or 0)),
                            ],
                        ],
                    }
                )
            engine = "pytesseract"
        except Exception as psm_error:
            return {
                "available": False,
                "engine": "pytesseract",
                "reason": f"OCR failed: {psm_error}",
            }

    if not boxes:
        return {
            "available": True,
            "engine": engine,
            "boxes": [],
            "text": "",
            "reason": "No text was detected.",
        }

    boxes.sort(key=lambda b: (b["bbox"][0][1], b["bbox"][0][0]))
    full_text = "\n".join(box["text"] for box in boxes)
    confidences = [b["confidence"] for b in boxes]
    return {
        "available": True,
        "engine": engine,
        "boxes": boxes,
        "text": full_text,
        "word_count": len(boxes),
        "mean_confidence": round(sum(confidences) / len(confidences), 3),
        "min_confidence": round(min(confidences), 3),
        "max_confidence": round(max(confidences), 3),
    }


def detect_ai_typos(text: str) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []
    tokens = re.findall(r"[A-Za-zА-Яа-я]{4,}", str(text or ""))
    seen: set[str] = set()

    for token in tokens:
        lowered = token.lower()
        correction = COMMON_MISSPELLINGS.get(lowered)
        if correction:
            key = ("spell", lowered)
            if key in seen:
                continue
            seen.add(key)
            flags.append(
                {
                    "flag": "AI_HALLUCINATED_WORD",
                    "type": "suspicious_spelling",
                    "token": lowered,
                    "suggestion": correction,
                    "message": f"Possibly hallucinated spelling: '{lowered}' (suggested '{correction}').",
                }
            )

    for match in BROKEN_GLYPH_PATTERN.finditer(str(text or "")):
        fragment = match.group(0).strip()
        if not fragment or len(fragment) > 12:
            continue
        lowered = fragment.lower()
        if ("spell", lowered) in seen:
            continue
        seen.add(("spell", lowered))
        flags.append(
            {
                "flag": "BROKEN_GLYPH",
                "type": "broken_glyph",
                "token": fragment,
                "suggestion": None,
                "message": f"Broken/distorted glyph fragment detected: '{fragment}'.",
            }
        )

    return flags


def validate_mandatory_fields(text: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for field_name, spec in MANDATORY_FIELD_PATTERNS.items():
        match = re.search(spec["pattern"], str(text or ""))
        value = None
        status = "MISSING"
        if match:
            groups = match.groups()
            value = groups[-1] if groups else match.group(0)
            if value and re.fullmatch(r"(_*|\s*)", str(value)):
                value = None
            status = "PRESENT" if value else "MISSING"

        results.append(
            {
                "field": field_name,
                "status": status,
                "value": str(value) if value else None,
                "verified": bool(value) and (field_name != "DOB" or _plausible_dob(str(value))),
            }
        )
    return results


def _plausible_dob(value: str) -> bool:
    try:
        parts = re.split(r"[-/.]", value)
        if len(parts) != 3:
            return False
        day, month, year = parts
        if not (day.isdigit() and month.isdigit() and year.isdigit()):
            return False
        d, m, y = int(day), int(month), int(year)
        if y < 100:
            y = y + 1900 if y > 40 else y + 2000
        if not (1 <= m <= 12 and 1 <= d <= 31):
            return False
        if y < 1900 or y > 2026:
            return False
        import calendar

        return d <= calendar.monthrange(y, m)[1]
    except Exception:
        return False


def layout_compliance(boxes: list[dict[str, Any]]) -> dict[str, Any]:
    if not boxes:
        return {"status": "NO_TEXT", "issues": ["No text boxes to analyze."]}

    issues: list[str] = []
    angles = []
    overlap_count = 0
    for box in boxes:
        pts = box["bbox"]
        if len(pts) < 2:
            continue
        (x1, y1), (x2, y2) = pts[0], pts[-1]
        width = x2 - x1
        height = y2 - y1
        if width <= 0 or height <= 0:
            continue
        from math import atan2, degrees

        angle = abs(degrees(atan2(height, width)))
        angles.append(angle)

    if angles:
        avg_angle = sum(angles) / len(angles)
        tilt = abs(90 - avg_angle) if avg_angle > 45 else avg_angle
        if tilt > 25:
            issues.append(f"OCR boxes average a {tilt:.0f} deg tilt, which is unusual for a printed ID.")



    sorted_boxes = sorted(boxes, key=lambda b: (b["bbox"][0][1], b["bbox"][0][0]))
    for i in range(1, min(len(sorted_boxes), 400)):
        cur = sorted_boxes[i]["bbox"]
        prev = sorted_boxes[i - 1]["bbox"]
        if len(cur) < 2 or len(prev) < 2:
            continue
        cup1, cup2 = cur[0], cur[-1]
        prev1, prev2 = prev[0], prev[-1]
        if abs(cup1[1] - prev1[1]) > 6:
            continue
        if cup1[0] < prev2[0] - 2 and cup1[1] < prev2[1] - 2:
            overlap_count += 1
    if overlap_count >= 4:
        issues.append(f"{overlap_count} overlapping text boxes detected; check for regenerated glyphs.")

    status = "REVIEW" if issues else "PASS"
    return {"status": status, "issues": issues, "box_count": len(boxes)}


def analyze_ocr_forensics(file_path: str | Path) -> dict[str, Any]:
    base = extract_text_boxes(file_path)
    if not base.get("available"):
        return {
            "available": False,
            "engine": base.get("engine"),
            "reason": base.get("reason", "OCR is unavailable."),
            "risk_level": "UNAVAILABLE",
            "summary": "OCR engine unavailable; typo and field checks were skipped.",
        }

    text = base.get("text", "")
    typos = detect_ai_typos(text)
    mandatory = validate_mandatory_fields(text)
    layout = layout_compliance(base.get("boxes", []))

    missing_fields = [item["field"] for item in mandatory if item["status"] == "MISSING"]
    typo_count = len(typos)

    if typo_count >= 3 or missing_fields and len(missing_fields) >= 2 and base.get("mean_confidence", 0) > 0.55:
        risk_level = "HIGH"
    elif typo_count >= 1 or layout.get("status") == "REVIEW":
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"

    summary = (
        f"OCR extracted {base.get('word_count', 0)} words with "
        f"{typo_count} hallucination/typo flag(s); {len(missing_fields)} mandatory field(s) missing."
    )

    return {
        "available": True,
        "engine": base.get("engine"),
        "text": text,
        "word_count": base.get("word_count", 0),
        "mean_confidence": base.get("mean_confidence"),
        "min_confidence": base.get("min_confidence"),
        "max_confidence": base.get("max_confidence"),
        "boxes": base.get("boxes", [])[:200],
        "typos": typos,
        "typo_count": typo_count,
        "mandatory_fields": mandatory,
        "missing_fields": missing_fields,
        "layout": layout,
        "risk_level": risk_level,
        "summary": summary,
    }
