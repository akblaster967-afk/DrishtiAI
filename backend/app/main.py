import asyncio
import time
from pathlib import Path
import re

import base64
import hashlib
import hmac
import json
import os
import secrets
import shutil
import tempfile
import smtplib
import cv2
import numpy as np
from dotenv import load_dotenv
from email.message import EmailMessage
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from fastapi import (
    FastAPI,
    UploadFile,
    File,
    HTTPException,
    Form,
    Request,
    Response,
    BackgroundTasks,
)

from pydantic import BaseModel, Field

from fastapi.responses import (
    JSONResponse,
    FileResponse,
    RedirectResponse,
)

from pdf2image import convert_from_path


load_dotenv(
    dotenv_path=Path(__file__).resolve().parent.parent / ".env",
)



from app.database import (
    init_database,
    create_audit_event,
    get_audit_logs,
    create_identity_verification,
    normalize_document_number,
    generate_unique_user_id,
    find_verified_user,
    create_verified_user,
    find_document_by_number,
    find_identity_registry_by_number,
    register_identity_number,
    find_user_document_by_name_and_type,
    delete_user_document,
    add_user_document,
    increment_user_document_reverification,
    get_user_documents,
    search_verified_documents,
    find_verified_user_by_email,
    create_password_reset_token,
    find_password_reset_token,
    mark_password_reset_token_used,
    create_auth_event,
    update_verified_user,
    create_otp_record,
    find_active_otp,
    mark_otp_used,
    add_face_capture,
    get_face_captures,
    get_face_capture,
)



from app.services.ocr import (
    extract_text_from_image,
    extract_text_from_pdf,
)

from app.services.field_extractor import (
    extract_fields,
    _extract_label_anchor_fields,
    reference_fields_for_document,
)

from app.services.identity_checker import (
    compare_identity,
    get_applicable_identity_fields,
)

from app.services.quality_analyzer import (
    analyze_image_quality,
)

from app.services.indicator_analyzer import (
    analyze_indicators,
)



from app.services.risk_engine import (
    calculate_risk_score,
)

from app.services.document_consistency import (
    check_document_consistency,
)
from app.services.reference_comparator import (
    build_reference_comparison,
)
from app.services.document_specific_extractor import (
    extract_document_specific_fields,
)
from app.services.cross_document_consistency import (
    build_cross_document_consistency,
)
from app.services.ai_document_detector import (
    analyze_ai_document,
)
from app.services.document_verification_engine import (
    build_document_verification,
)
from app.services.security_feature_analyzer import (
    analyze_security_features,
)

from app.services.face_matcher import (
    FaceComparisonError,
    compare_document_and_capture,
    validate_camera_capture_bytes,
    validate_liveness_frames,
)

from app.services.pdf_images import document_preview_data_url



app = FastAPI(
    title="Drishti AI API",
    description=(
        "AI-Based Fake Identity & Document Screening"
    ),
    version="5.0.0",
)



init_database()


class RegisterRequest(BaseModel):
    fullName: str = Field(..., min_length=1, max_length=120)
    email: str = Field(..., min_length=3, max_length=254)
    password: str = Field(..., min_length=1, max_length=10)
    verificationToken: str = Field(..., min_length=1, max_length=1024)


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    password: str = Field(..., min_length=1, max_length=10)


class ResendVerificationRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)


class ForgotPasswordRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)


class OTPRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    otp: str = Field(..., min_length=6, max_length=6)


class VerificationTokenRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    verificationToken: str = Field(..., min_length=1, max_length=1024)


class ResetPasswordRequest(BaseModel):
    token: str = Field(..., min_length=1, max_length=512)
    password: str = Field(..., min_length=1, max_length=10)



BASE_DIR = (
    Path(__file__)
    .resolve()
    .parent
    .parent
)

UPLOAD_DIR = (
    BASE_DIR /
    "uploads"
)

UPLOAD_DIR.mkdir(
    parents=True,
    exist_ok=True,
)



ALLOWED_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".pdf",
}

MAX_FILE_SIZE = (
    8 * 1024 * 1024
)


DOCUMENT_VERIFIED_RISK_LIMIT = 25
DOCUMENT_STORE_REJECT_LIMIT = 50



def _effective_ocr_confidence(raw_confidence, specialized_fields, id_type):
    try:
        raw = float(raw_confidence or 0.0)
    except (TypeError, ValueError):
        raw = 0.0
    field_conf = (specialized_fields or {}).get("fieldConfidence") or {}
    if not isinstance(field_conf, dict):
        return round(max(0.0, min(100.0, raw)), 2)
    normalized = str(id_type or "").strip().upper()
    required_by_type = {
        "AADHAAR": ("name", "dob", "gender", "document_number"),
        "PAN": ("name", "document_number"),
        "PASSPORT": ("name", "document_number", "nationality"),
        "VISA": ("name", "document_number", "dob"),
        "DRIVING_LICENSE": ("name", "document_number"),
        "COLLEGE_ID": ("name", "document_number"),
    }
    keys = required_by_type.get(normalized, tuple(field_conf.keys()))
    values = []
    for key in keys:
        try:
            value_conf = float(field_conf.get(key) or 0)
        except (TypeError, ValueError):
            value_conf = 0.0
        if value_conf > 0:
            values.append(value_conf)

    if normalized == "AADHAAR":
        for key in ("father_name", "address"):
            try:
                value_conf = float(field_conf.get(key) or 0)
            except (TypeError, ValueError):
                value_conf = 0.0
            if value_conf > 0:
                values.append(value_conf * 0.5)
    if len(values) >= 2:
        weighted = sum(values) / len(values)
        return round(max(0.0, min(100.0, max(raw, weighted))), 2)
    return round(max(0.0, min(100.0, raw)), 2)



USER_CREATION_RISK_LIMIT = DOCUMENT_STORE_REJECT_LIMIT


FACE_CAPTURE_DOCUMENT_TYPES = {
    "PASSPORT",
    "VISA",
    "AADHAAR",
    "PAN",
    "DRIVING_LICENSE",
    "COLLEGE_ID",
}
FACE_MATCH_THRESHOLD = 62.0



SESSION_COOKIE_NAME = (
    "drishti_ai_session"
)

# Never fall back to a predictable hard-coded secret. Production should set
# VERIFYSHIELD_SESSION_SECRET explicitly; local runs get a random per-process
# secret so a missing environment variable cannot silently weaken sessions.
SESSION_SECRET = os.getenv(
    "VERIFYSHIELD_SESSION_SECRET"
) or secrets.token_urlsafe(32)



PASSWORD_HASHER = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=2,
)

AUTH_FRONTEND_URL = os.getenv(
    "VERIFYSHIELD_FRONTEND_URL",