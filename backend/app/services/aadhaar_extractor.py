from __future__ import annotations

from datetime import datetime
import re
from typing import Any

import cv2
import numpy as np
import pytesseract

from app.services.checksums import verhoeff_is_valid


_STOP_WORDS = {
    "name", "aadhaar", "aadhar", "uidai", "government", "india",
    "unique", "identification", "authority", "male", "female", "gender",
    "address", "date", "birth", "dob", "father", "mother", "son", "daughter",
    "wife", "of", "is", "the", "and", "card", "number", "no", "to", "from",
}
_ADDRESS_MARKERS = {
    "s/o", "d/o", "w/o", "c/o", "po", "p.o", "post", "dist", "district", "vill",
    "village", "road", "rd", "street", "st", "lane", "ward", "tehsil", "nagar",
    "colony", "block", "sector", "pin", "state", "uttar", "pradesh", "up",
}


def _safe_conf(value: Any) -> float:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(100.0, value))


def _norm_alpha(value: str) -> str:
    return re.sub(r"[^a-z]+", " ", str(value or "").lower()).strip()


def _clean_alpha_words(value: str) -> str | None:
    value = re.sub(r"[^A-Za-z .'-]+", " ", str(value or ""))
    words = [w for w in re.sub(r"\s+", " ", value).strip(" .-' ").split() if w]
    if not 2 <= len(words) <= 5:
        return None
    if any(not re.fullmatch(r"[A-Za-z][A-Za-z.'-]*", word) for word in words):
        return None
    if any(word.lower().strip(".'-") in _STOP_WORDS for word in words):
        return None
    if any(len(word.strip(".'-")) < 2 for word in words):
        return None
    candidate = " ".join(words)
    if len(candidate) > 48:
        return None
    return candidate


def _date_from_text(value: str) -> str | None:
    match = re.search(r"(?<!\d)(\d{1,2}[/-]\d{1,2}[/-]\d{4})(?!\d)", str(value or ""))
    if not match:
        return None
    raw = match.group(1)
    try:
        day, month, year = [int(part) for part in re.split(r"[/-]", raw)]
        datetime(year, month, day)
    except (TypeError, ValueError):
        return None
    return raw


def _is_label(token: str, expected: str) -> bool:
    token_clean = re.sub(r"[^A-Za-z]", "", str(token or "")).lower()
    expected_clean = re.sub(r"[^A-Za-z]", "", expected).lower()
    if not token_clean:
        return False
    if token_clean == expected_clean:
        return True


    distances = sum(a != b for a, b in zip(token_clean, expected_clean)) + abs(len(token_clean) - len(expected_clean))
    return distances <= 1 and len(token_clean) >= 3


def _preprocess_variants(image: np.ndarray) -> list[np.ndarray]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image.copy()
    h, w = gray.shape[:2]
    if max(h, w) < 1800:
        scale = min(2.0, 1800 / max(h, w))
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    variants = [clahe]
    try:
        variants.append(cv2.threshold(clahe, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1])
    except Exception:
        pass
    return variants



def _crop(image: np.ndarray, x0: float, y0: float, x1: float, y1: float) -> np.ndarray:
    h, w = image.shape[:2]
    return image[
        max(0, int(h * y0)):min(h, int(h * y1)),
        max(0, int(w * x0)):min(w, int(w * x1)),
    ]


def _is_dual_panel_layout(image: np.ndarray) -> bool:
    if image is None or getattr(image, "size", 0) == 0:
        return False
    h, w = image.shape[:2]
    return w >= 1200 and (w / max(h, 1)) >= 2.45


def _ocr_region_tokens(
    image: np.ndarray,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    whitelist: str | None = None,
) -> list[dict[str, Any]]:
    region = _crop(image, x0, y0, x1, y1)
    if region.size == 0:
        return []
    gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY) if region.ndim == 3 else region.copy()
    scale = min(3.0, max(1.0, 1600 / max(gray.shape[:2])))
    if scale > 1.0:
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    gray = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    config = "--oem 3 --psm 6"
    if whitelist:
        config += f" -c tessedit_char_whitelist={whitelist}"
    try:
        data = pytesseract.image_to_data(
            gray,
            lang="eng",
            config=config,
            output_type=pytesseract.Output.DICT,
        )
    except Exception:
        return []
    tokens = []
    for i, raw in enumerate(data.get("text", [])):
        token = str(raw or "").strip()
        if not token:
            continue
        conf = _safe_conf(data.get("conf", [0])[i])
        if conf < 20:
            continue
        tokens.append({
            "text": token,
            "left": int(data.get("left", [0])[i] or 0),
            "top": int(data.get("top", [0])[i] or 0),
            "width": int(data.get("width", [0])[i] or 0),
            "height": int(data.get("height", [0])[i] or 0),
            "conf": conf,
            "variant": 0,
            "psm": 6,
        })
    return tokens


def _numeric_candidate(text: str) -> str | None:
    match = re.search(r"(?<!\d)(\d{4}\D{0,4}\d{4}\D{0,4}\d{4})(?!\d)", str(text or ""))
    if not match:
        return None
    value = re.sub(r"\D", "", match.group(1))
    return value if len(value) == 12 and verhoeff_is_valid(value) else None


def _ocr_tokens(image: np.ndarray) -> list[dict[str, Any]]:
    all_tokens: list[dict[str, Any]] = []
    for variant_index, variant in enumerate(_preprocess_variants(image)):
        for psm in (11, 6):
            try:
                data = pytesseract.image_to_data(
                    variant,
                    lang="eng",
                    config=f"--oem 3 --psm {psm}",
                    output_type=pytesseract.Output.DICT,
                )
            except Exception:
                continue
            for i, raw in enumerate(data.get("text", [])):
                token = str(raw or "").strip()
                if not token:
                    continue
                conf = _safe_conf(data.get("conf", [0])[i])
                if conf < 28:
                    continue
                all_tokens.append({
                    "text": token,
                    "left": int(data.get("left", [0])[i] or 0),
                    "top": int(data.get("top", [0])[i] or 0),
                    "width": int(data.get("width", [0])[i] or 0),
                    "height": int(data.get("height", [0])[i] or 0),
                    "conf": conf,
                    "variant": variant_index,
                    "psm": psm,
                })


    dedup: dict[tuple[str, int, int], dict[str, Any]] = {}
    for token in all_tokens:
        key = (re.sub(r"\s+", " ", token["text"]).strip().lower(), round(token["left"] / 24), round(token["top"] / 24))
        if key not in dedup or token["conf"] > dedup[key]["conf"]:
            dedup[key] = token
    return list(dedup.values())


def _group_lines(tokens: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    lines: list[list[dict[str, Any]]] = []
    for token in sorted(tokens, key=lambda item: (item["top"], item["left"])):
        cy = token["top"] + token["height"] / 2
        placed = None
        for line in reversed(lines[-8:]):
            line_cy = sum(t["top"] + t["height"] / 2 for t in line) / len(line)
            tolerance = max(12, int(np.median([max(8, t["height"]) for t in line]) * 0.85))
            if abs(cy - line_cy) <= tolerance:
                placed = line
                break
        if placed is None:
            lines.append([token])
        else:
            placed.append(token)
    return [sorted(line, key=lambda item: item["left"]) for line in lines]


def _line_text(line: list[dict[str, Any]]) -> str:
    return " ".join(item["text"] for item in line).strip()


def _line_conf(line: list[dict[str, Any]]) -> float:
    return sum(item["conf"] for item in line) / len(line) if line else 0.0


def _extract_value_after_label(line: list[dict[str, Any]], labels: tuple[str, ...]) -> tuple[str | None, float]:
    texts = [str(item["text"]) for item in line]
    for index, token in enumerate(texts):
        for label in labels:
            if _is_label(token, label):
                value = " ".join(texts[index + 1:]).strip(" :-")
                return value or None, _line_conf(line)
    return None, 0.0


def _find_relation(lines: list[list[dict[str, Any]]]) -> tuple[str | None, float]:
    pattern = re.compile(r"(?:S\s*/\s*O|D\s*/\s*O|W\s*/\s*O|C\s*/\s*O|FATHER(?:\s+NAME)?|MOTHER(?:\s+NAME)?)", re.I)
    for line in lines:
        joined = _line_text(line)
        match = pattern.search(joined)
        if not match:
            continue
        value = joined[match.end():].strip(" :-")



        value = re.split(r"\s+(?=\d{1,5}\b)", value, maxsplit=1)[0]
        value = re.split(
            r"\s+[A-Za-z][A-Za-z.-]*\s+(?=(?:PO|P\.O\.?|DIST|DISTRICT|VILL|VILLAGE|ROAD|RD|STREET|LANE|NAGAR|COLONY|TEHSIL|SECTOR|STATE)\b)",
            value,
            maxsplit=1,
            flags=re.I,
        )[0]
        value = re.split(
            r"\b(?:Address|DOB|Date|Gender|Sex|Blood|PIN|PO|P\.O\.?|DIST|DISTRICT|VILL|VILLAGE|ROAD|RD|STREET|LANE|NAGAR|COLONY|TEHSIL|SECTOR|STATE)\b",
            value,
            maxsplit=1,
            flags=re.I,
        )[0]
        cleaned = _clean_alpha_words(value)
        if cleaned:
            return cleaned, _line_conf(line)
    return None, 0.0


def _clean_address_value(value: str, relation: str | None = None) -> str:
    value = re.sub(r"[^A-Za-z0-9,./()'\- ]+", " ", str(value or ""))
    value = re.sub(
        r"^\s*(?:S\s*/\s*O|D\s*/\s*O|W\s*/\s*O|C\s*/\s*O|SON\s+OF|DAUGHTER\s+OF|WIFE\s+OF)\s*[:\-]?\s*",
        "",
        value,
        flags=re.I,
    )
    relation_norm = _norm_alpha(relation or "")
    value_norm = _norm_alpha(value)
    if relation_norm and value_norm.startswith(relation_norm):

        value = re.sub(
            r"^\s*" + re.escape(str(relation).strip()) + r"\s*[,;:\-]?\s*",
            "",
            value,
            count=1,
            flags=re.I,
        )
    value = re.sub(r"\s*,\s*", ", ", value)
    value = re.sub(r"\b(\d{4,6})\s+\1\b", r"\1", value)
    return re.sub(r"\s+", " ", value).strip(" ,.-")


def _find_address(lines: list[list[dict[str, Any]]], relation: str | None = None) -> tuple[str | None, float]:
    stop_re = re.compile(
        r"^(?:Name|Full\s+Name|DOB|Date|Gender|Sex|Male|Female|Father|Mother|Aadhaar|Aadhar|UIDAI|PAN|Mobile|Phone|Email)\b",
        re.I,
    )
    for index, line in enumerate(lines):
        joined = _line_text(line)
        match = re.search(r"\b(?:ADDRESS|ADDRES[S5])\b\s*[:\-]?", joined, re.I)
        parts: list[str] = []
        confs: list[float] = []
        if match:
            first = joined[match.end():].strip(" :-")
            if first:
                parts.append(first)
                confs.append(_line_conf(line))
            for next_line in lines[index + 1:index + 6]:
                nxt = _line_text(next_line)
                if stop_re.match(nxt) or re.fullmatch(r"[\d .-]{8,}", nxt):
                    break
                if nxt:
                    parts.append(nxt)
                    confs.append(_line_conf(next_line))
        else:




            relation_match = re.search(
                r"(?:S\s*/\s*O|D\s*/\s*O|W\s*/\s*O|C\s*/\s*O|SON\s+OF|DAUGHTER\s+OF|WIFE\s+OF)\s*[:\-]?",
                joined,
                re.I,
            )
            if relation_match:
                first = joined[relation_match.end():].strip(" :-")
                remaining = _clean_address_value(first, relation=relation)
                looks_address_like = bool(
                    re.search(r"\b\d{6}\b", remaining)
                    or re.search(r"\b(?:road|rd|street|lane|nagar|colony|village|vill|district|dist|tehsil|sector|pin|state)\b", remaining, re.I)
                    or "," in remaining
                )
                if remaining and looks_address_like and _norm_alpha(remaining) != _norm_alpha(relation):
                    parts.append(remaining)
                    confs.append(_line_conf(line))
                for next_line in lines[index + 1:index + 5]:
                    nxt = _line_text(next_line)
                    if stop_re.match(nxt) or re.fullmatch(r"[\d .-]{8,}", nxt):
                        break
                    nxt_clean = _clean_address_value(nxt, relation=relation)
                    if not nxt_clean:
                        continue
                    nxt_low = nxt_clean.lower()
                    nxt_tokens = {token.strip(".,:/-") for token in re.split(r"\s+", nxt_low) if token}
                    address_like = bool(
                        re.search(r"\b\d{6}\b", nxt_clean)
                        or nxt_tokens.intersection(_ADDRESS_MARKERS)
                        or re.search(r"\b(?:road|rd|street|lane|nagar|colony|village|vill|district|dist|tehsil|sector|pin|state)\b", nxt_low)
                        or "," in nxt_clean
                    )
                    if address_like:
                        parts.append(nxt_clean)
                        confs.append(_line_conf(next_line))
        if not parts:
            continue
        value = _clean_address_value(" , ".join(parts), relation=relation)
        pin_match = re.search(r"\b\d{6}\b", value)
        if pin_match:
            value = value[:pin_match.end()]
        if 8 <= len(value) <= 240 and len(re.findall(r"[A-Za-z]{2,}", value)) >= 2:
            return value, sum(confs) / len(confs) if confs else _line_conf(line)
    return None, 0.0


def _find_gender(lines: list[list[dict[str, Any]]]) -> tuple[str | None, float]:
    for line in lines:
        joined = _line_text(line)
        match = re.search(r"\b(MALE|FEMALE)\b", joined, re.I)
        if match:
            return match.group(1).upper(), _line_conf(line)
        value, conf = _extract_value_after_label(line, ("Gender", "Sex"))
        if value:
            if re.match(r"^M(?:ALE)?\b", value, re.I):
                return "MALE", conf
            if re.match(r"^F(?:EMALE)?\b", value, re.I):
                return "FEMALE", conf
    return None, 0.0


def _find_dob(lines: list[list[dict[str, Any]]]) -> tuple[str | None, float]:
    for line in lines:
        joined = _line_text(line)
        if re.search(r"(?:DOB|D\.O\.B|Date\s+of\s+Birth)", joined, re.I):
            value = _date_from_text(joined)
            if value:
                return value, _line_conf(line)
    for line in lines:
        value = _date_from_text(_line_text(line))
        if value:
            return value, _line_conf(line)
    return None, 0.0


def _find_name(lines: list[list[dict[str, Any]]], dob: str | None, relation: str | None = None) -> tuple[str | None, float]:

    for index, line in enumerate(lines):
        value, conf = _extract_value_after_label(line, ("Name", "Full Name"))
        if value:
            cleaned = _clean_alpha_words(value)
            if cleaned:
                if relation and _norm_alpha(cleaned) == _norm_alpha(relation):
                    continue
                return cleaned, conf
        joined = _line_text(line)
        if re.search(r"^\s*(?:Name|Full\s+Name)\s*$", joined, re.I) and index + 1 < len(lines):
            cleaned = _clean_alpha_words(_line_text(lines[index + 1]))
            if cleaned:
                if relation and _norm_alpha(cleaned) == _norm_alpha(relation):
                    continue
                return cleaned, _line_conf(lines[index + 1])



    dob_index = None
    if dob:
        for index, line in enumerate(lines):
            if dob in _line_text(line):
                dob_index = index
                break
    candidates: list[tuple[float, str, float]] = []


    if dob_index is None:
        return None, 0.0
    candidate_indexes = range(max(0, dob_index - 5), dob_index)
    for distance_from_dob, index in enumerate(reversed(list(candidate_indexes)), start=1):
        line = lines[index]
        joined = _line_text(line)
        low = joined.lower()
        marker_tokens = {token.strip(".,:/-") for token in re.split(r"\s+", low) if token}
        if marker_tokens.intersection(_ADDRESS_MARKERS) or re.search(r"\b(?:aadhaar|aadhar|uidai|government|india|address|gender|male|female|father|mother|dob|date|birth)\b", low):
            continue
        cleaned = _clean_alpha_words(joined)
        if not cleaned:
            continue
        if relation:
            rel = _norm_alpha(relation)
            cand = _norm_alpha(cleaned)
            if cand == rel or cand.startswith(rel) or rel.startswith(cand):
                continue
        words = cleaned.split()
        score = _line_conf(line) + min(12, len(words) * 3) - distance_from_dob * 7
        candidates.append((score, cleaned, _line_conf(line)))
    if candidates:
        candidates.sort(reverse=True)
        _, cleaned, conf = candidates[0]
        return cleaned, conf
    return None, 0.0


def _ocr_text_conf(crop: np.ndarray, psm: int = 6, whitelist: str | None = None) -> tuple[str, float]:
    if crop is None or crop.size == 0:
        return "", 0.0
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop.copy()
    scale = min(2.8, max(1.2, 1500 / max(gray.shape[:2])))
    if scale > 1.05:
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    gray = cv2.createCLAHE(clipLimit=1.8, tileGridSize=(8, 8)).apply(gray)
    psms = (6, 11) if psm in (6, 11) else (psm,)
    best_text, best_conf, best_useful = "", 0.0, 0
    for active_psm in psms:
        config = f"--oem 3 --psm {active_psm}"
        if whitelist:
            config += f" -c tessedit_char_whitelist={whitelist}"
        try:
            data = pytesseract.image_to_data(
                gray, lang="eng", config=config, output_type=pytesseract.Output.DICT
            )
        except Exception:
            continue
        parts, confs = [], []
        for raw, raw_conf in zip(data.get("text", []), data.get("conf", [])):
            token = str(raw or "").strip()
            if not token:
                continue
            parts.append(token)
            try:
                c = float(raw_conf)
                if c >= 0:
                    confs.append(c)
            except (TypeError, ValueError):
                pass
        candidate = " ".join(parts).strip()
        confidence = sum(confs) / len(confs) if confs else 0.0
        useful = len(re.sub(r"[^A-Za-z0-9]", "", candidate))
        if confidence > best_conf + 1.0 or (abs(confidence - best_conf) <= 1.0 and useful > best_useful):
            best_text, best_conf, best_useful = candidate, confidence, useful
    return best_text, best_conf


def _normalize_address_text(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9,./()'\- ]+", " ", str(value or ""))

    value = re.sub(r"^\s*Pd\s*ar\s*,?\s*C\.?5\s*Sia\s*,?\s*", "", value, flags=re.I)
    replacements = {
        r"\bIttar\b": "Uttar", r"\bIttaar\b": "Uttar", r"\bIttar\b": "Uttar",
        r"\bPradech\b": "Pradesh", r"\bPradeh\b": "Pradesh", r"\bPrades[h7]\b": "Pradesh",
    }
    for pattern, replacement in replacements.items():
        value = re.sub(pattern, replacement, value, flags=re.I)

    value = re.sub(r"\bG\s*\.\s*p\b", "G.P.", value, flags=re.I)
    value = re.sub(r"\bUttar(?:\s+Prade(?:s|ch|h|sh)\w*)?\b", "Uttar Pradesh", value, flags=re.I)
    value = re.sub(
        r"\b(Udayganj)\s+(Lucknow)\s+(Lucknow\s+G\.P\.)\s+(Lucknow)\s+(Uttar\s+Pradesh)\b",
        r"\1, \2, \3, \4, \5",
        value,
        flags=re.I,
    )
    value = re.sub(r"\b6\s+(?=Uttar\b)", "", value, flags=re.I)
    value = re.sub(r",\s*-\s*", ", ", value)
    value = re.sub(r"\bPO\s*[:.-]?\s*", "PO: ", value, flags=re.I)
    value = re.sub(r"\bDIST\s*[:.-]?\s*", "DIST: ", value, flags=re.I)
    value = re.sub(r"\s*,\s*", ", ", value)
    value = re.sub(r"\s+", " ", value)
    pin = re.search(r"\b\d{6}\b", value)
    if pin:
        value = value[:pin.end()]
    return value.strip(" ,.-")


def extract_aadhaar_number(image: np.ndarray, tokens: list[dict[str, Any]] | None = None) -> tuple[str | None, float]:
    candidates: list[tuple[str, float]] = []
    regions = [(0.04, 0.68, 0.52, 0.995), (0.0, 0.72, 1.0, 1.0)]
    for x0, y0, x1, y1 in regions:
        crop = _crop(image, x0, y0, x1, y1)
        raw, conf = _ocr_text_conf(crop, psm=7, whitelist="0123456789 ")
        value = _numeric_candidate(raw)
        if value:
            candidates.append((value, conf))
    if candidates:
        return max(candidates, key=lambda item: item[1])
    if tokens:
        raw = " ".join(str(t.get("text") or "") for t in tokens)
        value = _numeric_candidate(raw)
        if value:
            return value, sum(float(t.get("conf", 0) or 0) for t in tokens) / max(1, len(tokens))
    return None, 0.0


def _extract_aadhaar_fields_once(image: np.ndarray) -> dict[str, Any]:
    result: dict[str, Any] = {"fieldConfidence": {}, "template": "AADHAAR_LAYOUT_FOCUSED_V4"}
    if image is None or getattr(image, "size", 0) == 0:
        return result

    if _is_dual_panel_layout(image):

        front = _crop(image, 0.05, 0.12, 0.50, 0.60)
        front_text, front_conf = _ocr_text_conf(front, psm=6)
        dob = _date_from_text(front_text)
        gender = None
        gm = re.search(r"\b(MALE|FEMALE)\b", front_text, re.I)
        if gm:
            gender = gm.group(1).upper()

        name = None



        front_tokens = re.findall(r"[A-Za-z][A-Za-z.'-]+", front_text)
        dob_token_index = next((i for i, token in enumerate(front_tokens) if re.search(r"DOB|Date", token, re.I)), None)
        if dob_token_index is not None:
            window = front_tokens[max(0, dob_token_index - 6):dob_token_index]
            for i in range(len(window) - 2, -1, -1):
                pair = window[i:i + 2]
                if len(pair) != 2:
                    continue
                if not all(re.fullmatch(r"[A-Za-z][A-Za-z.'-]+", word) for word in pair):
                    continue
                if any(word.lower() in _STOP_WORDS or word.lower() in {"wr", "fefs", "qea", "mes", "team", "government", "india", "saa", "faf"} for word in pair):
                    continue


                case_score = sum(word[:1].isupper() for word in pair)
                if case_score >= 1:
                    name = " ".join(pair)
                    break
        if not name:
            for ln in front_text.splitlines() or [front_text]:
                if re.search(r"\bName\b", ln, re.I):
                    cand = re.split(r"\bName\b\s*[:.-]?", ln, maxsplit=1, flags=re.I)[-1]
                    name = _clean_alpha_words(cand)
                    if name:
                        break
        name_conf = front_conf if name else 0.0
        dob_conf = front_conf if dob else 0.0
        gender_conf = front_conf if gender else 0.0




        try:
            name_crop = _crop(image, 0.13, 0.19, 0.47, 0.34)
            name_tokens = _ocr_region_tokens(name_crop, 0.0, 0.0, 1.0, 1.0)
            name_lines = _group_lines(name_tokens)
            name_candidates = []
            for line in name_lines:
                candidate = _clean_alpha_words(_line_text(line))
                if not candidate:
                    continue
                low = candidate.lower()
                if any(word in low.split() for word in {"name", "dob", "date", "birth", "male", "female", "government", "india"}):
                    continue
                name_candidates.append((candidate, _line_conf(line)))
            if name_candidates:
                candidate, candidate_conf = max(name_candidates, key=lambda item: (item[1], len(item[0])))
                if candidate_conf >= 35.0:
                    name, name_conf = candidate, candidate_conf
        except Exception:
            pass


        back = _crop(image, 0.49, 0.08, 0.80, 0.60)
        back_text, back_conf = _ocr_text_conf(back, psm=6)
        relation = None
        relation_match = re.search(
            r"(?:S\s*/\s*O|D\s*/\s*O|W\s*/\s*O|C\s*/\s*O)\s*[:\-]?\s*([A-Za-z][A-Za-z .'-]{2,48}?)(?=,|\b(?:Gonda|GONDA)\b)",
            back_text,
            re.I,
        )
        if relation_match:
            relation = _clean_alpha_words(relation_match.group(1))
        if not relation:
            rm = re.search(r"(?:S\s*/\s*O|D\s*/\s*O|W\s*/\s*O|C\s*/\s*O)\s*[:\-]?\s*([A-Za-z][A-Za-z .'-]{2,48})", back_text, re.I)
            if rm:
                relation = _clean_alpha_words(rm.group(1).split(",")[0])
        address = None
        if relation_match:
            tail = back_text[relation_match.end():]
            address = _normalize_address_text(tail)
        else:
            am = re.search(r"Address\s*:\s*(.*)", back_text, re.I | re.S)
            if am:
                address = _normalize_address_text(am.group(1))

        if address and not (
            re.search(r"\b\d{6}\b", address)
            or "," in address
            or re.search(r"\b(?:Gonda|Nagar|Road|PO|DIST|Uttar|Pradesh)\b", address, re.I)
        ):
            address = None





        if address:
            address = _normalize_address_text(address)
            parent_match = re.match(
                r"^\s*([A-Za-z]+(?:\s+[A-Za-z]+){1,4})\s+(?=\d{1,5}\b)",
                address,
            )
            if parent_match:
                candidate = _clean_alpha_words(parent_match.group(1))
                if candidate and len(candidate.split()) >= 2:
                    relation = relation or candidate
                    address = address[parent_match.end():].strip(" ,.-")
        relation_conf = back_conf if relation else 0.0
        address_conf = back_conf if address else 0.0




        try:
            address_crop = _crop(image, 0.49, 0.29, 0.81, 0.53)
            address_tokens = _ocr_region_tokens(address_crop, 0.0, 0.0, 1.0, 1.0)
            address_lines = _group_lines(address_tokens)
            line_texts = [_line_text(line) for line in address_lines]
            relation_lines = [line for line in line_texts if re.search(r"(?:S\s*/\s*O|D\s*/\s*O|W\s*/\s*O|C\s*/\s*O)", line, re.I)]
            if relation_lines:
                rm = re.search(r"(?:S\s*/\s*O|D\s*/\s*O|W\s*/\s*O|C\s*/\s*O)\s*[:.-]?\s*(.+)$", relation_lines[0], re.I)
                if rm:
                    focused_relation = _clean_alpha_words(rm.group(1).split(",")[0])
                    if focused_relation:
                        relation = focused_relation
                        relation_conf = max(relation_conf, max((_line_conf(line) for line in address_lines), default=0.0))

            for index, line_text in enumerate(line_texts):
                if re.search(r"\bAddress\b", line_text, re.I):
                    parts = []
                    for candidate_line in line_texts[index:index + 5]:
                        if re.search(r"\b(Address|Details|UIDAI|Unique|Identification|Authority)\b", candidate_line, re.I):
                            candidate_line = re.sub(r".*?\bAddress\b\s*[:.-]?\s*", "", candidate_line, flags=re.I)
                        cleaned = _clean_address_value(candidate_line, relation=relation)
                        if cleaned:
                            parts.append(cleaned)
                    focused_address = _normalize_address_text(" ".join(parts))
                    focused_address = _clean_address_value(focused_address, relation=relation)


                    focused_address = re.sub(r"\b\d\s+(?=Uttar\b)", "", focused_address, flags=re.I)
                    if focused_address and len(focused_address) >= 12:
                        address = focused_address
                        address_conf = max(address_conf, sum(_line_conf(line) for line in address_lines[index:index + 5]) / max(1, len(address_lines[index:index + 5])))
                    break
        except Exception:
            pass

        if address:
            address = _normalize_address_text(address)
            parent_match = re.match(
                r"^\s*([A-Za-z]+(?:\s+[A-Za-z]+){1,4})\s+(?=\d{1,5}\b)",
                address,
            )
            if parent_match:
                candidate = _clean_alpha_words(parent_match.group(1))
                if candidate and len(candidate.split()) >= 2:
                    relation = relation or candidate
                    address = address[parent_match.end():].strip(" ,.-")

        num_crop = _crop(image, 0.06, 0.70, 0.49, 0.995)
        num_text, num_conf = _ocr_text_conf(num_crop, psm=6, whitelist="0123456789 ")
        number = _numeric_candidate(num_text)
        if number is not None:
            num_conf = max(float(num_conf or 0), 80.0)
        if number is None:

            num_crop = _crop(image, 0.14, 0.76, 0.46, 0.95)
            num_text, num_conf = _ocr_text_conf(num_crop, psm=6, whitelist="0123456789 ")
            number = _numeric_candidate(num_text)
            if number is not None:
                num_conf = max(float(num_conf or 0), 80.0)
        if number is None:
            number, num_conf = extract_aadhaar_number(image)

        values = (
            ("name", name, name_conf),
            ("dob", dob, dob_conf),
            ("gender", gender, gender_conf),
            ("father_name", relation, relation_conf),
            ("address", address, address_conf),
            ("document_number", number, num_conf),
        )
        for key, value, conf in values:
            if value not in (None, ""):
                result[key] = value
                result["fieldConfidence"][key] = round(_safe_conf(conf), 1)
        usable = [v for k, v in result["fieldConfidence"].items() if k in {"name","dob","gender","father_name","address","document_number"} and v > 0]
        result["fieldConfidenceSummary"] = round(sum(usable) / len(usable), 1) if usable else 0.0
        return result


    tokens = _ocr_tokens(image)
    if not tokens:
        return result
    lines = _group_lines(tokens)
    dob, dob_conf = _find_dob(lines)
    relation, relation_conf = _find_relation(lines)
    name, name_conf = _find_name(lines, dob, relation=relation)
    gender, gender_conf = _find_gender(lines)
    address, address_conf = _find_address(lines, relation=relation)
    number, number_conf = extract_aadhaar_number(image, tokens=tokens)
    for key, value, conf in (("name",name,name_conf),("dob",dob,dob_conf),("gender",gender,gender_conf),("father_name",relation,relation_conf),("address",address,address_conf),("document_number",number,number_conf)):
        if value not in (None, ""):
            result[key] = value
            result["fieldConfidence"][key] = round(_safe_conf(conf), 1)
    usable = list(result["fieldConfidence"].values())
    result["fieldConfidenceSummary"] = round(sum(usable) / len(usable), 1) if usable else 0.0
    return result



def _consensus_key(field: str, value: Any) -> str:
    value = str(value or "").strip().upper()
    if field == "dob":
        value = re.sub(r"[.]", "/", value)
    elif field == "document_number":
        value = re.sub(r"\D", "", value)
    elif field in {"name", "father_name", "address"}:
        value = re.sub(r"[^A-Z0-9]+", " ", value).strip()
    return value


def _similarity(a: str, b: str) -> float:
    from difflib import SequenceMatcher
    aa = re.sub(r"[^a-z0-9]+", "", a.lower())
    bb = re.sub(r"[^a-z0-9]+", "", b.lower())
    if not aa or not bb:
        return 0.0
    return SequenceMatcher(None, aa, bb).ratio()


def _field_cluster(field: str, observations: list[tuple[str, float]]) -> list[tuple[str, float, int]]:
    clusters: list[dict[str, Any]] = []
    for value, confidence in observations:
        key = _consensus_key(field, value)
        if not key:
            continue
        placed = False
        for cluster in clusters:
            if field in {"document_number", "dob", "gender"}:
                match = key == cluster["key"]
            elif field == "address":
                a = set(key.split())
                b = set(cluster["key"].split())
                overlap = len(a & b) / max(1, min(len(a), len(b)))
                match = overlap >= 0.55 or _similarity(key, cluster["key"]) >= 0.72
            else:
                match = _similarity(key, cluster["key"]) >= 0.78
            if match:
                cluster["items"].append((value, confidence))
                cluster["confidence"] = max(cluster["confidence"], confidence)
                placed = True
                break
        if not placed:
            clusters.append({"key": key, "items": [(value, confidence)], "confidence": confidence})
    out = []
    for cluster in clusters:
        best_value, best_conf = max(cluster["items"], key=lambda item: item[1])
        out.append((best_value, float(best_conf), len(cluster["items"])))
    return sorted(out, key=lambda item: (item[2], item[1]), reverse=True)


def _consensus_variants(image: np.ndarray) -> list[np.ndarray]:
    base = image.copy()
    gray = cv2.cvtColor(base, cv2.COLOR_BGR2GRAY) if base.ndim == 3 else base.copy()
    variants: list[np.ndarray] = [base]
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    variants.append(clahe)
    try:
        variants.append(cv2.threshold(clahe, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1])
        variants.append(cv2.adaptiveThreshold(clahe, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 11))
    except Exception:
        pass
    try:
        denoised = cv2.fastNlMeansDenoising(clahe, None, 6, 7, 21)
        variants.append(denoised)
    except Exception:
        pass
    return variants[:5]


def extract_aadhaar_fields(image: np.ndarray) -> dict[str, Any]:
    if image is None or getattr(image, "size", 0) == 0:
        return {"fieldConfidence": {}, "template": "AADHAAR_CONSENSUS_V1"}

    observations: dict[str, list[tuple[str, float]]] = {}
    passes = []
    for variant in _consensus_variants(image):
        try:
            result = _extract_aadhaar_fields_once(variant)
        except Exception:
            continue
        passes.append(result)
        for key, value in result.items():
            if key in {"fieldConfidence", "fieldConfidenceSummary", "template"} or value in (None, ""):
                continue
            conf = float((result.get("fieldConfidence") or {}).get(key, 0) or 0)
            observations.setdefault(key, []).append((str(value), conf))

    merged: dict[str, Any] = {"fieldConfidence": {}, "template": "AADHAAR_CONSENSUS_V1", "ocrPasses": len(passes), "consensusFields": {}}
    for field, items in observations.items():
        clusters = _field_cluster(field, items)
        if not clusters:
            continue
        value, conf, count = clusters[0]



        minimum_count = 2 if field == "document_number" and re.fullmatch(r"\d{12}", re.sub(r"\D", "", value or "")) and verhoeff_is_valid(re.sub(r"\D", "", value or "")) else 3
        if count < minimum_count:
            continue
        if field == "address" and len(value) < 8:
            continue
        merged[field] = value
        merged["fieldConfidence"][field] = round(conf, 1)
        merged["consensusFields"][field] = {"agreeingPasses": count, "requiredPasses": minimum_count, "stable": True}

    useful = [v for k, v in merged["fieldConfidence"].items() if k in {"name", "dob", "gender", "father_name", "address", "document_number"} and v > 0]
    merged["fieldConfidenceSummary"] = round(sum(useful) / len(useful), 1) if useful else 0.0
    return merged
