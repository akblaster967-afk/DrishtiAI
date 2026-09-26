from __future__ import annotations

import re
from datetime import date, datetime


def _parse_date(value):
    if not value:
        return None
    raw = str(value).strip()
    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _aadhaar_verhoeff(number: str) -> bool:

    d = [[0,1,2,3,4,5,6,7,8,9],[1,2,3,4,0,6,7,8,9,5],[2,3,4,0,1,7,8,9,5,6],[3,4,0,1,2,8,9,5,6,7],[4,0,1,2,3,9,5,6,7,8],[5,9,6,7,8,0,4,3,2,1],[6,5,7,8,9,1,0,2,3,4],[7,8,9,5,6,2,1,0,4,3],[8,7,5,6,9,3,2,1,0,4],[9,6,8,7,5,4,3,2,1,0]]
    p = [[0,1,2,3,4,5,6,7,8,9],[1,5,7,6,2,8,3,0,9,4],[5,8,0,3,7,9,6,1,4,2],[8,9,1,6,0,4,3,5,2,7],[9,4,5,3,1,2,6,8,7,0],[4,2,8,6,5,7,3,9,0,1],[2,7,9,3,8,0,6,4,1,5],[7,0,4,6,9,1,3,2,5,8]]
    inv = [0,4,3,2,1,5,6,7,8,9]
    try:
        digits = [int(x) for x in number]
    except ValueError:
        return False
    c = 0
    for i, digit in enumerate(reversed(digits)):
        c = d[c][p[i % 8][digit]]
    return c == 0


def check_document_consistency(id_type: str, fields: dict) -> dict:
    t = str(id_type or "").strip().upper().replace(" ", "_")
    f = fields or {}
    checks = []

    def add(name, status, message, severity="LOW"):
        checks.append({"check": name, "status": status, "severity": severity, "message": message})

    dob = _parse_date(f.get("dob"))
    issue = _parse_date(f.get("issue_date"))
    nt = _parse_date(f.get("validity_nt"))
    tr = _parse_date(f.get("validity_tr"))

    if dob and issue:
        if dob >= issue:
            add("DOB_BEFORE_ISSUE", "FAIL", "Date of birth is not earlier than the issue date.", "HIGH")
        else:
            add("DOB_BEFORE_ISSUE", "PASS", "Date of birth is earlier than the issue date.")

    for label, start, end in (("NT_VALIDITY", issue, nt), ("TR_VALIDITY", issue, tr)):
        if start and end:
            if end <= start:
                add(label, "FAIL", "Validity date is not later than the issue date.", "HIGH")
            else:
                add(label, "PASS", "Validity date is later than the issue date.")

    if t in {"AADHAAR", "AADHAR", "AADHAAR_CARD", "AADHAR_CARD"} and f.get("document_number"):
        number = re.sub(r"\D", "", str(f["document_number"]))
        if len(number) == 12:
            add("AADHAAR_FORMAT", "PASS", "12-digit Aadhaar number format detected.")
            add("AADHAAR_CHECKSUM", "PASS" if _aadhaar_verhoeff(number) else "FAIL",
                "Aadhaar checksum is internally consistent." if _aadhaar_verhoeff(number) else "Aadhaar checksum is inconsistent; the number may contain an OCR or alteration error.",
                "LOW" if _aadhaar_verhoeff(number) else "HIGH")

    if t == "PAN" and f.get("document_number"):
        pan = re.sub(r"\s+", "", str(f["document_number"]).upper())
        ok = bool(re.fullmatch(r"[A-Z]{5}[0-9]{4}[A-Z]", pan))
        add("PAN_FORMAT", "PASS" if ok else "FAIL",
            "PAN structure is valid." if ok else "PAN structure is inconsistent.", "LOW" if ok else "HIGH")

    if t in {"DRIVING_LICENSE", "DRIVING_LICENSE"} and f.get("document_number"):
        dl = re.sub(r"[^A-Z0-9]", "", str(f["document_number"]).upper())
        ok = bool(re.fullmatch(r"[A-Z]{2}\d{2}(?:19|20)\d{2}\d{4,8}", dl))
        add("DL_FORMAT", "PASS" if ok else "FAIL",
            "Driving licence number follows an Indian state/RTO/year/serial pattern." if ok else "Driving licence number does not match the expected Indian pattern.",
            "LOW" if ok else "HIGH")
        if ok and issue:
            year = int(dl[4:8])
            if year != issue.year:
                add("DL_YEAR_CONSISTENCY", "REVIEW", "The year embedded in the licence number differs from the issue year.", "MEDIUM")
            else:
                add("DL_YEAR_CONSISTENCY", "PASS", "Licence number year agrees with the issue year.")

    if f.get("address"):
        pin = re.search(r"\b\d{6}\b", str(f["address"]))
        add("ADDRESS_COMPLETENESS", "PASS" if pin else "REVIEW",
            "Address contains a 6-digit PIN code." if pin else "Address was extracted but no 6-digit PIN code was detected.",
            "LOW" if pin else "MEDIUM")


    if t in {"PASSPORT", "PASSPORT_CARD"} and f.get("document_number"):
        passport = re.sub(r"[^A-Z0-9]", "", str(f["document_number"]).upper())
        ok = bool(re.fullmatch(r"[A-Z][A-Z0-9]{7,8}", passport))
        add("PASSPORT_FORMAT", "PASS" if ok else "REVIEW",
            "Passport number has a plausible machine-readable structure." if ok else "Passport number format needs manual review.",
            "LOW" if ok else "MEDIUM")
        expiry = _parse_date(f.get("expiry_date"))
        if issue and expiry:
            add("PASSPORT_DATE_ORDER", "PASS" if expiry > issue else "FAIL",
                "Expiry date is later than issue date." if expiry > issue else "Expiry date is not later than issue date.",
                "LOW" if expiry > issue else "HIGH")


    if t == "COLLEGE_ID":
        valid_text = str(f.get("valid_until") or "").strip()
        match = re.search(r"\b((?:19|20)\d{2})\s*[-–]\s*((?:19|20)\d{2})\b", valid_text)
        if match:
            start_year, end_year = int(match.group(1)), int(match.group(2))
            current_year = date.today().year
            if end_year < start_year:
                add("COLLEGE_ID_VALIDITY_ORDER", "FAIL", "The College ID validity range ends before it starts.", "HIGH")
            elif end_year < current_year:
                add("COLLEGE_ID_VALIDITY", "REVIEW", "The College ID validity period appears to have expired.", "MEDIUM")
            else:
                add("COLLEGE_ID_VALIDITY", "PASS", "The College ID validity range is current or future.")

    if t == "COLLEGE_ID" and f.get("document_number"):
        cid = re.sub(r"[^A-Z0-9]", "", str(f["document_number"]).upper())
        ok = 4 <= len(cid) <= 31 and bool(re.fullmatch(r"[A-Z0-9]+", cid))
        add("COLLEGE_ID_FORMAT", "PASS" if ok else "REVIEW",
            "College/student ID has a plausible alphanumeric structure." if ok else "College/student ID structure needs manual review.",
            "LOW" if ok else "MEDIUM")
        valid_until = _parse_date(f.get("valid_until"))
        if valid_until:
            today = date.today()
            add("COLLEGE_ID_VALIDITY", "PASS" if valid_until >= today else "REVIEW",
                "College ID validity date is current or future." if valid_until >= today else "College ID validity date appears expired.",
                "LOW" if valid_until >= today else "MEDIUM")


    failed = [x for x in checks if x["status"] == "FAIL"]
    review = [x for x in checks if x["status"] == "REVIEW"]
    score = min(100, len(failed) * 35 + len(review) * 10)
    band = "HIGH" if score >= 50 else ("MEDIUM" if score >= 10 else "LOW")
    return {"available": bool(checks), "score": score, "band": band, "checks": checks,
            "reasons": [x["message"] for x in checks if x["status"] in {"FAIL", "REVIEW"}]}
