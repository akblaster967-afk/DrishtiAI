import re






def _clean_text(value: str):
    if not value:
        return ""

    value = value.replace("\r", "")
    value = re.sub(r"[ \t]+", " ", value)

    return value.strip()


def _clean_line(value: str):
    if not value:
        return ""

    value = re.sub(r"\s+", " ", value)
    return value.strip()






def _clean_name(value: str):

    if not value:
        return None

    value = value.strip()


    value = re.sub(r"^[^A-Za-z]+", "", value)
    value = re.sub(r"[^A-Za-z .'-]+$", "", value)

    value = re.sub(r"\s+", " ", value).strip()

    if not value:
        return None

    if len(value) < 2 or len(value) > 100:
        return None

    if not re.search(r"[A-Za-z]", value):
        return None


    blocked_words = {
        "address",
        "male",
        "female",
        "dob",
        "date of birth",
        "dateofbirth",
        "government of india",
        "government",
        "unique identification authority of india",
        "aadhaar",
        "pan",
        "passport",
        "driving licence",
        "driving license",
        "college",
        "student",
        "student id",
        "identity card",
        "identity",
    }

    if value.lower() in blocked_words:
        return None


    if sum(char.isdigit() for char in value) > 2:
        return None

    return value


def _clean_relation_name(value: str):
    if not value:
        return None
    value = re.sub(
        r"^\s*(?:s\s*(?:[/.:=-]\s*o?|o)|d\s*[/.:=-]\s*o|w\s*[/.:=-]\s*o|"
        r"son\s+of|daughter\s+of|wife\s+of|father(?:['’]s)?\s+name|father|name)\s*[:#=-]?\s*",
        "",
        str(value),
        flags=re.I,
    )
    value = re.sub(r"^[^A-Za-z]+", "", value)
    value = re.sub(r"\s+", " ", value).strip(" .,:;|'\"-")
    cleaned = _clean_name(value)
    if not cleaned:
        return None
    tokens = cleaned.split()
    if len(tokens) < 2 or all(len(token) <= 1 for token in tokens):
        return None
    return cleaned






def _find_name_near_dob(text: str):
    lines = [_clean_line(line) for line in str(text or "").splitlines() if _clean_line(line)]
    date_pattern = re.compile(r"\d{1,2}[\/-]\d{1,2}[\/-]\d{2,4}")
    dob_label = re.compile(r"(?:Date\s*of\s*Birth|DOB|D\.O\.B)", re.I)
    address_markers = re.compile(
        r"\b(?:PO|P\.?O\.?|DIST|DISTRICT|VILL|VILLAGE|ROAD|RD|STREET|HOUSE|H\.?NO|PIN|LANE|WARD|TEHSIL|POST|NAGAR|COLONY|BLOCK|SECTOR|STATE|UP|U\.?P\.?)\b",
        re.I,
    )
    blocked = {
        "government", "government of india", "aadhaar", "uidai",
        "unique identification authority of india", "male", "female",
        "address", "date of birth", "dob", "identity", "proof",
    }

    def score_candidate(raw: str, distance: int):
        candidate = _clean_name(raw)
        if not candidate:
            return None
        low = candidate.lower()
        if low in blocked or address_markers.search(candidate):
            return None
        if re.search(r"\b\d{5,6}\b", candidate):
            return None
        tokens = candidate.split()
        if not 2 <= len(tokens) <= 5:
            return None

        if any(not re.fullmatch(r"[A-Za-z][A-Za-z.'-]*", token) for token in tokens):
            return None
        punctuation_penalty = candidate.count("'") + candidate.count("-")
        score = 12 - distance * 2
        score += min(len(tokens), 4) * 2
        score += 2 if all(len(token) >= 2 for token in tokens) else 0
        score -= punctuation_penalty
        if len(candidate) > 42:
            score -= 6
        return score, candidate

    for index, line in enumerate(lines):
        if not date_pattern.search(line):
            continue
        if not (dob_label.search(line) or re.search(r"^\s*\d{1,2}[\/-]\d{1,2}[\/-]\d{4}\s*$", line)):
            continue

        candidates = []
        for distance, candidate_index in enumerate(range(index - 1, max(-1, index - 5), -1), start=1):
            result = score_candidate(lines[candidate_index], distance)
            if result:
                candidates.append(result)



        before = re.split(r"(?:Date\s*of\s*Birth|DOB|D\.O\.B)", line, maxsplit=1, flags=re.I)[0].strip(" :|=-")
        result = score_candidate(before, 1)
        if result:
            candidates.append(result)

        if candidates:
            return max(candidates, key=lambda item: item[0])[1]

    return None


def _find_dob(text: str, allow_standalone: bool = True):

    patterns = [
        r"(?:Date\s*of\s*Birth|DOB|D\.O\.B)"
        r"\s*[:\-]?\s*"
        r"(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4})",

        r"(?:Date\s*of\s*Birth|DOB|D\.O\.B)"
        r"[^\d]{0,20}"
        r"(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4})",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            re.IGNORECASE
        )

        if match:
            return match.group(1).strip()




    if allow_standalone:
        standalone = re.search(r"(?<!\d)(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{4})(?!\d)", text)
        if standalone:
            return standalone.group(1).strip()
    return None






def _normalize_id_type(id_type: str):

    value = str(
        id_type or ""
    ).strip().upper()

    aliases = {
        "AADHAAR CARD": "AADHAAR",
        "AADHAR": "AADHAAR",
        "AADHAR CARD": "AADHAAR",

        "PAN CARD": "PAN",

        "COLLEGE ID CARD": "COLLEGE_ID",
        "COLLEGE ID": "COLLEGE_ID",
        "STUDENT ID": "COLLEGE_ID",
        "STUDENT CARD": "COLLEGE_ID",

        "PASSPORT": "PASSPORT",

        "DRIVING LICENSE": "DRIVING_LICENSE",
        "DRIVING LICENCE": "DRIVING_LICENSE",
        "DL": "DRIVING_LICENSE",

        "NATIONAL ID": "NATIONAL_ID",
        "NATIONAL_ID": "NATIONAL_ID",

        "VISA": "VISA",

        "VISA CARD": "VISA",

        "TOURIST VISA": "VISA",

        "ENTRY VISA": "VISA",

        "WORK VISA": "VISA",

        "STUDENT VISA": "VISA",
    }

    return aliases.get(
        value,
        value
    )






def _aadhaar_verhoeff_valid(number: str) -> bool:
    from app.services.checksums import verhoeff_is_valid

    return verhoeff_is_valid(number)

def _find_aadhaar_number(text: str):
    candidates: list[str] = []

    grouped_patterns = [
        r"(?<!\d)(\d{4}\s+\d{4}\s+\d{4})(?!\d)",
        r"(?<!\d)(\d{4}\-\d{4}\-\d{4})(?!\d)",
        r"(?<!\d)(\d{4}[\s\-]\d{4}[\s\-]\d{4})(?!\d)",
    ]
    for pattern in grouped_patterns:
        for match in re.findall(pattern, text or ""):
            value = re.sub(r"\D", "", match)
            if len(value) == 12:
                candidates.append(value)

    for value in re.findall(r"(?<!\d)(\d{12})(?!\d)", text or ""):
        candidates.append(value)

    seen = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if _aadhaar_verhoeff_valid(candidate):
            return candidate
    return None

def _find_pan_number(text: str):

    patterns = [
        r"\b([A-Z]{5}[0-9]{4}[A-Z])\b",

        r"(?:PAN|PAN\s*No\.?|PAN\s*Number)"
        r"\s*[:\-]?\s*"
        r"([A-Z]{5}[0-9]{4}[A-Z])",
    ]


    for pattern in patterns[1:]:

        match = re.search(
            pattern,
            text,
            re.IGNORECASE
        )

        if match:
            return match.group(1).upper()


    for match in re.finditer(
        patterns[0],
        text.upper()
    ):

        candidate = match.group(1)

        if candidate:
            return candidate

    return None






def _find_passport_number(text: str):

    patterns = [
        r"(?:Passport\s*(?:No\.?|Number))"
        r"\s*[:\-]?\s*"
        r"([A-Z][A-Z0-9]{6,8})",

        r"\b([A-Z][0-9]{7})\b",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            re.IGNORECASE
        )

        if match:
            return match.group(1).upper()

    return None






def _find_college_id(text: str):
    text = str(text or "")
    label_groups = [
        (100, r"Student\s*ID|Student\s*No\.?"),
        (95, r"College\s*ID|College\s*No\.?"),
        (90, r"Enrollment\s*(?:No\.?|Number)"),
        (88, r"Registration\s*(?:No\.?|Number)|Reg(?:istration)?\s*No\.?"),
        (86, r"Roll\s*(?:No\.?|Number)|Roll\s*No"),
        (82, r"Admission\s*(?:No\.?|Number)"),
        (75, r"University\s*ID"),
        (55, r"ERP\s*(?:ID|No\.?)"),
    ]

    candidates = []
    for rank, labels in label_groups:
        pattern = rf"(?:{labels})\s*[:\-]?\s*([A-Z0-9][A-Z0-9\-\/ ]{{3,30}})"
        for match in re.finditer(pattern, text, re.IGNORECASE):
            candidate = re.sub(r"\s+", "", match.group(1)).upper()
            candidate = re.sub(r"[^A-Z0-9\-/]", "", candidate)
            if 4 <= len(candidate) <= 30:

                if re.fullmatch(r"\d{1,4}", candidate):
                    continue
                candidates.append((rank, candidate))

    if candidates:
        candidates.sort(key=lambda item: (-item[0], -len(item[1])))
        return candidates[0][1]



    generic = re.findall(r"\b[A-Z]{1,6}[0-9][A-Z0-9\-/]{2,20}\b", text.upper())
    generic = [v for v in generic if not re.fullmatch(r"(?:19|20)\d{2}", v)]
    return max(generic, key=len) if generic else None



def _find_visa_number(text: str):

    patterns = [
        r"(?:Visa\s*(?:No\.?|Number))"
        r"\s*[:\-]?\s*"
        r"([A-Z0-9][A-Z0-9\-\/]{4,30})",

        r"(?:Visa)"
        r"[^\n]{0,30}"
        r"\b([A-Z0-9]{5,20})\b",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            re.IGNORECASE
        )

        if match:

            candidate = match.group(1)

            if candidate:
                return candidate.upper()

    return None






def _find_labelled_document_number(text: str):
    lines = [_clean_line(line) for line in str(text or "").splitlines() if _clean_line(line)]
    labels = re.compile(
        r"(?:document\s*(?:no\.?|number)|id\s*(?:no\.?|number)|card\s*(?:no\.?|number)|serial\s*(?:no\.?|number))",
        re.I,
    )
    for index, line in enumerate(lines):
        match = labels.search(line)
        if not match:
            continue
        candidate = line[match.end():].strip(" :#=|-\t")
        if not candidate and index + 1 < len(lines):
            candidate = lines[index + 1]
        compact = re.sub(r"[^A-Za-z0-9./-]", "", candidate or "").upper()
        if compact and compact not in {"CARD", "NUMBER", "NO", "ID", "DOCUMENT", "SERIAL"} and 4 <= len(compact) <= 30:
            return compact
    return None


def _find_generic_document_number(
    text: str,
    id_type: str
):

    lines = [
        _clean_line(line)
        for line in text.splitlines()
    ]





    normalized_type = _normalize_id_type(
        id_type
    )




    if normalized_type == "AADHAAR":
        return _find_aadhaar_number(text)

    labelled = _find_labelled_document_number(text)

    if labelled:
        digits_only = re.sub(r"\D", "", labelled)
        if len(digits_only) != 16:
            return labelled

    normalized_type = _normalize_id_type(
        id_type
    )

    if normalized_type == "PAN":

        value = _find_pan_number(text)

        if value:
            return value

    elif normalized_type == "PASSPORT":

        value = _find_passport_number(text)

        if value:
            return value

    elif normalized_type == "COLLEGE_ID":

        value = _find_college_id(text)

        if value:
            return value

    elif normalized_type == "DRIVING_LICENSE":

        value = _find_driving_license(text)

        if value:
            return value

    elif normalized_type == "VISA":

        value = _find_visa_number(text)

        if value:
            return value





    candidates = []


    trailing_ocr_noise = {
        "ides", "smatwe", "smartwe", "smat", "smart", "sma",
        "yest", "gar", "es", "aan", "aa", "ee", "an", "in", "is", "ae",
    }

    for line in lines:

        upper_line = line.upper()


        if any(
            word in upper_line
            for word in [
                "DATE OF BIRTH",
                "DOB",
                "ADDRESS",
                "AADHAAR IS PROOF",
                "GOVERNMENT OF INDIA",
                "UIDAI",
                "EMAIL",
                "PHONE",
                "MOBILE",
                "PIN CODE",
                "VID",
            ]
        ):
            continue


        tokens = re.findall(
            r"\b[A-Z]{1,6}[0-9]{2,15}\b",
            upper_line
        )

        for token in tokens:


            if len(token) > 20:
                continue

            candidates.append(token)

    if candidates:


        candidates.sort(
            key=len,
            reverse=True
        )

        return candidates[0]

    return None






def _find_date_after_label(text: str, labels):
    label_pattern = "|".join(re.escape(x) for x in labels)
    pattern = rf"(?:{label_pattern})\s*[:\-]?[^\d]{{0,35}}(\d{{1,2}}[\-/]\d{{1,2}}[\-/]\d{{2,4}})"
    match = re.search(pattern, text or "", re.IGNORECASE)
    if match:
        return match.group(1)



    lines = [_clean_line(x) for x in (text or "").splitlines() if _clean_line(x)]
    for i, line in enumerate(lines):
        if re.search(label_pattern, line, re.I):
            window = " ".join(lines[i:i + 2])
            match = re.search(r"(\d{1,2}[\-/]\d{1,2}[\-/]\d{2,4})", window)
            if match:
                return match.group(1)
    return None


def _find_relation_name(text: str):
    match = re.search(
        r"(?:Son\s*/\s*Daughter\s*/\s*Wife\s*of|S/O|D/O|W/O|C/O|Care\s*of|S\s*[:;]|Father\s*Name|Father)\s*[:\-]?\s*([A-Za-z][A-Za-z .'-]{1,100})",
        text or "",
        re.IGNORECASE,
    )
    if not match:
        return None
    value = re.sub(r"[^A-Za-z .'-]", " ", match.group(1))
    value = re.sub(r"\s+", " ", value).strip(" .-'\t")

    value = re.split(
        r"\s+[A-Za-z][A-Za-z.-]*\s+(?=(?:PO|P\.O\.?|DIST|DISTRICT|VILL|VILLAGE|ROAD|RD|STREET|LANE|NAGAR|COLONY|TEHSIL|SECTOR|STATE)\b)",
        value,
        maxsplit=1,
        flags=re.I,
    )[0]
    value = re.split(
        r"\b(?:Address|Date|DOB|Blood|Organ|Validity|Issue|PO|P\.O\.?|DIST|DISTRICT|VILL|VILLAGE|ROAD|RD|STREET|LANE|NAGAR|COLONY|TEHSIL|SECTOR|STATE)\b",
        value,
        maxsplit=1,
        flags=re.I,
    )[0].strip()
    return _clean_relation_name(value)


def _find_blood_group(text: str):
    match = re.search(r"(?:Blood\s*Group|Blood\s*Grp)\s*[:\-]?\s*((?:A|B|AB|O)\s*[+-])", text or "", re.IGNORECASE)
    return re.sub(r"\s+", "", match.group(1)).upper() if match else None


def _find_organ_donor(text: str):
    match = re.search(r"Organ\s*Donor\s*[:\-]?\s*(Yes|No|Y|N)", text or "", re.IGNORECASE)
    if not match:
        return None
    value = match.group(1).upper()
    return {"Y": "YES", "N": "NO"}.get(value, value)


def _find_driving_license(text: str):
    text = str(text or "")
    if not text:
        return None


    labelled_patterns = [
        r"(?:DL|D\.L\.?|Driving\s+(?:Licence|License))\s*(?:No\.?|Number|#)?\s*[:\-]?\s*([A-Z]{2}\s*[-/]?\s*\d{1,4}\s*[-/]?\s*\d{4}\s*[-/]?\s*\d{4,11})",
        r"(?:Licence|License)\s*(?:No\.?|Number|#)\s*[:\-]?\s*([A-Z]{2}\s*[-/]?\s*\d{1,4}\s*[-/]?\s*\d{4}\s*[-/]?\s*\d{4,11})",
    ]
    for pattern in labelled_patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            value = re.sub(r"[^A-Za-z0-9]", "", m.group(1)).upper()
            if _looks_like_driving_license_number(value):
                return value


    candidates = re.findall(
        r"\b[A-Z]{2}\s*[-/]?\s*\d{1,4}\s*[-/]?\s*(?:19|20)\d{2}\s*[-/]?\s*\d{4,11}\b",
        text.upper(),
    )
    for candidate in candidates:
        value = re.sub(r"[^A-Z0-9]", "", candidate).upper()
        if _looks_like_driving_license_number(value):
            return value


    compact = re.sub(r"[^A-Z0-9]", "", text.upper())
    m = re.search(r"([A-Z]{2}\d{1,4}(?:19|20)\d{2}\d{4,11})", compact)
    if m and _looks_like_driving_license_number(m.group(1)):
        return m.group(1)

    return None


def _looks_like_driving_license_number(value: str) -> bool:
    value = re.sub(r"[^A-Z0-9]", "", str(value or "").upper())
    if not re.fullmatch(r"[A-Z]{2}\d{9,17}", value):
        return False

    if not re.search(r"(?:19|20)\d{2}", value[2:]):
        return False

    return len(value) >= 12


def _find_driving_license_details(text: str):
    issue_date = _find_date_after_label(text, ["Issue Date", "Date of Issue", "Issued On"])
    validity_nt = _find_date_after_label(text, ["Validity (NT)", "Validity NT", "Non Transport Validity", "NT Validity"])
    validity_tr = _find_date_after_label(text, ["Validity (TR)", "Validity TR", "Transport Validity", "TR Validity"])



    lines = [_clean_line(x) for x in (text or "").splitlines() if _clean_line(x)]
    for i, line in enumerate(lines):
        label_count = sum(bool(re.search(pattern, line, re.I)) for pattern in (
            r"Issue\s*Date", r"Validity\s*\(??NT\)?", r"Validity\s*\(??TR\)?"
        ))
        if re.search(r"Issue\s*Date", line, re.I) and re.search(r"Validity", line, re.I):
            window = " ".join(lines[i:i + 2])
            dates = re.findall(r"\d{1,2}[\-/]\d{1,2}[\-/]\d{2,4}", window)
            if dates:
                issue_date = issue_date or dates[0]
                if len(dates) >= 2:
                    validity_nt = dates[1]
                if len(dates) >= 3:
                    validity_tr = dates[2]
    relation_name = _find_relation_name(text)
    blood_group = _find_blood_group(text)
    organ_donor = _find_organ_donor(text)



    address = _find_address(text)
    if address:
        address = re.sub(r"[^A-Za-z0-9,./ -]", " ", address)
        pin = re.search(r"\b\d{6}\b", address)
        if pin:
            address = address[:pin.end()]
        address = re.sub(r"\b[aA]\b", "", address)
        address = re.sub(r"\s+", " ", address).strip(" ,.-")
    if not address:
        lines = [_clean_line(x) for x in text.splitlines() if _clean_line(x)]
        for i, line in enumerate(lines):
            if re.search(r"Son\s*/\s*Daughter\s*/\s*Wife\s*of|S/O|D/O|W/O", line, re.I):
                parts = []
                for nxt in lines[i + 1:i + 4]:
                    if re.search(r"^(?:Date|Blood|Organ|Issue|Validity|Name|DL\b)", nxt, re.I):
                        break
                    if re.search(r"(?:PIN|UP\s*\d{2,6}|\b\d{6}\b)", nxt, re.I) or len(nxt) > 12:
                        parts.append(nxt)
                if parts:
                    address = ", ".join(parts)
                    address = re.sub(r"[^A-Za-z0-9,./ -]", " ", address)
                    pin = re.search(r"\b\d{6}\b", address)
                    if pin:
                        address = address[:pin.end()]
                    address = re.sub(r"\b[aA]\b", "", address)
                    address = re.sub(r"\s+", " ", address).strip(" ,.-")
                    break

    return {
        "issue_date": issue_date,
        "validity_nt": validity_nt,
        "validity_tr": validity_tr,
        "relation_name": relation_name,
        "blood_group": blood_group,
        "organ_donor": organ_donor,
        "address": address,
    }


def _find_address(text: str):
    lines = [_clean_line(line) for line in text.splitlines() if _clean_line(line)]
    stop_labels = re.compile(
        r"^(?:date\s*of\s*birth|dob|blood\s*group|organ\s*donor|"
        r"son/daughter/wife|validity|issue\s*date|name|gender|sex|"
        r"aadhaar|aadhar|pan|passport|document|id|father|mother|"
        r"mobile|phone|email|nationality|occupation|signature)\b",
        re.IGNORECASE,
    )

    def clean(value, relation=None):
        value = re.sub(r"[^A-Za-z0-9,./()'\- ]+", " ", str(value or ""))



        relation_marker = re.search(
            r"(?:S\s*/\s*O|D\s*/\s*O|W\s*/\s*O|C\s*/\s*O|SON\s+OF|DAUGHTER\s+OF|WIFE\s+OF|CARE\s+OF)\s*[:\-]?\s*",
            value, flags=re.I,
        )
        if relation_marker:
            value = value[relation_marker.end():]
        else:
            value = re.sub(
                r"^\s*(?:S\s*/\s*O|D\s*/\s*O|W\s*/\s*O|C\s*/\s*O|SON\s+OF|DAUGHTER\s+OF|WIFE\s+OF)\s*[:\-]?\s*",
                "", value, flags=re.I,
            )
        relation_norm = re.sub(r"[^a-z]+", " ", str(relation or "").lower()).strip()
        value_norm = re.sub(r"[^a-z]+", " ", value.lower()).strip()
        if relation_norm and value_norm.startswith(relation_norm):
            value = re.sub(r"^\s*" + re.escape(str(relation).strip()) + r"\s*[,;:\-]?\s*", "", value, count=1, flags=re.I)
        value = re.sub(r"\s+", " ", value).strip(" ,.-")
        pin = re.search(r"\b\d{6}\b", value)
        if pin:
            value = value[:pin.end()]
        return value

    relation = _find_relation_name(text)


    for index, line in enumerate(lines):
        match = re.search(r"(?:Address|ADDRES[S5])\s*[:\-]?\s*(.*)", line, re.I)
        if not match:
            continue


        block_lines = []
        first = clean(match.group(1), relation=relation)
        if first:
            block_lines.append(first)
        block_lines.extend(lines[index + 1:index + 6])
        relation_line_index = next(
            (pos for pos, candidate_line in enumerate(block_lines)
             if re.search(r"(?:S\s*/\s*O|D\s*/\s*O|W\s*/\s*O|C\s*/\s*O|SON\s+OF|DAUGHTER\s+OF|WIFE\s+OF|CARE\s+OF)\s*[:\-]?", candidate_line, re.I)),
            None,
        )
        if relation_line_index is not None:
            block_lines = block_lines[relation_line_index:]

        parts = []
        for candidate_line in block_lines:
            if stop_labels.search(candidate_line):
                break
            cleaned_line = clean(candidate_line, relation=relation)
            if cleaned_line:
                parts.append(cleaned_line)
            if re.search(r"\b\d{6}\b", cleaned_line or ""):
                break
        value = clean(", ".join(x for x in parts if x), relation=relation)
        if len(value) >= 8 and len(re.findall(r"[A-Za-z]{2,}", value)) >= 2:
            return value



    for index, line in enumerate(lines):
        relation_match = re.search(
            r"(?:Son\s*/\s*Daughter\s*/\s*Wife\s*of|S\s*/\s*O|D\s*/\s*O|W\s*/\s*O|C\s*/\s*O)\s*[:\-]?\s*",
            line, re.I,
        )
        if not relation_match:
            continue
        parts = []
        tail = clean(line[relation_match.end():], relation=relation)
        if tail and (re.search(r"\b\d{6}\b", tail) or re.search(r"\b(?:road|rd|street|lane|nagar|colony|village|vill|district|dist|tehsil|sector|pin|state)\b", tail, re.I) or "," in tail):
            parts.append(tail)
        for next_line in lines[index + 1:index + 6]:
            if stop_labels.search(next_line):
                break
            nxt = clean(next_line, relation=relation)
            if not nxt:
                continue



            if parts:
                parts.append(nxt)
            elif (
                re.search(r"\b\d{6}\b", nxt)
                or re.search(r"\b(?:road|rd|street|lane|nagar|colony|village|vill|district|dist|tehsil|sector|pin|state)\b", nxt, re.I)
                or "," in nxt
            ):
                parts.append(nxt)
            if re.search(r"\b\d{6}\b", nxt):
                break
        value = clean(", ".join(x for x in parts if x), relation=relation)
        if len(value) >= 8 and len(re.findall(r"[A-Za-z]{2,}", value)) >= 2:
            return value

    return None



def _normalize_name_for_match(value: str):
    value = re.sub(r"[^A-Za-z ]+", " ", str(value or ""))
    return re.sub(r"\s+", " ", value).strip().lower()


def _find_explicit_name_marker(text: str):
    match = re.search(r"PAN_NAME_CANDIDATE\s*:\s*([A-Za-z][A-Za-z .'-]{1,100})", text, re.IGNORECASE)
    if not match:
        return None
    return _clean_name(match.group(1).strip())


def _best_name_candidate(text: str, reference_name: str = ""):
    lines = [_clean_line(x) for x in text.splitlines() if _clean_line(x)]


    trailing_ocr_noise = {
        "ides", "smatwe", "smartwe", "smat", "smart", "sma",
        "yest", "gar", "es", "aan", "aa", "ee", "an", "in", "is", "ae",
        "the", "of", "and"
    }




    for i, line in enumerate(lines):
        marker = re.search(r"^\s*(?:full\s*)?name\b\s*[:\-]?\s*(.*)$", line, re.IGNORECASE)
        if marker:
            candidate = marker.group(1).strip()
            if not candidate and i + 1 < len(lines):
                candidate = lines[i + 1]
            candidate = re.sub(r"[^A-Za-z .'-]", " ", candidate)
            candidate = re.sub(r"\s+", " ", candidate).strip(" .-'\t")
            words = candidate.split()
            while len(words) > 2 and words[-1].lower() in trailing_ocr_noise:

                if words[-1].lower() == "mishra" and len(words) == 2:
                    break
                words.pop()
            if 2 <= len(words) <= 5 and all(re.fullmatch(r"[A-Za-z][A-Za-z.'-]*", word) for word in words):
                return " ".join(words)

    blocked = ("government", "india", "aadhaar", "passport", "driving", "license",
               "college", "university", "student", "address", "date", "birth",
               "father", "mother", "male", "female", "identification", "identity", "pan",
               "given name", "given names", "surname", "school name", "institution",
               "nationality", "place of birth", "place of issue", "sex", "passport no",
               "passport number", "expiry", "valid until", "issue date")
    candidates = []
    for i, line in enumerate(lines):
        clean = re.sub(r"[^A-Za-z .'-]", " ", line)
        clean = re.sub(r"\s+", " ", clean).strip(" .-'")
        low = clean.lower()
        if low.startswith("p<") or re.match(r"^p\s+[a-z]{3}", low):
            continue
        if any(b in low for b in blocked):

            if re.search(r"^\s*(?:full\s*)?name\b", low, re.I) and i + 1 < len(lines):
                nxt = re.sub(r"[^A-Za-z .'-]", " ", lines[i + 1])
                nxt = re.sub(r"\s+", " ", nxt).strip(" .-'")
                if nxt:
                    clean = nxt
                else:
                    continue
            else:
                continue
        words = clean.split()
        while len(words) > 2 and words[-1].lower() in trailing_ocr_noise:
            words.pop()
        clean = " ".join(words)
        if 2 <= len(words) <= 5 and all(re.fullmatch(r"[A-Za-z][A-Za-z.'-]*", w) for w in words):
            candidates.append(clean)
        elif 1 <= len(words) <= 6 and re.search(r"^\s*(?:full\s*)?name\b", line, re.I):
            after = re.split(r"\b(?:full\s*)?name\b\s*[:\-]?", line, maxsplit=1, flags=re.I)[-1]
            after = re.sub(r"[^A-Za-z .'-]", " ", after)
            after = re.sub(r"\s+", " ", after).strip(" .-'")
            if 2 <= len(after.split()) <= 5:
                candidates.append(after)

    ref = _normalize_name_for_match(reference_name)
    if ref and reference_name:
        from difflib import SequenceMatcher
        ref_tokens = ref.split()


        for i, line in enumerate(lines):
            if re.search(r"^\s*(?:full\s*)?name\b", line, re.I):
                after = re.split(r"\b(?:full\s*)?name\b\s*[:\-]?", line, maxsplit=1, flags=re.I)[-1].strip()
                nearby = after or (lines[i + 1] if i + 1 < len(lines) else "")
                nearby = re.sub(r"[^A-Za-z .'-]", " ", nearby)
                nearby = re.sub(r"\s+", " ", nearby).strip()
                if nearby:
                    nearby_tokens = _normalize_name_for_match(nearby).split()
                    ratio = SequenceMatcher(None, _normalize_name_for_match(nearby), ref).ratio()
                    token_hit = any(
                        SequenceMatcher(None, token, ref_token).ratio() >= 0.78
                        for token in nearby_tokens
                        for ref_token in ref_tokens
                    )
                    if ratio >= 0.55 or token_hit:
                        return reference_name.strip()


        raw_tokens = re.findall(r"[A-Za-z]+", text)
        for width in range(min(4, len(ref_tokens) + 2), max(1, len(ref_tokens) - 1), -1):
            for i in range(0, max(0, len(raw_tokens) - width + 1)):
                window = raw_tokens[i:i + width]
                joined = " ".join(window)
                ratio = SequenceMatcher(None, _normalize_name_for_match(joined), ref).ratio()
                token_hits = sum(
                    any(SequenceMatcher(None, token.lower(), rt).ratio() >= 0.72 for rt in ref_tokens)
                    for token in window
                )
                if ratio >= 0.72 and token_hits >= len(ref_tokens):
                    return reference_name.strip()

        for cand in candidates:
            cn = _normalize_name_for_match(cand)
            if cn == ref or all(tok in cn.split() for tok in ref_tokens):
                return reference_name.strip()


        for cand in candidates:
            ct = _normalize_name_for_match(cand).split()
            if len(ct) == 1 and ct[0] in ref_tokens:
                return reference_name.strip()


        for cand in candidates:
            ratio = SequenceMatcher(None, _normalize_name_for_match(cand), ref).ratio()
            if ratio >= 0.72:
                return reference_name.strip()
    return max(candidates, key=lambda x: (len(x.split()), len(x)), default=None)



def _find_labelled_value(text: str, labels, max_len=120):
    if not text:
        return None
    label_pattern = "|".join(re.escape(x) for x in labels)
    stop = r"(?:Name|DOB|Date\s*of\s*Birth|Address|Gender|Sex|Nationality|Passport|PAN|Father|Mother|Course|Branch|College|University|Institution|Issue|Expiry|Valid|Roll|Registration|Enrollment|Student|Document|ID)"
    patterns = [
        rf"(?:{label_pattern})\s*[:#\-]?\s*([^\n\r]{{2,{max_len}}})",
        rf"(?:{label_pattern})\s*[:#\-]?\s*([^\n\r]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        value = re.sub(r"\s+", " ", match.group(1)).strip(" :#-|")
        value = re.split(stop, value, maxsplit=1, flags=re.IGNORECASE)[0].strip(" :#-|")
        if 1 < len(value) <= max_len:
            return value
    return None


def _find_gender(text: str):
    value = _find_labelled_value(text, ["Gender", "Sex", "लिंग"], 20)
    if value:
        cleaned = value.upper().strip()
        if re.match(r"^(?:MALE|M|पुरुष)\b", cleaned): return "MALE"
        if re.match(r"^(?:FEMALE|F|महिला)\b", cleaned): return "FEMALE"
        if re.match(r"^(?:OTHER|O)\b", cleaned): return "OTHER"

    match = re.search(r"(?:^|\s)(MALE|FEMALE)(?:\s|$)", text or "", re.I)
    return match.group(1).upper() if match else None


def _find_nationality(text: str):
    value = _find_labelled_value(text, ["Nationality", "Nationality of holder"], 40)
    if not value:
        return None
    value = re.sub(r"[^A-Za-z .'-]", " ", value)
    return re.sub(r"\s+", " ", value).strip() or None


def _find_father_name(text: str):
    relation = _find_relation_name(text)
    if relation:
        return relation
    value = _find_labelled_value(text, ["Father's Name", "Father Name", "Fathers Name"], 100)
    return _clean_name(value) if value else None


def _find_mother_name(text: str):
    value = _find_labelled_value(text, ["Mother's Name", "Mother Name", "Mother", "Mothers Name", "M/O"], 100)
    return _clean_name(value) if value else None


def _find_issue_expiry_dates(text: str):
    issue = _find_date_after_label(text, ["Issue Date", "Date of Issue", "Issued On", "Date of Issue"])
    expiry = _find_date_after_label(text, ["Expiry Date", "Date of Expiry", "Valid Until", "Valid Till", "Validity"])
    return issue, expiry


def _find_passport_fields(text: str):
    passport_number = _find_passport_number(text)
    issue, expiry = _find_issue_expiry_dates(text)
    nationality = _find_nationality(text)
    gender = _find_gender(text)
    surname = _find_labelled_value(text, ["Surname", "Surname / Nom"], 80)
    given = _find_labelled_value(text, ["Given Name", "Given Names", "Given name(s)"], 100)
    place_birth = _find_labelled_value(text, ["Place of Birth", "Place of birth"], 100)
    place_issue = _find_labelled_value(text, ["Place of Issue", "Place of issue"], 100)


    mrz_lines = [re.sub(r"\s+", "", x.upper()) for x in (text or "").splitlines() if "<" in x or x.strip().startswith("P<")]
    for i, line in enumerate(mrz_lines):
        if not line.startswith("P<"):
            continue
        if i + 1 >= len(mrz_lines):
            continue
        second = mrz_lines[i + 1].replace(" ", "")
        if len(second) < 40:
            continue
        if not passport_number:
            candidate = second[0:9].replace("<", "")
            if re.fullmatch(r"[A-Z0-9]{7,9}", candidate):
                passport_number = candidate
        if not nationality and len(second) >= 15:
            nat = second[10:13].replace("<", "")
            if re.fullmatch(r"[A-Z]{3}", nat):
                nationality = nat
        if not gender and len(second) >= 21 and second[20] in "MF<":
            gender = {"M":"MALE", "F":"FEMALE", "<":"UNSPECIFIED"}[second[20]]
        if not _find_mrz_date(second, 13):
            pass
        if not _find_mrz_date(second, 21):
            pass

        dob = _mrz_date_to_iso(second[13:19]) if len(second) >= 19 else None
        exp = _mrz_date_to_iso(second[21:27]) if len(second) >= 27 else None
        if dob and not _find_dob(text):
            text = text + "\nDOB: " + dob
        if exp and not expiry:
            expiry = f"{exp[8:10]}-{exp[5:7]}-{exp[:4]}"
        break

    return {
        "document_number": passport_number,
        "issue_date": issue,
        "expiry_date": expiry,
        "nationality": nationality,
        "gender": gender,
        "surname": _clean_name(surname) if surname else None,
        "given_names": _clean_name(given) if given else None,
        "place_of_birth": place_birth,
        "place_of_issue": place_issue,
    }


def _mrz_date_to_iso(value):
    if not re.fullmatch(r"\d{6}", str(value or "")):
        return None
    yy, mm, dd = int(value[:2]), int(value[2:4]), int(value[4:6])

    year = 2000 + yy if yy <= 49 else 1900 + yy
    try:
        from datetime import datetime
        return datetime(year, mm, dd).strftime("%Y-%m-%d")
    except ValueError:
        return None


def _find_mrz_date(second, start):
    return _mrz_date_to_iso(second[start:start+6]) if len(second) >= start + 6 else None


def _find_pan_fields(text: str):
    anchored = _extract_label_anchor_fields(text, "PAN", {})
    return {
        "name": anchored.get("name"),
        "father_name": anchored.get("father_name") or _find_father_name(text),
        "gender": _find_gender(text),
    }


def _find_aadhaar_fields(text: str):



    relation = _find_relation_name(text)
    return {
        "gender": _find_gender(text),
        "father_name": relation,
    }


def _find_college_institution(text: str):
    lines = [_clean_line(x) for x in str(text or "").splitlines()]
    for i, line in enumerate(lines):
        low = line.lower()
        if "college of" in low or "college" in low or "engineering &" in low or "engineering and" in low:
            pieces = [line]
            if i + 1 < len(lines):
                nxt = lines[i + 1]
                nxt_low = nxt.lower()


                if nxt and not re.match(r"^(name|roll|erp|id|course|valid|dob|date|address)\b", nxt_low):
                    if any(token in nxt_low for token in ("engineering", "management", "university", "lucknow", "institute", "college")):
                        pieces.append(nxt)
            value = re.sub(r"\s+", " ", " ".join(pieces)).strip(" :#-|=")



            value = re.sub(r"^[^A-Za-z]+", "", value)
            value = re.sub(r"\bof\s+(?:ia|1a|la)\b", "of", value, flags=re.I)
            value = re.sub(r"(?:^|\s)(?:0|O)\s*[%|]+\s*", " ", value)
            value = re.sub(r"\s+", " ", value).strip(" :#-|=")
            if len(value) >= 8 and not value.lower() in {"college of", "engineering", "management"}:
                return value
    return _find_labelled_value(
        text,
        ["College Name", "University Name", "Institution", "Institute"],
        140,
    )


def _clean_labelled_scalar(value):
    if value is None:
        return None
    cleaned = re.sub(r"\s+", " ", str(value)).strip(" :#-|=")
    cleaned = re.sub(r"\s*=+\s*$", "", cleaned).strip(" :#-|")
    if cleaned.lower() in {"of", "the", "and", "is", "-"}:
        return None
    return cleaned or None


def _find_college_fields(text: str):
    institution = _find_college_institution(text)
    course = _clean_labelled_scalar(
        _find_labelled_value(text, ["Course", "Program", "Programme", "Branch", "Department"], 100)
    )
    enrollment = _find_college_id(text)
    valid_until = _clean_labelled_scalar(
        _find_labelled_value(text, ["Valid Till", "Valid TIll", "Valid TH", "Valid Until", "Expiry Date", "Validity"], 40)
    )
    return {
        "institution_name": institution,
        "course": course,
        "enrollment_number": enrollment,
        "valid_until": valid_until,
    }






_LABEL_ANCHOR_FIELDS = {



    "AADHAAR": {
        "name": (r"full\s*name", r"holder\s*name", r"name", r"resident\s*name"),
        "father_name": (r"father(?:['’]s|s)?\s*name", r"father\s*name", r"father", r"s\s*/\s*o", r"son\s*of"),
        "mother_name": (r"mother(?:['’]s|s)?\s*name", r"mother", r"m\s*/\s*o", r"daughter\s*of"),
        "dob": (r"date\s*of\s*birth", r"dob", r"d\.?\s*o\.?\s*b", r"birth\s*date"),
        "document_number": (r"aadhaar(?:\s*(?:no|number))?", r"aadhar(?:\s*(?:no|number))?", r"uid(?:ai)?", r"unique\s*id", r"enrol(?:ment|lment)?(?:\s*(?:no|number|id))?"),
        "gender": (r"gender", r"sex"),
        "address": (r"address", r"permanent\s*address", r"residential\s*address"),
    },
    "PAN": {
        "name": (r"full\s*name", r"cardholder\s*name", r"holder\s*name", r"name"),
        "father_name": (r"father(?:['’]s|s)?\s*name", r"father\s*name", r"father", r"s\s*/\s*o"),
        "dob": (r"date\s*of\s*birth", r"dob", r"d\.?\s*o\.?\s*b", r"birth\s*date"),
        "document_number": (r"permanent\s*account\s*number", r"pan(?:\s*(?:no|number))?", r"permanent\s*account"),
    },
    "PASSPORT": {
        "name": (r"full\s*name", r"holder\s*name", r"name"),
        "surname": (r"surname", r"family\s*name", r"last\s*name"),
        "given_names": (r"given\s*names?", r"first\s*name"),
        "dob": (r"date\s*of\s*birth", r"dob", r"birth\s*date"),
        "document_number": (r"passport(?:\s*(?:no|number))?", r"passport\s*number", r"document\s*no"),
        "nationality": (r"nationality", r"nationality\s*of\s*holder"),
        "gender": (r"sex", r"gender"),
        "issue_date": (r"date\s*of\s*issue", r"issue\s*date", r"issued\s*on"),
        "expiry_date": (r"date\s*of\s*expiry", r"expiry\s*date", r"date\s*of\s*expiration", r"expiration\s*date"),
        "place_of_birth": (r"place\s*of\s*birth",),
        "place_of_issue": (r"place\s*of\s*issue",),
    },
    "DRIVING_LICENSE": {
        "name": (r"full\s*name", r"holder\s*name", r"name"),
        "father_name": (r"father(?:['’]s|s)?\s*name", r"father\s*name", r"son\s*/\s*daughter\s*/\s*wife\s*of", r"s\s*/\s*o", r"d\s*/\s*o", r"w\s*/\s*o"),
        "relation_name": (r"son\s*/\s*daughter\s*/\s*wife\s*of", r"father(?:['’]s|s)?\s*name", r"father", r"s\s*/\s*o", r"d\s*/\s*o", r"w\s*/\s*o"),
        "dob": (r"date\s*of\s*birth", r"dob", r"d\.?\s*o\.?\s*b", r"birth\s*date"),
        "document_number": (r"driving\s*(?:licen[sc]e|licence)(?:\s*(?:no|number))?", r"dl\s*(?:no|number)?", r"license\s*(?:no|number)?", r"licence\s*(?:no|number)?"),
        "address": (r"address", r"permanent\s*address", r"residential\s*address"),
        "gender": (r"gender", r"sex"),
        "issue_date": (r"date\s*of\s*issue", r"issue\s*date", r"issued\s*on"),
        "validity_nt": (r"non\s*transport", r"validity\s*nt", r"nt\s*validity", r"nt"),
        "validity_tr": (r"transport", r"validity\s*tr", r"tr\s*validity", r"tr"),
        "expiry_date": (r"date\s*of\s*expiry", r"expiry\s*date", r"valid\s*upto", r"valid\s*till", r"valid\s*until"),
    },
    "COLLEGE_ID": {
        "name": (r"student\s*name", r"candidate\s*name", r"full\s*name", r"name"),
        "document_number": (r"roll\s*(?:no\.?|number)?", r"roll\s*id", r"id\s*(?:no\.?|number)", r"student\s*id", r"card\s*(?:no\.?|number)"),
        "erp_id": (r"erp(?:\s*id)?", r"erp\s*(?:no\.?|number)"),
        "dob": (r"date\s*of\s*birth", r"dob", r"birth\s*date"),
        "course": (r"course", r"program(?:me)?", r"branch", r"department", r"stream"),
        "institution_name": (r"institution\s*name", r"college\s*name", r"university", r"college", r"institute"),
        "enrollment_number": (r"enrol(?:l)?ment\s*(?:no\.?|number|id)?", r"registration\s*(?:no\.?|number)", r"registration\s*id"),
        "valid_until": (r"valid\s*(?:till|until|upto)", r"validity", r"expiry\s*date", r"expiration\s*date"),
    },
    "NATIONAL_ID": {
        "name": (r"full\s*name", r"holder\s*name", r"name"),
        "document_number": (r"id\s*(?:no\.?|number)", r"identity\s*(?:no\.?|number)", r"national\s*id"),
        "dob": (r"date\s*of\s*birth", r"dob"),
        "gender": (r"gender", r"sex"),
        "address": (r"address", r"permanent\s*address", r"residential\s*address"),
    },
    "VISA": {
        "name": (r"full\s*name", r"surname", r"given\s*name", r"name"),
        "document_number": (r"visa\s*(?:no\.?|number)", r"document\s*(?:no\.?|number)"),
        "dob": (r"date\s*of\s*birth", r"dob"),
        "issue_date": (r"issue\s*date", r"date\s*of\s*issue"),
        "expiry_date": (r"expiry\s*date", r"date\s*of\s*expiry", r"valid\s*until"),
        "nationality": (r"nationality", r"national\s*of"),
        "gender": (r"gender", r"sex"),
        "passport_number": (r"passport\s*(?:no\.?|number)",),
        "place_of_birth": (r"place\s*of\s*birth", r"born\s*at", r"birth\s*place"),
        "place_of_issue": (r"place\s*of\s*issue", r"issued\s*at"),
    },
}


_GENERIC_LABEL_ANCHORS = {
    "name": (r"full\s*name", r"holder\s*name", r"candidate\s*name", r"student\s*name", r"cardholder\s*name", r"name"),
    "father_name": (r"father(?:['’]s|s)?\s*name", r"father\s*name", r"father", r"s\s*/\s*o", r"son\s*of"),
    "mother_name": (r"mother(?:['’]s|s)?\s*name", r"mother", r"m\s*/\s*o", r"daughter\s*of"),
    "dob": (r"date\s*of\s*birth", r"dob", r"d\.?\s*o\.?\s*b", r"birth\s*date"),
    "document_number": (r"document\s*(?:no\.?|number)", r"id\s*(?:no\.?|number)", r"card\s*(?:no\.?|number)"),
    "address": (r"address", r"permanent\s*address", r"residential\s*address"),
    "gender": (r"gender", r"sex"),
    "issue_date": (r"issue\s*date", r"date\s*of\s*issue", r"issued\s*on"),
    "expiry_date": (r"expiry\s*date", r"date\s*of\s*expiry", r"valid\s*until", r"valid\s*till"),
    "nationality": (r"nationality",),
    "course": (r"course", r"program(?:me)?", r"branch", r"department", r"stream"),
    "institution_name": (r"institution\s*name", r"college\s*name", r"university", r"college", r"institute"),
}


_ANCHOR_STOP_LABELS = (
    r"full\s*name", r"holder\s*name", r"candidate\s*name", r"student\s*name", r"cardholder\s*name", r"name", r"surname", r"given\s*names?",
    r"father(?:['’]s|s)?\s*name", r"father", r"mother(?:['’]s|s)?\s*name", r"mother",
    r"son\s*/\s*daughter\s*/\s*wife\s*of", r"s\s*/\s*o", r"d\s*/\s*o", r"w\s*/\s*o", r"son\s*of", r"daughter\s*of",
    r"date\s*of\s*birth", r"dob", r"d\.?\s*o\.?\s*b", r"birth\s*date", r"address", r"gender", r"sex",
    r"date\s*of\s*issue", r"issue\s*date", r"issued\s*on", r"date\s*of\s*expiry", r"expiry\s*date", r"expiration\s*date",
    r"valid\s*(?:till|until|upto)", r"validity", r"nationality", r"passport", r"pan", r"permanent\s*account\s*number",
    r"driving\s*(?:licen[sc]e|licence)", r"dl", r"roll\s*(?:no\.?|number)?", r"registration\s*(?:no\.?|number|id)?", r"reg(?:istration)?\s*no\.?",
    r"year\s*of\s*passing", r"passing\s*year", r"exam(?:ination)?\s*year", r"passed\s*in",
    r"school\s*name", r"name\s*of\s*school", r"school", r"institution\s*name", r"institution", r"board(?:\s*of\s*education)?", r"examination\s*board",
    r"examination", r"exam", r"stream", r"course", r"program(?:me)?", r"branch", r"department", r"student\s*id", r"erp(?:\s*id)?",
    r"enrol(?:l)?ment\s*(?:no\.?|number|id)?", r"card\s*(?:no\.?|number)", r"document\s*(?:no\.?|number)", r"id\s*(?:no\.?|number)",
    r"place\s*of\s*birth", r"place\s*of\s*issue", r"nationality",
)


def _anchor_line_value(line: str, label_patterns: tuple[str, ...]) -> str | None:
    value = str(line or "").strip()
    if not value:
        return None
    label_union = "|".join(f"(?:{pattern})" for pattern in label_patterns)
    match = re.search(rf"(?:{label_union})(?:\s*[:#=\-]|\s*\|)?\s*(.*)$", value, re.I)
    if not match:
        return None
    candidate = match.group(1).strip(" :#=|-\t")
    if not candidate:
        return None

    stop_patterns = list(_ANCHOR_STOP_LABELS)

    if any("board" in str(pattern).lower() for pattern in label_patterns):
        stop_patterns = [pattern for pattern in stop_patterns if "board" not in str(pattern).lower()]
    stop_union = "|".join(f"(?:{pattern})" for pattern in stop_patterns)
    candidate = re.split(
        rf"\s+(?=(?:{stop_union})(?:\s*[:#=\-]|\b))",
        candidate,
        maxsplit=1,
        flags=re.I,
    )[0]
    return re.sub(r"\s+", " ", candidate).strip(" .,:;-|") or None


def _anchor_clean_value(field: str, value: str) -> str | None:
    if not value:
        return None
    value = re.sub(r"\s+", " ", value).strip()
    lowered = value.lower()
    noise_phrases = (
        "valid unless physically signed",
        "important instructions",
        "see overleaf",
        "cum-marks",
        "cum marks",
        "for important instructions",
    )
    if any(phrase in lowered for phrase in noise_phrases) or re.search(
        r"\bvalid\b.{0,35}\b(?:physical|physically)\s+signed\b",
        lowered,
    ):
        return None
    if field in {"name", "father_name", "mother_name"}:
        value = re.sub(
            r"^\s*valid\b.{0,35}\b(?:unless|physic(?:al|ally)?|signed)\b\s*",
            "",
            value,
            flags=re.I,
        )
        value = re.sub(
            r"^\s*(?:wee\s+)?(?:ht\s+)?(?:artre|arte)\s*[:,-]?\s*",
            "",
            value,
            flags=re.I,
        )
        lowered = value.lower()
        if field == "name" and re.search(
            r"\bvalid\b.*\b(?:unless|physic(?:al|ally)?|signed)\b",
            lowered,
        ):
            return None
        if field in {"father_name", "mother_name"}:
            value = re.split(
                r"\s+[A-Za-z][A-Za-z.-]*\s+(?=(?:PO|P\.O\.?|DIST|DISTRICT|VILL|VILLAGE|ROAD|RD|STREET|LANE|NAGAR|COLONY|TEHSIL|SECTOR|STATE)\b)",
                value,
                maxsplit=1,
                flags=re.I,
            )[0]
            value = re.split(
                r"\b(?:Address|PO|P\.O\.?|DIST|DISTRICT|VILL|VILLAGE|ROAD|RD|STREET|LANE|NAGAR|COLONY|TEHSIL|SECTOR|STATE)\b",
                value,
                maxsplit=1,
                flags=re.I,
            )[0].strip(" ,.-")
        cleaned = _clean_relation_name(value) if field in {"father_name", "mother_name"} else _clean_name(value)
        if not cleaned:
            return None
        if any(token in {"wee", "arte", "artre"} for token in cleaned.lower().split()):
            return None
        if cleaned.lower() in {"name", "card", "number", "account", "permanent", "department", "government", "india", "of", "the", "holder", "student", "candidate"}:
            return None



        if field == "name" and len(cleaned.split()) == 1 and len(cleaned) < 5:
            return None
        name_tokens = cleaned.split()
        if len(name_tokens) == 1 and len(name_tokens[0]) < 3:
            return None
        if len(name_tokens) > 1 and all(len(token) == 1 for token in name_tokens):
            return None
        return cleaned
    if field in {"school_name", "institution_name"}:
        if re.search(r"\b(?:exam(?:ination)?|certificate|marksheet|mark\s*sheet|overleaf|instructions?|cum\s*marks?|year\s*of\s*passing|passing\s*year)\b", lowered):
            return None
        if re.search(r"\b(?:19|20)\d{2}\b", lowered):
            return None
        if len(value.split()) < 2:
            return None
        return value
    if field == "dob":
        match = re.search(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{4})\b", value)
        return match.group(1) if match else None
    if field == "passing_year":
        match = re.search(r"\b((?:19|20)\d{2})\b", value)
        return match.group(1) if match else None
    if field == "document_number":
        compact = re.sub(r"[^A-Za-z0-9./-]", "", value).upper()

        if compact in {"CARD", "NUMBER", "ACCOUNT", "PERMANENT", "ID", "NO", "PAN"}:
            return None
        if 4 <= len(compact) <= 30:
            return compact
        return None
    if field in {"registration_number", "erp_id", "enrollment_number"}:
        compact = re.sub(r"[^A-Za-z0-9./-]", "", value).upper()
        if compact in {"ID", "NUMBER", "NO", "CARD", "ENROLLMENT", "REGISTRATION", "ERP"}:
            return None
        return compact if 4 <= len(compact) <= 30 else None
    if field in {"gender"}:
        token = re.sub(r"[^A-Za-z]", "", value).upper()
        if token.startswith("MALE") or token == "M": return "MALE"
        if token.startswith("FEMALE") or token == "F": return "FEMALE"
        if token.startswith("OTHER") or token == "O": return "OTHER"
        return None
    if field in {"issue_date", "expiry_date", "valid_until", "validity_nt", "validity_tr"}:
        match = re.search(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b", value)
        return match.group(1) if match else (value if len(value) >= 2 else None)
    return value if len(value) >= 2 else None


def _extract_label_anchor_fields(text: str, id_type: str = "", reference_fields: dict[str, str] | None = None) -> dict[str, str]:
    reference_fields = reference_fields or {}
    normalized = _normalize_id_type(id_type)
    mapping = _LABEL_ANCHOR_FIELDS.get(normalized, _GENERIC_LABEL_ANCHORS)
    universal_name_anchors = {
        "name": (
            r"full\s*name",
            r"holder\s*name",
            r"cardholder\s*name",
            r"applicant\s*name",
            r"candidate\s*name",
            r"student\s*name",
            r"resident\s*name",
            r"person\s*name",
            r"name",
        ),
        "father_name": (
            r"father(?:['’]s|s)?\s*name",
            r"father\s*name",
            r"father",
            r"s\s*/\s*o",
            r"son\s*of",
        ),
        "mother_name": (
            r"mother(?:['’]s|s)?\s*name",
            r"mother\s*name",
            r"mother",
            r"m\s*/\s*o",
            r"daughter\s*of",
        ),
    }
    mapping = dict(mapping)
    for field, anchors in universal_name_anchors.items():
        mapping[field] = tuple(dict.fromkeys(
            (*mapping.get(field, ()), *anchors)
        ))
    lines = [_clean_line(line) for line in str(text or "").splitlines() if _clean_line(line)]
    if not lines:
        return {}

    extracted: dict[str, str] = {}
    for field, patterns in mapping.items():
        candidates: list[str] = []
        for index, line in enumerate(lines):
            low = line.lower()

            if field == "name" and re.search(r"father|mother|son\s*/\s*o|daughter\s*of|s\s*/\s*o|m\s*/\s*o", low):
                continue
            if field == "name" and re.search(r"institution|college|university|school", low):
                continue
            if field == "school_name" and re.search(r"high\s*school|secondary|matriculation", low) and re.search(r"certificate|marksheet|mark\s*sheet", low):
                continue

            anchored = _anchor_line_value(line, patterns)
            if field in {"father_name", "relation_name"} and re.match(r"^\s*s\s*[:;]", line, re.I):
                anchored = re.sub(r"^\s*s\s*[:;]\s*", "", line, flags=re.I).strip()
            if anchored:
                candidates.append(anchored)
                continue



            label_only = any(re.search(rf"^(?:{pattern})\s*(?:[:#=\-]|\|)?\s*$", line, re.I) for pattern in patterns)
            if not label_only:
                continue
            for offset in range(1, 5):
                if index + offset >= len(lines):
                    break
                nxt = lines[index + offset]
                if not nxt:
                    continue
                if any(re.search(rf"^(?:{pattern})(?:\s*[:#=\-]|\b)", nxt, re.I) for pattern in _ANCHOR_STOP_LABELS):
                    if field in {"school_name", "institution_name"} and _anchor_clean_value(field, nxt) is None:
                        continue
                    break

                if not re.search(r"[A-Za-z0-9]", nxt):
                    continue
                candidates.append(nxt)

        cleaned = [_anchor_clean_value(field, candidate) for candidate in candidates]
        cleaned = [value for value in cleaned if value]

        if field == "address":
            cleaned = [
                value for value in cleaned
                if not re.search(
                    r"\b(?:should\s+be\s+updated|update|upload|submit|enter|provide|click|select|choose|enter\s+your)\b",
                    value,
                    re.I,
                )
            ]




        if field == "document_number":
            if normalized == "PAN":
                pan_values = []
                for candidate in cleaned:
                    compact = re.sub(r"[^A-Za-z0-9]", "", candidate).upper()
                    m = re.search(r"[A-Z]{5}[0-9]{4}[A-Z]", compact)
                    if m:
                        pan_values.append(m.group(0))
                cleaned = pan_values
            elif normalized == "AADHAAR":
                valid_aadhaar = []
                for candidate in cleaned:
                    digits = re.sub(r"\D", "", candidate)
                    if len(digits) == 12:
                        try:
                            if _aadhaar_verhoeff_valid(digits):
                                valid_aadhaar.append(digits)
                        except Exception:
                            pass
                cleaned = valid_aadhaar
            elif normalized == "PASSPORT":
                cleaned = [candidate for candidate in cleaned if re.fullmatch(r"[A-Z0-9]{6,9}", re.sub(r"[^A-Za-z0-9]", "", candidate).upper())]
            elif normalized == "DRIVING_LICENSE":
                cleaned = [candidate for candidate in cleaned if re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9,17}", re.sub(r"[^A-Za-z0-9]", "", candidate).upper())]
            elif normalized == "COLLEGE_ID":
                cleaned = [candidate for candidate in cleaned if re.search(r"[A-Za-z0-9]", candidate) and candidate.upper() not in {"CARD", "NUMBER", "NO", "ID"}]
        if not cleaned:
            continue




        chosen = cleaned[0]
        if field in {"name", "father_name", "mother_name"}:
            reference = str(reference_fields.get(field) or (reference_fields.get("name") if field == "name" else "")).strip()
            if reference:
                from difflib import SequenceMatcher
                reference_norm = re.sub(r"[^a-z]", "", reference.lower())
                best_candidate = max(
                    cleaned,
                    key=lambda candidate: SequenceMatcher(
                        None,
                        re.sub(r"[^a-z]", "", candidate.lower()),
                        reference_norm,
                    ).ratio(),
                )
                similarity = SequenceMatcher(
                    None,
                    re.sub(r"[^a-z]", "", best_candidate.lower()),
                    reference_norm,
                ).ratio()
                if similarity >= 0.62:
                    chosen = reference
                else:
                    chosen = best_candidate
        extracted[field] = chosen
    return extracted


def _apply_label_anchor_extraction(fields: dict[str, str], text: str, id_type: str, reference_fields: dict[str, str] | None = None):
    anchored = _extract_label_anchor_fields(text, id_type, reference_fields)
    for key, value in anchored.items():
        if value not in (None, ""):
            fields[key] = value
    return fields


def reference_fields_for_document(id_type: str, values: dict[str, object] | None = None) -> dict[str, str]:
    normalized = _normalize_id_type(id_type)
    configured = _LABEL_ANCHOR_FIELDS.get(normalized, _GENERIC_LABEL_ANCHORS)
    values = values or {}
    return {
        field: str(values.get(field) or "").strip()
        for field in configured
        if str(values.get(field) or "").strip()
    }


def extract_fields(
    text: str,
    id_type: str = "",
    reference_name: str = ""
):

    fields = {
        "name": None,
        "dob": None,
        "document_number": None,
        "passing_year": None,
        "school_name": None,
        "address": None,
        "issue_date": None,
        "validity_nt": None,
        "validity_tr": None,
        "relation_name": None,
        "blood_group": None,
        "organ_donor": None,
        "expiry_date": None,
        "nationality": None,
        "gender": None,
        "father_name": None,
        "mother_name": None,
        "surname": None,
        "given_names": None,
        "place_of_birth": None,
        "place_of_issue": None,
        "institution_name": None,
        "course": None,
        "enrollment_number": None,
        "valid_until": None,
        "board": None,
        "registration_number": None,
        "examination": None,
    }

    if not text:
        return fields

    text = _clean_text(text)

    normalized_type = _normalize_id_type(
        id_type
    )








    explicit_name = _find_explicit_name_marker(text)
    if normalized_type == "PAN":
        fields["name"] = explicit_name or _best_name_candidate(text, reference_name)
    elif normalized_type == "AADHAAR":


        repaired_name = _best_name_candidate(text, reference_name) if reference_name else None
        fields["name"] = repaired_name or _find_name_near_dob(text) or explicit_name
    else:
        fields["name"] = _best_name_candidate(text, reference_name) or explicit_name

    fields["dob"] = _find_dob(
        text,
        allow_standalone=normalized_type != "COLLEGE_ID"
    )



    _apply_label_anchor_extraction(
        fields,
        text,
        normalized_type,
        {"name": reference_name} if reference_name else {},
    )

    if fields["name"] is None and not reference_name and normalized_type not in {"PASSPORT", "COLLEGE_ID"}:
        fields["name"] = _find_name_near_dob(text)






    if normalized_type == "AADHAAR":

        fields["document_number"] = (
            _find_aadhaar_number(text)
        )

    elif normalized_type == "PAN":

        fields["document_number"] = (
            _find_pan_number(text)
        )

    elif normalized_type == "PASSPORT":

        fields["document_number"] = (
            _find_passport_number(text)
        )

    elif normalized_type == "COLLEGE_ID":

        fields["document_number"] = (
            _find_college_id(text)
        )

    elif normalized_type == "DRIVING_LICENSE":

        fields["document_number"] = (
            _find_driving_license(text)
        )






    if fields["document_number"] is None and normalized_type != "AADHAAR":

        fields["document_number"] = (
            _find_generic_document_number(
                text,
                normalized_type
            )
        )





    fields["address"] = _find_address(text)

    if normalized_type == "DRIVING_LICENSE":
        dl_details = _find_driving_license_details(text)
        for key, value in dl_details.items():
            if value not in (None, ""):
                fields[key] = value
        fields["gender"] = fields.get("gender") or _find_gender(text)
        fields["father_name"] = fields.get("father_name") or _find_relation_name(text)

    elif normalized_type == "PASSPORT":
        passport = _find_passport_fields(text)
        for key, value in passport.items():
            if value not in (None, ""):
                fields[key] = value
        if not fields.get("name") and (passport.get("given_names") or passport.get("surname")):
            candidate = " ".join(x for x in (passport.get("given_names"), passport.get("surname")) if x)
            fields["name"] = _clean_name(candidate) or fields.get("name")

        if not fields.get("dob"):
            lines = [re.sub(r"\s+", "", x.upper()) for x in text.splitlines()]
            for i, line in enumerate(lines):
                if line.startswith("P<") and i + 1 < len(lines):
                    second = lines[i + 1]
                    if len(second) >= 19:
                        mrz_dob = _mrz_date_to_iso(second[13:19])
                        if mrz_dob:
                            fields["dob"] = mrz_dob
                            break


        if not fields.get("name"):
            for line in [re.sub(r"\s+", "", x.upper()) for x in text.splitlines()]:
                if line.startswith("P<") and "<<" in line:
                    name_part = line[5:]
                    parts = name_part.split("<<", 1)
                    if len(parts) == 2:
                        surname = parts[0].replace("<", " ").strip()
                        given = parts[1].replace("<", " ").strip()
                        candidate = _clean_name(f"{given} {surname}".strip())
                        if candidate:
                            fields["name"] = candidate
                            break

    elif normalized_type == "PAN":
        for key, value in _find_pan_fields(text).items():
            if value not in (None, ""):
                fields[key] = value

    elif normalized_type == "AADHAAR":
        for key, value in _find_aadhaar_fields(text).items():
            if value not in (None, ""):
                fields[key] = value


        fields["father_name"] = fields.get("father_name") or _find_relation_name(text)
        fields["relation_name"] = fields.get("relation_name") or fields.get("father_name")
        address = _find_address(text)
        if address:
            relation = fields.get("relation_name") or fields.get("father_name")
            relation_norm = re.sub(r"[^a-z]+", " ", str(relation or "").lower()).strip()
            if relation_norm:
                addr_norm = re.sub(r"[^a-z]+", " ", address.lower()).strip()
                if addr_norm.startswith(relation_norm):
                    address = re.sub(
                        r"^\s*" + re.escape(str(relation).strip()) + r"\s*[,;:\-]?\s*",
                        "", address, count=1, flags=re.I,
                    )
            fields["address"] = address or fields.get("address")

    elif normalized_type == "COLLEGE_ID":
        for key, value in _find_college_fields(text).items():
            if value not in (None, ""):
                fields[key] = value




    anchored = _extract_label_anchor_fields(
        text, normalized_type, {"name": reference_name} if reference_name else {}
    )



    if normalized_type == "AADHAAR":
        robust_address = _find_address(text)
        if robust_address:
            anchored["address"] = robust_address
        robust_relation = _find_relation_name(text)
        if robust_relation:
            anchored["father_name"] = robust_relation
            anchored["relation_name"] = robust_relation

    for key, value in anchored.items():
        if value not in (None, ""):
            fields[key] = value

    return {key: value for key, value in fields.items() if value not in (None, "", [], {})}
