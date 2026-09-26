from __future__ import annotations

import base64
import io
import os
from pathlib import Path
from typing import Any

from PIL import Image


EDITOR_SOFTWARE_MARKERS = {
    "adobe photoshop",
    "adobe",
    "photoshop",
    "lightroom",
    "gimp",
    "canva",
    "krita",
    "paint.net",
    "corel",
    "affinity",
    "pixelmator",
}

AI_SOFTWARE_MARKERS = {
    "stable diffusion",
    "midjourney",
    "dall-e",
    "openai",
    "firefly",
    "imagen",
    "sora",
    "leonardo",
    "insightface",
    "deepfake",
    "roop",
    "facefusion",
}

CAMERA_SOFTWARE_MARKERS = {
    "dcf",
    "exif",
    "samsung",
    "apple",
    "nokia",
    "motorola",
    "canon",
    "nikon",
    "sony",
    "xiaomi",
    "oppo",
    "vivo",
    "oneplus",
    "huawei",
    "realme",
    "pixel",
    "heic",
    "googlen",
}


def _read_with_exifread(file_path: str | Path) -> dict[str, Any]:
    try:
        import exifread
    except Exception:
        return {}
    try:
        with open(file_path, "rb") as handle:
            tags = exifread.process_file(handle, details=True)
        return tags or {}
    except Exception:
        return {}


def _tag_value(tags: dict, *names: str) -> str | None:
    for name in names:
        value = tags.get(name)
        if value is not None:
            rendered = str(value).strip()
            if rendered and rendered not in {"None", "Unknown"}:
                return rendered
    return None


def _pii_hash(value: str) -> str:
    import hashlib

    return hashlib.sha256(str(value).encode("utf-8", errors="ignore")).hexdigest()[:16]


def inspect_exif(file_path: str | Path) -> dict[str, Any]:
    path = Path(file_path)
    tags = _read_with_exifread(path)

    make = _tag_value(tags, "Image Make", "Image Model", "EXIF LensMake")
    model = _tag_value(tags, "Image Model", "EXIF BodySerialNumber")
    software = _tag_value(tags, "Image Software", "Image 0x0131", "EXIF Software")
    datetime_original = _tag_value(
        tags,
        "EXIF DateTimeOriginal",
        "Image DateTimeOriginal",
        "EXIF DateTimeDigitized",
    )


    if not tags and make is None and software is None:
        try:
            with Image.open(path) as image:
                getexif = image.getexif()
                if getexif:
                    software = software or _tag_or_none(getexif, 305)
                    make = make or _tag_or_none(getexif, 271)
                    model = model or _tag_or_none(getexif, 272)
                    datetime_original = datetime_original or _tag_or_none(getexif, 36867)
        except Exception:
            pass



    software_text = f"{software or ''} {make or ''} {model or ''}".lower()

    editor_hits: list[str] = []
    ai_hits: list[str] = []
    camera_hits: list[str] = []
    for marker in EDITOR_SOFTWARE_MARKERS:
        if marker in software_text:
            editor_hits.append(marker)
    for marker in AI_SOFTWARE_MARKERS:
        if marker in software_text:
            ai_hits.append(marker)
    for marker in CAMERA_SOFTWARE_MARKERS:
        if marker in software_text:
            camera_hits.append(marker)

    has_any_tag = bool(
        make
        or model
        or software
        or datetime_original
        or tags
    )

    if ai_hits:
        risk_level = "HIGH"
        summary = "Image metadata names an AI-generation tool."
    elif editor_hits:
        risk_level = "MEDIUM"
        summary = "Image metadata names a photo editor; this is a screening hint only."
    elif not has_any_tag:
        risk_level = "LOW"
        summary = "Image has no usable EXIF metadata (screen capture or re-encode)."
    else:
        risk_level = "LOW"
        summary = "Image contains camera/typical EXIF metadata."

    return {
        "metadata_present": has_any_tag,
        "tags": {
            "Make": make,
            "Model": model,
            "Software": software,
            "DateTimeOriginal": datetime_original,
        },
        "risk_level": risk_level,
        "summary": summary,
        "editor_software_hits": sorted(set(editor_hits)),
        "ai_software_hits": sorted(set(ai_hits)),
        "camera_software_hits": sorted(set(camera_hits)),
        "tag_count": len(tags) if tags else 0,
        "stripped_or_missing": not has_any_tag,
        "evidence_fp": {
            k: _pii_hash(v) for k, v in {
                "make": make,
                "model": model,
                "software": software,
                "datetime": datetime_original,
            }.items() if v
        },

        "preview": _base64_thumbnail(path),
    }


def _tag_or_none(getexif, tag_id: int) -> str | None:
    try:
        value = getexif.get(tag_id)
        return str(value).strip() if value not in (None, "", b"", 0) else None
    except Exception:
        return None


def _base64_thumbnail(path: Path, size: tuple[int, int] = (48, 48)) -> str | None:
    try:
        with Image.open(path) as image:
            thumb = image.convert("RGB")
            thumb.thumbnail(size)
            buffer = io.BytesIO()
            thumb.save(buffer, format="JPEG", quality=60)
            return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")
    except Exception:
        return None
