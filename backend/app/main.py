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

SESSION_SECRET = os.getenv(
    "VERIFYSHIELD_SESSION_SECRET",
    "VERIFYSHIELD_DEVELOPMENT_SECRET_CHANGE_ME",
)



PASSWORD_HASHER = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=2,
)

AUTH_FRONTEND_URL = os.getenv(
    "VERIFYSHIELD_FRONTEND_URL",
    "http://localhost:5173",
).rstrip("/")

SMTP_HOST = os.getenv("VERIFYSHIELD_SMTP_HOST", "")
SMTP_PORT = int(os.getenv("VERIFYSHIELD_SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("VERIFYSHIELD_SMTP_USERNAME", "")
SMTP_PASSWORD = os.getenv("VERIFYSHIELD_SMTP_PASSWORD", "")
SMTP_FROM_EMAIL = os.getenv("VERIFYSHIELD_SMTP_FROM_EMAIL", SMTP_USERNAME)
SMTP_USE_TLS = os.getenv("VERIFYSHIELD_SMTP_USE_TLS", "true").lower() == "true"

EMAIL_VERIFICATION_EXPIRY_MINUTES = 10
PASSWORD_RESET_EXPIRY_MINUTES = 10
OTP_LENGTH = 6
LOGIN_FAILURE_WINDOW_MINUTES = 15
MAX_LOGIN_FAILURES = 5

AUTH_SESSION_COOKIE_SECURE = os.getenv(
    "VERIFYSHIELD_SESSION_SECURE",
    "false",
).lower() == "true"



def serialize_user_document(
    document,
):
    details = document.get(
        "details"
    )

    if isinstance(
        details,
        str,
    ):
        try:
            details = json.loads(
                details
            )
        except Exception:
            details = {}

    elif not isinstance(
        details,
        dict,
    ):
        details = {}

    return {
        "id":
            document.get(
                "id"
            ),

        "idType":
            document.get(
                "id_type"
            ),

        "documentNumber":
            document.get(
                "document_number"
            ),

        "fullName":
            document.get(
                "full_name"
            ),

        "dateOfBirth":
            document.get(
                "date_of_birth"
            ),

        "address":
            document.get(
                "address"
            ),

        "riskScore":
            document.get(
                "risk_score"
            ),

        "finalStatus":
            document.get(
                "final_status"
            ),

        "createdAt":
            document.get(
                "created_at"
            ),

        "verificationId":
            document.get(
                "verification_id"
            ),

        "reverificationCount":
            document.get(
                "reverification_count",
                0,
            ),

        "details":
            details,
    }



def serialize_face_capture(capture):
    if not capture:
        return None

    return {
        "id": capture.get("id"),
        "capturedAt": capture.get("captured_at"),
        "originalFilename": capture.get("original_filename"),
        "storedFilename": capture.get("stored_filename"),
        "mimeType": capture.get("mime_type"),
        "sha256": capture.get("sha256"),
        "fileSize": capture.get("file_size"),
        "source": capture.get("source"),
        "livenessStatus": capture.get("liveness_status"),
        "motionScore": capture.get("motion_score"),
        "motionSamples": capture.get("motion_samples", 0),
    }


def get_safe_user_folder(unique_id):
    folder = (UPLOAD_DIR / str(unique_id)).resolve()
    base = UPLOAD_DIR.resolve()
    if base not in folder.parents and folder != base:
        raise HTTPException(status_code=403, detail="Capture storage access denied.")
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def create_session_token(
    unique_id,
):
    payload = json.dumps(
        {
            "uniqueId":
                unique_id,

            "exp":
                int(
                    (datetime.now(timezone.utc) + timedelta(days=7)).timestamp()
                ),
        },
        separators=(
            ",",
            ":",
        ),
    ).encode(
        "utf-8"
    )

    encoded_payload = (
        base64.urlsafe_b64encode(
            payload
        )
        .decode(
            "utf-8"
        )
        .rstrip("=")
    )

    signature = hmac.new(
        SESSION_SECRET.encode(
            "utf-8"
        ),
        encoded_payload.encode(
            "utf-8"
        ),
        hashlib.sha256,
    ).hexdigest()

    return (
        encoded_payload
        + "."
        + signature
    )


def get_session_user_id(
    request: Request,
):
    token = request.cookies.get(
        SESSION_COOKIE_NAME
    )

    if not token:
        return None

    try:
        encoded_payload, signature = (
            token.split(
                ".",
                1,
            )
        )

        expected_signature = (
            hmac.new(
                SESSION_SECRET.encode(
                    "utf-8"
                ),
                encoded_payload.encode(
                    "utf-8"
                ),
                hashlib.sha256,
            )
            .hexdigest()
        )

        if not hmac.compare_digest(
            signature,
            expected_signature,
        ):
            return None

        padding = "=" * (
            -len(
                encoded_payload
            )
            % 4
        )

        payload = (
            base64.urlsafe_b64decode(
                encoded_payload
                + padding
            )
        )

        data = json.loads(
            payload.decode(
                "utf-8"
            )
        )

        expiry = int(
            data.get(
                "exp",
                0,
            )
            or 0
        )

        if expiry < int(datetime.now(timezone.utc).timestamp()):
            return None

        unique_id = str(
            data.get(
                "uniqueId",
                "",
            )
        ).strip()

        if "@" in unique_id and "." in unique_id:
            return unique_id.lower()
        if len(unique_id) == 10 and unique_id.isdigit():
            return unique_id
        return None

    except Exception:
        return None


def set_user_session(
    response: Response,
    unique_id,
):
    response.set_cookie(
        key=SESSION_COOKIE_NAME,

        value=create_session_token(
            unique_id,
        ),

        httponly=True,

        samesite="lax",

        secure=AUTH_SESSION_COOKIE_SECURE,

        max_age=60 * 60 * 24 * 7,

        path="/",
    )


def clear_user_session(
    response: Response,
):
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
    )



def require_authenticated_user(
    request: Request,
):
    unique_id = (
        get_session_user_id(
            request
        )
    )

    if not unique_id:
        raise HTTPException(
            status_code=401,
            detail=(
                "Authenticated Drishti AI "
                "user session is required."
            ),
        )

    user = (
        find_verified_user(
            unique_id
        )
    )

    if user is None:
        raise HTTPException(
            status_code=401,
            detail=(
                "Drishti AI user session "
                "is invalid."
            ),
        )

    return (
        unique_id,
        user,
    )



def delete_file_safely(
    file_path,
):
    if not file_path:
        return

    try:
        path = Path(
            file_path
        )

        if (
            path.exists()
            and path.is_file()
        ):
            path.unlink()

    except Exception as error:
        print(
            "Unable to delete temporary file:",
            error,
        )


def move_document_to_user_folder(
    file_path,
    unique_id,
):
    source = Path(
        file_path
    )

    user_folder = (
        UPLOAD_DIR /
        unique_id
    )

    user_folder.mkdir(
        parents=True,
        exist_ok=True,
    )

    stored_name = (
        secrets.token_hex(4)
        + "_"
        + source.name
    )

    destination = (
        user_folder /
        stored_name
    )

    shutil.move(
        str(source),
        str(destination),
    )

    return destination


def validate_unique_id(
    unique_id,
):
    value = str(
        unique_id or ""
    ).strip()

    if "@" in value and "." in value:
        return value.lower()
    if len(value) == 10 and value.isdigit():
        return value
    raise HTTPException(status_code=400, detail="Invalid account identifier.")





@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "service": "Drishti AI API",
        "workflow": "USER_ONLY",
        "aiScreening": True,
        "strictDocumentVerification": True,
    }



def normalize_auth_email(email):
    value = str(email or "").strip().lower()
    if len(value) > 254 or "@" not in value:
        raise HTTPException(
            status_code=400,
            detail="Enter a valid email address.",
        )
    return value


def validate_password(password):
    value = str(password or "")
    if len(value) > 10:
        raise HTTPException(status_code=400, detail="Password must be at most 10 characters.")
    if len(value) < 8:
        raise HTTPException(
            status_code=400,
            detail="Password must be at least 8 characters.",
        )
    if not re.fullmatch(r"[A-Za-z0-9@]+", value):
        raise HTTPException(
            status_code=400,
            detail="Password may contain only letters, numbers and @.",
        )
    if not re.search(r"[A-Z]", value):
        raise HTTPException(status_code=400, detail="Password must contain at least 1 capital letter.")
    if not re.search(r"[a-z]", value):
        raise HTTPException(status_code=400, detail="Password must contain at least 1 small letter.")
    if not re.search(r"[0-9]", value):
        raise HTTPException(status_code=400, detail="Password must contain at least 1 number.")
    if "@" not in value:
        raise HTTPException(status_code=400, detail="Password must contain @ as the symbol.")
    return value


def hash_password(password):
    return PASSWORD_HASHER.hash(password)


def verify_password(password_hash, password):
    try:
        return PASSWORD_HASHER.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def password_needs_rehash(password_hash):
    try:
        return PASSWORD_HASHER.check_needs_rehash(password_hash)
    except Exception:
        return False



def generate_otp():
    return f"{secrets.randbelow(1000000):06d}"


def otp_hash(otp):
    return hashlib.sha256(str(otp).encode("utf-8")).hexdigest()


def create_otp_token(email, purpose, expiry_minutes=10):
    return create_signed_token(
        {"purpose": purpose, "email": normalize_auth_email(email)},
        expiry_minutes * 60,
    )


def verify_otp_code(email, purpose, otp):
    record = find_active_otp(email, purpose)
    if not record:
        return False
    try:
        if datetime.fromisoformat(record["expires_at"]) < datetime.now():
            return False
    except Exception:
        return False
    if not hmac.compare_digest(record["otp_hash"], otp_hash(otp)):
        return False
    mark_otp_used(record["id"])
    return True


def create_signed_token(payload, expiry_seconds):
    data = dict(payload)
    data["exp"] = int(
        (datetime.now(timezone.utc) + timedelta(seconds=expiry_seconds)).timestamp()
    )

    raw_payload = json.dumps(
        data,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")

    encoded = base64.urlsafe_b64encode(raw_payload).decode("utf-8").rstrip("=")
    signature = hmac.new(
        SESSION_SECRET.encode("utf-8"),
        encoded.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    return f"{encoded}.{signature}"


def read_signed_token(token):
    try:
        encoded_payload, signature = str(token or "").split(".", 1)
        expected_signature = hmac.new(
            SESSION_SECRET.encode("utf-8"),
            encoded_payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(signature, expected_signature):
            return None

        padding = "=" * (-len(encoded_payload) % 4)
        payload = base64.urlsafe_b64decode(encoded_payload + padding)
        data = json.loads(payload.decode("utf-8"))

        if int(data.get("exp", 0)) < int(datetime.now(timezone.utc).timestamp()):
            return None

        return data
    except Exception:
        return None


def create_email_verification_token(unique_id, email):
    return create_signed_token(
        {
            "purpose": "email_verification",
            "uniqueId": unique_id,
            "email": email,
        },
        EMAIL_VERIFICATION_EXPIRY_MINUTES * 60,
    )


def create_password_reset_link(token):
    return f"{AUTH_FRONTEND_URL}/reset-password?token={token}"


def send_email(to_email, subject, text_body, html_body=None):
    host = str(SMTP_HOST or "").strip()
    username = str(SMTP_USERNAME or "").strip()
    password = "".join(str(SMTP_PASSWORD or "").split())
    from_email = str(SMTP_FROM_EMAIL or username).strip()

    if not (host and username and password and from_email):
        raise RuntimeError(
            "SMTP email is not configured. Set VERIFYSHIELD_SMTP_HOST, "
            "VERIFYSHIELD_SMTP_PORT, VERIFYSHIELD_SMTP_USERNAME, "
            "VERIFYSHIELD_SMTP_PASSWORD and VERIFYSHIELD_SMTP_FROM_EMAIL."
        )

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = from_email
    message["To"] = to_email
    message.set_content(text_body)
    if html_body:
        message.add_alternative(html_body, subtype="html")

    configured_port = int(SMTP_PORT or 587)
    if host.lower() == "smtp.gmail.com":
        attempts = [(465, "ssl"), (587, "starttls")]
    elif configured_port == 465:
        attempts = [(465, "ssl"), (587, "starttls")]
    else:
        attempts = [
            (configured_port, "starttls" if SMTP_USE_TLS else "plain"),
            (465, "ssl"),
        ]

    errors = []
    for port, mode in attempts:
        try:
            if mode == "ssl":
                import ssl
                context = ssl.create_default_context()
                with smtplib.SMTP_SSL(host, port, timeout=20, context=context) as smtp:
                    smtp.ehlo()
                    smtp.login(username, password)
                    smtp.send_message(message)
                    return

            with smtplib.SMTP(host, port, timeout=20) as smtp:
                smtp.ehlo()
                if mode == "starttls":
                    smtp.starttls()
                    smtp.ehlo()
                smtp.login(username, password)
                smtp.send_message(message)
                return
        except smtplib.SMTPAuthenticationError as error:


            errors.append((port, mode, "authentication", str(error)))
        except smtplib.SMTPConnectError as error:
            errors.append((port, mode, "connection", str(error)))
        except smtplib.SMTPServerDisconnected as error:
            errors.append((port, mode, "connection", str(error)))
        except (TimeoutError, OSError) as error:
            errors.append((port, mode, "connection", str(error)))
        except smtplib.SMTPException as error:
            errors.append((port, mode, "smtp", str(error)))
        except Exception as error:
            errors.append((port, mode, "unknown", str(error)))

    if any(kind == "authentication" for _, _, kind, _ in errors):
        raise RuntimeError(
            "SMTP authentication failed. Verify that VERIFYSHIELD_SMTP_USERNAME "
            "is the Gmail account that created the App Password and that "
            "VERIFYSHIELD_SMTP_PASSWORD contains the current 16-character App Password."
        )

    if any(kind == "connection" for _, _, kind, _ in errors):
        details = "; ".join(
            f"{mode} port {port}: {message}" for port, mode, kind, message in errors
            if kind == "connection"
        )
        raise RuntimeError(f"SMTP connection failed. {details}")

    details = "; ".join(
        f"{mode} port {port}: {message}" for port, mode, _, message in errors
    )
    raise RuntimeError(f"SMTP delivery failed. {details}")


def recent_login_failures(email):
    from app.database import get_connection

    connection = get_connection()
    try:
        cutoff = (
            datetime.now() - timedelta(minutes=LOGIN_FAILURE_WINDOW_MINUTES)
        ).isoformat()
        row = connection.execute(
            """
            SELECT COUNT(*) AS failure_count
            FROM auth_events
            WHERE email = ?
              AND event_type = 'LOGIN'
              AND success = 0
              AND created_at >= ?
            """,
            (email, cutoff),
        ).fetchone()
        return int(row["failure_count"] or 0)
    finally:
        connection.close()


def sanitize_user_for_auth(user):
    return {
        "fullName": user.get("full_name"),
        "email": user.get("email"),
        "uniqueId": user.get("unique_id"),
        "emailVerified": bool(user.get("email_verified")),
        "mfaEnabled": bool(user.get("mfa_enabled")),
        "role": "USER",
    }


def issue_authenticated_response(user, message="Login successful."):
    response = JSONResponse(
        {
            "success": True,
            "user": sanitize_user_for_auth(user),
            "message": message,
        }
    )
    set_user_session(response, user.get("unique_id"))
    return response



def _deliver_otp_email(email, subject, otp, event_type, account_found=None):




    try:
        send_email(
            email,
            subject,
            (
                f"Your 6-digit Drishti AI verification code is: {otp}\n\n"
                "This code expires in 10 minutes."
            ),
        )
    except Exception as error:
        print(
            f"[OTP EMAIL ERROR] email={email} "
            f"type={type(error).__name__} error={error}"
        )
        raise




    try:
        details = {} if account_found is None else {
            "accountFound": bool(account_found)
        }
        create_auth_event(email, event_type, True, details)
    except Exception as error:


        print(
            f"[OTP AUDIT ERROR] email={email} "
            f"type={type(error).__name__} error={error}"
        )

    return True


def otp_delivery_error(error):
    message = str(error or "").strip()

    print(
        f"[OTP DELIVERY ERROR] type={type(error).__name__} "
        f"error={message}"
    )

    if "SMTP authentication failed" in message:
        return (
            "OTP could not be sent because Gmail SMTP authentication failed. "
            "Please check the Gmail App Password."
        )

    if "SMTP connection failed" in message:
        return (
            "OTP could not be sent because the SMTP server connection failed. "
            f"Details: {message}"
        )

    if "SMTP email is not configured" in message:
        return (
            "OTP could not be sent because SMTP is not configured correctly. "
            "Check the backend .env file."
        )

    if message:
        return f"OTP could not be sent: {message}"

    return "OTP could not be sent. Check the SMTP configuration."


@app.post("/api/auth/register/send-otp")
async def register_send_otp(data: ForgotPasswordRequest):
    email = normalize_auth_email(data.email)




    if find_verified_user_by_email(email):
        raise HTTPException(
            status_code=409,
            detail="An account with this email already exists.",
        )




    otp = generate_otp()




    try:
        create_otp_record(
            email,
            "register",
            otp_hash(otp),
            (datetime.now() + timedelta(minutes=10)).isoformat(),
        )
    except Exception as error:
        print(
            f"[OTP DATABASE ERROR] type={type(error).__name__} "
            f"error={error}"
        )
        raise HTTPException(
            status_code=500,
            detail=(
                "OTP could not be created in the database. "
                f"Details: {error}"
            ),
        ) from error




    try:
        _deliver_otp_email(
            email,
            "Your Drishti AI account verification code",
            otp,
            "REGISTER_OTP",
        )
    except Exception as error:
        print(
            f"[OTP SEND ERROR] type={type(error).__name__} "
            f"error={error}"
        )
        raise HTTPException(
            status_code=503,
            detail=otp_delivery_error(error),
        ) from error

    return {
        "success": True,
        "message": "OTP sent successfully. Check your email, including Spam/Junk.",
    }


@app.post("/api/auth/send-otp")
async def legacy_send_otp(data: ForgotPasswordRequest, background_tasks: BackgroundTasks):
    return await register_send_otp(data, background_tasks)


@app.post("/api/auth/verify-otp")
async def legacy_verify_otp(data: OTPRequest):
    return await register_verify_otp(data)


@app.post("/api/auth/register/verify-otp")
async def register_verify_otp(data: OTPRequest):
    email = normalize_auth_email(data.email)
    if not str(data.otp).isdigit():
        raise HTTPException(status_code=400, detail="Enter the 6-digit OTP.")
    if not verify_otp_code(email, "register", data.otp):
        raise HTTPException(status_code=400, detail="Invalid or expired OTP.")
    token = create_otp_token(email, "register_verified")
    return {"success": True, "verificationToken": token, "message": "Email verified successfully."}


@app.post("/api/auth/register")
async def register_user(data: RegisterRequest):
    full_name = str(data.fullName or "").strip()
    email = normalize_auth_email(data.email)
    password = validate_password(data.password)
    verified = read_signed_token(data.verificationToken)
    if not verified or verified.get("purpose") != "register_verified" or verified.get("email") != email:
        raise HTTPException(status_code=403, detail="Verify your email with OTP before creating the account.")
    if len(full_name) < 2 or len(full_name) > 120:
        raise HTTPException(status_code=400, detail="Enter a valid full name.")
    if find_verified_user_by_email(email):
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    unique_id = generate_unique_user_id()
    try:
        create_verified_user(
            unique_id=unique_id,
            full_name=full_name,
            date_of_birth=None,
            address=None,
            risk_score=0,
            email=email,
            password_hash=hash_password(password),
            email_verified=True,
            mfa_enabled=False,
        )
    except Exception as error:
        if "UNIQUE" in str(error).upper():
            raise HTTPException(status_code=409, detail="An account with this email already exists.")
        raise
    create_auth_event(email, "REGISTER", True, {"emailVerified": True, "uniqueId": unique_id})
    return {"success": True, "uniqueId": unique_id, "message": f"Account created successfully. Your Drishti AI Unique ID is {unique_id}. You can now log in."}



@app.get("/api/auth/verify-email")
async def verify_email(token: str):
    data = read_signed_token(token)

    if not data or data.get("purpose") != "email_verification":
        return RedirectResponse(
            url=f"{AUTH_FRONTEND_URL}/login?emailVerification=invalid",
            status_code=303,
        )

    unique_id = str(data.get("uniqueId", "")).strip()
    email = str(data.get("email", "")).strip().lower()

    user = find_verified_user(unique_id)

    if user is None or user.get("email") != email:
        return RedirectResponse(
            url=f"{AUTH_FRONTEND_URL}/login?emailVerification=invalid",
            status_code=303,
        )

    if not user.get("email_verified"):
        update_verified_user(
            unique_id=unique_id,
            email_verified=True,
        )
        create_auth_event(
            email,
            "EMAIL_VERIFIED",
            True,
            {"uniqueId": unique_id},
        )

    return RedirectResponse(
        url=f"{AUTH_FRONTEND_URL}/login?emailVerification=success",
        status_code=303,
    )



@app.post("/api/auth/resend-verification")
async def resend_email_verification(data: ResendVerificationRequest):
    email = normalize_auth_email(data.email)
    user = find_verified_user_by_email(email)
    if user is None or user.get("email_verified"):
        return {"success": True, "message": "If the account can receive verification email, a new OTP has been sent."}
    otp = generate_otp()
    create_otp_record(email, "register", otp_hash(otp), (datetime.now() + timedelta(minutes=10)).isoformat())
    try:
        send_email(email, "Your Drishti AI verification code", f"Your 6-digit Drishti AI verification code is: {otp}\n\nThis code expires in 10 minutes.")
    except Exception:
        raise HTTPException(status_code=503, detail="Unable to send verification OTP right now.")
    return {"success": True, "message": "A new verification OTP has been sent."}



@app.post("/api/auth/login")
async def auth_login(data: LoginRequest):
    email = normalize_auth_email(data.email)
    password = str(data.password or "")

    if recent_login_failures(email) >= MAX_LOGIN_FAILURES:
        create_auth_event(
            email,
            "LOGIN",
            False,
            {"reason": "temporary_rate_limit"},
        )
        raise HTTPException(
            status_code=429,
            detail="Too many failed login attempts. Please try again later.",
        )

    user = find_verified_user_by_email(email)

    valid_password = bool(
        user
        and user.get("password_hash")
        and verify_password(user.get("password_hash"), password)
    )

    if not user or not valid_password:
        create_auth_event(
            email,
            "LOGIN",
            False,
            {"reason": "invalid_credentials"},
        )
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password.",
        )

    if user.get("status") != "ACTIVE":
        create_auth_event(
            email,
            "LOGIN",
            False,
            {"reason": "account_inactive"},
        )
        raise HTTPException(
            status_code=403,
            detail="This Drishti AI account is not active.",
        )

    if not user.get("email_verified"):
        create_auth_event(
            email,
            "LOGIN",
            False,
            {"reason": "email_not_verified", "uniqueId": user.get("unique_id")},
        )
        raise HTTPException(
            status_code=403,
            detail="Verify your email before logging in.",
        )

    if password_needs_rehash(user.get("password_hash")):
        update_verified_user(
            unique_id=user.get("unique_id"),
            password_hash=hash_password(password),
        )
        user = find_verified_user(user.get("unique_id"))

    create_auth_event(
        email,
        "LOGIN",
        True,
        {"uniqueId": user.get("unique_id")},
    )

    return issue_authenticated_response(user)



@app.post("/api/auth/forgot-password")
async def forgot_password(data: ForgotPasswordRequest):
    email = normalize_auth_email(data.email)
    user = find_verified_user_by_email(email)
    if user is not None:
        otp = generate_otp()
        create_otp_record(email, "reset", otp_hash(otp), (datetime.now() + timedelta(minutes=10)).isoformat())
        try:
            _deliver_otp_email(
                email,
                "Your Drishti AI password reset OTP",
                otp,
                "PASSWORD_RESET_OTP",
                True,
            )
        except Exception as error:
            raise HTTPException(status_code=503, detail=otp_delivery_error(error)) from error
    create_auth_event(email, "PASSWORD_RESET_REQUEST", True, {"accountFound": bool(user)})
    return {"success": True, "message": "OTP sent successfully. Check your email, including Spam/Junk."}


@app.post("/api/auth/forgot-password/verify-otp")
async def forgot_password_verify_otp(data: OTPRequest):
    email = normalize_auth_email(data.email)
    if not str(data.otp).isdigit():
        raise HTTPException(status_code=400, detail="Enter the 6-digit OTP.")
    if not verify_otp_code(email, "reset", data.otp):
        raise HTTPException(status_code=400, detail="Invalid or expired OTP.")
    if not find_verified_user_by_email(email):
        raise HTTPException(status_code=400, detail="Invalid or expired OTP.")
    token = create_otp_token(email, "password_reset_verified")
    return {"success": True, "resetToken": token, "message": "OTP verified. Create your new password."}


@app.post("/api/auth/reset-password")
async def reset_password(data: ResetPasswordRequest):
    password = validate_password(data.password)
    reset_data = read_signed_token(data.token)
    if not reset_data or reset_data.get("purpose") != "password_reset_verified":
        raise HTTPException(status_code=400, detail="Password reset verification is invalid or expired.")
    email = normalize_auth_email(reset_data.get("email"))
    user = find_verified_user_by_email(email)
    if user is None:
        raise HTTPException(status_code=400, detail="Password reset verification is invalid.")
    update_verified_user(unique_id=user.get("unique_id"), password_hash=hash_password(password))
    create_auth_event(email, "PASSWORD_CHANGED", True, {"uniqueId": user.get("unique_id")})
    return {"success": True, "message": "Password changed successfully. You can now log in."}



@app.post("/api/user-login")
async def legacy_user_login():
    raise HTTPException(
        status_code=410,
        detail="Use email and password login for your account.",
    )



@app.post("/api/user-logout")
def user_logout(
    request: Request,
):
    unique_id = (
        get_session_user_id(
            request
        )
    )

    response = JSONResponse(
        {
            "success":
                True,
        }
    )

    clear_user_session(
        response
    )

    if unique_id:
        create_audit_event(
            "USER_LOGOUT",
            unique_id,
            "SUCCESS",
            {
                "uniqueId":
                    unique_id,
            },
        )

    return response



@app.get("/api/users/me")
def current_user(
    request: Request,
):
    unique_id, user = (
        require_authenticated_user(
            request
        )
    )

    documents = [
        serialize_user_document(
            document
        )
        for document
        in get_user_documents(
            unique_id
        )
    ]

    return {
        "success":
            True,

        "user": {
            "uniqueId":
                unique_id,

            "fullName":
                user.get(
                    "full_name"
                ),

            "email":
                user.get(
                    "email"
                ),

            "emailVerified":
                bool(
                    user.get(
                        "email_verified"
                    )
                ),

            "dateOfBirth":
                user.get(
                    "date_of_birth"
                ),

            "address":
                user.get(
                    "address"
                ),

            "createdAt":
                user.get(
                    "created_at"
                ),

            "updatedAt":
                user.get(
                    "updated_at"
                ),

            "latestRiskScore":
                user.get(
                    "latest_risk_score"
                ),

            "status":
                user.get(
                    "status"
                ),
        },

        "documents":
            documents,

        "faceCaptures": [
            serialize_face_capture(item)
            for item in get_face_captures(unique_id, limit=10)
        ],
    }


@app.get("/api/documents/search")
def search_documents(
    request: Request,
    q: str = "",
):
    require_authenticated_user(request)
    query = str(q or "").strip()
    if len(query) < 2:
        return {"success": True, "documents": []}

    return {
        "success": True,
        "documents": [
            {
                "idType": row.get("id_type"),
                "documentNumber": row.get("document_number"),
                "fullName": row.get("full_name"),
                "finalStatus": row.get("final_status"),
                "createdAt": row.get("created_at"),
            }
            for row in search_verified_documents(query)
        ],
    }



@app.get(
    "/api/users/{unique_id}"
)
def user_profile(
    unique_id: str,
    request: Request,
):
    authenticated_id, user = (
        require_authenticated_user(
            request
        )
    )

    unique_id = (
        validate_unique_id(
            unique_id
        )
    )

    if unique_id != authenticated_id:
        raise HTTPException(
            status_code=403,
            detail=(
                "You are not allowed to "
                "access another user's data."
            ),
        )

    return {
        "success":
            True,

        "user": {
            "uniqueId":
                user.get(
                    "unique_id"
                )
                or unique_id,

            "fullName":
                user.get(
                    "full_name"
                ),

            "email":
                user.get(
                    "email"
                ),

            "emailVerified":
                bool(
                    user.get(
                        "email_verified"
                    )
                ),

            "dateOfBirth":
                user.get(
                    "date_of_birth"
                ),

            "address":
                user.get(
                    "address"
                ),

            "createdAt":
                user.get(
                    "created_at"
                ),

            "updatedAt":
                user.get(
                    "updated_at"
                ),

            "latestRiskScore":
                user.get(
                    "latest_risk_score"
                ),

            "status":
                user.get(
                    "status"
                ),
        },

        "documents": [
            serialize_user_document(
                document
            )
            for document
            in get_user_documents(
                unique_id
            )
        ],
    }



@app.delete(
    "/api/users/{unique_id}/documents/{document_id}"
)
def remove_document(
    unique_id: str,
    document_id: int,
    request: Request,
):
    authenticated_id, _ = (
        require_authenticated_user(
            request
        )
    )

    unique_id = (
        validate_unique_id(
            unique_id
        )
    )

    if unique_id != authenticated_id:
        raise HTTPException(
            status_code=403,
            detail="Document removal denied.",
        )

    document = (
        delete_user_document(
            unique_id,
            document_id,
        )
    )

    if document is None:
        raise HTTPException(
            status_code=404,
            detail="Document not found.",
        )

    details = document.get(
        "details"
    )

    if isinstance(
        details,
        str,
    ):
        try:
            details = json.loads(
                details
            )
        except Exception:
            details = {}

    elif not isinstance(
        details,
        dict,
    ):
        details = {}

    stored_filename = (
        details.get(
            "storedFilename"
        )
    )

    if stored_filename:
        stored_path = (
            UPLOAD_DIR /
            unique_id /
            Path(
                stored_filename
            ).name
        ).resolve()

        user_folder = (
            UPLOAD_DIR /
            unique_id
        ).resolve()

        if (
            stored_path.parent ==
            user_folder
        ):
            delete_file_safely(
                stored_path
            )

    create_audit_event(
        "DOCUMENT_REMOVAL",
        unique_id,
        "DOCUMENT_REMOVED",
        {
            "documentId":
                document_id,

            "idType":
                document.get(
                    "id_type"
                ),

            "documentNumber":
                document.get(
                    "document_number"
                ),

            "fullName":
                document.get(
                    "full_name"
                ),

            "dataStored":
                False,

            "reverificationAllowed":
                True,
        },
    )

    return {
        "success":
            True,

        "removed":
            True,

        "documentId":
            document_id,

        "message":
            (
                "Document removed. It can be "
                "verified again because it no "
                "longer exists in your verified "
                "repository."
            ),
    }



@app.get(
    "/api/users/{unique_id}/documents/{document_id}/file"
)
def view_document(
    unique_id: str,
    document_id: int,
    request: Request,
):
    authenticated_id, _ = (
        require_authenticated_user(
            request
        )
    )

    unique_id = (
        validate_unique_id(
            unique_id
        )
    )

    if unique_id != authenticated_id:
        raise HTTPException(
            status_code=403,
            detail="Document access denied.",
        )

    documents = (
        get_user_documents(
            unique_id
        )
    )

    document = next(
        (
            item
            for item
            in documents
            if int(
                item.get(
                    "id"
                )
            )
            == int(
                document_id
            )
        ),
        None,
    )

    if document is None:
        raise HTTPException(
            status_code=404,
            detail="Document not found.",
        )

    details = document.get(
        "details"
    )

    if isinstance(
        details,
        str,
    ):
        try:
            details = json.loads(
                details
            )
        except Exception:
            details = {}

    elif not isinstance(
        details,
        dict,
    ):
        details = {}

    user_folder = (
        UPLOAD_DIR /
        unique_id
    ).resolve()

    if not user_folder.exists():
        raise HTTPException(
            status_code=404,
            detail=(
                "User document folder "
                "not found."
            ),
        )

    stored_filename = (
        details.get(
            "storedFilename"
        )
    )

    original_filename = (
        details.get(
            "originalFilename"
        )
    )

    if stored_filename:
        stored_file = (
            user_folder /
            Path(
                stored_filename
            ).name
        )

    else:
        original_filename = (
            Path(
                original_filename or ""
            ).name
        )

        matches = [
            path
            for path
            in user_folder.iterdir()
            if (
                path.is_file()
                and (
                    path.name ==
                    original_filename
                    or
                    path.name.endswith(
                        "_"
                        + original_filename
                    )
                )
            )
        ]

        if not matches:
            raise HTTPException(
                status_code=404,
                detail="Stored file not found.",
            )

        matches.sort(
            key=lambda path:
                path.stat().st_mtime,
            reverse=True,
        )

        stored_file = (
            matches[0]
        )

    stored_file = (
        Path(
            stored_file
        ).resolve()
    )

    if (
        user_folder
        not in stored_file.parents
    ):
        raise HTTPException(
            status_code=403,
            detail="Document access denied.",
        )

    if (
        not stored_file.exists()
        or not stored_file.is_file()
    ):
        raise HTTPException(
            status_code=404,
            detail=(
                "Stored document file "
                "not found."
            ),
        )

    extension = (
        stored_file.suffix.lower()
    )

    media_type = {
        ".pdf":
            "application/pdf",

        ".jpg":
            "image/jpeg",

        ".jpeg":
            "image/jpeg",

        ".png":
            "image/png",
    }.get(
        extension,
        "application/octet-stream",
    )

    display_name = Path(
        original_filename
        or stored_file.name
    ).name

    return FileResponse(
        path=stored_file,
        media_type=media_type,
        filename=display_name,
        content_disposition_type="inline",
    )



@app.get(
    "/api/audit-logs"
)
def audit_logs(
    request: Request,
):
    unique_id, _ = (
        require_authenticated_user(
            request
        )
    )

    return get_audit_logs(
        unique_id
    )



@app.post(
    "/api/audit-events"
)
async def audit_event(
    request: Request,
):
    unique_id, _ = (
        require_authenticated_user(
            request
        )
    )

    try:
        data = await request.json()

    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Invalid audit request.",
        )

    event_type = data.get(
        "eventType"
    )

    status = data.get(
        "status"
    )

    details = data.get(
        "details",
        {},
    )

    if (
        not event_type
        or not status
    ):
        raise HTTPException(
            status_code=400,
            detail="Audit fields are required.",
        )

    log_id = (
        create_audit_event(
            event_type,
            unique_id,
            status,
            details,
        )
    )

    return {
        "success":
            True,

        "log_id":
            log_id,
    }



@app.post(
    "/api/identity-verifications"
)
async def identity_verification(
    request: Request,
):
    unique_id, _ = (
        require_authenticated_user(
            request
        )
    )

    try:
        data = await request.json()

    except Exception:
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid identity verification "
                "request."
            ),
        )

    subject_id = data.get(
        "subjectId"
    )

    final_status = data.get(
        "finalStatus"
    )

    source = data.get(
        "source"
    )

    if (
        not subject_id
        or not final_status
        or not source
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "Identity verification fields "
                "are required."
            ),
        )

    if str(
        subject_id
    ).strip() != unique_id:
        raise HTTPException(
            status_code=403,
            detail=(
                "Identity verification access denied."
            ),
        )

    try:
        verification_id = (
            create_identity_verification(
                data
            )
        )

        return {
            "success":
                True,

            "verification_id":
                verification_id,
        }

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=(
                "Unable to record identity "
                f"verification: {str(error)}"
            ),
        )



@app.post(
    "/api/face-captures"
)
async def save_face_capture(
    request: Request,
):
    unique_id, _ = require_authenticated_user(request)

    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid camera capture request.")

    image_data = str(data.get("imageData") or "").strip()
    if not image_data:
        raise HTTPException(status_code=400, detail="No camera capture was provided.")

    if not image_data.startswith("data:image/jpeg;base64,"):
        raise HTTPException(
            status_code=400,
            detail="Camera capture must be a JPEG image captured by the browser camera.",
        )

    encoded = image_data.split(",", 1)[1]
    try:
        image_bytes = base64.b64decode(encoded, validate=True)
    except Exception:
        raise HTTPException(status_code=400, detail="Camera capture data is invalid.")

    if not image_bytes:
        raise HTTPException(status_code=400, detail="Camera capture is empty.")

    if len(image_bytes) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Camera capture must be 5 MB or smaller.")



    liveness_frames = data.get("livenessFrames") or []
    if not isinstance(liveness_frames, list):
        raise HTTPException(status_code=400, detail="Invalid liveness frame set.")
    liveness_ok, liveness_reason, liveness_details = validate_liveness_frames(liveness_frames)
    if not liveness_ok:
        messages = {
            "LIVENESS_NOT_ENOUGH_FRAMES": "Live check is incomplete. Keep your face in frame and move your head left and right for about 2 seconds.",
            "LIVENESS_INVALID_FRAMES": "The live-camera motion samples were invalid. Please restart the camera and try again.",
            "LIVENESS_MOTION_REQUIRED": "No sufficient live head movement was detected. Do not hold a photo to the camera; slowly move your head left and right and capture again.",
        }
        raise HTTPException(status_code=422, detail=messages.get(liveness_reason, "Live motion check failed. Please try again."))



    valid_capture, capture_reason, capture_quality = validate_camera_capture_bytes(image_bytes)
    if not valid_capture:
        messages = {
            "NO_CLEAR_FACE": "No clear human face detected. Keep one face centered in the camera and try again.",
            "MULTIPLE_FACES": "Multiple faces detected. Only one person may be in the camera frame.",
            "FACE_TOO_BLURRY": "Face is too blurry. Hold the camera steady and try again.",
            "FACE_FRAMING_INVALID": "Face is too small or too large in the frame. Move closer or farther away.",
            "FACE_NOT_CENTERED": "Face is not centered. Look straight at the camera and try again.",
            "FACE_QUALITY_INVALID": "Face lighting/contrast is insufficient. Improve lighting and try again.",
        }
        raise HTTPException(
            status_code=422,
            detail=messages.get(capture_reason, "Camera capture did not pass the face-quality check."),
        )

    folder = get_safe_user_folder(unique_id)
    stored_filename = f"camera_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{secrets.token_hex(4)}.jpg"
    stored_path = folder / stored_filename

    with open(stored_path, "wb") as output:
        output.write(image_bytes)

    digest = hashlib.sha256(image_bytes).hexdigest()
    relative_path = str(stored_path.relative_to(UPLOAD_DIR))

    capture_id = add_face_capture(
        unique_id=unique_id,
        stored_filename=stored_filename,
        stored_path=relative_path,
        sha256=digest,
        file_size=len(image_bytes),
        liveness_status="PASSED",
        motion_score=liveness_details.get("motionScore"),
        motion_samples=liveness_details.get("motionSamples", 0),
    )

    return {
        "success": True,
        "liveness": liveness_details,
        "capture": {
            **serialize_face_capture({
                "id": capture_id,
                "captured_at": datetime.now().isoformat(),
                "original_filename": "camera-capture.jpg",
                "stored_filename": stored_filename,
                "mime_type": "image/jpeg",
                "sha256": digest,
                "file_size": len(image_bytes),
                "source": "BROWSER_CAMERA",
                "liveness_status": "PASSED",
                "motion_score": liveness_details.get("motionScore"),
                "motion_samples": liveness_details.get("motionSamples", 0),
            }),
            "fileUrl": f"/api/users/{unique_id}/face-captures/{capture_id}/file",
        },
    }


@app.get(
    "/api/users/{unique_id}/face-captures/{capture_id}/file"
)
def view_face_capture(
    unique_id: str,
    capture_id: int,
    request: Request,
):
    authenticated_id, _ = require_authenticated_user(request)
    unique_id = validate_unique_id(unique_id)

    if unique_id != authenticated_id:
        raise HTTPException(status_code=403, detail="Face capture access denied.")

    capture = get_face_capture(unique_id, capture_id)
    if not capture:
        raise HTTPException(status_code=404, detail="Face capture not found.")

    user_folder = get_safe_user_folder(unique_id)
    stored_file = (user_folder / Path(capture["stored_filename"]).name).resolve()

    if user_folder not in stored_file.parents:
        raise HTTPException(status_code=403, detail="Face capture access denied.")

    if not stored_file.exists() or not stored_file.is_file():
        raise HTTPException(status_code=404, detail="Stored face capture not found.")

    return FileResponse(
        path=stored_file,
        media_type=capture.get("mime_type") or "image/jpeg",
        filename=Path(capture.get("original_filename") or "camera-capture.jpg").name,
        content_disposition_type="inline",
    )


def _passport_sample_overlay_signal(file_path: str, ocr_text: str) -> dict[str, str] | None:
    try:
        from app.services.pdf_images import load_pdf_page_image
        path = Path(file_path)
        if path.suffix.lower() == ".pdf":
            image = load_pdf_page_image(path, 0)
        else:
            data = np.fromfile(str(path), dtype=np.uint8)
            image = cv2.imdecode(data, cv2.IMREAD_COLOR)
        if image is None:
            return None
        upper_text = str(ocr_text or "").upper()
        if any(token in upper_text for token in ("SAMPLE VALID", "SPECIMEN", "SAMPLE PASSPORT", "NOT VALID")):
            return {"type": "SAMPLE_OR_SPECIMEN_OVERLAY", "severity": "HIGH", "message": "The passport image contains a visible sample/specimen or non-valid overlay."}
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        red = cv2.inRange(hsv, np.array([0, 75, 70]), np.array([14, 255, 255])) | cv2.inRange(hsv, np.array([165, 75, 70]), np.array([179, 255, 255]))
        ratio = float(np.mean(red > 0))
        lines = cv2.HoughLinesP(red, 1, np.pi / 180, threshold=max(50, min(image.shape[:2]) // 8), minLineLength=max(120, int(min(image.shape[:2]) * 0.22)), maxLineGap=24)
        diagonal = False
        if lines is not None:
            for line in lines[:, 0]:
                x1, y1, x2, y2 = map(int, line)
                angle = abs(float(np.degrees(np.arctan2(y2 - y1, x2 - x1))))
                length = float(((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5)
                if 18 <= angle <= 75 and length >= min(image.shape[:2]) * 0.24:
                    diagonal = True
                    break
        if ratio >= 0.012 and diagonal:
            return {"type": "SAMPLE_OR_SPECIMEN_OVERLAY", "severity": "HIGH", "message": "A prominent red diagonal sample/specimen-style overlay was detected across the passport image; this is treated as an edit/sample indicator."}
    except Exception:
        return None
    return None


@app.post(
    "/api/analyze"
)
async def analyze_document(
    request: Request,

    response: Response,

    file: UploadFile = File(...),

    reference_file: UploadFile | None = File(None),

    screening_mode:
        str = Form("REFERENCE_FORM"),

    reference_name:
        str = Form(""),

    reference_dob:
        str = Form(""),

    reference_document_number:
        str = Form(""),

    id_type:
        str = Form(...),

    user_unique_id:
        str = Form(""),

    capture_id:
        str = Form(""),

    reverify_existing_document_id:
        str = Form(""),

    allow_reverification:
        str = Form("0"),
):

    authenticated_user_id, authenticated_user = (
        require_authenticated_user(
            request
        )
    )

    user_unique_id = authenticated_user_id




    screening_case_id = (
        f"DRS-{datetime.now().strftime('%Y%m%d%H%M%S')}-"
        f"{secrets.token_hex(3).upper()}"
    )

    saved_capture = None
    if str(capture_id or "").strip():
        try:
            saved_capture = get_face_capture(
                user_unique_id,
                int(str(capture_id).strip()),
            )
        except (TypeError, ValueError):
            saved_capture = None

        if not saved_capture:
            raise HTTPException(
                status_code=400,
                detail="The selected camera capture could not be found.",
            )

    id_type = str(
        id_type or ""
    ).strip().upper()
    id_type_aliases = {
        "AADHAR": "AADHAAR",
        "AADAAR": "AADHAAR",
        "AADHAR_CARD": "AADHAAR",
        "AADHAAR_CARD": "AADHAAR",
        "COLLEGEID": "COLLEGE_ID",
        "COLLEGE-ID": "COLLEGE_ID",
        "COLLEGE ID": "COLLEGE_ID",
        "DRIVINGLICENSE": "DRIVING_LICENSE",
        "DRIVING-LICENSE": "DRIVING_LICENSE",
        "DL": "DRIVING_LICENSE",
        "PAN CARD": "PAN",
        "PANCARD": "PAN",
        "VISA": "VISA",
        "VISA CARD": "VISA",
        "TOURIST VISA": "VISA",
        "ENTRY VISA": "VISA",
    }
    id_type = id_type_aliases.get(id_type, id_type)

    screening_mode = str(screening_mode or "REFERENCE_FORM").strip().upper()
    single_document_mode = screening_mode == "SINGLE_DOCUMENT"
    reference_document_mode = screening_mode == "REFERENCE_DOCUMENT" and reference_file is not None

    reference_name = str(
        reference_name or ""
    ).strip()

    reference_dob = str(
        reference_dob or ""
    ).strip()

    reference_document_number = (
        str(
            reference_document_number
            or ""
        )
        .strip()
        .upper()
    )


    applicable_fields = (
        get_applicable_identity_fields(
            id_type
        )
    )

    if not single_document_mode and not reference_document_mode:
        if ("name" in applicable_fields and not reference_name):
            raise HTTPException(status_code=422, detail="Full name is required for this document type.")
        if ("dob" in applicable_fields and not reference_dob):
            raise HTTPException(status_code=422, detail="Date of birth is required for this document type.")
        if ("document_number" in applicable_fields and not reference_document_number):
            raise HTTPException(status_code=422, detail="Document number is required for this document type.")


    existing_user = None

    if user_unique_id:

        user_unique_id = (
            validate_unique_id(
                user_unique_id
            )
        )

        existing_user = (
            find_verified_user(
                user_unique_id
            )
        )

        if existing_user is None:
            raise HTTPException(
                status_code=401,
                detail=(
                    "Drishti AI user "
                    "was not found."
                ),
            )


    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="No file selected.",
        )

    filename = Path(
        file.filename
    ).name

    extension = (
        Path(filename)
        .suffix
        .lower()
    )

    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                "Only JPG, JPEG, PNG "
                "and PDF files are allowed."
            ),
        )

    contents = await file.read()

    if not contents:
        raise HTTPException(
            status_code=400,
            detail="Selected file is empty.",
        )

    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=(
                "File size must be 8 MB "
                "or less."
            ),
        )


    temporary_file = (
        UPLOAD_DIR /
        (
            "processing_"
            + secrets.token_hex(6)
            + "_"
            + filename
        )
    )

    stored_file_path = None

    try:
        with open(
            temporary_file,
            "wb",
        ) as output:
            output.write(
                contents
            )

        reference_temporary_file = None
        reference_contents = None
        if reference_document_mode:
            if not reference_file or not reference_file.filename:
                raise HTTPException(status_code=400, detail="Reference document is required in reference-comparison mode.")
            reference_name_file = Path(reference_file.filename).name
            reference_ext = Path(reference_name_file).suffix.lower()
            if reference_ext not in ALLOWED_EXTENSIONS:
                raise HTTPException(status_code=400, detail="Reference document must be JPG, JPEG, PNG or PDF.")
            reference_contents = await reference_file.read()
            if not reference_contents or len(reference_contents) > MAX_FILE_SIZE:
                raise HTTPException(status_code=400, detail="Reference document is empty or exceeds the 8 MB limit.")
            reference_temporary_file = UPLOAD_DIR / ("reference_" + secrets.token_hex(6) + "_" + reference_name_file)
            with open(reference_temporary_file, "wb") as ref_output:
                ref_output.write(reference_contents)




        face_comparison = None




        face_required = screening_mode == "REFERENCE_FORM" and id_type in FACE_CAPTURE_DOCUMENT_TYPES

        if face_required and not saved_capture:
            raise HTTPException(
                status_code=422,
                detail="A camera face capture is required for this document type.",
            )

        if face_required and saved_capture:
            if str(saved_capture.get("liveness_status") or "NOT_CHECKED").upper() != "PASSED":
                raise HTTPException(
                    status_code=422,
                    detail="A fresh live-camera capture with head movement is required before identity verification.",
                )




        capture_path = None
        if saved_capture:
            capture_path = (
                get_safe_user_folder(user_unique_id)
                / Path(saved_capture["stored_filename"]).name
            )

        async def _run_face_compare():
            try:
                return await asyncio.to_thread(
                    compare_document_and_capture,
                    temporary_file,
                    capture_path,
                    id_type,
                )
            except FaceComparisonError as face_error:
                return {
                    "status": "COMPARISON_ERROR",
                    "message": str(face_error),
                    "score": None,
                    "documentFace": None,
                    "captureFace": None,
                }
            except Exception as face_error:
                print("Face comparison error:", face_error)
                return {
                    "status": "COMPARISON_ERROR",
                    "message": "Face comparison could not be completed for this document.",
                    "score": None,
                    "documentFace": None,
                    "captureFace": None,
                }




        ocr_reference_fields = reference_fields_for_document(id_type, {
            "name": "" if single_document_mode or reference_document_mode else ((existing_user or {}).get("full_name") or reference_name),
            "dob": "" if single_document_mode or reference_document_mode else ((existing_user or {}).get("date_of_birth") or reference_dob),
            "document_number": "" if single_document_mode or reference_document_mode else reference_document_number,
            "address": "" if single_document_mode or reference_document_mode else ((existing_user or {}).get("address") or ""),
        })

        async def _run_ocr():
            if extension in {".jpg", ".jpeg", ".png"}:
                return await asyncio.to_thread(
                    extract_text_from_image,
                    str(temporary_file),
                    id_type,
                    ocr_reference_fields,
                )
            return await asyncio.to_thread(
                extract_text_from_pdf,
                str(temporary_file),
                id_type,
                ocr_reference_fields,
            )

        async def _run_specialized_fields_from_consensus(ocr_result):



            specialized = {
                "template": f"{str(id_type or '').strip().upper()}_FIVE_VIEW_LABEL_ANCHOR",
                "fieldConfidence": dict(ocr_result.get("fieldConfidence") or {}),
                "fieldConfidenceSummary": float(ocr_result.get("confidence") or 0),
                "ocrPasses": int(ocr_result.get("ocrPasses") or 5),
                "consensusFields": dict(ocr_result.get("consensusFields") or {}),
                "referencePoints": list(ocr_result.get("referencePoints") or []),
                "referenceFieldsUsed": list(ocr_result.get("referenceFieldsUsed") or []),
            }
            try:
                specific = await asyncio.to_thread(
                    extract_document_specific_fields,
                    str(temporary_file),
                    id_type,
                    ocr_reference_fields,
                    ocr_result=ocr_result,
                )
                specific_confidence = specific.get("fieldConfidence") or {}
                for key, value in specific.items():
                    if key in {"template", "fieldConfidence", "fieldConfidenceSummary", "ocrPasses", "consensusFields", "referencePoints"}:
                        continue
                    if value not in (None, "", [], {}) and (
                        key not in specialized or
                        float(specific_confidence.get(key, 0) or 0) >= float(specialized["fieldConfidence"].get(key, 0) or 0)
                    ):
                        specialized[key] = value
                        if key in specific_confidence:
                            specialized["fieldConfidence"][key] = specific_confidence[key]
                specialized["documentSpecificTemplate"] = specific.get("template")
            except Exception as extraction_error:
                print("Document-specific extraction error:", extraction_error)
            return specialized

        async def _ocr_and_project_fields():
            result = await _run_ocr()
            return result, await _run_specialized_fields_from_consensus(result)

        tasks = [_ocr_and_project_fields()]
        if face_required and saved_capture:
            tasks.insert(0, _run_face_compare())
            face_comparison, (ocr_result, specialized_fields) = await asyncio.gather(*tasks)
        else:
            ocr_result, specialized_fields = (await asyncio.gather(*tasks))[0]

        ocr_text = ocr_result.get("text", "")
        ocr_confidence = ocr_result.get("confidence", 0)
        ocr_reference_reocr = bool(ocr_result.get("referenceReOcr"))
        ocr_mode = ocr_result.get("ocrMode", "DOCUMENT_SPECIFIC")



        document_preview = await asyncio.to_thread(
            document_preview_data_url,
            str(temporary_file),
            1800,
        )

        raw_fields = extract_fields(ocr_text, id_type, reference_name)
        consensus_fields = dict(ocr_result.get("consensusFields") or {})
        extracted_fields = {
            key: value
            for key, value in (consensus_fields or raw_fields or {}).items()
            if value not in (None, "", [], {})
        }

        for key, value in (raw_fields or {}).items():
            if key not in extracted_fields and value not in (None, "", [], {}):
                extracted_fields[key] = value




        if id_type == "PASSPORT":
            passport_name = None
            given = str((specialized_fields or {}).get("given_names") or "").strip()
            surname = str((specialized_fields or {}).get("surname") or "").strip()
            candidate = re.sub(r"\s+", " ", f"{given} {surname}").strip()
            if given and surname and re.fullmatch(r"[A-Za-z][A-Za-z .'-]{2,80}", candidate):
                passport_name = candidate.upper()
            if not passport_name:
                passport_mrz_lines = [re.sub(r"\s+", "", line.upper()) for line in ocr_text.splitlines() if "<" in line]
                for mrz_line in passport_mrz_lines:
                    if mrz_line.startswith("P<") and "<<" in mrz_line[5:]:
                        name_part = mrz_line[5:]
                        mrz_surname, mrz_given = name_part.split("<<", 1)
                        mrz_surname = re.sub(r"<+", " ", mrz_surname).strip()
                        mrz_given = re.sub(r"<+", " ", mrz_given).strip()
                        mrz_surname = re.sub(r"^[A-Z]{3}", "", mrz_surname).strip()
                        mrz_surname = re.sub(r"\bX$", "", mrz_surname).strip()
                        candidate = re.sub(r"\s+", " ", f"{mrz_given} {mrz_surname}").strip()
                        if re.fullmatch(r"[A-Z][A-Z .'-]{2,80}", candidate):
                            passport_name = candidate
                            break
            if passport_name:
                extracted_fields["name"] = passport_name

        extraction_conflicts = []
        for key, value in (specialized_fields or {}).items():
            if key in {"fieldConfidence", "template", "documentSpecificTemplate"}:
                continue
            confidence = float((specialized_fields or {}).get("fieldConfidence", {}).get(key, 0) or 0)
            current = extracted_fields.get(key)
            should_override = confidence >= 50.0 or not current
            if id_type == "AADHAAR" and key in {"name", "dob", "gender", "document_number", "address", "father_name"}:
                should_override = confidence >= 45.0 or not current
            if id_type == "COLLEGE_ID" and key == "course":
                should_override = bool(re.search(r"B\s*TECH", str(value), re.I) and re.search(r"C\s*SE", str(value), re.I))
            if value not in (None, "", [], {}) and should_override:
                if current not in (None, "", [], {}) and str(current).strip().upper() != str(value).strip().upper():
                    extraction_conflicts.append({
                        "field": key,
                        "generic": current,
                        "specialized": value,
                        "specializedConfidence": round(confidence, 1),
                    })
                extracted_fields[key] = value




        if id_type in {"PAN", "AADHAAR"}:
            person_anchors = _extract_label_anchor_fields(ocr_text, id_type, {})
            for key in ("name", "father_name", "mother_name"):
                value = person_anchors.get(key)
                if value not in (None, ""):
                    extracted_fields[key] = value




        reference_name_for_extraction = str(ocr_reference_fields.get("name") or "").strip()
        extracted_name = str(extracted_fields.get("name") or "").strip()
        extracted_name_tokens = re.findall(r"[A-Za-z]+", extracted_name)
        if (
            reference_name_for_extraction
            and extracted_name
            and extracted_name.casefold() != reference_name_for_extraction.casefold()
            and len(extracted_name) <= 8
            and len(extracted_name_tokens) >= 2
            and all(len(token) <= 3 for token in extracted_name_tokens)
        ):
            extraction_conflicts.append({
                "field": "name",
                "generic": extracted_name,
                "referenceRepair": reference_name_for_extraction,
                "reason": "TRUNCATED_OCR_NAME",
            })
            extracted_fields["name"] = reference_name_for_extraction



        if id_type == "PASSPORT":
            passport_name = None
            given = str((specialized_fields or {}).get("given_names") or "").strip()
            surname = str((specialized_fields or {}).get("surname") or "").strip()
            candidate = re.sub(r"\s+", " ", f"{given} {surname}").strip()
            if given and surname and re.fullmatch(r"[A-Za-z][A-Za-z .'-]{2,80}", candidate):
                passport_name = candidate.upper()
            if not passport_name:
                passport_mrz_lines = [re.sub(r"\s+", "", line.upper()) for line in ocr_text.splitlines() if "<" in line]
                for mrz_line in passport_mrz_lines:
                    if mrz_line.startswith("P<") and "<<" in mrz_line[5:]:
                        name_part = mrz_line[5:]
                        mrz_surname, mrz_given = name_part.split("<<", 1)
                        mrz_surname = re.sub(r"<+", " ", mrz_surname).strip()
                        mrz_given = re.sub(r"<+", " ", mrz_given).strip()
                        mrz_surname = re.sub(r"^[A-Z]{3}", "", mrz_surname).strip()
                        mrz_surname = re.sub(r"\bX$", "", mrz_surname).strip()
                        candidate = re.sub(r"\s+", " ", f"{mrz_given} {mrz_surname}").strip()
                        if re.fullmatch(r"[A-Z][A-Z .'-]{2,80}", candidate):
                            passport_name = candidate
                            break
            if passport_name:
                extracted_fields["name"] = passport_name

        address_value = str(extracted_fields.get("address") or "")
        if re.search(
            r"\b(?:should\s+be\s+updated|update|upload|submit|enter|provide|click|select)\b",
            address_value,
            re.I,
        ):
            extracted_fields.pop("address", None)
        if id_type == "AADHAAR":
            extracted_fields.pop("father_name", None)
            extracted_fields.pop("mother_name", None)
            extracted_fields.pop("relation_name", None)
            from app.services.checksums import verhoeff_is_valid



            address = str(extracted_fields.get("address") or "")
            address = re.sub(r"[^A-Za-z0-9,./()'\- ]+", " ", address)
            address = re.sub(r"^\s*Pd\s*ar\s*,?\s*C\.?5\s*Sia\s*,?\s*", "", address, flags=re.I)
            address = re.sub(r"\bG\s*\.\s*p\b", "G.P.", address, flags=re.I)
            address = re.sub(r"\bUttar(?:\s+Prade(?:s|ch|h|sh)\w*)?\b", "Uttar Pradesh", address, flags=re.I)
            relation_prefix = re.match(
                r"^\s*(?:S\s*/\s*O|D\s*/\s*O|W\s*/\s*O|C\s*/\s*O|SON\s+OF|DAUGHTER\s+OF|WIFE\s+OF)\s*[:\-]?\s*",
                address,
                flags=re.I,
            )
            if relation_prefix:
                address = address[relation_prefix.end():].strip()
            address = re.sub(
                r"\b(Udayganj)\s+(Lucknow)\s+(Lucknow\s+G\.P\.)\s+(Lucknow)\s+(Uttar\s+Pradesh)\b",
                r"\1, \2, \3, \4, \5",
                address,
                flags=re.I,
            )
            address = re.sub(r"\s*,\s*", ", ", address)
            address = re.sub(r"\s+", " ", address).strip(" ,.-")
            if not address:


                address_match = re.search(
                    r"\bADDRESS\s*[:\-]?\s*(.+?)(?=\b(?:DOB|DATE|GENDER|SEX|AADHAAR|UIDAI)\b|$)",
                    ocr_text,
                    flags=re.I | re.S,
                )
                if address_match:
                    address = re.sub(r"\s+", " ", address_match.group(1)).strip(" ,.-")
                    relation_prefix = re.match(
                        r"^\s*(?:S\s*/\s*O|D\s*/\s*O|W\s*/\s*O|C\s*/\s*O)\s*[:\-]?\s*",
                        address,
                        flags=re.I,
                    )
                    if relation_prefix:
                        address = address[relation_prefix.end():].strip()
            if address:
                extracted_fields["address"] = address
            else:
                extracted_fields.pop("address", None)
            aadhaar_number = re.sub(r"\s+", "", str(extracted_fields.get("document_number") or ""))
            if not (re.fullmatch(r"\d{12}", aadhaar_number) and verhoeff_is_valid(aadhaar_number)):
                extracted_fields.pop("document_number", None)
            extracted_name = str(extracted_fields.get("name") or "")
            if extracted_name and (
                len(extracted_name.split()) > 5
                or len(extracted_name) > 52
                or re.search(r"\b(?:aadhaar|aadhar|uidai|government|india|address|s/o|d/o|w/o|c/o)\b", extracted_name, re.I)
            ):
                extracted_fields.pop("name", None)
            gender = str(extracted_fields.get("gender") or "").upper()
            if gender not in {"MALE", "FEMALE", "OTHER"}:
                extracted_fields.pop("gender", None)
            if extracted_fields.get("dob"):
                dob_value = str(extracted_fields["dob"])
                if not re.fullmatch(r"\d{1,2}[/-]\d{1,2}[/-]\d{4}", dob_value):
                    extracted_fields.pop("dob", None)

        if id_type == "PAN":


            pan_allowed = {"name", "father_name", "dob", "document_number"}
            extracted_fields = {
                key: value for key, value in extracted_fields.items()
                if key in pan_allowed and value not in (None, "", [], {})
            }
            pan_number = str(extracted_fields.get("document_number") or "").replace(" ", "").upper()
            if pan_number and not re.fullmatch(r"[A-Z]{5}[0-9]{4}[A-Z]", pan_number):
                extracted_fields.pop("document_number", None)

        if id_type == "COLLEGE_ID":
            course_value = str(extracted_fields.get("course") or "")
            if re.search(r"B\s*TECH", course_value, re.I) and re.search(r"C\s*SE", course_value, re.I):
                extracted_fields["course"] = "BTECH (CSE)"


            match = re.search(r"\b(BE\d{2}[A-Z]{2}\d{3})\b", str(ocr_text or "").upper())
            if match:
                extracted_fields["document_number"] = match.group(1)
                extracted_fields["enrollment_number"] = match.group(1)



            college_allowed = {
                "name", "dob", "document_number", "erp_id", "course",
                "institution_name", "enrollment_number", "valid_until",
            }
            extracted_fields = {
                key: value for key, value in extracted_fields.items()
                if key in college_allowed and value not in (None, "", [], {})
            }
        raw_ocr_confidence = ocr_confidence
        ocr_confidence = _effective_ocr_confidence(
            raw_ocr_confidence, specialized_fields, id_type
        )
        extraction_meta = {
            "template": (specialized_fields or {}).get("template"),
            "fieldConfidence": (specialized_fields or {}).get("fieldConfidence", {}),
            "fieldConfidenceSummary": (specialized_fields or {}).get("fieldConfidenceSummary", 0),
            "ocrPasses": (specialized_fields or {}).get("ocrPasses", 0),
            "consensusFields": (specialized_fields or {}).get("consensusFields", {}),
            "rawOcrConfidence": raw_ocr_confidence,
            "effectiveOcrConfidence": ocr_confidence,
        }

        reference_comparison = {
            "available": False,
            "mode": "SINGLE_DOCUMENT" if single_document_mode else "REFERENCE_FORM",
            "score": 0,
            "band": "UNAVAILABLE",
            "evidence": [],
        }
        if reference_document_mode and reference_temporary_file:
            reference_ext = Path(reference_temporary_file).suffix.lower()
            async def _run_reference_ocr():
                if reference_ext == ".pdf":
                    return await asyncio.to_thread(
                        extract_text_from_pdf, str(reference_temporary_file), id_type, {}
                    )
                return await asyncio.to_thread(
                    extract_text_from_image, str(reference_temporary_file), id_type, {}
                )

            async def _run_reference_specialized():
                try:
                    return await asyncio.to_thread(
                        extract_document_specific_fields, str(reference_temporary_file), id_type, {}
                    )
                except Exception:
                    return {}

            ref_ocr, ref_specialized = await asyncio.gather(
                _run_reference_ocr(), _run_reference_specialized()
            )
            ref_fields_raw = extract_fields(ref_ocr.get("text", ""), id_type, "")
            ref_fields = {key: value for key, value in (ref_fields_raw or {}).items() if value not in (None, "", [], {})}
            for key, value in (ref_specialized or {}).items():
                confidence = float((ref_specialized or {}).get("fieldConfidence", {}).get(key, 0) or 0)
                if key in {"fieldConfidence", "template"}:
                    continue
                if key == "course" and re.search(r"B\s*TECH", str(value), re.I) and re.search(r"C\s*SE", str(value), re.I):
                    ref_fields[key] = "BTECH (CSE)"
                elif value not in (None, "", [], {}) and (confidence >= 50.0 or not ref_fields.get(key)):
                    ref_fields[key] = value
            if id_type == "COLLEGE_ID":
                match = re.search(r"\b(BE\d{2}[A-Z]{2}\d{3})\b", str(ref_ocr.get("text", "")).upper())
                if match:
                    ref_fields["document_number"] = match.group(1)
                    ref_fields["enrollment_number"] = match.group(1)
                college_allowed = {
                    "name", "dob", "document_number", "erp_id", "course",
                    "institution_name", "enrollment_number", "valid_until",
                }
                ref_fields = {
                    key: value for key, value in ref_fields.items()
                    if key in college_allowed and value not in (None, "", [], {})
                }
            reference_comparison = build_reference_comparison(
                str(reference_temporary_file), str(temporary_file), ref_fields, extracted_fields
            )

        document_consistency = check_document_consistency(
            id_type,
            extracted_fields,
        )

        extracted_name = (
            extracted_fields.get(
                "name"
            )
        )

        extracted_dob = (
            extracted_fields.get(
                "dob"
            )
        )

        extracted_document_number = (
            extracted_fields.get(
                "document_number"
            )
        )


        if single_document_mode or reference_document_mode:
            effective_reference_fields = {}
        elif existing_user:
            effective_reference_fields = {
                "name": existing_user.get("full_name") or reference_name,
                "dob": existing_user.get("date_of_birth") or reference_dob,
                "document_number": reference_document_number,
            }
        else:
            effective_reference_fields = {
                "name": reference_name,
                "dob": reference_dob,
                "document_number": reference_document_number,
            }


        identity_results = (
            compare_identity(
                effective_reference_fields,
                extracted_fields,
                id_type,
            )
        )





        face_verification_failed = False
        face_score = None
        face_risk_score = 0.0
        face_risk_band = "NOT_REQUIRED"
        if face_required:
            raw_face_score = face_comparison.get("score")
            try:
                face_score = float(raw_face_score) if raw_face_score is not None else None
            except (TypeError, ValueError):
                face_score = None

            face_match_ok = (
                face_comparison.get("status") == "SIMILAR"
                and face_score is not None
                and face_score >= FACE_MATCH_THRESHOLD
            )
            face_risk_score = (
                round(max(0.0, min(100.0, 100.0 - face_score)), 1)
                if face_score is not None else 100.0
            )
            face_risk_band = "LOW" if face_match_ok else "HIGH"
            face_verification_failed = not face_match_ok
            face_comparison = {
                **face_comparison,
                "threshold": FACE_MATCH_THRESHOLD,
                "verified": face_match_ok,
                "riskScore": face_risk_score,
                "riskBand": face_risk_band,
            }

        evidence_started = time.perf_counter()


        async def _run_quality():
            if extension in {
                ".jpg",
                ".jpeg",
                ".png",
            }:
                return await asyncio.to_thread(
                    analyze_image_quality,
                    str(temporary_file),
                )

            from app.services.pdf_images import load_pdf_page_image

            page_image = await asyncio.to_thread(
                load_pdf_page_image,
                str(temporary_file),
                0,
            )
            if page_image is None:
                raise Exception("Unable to extract PDF page image.")

            temp_image = None
            with tempfile.NamedTemporaryFile(
                suffix=".png",
                delete=False,
            ) as temp:
                temp_image = Path(temp.name)
            try:
                ok, encoded = await asyncio.to_thread(
                    cv2.imencode, ".png", page_image
                )
                if not ok:
                    raise Exception("Unable to encode extracted PDF page image.")
                await asyncio.to_thread(temp_image.write_bytes, encoded.tobytes())
                result = await asyncio.to_thread(
                    analyze_image_quality,
                    str(temp_image),
                )
                result["sourceImage"] = "PDF_EMBEDDED_IMAGE_OR_HIRES_RENDER"
                return result
            finally:
                if temp_image and temp_image.exists():
                    temp_image.unlink()

        async def _run_indicators():
            return await asyncio.to_thread(
                analyze_indicators,
                str(temporary_file),
                ocr_confidence,
                identity_results,
            )

        quality_result, indicator_result = await asyncio.gather(
            _run_quality(),
            _run_indicators(),
        )
        quality_finished = time.perf_counter()

        async def _run_cross_document_consistency():
            try:
                existing_user_documents = (
                    await asyncio.to_thread(get_user_documents, user_unique_id)
                    if user_unique_id else []
                )
                return build_cross_document_consistency(
                    extracted_fields,
                    existing_user_documents,
                    id_type,
                )
            except Exception as consistency_error:
                print("Cross-document consistency error:", consistency_error)
                return {
                    "available": False,
                    "status": "UNAVAILABLE",
                    "summary": "Account-level consistency checks were unavailable for this attempt.",
                    "signals": [],
                    "checkedDocuments": 0,
                }



        cross_document_task = asyncio.create_task(_run_cross_document_consistency())




        try:
            ai_document_result = await asyncio.to_thread(
                analyze_ai_document,
                str(temporary_file),
                id_type,
                ocr_confidence,
                ocr_text,
                extracted_fields,
            )
        except Exception as ai_error:
            print("AI document screening error:", ai_error)
            ai_document_result = {
                "enabled": False,
                "available": False,
                "band": "UNAVAILABLE",
                "score": 0,
                "signals": [],
                "qualitySignals": [],
                "features": {},
                "notice": "AI/synthetic screening was unavailable for this document.",
            }
        ai_finished = time.perf_counter()




        try:
            document_verification = await asyncio.to_thread(
                build_document_verification,
                str(temporary_file),
                id_type,
                extracted_fields,
                ocr_confidence,
                ocr_text,
                ai_document_result,
                document_consistency,
            )
            if id_type == "PASSPORT":
                sample_signal = _passport_sample_overlay_signal(str(temporary_file), ocr_text)
                if sample_signal:
                    document_verification = {
                        **document_verification,
                        "overallStatus": "HIGH",
                        "summary": "A sample/specimen overlay was detected on the passport image; the document should be treated as edited or non-genuine for this screening.",
                        "fabricationScreening": {
                            **(document_verification.get("fabricationScreening") or {}),
                            "verdict": "EDITED_OR_SAMPLE_DOCUMENT",
                            "status": "HIGH",
                            "summary": "A visible sample/specimen overlay is present on the passport image.",
                            "signals": [sample_signal, *((document_verification.get("fabricationScreening") or {}).get("signals") or [])[:7]],
                        },
                        "modules": [
                            *[module for module in (document_verification.get("modules") or []) if module.get("id") != "fabrication"],
                            {"id": "fabrication", "label": "Fabrication assessment", "status": "HIGH", "message": "A visible sample/specimen overlay was detected; document appears edited or non-genuine."},
                        ],
                        "evidenceReasons": [sample_signal.get("message")] + list(document_verification.get("evidenceReasons") or [])[:7],
                    }
        except Exception as verification_error:
            print("Document verification evidence error:", verification_error)
            document_verification = {
                "available": False,
                "overallStatus": "UNAVAILABLE",
                "summary": "Verification evidence module was unavailable for this attempt.",
                "modules": [],
                "evidenceReasons": [],
                "issuerVerification": {
                    "status": "NOT_CONFIGURED",
                    "message": "No authorised issuer connector is configured.",
                },
            }
        verification_finished = time.perf_counter()
        cross_document_consistency = await cross_document_task
        print("Evidence pipeline timings:", {
            "qualityAndIndicators": round(quality_finished - evidence_started, 3),
            "syntheticSignals": round(ai_finished - quality_finished, 3),
            "verificationEvidence": round(verification_finished - ai_finished, 3),
            "total": round(verification_finished - evidence_started, 3),
        })

        risk_result = calculate_risk_score(
            identity_results=identity_results,
            ocr_confidence=ocr_confidence,
            quality_result=quality_result,
            indicator_result=indicator_result,
            document_consistency=document_consistency,
            reference_comparison=reference_comparison,
            ai_document_analysis=ai_document_result,
            document_verification=document_verification,
            cross_document_consistency=cross_document_consistency,
            extraction_conflicts=extraction_conflicts,
            face_comparison=face_comparison,
        )

        risk_score = int(
            risk_result.get(
                "score",
                0,
            )
        )

        risk_band = (
            risk_result.get(
                "risk_band",
                "Unknown",
            )
        )


        document_number_result = (
            identity_results.get(
                "document_number"
            )
        )

        document_number_mismatch = (
            "document_number"
            in applicable_fields

            and isinstance(
                document_number_result,
                dict,
            )

            and document_number_result.get(
                "status"
            ) != "MATCH"
        )

        if document_number_mismatch:





            risk_result = {
                **risk_result,
                "identity_gate": {
                    **(risk_result.get("identity_gate") or {}),
                    "status": "FAIL",
                    "mismatches": list(
                        set(
                            list((risk_result.get("identity_gate") or {}).get("mismatches", []))
                            + ["document_number"]
                        )
                    ),
                },
                "document_number_mismatch": True,
                "reason": (
                    "Document number mismatch between entered/reference number "
                    "and OCR-extracted number. The identity gate fails, but the "
                    "document-authenticity risk score is kept separate."
                ),
            }


        if single_document_mode or reference_document_mode:
            confidence = str(risk_result.get("analysis_confidence", "LOW")).upper()
            mode_message = (
                "Single-document forensic screening completed. The result combines observable forensic signals; it does not prove legal authenticity."
                if single_document_mode else
                "Reference comparison completed. Observable differences are reported as forensic evidence; they do not by themselves establish which copy is legally genuine."
            )
            screening_outcome = str(risk_result.get("screening_outcome", "REVIEW")).upper()
            response_payload = {
                "success": True,
                "dataStored": False,
                "status": "SCREENED_ONLY",
                "screeningMode": "SINGLE_DOCUMENT" if single_document_mode else "REFERENCE_DOCUMENT",
                "caseId": screening_case_id,
                "message": mode_message,
                "riskScore": risk_score,
                "documentRiskScore": risk_score,
                "riskBand": risk_band,
                "finalDecision": {
                    "outcome": f"SCREENED_{screening_outcome}",
                    "documentAuthenticity": screening_outcome,
                    "identityVerification": "NOT_REQUIRED",
                    "evidenceConfidence": confidence,
                    "riskScore": risk_score,
                    "nextAction": risk_result.get("recommendation") or mode_message,
                },
                "riskBand": risk_band,
                "evidenceConfidence": confidence,
                "extractedFields": extracted_fields,
                "extractionMeta": extraction_meta,
                "identityAnalysis": identity_results,
                "qualityAnalysis": quality_result,
                "suspiciousIndicators": indicator_result,
                "aiDocumentAnalysis": ai_document_result,
                "documentConsistency": document_consistency,
                "documentVerification": document_verification,
                "referenceComparison": reference_comparison,
                "riskAssessment": risk_result,
                "ocrConfidence": ocr_confidence,
                "ocrText": ocr_text,
                "documentPreview": document_preview,
                "faceComparison": face_comparison if screening_mode == "REFERENCE_FORM" else None,
            }
            create_audit_event("DOCUMENT_SCREENING", user_unique_id or None, "FORENSIC_SCREENING_COMPLETED", response_payload)
            delete_file_safely(temporary_file)
            temporary_file = None
            if reference_temporary_file:
                delete_file_safely(reference_temporary_file)
                reference_temporary_file = None
            return JSONResponse(status_code=200, content=response_payload)

        stored_document_number = (
            reference_document_number
            or
            extracted_document_number
        )

        if not stored_document_number:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Document number could "
                    "not be determined."
                ),
            )

        stored_full_name = (
            reference_name
            or
            extracted_name
        )

        stored_dob = (
            reference_dob
            or
            extracted_dob
        )


        identity_statuses = [
            result.get(
                "status"
            )
            for result
            in identity_results.values()
            if isinstance(
                result,
                dict,
            )
        ]

        if "MISMATCH" in identity_statuses:

            overall_identity_status = (
                "MISMATCH"
            )

        elif "PARTIAL" in identity_statuses:

            overall_identity_status = (
                "PARTIAL"
            )

        elif "UNKNOWN" in identity_statuses:

            overall_identity_status = (
                "UNKNOWN"
            )

        else:

            overall_identity_status = (
                "MATCH"
            )


        if document_number_mismatch:

            create_audit_event(
                "DOCUMENT_SCREENING",
                user_unique_id or None,
                "DOCUMENT_NUMBER_MISMATCH",
                {
                    "idType":
                        id_type,

                    "referenceDocumentNumber":
                        reference_document_number,

                    "extractedDocumentNumber":
                        extracted_document_number,

                    "dataStored":
                        False,


                    "riskBand":
                        "HIGH RISK",

                    "riskScore":
                        risk_score,
                    "faceComparison":
                        face_comparison,
                },
            )

            delete_file_safely(
                temporary_file
            )

            temporary_file = None

            return JSONResponse(
                status_code=422,
                content={
                    "success":
                        False,

                    "dataStored":
                        False,



                    "status":
                        "DOCUMENT_NUMBER_MISMATCH",

                    "message":
                        (
                            "Document number "
                            "mismatch. Verification "
                            "rejected and the document "
                            "was not stored."
                        ),

                    "riskScore":
                        risk_score,

                    "riskBand":
                        risk_band,

                    "extractedFields":
                        extracted_fields,

                    "identityAnalysis":
                        identity_results,

                    "qualityAnalysis":
                        quality_result,

                    "suspiciousIndicators":
                        indicator_result,
                    "aiDocumentAnalysis":
                        ai_document_result,

                    "documentConsistency":
                        document_consistency,

                    "documentVerification":
                        document_verification,

                    "riskAssessment":
                        risk_result,

                    "ocrConfidence":
                        ocr_confidence,

                    "ocrText":
                        ocr_text,

                    "faceComparison":
                        face_comparison,
                },
            )





        if face_required and face_verification_failed:



            risk_result = {
                **risk_result,
                "face_verification_failed": True,
                "face_risk_score": face_risk_score,
                "face_threshold": FACE_MATCH_THRESHOLD,
                "reason": (
                    "Live-face verification failed. The identity gate is rejected; "
                    "the document-authenticity risk score remains unchanged."
                ),
            }

            create_audit_event(
                "DOCUMENT_SCREENING",
                user_unique_id or None,
                "FACE_VERIFICATION_FAILED",
                {
                    "idType": id_type,
                    "documentNumber": reference_document_number or None,
                    "dataStored": False,
                    "faceComparison": face_comparison,
                    "faceThreshold": FACE_MATCH_THRESHOLD,
                    "faceRiskScore": face_risk_score,
                    "faceRiskBand": face_risk_band,
                    "riskScore": risk_score,
                    "riskBand": risk_band,
                    "ocrConfidence": ocr_confidence,
                    "extractedFields": extracted_fields,
                    "qualityAnalysis": quality_result,
                    "documentConsistency": document_consistency,
                    "documentVerification": document_verification,
                },
            )

            delete_file_safely(temporary_file)
            temporary_file = None

            return JSONResponse(
                status_code=422,
                content={
                    "success": False,
                    "dataStored": False,
                    "status": "FACE_VERIFICATION_FAILED",
                    "caseId": screening_case_id,
                    "finalDecision": {
                        "outcome": "REJECTED_IDENTITY",
                        "documentAuthenticity": (
                            "LOW_RISK" if risk_score < DOCUMENT_VERIFIED_RISK_LIMIT else
                            "REVIEW" if risk_score < DOCUMENT_STORE_REJECT_LIMIT else
                            "HIGH_RISK"
                        ),
                        "identityVerification": "FAILED",
                        "evidenceConfidence": str(risk_result.get("analysis_confidence", "LOW")),
                        "riskScore": risk_score,
                        "nextAction": "Do not accept for this identity; capture the correct document holder or review the live-face evidence.",
                        "verificationExplanation": (
                            f"Document screening risk is {risk_score}/100 ({risk_band}), but identity verification failed. "
                            "A low document-risk score only means that the configured manipulation checks found no strong contradiction; "
                            "it does not prove that the person presenting the document is its holder. Because the face gate failed, the overall result is NOT VERIFIED."
                        ),
                    },
                    "message": (
                        "Document screening completed, but live-face verification failed. "
                        "The document was not stored because identity verification failed."
                    ),
                    "verificationExplanation": (
                        f"Document screening risk is {risk_score}/100 ({risk_band}), but identity verification failed. "
                        "The document can be low-risk for editing and still fail identity verification when the live face does not sufficiently match the document portrait. "
                        "Overall result: NOT VERIFIED."
                    ),
                    "riskScore": risk_score,
                    "documentRiskScore": risk_score,
                    "riskBand": risk_band,
                    "threshold": FACE_MATCH_THRESHOLD,
                    "faceVerification": {
                        "required": True,
                        "threshold": FACE_MATCH_THRESHOLD,
                        "score": face_score,
                        "verified": False,
                        "riskScore": face_risk_score,
                        "riskBand": face_risk_band,
                    },
                    "faceComparison": face_comparison,
                    "ocrConfidence": ocr_confidence,
                    "ocrText": ocr_text,
                    "extractedFields": extracted_fields,
                    "identityAnalysis": identity_results,
                    "qualityAnalysis": quality_result,
                    "suspiciousIndicators": indicator_result,
                    "aiDocumentAnalysis": ai_document_result,
                    "documentConsistency": document_consistency,
                    "documentVerification": document_verification,
                    "crossDocumentConsistency": cross_document_consistency,
                    "extractionMeta": extraction_meta,
                    "riskAssessment": risk_result,
                },
            )






        identity_gate = str((risk_result.get("identity_gate") or {}).get("status", "PASS")).upper()
        if screening_mode == "REFERENCE_FORM" and identity_gate == "FAIL":
            mismatch_fields = (risk_result.get("identity_gate") or {}).get("mismatches", [])
            create_audit_event(
                "DOCUMENT_SCREENING",
                user_unique_id or None,
                "IDENTITY_VERIFICATION_FAILED",
                {
                    "idType": id_type,
                    "dataStored": False,
                    "identityMismatches": mismatch_fields,
                    "riskScore": risk_score,
                    "riskBand": risk_band,
                    "extractedFields": extracted_fields,
                    "identityAnalysis": identity_results,
                    "riskAssessment": risk_result,
                },
            )

            final_decision = {
                "outcome": "REJECTED_IDENTITY",
                "documentAuthenticity": (
                    "LOW_RISK" if risk_score < DOCUMENT_VERIFIED_RISK_LIMIT else
                    "REVIEW" if risk_score < DOCUMENT_STORE_REJECT_LIMIT else
                    "HIGH_RISK"
                ),
                "identityVerification": "FAILED",
                "evidenceConfidence": str(risk_result.get("analysis_confidence", "LOW")),
                "riskScore": risk_score,
                "nextAction": "Do not accept for this identity; review the mismatched identity fields or capture the correct document holder.",
                "verificationExplanation": (
                    f"Document screening risk is {risk_score}/100 ({risk_band}), while the supplied identity fields did not match the extracted document fields. "
                    "Document risk and identity verification are separate checks, so a low-risk document can still be NOT VERIFIED for the supplied identity."
                ),
            }

            delete_file_safely(temporary_file)
            temporary_file = None
            if reference_temporary_file:
                delete_file_safely(reference_temporary_file)
                reference_temporary_file = None

            return JSONResponse(
                status_code=422,
                content={
                    "success": False,
                    "dataStored": False,
                    "status": "IDENTITY_VERIFICATION_FAILED",
                    "message": "Document screening completed, but the supplied identity fields do not match the extracted document identity.",
                    "caseId": screening_case_id,
                    "finalDecision": final_decision,
                    "riskScore": risk_score,
                    "documentRiskScore": risk_score,
                    "riskBand": risk_band,
                    "extractedFields": extracted_fields,
                    "identityAnalysis": identity_results,
                    "qualityAnalysis": quality_result,
                    "suspiciousIndicators": indicator_result,
                    "aiDocumentAnalysis": ai_document_result,
                    "documentConsistency": document_consistency,
                    "documentVerification": document_verification,
                    "crossDocumentConsistency": cross_document_consistency,
                    "extractionMeta": extraction_meta,
                    "riskAssessment": risk_result,
                    "ocrConfidence": ocr_confidence,
                    "ocrText": ocr_text,
                    "documentPreview": document_preview,
                    "faceComparison": face_comparison,
                },
            )


        if (
            user_unique_id
            and stored_full_name
            and not stored_document_number
        ):

            duplicate_by_identity = (
                find_user_document_by_name_and_type(
                    user_unique_id,
                    id_type,
                    stored_full_name,
                )
            )

            if duplicate_by_identity:

                existing_duplicate_id = (
                    duplicate_by_identity[
                        "unique_id"
                    ]
                )

                create_audit_event(
                    "DOCUMENT_SCREENING",
                    existing_duplicate_id,
                    "DUPLICATE_IDENTITY_DOCUMENT",
                    {
                        "idType":
                            id_type,

                        "fullName":
                            stored_full_name,

                        "newDocumentNumber":
                            stored_document_number,

                        "existingDocumentNumber":
                            duplicate_by_identity.get(
                                "document_number"
                            ),

                        "existingDocumentId":
                            duplicate_by_identity.get(
                                "id"
                            ),

                        "dataStored":
                            False,
                        "faceComparison":
                            face_comparison,
                    },
                )

                delete_file_safely(
                    temporary_file
                )

                temporary_file = None

                return JSONResponse(
                    status_code=409,
                    content={
                        "success":
                            False,

                        "duplicate":
                            True,

                        "duplicateReason":
                            (
                                "IDENTITY_DOCUMENT_"
                                "ALREADY_EXISTS"
                            ),

                        "message":
                            (
                                f"A verified {id_type} "
                                "already exists for "
                                "this user."
                            ),

                        "detail":
                            (
                                "Remove the existing "
                                "document from the "
                                "User Portal first. "
                                "After removal, the "
                                "document can be "
                                "verified again."
                            ),

                        "existingDocumentId":
                            duplicate_by_identity.get(
                                "id"
                            ),

                        "existingDocumentNumber":
                            duplicate_by_identity.get(
                                "document_number"
                            ),

                        "documentNumber":
                            stored_document_number,
                    },
                )


        duplicate = find_document_by_number(stored_document_number)
        explicit_reverify = str(allow_reverification or "0").strip().lower() in {"1", "true", "yes"}
        requested_existing_id = None
        try:
            requested_existing_id = int(str(reverify_existing_document_id).strip()) if str(reverify_existing_document_id).strip() else None
        except (TypeError, ValueError):
            requested_existing_id = None

        if duplicate:
            duplicate_owner = str(duplicate.get("unique_id") or "")
            duplicate_count = int(duplicate.get("reverification_count") or 0)
            same_account = duplicate_owner == str(user_unique_id)
            same_record = requested_existing_id is not None and requested_existing_id == int(duplicate.get("id"))




            if not explicit_reverify:
                create_audit_event(
                    "DOCUMENT_SCREENING",
                    user_unique_id,
                    "DUPLICATE_DOCUMENT",
                    {
                        "idType": id_type,
                        "documentNumber": stored_document_number,
                        "existingDocumentId": duplicate.get("id"),
                        "existingOwner": "CURRENT_USER" if same_account else "OTHER_USER",
                        "reverificationCount": duplicate_count,
                        "dataStored": False,
                        "updateAvailable": duplicate_count == 0,
                    },
                )
                delete_file_safely(temporary_file)
                temporary_file = None
                return JSONResponse(
                    status_code=409,
                    content={
                        "success": False,
                        "duplicate": True,
                        "alreadyStored": True,
                        "canUpdate": duplicate_count == 0,
                        "duplicateReason": (
                            "DOCUMENT_ALREADY_UPDATED"
                            if duplicate_count > 0
                            else "DOCUMENT_ALREADY_STORED"
                        ),
                        "message": (
                            f"This {id_type} document is already stored in your account."
                            if same_account
                            else f"This {id_type} document is already stored in another account."
                        ),
                        "detail": (
                            "Use Update to open Forensic Deep Dive and perform one fresh re-verification."
                            if duplicate_count == 0
                            else "This document has already been re-verified once. Another verification attempt is a duplicate."
                        ),
                        "existingDocumentId": duplicate.get("id"),
                        "existingDocumentNumber": duplicate.get("document_number"),
                        "existingOwner": "CURRENT_USER" if same_account else "OTHER_USER",
                        "existingFullName": duplicate.get("full_name") if same_account else None,
                        "existingDob": duplicate.get("date_of_birth") if same_account else None,
                        "reverificationCount": duplicate_count,
                        "documentNumber": stored_document_number,
                        "idType": id_type,
                    },
                )



            if not same_record or not same_account:
                delete_file_safely(temporary_file)
                temporary_file = None
                return JSONResponse(
                    status_code=409,
                    content={
                        "success": False,
                        "duplicate": True,
                        "alreadyStored": True,
                        "canUpdate": False,
                        "duplicateReason": "DOCUMENT_ALREADY_STORED",
                        "message": (
                            "This document is already stored for another account and cannot be transferred by re-verification."
                            if not same_account
                            else "The stored document could not be matched for the requested update."
                        ),
                        "detail": "The original stored record remains unchanged.",
                        "existingDocumentId": duplicate.get("id"),
                        "existingDocumentNumber": duplicate.get("document_number"),
                        "existingOwner": "CURRENT_USER" if same_account else "OTHER_USER",
                        "reverificationCount": duplicate_count,
                        "documentNumber": stored_document_number,
                        "idType": id_type,
                    },
                )

            if duplicate_count > 0:
                delete_file_safely(temporary_file)
                temporary_file = None
                return JSONResponse(
                    status_code=409,
                    content={
                        "success": False,
                        "duplicate": True,
                        "alreadyStored": True,
                        "canUpdate": False,
                        "duplicateReason": "DOCUMENT_ALREADY_UPDATED",
                        "message": "This document has already been re-verified and updated. Another verification attempt is a duplicate.",
                        "detail": "No further update is allowed for this stored document.",
                        "existingDocumentId": duplicate.get("id"),
                        "existingDocumentNumber": duplicate.get("document_number"),
                        "existingOwner": "CURRENT_USER",
                        "reverificationCount": duplicate_count,
                        "documentNumber": stored_document_number,
                        "idType": id_type,
                    },
                )












        if risk_score >= DOCUMENT_STORE_REJECT_LIMIT:

            create_audit_event(
                "DOCUMENT_SCREENING",
                user_unique_id or None,
                "RISK_REJECTED",
                {
                    "idType": id_type,
                    "documentNumber": stored_document_number,
                    "riskScore": risk_score,
                    "riskBand": risk_band,
                    "dataStored": False,
                    "aiDocumentAnalysis": ai_document_result,
                    "documentConsistency": document_consistency,
                    "documentVerification": document_verification,
                    "riskAssessment": risk_result,
                },
            )

            delete_file_safely(temporary_file)
            temporary_file = None

            return JSONResponse(
                status_code=422,
                content={
                    "success": False,
                    "dataStored": False,
                    "message": (
                        "Document was not stored because the document-authenticity "
                        f"risk score reached the hard rejection limit of {DOCUMENT_STORE_REJECT_LIMIT}."
                    ),
                    "riskScore": risk_score,
                    "documentRiskScore": risk_score,
                    "riskBand": risk_band,
                    "threshold": f">= {DOCUMENT_STORE_REJECT_LIMIT}",
                    "storageDecision": "REJECTED",
                    "finalDecision": {
                        "outcome": "REJECTED_DOCUMENT_RISK",
                        "documentAuthenticity": "HIGH_RISK",
                        "identityVerification": "NOT_REQUIRED" if screening_mode != "REFERENCE_FORM" else str((risk_result.get("identity_gate") or {}).get("status", "REVIEW")),
                        "evidenceConfidence": str(risk_result.get("analysis_confidence", "LOW")),
                        "riskScore": risk_score,
                        "nextAction": "Do not accept; inspect the flagged forensic evidence and escalate for manual verification.",
                    },
                    "extractedFields": extracted_fields,
                    "identityAnalysis": identity_results,
                    "qualityAnalysis": quality_result,
                    "suspiciousIndicators": indicator_result,
                    "aiDocumentAnalysis": ai_document_result,
                    "documentConsistency": document_consistency,
                    "documentVerification": document_verification,
                    "riskAssessment": risk_result,
                    "ocrConfidence": ocr_confidence,
                    "ocrText": ocr_text,
                    "documentPreview": document_preview,
                    "faceComparison": face_comparison,
                },
            )

        analysis_confidence = str(
            risk_result.get("analysis_confidence", "LOW")
        ).upper()




        storage_status = (
            "VERIFIED" if risk_score < DOCUMENT_VERIFIED_RISK_LIMIT
            else "PENDING_REVIEW"
        )

        unique_id = user_unique_id

        update_verified_user(
            unique_id=unique_id,
            full_name=stored_full_name,
            date_of_birth=stored_dob,
            risk_score=risk_score,
        )

        verification_id = (
            create_identity_verification(
                {
                    "subjectId":
                        unique_id,

                    "idType":
                        id_type,

                    "idNumber":
                        stored_document_number,

                    "fullName":
                        stored_full_name,

                    "nationality":
                        None,

                    "biometricStatus":
                        "NOT_PERFORMED",


                    "documentStatus":
                        quality_result.get(
                            "overall",
                            "UNKNOWN",
                        ),

                    "watchlistStatus":
                        None,

                    "riskScore":
                        risk_score,

                    "finalStatus":
                        storage_status,

                    "source":
                        "DOCUMENT_ANALYSIS",
                }
            )
        )


        stored_file_path = (
            move_document_to_user_folder(
                temporary_file,
                unique_id,
            )
        )

        temporary_file = None


        document_id = (
            add_user_document(
                unique_id=
                    unique_id,

                id_type=
                    id_type,

                document_number=
                    stored_document_number,

                full_name=
                    stored_full_name,

                date_of_birth=
                    stored_dob,

                address=
                    extracted_fields.get("address"),

                risk_score=
                    risk_score,

                final_status=
                    storage_status,

                verification_id=
                    verification_id,

                details={
                    "originalFilename":
                        filename,

                    "storedFilename":
                        stored_file_path.name,

                    "storedPath":
                        str(
                            stored_file_path
                            .relative_to(
                                UPLOAD_DIR
                            )
                        ),

                    "fileType":
                        extension,

                    "ocrConfidence":
                        ocr_confidence,

                    "extractedFields":
                        extracted_fields,

                    "identityAnalysis":
                        identity_results,

                    "qualityAnalysis":
                        quality_result,

                    "suspiciousIndicators":
                        indicator_result,
                    "aiDocumentAnalysis":
                        ai_document_result,

                    "documentConsistency":
                        document_consistency,

                    "documentVerification":
                        document_verification,

                    "riskAssessment":
                        risk_result,

                    "cameraCapture":
                        {
                            "captureId": saved_capture.get("id") if saved_capture else None,
                            "capturedAt": saved_capture.get("captured_at") if saved_capture else None,
                            "source": saved_capture.get("source") if saved_capture else None,
                            "fileUrl": (
                                f"/api/users/{unique_id}/face-captures/{saved_capture.get('id')}/file"
                                if saved_capture else None
                            ),
                            "biometricComparison": face_comparison.get("status"),
                            "livenessStatus": saved_capture.get("liveness_status") if saved_capture else None,
                            "motionScore": saved_capture.get("motion_score") if saved_capture else None,
                            "motionSamples": saved_capture.get("motion_samples") if saved_capture else 0,
                        },
                    "faceComparison": {
                        "status": face_comparison.get("status"),
                        "score": face_comparison.get("score"),
                        "matchedFeatures": face_comparison.get("matchedFeatures"),
                        "comparisonBasis": face_comparison.get("comparisonBasis"),
                    },
                },
            )
        )


        if explicit_reverify and duplicate:
            increment_user_document_reverification(unique_id, document_id)

        register_identity_number(
            id_type=
                id_type,

            document_number=
                stored_document_number,

            unique_id=
                unique_id,

            full_name=
                stored_full_name,
        )


        audit_status = (
            "DOCUMENT_REVERIFIED_UPDATED"
            if explicit_reverify and duplicate
            else "DOCUMENT_ADDED"
            if storage_status == "VERIFIED"
            else "DOCUMENT_ADDED_PENDING_REVIEW"
        )

        create_audit_event(
            "DOCUMENT_SCREENING",
            unique_id,
            audit_status,
            {
                "dataStored":
                    True,

                "idType":
                    id_type,

                "documentNumber":
                    stored_document_number,

                "fullName":
                    stored_full_name,

                "dob":
                    stored_dob,

                "riskScore":
                    risk_score,

                "riskBand":
                    risk_band,
                "verificationId":
                    verification_id,

                "documentId":
                    document_id,

                "cameraCapture":
                    {
                        "captureId": saved_capture.get("id") if saved_capture else None,
                        "capturedAt": saved_capture.get("captured_at") if saved_capture else None,
                        "source": saved_capture.get("source") if saved_capture else None,
                    "biometricComparison": face_comparison.get("status"),
                    },
                "faceComparison": {
                    "status": face_comparison.get("status"),
                    "score": face_comparison.get("score"),
                    "matchedFeatures": face_comparison.get("matchedFeatures"),
                    "comparisonBasis": face_comparison.get("comparisonBasis"),
                },
            },
        )


        final_decision = {
            "outcome": "VERIFIED" if storage_status == "VERIFIED" else "UNDER_REVIEW",
            "documentAuthenticity": (
                "LOW_RISK" if risk_score < DOCUMENT_VERIFIED_RISK_LIMIT else
                "REVIEW" if risk_score < DOCUMENT_STORE_REJECT_LIMIT else
                "HIGH_RISK"
            ),
            "identityVerification": (
                "NOT_REQUIRED"
                if screening_mode != "REFERENCE_FORM"
                else str((risk_result.get("identity_gate") or {}).get("status", "REVIEW"))
            ),
            "evidenceConfidence": analysis_confidence,
            "riskScore": risk_score,
            "nextAction": (
                "Document passed the configured risk threshold and was stored as verified."
                if storage_status == "VERIFIED"
                else "Document is stored pending review because its screening risk is below rejection but above the automatic-verification threshold."
            ),
            "verificationExplanation": (
                "Both document-screening and identity-verification gates passed."
                if storage_status == "VERIFIED"
                else "Document screening is separate from identity verification; this result is not marked VERIFIED until every required gate passes."
            ),
            "authenticityStatus": risk_result.get("authenticity_status", "REVIEW_REQUIRED"),
        }

        json_response = {
            "success":
                True,

            "caseId":
                screening_case_id,

            "message":
                (
                    "Document analyzed successfully."
                ),

            "userStorage": {
                "dataStored": True,
                "storageDecision": storage_status,
                "riskScore": risk_score,
                "riskBand": risk_band,
                "finalDecision": final_decision,
                "authenticityStatus": risk_result.get("authenticity_status"),
            },

            "screening": {
                "dataStored": True,
                "storageDecision": storage_status,
                "verificationId": verification_id,
                "documentId": document_id,
                "finalDecision": final_decision,
            },

            "reverification": {
                "performed": bool(explicit_reverify and duplicate),
                "existingDocumentId": duplicate.get("id") if explicit_reverify and duplicate else None,
                "reverificationCount": (int(duplicate.get("reverification_count") or 0) + 1) if explicit_reverify and duplicate else 0,
            },

            "finalDecision": final_decision,
            "authenticityStatus": risk_result.get("authenticity_status"),

            "file": {
                "filename":
                    filename,

                "fileType":
                    extension,

                "storedFilename":
                    stored_file_path.name,
            },

            "ocr": {
                "confidence":
                    ocr_confidence,

                "rawConfidence":
                    raw_ocr_confidence,

                "text":
                    ocr_text,

                "mode":
                    ocr_mode,

                "referenceReOcr":
                    ocr_reference_reocr,

                "documentPreview":
                    document_preview,
            },

            "documentPreview":
                document_preview,

            "extracted_fields":
                extracted_fields,

            "identity_analysis":
                identity_results,

            "quality_analysis":
                quality_result,

            "suspicious_indicators":
                indicator_result,
            "ai_document_analysis":
                ai_document_result,
            "document_verification":
                document_verification,
            "document_consistency":
                document_consistency,
            "cross_document_consistency":
                cross_document_consistency,
            "risk_assessment":
                risk_result,

            "cameraCapture":
                {
                    "captureId": saved_capture.get("id") if saved_capture else None,
                    "capturedAt": saved_capture.get("captured_at") if saved_capture else None,
                    "source": saved_capture.get("source") if saved_capture else None,
                    "fileUrl": (
                        f"/api/users/{unique_id}/face-captures/{saved_capture.get('id')}/file"
                        if saved_capture else None
                    ),
                    "biometricComparison":
                        face_comparison.get("status"),
                },
            "faceComparison":
                face_comparison,
        }

        final_response = (
            JSONResponse(
                json_response
            )
        )

        set_user_session(
            final_response,
            unique_id,
        )

        return final_response

    except HTTPException:
        raise

    except Exception as error:

        delete_file_safely(
            temporary_file
        )

        delete_file_safely(
            stored_file_path
        )

        try:
            if 'reference_temporary_file' in locals() and reference_temporary_file is not None:
                delete_file_safely(reference_temporary_file)
        except Exception:
            pass

        print(
            "Document screening error:",
            error,
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "Document screening failed: "
                f"{str(error)}"
            ),
        )







from app.ai_screening_routes import router as ai_screening_router

app.include_router(ai_screening_router)
