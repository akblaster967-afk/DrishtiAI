from __future__ import annotations

from pathlib import Path
import re
from typing import Any

import cv2
import numpy as np
from PIL import Image
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


def _status(ok: bool, label: str, found: str, missing: str) -> dict[str, Any]:
    return {
        "label": label,
        "status": "PASS" if ok else "REVIEW",
        "found": found,
        "message": found if ok else missing,
    }


def _roi(image: np.ndarray, x1: float, y1: float, x2: float, y2: float) -> np.ndarray:
    h, w = image.shape[:2]
    xa, ya = max(0, int(w * x1)), max(0, int(h * y1))
    xb, yb = min(w, int(w * x2)), min(h, int(h * y2))
    return image[ya:yb, xa:xb]


def _edge_density(region: np.ndarray) -> float:
    if region.size == 0:
        return 0.0
    gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 60, 150)
    return float(np.mean(edges > 0))


def _ink_density(region: np.ndarray) -> float:
    if region.size == 0:
        return 0.0
    gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
    thr = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        31,
        9,
    )
    return float(np.mean(thr > 0))


def _face_count(region: np.ndarray) -> int:
    if region.size == 0:
        return 0
    gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)
    cascade = cv2.CascadeClassifier(
        str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml")
    )
    if cascade.empty():
        return 0
    faces = cascade.detectMultiScale(gray, scaleFactor=1.08, minNeighbors=5, minSize=(28, 28))
    return int(len(faces))


def _circle_count(region: np.ndarray) -> int:
    if region.size == 0:
        return 0
    gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
    gray = cv2.medianBlur(gray, 5)
    h, w = gray.shape[:2]
    min_r = max(10, int(min(h, w) * 0.08))
    max_r = max(min_r + 2, int(min(h, w) * 0.42))
    circles = cv2.HoughCircles(
        gray,
        cv2.HOUGH_GRADIENT,
        dp=1.2,
        minDist=max(18, int(min(h, w) * 0.18)),
        param1=120,
        param2=28,
        minRadius=min_r,
        maxRadius=max_r,
    )
    return 0 if circles is None else int(len(circles[0]))


def _color_complexity(image: np.ndarray) -> float:
    if image.size == 0:
        return 0.0
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    return float(np.std(hsv[:, :, 1]))


def _college_profile(image: np.ndarray) -> dict[str, Any]:

    logo_zone = _roi(image, 0.00, 0.02, 0.24, 0.35)
    portrait_zone = _roi(image, 0.02, 0.28, 0.28, 0.78)
    signature_left = _roi(image, 0.00, 0.72, 0.42, 1.00)
    signature_right = _roi(image, 0.72, 0.72, 1.00, 1.00)
    header_zone = _roi(image, 0.22, 0.02, 0.98, 0.28)
    badge_zone = _roi(image, 0.82, 0.30, 1.00, 0.76)

    h, w = image.shape[:2]
    aspect = w / max(h, 1)
    face_count = _face_count(portrait_zone)
    seal_count = _circle_count(logo_zone)
    signature_density = max(_ink_density(signature_left), _ink_density(signature_right))
    header_edges = _edge_density(header_zone)
    badge_edges = _edge_density(badge_zone)
    color_std = _color_complexity(image)

    features = [
        _status(
            1.25 <= aspect <= 2.10,
            "Landscape card geometry",
            f"Aspect ratio {aspect:.2f} is within the configured college-ID range.",
            f"Aspect ratio {aspect:.2f} falls outside the configured college-ID range; crop/rotation may be affecting analysis.",
        ),
        _status(
            face_count >= 1,
            "Portrait / photo area",
            f"Detected {face_count} face(s) in the expected portrait zone.",
            "No face was detected in the expected portrait zone; verify crop, image quality or photo placement.",
        ),
        _status(
            seal_count >= 1,
            "Logo / seal region",
            f"Detected {seal_count} circular visual element(s) in the expected logo/seal zone.",
            "No clear circular logo/seal geometry was detected in the expected zone.",
        ),
        _status(
            0.002 <= signature_density <= 0.35,
            "Signature region",
            f"Ink density in the expected signature region is {signature_density:.3f}.",
            f"Expected signature-region ink pattern was weak or atypical ({signature_density:.3f}).",
        ),
        _status(
            header_edges > 0.008,
            "Header / security printing region",
            f"Header contains structured printed content (edge density {header_edges:.3f}).",
            "Header structure is unusually sparse; check crop, blur or synthetic reconstruction.",
        ),
        _status(
            badge_edges > 0.004,
            "Certification / emblem area",
            f"Right-side emblem/certification zone contains structured detail (edge density {badge_edges:.3f}).",
            "Expected right-side emblem/certification structure was not clearly detected.",
        ),
    ]

    return {
        "profile": "COLLEGE_ID_SRMCE_VISUAL",
        "features": features,
        "metrics": {
            "aspectRatio": round(aspect, 3),
            "portraitFaceCount": face_count,
            "logoCircleCount": seal_count,
            "signatureInkDensity": round(signature_density, 5),
            "headerEdgeDensity": round(header_edges, 5),
            "badgeEdgeDensity": round(badge_edges, 5),
            "colorSaturationStd": round(color_std, 3),
        },
    }



def _text_upper(value: str) -> str:
    return str(value or "").upper()


def _aadhaar_profile(image: np.ndarray, ocr_text: str) -> dict[str, Any]:
    h, w = image.shape[:2]
    upper = _text_upper(ocr_text)
    qr_detector = cv2.QRCodeDetector()
    qr_result = qr_detector.detectAndDecode(image)
    qr_data = qr_result[0] if qr_result else ""
    number_like = bool(re.search(r"\b\d{4}[ -]\d{4}[ -]\d{4}\b|\b\d{12}\b", upper))
    face_count = _face_count(_roi(image, 0.00, 0.18, 0.45, 0.88))
    bottom_ink = _ink_density(_roi(image, 0.05, 0.55, 0.95, 0.98))
    aspect = w / max(h, 1)
    return {
        "profile": "AADHAAR_PUBLIC_STRUCTURE",
        "features": [
            _status(number_like, "Aadhaar number structure", "A 12-digit Aadhaar-like number was found in OCR.", "No 12-digit Aadhaar-like identifier was established; verify OCR/crop."),
            _status(bool(qr_data), "Machine-readable QR", "A readable QR payload was detected.", "No readable QR payload was detected; absence is a review signal only."),
            _status(face_count >= 1, "Portrait region", "A face was detected in a plausible portrait area.", "No face was detected in a broad portrait search area; verify crop/image quality."),
            _status(0.50 <= aspect <= 2.80, "Card geometry", f"Aspect ratio {aspect:.2f} is within a broad identity-card range.", f"Aspect ratio {aspect:.2f} is unusual; crop/rotation may be affecting analysis."),
            _status(bottom_ink > 0.002, "Lower content structure", f"Lower document detail was detected (ink density {bottom_ink:.3f}).", "Lower document detail appears sparse; verify the scan/crop."),
        ],
        "metrics": {"width": w, "height": h, "aspectRatio": round(aspect, 3), "qrReadable": bool(qr_data), "portraitFaceCount": face_count},
    }


def _pan_profile(image: np.ndarray, ocr_text: str) -> dict[str, Any]:
    h, w = image.shape[:2]
    upper = _text_upper(ocr_text)
    pan_pattern = bool(re.search(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b", upper))
    face_count = _face_count(_roi(image, 0.00, 0.10, 0.55, 0.95))
    signature_density = max(_ink_density(_roi(image, 0.45, 0.68, 0.98, 0.99)), _ink_density(_roi(image, 0.02, 0.68, 0.45, 0.99)))
    aspect = w / max(h, 1)
    return {
        "profile": "PAN_PUBLIC_STRUCTURE",
        "features": [
            _status(pan_pattern, "PAN number structure", "A PAN-style 10-character identifier was found in OCR.", "No PAN-style identifier was established; verify OCR/crop."),
            _status(face_count >= 1, "Portrait region", "A face was detected in the broad portrait area.", "No face was detected in the broad portrait search area."),
            _status(signature_density > 0.002, "Signature/detail region", f"Lower-area ink/detail is present ({signature_density:.3f}).", "Lower-area signature/detail is weak; verify the scan/crop."),
            _status(0.90 <= aspect <= 2.20, "Card geometry", f"Aspect ratio {aspect:.2f} is within a broad PAN-card range.", f"Aspect ratio {aspect:.2f} is unusual for a PAN card."),
        ],
        "metrics": {"width": w, "height": h, "aspectRatio": round(aspect, 3), "portraitFaceCount": face_count, "panPattern": pan_pattern},
    }


def _passport_profile(image: np.ndarray, ocr_text: str) -> dict[str, Any]:
    h, w = image.shape[:2]
    upper = _text_upper(ocr_text)
    mrz = "<<<<" in upper and sum(line.count("<") >= 5 for line in upper.splitlines()) >= 1
    passport_number = bool(re.search(r"\b[A-Z][A-Z0-9]{7,8}\b", upper))
    face_count = _face_count(_roi(image, 0.00, 0.05, 0.48, 0.85))
    return {
        "profile": "PASSPORT_PUBLIC_STRUCTURE",
        "features": [
            _status(passport_number, "Passport number structure", "A plausible passport-number pattern was found.", "No plausible passport-number pattern was established."),
            _status(mrz, "MRZ structure", "Machine-readable-zone-like text was detected.", "No MRZ-like structure was detected; verify crop/page."),
            _status(face_count >= 1, "Portrait region", "A face was detected in the identity-photo area.", "No face was detected in the expected portrait area."),
            _status(w > h, "Landscape passport page geometry", f"Rendered page is wider than tall ({w}×{h}).", "Rendered page geometry may indicate an unusual crop/orientation."),
        ],
        "metrics": {"width": w, "height": h, "mrzDetected": mrz, "portraitFaceCount": face_count},
    }


def _driving_license_profile(image: np.ndarray, ocr_text: str) -> dict[str, Any]:
    h, w = image.shape[:2]
    upper = _text_upper(ocr_text)
    number_like = bool(re.search(r"\b[A-Z]{2}\s?\d{2}\s?(?:19|20)\d{2}\s?\d{4,8}\b", upper))
    pin_present = bool(re.search(r"\b\d{6}\b", upper))
    face_count = _face_count(_roi(image, 0.00, 0.12, 0.45, 0.88))
    signature_density = _ink_density(_roi(image, 0.40, 0.72, 0.98, 0.99))
    return {
        "profile": "DRIVING_LICENSE_PUBLIC_STRUCTURE",
        "features": [
            _status(number_like, "Licence-number structure", "A plausible Indian driving-licence number pattern was found.", "No plausible driving-licence number pattern was established."),
            _status(pin_present, "Address/PIN structure", "A six-digit PIN-like value is present in OCR.", "No six-digit PIN-like value was found; verify address extraction."),
            _status(face_count >= 1, "Portrait region", "A face was detected in a plausible portrait area.", "No face was detected in the portrait search area."),
            _status(signature_density > 0.002, "Signature/detail region", f"Lower-area signature/detail is present ({signature_density:.3f}).", "Lower-area signature/detail is weak; verify crop/scan."),
        ],
        "metrics": {"width": w, "height": h, "licencePattern": number_like, "pinPresent": pin_present, "portraitFaceCount": face_count},
    }


def _generic_profile(image: np.ndarray, ocr_text: str = "") -> dict[str, Any]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape[:2]
    aspect = w / max(h, 1)
    qr_detector = cv2.QRCodeDetector()
    qr_result = qr_detector.detectAndDecode(image)
    qr_data = qr_result[0] if qr_result else ""
    upper_text = str(ocr_text or "").upper()
    has_mrz = "<<<<" in upper_text and len([line for line in upper_text.splitlines() if line.count("<") >= 5]) >= 1
    bottom_ink = _ink_density(_roi(image, 0.05, 0.72, 0.95, 1.0))
    features = [
        _status(
            min(h, w) >= 500,
            "Minimum forensic resolution",
            f"Image resolution is {w}×{h}.",
            f"Image resolution is only {w}×{h}; forensic checks may be unreliable.",
        ),
        _status(
            0.50 <= aspect <= 2.60,
            "Document geometry",
            f"Aspect ratio {aspect:.2f} is within a broad document range.",
            f"Aspect ratio {aspect:.2f} is unusual for a document and may indicate crop/rotation.",
        ),
        _status(
            bool(qr_data),
            "QR / encoded region",
            "A machine-readable QR region is present and readable.",
            "No readable QR payload was found; absence is not itself evidence of forgery.",
        ),
        _status(
            has_mrz,
            "MRZ structure",
            "MRZ-like machine-readable text was found.",
            "No MRZ-like structure was found in OCR; only relevant for MRZ-bearing documents.",
        ),
        _status(
            bottom_ink > 0.003,
            "Signature / lower security region",
            f"Structured ink/detail is present near the lower edge ({bottom_ink:.3f}).",
            "Little lower-edge detail was detected; verify the document crop and signature area.",
        ),
    ]
    return {
        "profile": "GENERIC_VISUAL_SECURITY",
        "features": features,
        "metrics": {"width": w, "height": h, "aspectRatio": round(aspect, 3), "qrReadable": bool(qr_data)},
    }


def analyze_security_features(file_path: str, id_type: str, ocr_text: str = "") -> dict[str, Any]:
    image = _load_image(file_path)
    if image is None:
        return {
            "available": False,
            "overallStatus": "UNAVAILABLE",
            "score": None,
            "profile": str(id_type or "UNKNOWN").upper(),
            "features": [],
            "metrics": {},
            "summary": "Security-feature analysis could not read the uploaded document image.",
            "notice": "This layer checks visible/structural security cues. It does not verify proprietary holograms or issuer secrets.",
        }

    profile = str(id_type or "").strip().upper()
    if profile == "COLLEGE_ID":
        detail = _college_profile(image)
    elif profile == "AADHAAR":
        detail = _aadhaar_profile(image, ocr_text)
    elif profile == "PAN":
        detail = _pan_profile(image, ocr_text)
    elif profile == "PASSPORT":
        detail = _passport_profile(image, ocr_text)
    elif profile == "DRIVING_LICENSE":
        detail = _driving_license_profile(image, ocr_text)
    else:
        detail = _generic_profile(image, ocr_text)
    features = detail["features"]
    passed = sum(item["status"] == "PASS" for item in features)
    reviewed = len(features) - passed
    score = round((passed / max(len(features), 1)) * 100, 1)

    if reviewed == 0:
        overall = "PASS"
        summary = "Configured visible security/design cues were detected in the expected regions."
    elif passed >= max(2, len(features) // 2):
        overall = "REVIEW"
        summary = "Some expected security/design cues were weak or missing; inspect the evidence before accepting the document."
    else:
        overall = "HIGH"
        summary = "Several expected security/design cues were not detected; the document requires detailed verification."

    return {
        "available": True,
        "overallStatus": overall,
        "score": score,
        "profile": detail["profile"],
        "features": features,
        "metrics": detail["metrics"],
        "summary": summary,
        "passCount": passed,
        "reviewCount": reviewed,
        "notice": "Visible security-feature checks are screening evidence only. A missing feature can also be caused by crop, blur, scan quality, document redesign, or a different legitimate template. Proprietary holograms and issuer databases require authoritative source material or an authorised connector.",
    }
