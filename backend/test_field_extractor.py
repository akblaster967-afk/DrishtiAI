import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.services.field_extractor import extract_fields, _best_name_candidate


def test_aadhaar_relation_prefix_extracts_parent_name_before_address_digits():
    from app.services.aadhaar_extractor import _find_relation

    lines = [[
        {"text": "S/O", "conf": 92, "left": 0, "top": 0, "width": 30, "height": 12},
        {"text": "JOWAHER", "conf": 92, "left": 35, "top": 0, "width": 60, "height": 12},
        {"text": "ALI", "conf": 92, "left": 100, "top": 0, "width": 25, "height": 12},
        {"text": "AHMED", "conf": 92, "left": 130, "top": 0, "width": 45, "height": 12},
        {"text": "15", "conf": 92, "left": 180, "top": 0, "width": 15, "height": 12},
        {"text": "GONDA", "conf": 92, "left": 200, "top": 0, "width": 45, "height": 12},
    ]]

    relation, confidence = _find_relation(lines)

    assert relation == "JOWAHER ALI AHMED"
    assert confidence == 92


def test_name_repairs_ocr_noise_using_reference():
    text = "DIVYANSHU MISHRA ides smatwe\n28-01-2002\nDL No: UP3420210003592"
    fields = extract_fields(text, "DRIVING_LICENSE", "Divyanshu Mishra")
    assert fields["name"] == "Divyanshu Mishra"


def test_name_does_not_include_ocr_noise_without_reference():
    text = "DIVYANSHU MISHRA ides smatwe\n28-01-2002"
    candidate = _best_name_candidate(text, "")
    assert candidate != "DIVYANSHU MISHRA ides smatwe"


def test_aadhaar_does_not_use_address_as_name_when_ocr_is_noisy():
    text = "Government of India\nGonda PO Gonda DIST Gonda\nDOB: 04/07/2007\nGender: Male\nAadhaar No: 390424945992"
    fields = extract_fields(text, "AADHAAR")
    assert fields.get("name") is None


def test_aadhaar_prefers_explicit_holder_name_and_relation():
    text = (
        "Name\nAbhishek Gupta\nDOB: 04/07/2007\n"
        "Father: Anand Kumar Gupta\nAddress: Gonda PO Gonda DIST Gonda\n"
        "Aadhaar No: 390424945992"
    )
    fields = extract_fields(text, "AADHAAR")
    assert fields["name"] == "Abhishek Gupta"
    assert fields["father_name"] == "Anand Kumar Gupta"
    assert fields["address"] == "Gonda PO Gonda DIST Gonda"


def test_aadhaar_invalid_labelled_number_is_not_promoted():
    text = "Aadhaar No: 913017706757\nDOB: 04/07/2007\nGender: Male"
    fields = extract_fields(text, "AADHAAR")
    assert fields.get("document_number") is None


def test_pan_keyword_anchor_extracts_value_after_name_labels():
    text = (
        "INCOME TAX DEPARTMENT\nPermanent Account Number Card\nEXLPG7364D\n"
        "Name\nABHISHEK GUPTA\nFather's Name\nANAND KUMAR GUPTA\n"
        "Date of Birth\n04/07/2007"
    )
    fields = extract_fields(text, "PAN")
    assert fields["document_number"] == "EXLPG7364D"
    assert fields["name"] == "ABHISHEK GUPTA"
    assert fields["father_name"] == "ANAND KUMAR GUPTA"
    assert fields["dob"] == "04/07/2007"


def test_anchor_does_not_promote_pan_title_word_as_document_number():
    text = "Permanent Account Number Card\nName\nABHISHEK GUPTA"
    fields = extract_fields(text, "PAN")
    assert fields.get("document_number") is None


def test_anchor_skips_pan_footer_noise_before_name_and_father_values():
    text = (
        "Permanent Account Number Card\nEXLPG7364D\nName\n"
        "Valid unless Physically Signed\nABHISHEK GUPTA\n"
        "Father's Name\nwee i arte\nANAND KUMAR GUPTA\n"
        "Date of Birth\n04/07/2007"
    )

    fields = extract_fields(text, "PAN", "Abhishek Gupta")

    assert fields["name"] == "Abhishek Gupta"
    assert fields["father_name"] == "ANAND KUMAR GUPTA"


def test_anchor_reads_value_on_second_line_after_label():
    text = "Student Name\nAGRIM YADAV\nRoll No\nBE25CS026\nCourse\nBTECH (CSE)"
    fields = extract_fields(text, "COLLEGE_ID")
    assert fields["name"] == "AGRIM YADAV"
    assert fields["document_number"] == "BE25CS026"
    assert fields["course"] == "BTECH (CSE)"


def test_anchor_extraction_is_available_for_all_supported_document_families():
    import app.services.field_extractor as fe
    supported = {
        "PAN", "AADHAAR", "PASSPORT", "DRIVING_LICENSE", "COLLEGE_ID",
        "NATIONAL_ID", "VISA",
    }
    assert supported.issubset(set(fe._LABEL_ANCHOR_FIELDS))
