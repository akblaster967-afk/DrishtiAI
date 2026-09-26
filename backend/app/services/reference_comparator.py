from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import numpy as np

from app.services.pdf_images import load_pdf_page_image


def _load_image(path: str) -> np.ndarray:
    p = Path(path)
    if p.suffix.lower() == ".pdf":
        image = load_pdf_page_image(p, 0)
        if image is None:
            raise ValueError("Unable to extract reference PDF page image")
        return image
    data = np.fromfile(str(p), dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Unable to decode reference image")
    return image


def _norm_text(value: Any, field: str = "") -> str:
    text = " ".join(str(value or "").upper().split())
    if field in {"document_number", "enrollment_number"}:
        return "".join(ch for ch in text if ch.isalnum())
    if field == "valid_until":
        return "".join(ch for ch in text if ch.isdigit())
    if field == "course":
        if "BTECH" in text.replace(" ", "") and "CSE" in text.replace(" ", ""):
            return "BTECH(CSE)"
    if field == "dob":
        return "".join(ch for ch in text if ch.isdigit())
    return " ".join(text.split())


def _similar(a: str, b: str, field: str) -> bool:
    if not a or not b:
        return False
    if a == b:
        return True
    if field == "institution_name":
        anchors = ("RAMSWAROOP", "MEMORIAL", "COLLEGE", "ENGINEERING")
        return sum(anchor in a and anchor in b for anchor in anchors) >= 3
    return False


def compare_reference_fields(reference_fields: dict, suspect_fields: dict) -> dict:
    keys = sorted(set(reference_fields or {}) | set(suspect_fields or {}))

    comparisons = []
    changed = added = removed = 0
    for key in keys:
        ref = reference_fields.get(key)
        sus = suspect_fields.get(key)
        ref_text = _norm_text(ref, key)
        sus_text = _norm_text(sus, key)
        if not ref_text and sus_text:
            status = "ADDED"
            added += 1
        elif ref_text and not sus_text:
            status = "REMOVED"
            removed += 1
        elif _similar(ref_text, sus_text, key):
            status = "MATCH"
        elif ref_text == sus_text:
            status = "MATCH"
        else:
            status = "CHANGED"
            changed += 1
        comparisons.append({"field": key, "reference": ref, "suspect": sus, "status": status})

    total = len(comparisons)
    diff_count = sum(item["status"] != "MATCH" for item in comparisons)
    field_score = round((diff_count / total) * 100, 1) if total else 0.0
    return {
        "available": bool(comparisons),
        "comparisons": comparisons,
        "changedCount": changed,
        "addedCount": added,
        "removedCount": removed,
        "differenceCount": diff_count,
        "score": field_score,
    }


def _align_images(reference: np.ndarray, suspect: np.ndarray) -> tuple[np.ndarray, dict[str, Any]]:
    target_w = max(900, min(1800, reference.shape[1]))
    target_h = max(520, min(1200, reference.shape[0]))
    ref = cv2.resize(reference, (target_w, target_h), interpolation=cv2.INTER_AREA)
    suspect_ratio = target_w / max(suspect.shape[1], 1)
    suspect_h = max(400, int(suspect.shape[0] * suspect_ratio))
    sus = cv2.resize(suspect, (target_w, suspect_h), interpolation=cv2.INTER_AREA)

    if sus.shape[0] != target_h:
        sus = cv2.resize(sus, (target_w, target_h), interpolation=cv2.INTER_AREA)

    ref_gray = cv2.cvtColor(ref, cv2.COLOR_BGR2GRAY)
    sus_gray = cv2.cvtColor(sus, cv2.COLOR_BGR2GRAY)
    orb = cv2.ORB_create(nfeatures=2500, fastThreshold=7)
    kp1, des1 = orb.detectAndCompute(ref_gray, None)
    kp2, des2 = orb.detectAndCompute(sus_gray, None)
    if des1 is None or des2 is None or len(kp1) < 8 or len(kp2) < 8:
        return sus, {"aligned": False, "matches": 0, "reason": "INSUFFICIENT_FEATURES"}

    matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
    pairs = matcher.knnMatch(des1, des2, k=2)
    good = [m for m, n in pairs if m.distance < 0.72 * n.distance]
    if len(good) < 8:
        return sus, {"aligned": False, "matches": len(good), "reason": "INSUFFICIENT_MATCHES"}

    src = np.float32([kp2[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
    dst = np.float32([kp1[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    matrix, mask = cv2.findHomography(src, dst, cv2.RANSAC, 4.0)
    if matrix is None or mask is None or int(mask.sum()) < 6:
        return sus, {"aligned": False, "matches": len(good), "reason": "HOMOGRAPHY_FAILED"}
    warped = cv2.warpPerspective(sus, matrix, (target_w, target_h), borderMode=cv2.BORDER_REPLICATE)
    return warped, {"aligned": True, "matches": len(good), "inliers": int(mask.sum())}


def compare_reference_images(reference_path: str, suspect_path: str) -> dict[str, Any]:
    ref = _load_image(reference_path)
    suspect = _load_image(suspect_path)
    aligned_suspect, alignment = _align_images(ref, suspect)
    target = cv2.resize(ref, (aligned_suspect.shape[1], aligned_suspect.shape[0]), interpolation=cv2.INTER_AREA)

    ref_gray = cv2.cvtColor(target, cv2.COLOR_BGR2GRAY)
    sus_gray = cv2.cvtColor(aligned_suspect, cv2.COLOR_BGR2GRAY)

    ref_norm = cv2.normalize(ref_gray, None, 0, 255, cv2.NORM_MINMAX)
    sus_norm = cv2.normalize(sus_gray, None, 0, 255, cv2.NORM_MINMAX)
    diff = cv2.absdiff(ref_norm, sus_norm)
    diff = cv2.GaussianBlur(diff, (5, 5), 0)



    mask_valid = np.zeros_like(diff, dtype=np.uint8)
    pad_x = int(diff.shape[1] * 0.02)
    pad_y = int(diff.shape[0] * 0.02)
    mask_valid[pad_y:diff.shape[0]-pad_y, pad_x:diff.shape[1]-pad_x] = 1

    threshold = max(18.0, float(np.percentile(diff[mask_valid > 0], 90)))
    change_mask = ((diff >= threshold) & (mask_valid > 0)).astype(np.uint8) * 255
    kernel = np.ones((5, 5), np.uint8)
    change_mask = cv2.morphologyEx(change_mask, cv2.MORPH_OPEN, kernel)
    change_mask = cv2.morphologyEx(change_mask, cv2.MORPH_CLOSE, kernel)

    changed_fraction = float((change_mask > 0).mean())
    contours, _ = cv2.findContours(change_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    regions = []
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:20]:
        area = cv2.contourArea(contour)
        if area < 180:
            continue
        x, y, w, h = cv2.boundingRect(contour)
        regions.append({"x": int(x), "y": int(y), "width": int(w), "height": int(h), "area": int(area)})

    score = min(100.0, changed_fraction * 280.0 + len(regions) * 1.8)
    band = "HIGH" if score >= 55 else ("MEDIUM" if score >= 18 else "LOW")
    return {
        "available": True,
        "changedPixelFraction": round(changed_fraction * 100, 2),
        "differenceScore": round(score, 1),
        "band": band,
        "regions": regions,
        "regionCount": len(regions),
        "alignment": alignment,
        "dimensions": {"reference": [int(ref.shape[1]), int(ref.shape[0])], "suspect": [int(suspect.shape[1]), int(suspect.shape[0])]},
        "notice": "Visual comparison is a screening signal. Alignment reduces false differences from crop/scale/perspective changes; lighting and scan variation can still affect it.",
    }


def build_reference_comparison(reference_path: str, suspect_path: str, reference_fields: dict, suspect_fields: dict) -> dict:
    fields = compare_reference_fields(reference_fields, suspect_fields)
    try:
        visual = compare_reference_images(reference_path, suspect_path)
    except Exception as exc:
        visual = {"available": False, "differenceScore": None, "band": "UNAVAILABLE", "regionCount": 0, "regions": [], "error": type(exc).__name__}

    evidence = []
    if fields["changedCount"]:
        evidence.append({"type": "FIELD_CHANGED", "severity": "HIGH", "message": f"{fields['changedCount']} extracted field(s) differ from the reference copy."})
    if fields["addedCount"]:
        evidence.append({"type": "FIELD_ADDED", "severity": "HIGH", "message": f"{fields['addedCount']} field(s) appear in the suspect copy but not in the reference copy."})
    if fields["removedCount"]:
        evidence.append({"type": "FIELD_REMOVED", "severity": "MEDIUM", "message": f"{fields['removedCount']} field(s) present in the reference copy were not found in the suspect copy."})
    if visual.get("band") in {"MEDIUM", "HIGH"}:
        evidence.append({"type": "VISUAL_DIFFERENCE", "severity": visual["band"], "message": f"Visual comparison found {visual.get('regionCount', 0)} notable changed region(s) after alignment."})

    score = min(100, round(max(fields.get("score", 0) * 0.68, visual.get("differenceScore") or 0)))
    band = "HIGH" if score >= 55 else ("MEDIUM" if score >= 18 else "LOW")
    return {
        "available": True,
        "score": score,
        "band": band,
        "referenceMode": "REFERENCE_DOCUMENT",
        "fieldComparison": fields,
        "visualComparison": visual,
        "evidence": evidence,
        "changed": bool(evidence),
        "message": "Reference comparison found observable differences." if evidence else "No strong differences were detected by the current comparison heuristics.",
    }
