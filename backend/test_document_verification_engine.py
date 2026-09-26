from app.services.document_verification_engine import _fabrication_screen, build_document_verification


def test_college_id_schema_and_fingerprint(tmp_path):
    path = tmp_path / "sample.jpg"
    
    path.write_bytes(b"not-an-image")
    result = build_document_verification(
        str(path),
        "COLLEGE_ID",
        {"name": "ANURESH KUMAR MISHRA", "document_number": "BE25CS014", "course": "BTECH (CSE)", "valid_until": "2025 - 2029"},
        91.0,
        "NAME ANURESH KUMAR MISHRA ROLL BE25CS014 COURSE BTECH CSE VALID 2025 2029",
        {"band": "LOW", "score": 4, "signals": [], "notice": "test"},
    )
    assert result["available"] is True
    assert result["issuerVerification"]["status"] == "NOT_CONFIGURED"
    assert result["sha256"]


def test_aadhaar_verhoeff_candidate_is_not_marked_invalid_by_bad_table():
    result = build_document_verification(
        "/tmp/not-an-image",
        "AADHAAR",
        {"name": "TEST PERSON", "document_number": "390424945992"},
        54.0,
        "AADHAAR GOVERNMENT OF INDIA 3904 2494 5992",
        {"band": "LOW", "score": 4, "signals": []},
    )
    checks = {item["field"]: item for item in result["schemaChecks"]}
    assert checks["AADHAAR_CHECKSUM"]["status"] == "PASS"


def test_valid_pan_format_does_not_imply_genuine_document():
    result = _fabrication_screen(
        "PAN",
        {"document_number": "AGTPH9173J", "name": "MD AMIR HAMZA"},
        [
            {"field": "name", "status": "PASS"},
            {"field": "document_number", "status": "PASS"},
        ],
        {"status": "PASS"},
        {"status": "PASS"},
        {"status": "NOT_DETECTED"},
        {"overallStatus": "REVIEW", "summary": "Expected security cues require review."},
        {"status": "POSSIBLE_EDITING", "summary": "Independent image signals indicate local editing."},
        {"band": "LOW", "signals": []},
        {"signals": [{"type": "PHOTO_REGION_INCONSISTENCY", "severity": "HIGH", "message": "Portrait region differs from card texture."}]},
        {"band": "LOW"},
    )
    assert result["verdict"] == "FABRICATED_OR_TAMPERED"
    assert result["status"] == "HIGH"


def test_supported_document_types_flag_sample_identifiers():
    common = {
        "schema": [{"field": "document_number", "status": "PASS"}],
        "keywords": {"status": "PASS"},
        "profile": {"status": "PASS"},
        "qr": {"status": "NOT_DETECTED"},
        "security": {"overallStatus": "PASS"},
        "integrity": {"status": "NO_STRONG_EDIT_SIGNAL"},
        "ai": {"band": "LOW", "signals": []},
        "visual": {"signals": []},
        "consistency": {"band": "LOW"},
    }
    samples = {
        "AADHAAR": "123456789012",
        "PASSPORT": "U1234567",
        "DRIVING_LICENSE": "DL000000",
        "COLLEGE_ID": "BE25CS000",
    }
    for id_type, number in samples.items():
        result = _fabrication_screen(
            id_type,
            {"document_number": number},
            common["schema"], common["keywords"], common["profile"], common["qr"],
            common["security"], common["integrity"], common["ai"], common["visual"], common["consistency"],
        )
        assert any(signal["type"] in {"PLACEHOLDER_IDENTIFIER", "DOCUMENT_TYPE_SAMPLE_IDENTIFIER", "SEQUENTIAL_OR_REPEATED_IDENTIFIER"} for signal in result["signals"]), id_type
