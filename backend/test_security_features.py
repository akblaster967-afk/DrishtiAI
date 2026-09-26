from pathlib import Path

import cv2
import numpy as np

from app.services.security_feature_analyzer import analyze_security_features


def _sample(path: Path) -> None:
    image = np.full((800, 1200, 3), 242, dtype=np.uint8)
    cv2.rectangle(image, (20, 20), (250, 260), (230, 230, 230), -1)
    cv2.rectangle(image, (40, 320), (310, 690), (210, 210, 210), -1)
    cv2.putText(image, "NAME", (360, 360), cv2.FONT_HERSHEY_SIMPLEX, 1.6, (30, 30, 30), 3)
    cv2.putText(image, "COURSE", (360, 430), cv2.FONT_HERSHEY_SIMPLEX, 1.6, (30, 30, 30), 3)
    cv2.putText(image, "VALID", (360, 500), cv2.FONT_HERSHEY_SIMPLEX, 1.6, (30, 30, 30), 3)
    cv2.putText(image, "Student Signature", (60, 755), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (20, 20, 120), 2)
    cv2.circle(image, (120, 120), 70, (50, 50, 180), 4)
    cv2.imwrite(str(path), image)


def test_security_feature_layer(tmp_path: Path):
    path = tmp_path / "college.png"
    _sample(path)
    result = analyze_security_features(str(path), "COLLEGE_ID", "NAME COURSE VALID")
    assert result["available"] is True
    assert result["profile"] == "COLLEGE_ID_SRMCE_VISUAL"
    assert "features" in result and len(result["features"]) >= 5
    assert result["score"] is not None
