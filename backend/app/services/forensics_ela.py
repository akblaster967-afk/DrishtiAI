from __future__ import annotations

import base64
import io
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image

ELA_QUALITY = 90
ELA_SCALE = 12.0

_rng = np.random.default_rng(7)


def _load_bgr(file_path: str | Path) -> np.ndarray:
    data = np.fromfile(str(file_path), dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Unable to decode image.")
    return image


def _reencode_as_jpeg(image_bgr: np.ndarray, quality: int) -> np.ndarray:
    ok, encoded = cv2.imencode(
        ".jpg",
        image_bgr,
        [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)],
    )
    if not ok:
        raise ValueError("Unable to re-encode image as JPEG.")
    return cv2.imdecode(encoded, cv2.IMREAD_COLOR)


def compute_ela(
    file_path: str | Path,
    quality: int = ELA_QUALITY,
    scale: float = ELA_SCALE,
) -> dict[str, Any]:
    image_bgr = _load_bgr(file_path)
    height, width = image_bgr.shape[:2]


    max_dim = 1400
    if max(height, width) > max_dim:
        factor = max_dim / float(max(height, width))
        image_bgr = cv2.resize(
            image_bgr,
            (max(1, int(round(width * factor))), max(1, int(round(height * factor)))),
            interpolation=cv2.INTER_AREA,
        )

    resaved = _reencode_as_jpeg(image_bgr, quality)

    gray_original = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    gray_resaved = cv2.cvtColor(resaved, cv2.COLOR_BGR2GRAY).astype(np.float32)

    abs_diff = cv2.absdiff(gray_resaved, gray_original)

    ela_variance = float(abs_diff.var())
    ela_mean = float(abs_diff.mean())
    ela_std = float(abs_diff.std())


    threshold_ratio = 0.08
    hot_fraction = float(
        np.mean((abs_diff / 255.0) > threshold_ratio)
    )



    block_sizes = [max(8, image_bgr.shape[0] // 16), max(8, image_bgr.shape[1] // 16)]
    block_sizes = [max(8, min(96, size)) for size in block_sizes]
    local_max_var = _block_variance_peak(abs_diff, block_sizes)

    score = float(
        np.clip(
            0.28 * ela_variance
            + 0.38 * (100.0 * hot_fraction)
            + 0.34 * min(100.0, local_max_var * 0.15),
            0.0,
            100.0,
        )
    )

    if score >= 55:
        risk_level = "HIGH"
        summary = "ELA shows strongly non-uniform error levels, consistent with local editing or splicing."
    elif score >= 30:
        risk_level = "MEDIUM"
        summary = "ELA shows moderately uneven error levels; verify the highlighted regions manually."
    else:
        risk_level = "LOW"
        summary = "ELA error levels are uniform across the image."

    heatmap = _build_heatmap(abs_diff, image_bgr.shape[:2])
    heatmap_data_url = _to_data_url(heatmap)

    return {
        "summary": summary,
        "risk_level": risk_level,
        "score": round(score, 2),
        "ela_variance": round(ela_variance, 4),
        "ela_mean": round(ela_mean, 4),
        "ela_std": round(ela_std, 4),
        "hot_region_ratio": round(hot_fraction, 4),
        "local_max_variance": round(local_max_var, 4),
        "quality": quality,
        "scale": scale,
        "analyzed_shape": list(image_bgr.shape[:2]),
        "heatmap_data_url": heatmap_data_url,
        "heatmap_png_b64": _to_png_b64(heatmap),
    }


def _block_variance_peak(abs_diff: np.ndarray, block_sizes: list[int]) -> float:
    bh, bw = block_sizes
    block_values: list[float] = []
    rows, cols = abs_diff.shape
    for y in range(0, rows - bh, bh):
        for x in range(0, cols - bw, bw):
            block = abs_diff[y : y + bh, x : x + bw]
            block_values.append(float(block.var()))
    if not block_values:
        return 0.0

    arr = np.asarray(block_values, dtype=np.float64)
    median = float(np.median(arr))
    mad = float(np.median(np.abs(arr - median))) or 1e-6
    z_scores = np.abs(arr - median) / mad
    return float(np.max(arr) if np.any(z_scores >= 3) else np.percentile(arr, 95))


def _build_heatmap(abs_diff: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    heat = np.clip(abs_diff * ELA_SCALE, 0.0, 255.0).astype(np.uint8)
    colored = cv2.applyColorMap(heat, cv2.COLORMAP_JET)
    return cv2.resize(colored, (shape[1], shape[0]), interpolation=cv2.INTER_CUBIC)


def _to_data_url(image_bgr: np.ndarray) -> str:
    ok, encoded = cv2.imencode(
        ".jpg",
        image_bgr,
        [int(cv2.IMWRITE_JPEG_QUALITY), 92],
    )
    return (
        "data:image/jpeg;base64,"
        + base64.b64encode(encoded.tobytes()).decode("ascii")
    )


def _to_png_b64(image_bgr: np.ndarray) -> str:
    ok, encoded = cv2.imencode(".png", image_bgr)
    if not ok:
        return ""
    return base64.b64encode(encoded.tobytes()).decode("ascii")
