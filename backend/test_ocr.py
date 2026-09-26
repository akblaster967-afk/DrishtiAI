import os
from pathlib import Path
import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.services.ocr import extract_text_from_image


def test_ocr_smoke():
    image_path = os.getenv("DRISHTI_TEST_IMAGE")
    if not image_path or not Path(image_path).exists():
        pytest.skip("Set DRISHTI_TEST_IMAGE to a local document image to run the OCR smoke test.")
    result = extract_text_from_image(image_path, "DRIVING_LICENSE")
    assert "text" in result and "confidence" in result
