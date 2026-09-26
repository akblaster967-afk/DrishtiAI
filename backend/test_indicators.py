import os
from pathlib import Path
import pytest
from app.services.indicator_analyzer import analyze_indicators


def test_indicator_smoke():
    file_path = os.getenv("DRISHTI_TEST_IMAGE")
    if not file_path or not Path(file_path).exists():
        pytest.skip("Set DRISHTI_TEST_IMAGE to a local document image to run the indicator smoke test.")
    result = analyze_indicators(file_path)
    assert "sha256" in result
    assert "indicators" in result
    assert "highest_severity" in result
