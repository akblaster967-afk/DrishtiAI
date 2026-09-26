import os
from pathlib import Path
import pytest
from app.services.quality_analyzer import analyze_image_quality


def test_quality_smoke():
    image_path = os.getenv("DRISHTI_TEST_IMAGE")
    if not image_path or not Path(image_path).exists():
        pytest.skip("Set DRISHTI_TEST_IMAGE to a local document image to run the quality smoke test.")
    result = analyze_image_quality(image_path)
    assert result["overall"] in {"GOOD", "MODERATE", "POOR"}
    assert "skew" in result and "glare" in result
