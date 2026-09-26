import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.services.universal_field_extractor import extract_universal_field_result


def test_universal_extracts_values_from_label_value_table_rows():
    text = "Name | DOB | Gender\nAbhishek Gupta | 04/07/2007 | Male"

    fields = extract_universal_field_result(text, "AUTO")["fields"]

    assert fields["name"] == "Abhishek Gupta"
    assert fields["dob"] == "04/07/2007"
    assert fields["gender"] == "MALE"


def test_universal_extracts_multiline_address_with_embedded_district_label():
    text = "Name\nAbhishek Gupta\nAddress\nGonda PO Gonda DIST Gonda\nUttar Pradesh 271001"

    fields = extract_universal_field_result(text, "AUTO")["fields"]

    assert fields["address"] == "Gonda PO Gonda DIST Gonda, Uttar Pradesh 271001"


def test_universal_extracts_family_specific_identifier_and_alias():
    text = "Permanent Account Number Card\nPAN No: EXLPG7364D\nName: Abhishek Gupta"

    result = extract_universal_field_result(text, "PAN")

    assert result["fields"]["pan_number"] == "EXLPG7364D"
    assert result["fields"]["document_number"] == "EXLPG7364D"


def test_universal_skips_pan_footer_noise_before_name_and_father_values():
    text = (
        "Permanent Account Number Card\nEXLPG7364D\nName\n"
        "Valid unless Physically Signed\nABHISHEK GUPTA\n"
        "Father's Name\nwee i arte\nANAND KUMAR GUPTA\n"
        "Date of Birth\n04/07/2007"
    )

    fields = extract_universal_field_result(text, "PAN", {"name": "Abhishek Gupta"})["fields"]

    assert fields["name"] == "Abhishek Gupta"
    assert fields["father_name"] == "ANAND KUMAR GUPTA"
