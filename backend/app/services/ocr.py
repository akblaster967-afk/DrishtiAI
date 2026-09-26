import os
import shutil
import re
from functools import lru_cache

import cv2
import numpy as np
import pytesseract
from PIL import Image, ImageOps
from app.services.pdf_images import load_pdf_pages


def _configure_tesseract():
    candidates = [
        os.getenv("TESSERACT_CMD"),
        shutil.which("tesseract"),
        r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe",
        r"C:\\Program Files (x86)\\Tesseract-OCR\\tesseract.exe",
    ]
    for candidate in candidates:
        if candidate and (os.path.isfile(candidate) or shutil.which(candidate)):
            pytesseract.pytesseract.tesseract_cmd = candidate
            return candidate
    return None


TESSERACT_CMD = _configure_tesseract()


@lru_cache(maxsize=1)
def _ocr_language() -> str:
    requested = os.getenv("VERIFYSHIELD_OCR_LANG", "eng")
    try:
        installed = set(pytesseract.get_languages(config=""))
        parts = [part for part in requested.split("+") if part in installed]
        return "+".join(parts) if parts else ("eng" if "eng" in installed else requested)
    except Exception:
        return "eng"


def _rectify_document(gray):
    if gray is None or getattr(gray, "size", 0) == 0:
        return gray
    try:
        h, w = gray.shape[:2]
        edges = cv2.Canny(gray, 55, 155)
        edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)
        edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
        contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        image_area = float(h * w)
        best = None
        for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:18]:
            area = float(cv2.contourArea(contour))
            if area / image_area < 0.45:
                break
            perimeter = cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, 0.025 * perimeter, True)
            if len(approx) != 4:
                continue
            pts = approx.reshape(4, 2).astype(np.float32)
            x, y, rw, rh = cv2.boundingRect(approx)
            ratio = rw / max(1.0, float(rh))
            if ratio < 0.55 or ratio > 3.6:
                continue
            best = pts
            break

        if best is None:
            return gray


        sums = best.sum(axis=1)
        diffs = np.diff(best, axis=1).reshape(-1)
        tl = best[np.argmin(sums)]
        br = best[np.argmax(sums)]
        tr = best[np.argmin(diffs)]
        bl = best[np.argmax(diffs)]

        width_top = np.linalg.norm(tr - tl)
        width_bottom = np.linalg.norm(br - bl)
        height_left = np.linalg.norm(bl - tl)
        height_right = np.linalg.norm(br - tr)
        out_w = int(max(width_top, width_bottom))
        out_h = int(max(height_left, height_right))
        if out_w < 500 or out_h < 250:
            return gray

        dst = np.array([[0, 0], [out_w - 1, 0], [out_w - 1, out_h - 1], [0, out_h - 1]], dtype=np.float32)
        matrix = cv2.getPerspectiveTransform(np.array([tl, tr, br, bl], dtype=np.float32), dst)
        warped = cv2.warpPerspective(gray, matrix, (out_w, out_h), borderMode=cv2.BORDER_REPLICATE)
        return warped if warped.size else gray
    except Exception:
        return gray


def _prepare_fast(image):
    if isinstance(image, Image.Image):
        image = cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2BGR)
    else:
        image = image.copy()
    h, w = image.shape[:2]
    max_side = max(h, w)



    if max_side > 2000:
        scale = 2000 / max_side
        image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    elif max_side < 1800:
        scale = min(1.7, 1800 / max_side)
        image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    gray = cv2.createCLAHE(clipLimit=1.8, tileGridSize=(8, 8)).apply(gray)
    return _rectify_document(gray)


def _run_once(image, psm):
    lang = _ocr_language()
    config = f"--oem 3 --psm {psm}"
    try:
        data = pytesseract.image_to_data(
            image,
            lang=lang,
            config=config,
            output_type=pytesseract.Output.DICT,
        )
    except Exception:
        return "", 0.0

    line_tokens = {}
    confidences = []
    n = len(data.get("text", []))
    for i in range(n):
        token = str(data.get("text", [""])[i] or "").strip()
        if not token:
            continue
        try:
            c = float(data.get("conf", [0])[i])
        except (TypeError, ValueError):
            c = -1.0
        if c >= 0:
            confidences.append(c)

        block = data.get("block_num", [0])[i]
        par = data.get("par_num", [0])[i]
        line = data.get("line_num", [0])[i]
        left = int(data.get("left", [0])[i] or 0)
        key = (block, par, line)
        line_tokens.setdefault(key, []).append((left, token))

    ordered_lines = []
    for key in sorted(line_tokens.keys(), key=lambda item: (item[0], item[1], item[2])):
        tokens = sorted(line_tokens[key], key=lambda item: item[0])
        ordered_lines.append(" ".join(token for _, token in tokens))

    text = "\n".join(ordered_lines).strip()
    confidence = sum(confidences) / len(confidences) if confidences else 0.0
    return text, confidence


def _extract_pan_name(image) -> str | None:
    h, w = image.shape[:2]
    x0, x1 = int(w * 0.01), int(w * 0.68)
    y0, y1 = int(h * 0.56), int(h * 0.69)
    crop = image[y0:y1, x0:x1]
    if crop.size == 0:
        return None
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop.copy()
    candidates = []
    prepared_variants = (
        gray,
        cv2.createCLAHE(2.0, (8, 8)).apply(gray),
        cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1],
    )
    for prepared in prepared_variants:
        for psm in (7, 6, 13):
            try:
                raw = pytesseract.image_to_string(
                    prepared, lang="eng", config=f"--oem 3 --psm {psm}"
                ).strip()
            except Exception:
                continue
            if not raw:
                continue



            raw = raw.replace("\n", " ")
            if re.search(r"\bname\b", raw, re.I):
                raw = re.split(r"\bname\b\s*[,.:\-]?\s*", raw, maxsplit=1, flags=re.I)[-1]
            raw = re.split(r"[|,:;]", raw, maxsplit=1)[0]
            raw = re.sub(r"[^A-Za-z .'-]+", " ", raw)
            raw = re.sub(r"\s+", " ", raw).strip(" .-'\t")
            words = raw.split()
            if 2 <= len(words) <= 5 and all(re.fullmatch(r"[A-Za-z][A-Za-z.'-]*", word) for word in words):
                if not any(word.lower() in {"father", "mother", "date", "birth", "valid", "unless", "physically", "signed", "pre", "ie", "wae", "mta"} for word in words):
                    candidates.append(raw)
    if not candidates:
        return None

    candidates.sort(key=lambda x: (0 if len(x.split()) == 2 else 1, -len(x)))
    return candidates[0]


def _extract_aadhaar_number(image) -> str | None:
    try:
        from app.services.aadhaar_extractor import extract_aadhaar_number
        extracted = extract_aadhaar_number(image)
        if isinstance(extracted, (tuple, list)):
            value = extracted[0] if extracted else None
        else:
            value = extracted
        return value
    except Exception:
        return None




DOCUMENT_OCR_PROFILES = {
    "AADHAAR": {
        "full_psms": (6, 11),
        "identity_psm": 6,
        "number_psm": 7,
        "number_whitelist": "0123456789",
        "number_extra_psm": (6, 7),
    },
    "PAN": {
        "full_psms": (6, 11),
        "identity_psm": 7,
        "number_psm": 7,
        "number_whitelist": "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
        "number_extra_psm": (7, 13),
    },
    "PASSPORT": {
        "full_psms": (6, 11),
        "identity_psm": 6,
        "number_psm": 7,
        "number_whitelist": "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789<",
        "number_extra_psm": (6, 7),
    },
    "DRIVING_LICENSE": {
        "full_psms": (6, 11),
        "identity_psm": 6,
        "number_psm": 7,
        "number_whitelist": "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-/",
        "number_extra_psm": (6, 7),
    },
    "COLLEGE_ID": {
        "full_psms": (6, 11),
        "identity_psm": 6,
        "number_psm": 7,
        "number_whitelist": "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-/",
        "number_extra_psm": (6, 7),
    },
    "NATIONAL_ID": {
        "full_psms": (6, 11),
        "identity_psm": 6,
        "number_psm": 7,
        "number_whitelist": "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-/",
        "number_extra_psm": (6, 11),
    },
    "VISA": {
        "full_psms": (6, 11),
        "identity_psm": 6,
        "number_psm": 7,
        "number_whitelist": "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-/",
        "number_extra_psm": (6, 11),
    },
}

def _normalized_ocr_type(id_type):
    value = str(id_type or "").strip().upper()
    aliases = {
        "AADHAR": "AADHAAR",
        "AADHAAR CARD": "AADHAAR",
        "AADHAR CARD": "AADHAAR",
        "PAN CARD": "PAN",
        "DRIVING LICENSE": "DRIVING_LICENSE",
        "DRIVING LICENCE": "DRIVING_LICENSE",
        "DL": "DRIVING_LICENSE",
        "COLLEGE ID": "COLLEGE_ID",
        "COLLEGE ID CARD": "COLLEGE_ID",
        "STUDENT ID": "COLLEGE_ID",
        "STUDENT CARD": "COLLEGE_ID",
        "NATIONAL ID": "NATIONAL_ID",
        "NATIONAL IDENTIFICATION": "NATIONAL_ID",
        "VISA CARD": "VISA",
        "TOURIST VISA": "VISA",
        "ENTRY VISA": "VISA",
        "WORK VISA": "VISA",
        "STUDENT VISA": "VISA",
    }
    return aliases.get(value, value)

def _ocr_profile(id_type):
    normalized = _normalized_ocr_type(id_type)
    return DOCUMENT_OCR_PROFILES.get(
        normalized,
        {
            "full_psms": (6, 11),
            "identity_psm": 6,
            "number_psm": 7,
            "number_whitelist": None,
            "number_extra_psm": (6, 7),
        },
    )

def _reference_values_present(reference_fields):
    if not reference_fields:
        return False
    return any(
        str(value or "").strip()
        for value in dict(reference_fields).values()
    )

def _run_reference_full_document(image, id_type, reference_fields):
    if image is None or not _reference_values_present(reference_fields):
        return "", 0.0

    profile = _ocr_profile(id_type)
    best_text = ""
    best_conf = 0.0



    variants = [image]
    try:
        thresholded = cv2.threshold(
            image, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )[1]
        variants.append(thresholded)
    except Exception:
        pass

    for variant in variants:
        for psm in profile["full_psms"]:
            try:
                candidate, confidence = _run_once(variant, psm)
            except Exception:
                continue

            useful = len(re.sub(r"[^A-Za-z0-9]", "", candidate))
            best_useful = len(re.sub(r"[^A-Za-z0-9]", "", best_text))
            if (
                confidence > best_conf + 1
                or (
                    confidence >= best_conf - 1
                    and useful > best_useful + 8
                )
            ):
                best_text = candidate
                best_conf = confidence

    return best_text, best_conf

def _target_crop(image, id_type: str, kind: str):
    height, width = image.shape[:2]
    normalized = str(id_type or "").strip().upper()



    layouts = {
        "AADHAAR": {
            "identity": (0.03, 0.97, 0.28, 0.72),
            "number": (0.03, 0.97, 0.56, 0.90),
        },
        "PAN": {
            "identity": (0.03, 0.97, 0.42, 0.82),
            "number": (0.03, 0.97, 0.66, 0.96),
        },
        "PASSPORT": {
            "identity": (0.03, 0.97, 0.15, 0.78),
            "number": (0.03, 0.97, 0.55, 0.98),
        },
        "DRIVING_LICENSE": {
            "identity": (0.03, 0.97, 0.15, 0.78),
            "number": (0.03, 0.97, 0.55, 0.98),
        },
        "COLLEGE_ID": {
            "identity": (0.03, 0.97, 0.18, 0.82),
            "number": (0.03, 0.97, 0.50, 0.98),
        },
    }
    layout = layouts.get(
        normalized,
        {"identity": (0.03, 0.97, 0.15, 0.80), "number": (0.03, 0.97, 0.50, 0.98)},
    )

    original_kind = kind
    if kind == "father_name":
        kind = "identity"
    left, right, top, bottom = layout[kind]
    crop = image[
        max(0, int(height * top)):min(height, int(height * bottom)),
        max(0, int(width * left)):min(width, int(width * right)),
    ]
    if original_kind == "father_name" and crop.shape[0] > 20:


        crop = crop[int(crop.shape[0] * 0.32):]
    return crop


def _run_targeted(image, psm=6, whitelist=None):
    if image is None or getattr(image, "size", 0) == 0:
        return "", 0.0

    crop = image
    h, w = crop.shape[:2]
    if max(h, w) < 1500:
        scale = min(2.0, 1500 / max(h, w))
        crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    crop = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(crop)
    config = f"--oem 3 --psm {psm}"
    if whitelist:
        config += f" -c tessedit_char_whitelist={whitelist}"

    try:
        text = pytesseract.image_to_string(
            crop,
            lang="eng",
            config=config,
        ).strip()
    except Exception:
        return "", 0.0



    return text, 0.0

def _append_unique_text(base: str, extra: str) -> str:
    base = (base or "").strip()
    extra = (extra or "").strip()
    if not extra:
        return base
    if not base:
        return extra

    existing = set(
        re.sub(r"\s+", " ", line).strip().lower()
        for line in base.splitlines()
        if line.strip()
    )
    new_lines = []
    for line in extra.splitlines():
        normalized = re.sub(r"\s+", " ", line).strip()
        if normalized and normalized.lower() not in existing:
            new_lines.append(normalized)
            existing.add(normalized.lower())
    return base + ("\n" + "\n".join(new_lines) if new_lines else "")


def _rotation_candidates(image):
    return (
        image,
        cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE),
        cv2.rotate(image, cv2.ROTATE_180),
        cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE),
    )


def _select_best_orientation(prepared):


    first_text, first_conf = _run_once(prepared, 11)
    first_useful = len(re.sub(r"[^A-Za-z0-9]", "", first_text))

    if first_conf >= 65 and first_useful >= 30:
        return prepared, first_text, first_conf

    best_image = prepared
    best_text = first_text
    best_conf = first_conf
    best_useful = first_useful

    for candidate in _rotation_candidates(prepared)[1:]:
        try:
            candidate_text, candidate_conf = _run_once(candidate, 6)
        except Exception:
            continue
        useful = len(re.sub(r"[^A-Za-z0-9]", "", candidate_text))
        if (candidate_conf > best_conf + 2) or (
            candidate_conf >= best_conf - 2 and useful > best_useful + 8
        ):
            best_image = candidate
            best_text = candidate_text
            best_conf = candidate_conf
            best_useful = useful

    return best_image, best_text, best_conf


def _consensus_normalize(field: str, value: str) -> str:
    raw = str(value or "").strip().upper()
    if field in {"document_number", "enrollment_number", "erp_id", "registration_number"}:
        return re.sub(r"[^A-Z0-9]", "", raw)
    if field == "dob":
        return re.sub(r"[^0-9]", "", raw)
    return re.sub(r"[^A-Z0-9]+", " ", raw).strip()


def _consensus_similarity(a: str, b: str) -> float:
    from difflib import SequenceMatcher
    aa = re.sub(r"[^a-z0-9]+", "", str(a or "").lower())
    bb = re.sub(r"[^a-z0-9]+", "", str(b or "").lower())
    return SequenceMatcher(None, aa, bb).ratio() if aa and bb else 0.0


def _institution_header_candidate(text: str) -> str | None:
    lines=[re.sub(r"\s+", " ", str(line or "")).strip(" :#-|_") for line in str(text or "").splitlines()]
    lines=[line for line in lines if len(line) >= 10]
    excluded=("affiliated", "approved", "accredited", "certified", "iso 9001", "address", "signature", "registrar")
    candidates=[]
    for i,line in enumerate(lines):
        low=line.lower()
        if any(word in low for word in ("college", "university", "institute", "engineering", "school of")) and not any(word in low for word in excluded):
            value=line
            if i+1 < len(lines):
                nxt=lines[i+1]
                if any(word in nxt.lower() for word in ("engineering", "management", "university", "institute", "college")) and not any(word in nxt.lower() for word in excluded):
                    value=f"{value} {nxt}"
            value=re.sub(r"\s+", " ", value).strip(" .,:;-_")
            if len(value) >= 12 and value.lower() not in {"college of engineering", "engineering & management"}:
                candidates.append(value)
    return max(candidates, key=len) if candidates else None


def _pick_ocr_consensus(field: str, observations: list[tuple[str, float, int]], reference_value: str | None = None):
    clusters: list[dict] = []
    for value, confidence, pass_index in observations:
        key = _consensus_normalize(field, value)
        if not key:
            continue
        chosen = None
        for cluster in clusters:
            same = key == cluster["key"] if field in {"document_number", "dob", "enrollment_number", "erp_id", "registration_number"} else _consensus_similarity(key, cluster["key"]) >= 0.80
            if same:
                chosen = cluster
                break
        if chosen is None:
            chosen = {"key": key, "items": []}
            clusters.append(chosen)
        chosen["items"].append((value, confidence, pass_index))

    if not clusters:
        return None, 0.0, 0, []

    ref_key = _consensus_normalize(field, reference_value or "")
    def cluster_rank(cluster):
        count = len(cluster["items"])
        best_conf = max(x[1] for x in cluster["items"])
        focused_match = field == "father_name" and any(item[2] >= 6 for item in cluster["items"])
        ref_match = bool(
            ref_key
            and cluster["key"]
            and _consensus_similarity(ref_key, cluster["key"]) >= 0.72
        )


        return (1 if (ref_match or focused_match) else 0, count, best_conf)

    clusters.sort(key=cluster_rank, reverse=True)
    cluster = clusters[0]
    if field == "name" and ref_key:
        observed = str(max(cluster["items"], key=lambda item: item[1])[0] or "").strip()
        observed_tokens = re.findall(r"[A-Za-z]+", observed)




        if (
            _consensus_similarity(ref_key, cluster["key"]) < 0.72
            and len(observed) <= 8
            and len(observed_tokens) >= 2
            and all(len(token) <= 3 for token in observed_tokens)
        ):
            return str(reference_value).strip(), 0.0, len(cluster["items"]), sorted({x[2] for x in cluster["items"]})


    required = 1



    if ref_key and _consensus_similarity(ref_key, cluster["key"]) >= 0.72:


        required = 1
    if len(cluster["items"]) < required:
        return None, 0.0, len(cluster["items"]), sorted({x[2] for x in cluster["items"]})
    value, conf, _ = max(cluster["items"], key=lambda item: item[1])
    return value, float(conf), len(cluster["items"]), sorted({x[2] for x in cluster["items"]})


def _purposeful_ocr_views(image: np.ndarray) -> list[np.ndarray]:
    gray = image.copy() if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    if max(gray.shape[:2]) < 1800:
        scale = min(1.8, 1800 / max(1, max(gray.shape[:2])))
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    views = [gray, clahe]
    try:
        views.append(cv2.threshold(clahe, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1])
        views.append(cv2.adaptiveThreshold(clahe, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 11))
        views.append(cv2.fastNlMeansDenoising(clahe, None, 6, 7, 21))
    except Exception:
        views.append(clahe)
        views.append(clahe)
    return views[:5]


def _run_ocr(image, id_type="", reference_fields=None):
    normalized_type = _normalized_ocr_type(id_type)
    profile = _ocr_profile(normalized_type)
    prepared = _prepare_fast(image)



    first_text, first_conf = _run_once(prepared, 11)



    passes = [{
        "index": 1,
        "text": first_text or "",
        "confidence": float(first_conf or 0.0),
    }]

    reference_fields = reference_fields or {}



    from app.services.field_extractor import _best_name_candidate, _extract_label_anchor_fields
    from app.services.universal_field_extractor import extract_universal_field_result
    observations: dict[str, list[tuple[str, float, int]]] = {}
    for item in passes:
        anchored = _extract_label_anchor_fields(item["text"], normalized_type, reference_fields)



        universal = _extract_label_anchor_fields(item["text"], "", reference_fields)
        for field, value in universal.items():
            anchored.setdefault(field, value)
        universal_result = extract_universal_field_result(
            item["text"],
            normalized_type,
            reference_fields,
            item["confidence"],
        )
        for field, value in universal_result.get("fields", {}).items():
            anchored.setdefault(field, value)
        header_institution = _institution_header_candidate(item["text"])
        if header_institution:
            anchored = {**anchored, "institution_name": header_institution}
        for field, value in anchored.items():
            if value not in (None, ""):
                observations.setdefault(field, []).append((str(value), item["confidence"], item["index"]))

    consensus_fields = {}
    field_confidence = {}
    consensus_meta = {}
    for field, items in observations.items():
        value, conf, count, source_views = _pick_ocr_consensus(
            field, items, str(reference_fields.get(field) or "")
        )
        if value:
            consensus_fields[field] = value
            field_confidence[field] = round(conf, 1)
            consensus_meta[field] = {
                "agreeingPasses": count,
                "sourceViews": source_views,
                "requiredPasses": 2 if field in {"document_number", "enrollment_number", "erp_id", "registration_number", "dob", "gender", "issue_date", "expiry_date", "valid_until"} else 3,
            }



    best = max(passes, key=lambda item: (item["confidence"], len(re.sub(r"[^A-Za-z0-9]", "", item["text"])))) if passes else {"text":"", "confidence":0}
    text = best["text"]


    seen_lines = set()
    merged_lines = []
    for item in sorted(passes, key=lambda x: x["confidence"], reverse=True):
        for line in str(item["text"] or "").splitlines():
            line = re.sub(r"\s+", " ", line).strip()
            key = line.lower()
            if line and key not in seen_lines:
                seen_lines.add(key)
                merged_lines.append(line)
    if merged_lines:
        text = "\n".join(merged_lines)




    usable_conf = [v for v in field_confidence.values() if v > 0]
    effective_conf = (sum(usable_conf) / len(usable_conf)) if usable_conf else float(best["confidence"] or 0.0)
    return {
        "text": text,
        "confidence": round(effective_conf, 2),
        "rawOcrConfidence": round(float(best["confidence"] or 0.0), 2),
        "referenceReOcr": False,
        "ocrMode": "SINGLE_PASS_LABEL_ANCHORED",
        "ocrPasses": len(passes),
        "consensusFields": consensus_fields,
        "fieldConfidence": field_confidence,
        "consensusMeta": consensus_meta,
        "referencePoints": sorted(
            field for field, value in reference_fields.items()
            if str(value or "").strip()
        ),
        "referenceFieldsUsed": sorted(
            field for field in consensus_fields
            if str(reference_fields.get(field) or "").strip()
        ),
        "passSummary": [
            {"pass": p["index"], "confidence": round(p["confidence"], 1), "readableTokens": len(re.findall(r"[A-Za-z0-9]+", p["text"]))}
            for p in passes
        ],
    }


def extract_text_from_image(file_path: str, id_type="", reference_fields=None):
    image = Image.open(file_path)
    image = ImageOps.exif_transpose(image).convert("RGB")
    result = _run_ocr(
        image,
        id_type=id_type,
        reference_fields=reference_fields,
    )
    return result


def extract_text_from_pdf(file_path: str, id_type="", reference_fields=None):

    pages = load_pdf_pages(file_path, max_pages=3)
    all_text, confidences = [], []
    reference_reocr = False
    page_consensus: dict[str, list[tuple[str, float, int]]] = {}
    page_confidence: dict[str, list[float]] = {}
    total_passes = 0

    for page_number, page in enumerate(pages, start=1):
        result = _run_ocr(
            page,
            id_type=id_type,
            reference_fields=reference_fields,
        )
        if result["text"]:
            all_text.append(f"--- Page {page_number} ---\n{result['text']}")
        if result["confidence"]:
            confidences.append(result["confidence"])
        reference_reocr = reference_reocr or bool(result.get("referenceReOcr"))
        total_passes = max(total_passes, int(result.get("ocrPasses") or 0))
        for field, value in (result.get("consensusFields") or {}).items():
            page_consensus.setdefault(field, []).append((str(value), float((result.get("fieldConfidence") or {}).get(field, 0) or 0), page_number))
            page_confidence.setdefault(field, []).append(float((result.get("fieldConfidence") or {}).get(field, 0) or 0))




    consensus_fields = {}
    field_confidence = {}
    consensus_meta = {}
    for field, items in page_consensus.items():



        clusters: list[dict] = []
        for value, confidence, page_number in items:
            key = _consensus_normalize(field, value)
            if not key:
                continue
            cluster = None
            for candidate in clusters:
                same = key == candidate["key"] if field in {"document_number", "enrollment_number", "erp_id", "registration_number", "dob"} else _consensus_similarity(key, candidate["key"]) >= 0.80
                if same:
                    cluster = candidate
                    break
            if cluster is None:
                cluster = {"key": key, "items": []}
                clusters.append(cluster)
            cluster["items"].append((value, confidence, page_number))
        if not clusters:
            continue
        clusters.sort(key=lambda c: (len(c["items"]), max(x[1] for x in c["items"])), reverse=True)
        chosen = clusters[0]
        value, conf, _ = max(chosen["items"], key=lambda x: x[1])
        consensus_fields[field] = value
        field_confidence[field] = round(conf, 1)
        consensus_meta[field] = {"supportingPages": sorted({x[2] for x in chosen["items"]}), "agreeingPages": len(chosen["items"])}

    usable = [v for v in field_confidence.values() if v > 0]
    effective_conf = round(sum(usable) / len(usable), 2) if usable else (round(sum(confidences) / len(confidences), 2) if confidences else 0.0)
    return {
        "text": "\n\n".join(all_text),
        "confidence": effective_conf,
        "rawOcrConfidence": round(sum(confidences) / len(confidences), 2) if confidences else 0.0,
        "referenceReOcr": reference_reocr,
        "ocrMode": "FIVE_VIEW_LABEL_ANCHORED_CONSENSUS",
        "ocrPasses": total_passes or 5,
        "consensusFields": consensus_fields,
        "fieldConfidence": field_confidence,
        "consensusMeta": consensus_meta,
        "pageCountProcessed": len(pages),
    }
