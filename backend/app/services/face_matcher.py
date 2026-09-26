from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from app.services.pdf_images import load_pdf_page_image, load_pdf_page_image_high_res


class FaceComparisonError(Exception):
    pass


_FACE_CASCADE = cv2.CascadeClassifier(
    str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml")
)
_EYE_CASCADE = cv2.CascadeClassifier(
    str(Path(cv2.data.haarcascades) / "haarcascade_eye.xml")
)


def _load_image(path: str | Path, *, high_res: bool = True) -> np.ndarray:
    path = Path(path)
    if path.suffix.lower() == ".pdf":
        try:
            image_loader = load_pdf_page_image_high_res if high_res else load_pdf_page_image
            image = image_loader(path, 0)
            if image is None:
                raise FaceComparisonError("The document has no readable first page.")
            return image
        except FaceComparisonError:
            raise
        except Exception as exc:
            raise FaceComparisonError(f"Unable to render the document: {exc}") from exc

    data = path.read_bytes()
    image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise FaceComparisonError("The uploaded document is not a readable image.")
    return image


def _iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    x0, y0 = max(ax, bx), max(ay, by)
    x1, y1 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    inter = max(0, x1 - x0) * max(0, y1 - y0)
    if inter <= 0:
        return 0.0
    union = aw * ah + bw * bh - inter
    return inter / max(1, union)


_FACE_CASCADES = [
    _FACE_CASCADE,
    cv2.CascadeClassifier(str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_alt.xml")),
    cv2.CascadeClassifier(str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_alt2.xml")),
    cv2.CascadeClassifier(str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_alt_tree.xml")),
    cv2.CascadeClassifier(str(Path(cv2.data.haarcascades) / "haarcascade_profileface.xml")),
]

def _detect_faces(image: np.ndarray, require_eye: bool = False) -> list[tuple[int, int, int, int]]:
    if image is None or image.size == 0:
        return []
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)
    candidates: list[tuple[tuple[int, int, int, int], int]] = []
    for cascade_index, cascade in enumerate(_FACE_CASCADES):
        if cascade.empty():
            continue
        for scale in (1.0, 1.5):
            work = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
            faces = cascade.detectMultiScale(
                work, scaleFactor=1.06, minNeighbors=5, minSize=(40, 40)
            )
            for x, y, w, h in faces:
                box = (int(x / scale), int(y / scale), int(w / scale), int(h / scale))
                candidates.append((box, cascade_index))


    clusters: list[dict[str, Any]] = []
    for box, detector_id in sorted(candidates, key=lambda item: item[0][2] * item[0][3], reverse=True):
        placed = False
        for cluster in clusters:
            if _iou(box, cluster["box"]) >= 0.28:
                cluster["boxes"].append(box)
                cluster["detectors"].add(detector_id)

                if box[2] * box[3] > cluster["box"][2] * cluster["box"][3]:
                    cluster["box"] = box
                placed = True
                break
        if not placed:
            clusters.append({"box": box, "boxes": [box], "detectors": {detector_id}})



    unique: list[tuple[int, int, int, int]] = []
    image_area = float(image.shape[0] * image.shape[1])
    for cluster in clusters:
        if len(cluster["detectors"]) < 2:
            continue
        box = cluster["box"]
        x, y, w, h = box
        if min(w, h) < 60 or (w * h) / image_area < 0.004:
            continue
        if require_eye:




            x0, y0 = max(0, x), max(0, y)
            x1, y1 = min(image.shape[1], x + w), min(image.shape[0], y + h)
            candidate = gray[y0:y1, x0:x1]
            if candidate.size == 0:
                continue
            eyes = _EYE_CASCADE.detectMultiScale(
                candidate, scaleFactor=1.08, minNeighbors=5, minSize=(max(10, int(w * 0.08)), max(10, int(h * 0.08)))
            )
            upper_eyes = [
                (ex, ey, ew, eh) for ex, ey, ew, eh in eyes
                if ey + eh / 2.0 < h * 0.62
            ]
            if not upper_eyes:
                continue
        if not any(_iou(box, existing) >= 0.35 for existing in unique):
            unique.append(box)

    return sorted(unique, key=lambda b: b[2] * b[3], reverse=True)


def _simple_face_candidates(image: np.ndarray, require_eye: bool = False) -> list[tuple[int, int, int, int]]:
    if image is None or image.size == 0:
        return []
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)
    h, w = image.shape[:2]
    min_side = max(32, int(min(h, w) * 0.035))
    candidates: list[tuple[int, int, int, int, int]] = []
    for detector_id, cascade in enumerate(_FACE_CASCADES):
        if cascade.empty():
            continue
        for scale in (1.0, 1.25):
            work = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
            found = cascade.detectMultiScale(
                work,
                scaleFactor=1.05,
                minNeighbors=4,
                minSize=(min_side, min_side),
            )
            for x, y, fw, fh in found:
                box = (int(x / scale), int(y / scale), int(fw / scale), int(fh / scale))
                bx, by, bw, bh = box
                ratio = bw / max(1.0, float(bh))
                area_ratio = (bw * bh) / float(w * h)
                if ratio < 0.55 or ratio > 1.65:
                    continue
                if area_ratio < 0.0015 or area_ratio > 0.45:
                    continue
                candidates.append((*box, detector_id))

    if not candidates:
        return []


    clusters: list[dict[str, Any]] = []
    for x, y, fw, fh, detector_id in sorted(
        candidates, key=lambda item: item[2] * item[3], reverse=True
    ):
        box = (x, y, fw, fh)
        placed = False
        for cluster in clusters:
            if _iou(box, cluster["box"]) >= 0.30:
                cluster["boxes"].append(box)
                cluster["detectors"].add(detector_id)
                if fw * fh > cluster["box"][2] * cluster["box"][3]:
                    cluster["box"] = box
                placed = True
                break
        if not placed:
            clusters.append({"box": box, "boxes": [box], "detectors": {detector_id}})

    out: list[tuple[int, int, int, int]] = []
    for cluster in clusters:
        x, y, fw, fh = cluster["box"]
        cx, cy = x + fw / 2.0, y + fh / 2.0
        area_ratio = (fw * fh) / float(w * h)
        center_bonus = max(0.0, 1.0 - (abs(cx - w / 2.0) / (w / 2.0))) * 0.18
        detector_bonus = 0.12 if len(cluster["detectors"]) >= 2 else 0.0
        eye_bonus = 0.0
        if require_eye:
            crop = gray[max(0, y):min(h, y + fh), max(0, x):min(w, x + fw)]
            if crop.size:
                eyes = _EYE_CASCADE.detectMultiScale(
                    crop,
                    scaleFactor=1.08,
                    minNeighbors=4,
                    minSize=(max(8, int(fw * 0.07)), max(8, int(fh * 0.07))),
                )
                upper = [ey for ex, ey, ew, eh in eyes if ey + eh / 2.0 < fh * 0.65]
                if upper:
                    eye_bonus = 0.22



        size_score = min(1.0, area_ratio / 0.08)
        score = size_score * 0.60 + center_bonus + detector_bonus + eye_bonus
        cluster["score"] = score

    clusters.sort(key=lambda item: item["score"], reverse=True)
    for cluster in clusters:
        box = cluster["box"]
        if not any(_iou(box, existing) >= 0.35 for existing in out):
            out.append(box)
    return out


def _document_region(image: np.ndarray) -> np.ndarray:
    if image is None or image.size == 0:
        return image
    h, w = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


    mask = cv2.inRange(gray, 150, 255)
    kernel = np.ones((max(5, int(min(h, w) * 0.02)),) * 2, np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    best_rect = None
    best_area = 0.0
    image_area = float(h * w)
    for contour in contours:
        x, y, rw, rh = cv2.boundingRect(contour)
        area = float(rw * rh)
        ratio = rw / max(1.0, float(rh))
        area_ratio = area / image_area
        if area_ratio < 0.20 or area_ratio > 0.98:
            continue
        if ratio < 0.45 or ratio > 2.6:
            continue
        if area > best_area:
            best_area = area
            best_rect = (x, y, rw, rh)

    if best_rect is not None:
        x, y, rw, rh = best_rect
        pad = max(4, int(min(rw, rh) * 0.015))
        x0, y0 = max(0, x - pad), max(0, y - pad)
        x1, y1 = min(w, x + rw + pad), min(h, y + rh + pad)
        region = image[y0:y1, x0:x1].copy()
        if region.size and region.shape[0] >= 120 and region.shape[1] >= 160:
            return region


    edges = cv2.Canny(gray, 60, 160)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:12]:
        perimeter = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, 0.03 * perimeter, True)
        if len(approx) != 4:
            continue
        x, y, rw, rh = cv2.boundingRect(approx)
        area_ratio = (rw * rh) / image_area
        ratio = rw / max(1.0, float(rh))
        if 0.20 <= area_ratio <= 0.98 and 0.45 <= ratio <= 2.6:
            pad = max(4, int(min(rw, rh) * 0.015))
            x0, y0 = max(0, x - pad), max(0, y - pad)
            x1, y1 = min(w, x + rw + pad), min(h, y + rh + pad)
            return image[y0:y1, x0:x1].copy()
    return image


def _ocr_text_boxes(image: np.ndarray) -> list[tuple[int, int, int, int, float, str]]:
    if image is None or image.size == 0:
        return []
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    if max(gray.shape[:2]) > 2200:
        scale = 2200 / float(max(gray.shape[:2]))
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    try:
        data = pytesseract.image_to_data(
            gray, lang="eng", config="--oem 3 --psm 11",
            output_type=pytesseract.Output.DICT,
        )
    except Exception:
        return []
    sx = image.shape[1] / max(1, gray.shape[1])
    sy = image.shape[0] / max(1, gray.shape[0])
    out = []
    for i, raw in enumerate(data.get("text", [])):
        token = str(raw or "").strip()
        if not token:
            continue
        try:
            conf = float(data.get("conf", [0])[i])
        except Exception:
            conf = 0.0
        if conf < 35:
            continue
        x = int((data.get("left", [0])[i] or 0) * sx)
        y = int((data.get("top", [0])[i] or 0) * sy)
        w = int((data.get("width", [0])[i] or 0) * sx)
        h = int((data.get("height", [0])[i] or 0) * sy)
        if w > 0 and h > 0:
            out.append((x, y, w, h, conf, token))
    return out


def _intersection_area(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> int:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    x0, y0 = max(ax, bx), max(ay, by)
    x1, y1 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    return max(0, x1 - x0) * max(0, y1 - y0)


def _text_overlap_ratio(box: tuple[int, int, int, int], text_boxes: list[tuple[int, int, int, int, float, str]]) -> tuple[float, float, int]:
    area = float(max(1, box[2] * box[3]))
    covered = 0.0
    digit_tokens = 0
    for x, y, w, h, conf, token in text_boxes:
        inter = _intersection_area(box, (x, y, w, h))
        if inter <= 0:
            continue
        covered += min(inter, w * h)
        if any(ch.isdigit() for ch in token):
            digit_tokens += 1
    return min(1.0, covered / area), covered, digit_tokens


def _face_shape_score(crop: np.ndarray) -> float:
    if crop is None or crop.size == 0:
        return 0.0
    try:
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop.copy()
        gray = cv2.resize(gray, (96, 120), interpolation=cv2.INTER_AREA)
        gray = cv2.createCLAHE(clipLimit=1.6, tileGridSize=(6, 6)).apply(gray)
        left = gray[:, :48].astype(np.float32)
        right = cv2.flip(gray[:, 48:], 1).astype(np.float32)
        sym = float(np.corrcoef(left.ravel(), right.ravel())[0, 1]) if left.std() > 1 and right.std() > 1 else 0.0


        thirds = [float(cv2.Canny(gray[y0:y1], 40, 120).mean()) for y0, y1 in ((8, 48), (42, 84), (76, 116))]
        structure = min(1.0, (max(thirds) + sorted(thirds)[1]) / 180.0)
        symmetry = min(1.0, max(0.0, (sym + 1.0) / 2.0))
        return 0.55 * symmetry + 0.45 * structure
    except Exception:
        return 0.0


DOCUMENT_FACE_LAYOUTS = {



    "PAN": {
        "preferred": [(0.00, 0.18, 0.34, 0.82)],
        "fallback": [(0.00, 0.12, 0.46, 0.92), (0.46, 0.16, 0.98, 0.88)],
    },
    "AADHAAR": {
        "preferred": [(0.00, 0.12, 0.46, 0.88), (0.54, 0.12, 0.99, 0.88)],
        "fallback": [(0.00, 0.08, 0.98, 0.92)],
    },
    "PASSPORT": {
        "preferred": [(0.00, 0.06, 0.46, 0.82)],
        "fallback": [(0.00, 0.06, 0.60, 0.90), (0.40, 0.06, 0.99, 0.90)],
    },
    "DRIVING_LICENSE": {
        "preferred": [(0.00, 0.08, 0.46, 0.90), (0.54, 0.08, 0.99, 0.90)],
        "fallback": [(0.00, 0.05, 0.99, 0.94)],
    },
    "COLLEGE_ID": {
        "preferred": [(0.00, 0.08, 0.48, 0.92)],
        "fallback": [(0.00, 0.05, 0.50, 0.95), (0.50, 0.05, 0.99, 0.95)],
    },
    "NATIONAL_ID": {
        "preferred": [(0.00, 0.06, 0.48, 0.88), (0.52, 0.06, 0.99, 0.88)],
        "fallback": [(0.00, 0.04, 0.99, 0.94)],
    },
    "VISA": {
        "preferred": [(0.00, 0.06, 0.46, 0.86), (0.54, 0.06, 0.99, 0.86)],
        "fallback": [(0.00, 0.04, 0.99, 0.94)],
    },
}

def _zone_score(cx: float, cy: float, zones) -> float:
    score = 0.0
    for zx0, zy0, zx1, zy1 in zones:
        if zx0 <= cx <= zx1 and zy0 <= cy <= zy1:
            dx = min(cx - zx0, zx1 - cx) / max(0.001, (zx1 - zx0) / 2.0)
            dy = min(cy - zy0, zy1 - cy) / max(0.001, (zy1 - zy0) / 2.0)
            score = max(score, min(1.0, max(0.0, min(dx, dy))))
    return score


def _document_face_candidates(image: np.ndarray, document_type: str | None = None) -> list[tuple[int, int, int, int]]:
    if image is None or image.size == 0:
        return []
    normalized = (document_type or "").strip().upper().replace(" ", "_")
    h, w = image.shape[:2]
    broad = _simple_face_candidates(image, require_eye=False)
    if not broad:

        broad = _detect_faces(image, require_eye=False)
    if not broad:
        return []

    text_boxes = _ocr_text_boxes(image)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    scored = []
    bottom_limit = {
        "PASSPORT": 0.80,
        "AADHAAR": 0.84,
        "PAN": 0.90,
        "DRIVING_LICENSE": 0.88,
        "COLLEGE_ID": 0.92,
        "NATIONAL_ID": 0.92,
        "VISA": 0.92,
    }.get(normalized, 0.90)

    for rank, box in enumerate(broad):
        x, y, fw, fh = box
        ratio = fw / max(1.0, float(fh))
        cy = (y + fh / 2.0) / max(1.0, float(h))
        cx = (x + fw / 2.0) / max(1.0, float(w))
        area_ratio = (fw * fh) / float(w * h)
        if not (0.58 <= ratio <= 1.50):
            continue
        if area_ratio < 0.0012 or area_ratio > 0.28 or cy > bottom_limit:
            continue
        if x <= 0 or y <= 0 or x + fw >= w or y + fh >= h:

            if area_ratio < 0.008:
                continue

        overlap, _, digit_tokens = _text_overlap_ratio(box, text_boxes)


        if overlap >= 0.24 or (digit_tokens >= 2 and overlap >= 0.10):
            continue

        crop = gray[y:y + fh, x:x + fw]
        if crop.size == 0 or crop.shape[0] < 45 or crop.shape[1] < 45:
            continue
        norm_face = _normalize_face(cv2.cvtColor(crop, cv2.COLOR_GRAY2BGR))
        eyes = _eye_center_pair(norm_face)
        eye_score = 1.0 if eyes else 0.0
        shape_score = _face_shape_score(cv2.cvtColor(crop, cv2.COLOR_GRAY2BGR))
        sharpness = float(cv2.Laplacian(crop, cv2.CV_64F).var())
        contrast = float(crop.std())
        brightness = float(crop.mean())
        if sharpness < 2.0 or contrast < 6.0 or not (15.0 <= brightness <= 248.0):
            continue



        detector_hits = 0
        local_roi = image[max(0, y - int(fh * .10)):min(h, y + fh + int(fh * .10)),
                           max(0, x - int(fw * .10)):min(w, x + fw + int(fw * .10))]
        if local_roi.size:
            roi_gray = cv2.cvtColor(local_roi, cv2.COLOR_BGR2GRAY)
            for cascade in _FACE_CASCADES:
                if cascade.empty():
                    continue
                try:
                    found = cascade.detectMultiScale(roi_gray, scaleFactor=1.06, minNeighbors=4, minSize=(max(24, int(fw * .45)), max(24, int(fh * .45))))
                except Exception:
                    found = ()
                if len(found):
                    detector_hits += 1


        side_prior = 0.5
        preferred = DOCUMENT_FACE_LAYOUTS.get(normalized, {}).get("preferred", [])
        preferred_score = _zone_score(cx, cy, preferred)
        if normalized == "PAN":


            side_prior = max(0.0, 1.0 - abs(cx - 0.18) / 0.44)
        elif normalized in {"COLLEGE_ID", "PASSPORT"}:
            side_prior = max(0.0, 1.0 - abs(cx - 0.24) / 0.60)
        elif normalized in {"DRIVING_LICENSE", "AADHAAR", "NATIONAL_ID", "VISA"}:
            side_prior = 0.55 + 0.45 * preferred_score
        else:
            side_prior = 0.55 + 0.45 * preferred_score




        portrait_zones = DOCUMENT_FACE_LAYOUTS.get(normalized, {}).get("preferred", [(0.00, 0.08, 0.98, 0.86)])
        region_prior = _zone_score(cx, cy, portrait_zones)

        size_score = min(1.0, area_ratio / 0.009)
        vertical_score = max(0.0, 1.0 - abs(cy - 0.48) / 0.55)
        text_penalty = max(0.0, 1.0 - overlap * 3.0)
        detector_score = min(1.0, detector_hits / 3.0)




        outside_penalty = 0.0
        if normalized == "PAN" and region_prior < 0.10:
            outside_penalty = 0.18
        score = (
            0.24 * detector_score
            + 0.20 * eye_score
            + 0.18 * shape_score
            + 0.10 * size_score
            + 0.08 * vertical_score
            + 0.07 * side_prior
            + 0.09 * region_prior
            + 0.04 * text_penalty
            - outside_penalty
        )
        scored.append((score, box, detector_hits, eyes is not None, overlap, shape_score, rank))

    scored.sort(key=lambda item: (item[0], item[2], item[5], -item[6]), reverse=True)
    return [item[1] for item in scored]


def _template_face_candidates(image: np.ndarray, document_type: str | None = None) -> list[tuple[int, int, int, int]]:
    normalized = (document_type or "").strip().upper().replace(" ", "_")
    if image is None or image.size == 0:
        return []
    h, w = image.shape[:2]
    layout = DOCUMENT_FACE_LAYOUTS.get(normalized)
    regions = (layout["preferred"] + layout["fallback"]) if layout else [(0.00, 0.08, 0.48, 0.88), (0.52, 0.08, 0.98, 0.88)]

    text_boxes = _ocr_text_boxes(image)
    out = []
    for rx0, ry0, rx1, ry1 in regions:
        x0, x1 = int(w * rx0), int(w * rx1)
        y0, y1 = int(h * ry0), int(h * ry1)
        roi = image[y0:y1, x0:x1]
        if roi.size == 0:
            continue
        scale = 2.0 if max(roi.shape[:2]) < 1500 else 1.0
        working = cv2.resize(roi, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        candidates = _simple_face_candidates(working, require_eye=False)
        for bx, by, bw, bh in candidates[:6]:
            x = int(bx / scale) + x0
            y = int(by / scale) + y0
            fw = int(bw / scale)
            fh = int(bh / scale)
            box = (x, y, fw, fh)
            ratio = fw / max(1.0, float(fh))
            area_ratio = (fw * fh) / float(w * h)
            if not (0.56 <= ratio <= 1.50 and 0.002 <= area_ratio <= 0.16):
                continue
            overlap, _, digit_tokens = _text_overlap_ratio(box, text_boxes)
            if overlap >= 0.20 or (digit_tokens >= 2 and overlap >= 0.09):
                continue
            crop = image[y:y+fh, x:x+fw]
            if crop.size == 0:
                continue
            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
            contrast = float(gray.std())
            shape = _face_shape_score(crop)
            if sharpness < 2.0 or contrast < 6.0 or shape < 0.28:
                continue
            if not any(_iou(box, existing) >= 0.45 for existing in out):
                out.append(box)
    return out


def _best_oriented_face(
    image: np.ndarray,
    document_type: str | None = None,
) -> tuple[np.ndarray | None, tuple[int, int, int, int] | None, int | None]:
    normalized = (document_type or "").strip().upper().replace(" ", "_")



    layout = DOCUMENT_FACE_LAYOUTS.get(normalized)
    zones = layout["preferred"] if layout else [(0.00, 0.05, 1.00, 0.95)]

    best = None





    rotation_order = [0, 2, 1, 3]
    for rotation in rotation_order:
        rotated = np.rot90(image, rotation).copy()
        regions = [("full", rotated), ("document", _document_region(rotated))]
        seen_region_shapes = set()

        for source_name, candidate in regions:
            if candidate is None or candidate.size == 0:
                continue
            shape_key = tuple(candidate.shape[:2])
            if shape_key in seen_region_shapes:
                continue
            seen_region_shapes.add(shape_key)

            h, w = candidate.shape[:2]



            detect_candidate = candidate
            detect_scale = 1.0
            max_detection_side = 1600
            if max(h, w) > max_detection_side:
                detect_scale = max_detection_side / float(max(h, w))
                detect_candidate = cv2.resize(
                    candidate, None, fx=detect_scale, fy=detect_scale,
                    interpolation=cv2.INTER_AREA,
                )



            faces = _document_face_candidates(detect_candidate, normalized)
            if not faces:
                faces = _template_face_candidates(detect_candidate, normalized)
            if not faces:
                continue
            if detect_scale != 1.0:
                inv = 1.0 / detect_scale
                faces = [
                    (
                        int(round(x * inv)), int(round(y * inv)),
                        int(round(fw * inv)), int(round(fh * inv)),
                    )
                    for x, y, fw, fh in faces
                ]

            for box in faces[:8]:
                x, y, fw, fh = box
                if fw < max(35, int(w * 0.035)) or fh < max(35, int(h * 0.055)):
                    continue
                cx = (x + fw / 2.0) / max(1.0, float(w))
                cy = (y + fh / 2.0) / max(1.0, float(h))
                area_ratio = (fw * fh) / float(w * h)



                edge_clearance = min(cx, cy, 1.0 - cx, 1.0 - cy)
                if edge_clearance < 0.015:
                    continue

                zone_score = 0.0
                for zx0, zy0, zx1, zy1 in zones:
                    if zx0 <= cx <= zx1 and zy0 <= cy <= zy1:

                        dx = min(cx - zx0, zx1 - cx) / max(0.001, (zx1 - zx0) / 2)
                        dy = min(cy - zy0, zy1 - cy) / max(0.001, (zy1 - zy0) / 2)
                        zone_score = max(zone_score, min(1.0, max(0.0, min(dx, dy))))



                size_score = min(1.0, max(0.0, area_ratio / 0.010))
                if area_ratio > 0.16:
                    size_score *= 0.45




                px0 = max(0, x - int(fw * 0.55))
                py0 = max(0, y - int(fh * 0.55))
                px1 = min(w, x + fw + int(fw * 0.55))
                py1 = min(h, y + fh + int(fh * 0.55))
                local = candidate[py0:py1, px0:px1]
                texture_score = 0.0
                if local.size:
                    hsv = cv2.cvtColor(local, cv2.COLOR_BGR2HSV)
                    sat_mean = float(hsv[:, :, 1].mean())
                    gray_local = cv2.cvtColor(local, cv2.COLOR_BGR2GRAY)
                    texture = float(gray_local.std())
                    texture_score = min(1.0, 0.45 * sat_mean / 120.0 + 0.55 * texture / 55.0)






                face_crop = candidate[y:y + fh, x:x + fw]
                eye_supported = False
                if face_crop.size:
                    eye_supported = _eye_center_pair(_normalize_face(face_crop)) is not None



                vertical_score = max(0.0, 1.0 - abs(cy - 0.48) / 0.52)
                source_bonus = 0.10 if source_name == "document" else 0.0




                score = (
                    0.30 * zone_score
                    + 0.20 * size_score
                    + 0.18 * vertical_score
                    + 0.18 * texture_score
                    + (0.16 if eye_supported else 0.0)
                    + 0.10 * min(1.0, edge_clearance / 0.12)
                    + source_bonus
                )

                if best is None or score > best[0]:
                    best = (score, candidate, box, rotation)
                preferred_score = _zone_score(cx, cy, zones)









                if normalized != "AADHAAR" and rotation == 0 and score >= 0.62 and preferred_score >= 0.28:
                    return candidate, box, rotation

    if best is None:
        return None, None, None
    return best[1], best[2], best[3]

def _largest_face(image: np.ndarray) -> tuple[np.ndarray | None, dict[str, int] | None]:
    faces = _detect_faces(image)
    if not faces:
        return None, None
    x, y, w, h = max(faces, key=lambda item: item[2] * item[3])

    pad_x = int(w * 0.10)
    pad_top = int(h * 0.12)
    pad_bottom = int(h * 0.18)
    x0, y0 = max(0, x - pad_x), max(0, y - pad_top)
    x1 = min(image.shape[1], x + w + pad_x)
    y1 = min(image.shape[0], y + h + pad_bottom)
    return image[y0:y1, x0:x1].copy(), {"x": x, "y": y, "width": w, "height": h}


def _data_url(image: np.ndarray) -> str:
    ok, encoded = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), 96])
    if not ok:
        raise FaceComparisonError("Unable to encode the detected face.")
    return "data:image/jpeg;base64," + base64.b64encode(encoded.tobytes()).decode("ascii")


def _normalize_face(image: np.ndarray) -> np.ndarray:
    image = cv2.resize(image, (180, 220), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    return gray


def _eye_center_pair(gray: np.ndarray) -> tuple[tuple[float, float], tuple[float, float]] | None:
    eyes = _EYE_CASCADE.detectMultiScale(gray, scaleFactor=1.08, minNeighbors=6, minSize=(16, 16))
    if len(eyes) < 2:
        return None
    centers = sorted(
        [(x + w / 2.0, y + h / 2.0) for x, y, w, h in eyes],
        key=lambda p: p[0],
    )

    upper = [p for p in centers if p[1] < gray.shape[0] * 0.62]
    if len(upper) < 2:
        upper = centers[:]
    best = None
    best_dx = 0
    for i, left in enumerate(upper):
        for right in upper[i + 1:]:
            dx = abs(right[0] - left[0])
            if dx > best_dx:
                best_dx = dx
                best = (left, right)
    return best


def _align_faces(first: np.ndarray, second: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    a = _normalize_face(first)
    b = _normalize_face(second)

    eyes_a = _eye_center_pair(a)
    eyes_b = _eye_center_pair(b)
    if eyes_a and eyes_b:
        (ax1, ay1), (ax2, ay2) = eyes_a
        (bx1, by1), (bx2, by2) = eyes_b
        da = max(1.0, float(np.hypot(ax2 - ax1, ay2 - ay1)))
        db = max(1.0, float(np.hypot(bx2 - bx1, by2 - by1)))
        angle_a = np.degrees(np.arctan2(ay2 - ay1, ax2 - ax1))
        angle_b = np.degrees(np.arctan2(by2 - by1, bx2 - bx1))
        scale = da / db
        center_b = ((bx1 + bx2) / 2.0, (by1 + by2) / 2.0)
        center_a = ((ax1 + ax2) / 2.0, (ay1 + ay2) / 2.0)
        matrix = cv2.getRotationMatrix2D(center_b, angle_b - angle_a, scale)
        matrix[0, 2] += center_a[0] - center_b[0]
        matrix[1, 2] += center_a[1] - center_b[1]
        b = cv2.warpAffine(b, matrix, (a.shape[1], a.shape[0]), borderMode=cv2.BORDER_REFLECT)
        return a, b






    try:
        ref = a.astype(np.float32) / 255.0
        moving = b.astype(np.float32) / 255.0
        warp = np.eye(2, 3, dtype=np.float32)
        criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 80, 1e-5)
        correlation, matrix = cv2.findTransformECC(
            ref, moving, warp, cv2.MOTION_AFFINE, criteria, None, 3
        )
        if np.isfinite(correlation) and float(correlation) >= 0.42:
            candidate = cv2.warpAffine(
                b, matrix, (a.shape[1], a.shape[0]),
                flags=cv2.INTER_LINEAR + cv2.WARP_INVERSE_MAP,
                borderMode=cv2.BORDER_REFLECT,
            )
            return a, candidate
    except (cv2.error, ValueError, FloatingPointError):
        pass
    return a, b


def _corr_score(a: np.ndarray, b: np.ndarray) -> float:
    aa = a.astype(np.float32) / 255.0
    bb = b.astype(np.float32) / 255.0
    aa = (aa - aa.mean()) / (aa.std() + 1e-6)
    bb = (bb - bb.mean()) / (bb.std() + 1e-6)
    corr = float(np.mean(aa * bb))
    return float(np.clip((corr + 1.0) * 50.0, 0.0, 100.0))


def _gradient_score(a: np.ndarray, b: np.ndarray) -> float:
    def grad(g: np.ndarray) -> np.ndarray:
        gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)
        m = cv2.magnitude(gx, gy)
        return m / (m.max() + 1e-6)
    ga, gb = grad(a), grad(b)
    corr = float(np.corrcoef(ga.ravel(), gb.ravel())[0, 1])
    if not np.isfinite(corr):
        return 0.0
    return float(np.clip((corr + 1.0) * 50.0, 0.0, 100.0))


def _histogram_score(a: np.ndarray, b: np.ndarray) -> float:
    ha = cv2.calcHist([a], [0], None, [32], [0, 256])
    hb = cv2.calcHist([b], [0], None, [32], [0, 256])
    ha = cv2.normalize(ha, None).ravel()
    hb = cv2.normalize(hb, None).ravel()
    return float(np.clip(np.minimum(ha, hb).sum() * 100.0, 0.0, 100.0))


def _orb_score(a: np.ndarray, b: np.ndarray) -> tuple[float, int, int, float, int]:
    detector = cv2.ORB_create(
        nfeatures=1800,
        scaleFactor=1.2,
        nlevels=8,
        edgeThreshold=15,
        patchSize=31,
        fastThreshold=5,
    )
    kp1, des1 = detector.detectAndCompute(a, None)
    kp2, des2 = detector.detectAndCompute(b, None)
    if des1 is None or des2 is None or len(kp1) < 8 or len(kp2) < 8:
        return 0.0, 0, 0, 0.0, 0

    pairs = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(des1, des2, k=2)
    good = [m for pair in pairs if len(pair) == 2 for m, n in [pair] if m.distance < 0.78 * n.distance]
    if not good:
        return 0.0, 0, 0, 0.0, 0

    inliers = 0
    coverage = 0.0
    covered_cells = 0
    if len(good) >= 4:
        src = np.float32([kp1[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
        dst = np.float32([kp2[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
        try:
            _, mask = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
            if mask is not None:
                inlier_mask = mask.ravel().astype(bool)
                inliers = int(inlier_mask.sum())
                if inliers:
                    pts = src.reshape(-1, 2)[inlier_mask]
                    width = max(1.0, float(a.shape[1]))
                    height = max(1.0, float(a.shape[0]))
                    nx = float(np.clip((pts[:, 0].max() - pts[:, 0].min()) / width, 0.0, 1.0))
                    ny = float(np.clip((pts[:, 1].max() - pts[:, 1].min()) / height, 0.0, 1.0))
                    spread = min(1.0, 0.55 * (nx / 0.42) + 0.45 * (ny / 0.42))
                    cells = set()
                    for px, py in pts:
                        gx = min(2, max(0, int(px / width * 3.0)))
                        gy = min(2, max(0, int(py / height * 3.0)))
                        cells.add((gx, gy))
                    covered_cells = len(cells)
                    grid_score = min(1.0, covered_cells / 4.0)
                    coverage = float(np.clip(0.65 * spread + 0.35 * grid_score, 0.0, 1.0))
        except cv2.error:
            inliers = 0

    denominator = max(1, min(len(kp1), len(kp2)))
    match_ratio_score = 100.0 * (1.0 - np.exp(-(len(good) / denominator) * 7.0))
    inlier_ratio = inliers / max(1, len(good))
    inlier_score = 100.0 * min(1.0, inlier_ratio / 0.50)
    coverage_score = coverage * 100.0
    score = 0.26 * match_ratio_score + 0.54 * inlier_score + 0.20 * coverage_score
    return float(np.clip(score, 0.0, 100.0)), len(good), inliers, coverage, covered_cells


def _inner_face_region(gray: np.ndarray) -> np.ndarray:
    if gray is None or gray.size == 0:
        return gray
    h, w = gray.shape[:2]
    x0, x1 = int(w * 0.08), int(w * 0.92)
    y0, y1 = int(h * 0.05), int(h * 0.95)
    region = gray[y0:y1, x0:x1]
    if region.size == 0:
        return gray
    mask = np.zeros(region.shape, dtype=np.uint8)
    center = (region.shape[1] // 2, int(region.shape[0] * 0.49))
    axes = (max(8, int(region.shape[1] * 0.43)), max(8, int(region.shape[0] * 0.47)))
    cv2.ellipse(mask, center, axes, 0, 0, 360, 255, -1)


    median = int(np.median(region))
    return np.where(mask > 0, region, median).astype(np.uint8)


def _sift_score(a: np.ndarray, b: np.ndarray) -> tuple[float, int, int, float, int]:
    a_core = _inner_face_region(a)
    b_core = _inner_face_region(b)
    sift = cv2.SIFT_create(nfeatures=1400, contrastThreshold=0.02)
    kp1, des1 = sift.detectAndCompute(a_core, None)
    kp2, des2 = sift.detectAndCompute(b_core, None)
    if des1 is None or des2 is None or len(kp1) < 8 or len(kp2) < 8:
        return 0.0, 0, 0, 0.0, 0
    pairs = cv2.BFMatcher(cv2.NORM_L2).knnMatch(des1, des2, k=2)
    good = [m for pair in pairs if len(pair) == 2 for m, n in [pair] if m.distance < 0.70 * n.distance]
    if not good:
        return 0.0, 0, 0, 0.0, 0

    inliers = 0
    coverage = 0.0
    covered_cells = 0
    if len(good) >= 4:
        src = np.float32([kp1[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
        dst = np.float32([kp2[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
        try:
            _, mask = cv2.findHomography(src, dst, cv2.RANSAC, 4.0)
            if mask is not None:
                inlier_mask = mask.ravel().astype(bool)
                inliers = int(inlier_mask.sum())
                if inliers:
                    pts = src.reshape(-1, 2)[inlier_mask]
                    width = max(1.0, float(a_core.shape[1]))
                    height = max(1.0, float(a_core.shape[0]))
                    nx = float(np.clip((pts[:, 0].max() - pts[:, 0].min()) / width, 0.0, 1.0))
                    ny = float(np.clip((pts[:, 1].max() - pts[:, 1].min()) / height, 0.0, 1.0))
                    spread = min(1.0, 0.55 * (nx / 0.42) + 0.45 * (ny / 0.42))
                    cells = set()
                    for px, py in pts:
                        gx = min(2, max(0, int(px / width * 3.0)))
                        gy = min(2, max(0, int(py / height * 3.0)))
                        cells.add((gx, gy))
                    covered_cells = len(cells)
                    grid_score = min(1.0, covered_cells / 4.0)
                    coverage = float(np.clip(0.65 * spread + 0.35 * grid_score, 0.0, 1.0))
        except cv2.error:
            inliers = 0

    denominator = max(1, min(len(kp1), len(kp2)))
    match_ratio_score = 100.0 * (1.0 - np.exp(-(len(good) / denominator) * 9.0))
    inlier_ratio = inliers / max(1, len(good))
    inlier_score = 100.0 * min(1.0, inlier_ratio / 0.58)
    coverage_score = coverage * 100.0
    score = 0.26 * match_ratio_score + 0.54 * inlier_score + 0.20 * coverage_score
    return float(np.clip(score, 0.0, 100.0)), len(good), inliers, coverage, covered_cells


def validate_liveness_frames(frame_payloads: list[str] | None, *, min_frames: int = 5, motion_threshold: float = 0.8) -> tuple[bool, str, dict[str, Any]]:
    frames = list(frame_payloads or [])
    if len(frames) < min_frames:
        return False, "LIVENESS_NOT_ENOUGH_FRAMES", {"frameCount": len(frames)}

    decoded: list[np.ndarray] = []
    for payload in frames[-10:]:
        value = str(payload or "")
        if not value.startswith("data:image/jpeg;base64,"):
            continue
        try:
            raw = base64.b64decode(value.split(",", 1)[1], validate=True)
            image = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_GRAYSCALE)
        except Exception:
            continue
        if image is None or image.size == 0:
            continue
        image = cv2.resize(image, (96, 72), interpolation=cv2.INTER_AREA)

        image = image[8:64, 10:86]
        decoded.append(image.astype(np.float32))

    if len(decoded) < min_frames:
        return False, "LIVENESS_INVALID_FRAMES", {"frameCount": len(decoded)}

    diffs = []
    for previous, current in zip(decoded, decoded[1:]):
        diffs.append(float(np.mean(np.abs(current - previous)) / 255.0 * 100.0))
    if not diffs:
        return False, "LIVENESS_NOT_ENOUGH_MOTION", {"frameCount": len(decoded), "motionScore": 0.0}

    motion_score = float(np.mean(diffs))
    active_samples = sum(1 for diff in diffs if diff >= motion_threshold)
    peak_motion = float(max(diffs))
    passed = motion_score >= motion_threshold and active_samples >= 2
    details = {
        "frameCount": len(decoded),
        "motionScore": round(motion_score, 2),
        "peakMotion": round(peak_motion, 2),
        "motionSamples": active_samples,
        "threshold": motion_threshold,
    }
    if passed:
        return True, "LIVENESS_PASSED", details
    return False, "LIVENESS_MOTION_REQUIRED", details


def validate_camera_capture_bytes(image_bytes: bytes) -> tuple[bool, str, dict[str, Any]]:
    image = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        return False, "INVALID_CAMERA_IMAGE", {}
    h, w = image.shape[:2]
    if w < 320 or h < 240:
        return False, "CAMERA_IMAGE_TOO_SMALL", {"width": w, "height": h}





    faces = _detect_faces(image, require_eye=True)
    detector_mode = "strict_consensus"
    if not faces:
        faces = _simple_face_candidates(image, require_eye=True)
        detector_mode = "multi_detector_fallback"
    if not faces:
        faces = _simple_face_candidates(image, require_eye=False)
        detector_mode = "geometry_fallback"
    if len(faces) == 0:
        return False, "NO_CLEAR_FACE", {"faceCount": 0, "detectorMode": detector_mode}
    if len(faces) > 1:
        return False, "MULTIPLE_FACES", {"faceCount": len(faces), "detectorMode": detector_mode}

    x, y, fw, fh = faces[0]
    area_ratio = (fw * fh) / float(w * h)
    cx, cy = x + fw / 2.0, y + fh / 2.0
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    face_gray = gray[max(0, y):min(h, y + fh), max(0, x):min(w, x + fw)]
    if face_gray.size == 0:
        return False, "INVALID_FACE_CROP", {}
    sharpness = float(cv2.Laplacian(face_gray, cv2.CV_64F).var())
    brightness = float(face_gray.mean())
    contrast = float(face_gray.std())

    if fw < 60 or fh < 60 or area_ratio < 0.012 or area_ratio > 0.65:
        return False, "FACE_FRAMING_INVALID", {
            "faceWidth": fw, "faceHeight": fh, "faceAreaRatio": round(area_ratio, 4)
        }
    if not (0.15 * w <= cx <= 0.85 * w and 0.10 * h <= cy <= 0.90 * h):
        return False, "FACE_NOT_CENTERED", {"centerX": round(cx, 1), "centerY": round(cy, 1)}



    if sharpness < 2.0:
        return False, "FACE_TOO_BLURRY", {"sharpness": round(sharpness, 1)}
    if brightness < 25.0 or brightness > 235.0 or contrast < 10.0:
        return False, "FACE_QUALITY_INVALID", {
            "brightness": round(brightness, 1), "contrast": round(contrast, 1)
        }

    return True, "FACE_OK", {
        "faceCount": 1,
        "detectorMode": detector_mode,
        "faceBox": {"x": x, "y": y, "width": fw, "height": fh},
        "sharpness": round(sharpness, 1),
        "brightness": round(brightness, 1),
        "contrast": round(contrast, 1),
    }


def compare_document_and_capture(
    document_path: str | Path,
    capture_path: str | Path,
    document_type: str | None = None,
) -> dict[str, Any]:





    document_path_obj = Path(document_path)
    if document_path_obj.suffix.lower() == ".pdf":
        document_detection_image = _load_image(document_path_obj, high_res=False)
        high_res_document = _load_image(document_path_obj, high_res=True)
    else:
        document_detection_image = _load_image(document_path_obj, high_res=True)
        high_res_document = document_detection_image

    capture_image = _load_image(capture_path, high_res=False)





    oriented_detection, detection_box, document_rotation = _best_oriented_face(
        document_detection_image, document_type
    )
    if oriented_detection is not None and detection_box is not None:
        oriented_high_res = np.rot90(high_res_document, int(document_rotation or 0)).copy()
        dh, dw = oriented_detection.shape[:2]
        hh, hw = oriented_high_res.shape[:2]
        sx = hw / max(1.0, float(dw))
        sy = hh / max(1.0, float(dh))
        dx, dy, dww, dhh = detection_box
        high_box = (
            int(round(dx * sx)), int(round(dy * sy)),
            int(round(dww * sx)), int(round(dhh * sy)),
        )
        document_image = oriented_high_res
        document_faces = [high_box]
    else:
        document_image = high_res_document
        document_faces = []




    capture_faces = _detect_faces(capture_image, require_eye=True)
    if not capture_faces:
        capture_faces = _simple_face_candidates(capture_image, require_eye=True)
    if not capture_faces:
        capture_faces = _simple_face_candidates(capture_image, require_eye=False)

    base = {
        "comparisonBasis": "MULTI_SIGNAL_FACE_STRUCTURE_SIMILARITY",
        "documentFace": None,
        "captureFace": None,
        "documentBox": None,
        "captureBox": None,
        "documentRotation": document_rotation,
    }
    if not document_faces:
        return {**base, "status": "DOCUMENT_FACE_NOT_FOUND", "score": None, "matchedFeatures": 0,
                "message": "No clear face was detected in the uploaded document image."}
    if len(document_faces) > 1:
        return {**base, "status": "MULTIPLE_DOCUMENT_FACES", "score": None, "matchedFeatures": 0,
                "message": "More than one face was detected in the uploaded document."}
    if not capture_faces:
        return {**base, "status": "CAPTURE_FACE_NOT_FOUND", "score": None, "matchedFeatures": 0,
                "message": "No clear human face was detected in the camera capture."}
    if len(capture_faces) > 1:


        primary = capture_faces[0]
        px, py, pw, ph = primary
        primary_area = pw * ph
        significant = []
        for candidate in capture_faces[1:]:
            cx, cy, cw, ch = candidate
            if cw * ch < primary_area * 0.45:
                continue
            crop = capture_image[cy:cy + ch, cx:cx + cw]
            if crop.size == 0:
                continue
            gray_candidate = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            sharpness = float(cv2.Laplacian(gray_candidate, cv2.CV_64F).var())
            contrast = float(gray_candidate.std())
            if sharpness >= 2.0 and contrast >= 10.0:
                significant.append(candidate)
        if significant:
            return {**base, "status": "MULTIPLE_CAPTURE_FACES", "score": None, "matchedFeatures": 0,
                    "message": "More than one clear face was detected in the camera capture."}
        capture_faces = [primary]

    def crop_from_box(image: np.ndarray, box: tuple[int, int, int, int]):
        x, y, w, h = box



        pad_x = int(w * 0.12)
        pad_top = int(h * 0.12)
        pad_bottom = int(h * 0.16)
        x0, y0 = max(0, x - pad_x), max(0, y - pad_top)
        x1 = min(image.shape[1], x + w + pad_x)
        y1 = min(image.shape[0], y + h + pad_bottom)
        crop = image[y0:y1, x0:x1].copy()
        return crop, {"x": x, "y": y, "width": w, "height": h}

    document_face, document_box = crop_from_box(document_image, document_faces[0])
    capture_face, capture_box = crop_from_box(capture_image, capture_faces[0])
    base.update({
        "documentFace": _data_url(document_face),
        "captureFace": _data_url(capture_face),
        "documentBox": document_box,
        "captureBox": capture_box,
    })



    ok, reason, quality = validate_camera_capture_bytes(Path(capture_path).read_bytes())
    if not ok:
        return {**base, "status": "CAPTURE_QUALITY_FAILED", "score": None, "matchedFeatures": 0,
                "captureQuality": {"reason": reason, **quality},
                "message": "The camera capture did not pass the strict face-quality gate."}

    a, b = _align_faces(document_face, capture_face)

    def score_pair(x: np.ndarray, y: np.ndarray) -> tuple[float, dict[str, float], int, int]:


        x_core = _inner_face_region(x)
        y_core = _inner_face_region(y)
        corr = _corr_score(x_core, y_core)
        grad = _gradient_score(x_core, y_core)
        hist = _histogram_score(x_core, y_core)
        sift, sift_good, sift_inliers, sift_spatial_coverage, sift_covered_cells = _sift_score(x_core, y_core)
        orb, orb_good, orb_inliers, orb_spatial_coverage, orb_covered_cells = _orb_score(x_core, y_core)




        local = max(sift, orb)
        score = (0.20 * corr) + (0.15 * grad) + (0.03 * hist) + (0.50 * orb) + (0.12 * sift)
        good = max(orb_good, sift_good)
        inliers = max(orb_inliers, sift_inliers)
        spatial_coverage = max(orb_spatial_coverage, sift_spatial_coverage)
        covered_cells = max(orb_covered_cells, sift_covered_cells)
        return float(np.clip(score, 0.0, 100.0)), {
            "structureCorrelation": round(corr, 1),
            "gradientSimilarity": round(grad, 1),
            "toneSimilarity": round(hist, 1),
            "localFeatureSimilarity": round(local, 1),
            "siftSimilarity": round(sift, 1),
            "siftMatches": float(sift_good),
            "siftSpatialInliers": float(sift_inliers),
            "orbSimilarity": round(orb, 1),
            "orbMatches": float(orb_good),
            "orbSpatialInliers": float(orb_inliers),
            "spatialInliers": float(inliers),
            "spatialCoverage": round(spatial_coverage * 100.0, 1),
            "coveredFaceZones": float(covered_cells),
        }, good, inliers


    score_a, signals_a, good_a, inliers_a = score_pair(a, b)
    score_b, signals_b, good_b, inliers_b = score_pair(a, cv2.flip(b, 1))
    if score_b > score_a:
        score, signals, good, inliers = score_b, signals_b, good_b, inliers_b
    else:
        score, signals, good, inliers = score_a, signals_a, good_a, inliers_a





    threshold = 62.0
    sift_gate = (
        signals.get("siftMatches", 0) >= 7
        and signals.get("siftSpatialInliers", 0) >= 5
        and signals.get("siftSimilarity", 0) >= 30.0
    )
    orb_gate = (
        signals.get("orbMatches", 0) >= 10
        and signals.get("orbSpatialInliers", 0) >= 6
        and signals.get("orbSimilarity", 0) >= 45.0
    )
    spatial_gate = (
        signals.get("spatialCoverage", 0) >= 22.0
        and signals.get("coveredFaceZones", 0) >= 2
    )
    strong_local_evidence = spatial_gate and (sift_gate or orb_gate)
    structural_gate = (
        signals.get("structureCorrelation", 0) >= 55.0
        and signals.get("gradientSimilarity", 0) >= 50.0
    )
    status = "SIMILAR" if score >= threshold and strong_local_evidence and structural_gate else ("LOW_SIMILARITY" if score >= 45.0 else "NOT_SIMILAR")
    failed_gates = []
    if score < threshold:
        failed_gates.append(f"similarity score {score:.1f}% is below the {threshold:.0f}% threshold")
    if not strong_local_evidence:
        failed_gates.append("local feature evidence gate was not met")
    if not structural_gate:
        failed_gates.append("face structure gate was not met")
    message = (
        "The detected document and camera faces meet the strict prototype similarity gate."
        if status == "SIMILAR" else
        "The document and camera faces do not meet the strict prototype similarity gate: "
        + "; ".join(failed_gates) + "."
    )
    return {
        **base,
        "status": status,
        "score": round(score, 1),
        "matchedFeatures": int(good),
        "spatialInliers": int(inliers),
        "identityEvidence": {
            "localFeatureGate": bool(strong_local_evidence),
            "siftGate": bool(sift_gate),
            "orbGate": bool(orb_gate),
            "spatialGate": bool(spatial_gate),
            "structuralGate": bool(structural_gate),
            "minimumSiftMatches": 7,
            "minimumSiftSpatialInliers": 5,
            "minimumOrbMatches": 10,
            "minimumOrbSpatialInliers": 6,
            "minimumSpatialCoverage": 22.0,
            "minimumCoveredFaceZones": 2,
        },
        "basisCount": 100,
        "threshold": threshold,
        "captureQuality": quality,
        "signals": signals,
        "message": message,
    }

