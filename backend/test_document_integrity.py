from app.services.document_integrity import build_integrity_screening


def test_integrity_clean_document_has_no_strong_edit_signal():
    result = build_integrity_screening(
        {
            "available": True,
            "features": {
                "ela": {"ela_outlier_ratio": 0.01, "ela_max_z": 2.0},
                "texture": {"texture_outlier_ratio": 0.01, "noise_cv": 0.15, "texture_cv": 0.10},
                "laplacianVariance": 250,
            },
        },
        {"editingMarkers": []},
        {"status": "PASS"},
    )
    assert result["status"] == "NO_STRONG_EDIT_SIGNAL"
    assert result["score"] < 20


def test_integrity_multiple_strong_signals_raise_possible_editing():
    result = build_integrity_screening(
        {
            "available": True,
            "features": {
                "ela": {"ela_outlier_ratio": 0.10, "ela_max_z": 8.0},
                "texture": {"texture_outlier_ratio": 0.12, "noise_cv": 0.90, "texture_cv": 0.40},
                "laplacianVariance": 300,
            },
        },
        {"editingMarkers": ["Software"]},
        {"status": "PASS"},
    )
    assert result["status"] == "POSSIBLE_EDITING"
    assert result["score"] >= 45
