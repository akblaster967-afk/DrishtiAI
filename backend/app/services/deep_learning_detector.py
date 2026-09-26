from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Any

import numpy as np

try:
    import cv2
    HAVE_CV2 = True
except Exception:
    HAVE_CV2 = False

MODEL_PATH_ENV = "DRISHTI_AI_MODEL_PATH"
DEFAULT_MODEL = "mobilenet_v3_small"





_torch = None
_torchvision = None


def _ensure_torch():
    global _torch, _torchvision
    if _torch is None:
        try:
            import torch
            import torchvision

            _torch = torch
            _torchvision = torchvision
        except Exception:
            _torch = False
            _torchvision = False
    return bool(_torch and _torchvision)


def _load_image_bgr(file_path: str | Path) -> np.ndarray | None:
    data = np.fromfile(str(file_path), dtype=np.uint8)
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def _preprocess_for_cnn(image_bgr: np.ndarray) -> Any:
    torch = _torch
    from torchvision import transforms

    transform = transforms.Compose(
        [
            transforms.ToTensor(),
            transforms.Resize((224, 224), interpolation=transforms.InterpolationMode.BILINEAR),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ]
    )
    rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    tensor = torch.from_numpy(rgb.transpose(2, 0, 1))
    return transform(tensor).unsqueeze(0)


def _build_cnn(model_name: str = DEFAULT_MODEL):
    torchvision = _torchvision
    if model_name == "resnet18":
        weights = torchvision.models.ResNet18_Weights.DEFAULT
        model = torchvision.models.resnet18(weights=weights)
        n_features = model.fc.in_features
        model.fc = _torch.nn.Linear(n_features, 2)
    else:
        weights = torchvision.models.MobileNetV3_Small_Weights.DEFAULT
        model = torchvision.models.mobilenet_v3_small(weights=weights)
        n_features = model.classifier[3].in_features
        model.classifier[3] = _torch.nn.Linear(n_features, 2)
    model.eval()
    return model





def _classical_ai_scorer(image_bgr: np.ndarray) -> dict[str, float]:
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    if gray.size == 0:
        return {"ai_score": 50.0, "real_score": 50.0, "heuristic_components": {}}

    features: dict[str, float] = {}



    h, w = gray.shape
    block = 32
    noise_vars = []
    for y in range(0, h - block, block):
        for x in range(0, w - block, block):
            patch = gray[y : y + block, x : x + block]
            if patch.size == 0:
                continue
            noise_vars.append(float(np.var(cv2.Laplacian(patch, cv2.CV_64F))))
    if noise_vars:
        arr = np.asarray(noise_vars, dtype=np.float64)
        features["texture_noise_cv"] = float(np.std(arr) / max(np.mean(np.abs(arr)), 1e-6))



    try:
        small = cv2.resize(gray, (128, 128), interpolation=cv2.INTER_AREA).astype(np.float32)
        fshift = np.fft.fftshift(np.fft.fft2(small - small.mean()))
        magnitude = np.abs(fshift)
        magnitude /= max(float(magnitude.max()), 1e-9)
        rows, cols = magnitude.shape
        cy, cx = rows // 2, cols // 2
        radius = max(4, min(rows, cols) // 10)
        center_window = magnitude[cy - radius : cy + radius, cx - radius : cx + radius].sum()
        total = float(magnitude.sum())
        features["spectral_energy_ratio"] = float(center_window / max(total, 1e-9))
    except Exception:
        features["spectral_energy_ratio"] = 0.5




    try:
        ok1, enc1 = cv2.imencode(".jpg", image_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
        dec1 = cv2.imdecode(enc1, cv2.IMREAD_COLOR)
        gray1 = cv2.cvtColor(dec1, cv2.COLOR_BGR2GRAY).astype(np.float32)
        ok2, enc2 = cv2.imencode(".jpg", dec1, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
        dec2 = cv2.imdecode(enc2, cv2.IMREAD_COLOR)
        gray2 = cv2.cvtColor(dec2, cv2.COLOR_BGR2GRAY).astype(np.float32)
        features["reencode_drift"] = float(np.mean(np.abs(gray1 - gray2)))
    except Exception:
        features["reencode_drift"] = 0.0


    edges = cv2.Canny(gray, 60, 140)
    if edges.size:
        features["edge_density"] = float(np.mean(edges > 0))
    else:
        features["edge_density"] = 0.0

    return _combine_classical_features(features)


def _combine_classical_features(features: dict[str, float]) -> dict[str, float]:
    noise_cv = features.get("texture_noise_cv", 0.0)
    spectral = features.get("spectral_energy_ratio", 0.5)
    drift = features.get("reencode_drift", 0.0)
    edge = features.get("edge_density", 0.0)



    noise_component = float(np.clip(np.log1p(noise_cv) / 4.0, 0.0, 1.0))
    spectral_component = float(np.clip((0.55 - spectral) * 2.0, 0.0, 1.0))
    drift_component = float(np.clip((2.0 - 200.0 * drift), 0.0, 1.0))
    edge_component = float(np.clip((0.12 - edge) * 8.0, 0.0, 1.0))

    ai_score = 100.0 * (
        0.3 * noise_component
        + 0.3 * spectral_component
        + 0.2 * drift_component
        + 0.2 * edge_component
    )
    ai_score = float(np.clip(ai_score, 0.0, 100.0))
    return {
        "ai_score": round(ai_score, 2),
        "real_score": round(100.0 - ai_score, 2),
        "heuristic_components": {
            "noise_cv": round(features.get("texture_noise_cv", 0.0), 4),
            "spectral_energy_ratio": round(features.get("spectral_energy_ratio", 0.0), 4),
            "reencode_drift": round(features.get("reencode_drift", 0.0), 6),
            "edge_density": round(features.get("edge_density", 0.0), 4),
        },
    }


def _cnn_scorer(model, image_bgr: np.ndarray) -> dict[str, float]:
    torch = _torch
    with torch.no_grad():
        inputs = _preprocess_for_cnn(image_bgr)
        logits = model(inputs)
        probabilities = torch.softmax(logits, dim=1)[0]
        ai_score = float(probabilities[1].item() * 100.0)
    return {
        "ai_score": round(ai_score, 2),
        "real_score": round(100.0 - ai_score, 2),
    }


def detect_ai_generated(
    file_path: str | Path,
    model_name: str = DEFAULT_MODEL,
    checkpoint_path: str | None = None,
) -> dict[str, Any]:
    if not HAVE_CV2:
        return {
            "available": False,
            "reason": "OpenCV is not installed.",
            "ai_score": None,
            "real_score": None,
        }

    image = _load_image_bgr(file_path)
    if image is None:
        return {
            "available": False,
            "reason": "Unable to decode image.",
            "ai_score": None,
            "real_score": None,
        }

    result: dict[str, Any] = {
        "available": True,
        "model": model_name,
        "method": "classical_fallback",
        "ai_score": None,
        "real_score": None,
    }

    if _ensure_torch():
        try:
            model = _build_cnn(model_name)
            checkpoint = checkpoint_path or os.getenv(MODEL_PATH_ENV)
            if checkpoint and Path(checkpoint).exists():
                state = _torch.load(checkpoint, map_location="cpu", weights_only=True)
                model.load_state_dict(state, strict=False)
                result["fine_tuned"] = True
            else:
                result["fine_tuned"] = False
            scores = _cnn_scorer(model, image)
            result["method"] = "cnn"
            result.update(scores)
            return result
        except Exception:

            pass

    result.update(_classical_ai_scorer(image))
    result["note"] = (
        "Torch/torchvision were unavailable, so a classical pixel/frequency "
        "forensic scorer produced the AI probability instead of the CNN."
    )
    return result
