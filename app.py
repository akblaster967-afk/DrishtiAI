from __future__ import annotations

import base64
import io
import sys
from pathlib import Path


_BACKEND_DIR = Path(__file__).resolve().parent / "backend"
_BACKEND_STR = str(_BACKEND_DIR)
if _BACKEND_STR not in sys.path:
    sys.path.insert(0, _BACKEND_STR)

import tempfile

import cv2
import numpy as np
import streamlit as st
from PIL import Image

from app.services.c2pa_checker import check_c2pa
from app.services.deep_learning_detector import detect_ai_generated
from app.services.exif_checker import inspect_exif
from app.services.forensics_ela import compute_ela
from app.services.ocr_forensics import analyze_ocr_forensics

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}

MAX_UPLOAD_MB = 10


def _save_upload(uploaded) -> str:
    filename = Path(uploaded.name).name
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError(
            "Unsupported file type. Please upload a JPG, PNG, WEBP, BMP or TIFF image."
        )
    temp = tempfile.NamedTemporaryFile(
        suffix=extension,
        prefix="drishti_ai_",
        delete=False,
    )
    temp.write(uploaded.getbuffer())
    temp.close()
    return temp.name


def _b64_to_image(b64: str) -> Image.Image:
    raw = base64.b64decode(b64.split(",", 1)[-1])
    return Image.open(io.BytesIO(raw))


def _status_card(label: str, status: str, detail: str, data_url: str | None = None):
    color = {
        "PASS": "#16a34a",
        "REVIEW": "#d97706",
        "FAIL": "#dc2626",
        "LOW": "#16a34a",
        "MEDIUM": "#d97706",
        "HIGH": "#dc2626",
        "AVAILABLE": "#16a34a",
        "UNAVAILABLE": "#64748b",
    }.get(status.upper(), "#64748b")

    with st.container(border=True):
        cols = st.columns([1, 4])
        with cols[0]:
            if data_url:
                try:
                    st.image(_b64_to_image(data_url), use_container_width=True)
                except Exception:
                    st.markdown(
                        f'<div style="width:48px;height:48px;border-radius:8px;'
                        f'background:{color};color:#fff;display:flex;align-items:center;'
                        f'justify-content:center;font-weight:700;font-size:18px">'
                        f'{status[0]}</div>',
                        unsafe_allow_html=True,
                    )
            else:
                st.markdown(
                    f'<div style="width:48px;height:48px;border-radius:8px;'
                    f'background:{color};color:#fff;display:flex;align-items:center;'
                    f'justify-content:center;font-weight:700;font-size:18px">'
                    f'{status[0] or "?"}</div>',
                    unsafe_allow_html=True,
                )
        with cols[1]:
            st.markdown(f"**{label}** — `{status}`")
            st.caption(detail)


def _run_screening(file_path: str) -> dict:
    return {
        "c2pa": check_c2pa(file_path),
        "exif": inspect_exif(file_path),
        "ela": compute_ela(file_path),
        "ocr": analyze_ocr_forensics(file_path),
        "dl": detect_ai_generated(file_path),
    }


def _trust_score(modules: dict) -> dict:

    caps = {"c2pa": 25, "exif": 20, "ela": 22, "ocr": 20, "dl": 30}
    points = 0

    c2pa = modules["c2pa"]
    if c2pa.get("is_ai_generated_flag"):
        points -= caps["c2pa"]
    elif c2pa.get("has_c2pa") and c2pa.get("issuer_name"):
        points += 15

    exif = modules["exif"]
    if exif.get("ai_software_hits"):
        points -= caps["exif"]
    elif exif.get("editor_software_hits"):
        points -= 10

    ela_status = str(modules["ela"].get("risk_level", "")).upper()
    if ela_status == "HIGH":
        points -= caps["ela"]
    elif ela_status == "MEDIUM":
        points -= 11

    ocr = modules["ocr"]
    if str(ocr.get("risk_level", "")).upper() == "HIGH":
        points -= caps["ocr"]
    else:
        points -= min(8, 2 * int(ocr.get("typo_count") or 0))
        points -= min(6, 3 * len(ocr.get("missing_fields") or []))

    dl_ai = modules["dl"].get("ai_score")
    if dl_ai is not None:
        if dl_ai >= 80:
            points -= caps["dl"]
        elif dl_ai >= 60:
            points -= 18
        elif dl_ai >= 45:
            points -= 8
        elif dl_ai <= 20:
            points += 10

    trust = int(max(0, min(100, 100 + points)))
    green = trust >= 70
    return {
        "trust": trust,
        "verdict": "AUTHENTIC / REAL" if green else "AI-GENERATED / TAMPERED",
        "color": "green" if green else "red",
        "points": points,
    }


st.set_page_config(
    page_title="Drishti AI - AI/Fake Document Screener",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.title("🛡️ Drishti AI — AI & Fake Document Screener")
st.caption(
    "C2PA credentials · EXIF · Error Level Analysis · OCR forensics · "
    "Deep-learning AI probability — with a weighted Trust Score verdict."
)

left, right = st.columns([2, 1])
with left:
    uploaded = st.file_uploader(
        "Drag and drop an image (JPG, PNG)",
        type=["jpg", "jpeg", "png", "webp", "bmp", "tif", "tiff"],
    )
with right:
    if uploaded:
        mib = uploaded.size / (1024 * 1024)
        if mib > MAX_UPLOAD_MB:
            st.error(f"File is {mib:.1f} MB. Limit is {MAX_UPLOAD_MB} MB.")
            uploaded = None

if uploaded:
    try:
        file_path = _save_upload(uploaded)
    except ValueError as error:
        st.error(str(error))
        file_path = None

    if file_path:
        with st.spinner("Running the five-module AI/fake-document screening..."):
            modules = _run_screening(file_path)
            trust = _trust_score(modules)

        try:
            original = Image.open(file_path)
        except Exception:
            original = None




        st.subheader("Original Image vs ELA Heatmap")
        ela_col, heat_col = st.columns(2)
        with ela_col:
            if original is not None:
                st.image(original, caption="Original Image", use_container_width=True)
            else:
                st.warning("Could not open the original image.")
        with heat_col:
            heat_b64 = modules["ela"].get("heatmap_png_b64")
            if heat_b64:
                st.image(
                    _b64_to_image(heat_b64),
                    caption=f"ELA Heatmap — score {modules['ela'].get('score')} / 100",
                    use_container_width=True,
                )
            else:
                st.info("ELA heatmap unavailable.")




        st.subheader("Screening Status Cards")

        c2pa = modules["c2pa"]
        c2pa_status = "AVAILABLE" if c2pa.get("available") else "UNAVAILABLE"
        if c2pa.get("is_ai_generated_flag"):
            c2pa_label = "AI CLAIM"
        elif c2pa.get("has_c2pa") and c2pa.get("issuer_name"):
            c2pa_label = "SIGNED"
        else:
            c2pa_label = "NO MANIFEST"
        _status_card(
            "C2PA Credentials",
            c2pa_label,
            c2pa.get("reason") or f"Signers: {', '.join(c2pa.get('claim_signers', []) or []) or 'none'}.",
            c2pa.get("preview"),
        )

        exif = modules["exif"]
        _status_card(
            "EXIF Metadata",
            exif.get("risk_level", "LOW"),
            exif.get("summary", "") + f" ({exif.get('tag_count', 0)} tags)",
            exif.get("preview"),
        )

        ocr = modules["ocr"]
        ocr_detail = (
            f"{ocr.get('typo_count', 0)} typo/hallucination flag(s); "
            f"missing fields: {', '.join(ocr.get('missing_fields', []) or []) or 'none'}."
            if ocr.get("available")
            else ocr.get("reason", "OCR unavailable.")
        )
        _status_card(
            "OCR Typo Warnings",
            ocr.get("risk_level", "UNAVAILABLE"),
            ocr_detail,
        )

        dl = modules["dl"]
        dl_detail = (
            f"AI probability {dl.get('ai_score')}% · Real probability "
            f"{dl.get('real_score')}% · Method: {dl.get('method', 'n/a')}."
            if dl.get("ai_score") is not None
            else dl.get("reason", "Deep-learning detector unavailable.")
        )
        _status_card(
            "Deep-Learning AI Probability",
            "HIGH" if (dl.get("ai_score") or 0) >= 60 else ("LOW" if (dl.get("ai_score") or 0) < 45 else "MEDIUM"),
            dl_detail,
        )




        st.subheader("Overall Trust Score")
        col_score, col_verdict = st.columns([1, 2])
        with col_score:
            st.metric(
                "Trust Score",
                f"{trust['trust']}%",
                delta=f"{trust['points']:+d} points",
            )
            st.progress(trust["trust"] / 100)
        with col_verdict:
            banner_color = "green" if trust["color"] == "green" else "red"
            st.markdown(
                f"""
                <div style="border:2px solid {banner_color};border-radius:14px;
                            padding:22px;text-align:center;
                            background:{'#f0fdf4' if trust['color'] == 'green' else '#fef2f2'};
                            border-left:8px solid {banner_color};">
                  <div style="font-size:15px;color:#475569">FINAL VERDICT</div>
                  <div style="font-size:26px;font-weight:800;color:{banner_color}">
                    {trust['verdict']}
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )




        with st.expander("C2PA manifest details"):
            st.json(c2pa)
        with st.expander("EXIF evidence"):
            st.json(exif)
        with st.expander("ELA scoring"):
            st.json(
                {
                    k: modules["ela"][k]
                    for k in ("score", "risk_level", "summary", "ela_variance", "ela_mean", "hot_region_ratio", "analyzed_shape")
                    if k in modules["ela"]
                }
            )
        with st.expander("OCR forensics - extracted text & mandatory fields"):
            if ocr.get("available"):
                st.text(ocr.get("text", "")[:4000] or "(no text extracted)")
                if ocr.get("mandatory_fields"):
                    st.table(
                        [
                            {
                                "Field": item.get("field"),
                                "Status": item.get("status"),
                                "Value": item.get("value"),
                            }
                            for item in ocr["mandatory_fields"]
                        ]
                    )
            else:
                st.info(ocr.get("reason", "OCR unavailable."))
        with st.expander("Deep-learning detector"):
            st.json(
                {
                    k: dl[k]
                    for k in ("ai_score", "real_score", "model", "method", "fine_tuned", "available", "note")
                    if k in dl
                }
            )
else:
    st.info("⬆️ Drag and drop an image to begin the AI/fake-document screening.")
    st.markdown(
        """
        **Screening modules**
        - **C2PA Credentials** — reads provenance manifests signed by real
          content-credential tools (Adobe, OpenAI, Midjourney, ...).
        - **EXIF Metadata** — camera tags + editor/AI software markers.
        - **ELA** — Error Level Analysis heatmap for spliced/edited regions.
        - **OCR Forensics** — hallucinated spellings, broken glyphs and
          mandatory-field regex checks (Roll Number, ERP ID, DOB, Aadhaar, PAN).
        - **Deep Learning** — CNN (MobileNetV3/ResNet18) AI-vs-Real score.

        > **Honest limitation:** suspicious signals raise review flags; absence
        > of metadata (e.g. cropped screenshots) is *not* treated as proof of
        > forgery. The Trust Score is a weighted screening helper, not a legal
        > authenticity certificate.
        """
    )
