
import re
from difflib import SequenceMatcher








DOCUMENT_IDENTITY_FIELDS = {
    "PASSPORT": (
        "name",
        "dob",
        "document_number",
        "nationality",
    ),

    "AADHAAR": (
        "name",
        "dob",
        "document_number",
        "address",
        "father_name",
    ),

    "PAN": (
        "name",
        "document_number",
        "father_name",
    ),

    "COLLEGE_ID": (
        "name",
        "document_number",
    ),

    "DRIVING_LICENSE": (
        "name",
        "dob",
        "document_number",
        "address",
        "father_name",
    ),

    "VISA": (
        "name",
        "dob",
        "document_number",
        "nationality",
    ),

}






def normalize_text(value):
    if value is None:
        return ""

    value = str(value).lower()

    return re.sub(
        r"[^a-z0-9]",
        "",
        value,
    )


def normalize_date(value):
    raw = str(value or "").strip()
    for pattern in (
        r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$",
        r"^(\d{1,2})[-/](\d{1,2})[-/](\d{4})$",
    ):
        match = re.match(pattern, raw)
        if not match:
            continue
        a, b, c = map(int, match.groups())
        if len(match.group(1)) == 4:
            year, month, day = a, b, c
        else:
            day, month, year = a, b, c
        if 1 <= month <= 12 and 1 <= day <= 31:
            return f"{year:04d}{month:02d}{day:02d}"
    return normalize_text(raw)






def similarity_score(
    value1,
    value2,
):
    value1 = normalize_text(
        value1,
    )

    value2 = normalize_text(
        value2,
    )

    if not value1 or not value2:
        return 0

    return SequenceMatcher(
        None,
        value1,
        value2,
    ).ratio()






def compare_field(
    reference_value,
    extracted_value,
    field_name=None,
):
    if (
        reference_value is None
        or extracted_value is None
    ):
        return "NOT_APPLICABLE"

    reference_value = str(
        reference_value
    ).strip()

    extracted_value = str(
        extracted_value
    ).strip()

    if not reference_value:
        return "NOT_APPLICABLE"

    if not extracted_value:
        return "UNKNOWN"

    if str(field_name or "").lower() == "dob":
        reference = normalize_date(reference_value)
        extracted = normalize_date(extracted_value)
    else:
        reference = normalize_text(reference_value)
        extracted = normalize_text(extracted_value)

    if not reference:
        return "NOT_APPLICABLE"

    if reference == extracted:
        return "MATCH"

    similarity = similarity_score(
        reference_value,
        extracted_value,
    )

    if similarity >= 0.70:
        return "PARTIAL"

    return "MISMATCH"






def normalize_document_type(
    id_type,
):
    value = str(
        id_type or ""
    ).strip().upper()

    aliases = {
        "AADHAAR CARD":
            "AADHAAR",

        "AADHAR":
            "AADHAAR",

        "AADHAR CARD":
            "AADHAAR",

        "PAN CARD":
            "PAN",

        "COLLEGE ID CARD":
            "COLLEGE_ID",

        "COLLEGE ID":
            "COLLEGE_ID",

        "STUDENT ID":
            "COLLEGE_ID",

        "STUDENT CARD":
            "COLLEGE_ID",

        "DRIVING LICENSE":
            "DRIVING_LICENSE",

        "DRIVING LICENCE":
            "DRIVING_LICENSE",

        "DL":
            "DRIVING_LICENSE",

        "VISA":
            "VISA",

        "VISA CARD":
            "VISA",

        "TOURIST VISA":
            "VISA",

        "ENTRY VISA":
            "VISA",

        "WORK VISA":
            "VISA",

        "STUDENT VISA":
            "VISA",

    }

    return aliases.get(
        value,
        value,
    )






def get_applicable_identity_fields(
    id_type,
):
    normalized_type = (
        normalize_document_type(
            id_type,
        )
    )

    return DOCUMENT_IDENTITY_FIELDS.get(
        normalized_type,
        (
            "name",
            "document_number",
        ),
    )






def compare_identity(
    reference_fields,
    extracted_fields,
    id_type=None,
):

    reference_fields = (
        reference_fields or {}
    )

    extracted_fields = (
        extracted_fields or {}
    )

    fields = (
        get_applicable_identity_fields(
            id_type,
        )
    )

    results = {}

    for field in fields:

        reference_value = (
            reference_fields.get(
                field,
            )
        )

        extracted_value = (
            extracted_fields.get(
                field,
            )
        )

        results[field] = {
            "reference":
                reference_value,

            "extracted":
                extracted_value,

            "status":
                compare_field(
                    reference_value,
                    extracted_value,
                    field,
                ),
        }

    return results
