from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.services.ai_fake_screener import run_ai_fake_document_screening

router = APIRouter(prefix="/api/ai-screening", tags=["AI Fake Document Screening"])

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}


def _delete_safely(path: Path) -> None:
    try:
        if path.exists() and path.is_file():
            path.unlink()
    except Exception as error:
        print("Unable to delete temporary AI-screening file:", error)


def _save_upload(upload: UploadFile) -> Path:
    filename = Path(upload.filename or "upload.png").name
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Only image files (JPG, PNG, WEBP, BMP, TIFF) are supported by the AI fake-document screener.",
        )

    temp = Path(tempfile.mkstemp(suffix=extension, prefix="drishti_ai_")[1])
    with open(temp, "wb") as handle:
        while True:
            chunk = upload.file.read(1024 * 1024)
            if not chunk:
                break
            handle.write(chunk)
    return temp


@router.post("/analyze")
async def analyze_ai_fake_document(
    file: UploadFile = File(...),
):
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="An image file is required.")

    temp_path = None
    try:
        temp_path = _save_upload(file)
        report = run_ai_fake_document_screening(temp_path)


        ela = report.get("modules", {}).get("ela", {})
        ela_heatmap_url = ela.pop("heatmap_png_b64", None)
        return {
            "success": True,
            "ts": __import__("time").time(),
            **report,
        }
    except HTTPException:
        raise
    except Exception as error:
        import traceback

        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"AI fake-document screening failed: {error}",
        )
    finally:
        if temp_path is not None:
            _delete_safely(temp_path)


@router.post("/heatmap")
async def ai_screening_heatmap(
    file: UploadFile = File(...),
):
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="An image file is required.")

    temp_path = None
    try:
        temp_path = _save_upload(file)
        from app.services.forensics_ela import compute_ela

        ela = compute_ela(temp_path)
        return {
            "success": True,
            "score": ela.get("score"),
            "risk_level": ela.get("risk_level"),
            "summary": ela.get("summary"),
            "heatmap_png_b64": ela.get("heatmap_png_b64"),
            "heatmap_data_url": ela.get("heatmap_data_url"),
        }
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"ELA heatmap failed: {error}")
    finally:
        if temp_path is not None:
            _delete_safely(temp_path)
