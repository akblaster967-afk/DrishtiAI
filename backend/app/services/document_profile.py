from __future__ import annotations

import re
from typing import Any


PROFILES = {
    "PAN": {
        "anchors": ("PAN", "PERMANENT ACCOUNT", "INCOME TAX"),
        "other_markers": ("AADHAAR", "PASSPORT", "DRIVING LICENCE", "DRIVING LICENSE"),
        "patterns": (re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b"),),
    },
    "AADHAAR": {
        "anchors": ("AADHAAR", "UIDAI", "UNIQUE IDENTIFICATION", "GOVERNMENT OF INDIA"),
        "other_markers": (
            "PAN",
            "PASSPORT",
            "DRIVING LICENCE",
            "DRIVING LICENSE",
            "COLLEGE",
            "STUDENT",
            "COURSE",
            "ROLL",
            "ERP",
            "ENGINEERING",
            "INSTITUTE",
        ),
        "patterns": (re.compile(r"\b\d{4}[ -]\d{4}[ -]\d{4}\b"), re.compile(r"\b\d{12}\b")),
    },
    "PASSPORT": {
        "anchors": ("PASSPORT", "REPUBLIC OF INDIA", "SURNAME", "GIVEN NAMES", "NATIONALITY"),
        "other_markers": ("PAN", "AADHAAR", "DRIVING LICENCE", "DRIVING LICENSE"),
        "patterns": (re.compile(r"\b[A-Z][A-Z0-9]{7,8}\b"), re.compile(r"[A-Z0-9<]{20,}<{2,}")),
    },
    "DRIVING_LICENSE": {
        "anchors": ("DRIVING LICENCE", "DRIVING LICENSE", "TRANSPORT", "DL NO", "VALIDITY"),
        "other_markers": ("PAN", "AADHAAR", "PASSPORT"),
        "patterns": (re.compile(r"\b[A-Z]{2}\s?\d{2}\s?(?:19|20)\d{2}\s?\d{4,8}\b"),),
    },
    "COLLEGE_ID": {
        "anchors": ("COLLEGE", "STUDENT", "COURSE", "ROLL", "ERP", "ENGINEERING", "INSTITUTE"),
        "other_markers": ("PAN", "AADHAAR", "PASSPORT", "DRIVING LICENCE", "DRIVING LICENSE"),
        "patterns": (re.compile(r"\b[A-Z]{2}\d{2}[A-Z]{2}\d{3,}\b"),),
    },
    "NATIONAL_ID": {
        "anchors": ("NATIONAL ID", "NATIONAL IDENTIFICATION", "IDENTITY CARD", "ID CARD"),
        "other_markers": ("PAN", "AADHAAR", "PASSPORT", "DRIVING LICENCE", "DRIVING LICENSE"),
        "patterns": (re.compile(r"\b[A-Z0-9]{6,20}\b"),),
    },
    "VISA": {
        "anchors": ("VISA", "ENTRY PERMIT", "IMMIGRATION"),
        "other_markers": ("PAN", "AADHAAR", "DRIVING LICENCE", "DRIVING LICENSE"),
        "patterns": (re.compile(r"\b[A-Z0-9]{5,20}\b"),),
    },
}


def _norm_id_type(value: str) -> str:
    raw = str(value or "").strip().upper()
    aliases = {
        "PAN CARD": "PAN",
        "AADHAAR CARD": "AADHAAR",
        "AADHAR": "AADHAAR",
        "AADHAR CARD": "AADHAAR",
        "DRIVING LICENSE": "DRIVING_LICENSE",
        "DRIVING LICENCE": "DRIVING_LICENSE",
        "DL": "DRIVING_LICENSE",
        "COLLEGE ID": "COLLEGE_ID",
        "COLLEGE ID CARD": "COLLEGE_ID",
        "STUDENT ID": "COLLEGE_ID",
        "STUDENT CARD": "COLLEGE_ID",
        "VISA CARD": "VISA",
        "TOURIST VISA": "VISA",
        "ENTRY VISA": "VISA",
        "WORK VISA": "VISA",
        "STUDENT VISA": "VISA",
    }
    return aliases.get(raw, raw)


def check_document_profile(id_type: str, ocr_text: str, fields: dict[str, Any] | None = None) -> dict[str, Any]:
    normalized = _norm_id_type(id_type)
    profile = PROFILES.get(normalized)
    text = str(ocr_text or "").upper()
    fields = fields or {}
    if not profile:
        return {
            "available": False,
            "status": "UNAVAILABLE",
            "score": 0,
            "matchedAnchors": [],
            "matchedPatterns": [],
            "message": "No document-family profile is configured for this document type.",
        }

    anchors = [anchor for anchor in profile["anchors"] if anchor in text]
    patterns = [pattern.pattern for pattern in profile["patterns"] if pattern.search(text)]
    other_markers = [marker for marker in profile["other_markers"] if marker in text]


    if fields.get("document_number"):
        score = 35
    else:
        score = 0
    score += min(45, len(anchors) * 12)
    score += min(20, len(patterns) * 10)





    explicit_conflict = len(other_markers) >= 1 and len(anchors) == 0 and not patterns
    if explicit_conflict:
        return {
            "available": True,
            "status": "FAIL",
            "score": 0,
            "matchedAnchors": anchors,
            "matchedPatterns": patterns,
            "conflictingMarkers": other_markers,
            "message": "OCR content strongly resembles another document family rather than the selected type.",
        }

    if score >= 55:
        status = "PASS"
        message = "The OCR text and extracted structure are compatible with the selected document family."
    elif score >= 25:
        status = "REVIEW"
        message = "Some expected document-family cues were found, but the match is incomplete."
    else:
        status = "REVIEW"
        message = "The selected document type could not be confidently established from the available OCR evidence."

    return {
        "available": True,
        "status": status,
        "score": min(100, score),
        "matchedAnchors": anchors,
        "matchedPatterns": patterns,
        "conflictingMarkers": other_markers,
        "message": message,
    }
