from __future__ import annotations

import math
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageStat


def _load_image(file_path: str):
    data = np.fromfile(str(file_path), dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Unable to decode image")
    return image


def _skew_angle(gray):
    edges = cv2.Canny(gray, 50, 150)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=80,
                            minLineLength=max(80, min(gray.shape) // 5), maxLineGap=12)
    if lines is None:
        return 0.0
    angles = []
    for line in lines[:, 0]:
        x1, y1, x2, y2 = map(int, line)
        angle = math.degrees(math.atan2(y2 - y1, x2 - x1))
        if -15 <= angle <= 15:
            angles.append(angle)
    return float(np.median(angles)) if angles else 0.0


def analyze_image_quality(file_path: str):
    image = Image.open(file_path).convert("RGB")
    width, height = image.size
    total_pixels = width * height
    grayscale = image.convert("L")
    statistics = ImageStat.Stat(grayscale)
    brightness = float(statistics.mean[0])
    contrast = float(statistics.stddev[0])

    cv_image = _load_image(file_path)
    gray = cv2.cvtColor(cv_image, cv2.COLOR_BGR2GRAY)
    laplacian_variance = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    blur_score = math.sqrt(max(laplacian_variance, 0.0))

    if width >= 1200 and height >= 800:
        resolution_status = "GOOD"
    elif width >= 700 and height >= 450:
        resolution_status = "MODERATE"
    else:
        resolution_status = "POOR"

    if 65 <= brightness <= 195:
        brightness_status = "GOOD"
    elif 40 <= brightness < 65 or 195 < brightness <= 225:
        brightness_status = "MODERATE"
    else:
        brightness_status = "POOR"

    if contrast >= 40:
        contrast_status = "GOOD"
    elif contrast >= 22:
        contrast_status = "MODERATE"
    else:
        contrast_status = "POOR"

    if laplacian_variance >= 180:
        blur_status = "GOOD"
    elif laplacian_variance >= 45:
        blur_status = "MODERATE"
    else:
        blur_status = "POOR"

    skew = _skew_angle(gray)
    skew_status = "GOOD" if abs(skew) <= 2.5 else ("MODERATE" if abs(skew) <= 6 else "POOR")


    hsv = cv2.cvtColor(cv_image, cv2.COLOR_BGR2HSV)
    glare_mask = ((hsv[:, :, 1] < 35) & (hsv[:, :, 2] > 245)).astype(np.uint8)
    glare_ratio = float(glare_mask.mean())
    glare_status = "GOOD" if glare_ratio < 0.025 else ("MODERATE" if glare_ratio < 0.08 else "POOR")



    edges = cv2.Canny(gray, 60, 160)
    edge_density = float((edges > 0).mean())
    edge_status = "GOOD" if 0.02 <= edge_density <= 0.35 else "MODERATE"

    statuses = [resolution_status, brightness_status, contrast_status, blur_status, skew_status, glare_status]
    poor_count = statuses.count("POOR")
    moderate_count = statuses.count("MODERATE")
    overall_status = "POOR" if poor_count >= 2 else ("MODERATE" if poor_count == 1 or moderate_count >= 2 else "GOOD")

    return {
        "resolution": {"width": width, "height": height, "pixels": total_pixels, "status": resolution_status},
        "brightness": {"value": round(brightness, 2), "status": brightness_status},
        "contrast": {"value": round(contrast, 2), "status": contrast_status},
        "blur": {"score": round(blur_score, 2), "laplacian_variance": round(laplacian_variance, 2), "status": blur_status},
        "skew": {"angle_degrees": round(skew, 2), "status": skew_status},
        "glare": {"ratio": round(glare_ratio, 4), "status": glare_status},
        "edge_density": {"value": round(edge_density, 5), "status": edge_status},
        "overall": overall_status,
    }
