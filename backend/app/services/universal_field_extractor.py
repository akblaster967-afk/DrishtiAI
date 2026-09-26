from __future__ import annotations

import re
from collections import OrderedDict
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any

KNOWN_DOCUMENT_TYPES = (
    "AADHAAR",
    "PAN",
    "PASSPORT",
    "DRIVING_LICENSE",
    "COLLEGE_ID",
    "NATIONAL_ID",
    "VISA",
)

_TYPE_ALIASES = {
    "AADHAR": "AADHAAR",
    "AADHAAR CARD": "AADHAAR",
    "AADHAR CARD": "AADHAAR",
    "AADAAR": "AADHAAR",
    "PAN CARD": "PAN",
    "PANCARD": "PAN",
    "DRIVING LICENSE": "DRIVING_LICENSE",
    "DRIVING-LICENSE": "DRIVING_LICENSE",
    "DRIVING LICENCE": "DRIVING_LICENSE",
    "DL": "DRIVING_LICENSE",
    "COLLEGE ID": "COLLEGE_ID",
    "COLLEGE-ID": "COLLEGE_ID",
    "COLLEGE ID CARD": "COLLEGE_ID",
    "STUDENT ID": "COLLEGE_ID",
    "STUDENT CARD": "COLLEGE_ID",
    "NATIONAL ID": "NATIONAL_ID",
    "NATIONAL IDENTIFICATION": "NATIONAL_ID",
    "NATIONAL ID CARD": "NATIONAL_ID",
    "NATIONAL_ID_CARD": "NATIONAL_ID",
    "VISA CARD": "VISA",
    "TOURIST VISA": "VISA",
    "ENTRY VISA": "VISA",
    "WORK VISA": "VISA",
    "STUDENT VISA": "VISA",
    "AUTO": "",
    "UNIVERSAL": "",
    "ANY": "",
    "UNKNOWN": "",
}


def normalize_document_type(value: Any) -> str:
    raw = str(value or "").strip().upper()
    raw = re.sub(r"[\s-]+", "_", raw)

    human = raw.replace("_", " ")
    return _TYPE_ALIASES.get(raw, _TYPE_ALIASES.get(human, raw))





FIELD_SPECS: "OrderedDict[str, dict[str, Any]]" = OrderedDict([
    ("name", {"kind": "name", "patterns": (
        r"full\s*name", r"holder\s*name", r"applicant\s*name", r"candidate\s*name",
        r"student\s*name", r"cardholder\s*name", r"person\s*name", r"name",
    )}),
    ("father_name", {"kind": "name", "patterns": (
        r"father(?:['’]s|s)?\s*name", r"father\s*name", r"father",
    )}),
    ("mother_name", {"kind": "name", "patterns": (
        r"mother(?:['’]s|s)?\s*name", r"mother\s*name", r"mother",
    )}),
    ("relation_name", {"kind": "name", "patterns": (
        r"son\s*/\s*daughter\s*/\s*wife\s*of", r"relation\s*name", r"guardian\s*name",
        r"spouse\s*name", r"husband\s*name", r"wife\s*name", r"relation",
    )}),
    ("dob", {"kind": "date", "patterns": (
        r"date\s*of\s*birth", r"birth\s*date", r"d\.?\s*o\.?\s*b", r"dob",
    )}),
    ("gender", {"kind": "gender", "patterns": (r"gender", r"sex")}),
    ("document_number", {"kind": "identifier", "patterns": (
        r"document\s*(?:no\.?|number|id)", r"identity\s*(?:no\.?|number|id)",
        r"id\s*(?:no\.?|number)", r"card\s*(?:no\.?|number)",
        r"certificate\s*(?:no\.?|number)", r"serial\s*(?:no\.?|number)",
        r"licen[sc]e\s*(?:no\.?|number)",
    )}),
    ("aadhaar_number", {"kind": "identifier", "patterns": (
        r"aadhaar\s*(?:no\.?|number|id)?", r"aadhar\s*(?:no\.?|number|id)?",
        r"uid(?:ai)?\s*(?:no\.?|number|id)?", r"unique\s*identification\s*(?:no\.?|number)?",
    )}),
    ("pan_number", {"kind": "identifier", "patterns": (
        r"permanent\s*account\s*(?:no\.?|number)", r"pan\s*(?:no\.?|number)",
    )}),
    ("passport_number", {"kind": "identifier", "patterns": (
        r"passport\s*(?:no\.?|number)", r"passport\s*id",
    )}),
    ("visa_number", {"kind": "identifier", "patterns": (
        r"visa\s*(?:no\.?|number)", r"visa\s*id",
    )}),
    ("roll_number", {"kind": "identifier", "patterns": (
        r"roll\s*(?:no\.?|number)", r"roll\s*id",
    )}),
    ("enrollment_number", {"kind": "identifier", "patterns": (
        r"enrol+l?ment\s*(?:no\.?|number|id)", r"enrollment\s*(?:no\.?|number|id)",
    )}),
    ("registration_number", {"kind": "identifier", "patterns": (
        r"registration\s*(?:no\.?|number|id)", r"reg(?:istration)?\s*no\.?",
    )}),
    ("erp_id", {"kind": "identifier", "patterns": (
        r"erp\s*(?:id|no\.?|number)", r"erp\s*id",
    )}),
    ("national_id_number", {"kind": "identifier", "patterns": (
        r"national\s*(?:id|identity)\s*(?:no\.?|number)", r"identity\s*card\s*(?:no\.?|number)",
        r"nid\s*(?:no\.?|number)",
    )}),
    ("address", {"kind": "address", "patterns": (
        r"permanent\s*address", r"residential\s*address", r"present\s*address", r"address",
    )}),
    ("issue_date", {"kind": "date", "patterns": (
        r"date\s*of\s*issue", r"issue\s*date", r"issued\s*on", r"date\s*issued",
    )}),
    ("expiry_date", {"kind": "date", "patterns": (
        r"date\s*of\s*expiry", r"date\s*of\s*expiration", r"expiry\s*date",
        r"expiration\s*date", r"valid\s*upto", r"valid\s*until", r"valid\s*till",
    )}),
    ("validity_nt", {"kind": "date", "patterns": (
        r"non\s*transport\s*validity", r"validity\s*\(?\s*nt\s*\)?", r"nt\s*validity",
    )}),
    ("validity_tr", {"kind": "date", "patterns": (
        r"transport\s*validity", r"validity\s*\(?\s*tr\s*\)?", r"tr\s*validity",
    )}),
    ("valid_until", {"kind": "date_or_range", "patterns": (
        r"valid\s*(?:till|until|upto)", r"validity\s*date", r"expires?\s*on",
    )}),
    ("passing_year", {"kind": "year", "patterns": (
        r"year\s*of\s*passing", r"passing\s*year", r"year\s*of\s*exam(?:ination)?",
        r"exam(?:ination)?\s*year", r"passed\s*in", r"year\s*passed",
    )}),
    ("school_name", {"kind": "text", "patterns": (
        r"name\s*of\s*school", r"school\s*name", r"school", r"secondary\s*school",
    )}),
    ("institution_name", {"kind": "text", "patterns": (
        r"institution\s*name", r"college\s*name", r"university\s*name", r"college", r"university", r"institute",
    )}),
    ("course", {"kind": "text", "patterns": (
        r"course", r"program(?:me)?", r"branch", r"department", r"stream", r"semester",
    )}),
    ("board", {"kind": "text", "patterns": (
        r"board\s*of\s*education", r"examination\s*board", r"board",
    )}),
    ("examination", {"kind": "text", "patterns": (
        r"examination", r"exam", r"class\s*(?:x|xi|xii)?", r"stream",
    )}),
    ("nationality", {"kind": "text", "patterns": (r"nationality",)}),
    ("surname", {"kind": "name", "patterns": (r"surname", r"family\s*name", r"last\s*name")}),
    ("given_names", {"kind": "name", "patterns": (r"given\s*names?", r"first\s*name", r"forename")}),
    ("place_of_birth", {"kind": "text", "patterns": (r"place\s*of\s*birth", r"birth\s*place")}),
    ("place_of_issue", {"kind": "text", "patterns": (r"place\s*of\s*issue", r"issue\s*place")}),
    ("blood_group", {"kind": "blood_group", "patterns": (r"blood\s*group", r"blood\s*grp")}),
    ("organ_donor", {"kind": "yes_no", "patterns": (r"organ\s*donor", r"donor")}),
    ("phone", {"kind": "phone", "patterns": (r"phone\s*(?:no\.?|number)", r"mobile\s*(?:no\.?|number)", r"contact\s*(?:no\.?|number)")}),
    ("email", {"kind": "email", "patterns": (r"e[-\s]?mail", r"email\s*address")}),
    ("pincode", {"kind": "postal_code", "patterns": (r"pin\s*code", r"postal\s*code", r"zip\s*code")}),
    ("state", {"kind": "text", "patterns": (r"state",)}),
    ("district", {"kind": "text", "patterns": (r"district", r"dist")}),
    ("country", {"kind": "text", "patterns": (r"country", r"nationality")}),
    ("occupation", {"kind": "text", "patterns": (r"occupation", r"profession")}),
    ("marital_status", {"kind": "text", "patterns": (r"marital\s*status",)}),
    ("issuing_authority", {"kind": "text", "patterns": (r"issuing\s*authority", r"issued\s*by", r"authority")}),
    ("document_type", {"kind": "text", "patterns": (r"document\s*type", r"type\s*of\s*document")}),
])




DOCUMENT_FIELD_SCHEMAS: dict[str, tuple[str, ...]] = {
    "AADHAAR": ("name", "father_name", "mother_name", "relation_name", "dob", "gender", "document_number", "address"),
    "PAN": ("name", "father_name", "mother_name", "dob", "gender", "document_number", "address"),
    "PASSPORT": ("name", "surname", "given_names", "dob", "document_number", "nationality", "gender", "issue_date", "expiry_date", "place_of_birth", "place_of_issue"),
    "DRIVING_LICENSE": ("name", "father_name", "mother_name", "relation_name", "dob", "document_number", "address", "gender", "issue_date", "validity_nt", "validity_tr", "expiry_date", "phone"),
    "COLLEGE_ID": ("name", "document_number", "roll_number", "erp_id", "enrollment_number", "dob", "course", "institution_name", "valid_until"),
    "NATIONAL_ID": ("name", "father_name", "mother_name", "dob", "gender", "document_number", "national_id_number", "address", "nationality", "issue_date", "expiry_date", "phone", "email"),
    "VISA": ("name", "surname", "given_names", "dob", "document_number", "visa_number", "passport_number", "nationality", "gender", "issue_date", "expiry_date", "place_of_birth", "place_of_issue"),
}

_COMMON_FIELDS = (
    "name", "document_number", "dob", "gender", "address", "issue_date",
    "expiry_date", "valid_until", "nationality", "phone", "email",
)
ALL_FIELD_KEYS = tuple(FIELD_SPECS.keys())



_IDENTIFIER_ALIAS_TARGETS = {
    "aadhaar_number": "document_number",
    "pan_number": "document_number",
    "passport_number": "document_number",
    "visa_number": "document_number",
    "roll_number": "document_number",
    "national_id_number": "document_number",
}

def fields_for_document(id_type: Any, detected_type: str | None = None, universal: bool = False) -> tuple[str, ...]:
    normalized = normalize_document_type(id_type)
    if universal or not normalized:
        return ALL_FIELD_KEYS
    if normalized in DOCUMENT_FIELD_SCHEMAS:
        values = DOCUMENT_FIELD_SCHEMAS[normalized] + _COMMON_FIELDS
        return tuple(dict.fromkeys(values))
    return ALL_FIELD_KEYS


def get_document_field_schema(id_type: Any) -> tuple[str, ...]:
    return fields_for_document(id_type)


def _detection_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).upper()


def detect_document_type_details(
    text: str,
    fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    upper = _detection_text(text)
    fields = fields or {}
    scores: dict[str, int] = {key: 0 for key in KNOWN_DOCUMENT_TYPES}
    evidence: dict[str, list[str]] = {key: [] for key in KNOWN_DOCUMENT_TYPES}

    def hit(kind: str, label: str, pattern: str, weight: int) -> None:
        if re.search(pattern, upper, re.IGNORECASE):
            scores[kind] += weight
            evidence[kind].append(label)

    for kind, markers in {
        "AADHAAR": (
            ("Aadhaar/UIDAI", r"\b(?:AADHAAR|AADHAR|UIDAI)\b", 38),
            ("unique identification authority", r"UNIQUE\s+IDENTIFICATION", 22),
        ),
        "PAN": (
            ("permanent account", r"PERMANENT\s+ACCOUNT", 38),
            ("PAN card", r"\bPAN\s*(?:CARD|NUMBER|NO\.?)\b", 32),
            ("income tax", r"INCOME\s+TAX", 18),
            ("PAN label", r"\bPAN\b", 30),
        ),
        "PASSPORT": (
            ("passport", r"\bPASSPORT\b", 38),
            ("surname/given names", r"\b(?:SURNAME|GIVEN\s+NAMES?)\b", 18),
            ("nationality", r"\bNATIONALITY\b", 8),
        ),
        "DRIVING_LICENSE": (
            ("driving licence", r"DRIVING\s+LICEN[SC]E", 40),
            ("transport/validity", r"\b(?:TRANSPORT|VALIDITY)\b", 14),
            ("DL label", r"\bDL\s*(?:NO|NUMBER)?\b", 18),
        ),
        "COLLEGE_ID": (
            ("college/student", r"\b(?:COLLEGE|STUDENT|UNIVERSITY|INSTITUTE)\b", 24),
            ("roll/ERP/course", r"\b(?:ROLL|ERP|COURSE|PROGRAMME|PROGRAM)\b", 24),
        ),
        "NATIONAL_ID": (
            ("national ID", r"\bNATIONAL\s+(?:ID|IDENTITY)\b", 42),
            ("identity card", r"\bIDENTITY\s+CARD\b", 24),
            ("NID", r"\bNID\b", 16),
        ),
        "VISA": (
            ("visa", r"\bVISA\b", 42),
            ("entry permit", r"\bENTRY\s+PERMIT\b", 28),
            ("immigration", r"\bIMMIGRATION\b", 18),
        ),
    }.items():
        for label, pattern, weight in markers:
            hit(kind, label, pattern, weight)


    number = str(fields.get("document_number") or "")
    if re.fullmatch(r"\d{4}[ -]?\d{4}[ -]?\d{4}", number):
        scores["AADHAAR"] += 20
        evidence["AADHAAR"].append("12-digit identifier shape")
    if re.fullmatch(r"[A-Z]{5}\d{4}[A-Z]", re.sub(r"\s+", "", number.upper())):
        scores["PAN"] += 24
        evidence["PAN"].append("PAN identifier shape")
    if re.search(r"\bP<[A-Z]{3}", upper):
        scores["PASSPORT"] += 35
        evidence["PASSPORT"].append("passport MRZ")
    if re.fullmatch(r"[A-Z]{2}\d{9,17}", re.sub(r"[^A-Z0-9]", "", number.upper())):
        scores["DRIVING_LICENSE"] += 22
        evidence["DRIVING_LICENSE"].append("driving-licence identifier shape")

    best_type = max(scores, key=lambda key: scores.get(key, 0)) if scores else None
    best_score = int(scores.get(best_type, 0)) if best_type else 0

    if best_score < 25:
        best_type = None
        best_score = 0
    ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    return {
        "documentType": best_type,
        "detectedType": best_type,
        "confidence": min(100, best_score),
        "scores": dict(ordered),
        "evidence": {key: value for key, value in evidence.items() if value},
    }


def detect_document_type(text: str, fields: dict[str, Any] | None = None) -> str | None:
    return detect_document_type_details(text, fields).get("documentType")





_COMPILED_LABELS: list[tuple[str, re.Pattern[str], int, str]] = []
for _field, _spec in FIELD_SPECS.items():
    for _order, _pattern in enumerate(_spec["patterns"]):
        try:
            _compiled = re.compile(
                rf"(?<![A-Za-z])(?:{_pattern})(?![A-Za-z])",
                re.IGNORECASE,
            )
        except re.error:
            continue
        _COMPILED_LABELS.append((_field, _compiled, _order, _spec["kind"]))


def _looks_like_label_context(line: str, start: int, end: int) -> bool:
    if start > 0 and (line[start - 1].isalnum() or line[start - 1] == "_"):
        return False
    tail = line[end:]
    if not tail:
        return True


    return (
        tail[0].isspace()
        or tail[0] in ":=#|-–—;,/([<"
        or tail[0].isdigit()
    )


def _label_matches(line: str) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for field, pattern, order, kind in _COMPILED_LABELS:
        for match in pattern.finditer(line or ""):
            if not _looks_like_label_context(line, match.start(), match.end()):
                continue
            candidates.append({
                "field": field,
                "kind": kind,
                "start": match.start(),
                "end": match.end(),
                "label": re.sub(r"\s+", " ", line[match.start():match.end()]).strip(),
                "order": order,
                "length": match.end() - match.start(),
            })

    candidates.sort(key=lambda item: (item["start"], -item["length"], item["order"]))
    selected: list[dict[str, Any]] = []
    for candidate in candidates:
        overlap = next(
            (
                index for index, existing in enumerate(selected)
                if candidate["start"] < existing["end"] and existing["start"] < candidate["end"]
            ),
            None,
        )
        if overlap is None:
            selected.append(candidate)
            continue
        existing = selected[overlap]
        if (candidate["length"], -candidate["order"]) > (existing["length"], -existing["order"]):
            selected[overlap] = candidate
    selected.sort(key=lambda item: item["start"])
    return selected


def _label_words(value: str) -> set[str]:
    return {
        item["label"].lower().replace(".", "")
        for item in _label_matches(str(value or ""))
    }


def _normalize_ocr_text(value: str) -> str:
    text = str(value or "").replace("\r", "")
    text = text.replace("’", "'").replace("‘", "'")
    text = text.replace("–", "-").replace("—", "-").replace("−", "-")
    text = text.replace("\u00a0", " ")
    return text


def _strip_value(value: Any) -> str:
    text = _normalize_ocr_text(value).strip()
    text = re.sub(r"^[\s:;#=|/\\-]+", "", text)
    text = re.sub(r"[\s:;#=|/\\-]+$", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _remove_leading_label(value: str) -> str:
    text = _strip_value(value)
    matches = _label_matches(text)
    if matches and matches[0]["start"] <= 2:
        text = text[matches[0]["end"]:]
    text = re.sub(
        r"^(?:full\s*name|holder\s*name|applicant\s*name|candidate\s*name|"
        r"student\s*name|cardholder\s*name|name|father(?:['’]s|s)?\s*name|"
        r"father|mother(?:['’]s|s)?\s*name|mother|dob|date\s*of\s*birth|"
        r"gender|sex|address|surname|given\s*names?|nationality)\s*[:=\-]?\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )
    return _strip_value(text)


def _numeric_date(value: str) -> str | None:
    text = _strip_value(value)
    match = re.search(
        r"(?<!\d)(\d{1,4}\s*[-/.]\s*\d{1,2}\s*[-/.]\s*\d{1,4})(?!\d)",
        text,
    )
    if not match:
        return None
    candidate = re.sub(r"\s+", "", match.group(1)).replace(".", "/")
    parts = re.split(r"[-/]", candidate)
    try:
        if len(parts[0]) == 4:
            year, month, day = (int(parts[0]), int(parts[1]), int(parts[2]))
        else:
            day, month, year = (int(parts[0]), int(parts[1]), int(parts[2]))
        if year < 100:
            year += 2000 if year <= 49 else 1900
        datetime(year, month, day)
    except (TypeError, ValueError):
        return None
    return candidate


def _clean_date_value(value: str, allow_range: bool = False) -> str | None:
    text = _remove_leading_label(value)
    numeric = _numeric_date(text)
    if numeric:
        return numeric
    if allow_range:
        compact = re.sub(r"\s+", " ", text).strip(" .:-")
        if re.search(r"(?:19|20)\d{2}", compact) and len(compact) <= 60:
            return compact

    if re.search(
        r"\b(?:19|20)\d{2}\b|\b(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[A-Z]*\b",
        text,
        re.IGNORECASE,
    ) and len(text) <= 60:
        return text
    return None


def _clean_year(value: str) -> str | None:
    text = _remove_leading_label(value)
    match = re.search(r"(?<!\d)((?:19|20)\d{2})(?!\d)", text)
    return match.group(1) if match else None


def _clean_name_value(value: str, relation: bool = False) -> str | None:
    text = _remove_leading_label(value)
    if re.search(
        r"\b(?:valid\s+unless\s+physically\s+signed|important\s+instructions|"
        r"see\s+overleaf|cum\s*-?\s*marks|for\s+important\s+instructions)\b",
        text,
        re.IGNORECASE,
    ):
        return None
    text = re.sub(
        r"^\s*(?:son\s*/\s*daughter\s*/\s*wife\s*of|s\s*/\s*o|d\s*/\s*o|"
        r"w\s*/\s*o|c\s*/\s*o|son\s+of|daughter\s+of|wife\s+of|husband\s+of|"
        r"father|mother|relation|guardian)\s*[:=\-]?\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\b(?:date\s*of\s*birth|dob|gender|sex|address|nationality|valid\s*(?:till|until)|"
        r"issue\s*date|expiry\s*date|phone|mobile|email)\b.*$",
        "",
        text,
        flags=re.IGNORECASE,
    )
    words = re.findall(r"[A-Za-z][A-Za-z.'-]*", text)
    if not words:
        words = re.findall(r"[^\W\d_][\w.'-]*", text, flags=re.UNICODE)
    if not words:
        return None
    blocked = {
        "name", "full", "holder", "candidate", "student", "cardholder", "father",
        "mother", "male", "female", "gender", "sex", "address", "dob", "date",
        "birth", "nationality", "passport", "aadhaar", "pan", "valid", "till",
        "validity", "phone", "mobile", "email", "college", "university", "school",
        "certificate", "board", "roll", "number", "id", "government", "india",
    }
    filtered = [word for word in words if word.lower() not in blocked]
    if not filtered:
        return None


    if len(filtered) > 6:
        filtered = filtered[:5]
    result = " ".join(filtered).strip(" .-'")
    if len(result) < 2:
        return None
    if len(result.split()) < 2 or any(len(word) == 1 for word in result.split()):
        return None
    if relation and len(result.split()) == 1 and len(result) < 4:
        return None
    return result


def _verhoeff_valid(number: str) -> bool:
    try:
        from app.services.checksums import verhoeff_is_valid
        return bool(verhoeff_is_valid(number))
    except Exception:
        return False


def _clean_identifier_value(
    value: str,
    field: str,
    id_type: str = "",
) -> str | None:
    text = _remove_leading_label(value)
    text = re.sub(
        r"^(?:permanent\s*account|pan|aadhaar|aadhar|passport|visa|roll|"
        r"enrollment|enrolment|registration|erp|nid|document|identity|card|"
        r"certificate|serial|licen[sc]e|id)\s*(?:no\.?|number|id)?\s*[:=\-]?\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = _strip_value(text)
    if not text:
        return None
    if re.search(r"\b(?:not\s+available|unknown|na|nil|none)\b", text, re.I):
        return None
    text = re.sub(r"\s*([-/])\s*", r"\1", text)
    compact = re.sub(r"[^A-Za-z0-9]", "", text).upper()
    if not compact:
        return None
    if compact in {
        "AADHAAR", "AADHAR", "PAN", "PASSPORT", "VISA", "ROLL", "NUMBER", "NO",
        "ID", "CARD", "DOCUMENT", "CERTIFICATE", "DATE", "DOB", "N/A",
    }:
        return None
    if re.fullmatch(r"(?:19|20)\d{2}", compact):
        return None
    if re.search(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}", text):
        return None

    if field == "aadhaar_number" or (field == "document_number" and id_type == "AADHAAR"):
        digits = re.sub(r"\D", "", text)
        if len(digits) != 12 or not _verhoeff_valid(digits):
            return None
        return digits
    if field == "pan_number" or (field == "document_number" and id_type == "PAN"):
        if not re.fullmatch(r"[A-Z]{5}\d{4}[A-Z]", compact):
            return None
        return compact
    if field == "passport_number" or (field == "document_number" and id_type == "PASSPORT"):
        candidate = compact.replace("<", "")
        return candidate if 6 <= len(candidate) <= 9 and re.search(r"\d", candidate) else None
    if field == "document_number" and id_type == "DRIVING_LICENSE":
        candidate = re.sub(r"[^A-Z0-9]", "", text.upper())
        return candidate if re.fullmatch(r"[A-Z]{2}\d{9,17}", candidate) else None
    if field in {"roll_number", "registration_number", "enrollment_number", "erp_id", "national_id_number", "visa_number"}:
        if len(compact) < 3 or len(compact) > 40:
            return None
        if field == "erp_id" and not re.search(r"\d", compact):
            return None
        return text.upper()
    if field == "document_number":
        if len(compact) < 4 or len(compact) > 40:
            return None

        if compact.isdigit() and 10 <= len(compact) <= 15 and field == "document_number":
            return None
        return compact
    return compact if 3 <= len(compact) <= 40 else None


def _clean_address_value(value: str) -> str | None:
    text = _remove_leading_label(value)
    text = re.sub(
        r"^\s*(?:s\s*/\s*o|d\s*/\s*o|w\s*/\s*o|c\s*/\s*o|son\s*/\s*daughter\s*/\s*wife\s*of|"
        r"son\s+of|daughter\s+of|wife\s+of)\s*[:=\-]?\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\b(?:please\s+(?:enter|provide)|should\s+be\s+updated|update|upload|submit|"
        r"click|select|choose)\b.*$",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\s+", " ", text).strip(" .,:;-")
    if len(text) < 5 or not re.search(r"[A-Za-z]{2,}", text):
        return None
    return text


def _clean_generic_value(value: str, field: str, id_type: str = "") -> str | None:
    kind = FIELD_SPECS.get(field, {}).get("kind", "text")
    if kind == "name":
        return _clean_name_value(value, relation=field in {"father_name", "mother_name", "relation_name"})
    if kind == "date":
        return _clean_date_value(value)
    if kind == "date_or_range":
        return _clean_date_value(value, allow_range=True)
    if kind == "year":
        return _clean_year(value)
    if kind == "identifier":
        return _clean_identifier_value(value, field, id_type)
    if kind == "address":
        return _clean_address_value(value)
    if kind == "gender":
        upper = _strip_value(value).upper()
        if re.search(r"\bMALE\b|\bM\b", upper):
            return "MALE"
        if re.search(r"\bFEMALE\b|\bF\b", upper):
            return "FEMALE"
        if re.search(r"\bOTHER\b|\bO\b", upper):
            return "OTHER"
        return None
    if kind == "blood_group":
        match = re.search(r"\b(?:A|B|AB|O)\s*([+-])\b", _strip_value(value).upper())
        return re.sub(r"\s+", "", match.group(0)) if match else None
    if kind == "yes_no":
        upper = _strip_value(value).upper()
        if re.search(r"\b(?:YES|Y)\b", upper):
            return "YES"
        if re.search(r"\b(?:NO|N)\b", upper):
            return "NO"
        return None
    if kind == "email":
        match = re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", _strip_value(value))
        return match.group(0) if match else None
    if kind == "phone":
        digits = re.sub(r"\D", "", _strip_value(value))
        return re.sub(r"\s+", "", _strip_value(value)) if 7 <= len(digits) <= 15 else None
    if kind == "postal_code":
        match = re.search(r"\b\d{5,6}\b", _strip_value(value))
        return match.group(0) if match else None

    text = _remove_leading_label(value)
    text = re.sub(r"\s+", " ", text).strip(" :#=|-\t")
    if not text or len(text) < 2:
        return None
    if text.lower() in {"name", "number", "no", "id", "card", "address", "date", "valid", "none", "n/a"}:
        return None
    if field in {"school_name", "institution_name"} and re.search(
        r"\b(?:certificate|marksheet|mark\s*sheet|examination|exam|overleaf|instructions?|cum\s*-?\s*marks|"
        r"year\s+of\s+passing|passing\s+year)\b|\b(?:19|20)\d{2}\b",
        text,
        re.IGNORECASE,
    ):
        return None

    if len(_label_words(text)) == 1 and len(text.split()) <= 2:
        return None
    return text


def _line_entries(text: str) -> list[tuple[int, str]]:
    return [
        (index, re.sub(r"\s+", " ", line).strip())
        for index, line in enumerate(_normalize_ocr_text(text).splitlines())
        if line.strip()
    ]


def _meaningful_segment(value: str) -> bool:
    text = _strip_value(value)
    if not text:
        return False
    if not re.search(r"[A-Za-z0-9@]", text):
        return False

    if _label_matches(text) and len(_label_matches(text)) == 1:
        match = _label_matches(text)[0]
        if match["start"] <= 1 and len(text) <= match["length"] + 3:
            return False
    return True


def _line_starts_with_label(line: str) -> bool:
    text = str(line or "").lstrip(" :#=|-\t")
    matches = _label_matches(text)
    return bool(matches and matches[0]["start"] == 0)


def _row_value(field: str, raw: str, position: int, total: int) -> str:
    kind = FIELD_SPECS.get(field, {}).get("kind", "text")
    text = _strip_value(raw)
    if kind == "date" or kind == "date_or_range":
        return _numeric_date(text) or text
    if kind == "year":
        match = re.search(r"(?<!\d)((?:19|20)\d{2})(?!\d)", text)
        return match.group(1) if match else text
    if kind == "gender":
        match = re.search(r"\b(?:MALE|FEMALE|OTHER|M|F|O)\b", text, re.I)
        return match.group(0) if match else text
    if kind == "identifier":


        if field in {"erp_id", "national_id_number"}:
            match = re.search(r"\b\d{3,20}\b", text)
            if match:
                return match.group(0)
        tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9./-]{2,30}", text)
        mixed = [token for token in tokens if re.search(r"[A-Za-z]", token) and re.search(r"\d", token)]
        if mixed:
            return mixed[0]
        if tokens:
            return tokens[0]
    if kind == "name":

        match = re.match(
            r"^\s*([A-Za-z][A-Za-z .'-]{1,60}?)(?=\s*(?:\d|[|,;])|$)",
            text,
        )
        if match:
            return match.group(1)
    parts = [
        part.strip() for part in re.split(r"\s*\|\s*|\t+|\s{2,}", text)
        if part.strip()
    ]
    if parts:
        return parts[min(position, len(parts) - 1)]
    return text


def _reference_similarity(field: str, value: str, reference_fields: dict[str, Any]) -> float:
    reference = str(reference_fields.get(field) or "").strip()
    if not reference:
        return 0.0
    if field in {"name", "father_name", "mother_name", "relation_name", "surname", "given_names"}:
        left = re.sub(r"[^a-z0-9]", "", value.lower())
        right = re.sub(r"[^a-z0-9]", "", reference.lower())
    else:
        left = re.sub(r"[^A-Z0-9]", "", value.upper())
        right = re.sub(r"[^A-Z0-9]", "", reference.upper())
    return SequenceMatcher(None, left, right).ratio() if left and right else 0.0


def _candidate_score(
    field: str,
    value: str,
    source: str,
    reference_fields: dict[str, Any],
    ocr_confidence: float,
) -> float:
    score = {"SAME_LINE": 96.0, "NEXT_LINE": 84.0, "MULTI_LINE": 78.0, "VALUE_ROW": 80.0}.get(source, 80.0)
    if field in _IDENTIFIER_ALIAS_TARGETS or field == "document_number":
        score += 3.0
    if field == "address":
        score += min(5.0, len(value) / 40.0)
    score += _reference_similarity(field, value, reference_fields) * 4.0
    if ocr_confidence > 0:
        ratio = max(0.0, min(1.0, ocr_confidence / 100.0))
        score *= 0.78 + (0.22 * ratio)
    return round(max(0.0, min(99.0, score)), 1)


def _collect_candidates(
    text: str,
    active_fields: set[str],
    id_type: str,
    reference_fields: dict[str, Any],
    ocr_confidence: float,
) -> dict[str, list[dict[str, Any]]]:
    entries = _line_entries(text)
    candidates: dict[str, list[dict[str, Any]]] = {}

    for position, (line_index, line) in enumerate(entries):
        matches = _label_matches(line)
        if not matches:
            continue


        row_mode = len(matches) > 1 and all(
            not _meaningful_segment(line[item["end"]: (matches[index + 1]["start"] if index + 1 < len(matches) else len(line))])
            for index, item in enumerate(matches)
        )
        next_entry = entries[position + 1] if position + 1 < len(entries) else None
        for match_index, match in enumerate(matches):
            field = match["field"]
            if field not in active_fields:
                continue
            if field == "school_name" and re.search(
                r"\b(?:high\s*school|secondary|matriculation)\b.*\b(?:certificate|marksheet|mark\s*sheet)\b",
                line,
                re.IGNORECASE,
            ):
                continue
            next_start = matches[match_index + 1]["start"] if match_index + 1 < len(matches) else len(line)
            segment = line[match["end"]:next_start]
            source = "SAME_LINE"
            raw = _strip_value(segment)
            if not _meaningful_segment(segment):

                if match_index + 1 < len(matches) and not row_mode:
                    continue
                raw = ""
                if next_entry and (
                    not _line_starts_with_label(next_entry[1])
                    or field in {"school_name", "institution_name"}
                ):
                    next_line = next_entry[1]
                    if field == "address":
                        parts = [next_line]
                        for _, later_line in entries[position + 2:position + 6]:
                            if _line_starts_with_label(later_line):
                                break
                            parts.append(later_line)
                        raw = ", ".join(parts)
                        source = "MULTI_LINE"
                    else:
                        for _, later_line in entries[position + 1:position + 5]:
                            if _line_starts_with_label(later_line):
                                if field in {"school_name", "institution_name"} and _clean_generic_value(later_line, field, id_type) is None:
                                    continue
                                break
                            if _clean_generic_value(later_line, field, id_type):
                                raw = later_line
                                source = "NEXT_LINE"
                                break
                elif row_mode and next_entry:
                    raw = next_entry[1]
                    source = "VALUE_ROW"
            elif row_mode:
                raw = _row_value(field, next_entry[1] if next_entry else "", match_index, len(matches))
                source = "VALUE_ROW"
            if not _meaningful_segment(raw):
                continue
            value = _clean_generic_value(raw, field, id_type)
            if not value:
                continue
            evidence = {
                "field": field,
                "label": match["label"],
                "value": value,
                "rawValue": _strip_value(raw),
                "line": line_index,
                "source": source,
            }
            candidates.setdefault(field, []).append({
                "value": value,
                "label": match["label"],
                "line": line_index,
                "source": source,
                "evidence": evidence,
                "score": _candidate_score(field, value, source, reference_fields, ocr_confidence),
            })
    return candidates


def _choose_candidate(field: str, items: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not items:
        return None
    normalized = []
    for item in items:
        value = str(item.get("value") or "")
        if field in _IDENTIFIER_ALIAS_TARGETS or field == "document_number":
            key = re.sub(r"[^A-Z0-9]", "", value.upper())
        else:
            key = re.sub(r"[^A-Z0-9]+", " ", value.upper()).strip()
        normalized.append((key, item))



    return max(
        normalized,
        key=lambda pair: (
            pair[1].get("score", 0.0),
            len(str(pair[1].get("value") or "")) if field == "address" else 0,
            -int(pair[1].get("line", 0)),
        ),
    )[1]


def extract_universal_field_result(
    text: str,
    id_type: Any = "",
    reference_fields: dict[str, Any] | None = None,
    ocr_confidence: float = 0.0,
) -> dict[str, Any]:
    normalized_text = _normalize_ocr_text(text)
    normalized_type = normalize_document_type(id_type)
    reference_fields = reference_fields or {}
    initial_detection = detect_document_type_details(normalized_text)
    universal_mode = not normalized_type
    active = set(fields_for_document(id_type, initial_detection.get("documentType"), universal=universal_mode))


    for alias, target in _IDENTIFIER_ALIAS_TARGETS.items():
        if target in active:
            active.add(alias)
    try:
        confidence = float(ocr_confidence or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    observations = _collect_candidates(
        normalized_text,
        active,
        normalized_type or str(initial_detection.get("documentType") or ""),
        reference_fields,
        confidence,
    )

    selected: dict[str, dict[str, Any]] = {}
    for field, items in observations.items():
        chosen = _choose_candidate(field, items)
        if chosen:
            selected[field] = chosen

    fields: dict[str, Any] = {}
    for field, item in selected.items():
        value = item["value"]
        reference = str(reference_fields.get(field) or (reference_fields.get("name") if field == "name" else "")).strip()
        if reference and field in {"name", "father_name", "mother_name", "relation_name"}:
            left = re.sub(r"[^a-z0-9]", "", value.lower())
            right = re.sub(r"[^a-z0-9]", "", reference.lower())
            if SequenceMatcher(None, left, right).ratio() >= 0.62:
                value = reference
        fields[field] = value
    field_confidence = {
        field: round(float(item.get("score") or 0.0), 1)
        for field, item in selected.items()
    }
    field_sources = {
        field: item.get("source", "LABEL_ANCHOR")
        for field, item in selected.items()
    }
    field_evidence = {
        field: item.get("evidence", {})
        for field, item in selected.items()
    }



    for alias, target in _IDENTIFIER_ALIAS_TARGETS.items():
        if target in active and alias in fields and target not in fields:
            fields[target] = fields[alias]
            field_confidence[target] = field_confidence.get(alias, 0.0)
            field_sources[target] = field_sources.get(alias, "LABEL_ANCHOR")
            field_evidence[target] = field_evidence.get(alias, {})
    if normalized_type in {"AADHAAR", "DRIVING_LICENSE"} and "relation_name" in fields and "father_name" not in fields:
        fields["father_name"] = fields["relation_name"]
        field_confidence["father_name"] = field_confidence.get("relation_name", 0.0)
        field_sources["father_name"] = field_sources.get("relation_name", "LABEL_ANCHOR")
        field_evidence["father_name"] = field_evidence.get("relation_name", {})


    final_detection = detect_document_type_details(normalized_text, fields)
    schema_fields = list(fields_for_document(id_type, final_detection.get("documentType"), universal=universal_mode))
    return {
        "fields": fields,
        "fieldConfidence": field_confidence,
        "fieldSources": field_sources,
        "fieldEvidence": field_evidence,
        "availableFields": sorted(fields),
        "missingFields": [field for field in schema_fields if field not in fields],
        "schemaFields": schema_fields,
        "detectedDocumentType": final_detection.get("documentType"),
        "documentDetection": final_detection,
        "universalMode": universal_mode,
        "labelCount": sum(len(items) for items in observations.values()),
    }


def extract_universal_fields(
    text: str,
    id_type: Any = "",
    reference_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return extract_universal_field_result(text, id_type, reference_fields).get("fields", {})




infer_document_type = detect_document_type
infer_document_type_details = detect_document_type_details
extract_fields_universal = extract_universal_fields
