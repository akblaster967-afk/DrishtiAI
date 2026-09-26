from app.services.risk_engine import calculate_risk_score
from app.services.cross_document_consistency import build_cross_document_consistency
from app.services.document_profile import check_document_profile


def _base(**overrides):
    data = dict(
        identity_results={},
        ocr_confidence=88,
        quality_result={"overall": "GOOD"},
        indicator_result={"indicators": [], "highest_severity": "LOW"},
        document_consistency={"band": "LOW", "score": 0},
        reference_comparison={"available": False},
        ai_document_analysis={"available": True, "band": "LOW", "score": 5, "signals": []},
        document_verification={
            "documentProfile": {"status": "PASS", "score": 80, "message": "ok"},
            "qrCheck": {"status": "NOT_DETECTED"},
            "schemaChecks": [],
            "securityFeatures": {"overallStatus": "PASS", "reviewCount": 0},
        },
    )
    data.update(overrides)
    return data


def test_low_confidence_advisory_signals_are_capped():
    result = calculate_risk_score(**_base(
        ocr_confidence=42,
        quality_result={"overall": "POOR"},
        indicator_result={"indicators": [{"severity": "MEDIUM"}], "highest_severity": "MEDIUM"},
    ))
    assert result["score"] <= 24
    assert result["analysis_confidence"] == "LOW"


def test_identity_failure_does_not_inflate_document_risk():
    normal = calculate_risk_score(**_base())
    mismatch = calculate_risk_score(**_base(identity_results={
        "name": {"status": "MISMATCH", "reference": "A", "extracted": "B"}
    }))
    assert mismatch["score"] == normal["score"]
    assert mismatch["identity_gate"]["status"] == "FAIL"


def test_qr_mismatch_is_strong_document_evidence():
    result = calculate_risk_score(**_base(
        ocr_confidence=40,
        quality_result={"overall": "POOR"},
        document_verification={
            "documentProfile": {"status": "PASS", "score": 80},
            "qrCheck": {"status": "MISMATCH"},
            "schemaChecks": [],
            "securityFeatures": {"overallStatus": "PASS", "reviewCount": 0},
        },
    ))
    assert result["score"] > 24
    assert "ENCODED_DATA_MISMATCH" in result["hard_flags"]


def test_face_gate_does_not_inflate_document_risk():
    without_face = calculate_risk_score(**_base())
    with_face = calculate_risk_score(**_base(
        face_comparison={"status": "SIMILAR", "verified": True, "score": 40}
    ))
    assert with_face["score"] == without_face["score"]
    assert with_face["score_breakdown"]["faceMatching"] == 0
    assert with_face["signal_risk_scores"]["face_matching"] == 0
    assert with_face["score_breakdown"]["faceGate"] == "SIMILAR"


def test_cross_document_mismatch_routes_to_review():
    result = build_cross_document_consistency(
        {"name": "ANURESH KUMAR MISHRA", "dob": "08/09/2008"},
        [{
            "id": 1,
            "id_type": "COLLEGE_ID",
            "full_name": "ANURESH KUMAR SHARMA",
            "date_of_birth": "08/09/2008",
            "details": "{}",
        }],
        "PAN",
    )
    assert result["available"] is True
    assert result["status"] == "REVIEW"
    assert result["score"] > 0


def test_document_profile_pan_and_conflict_detection():
    good = check_document_profile("PAN", "INCOME TAX DEPARTMENT PAN ABCDE1234F", {"document_number": "ABCDE1234F"})
    assert good["status"] == "PASS"

    bad = check_document_profile("PAN", "AADHAAR CARD GOVERNMENT OF INDIA 1234 5678 9012", {})
    assert bad["status"] == "FAIL"


def test_aadhaar_checksum_uses_standard_verhoeff_and_does_not_false_fail():
    result = calculate_risk_score(**_base(
        ocr_confidence=54,
        document_verification={
            "documentProfile": {"status": "PASS", "score": 90},
            "qrCheck": {"status": "NOT_DETECTED"},
            "schemaChecks": [],
            "securityFeatures": {"overallStatus": "PASS", "reviewCount": 0},
        },
    ))
    assert result["score"] < 25


def test_multiple_medium_forensic_signals_move_to_review_not_low_risk():
    result = calculate_risk_score(**_base(
        ocr_confidence=90,
        quality_result={"overall": "GOOD"},
        indicator_result={"indicators": [], "highest_severity": "LOW"},
        ai_document_analysis={"available": True, "band": "MEDIUM", "score": 25, "signals": [{"severity": "HIGH", "type": "TEXT_RENDERING_MISMATCH"}]},
        document_consistency={"band": "MEDIUM", "score": 24},
        document_verification={
            "documentProfile": {"status": "FAIL", "score": 20},
            "qrCheck": {"status": "NOT_DETECTED"},
            "schemaChecks": [{"field": "document_number", "status": "FAIL"}],
            "securityFeatures": {"overallStatus": "PASS", "reviewCount": 0},
        },
    ))
    assert result["score"] >= 25
    assert result["screening_outcome"] == "REVIEW"


def test_ocr_render_mismatch_does_not_create_ai_score():
    from app.services.ai_document_detector import analyze_ai_document
    from PIL import Image, ImageDraw, ImageFont
    from unittest.mock import patch
    import tempfile
    from pathlib import Path

    image = Image.new("RGB", (1600, 1000), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 50)
    for i, line in enumerate((
        "AADHAAR",
        "Name: Abhishek Gupta",
        "DOB: 04/07/2007",
        "Address: Gonda Uttar Pradesh 271001",
        "Aadhaar: 3904 2494 5992",
    )):
        draw.text((80, 80 + i * 160), line, font=font, fill="black")

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "sample.png"
        image.save(path)
        
        
        with patch(
            "app.services.ai_document_detector._block_texture",
            return_value={"texture_cv": 0.0, "noise_cv": 0.0, "texture_outlier_ratio": 0.0},
        ), patch(
            "app.services.ai_document_detector._ela_signal",
            return_value={"ela_outlier_ratio": 0.0, "ela_max_z": 0.0},
        ), patch(
            "app.services.ai_document_detector.cv2.Laplacian",
            return_value=__import__("numpy").arange(70, dtype=float).reshape(7, 10),
        ), patch(
            "app.services.ai_document_detector.cv2.Canny",
            return_value=__import__("numpy").zeros((1000, 1600), dtype="uint8"),
        ):
            result = analyze_ai_document(str(path), "AADHAAR", 40, "A" * 90, {})

        assert result["score"] == 0
        assert not any(signal.get("type") == "TEXT_RENDERING_MISMATCH" for signal in result["signals"])
        assert any(signal.get("type") == "TEXT_RENDERING_MISMATCH" for signal in result["qualitySignals"])


def test_risk_score_ignores_ocr_quality_note():
    normal = calculate_risk_score(**_base())
    with_quality_note = calculate_risk_score(**_base(
        ai_document_analysis={
            "available": True,
            "band": "LOW",
            "score": 0,
            "signals": [],
            "qualitySignals": [{
                "type": "TEXT_RENDERING_MISMATCH",
                "severity": "REVIEW",
                "message": "OCR readability is weak.",
            }],
        },
    ))
    assert with_quality_note["score"] == normal["score"]


def test_aadhaar_relation_name_is_not_selected_as_holder_name():
    from app.services.aadhaar_extractor import _find_name, _find_relation, _find_address

    def tok(text, left, top, conf=95):
        return {"text": text, "left": left, "top": top, "width": 50, "height": 20, "conf": conf}

    lines = [
        [tok("S/O", 0, 100), tok("Anand", 60, 100), tok("Kumar", 125, 100), tok("Gupta", 200, 100)],
        [tok("Abhishek", 0, 140), tok("Gupta", 100, 140)],
        [tok("DOB:", 0, 180), tok("04/07/2007", 70, 180)],
        [tok("Address:", 0, 220), tok("S/O:", 90, 220), tok("Anand", 145, 220), tok("Kumar", 210, 220), tok("Gupta", 275, 220), tok("Gonda", 345, 220), tok("Uttar", 410, 220), tok("Pradesh", 480, 220), tok("271001", 560, 220)],
    ]
    relation, _ = _find_relation(lines)
    name, _ = _find_name(lines, "04/07/2007", relation=relation)
    address, _ = _find_address(lines, relation=relation)

    assert relation == "Anand Kumar Gupta"
    assert name == "Abhishek Gupta"
    assert address == "Gonda Uttar Pradesh 271001"


def test_aadhaar_relation_and_multiline_address_are_cleaned():
    from app.services.field_extractor import extract_fields

    result = extract_fields(
        """Government of India\nAgrim Yadav\n06/08/2007\n"""
        "C/O: Anand Narayan Yadav 90, Daimand Dairy\n"
        "Udayganj Lucknow Lucknow G.p Lucknow Uttar\n"
        "Pradesh - 226001\nMALE\n",
        "AADHAAR",
    )
    assert result["father_name"] == "Anand Narayan Yadav"
    assert result["relation_name"] == "Anand Narayan Yadav"
    assert result["address"].startswith("90, Daimand Dairy")
    assert "Udayganj" in result["address"]
    assert result["address"].endswith("226001")


def test_aadhaar_multiline_address_survives_final_anchor_pass():
    from app.services.field_extractor import extract_fields

    text = (
        "Agrim Yadav\nDOB : 06/08/2007\nMALE\n3435 5321 6457\n"
        "Address\n+ or\nC.5 bias\nC/O: Anand Narayan Yadav 90, Daimand Dairy\n"
        "Udayganj Lucknow Lucknow G.p Lucknow Uttar\nPradesh - 226001"
    )
    result = extract_fields(text, "AADHAAR")
    assert result["address"].startswith("90, Daimand Dairy")
    assert "or" not in result["address"].lower().split(",")[0]
    assert "Udayganj" in result["address"]
