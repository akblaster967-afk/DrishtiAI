from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from typing import Any


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def _similar(a: Any, b: Any) -> float:
    aa, bb = _norm(a), _norm(b)
    if not aa or not bb:
        return 0.0
    return SequenceMatcher(None, aa, bb).ratio()


def _extract_shared_fields(document: dict[str, Any]) -> dict[str, Any]:
    details = document.get("details") or {}
    if isinstance(details, str):
        try:
            details = json.loads(details)
        except Exception:
            details = {}
    fields = details.get("extractedFields") or details.get("extracted_fields") or {}
    if not isinstance(fields, dict):
        fields = {}

    return {
        "name": fields.get("name") or document.get("full_name"),
        "dob": fields.get("dob") or document.get("date_of_birth"),
    }


def build_cross_document_consistency(
    current_fields: dict[str, Any],
    existing_documents: list[dict[str, Any]] | None,
    current_id_type: str,
) -> dict[str, Any]:
    existing_documents = existing_documents or []
    usable = []
    for document in existing_documents:
        fields = _extract_shared_fields(document)
        if any(fields.values()):
            usable.append((document, fields))

    if not usable:
        return {
            "available": False,
            "status": "NOT_AVAILABLE",
            "score": 0,
            "band": "UNAVAILABLE",
            "matches": [],
            "reasons": [],
            "notice": "No previously stored document with comparable identity fields is available for cross-document checking.",
        }

    comparisons: list[dict[str, Any]] = []
    review_count = 0
    mismatch_count = 0
    current_name = current_fields.get("name")
    current_dob = current_fields.get("dob")

    for document, previous in usable:
        for field, current in (("name", current_name), ("dob", current_dob)):
            previous_value = previous.get(field)
            if not current or not previous_value:
                continue
            similarity = _similar(current, previous_value) if field == "name" else (1.0 if _norm(current) == _norm(previous_value) else 0.0)
            if similarity >= 0.92:
                status = "MATCH"
            elif similarity >= 0.70:
                status = "PARTIAL"
                review_count += 1
            else:
                status = "MISMATCH"
                mismatch_count += 1
            comparisons.append({
                "documentId": document.get("id"),
                "documentType": document.get("id_type"),
                "field": field,
                "current": current,
                "previous": previous_value,
                "similarity": round(similarity * 100, 1),
                "status": status,
            })

    if mismatch_count:
        score = min(10, 6 + min(4, mismatch_count * 2))
        band = "REVIEW"
        status = "REVIEW"
        reasons = ["Current identity details differ from a previously stored document for the same account."]
    elif review_count:
        score = 4
        band = "LOW"
        status = "REVIEW"
        reasons = ["Some identity details are only partially consistent with previously stored documents."]
    else:
        score = 0
        band = "LOW"
        status = "PASS"
        reasons = ["Shared identity fields are consistent with previously stored documents."]

    return {
        "available": True,
        "status": status,
        "score": score,
        "band": band,
        "comparedDocumentCount": len(usable),
        "matches": comparisons,
        "reasons": reasons,
        "notice": "Cross-document consistency is an account-level review aid; it does not query an external issuer and does not prove a legal name change or fraud.",
        "currentDocumentType": current_id_type,
    }
