from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import fitz
import numpy as np
from PIL import Image


def _pixmap_to_bgr(pix: fitz.Pixmap) -> np.ndarray | None:
    if pix is None or pix.width <= 0 or pix.height <= 0:
        return None
    try:
        channels = pix.n
        raw = np.frombuffer(pix.samples, dtype=np.uint8)
        if channels == 4:
            rgba = raw.reshape(pix.height, pix.width, 4)
            return cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGR)
        rgb = raw.reshape(pix.height, pix.width, channels)
        if channels == 1:
            return cv2.cvtColor(rgb, cv2.COLOR_GRAY2BGR)
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    except Exception:
        return None


def _pil_to_bgr(image: Image.Image) -> np.ndarray | None:
    try:
        rgb = np.asarray(image.convert("RGB"))
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    except Exception:
        return None


def _load_pdf_page_with_fallback(
    path: str | Path,
    page_index: int = 0,
    *,
    high_res: bool = False,
) -> np.ndarray | None:
    document = None
    try:
        document = fitz.open(str(path))
        if page_index < 0 or page_index >= document.page_count:
            return None
        page = document.load_page(page_index)

        candidates: list[tuple[int, int, int, int]] = []
        for item in page.get_images(full=True):
            xref = int(item[0])
            width = int(item[2] or 0)
            height = int(item[3] or 0)
            if width > 0 and height > 0:
                candidates.append((width * height, xref, width, height))

        min_embedded_side = 1400 if high_res else 500
        for _, xref, width, height in sorted(candidates, reverse=True):
            try:
                pix = fitz.Pixmap(document, xref)
                image = _pixmap_to_bgr(pix)
                if image is not None and min(image.shape[:2]) >= 500:
                    if not high_res or max(image.shape[:2]) >= min_embedded_side:
                        return image
            except Exception:
                continue



        matrix = fitz.Matrix(4.0, 4.0) if high_res else fitz.Matrix(3.2, 3.2)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        return _pixmap_to_bgr(pix)
    except Exception:
        return None
    finally:
        if document is not None:
            document.close()


def load_pdf_page_image(path: str | Path, page_index: int = 0) -> np.ndarray | None:
    return _load_pdf_page_with_fallback(path, page_index, high_res=False)


def load_pdf_page_image_high_res(path: str | Path, page_index: int = 0) -> np.ndarray | None:
    return _load_pdf_page_with_fallback(path, page_index, high_res=True)


def load_pdf_pages(path: str | Path, max_pages: int = 3) -> list[np.ndarray]:
    try:
        with fitz.open(str(path)) as document:
            page_count = min(max_pages, document.page_count)
        pages: list[np.ndarray] = []
        for index in range(page_count):
            page = load_pdf_page_image(path, index)
            if page is not None and page.size:
                pages.append(page)
        return pages
    except Exception:
        return []


def enhance_document_image(image: np.ndarray, max_width: int = 1600) -> np.ndarray:
    if image is None or image.size == 0:
        return image

    working = image.copy()
    try:


        lab = cv2.cvtColor(working, cv2.COLOR_BGR2LAB)
        l_channel, a_channel, b_channel = cv2.split(lab)
        l_channel = cv2.createCLAHE(clipLimit=1.5, tileGridSize=(8, 8)).apply(l_channel)
        normalized = cv2.cvtColor(cv2.merge((l_channel, a_channel, b_channel)), cv2.COLOR_LAB2BGR)



        blurred = cv2.GaussianBlur(normalized, (0, 0), 1.1)
        working = cv2.addWeighted(normalized, 1.16, blurred, -0.16, 0)
    except Exception:
        pass

    h, w = working.shape[:2]
    if w > max_width:
        scale = max_width / float(w)
        working = cv2.resize(
            working,
            (max_width, max(1, int(round(h * scale)))),
            interpolation=cv2.INTER_AREA,
        )
    return working


def image_data_url(image: np.ndarray, quality: int = 95) -> str | None:
    if image is None or image.size == 0:
        return None
    try:
        ok, encoded = cv2.imencode(
            ".jpg",
            image,
            [int(cv2.IMWRITE_JPEG_QUALITY), int(max(70, min(100, quality)))],
        )
        if not ok:
            return None
        import base64
        return "data:image/jpeg;base64," + base64.b64encode(encoded.tobytes()).decode("ascii")
    except Exception:
        return None


def document_preview_data_url(file_path: str | Path, max_width: int = 1600) -> str | None:
    path = Path(file_path)
    try:
        if path.suffix.lower() == ".pdf":
            image = load_pdf_page_image_high_res(path, 0)
        else:
            raw = np.fromfile(str(path), dtype=np.uint8)
            image = cv2.imdecode(raw, cv2.IMREAD_COLOR)
        if image is None:
            return None
        enhanced = enhance_document_image(image, max_width=max_width)
        return image_data_url(enhanced, quality=95)
    except Exception:
        return None
