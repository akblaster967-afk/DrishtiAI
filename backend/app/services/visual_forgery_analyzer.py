from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import numpy as np
from app.services.pdf_images import load_pdf_page_image


def _load_image(file_path: str) -> np.ndarray | None:
    try:
        path = Path(file_path)
        if path.suffix.lower() == ".pdf":
            return load_pdf_page_image(path, 0)
        data = np.fromfile(str(path), dtype=np.uint8)
        return cv2.imdecode(data, cv2.IMREAD_COLOR)
    except Exception:
        return None


def _crop(image: np.ndarray, box: tuple[float, float, float, float]) -> np.ndarray:
    h, w = image.shape[:2]
    x1, y1, x2, y2 = box
    return image[max(0, int(y1 * h)):min(h, int(y2 * h)), max(0, int(x1 * w)):min(w, int(x2 * w))]


def _variation(values: list[float]) -> float:
    if len(values) < 4:
        return 0.0
    array = np.asarray(values, dtype=np.float64)
    return float(np.std(array) / max(abs(float(np.mean(array))), 0.1))


def _text_geometry(image: np.ndarray) -> dict[str, Any]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    connected = cv2.connectedComponentsWithStats(binary, 8)




    if len(connected) == 4:
        _, _, stats, _ = connected
    elif len(connected) == 3:
        _, stats, _ = connected
    else:
        return {"available": False, "tokenCount": 0, "heightVariation": 0.0, "lineSpacingVariation": 0.0}
    boxes: list[tuple[int, int, int, int]] = []
    image_area = float(gray.shape[0] * gray.shape[1])
    for left, top, width, height, area in stats[1:]:
        if 2 <= width <= gray.shape[1] * 0.25 and 3 <= height <= gray.shape[0] * 0.12 and 6 <= area <= image_area * 0.02:
            boxes.append((int(left), int(top), int(width), int(height)))
    heights = [box[3] for box in boxes]
    centers = sorted(box[1] + box[3] / 2 for box in boxes)
    gaps = [centers[index] - centers[index - 1] for index in range(1, len(centers)) if centers[index] - centers[index - 1] > 2]
    return {
        "available": bool(boxes),
        "tokenCount": len(boxes),
        "heightVariation": round(_variation([float(value) for value in heights]), 4),
        "lineSpacingVariation": round(_variation([float(value) for value in gaps]), 4),
    }


def _region_texture(region: np.ndarray) -> tuple[float, float]:
    if region.size == 0:
        return 0.0, 0.0
    gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var()), float(np.var(cv2.subtract(gray, cv2.GaussianBlur(gray, (3, 3), 0))))


def _photo_region(image: np.ndarray, id_type: str) -> dict[str, Any]:
    normalized = str(id_type or "").upper()

    box = (0.03, 0.10, 0.34, 0.72)
    if normalized in {"PASSPORT", "DRIVING_LICENSE"}:
        box = (0.02, 0.04, 0.45, 0.68)
    elif normalized == "AADHAAR":
        box = (0.02, 0.18, 0.48, 0.82)
    portrait = _crop(image, box)
    background = np.concatenate([_crop(image, (0.50, 0.08, 0.95, 0.30)).reshape(-1, 3), _crop(image, (0.50, 0.70, 0.95, 0.94)).reshape(-1, 3)])
    portrait_lap, portrait_noise = _region_texture(portrait)
    background_lap, background_noise = _region_texture(background.reshape(-1, 1, 3))
    lap_ratio = portrait_lap / max(background_lap, 1.0)
    noise_ratio = portrait_noise / max(background_noise, 0.1)
    suspicious = bool((lap_ratio > 8.0 and noise_ratio > 3.0) or (lap_ratio < 0.08 and noise_ratio < 0.18))
    return {
        "available": bool(portrait.size),
        "portraitSharpness": round(portrait_lap, 2),
        "cardSharpness": round(background_lap, 2),
        "portraitNoiseRatio": round(noise_ratio, 3),
        "suspicious": suspicious,
    }


def _resampling(image: np.ndarray) -> dict[str, Any]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape[:2]
    sharpness: list[float] = []
    block_error: list[float] = []
    for row in range(4):
        for column in range(4):
            tile = gray[int(row * h / 4):int((row + 1) * h / 4), int(column * w / 4):int((column + 1) * w / 4)]
            if tile.size:
                sharpness.append(float(cv2.Laplacian(tile, cv2.CV_64F).var()))
                block_error.append(float(np.mean(np.abs(tile[:, 1:].astype(np.float32) - tile[:, :-1].astype(np.float32)))))
    sharpness_cv = _variation(sharpness)
    block_cv = _variation(block_error)
    suspicious = bool(sharpness_cv >= 1.15 and block_cv >= 0.55)
    return {"available": bool(sharpness), "tileSharpnessVariation": round(sharpness_cv, 4), "tileCompressionVariation": round(block_cv, 4), "suspicious": suspicious}


def analyze_visual_forgery(file_path: str, id_type: str) -> dict[str, Any]:
    image = _load_image(file_path)
    if image is None:
        return {"available": False, "signals": [], "features": {}, "status": "UNAVAILABLE"}

    geometry = _text_geometry(image)
    photo = _photo_region(image, id_type)
    resampling = _resampling(image)
    signals: list[dict[str, str]] = []
    if geometry["available"] and geometry["tokenCount"] >= 12:
        if geometry["heightVariation"] >= 0.85 or geometry["lineSpacingVariation"] >= 1.0:
            signals.append({"type": "TEXT_GEOMETRY_ANOMALY", "severity": "MEDIUM", "message": "OCR text boxes have unusually inconsistent character sizing or line spacing."})
    if photo.get("suspicious"):
        signals.append({"type": "PHOTO_REGION_INCONSISTENCY", "severity": "HIGH", "message": "The portrait region has sharpness/noise characteristics that differ substantially from the surrounding card."})
    if resampling.get("suspicious"):
        signals.append({"type": "RESAMPLING_INCONSISTENCY", "severity": "MEDIUM", "message": "Image tiles show uneven sharpness and compression response consistent with recompositing or repeated resampling."})

    return {
        "available": True,
        "status": "REVIEW" if signals else "PASS",
        "signals": signals,
        "features": {"textGeometry": geometry, "photoRegion": photo, "resampling": resampling},
        "notice": "Visual forgery signals are advisory and should be combined with document rules and issuer verification.",
    }
