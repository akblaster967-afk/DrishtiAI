import hashlib
from pathlib import Path

from PIL import Image


def calculate_sha256(file_path: str):
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as file:
        for chunk in iter(lambda: file.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def analyze_indicators(file_path: str, ocr_confidence=None, identity_results=None):
    path = Path(file_path)
    indicators = []
    file_size = path.stat().st_size

    if file_size < 10 * 1024:
        indicators.append({
            "type": "file_size",
            "severity": "LOW",
            "message": "File size is unusually small.",
        })

    sha256 = calculate_sha256(file_path)
    try:
        image = Image.open(file_path)
        width, height = image.size
        metadata = image.getexif()

        if width < 600 or height < 400:
            indicators.append({
                "type": "resolution",
                "severity": "MEDIUM",
                "message": "Image dimensions are relatively low.",
            })

        software = image.info.get("software") or image.info.get("Software") or metadata.get(305)
        if software:
            indicators.append({
                "type": "software_metadata",
                "severity": "MEDIUM",
                "message": f"Image metadata identifies software: {str(software)[:120]}.",
            })
    except Exception:
        pass

    severity_order = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}
    highest_severity = max((item["severity"] for item in indicators), key=severity_order.get, default="LOW")

    return {
        "sha256": sha256,
        "file_size_bytes": file_size,
        "indicators": indicators,
        "highest_severity": highest_severity,
    }
