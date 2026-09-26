
import sqlite3
import json
import secrets

from pathlib import Path
from datetime import datetime


                                                           
                   
                                                           

BASE_DIR = Path(
    __file__
).resolve().parent.parent

DATABASE_PATH = (
    BASE_DIR /
    "drishti_ai.db"
)


                                                           
            
                                                           

def get_connection():
    connection = sqlite3.connect(
        DATABASE_PATH,
    )

    connection.row_factory = (
        sqlite3.Row
    )

    connection.execute(
        "PRAGMA foreign_keys = ON"
    )

    return connection


                                                           
                         
                                                           

def init_database():

    connection = get_connection()

    cursor = connection.cursor()

                                                           
                
                                                           

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_logs (
            log_id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            event_type TEXT NOT NULL,
            subject_id TEXT,
            status TEXT,
            details TEXT
        )
        """
    )

                                                           
                                   
                                                           

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS identity_verifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            subject_id TEXT,
            id_type TEXT,
            id_number TEXT,
            full_name TEXT,
            nationality TEXT,
            biometric_status TEXT,
            document_status TEXT,
            watchlist_status TEXT,
            risk_score TEXT,
            final_status TEXT,
            source TEXT
        )
        """
    )

                                                           
                    
                                                           

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS verified_users (
            unique_id TEXT PRIMARY KEY,

            full_name TEXT,

            date_of_birth TEXT,

            address TEXT,

            created_at TEXT NOT NULL,

            updated_at TEXT NOT NULL,

            latest_risk_score INTEGER,

            status TEXT NOT NULL,

            email TEXT,

            password_hash TEXT,

            email_verified INTEGER NOT NULL DEFAULT 0,

            mfa_enabled INTEGER NOT NULL DEFAULT 0

        )
        """
    )

                                                           
                    
                                                           

    existing_columns = {
        row[1]
        for row in cursor.execute("PRAGMA table_info(verified_users)").fetchall()
    }

    auth_columns = {
        "email": "TEXT",
        "password_hash": "TEXT",
        "email_verified": "INTEGER NOT NULL DEFAULT 0",
        "mfa_enabled": "INTEGER NOT NULL DEFAULT 0",
    }

    for column_name, column_definition in auth_columns.items():
        if column_name not in existing_columns:
            cursor.execute(
                f"ALTER TABLE verified_users ADD COLUMN {column_name} {column_definition}"
            )

    cursor.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_verified_users_email
        ON verified_users(email)
        WHERE email IS NOT NULL AND email <> ''
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unique_id TEXT NOT NULL,
            token_hash TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            used_at TEXT,
            FOREIGN KEY (unique_id) REFERENCES verified_users(unique_id) ON DELETE CASCADE
        )
        """
    )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_user
        ON password_reset_tokens(unique_id)
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS auth_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            email TEXT,
            event_type TEXT NOT NULL,
            success INTEGER NOT NULL DEFAULT 0,
            details TEXT
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS email_otps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            purpose TEXT NOT NULL,
            otp_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            used_at TEXT
        )
        """
    )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_email_otps_lookup
        ON email_otps(email, purpose, used_at)
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS identity_registry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_type TEXT NOT NULL,
            document_number_normalized TEXT NOT NULL UNIQUE,
            unique_id TEXT NOT NULL,
            full_name TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (unique_id) REFERENCES verified_users(unique_id)
        )
        """
    )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_identity_registry_type_number
        ON identity_registry(id_type, document_number_normalized)
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS face_captures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unique_id TEXT NOT NULL,
            captured_at TEXT NOT NULL,
            original_filename TEXT,
            stored_filename TEXT NOT NULL,
            stored_path TEXT NOT NULL,
            mime_type TEXT NOT NULL DEFAULT 'image/jpeg',
            sha256 TEXT NOT NULL,
            file_size INTEGER NOT NULL,
            source TEXT NOT NULL DEFAULT 'BROWSER_CAMERA',
            FOREIGN KEY (unique_id) REFERENCES verified_users(unique_id)
                ON DELETE CASCADE
        )
        """
    )

    face_columns = {row[1] for row in cursor.execute("PRAGMA table_info(face_captures)").fetchall()}
    face_migrations = {
        "liveness_status": "TEXT NOT NULL DEFAULT 'NOT_CHECKED'",
        "motion_score": "REAL",
        "motion_samples": "INTEGER NOT NULL DEFAULT 0",
    }
    for column_name, column_definition in face_migrations.items():
        if column_name not in face_columns:
            cursor.execute(f"ALTER TABLE face_captures ADD COLUMN {column_name} {column_definition}")

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_face_captures_user_time
        ON face_captures(unique_id, captured_at DESC)
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS user_documents (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            unique_id TEXT NOT NULL,

            id_type TEXT NOT NULL,

            document_number TEXT NOT NULL,

            document_number_normalized TEXT NOT NULL UNIQUE,

            full_name TEXT,

            date_of_birth TEXT,

            address TEXT,

            risk_score INTEGER NOT NULL,

            final_status TEXT NOT NULL,

            created_at TEXT NOT NULL,

            verification_id INTEGER,

            details TEXT,

            FOREIGN KEY (unique_id)
                REFERENCES verified_users(unique_id)
                ON DELETE CASCADE
        )
        """
    )

    user_document_columns = {row[1] for row in cursor.execute("PRAGMA table_info(user_documents)").fetchall()}
    if "reverification_count" not in user_document_columns:
        cursor.execute("ALTER TABLE user_documents ADD COLUMN reverification_count INTEGER NOT NULL DEFAULT 0")

    connection.commit()

    connection.close()


                                                           
              
                                                           

def create_audit_event(
    event_type,
    subject_id,
    status,
    details,
):

    connection = get_connection()

    try:
        if isinstance(
            details,
            (dict, list),
        ):
            details = json.dumps(
                details,
            )

        cursor = connection.cursor()

        cursor.execute(
            """
            INSERT INTO audit_logs
            (
                created_at,
                event_type,
                subject_id,
                status,
                details
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                datetime.now().isoformat(),
                event_type,
                subject_id,
                status,
                details,
            ),
        )

        log_id = cursor.lastrowid

        connection.commit()

        return log_id

    finally:
        connection.close()


                                                           
                        
                                                           

def get_audit_logs(subject_id):
    connection = get_connection()
    try:
        user = connection.execute(
            "SELECT unique_id, email, full_name, email_verified, status FROM verified_users WHERE unique_id = ?",
            (subject_id,),
        ).fetchone()
        email = user["email"] if user else None
        rows = connection.execute(
            """
            SELECT log_id, created_at, event_type, subject_id, status, details,
                   'AUDIT' AS log_source
            FROM audit_logs
            WHERE subject_id = ?
              AND event_type = 'DOCUMENT_SCREENING'
            UNION ALL
            SELECT id AS log_id, created_at, event_type, email AS subject_id,
                   'SUCCESS' AS status, details,
                   'AUTH' AS log_source
            FROM auth_events
            WHERE email = ?
              AND event_type = 'LOGIN'
              AND success = 1
            ORDER BY created_at DESC, log_id DESC
            """,
            (subject_id, email or ""),
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            details = item.get("details")
            if isinstance(details, str):
                try: details = json.loads(details)
                except Exception: details = {}
            if not isinstance(details, dict): details = {}
            details["user"] = {
                "uniqueId": subject_id,
                "email": email,
                "fullName": user["full_name"] if user else None,
                "emailVerified": bool(user["email_verified"]) if user else False,
                "status": user["status"] if user else None,
            }
            item["details"] = json.dumps(details)
            result.append(item)
        return result
    finally:
        connection.close()


def create_identity_verification(
    data,
):

    connection = get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute(
            """
            INSERT INTO identity_verifications
            (
                created_at,
                subject_id,
                id_type,
                id_number,
                full_name,
                nationality,
                biometric_status,
                document_status,
                watchlist_status,
                risk_score,
                final_status,
                source
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now().isoformat(),

                data.get(
                    "subjectId"
                ),

                data.get(
                    "idType"
                ),

                data.get(
                    "idNumber"
                ),

                data.get(
                    "fullName"
                ),

                data.get(
                    "nationality"
                ),

                data.get(
                    "biometricStatus"
                ),

                data.get(
                    "documentStatus"
                ),

                data.get(
                    "watchlistStatus"
                ),

                data.get(
                    "riskScore"
                ),

                data.get(
                    "finalStatus"
                ),

                data.get(
                    "source"
                ),
            ),
        )

        verification_id = (
            cursor.lastrowid
        )

        connection.commit()

        return verification_id

    finally:
        connection.close()


                                                           
                               
                                                           

def normalize_document_number(
    document_number,
):
    if document_number is None:
        return ""

    value = str(
        document_number
    ).strip().upper()

    return "".join(
        character
        for character in value
        if character.isalnum()
    )


                                                           
                  
                                                           

def generate_unique_user_id():

    connection = get_connection()

    try:
        cursor = connection.cursor()

        while True:

            first_digit = str(
                secrets.randbelow(9) + 1
            )

            remaining_digits = "".join(
                str(
                    secrets.randbelow(10)
                )
                for _ in range(9)
            )

            unique_id = (
                first_digit +
                remaining_digits
            )

            existing = cursor.execute(
                """
                SELECT unique_id
                FROM verified_users
                WHERE unique_id = ?
                """,
                (
                    unique_id,
                ),
            ).fetchone()

            if existing is None:
                return unique_id

    finally:
        connection.close()


                                                           
             
                                                           

def normalize_email(email):
    if email is None:
        return ""
    return str(email).strip().lower()


def find_verified_user_by_email(email):
    normalized_email = normalize_email(email)
    if not normalized_email:
        return None

    connection = get_connection()
    try:
        row = connection.execute(
            """
            SELECT
                unique_id, full_name, date_of_birth, address,
                created_at, updated_at, latest_risk_score, status,
                email, password_hash, email_verified, mfa_enabled
            FROM verified_users
            WHERE email = ?
            """,
            (normalized_email,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        connection.close()


def create_password_reset_token(unique_id, token_hash, expires_at):
    connection = get_connection()
    try:
        connection.execute(
            "DELETE FROM password_reset_tokens WHERE unique_id = ? AND used_at IS NULL",
            (unique_id,),
        )
        connection.execute(
            """
            INSERT INTO password_reset_tokens
            (unique_id, token_hash, created_at, expires_at, used_at)
            VALUES (?, ?, ?, ?, NULL)
            """,
            (unique_id, token_hash, datetime.now().isoformat(), expires_at),
        )
        connection.commit()
    finally:
        connection.close()


def find_password_reset_token(token_hash):
    connection = get_connection()
    try:
        row = connection.execute(
            """
            SELECT id, unique_id, token_hash, created_at, expires_at, used_at
            FROM password_reset_tokens
            WHERE token_hash = ?
            """,
            (token_hash,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        connection.close()


def mark_password_reset_token_used(token_hash):
    connection = get_connection()
    try:
        connection.execute(
            "UPDATE password_reset_tokens SET used_at = ? WHERE token_hash = ? AND used_at IS NULL",
            (datetime.now().isoformat(), token_hash),
        )
        connection.commit()
    finally:
        connection.close()



def create_otp_record(email, purpose, otp_hash, expires_at):
    connection = get_connection()
    try:
        connection.execute(
            "DELETE FROM email_otps WHERE email = ? AND purpose = ? AND used_at IS NULL",
            (normalize_email(email), purpose),
        )
        connection.execute(
            """
            INSERT INTO email_otps (email, purpose, otp_hash, created_at, expires_at, used_at)
            VALUES (?, ?, ?, ?, ?, NULL)
            """,
            (normalize_email(email), purpose, otp_hash, datetime.now().isoformat(), expires_at),
        )
        connection.commit()
    finally:
        connection.close()


def find_active_otp(email, purpose):
    connection = get_connection()
    try:
        row = connection.execute(
            """
            SELECT id, email, purpose, otp_hash, created_at, expires_at, used_at
            FROM email_otps
            WHERE email = ? AND purpose = ? AND used_at IS NULL
            ORDER BY id DESC LIMIT 1
            """,
            (normalize_email(email), purpose),
        ).fetchone()
        return dict(row) if row else None
    finally:
        connection.close()


def mark_otp_used(otp_id):
    connection = get_connection()
    try:
        connection.execute(
            "UPDATE email_otps SET used_at = ? WHERE id = ? AND used_at IS NULL",
            (datetime.now().isoformat(), otp_id),
        )
        connection.commit()
    finally:
        connection.close()


def create_auth_event(email, event_type, success, details=None):
    connection = get_connection()
    try:
        if isinstance(details, (dict, list)):
            details = json.dumps(details)
        connection.execute(
            """
            INSERT INTO auth_events
            (created_at, email, event_type, success, details)
            VALUES (?, ?, ?, ?, ?)
            """,
            (datetime.now().isoformat(), normalize_email(email) if email else None, event_type, 1 if success else 0, details),
        )
        connection.commit()
    finally:
        connection.close()


def find_verified_user(unique_id):
    if not unique_id:
        return None

    connection = get_connection()
    try:
        row = connection.execute(
            """
            SELECT
                unique_id, full_name, date_of_birth, address,
                created_at, updated_at, latest_risk_score, status,
                email, password_hash, email_verified, mfa_enabled
            FROM verified_users
            WHERE unique_id = ?
            """,
            (str(unique_id).strip(),),
        ).fetchone()
        return dict(row) if row else None
    finally:
        connection.close()


def create_verified_user(
    unique_id,
    full_name,
    date_of_birth,
    address,
    risk_score,
    email=None,
    password_hash=None,
    email_verified=False,
    mfa_enabled=False,
):
    normalized_email = normalize_email(email) if email else None
    connection = get_connection()
    try:
        connection.execute(
            """
            INSERT INTO verified_users
            (
                unique_id, full_name, date_of_birth, address,
                created_at, updated_at, latest_risk_score, status,
                email, password_hash, email_verified, mfa_enabled
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                unique_id, full_name, date_of_birth, address,
                datetime.now().isoformat(), datetime.now().isoformat(),
                risk_score, "ACTIVE", normalized_email, password_hash,
                1 if email_verified else 0, 1 if mfa_enabled else 0,
            ),
        )
        connection.commit()
    finally:
        connection.close()


def update_verified_user(
    unique_id,
    full_name=None,
    date_of_birth=None,
    address=None,
    risk_score=None,
    email=None,
    password_hash=None,
    email_verified=None,
    mfa_enabled=None,
):
    connection = get_connection()
    try:
        existing = connection.execute(
            """
            SELECT full_name, date_of_birth, address, latest_risk_score,
                   email, password_hash, email_verified, mfa_enabled
            FROM verified_users
            WHERE unique_id = ?
            """,
            (unique_id,),
        ).fetchone()
        if existing is None:
            return False

        updated_name = full_name if full_name else existing["full_name"]
        updated_dob = date_of_birth if date_of_birth else existing["date_of_birth"]
        updated_address = address if address else existing["address"]
        updated_risk_score = risk_score if risk_score is not None else existing["latest_risk_score"]
        updated_email = normalize_email(email) if email is not None else existing["email"]
        updated_password_hash = password_hash if password_hash is not None else existing["password_hash"]
        updated_email_verified = (1 if email_verified else 0) if email_verified is not None else existing["email_verified"]
        updated_mfa_enabled = (1 if mfa_enabled else 0) if mfa_enabled is not None else existing["mfa_enabled"]

        connection.execute(
            """
            UPDATE verified_users
            SET full_name = ?, date_of_birth = ?, address = ?, updated_at = ?,
                latest_risk_score = ?, email = ?, password_hash = ?,
                email_verified = ?, mfa_enabled = ?
            WHERE unique_id = ?
            """,
            (
                updated_name, updated_dob, updated_address, datetime.now().isoformat(),
                updated_risk_score, updated_email, updated_password_hash,
                updated_email_verified, updated_mfa_enabled, unique_id,
            ),
        )
        connection.commit()
        return True
    finally:
        connection.close()


def find_identity_registry_by_number(
    id_type,
    document_number,
):
    normalized = normalize_document_number(document_number)
    if not normalized or not id_type:
        return None

    connection = get_connection()
    try:
        row = connection.execute(
            """
            SELECT id, id_type, document_number_normalized, unique_id,
                   full_name, created_at, updated_at
            FROM identity_registry
            WHERE id_type = ? AND document_number_normalized = ?
            """,
            (str(id_type).strip().upper(), normalized),
        ).fetchone()
        return dict(row) if row else None
    finally:
        connection.close()


def register_identity_number(
    id_type,
    document_number,
    unique_id,
    full_name=None,
):
    normalized = normalize_document_number(document_number)
    if not normalized or not id_type or not unique_id:
        return

    now = datetime.now().isoformat()
    connection = get_connection()
    try:
        connection.execute(
            """
            INSERT INTO identity_registry
                (id_type, document_number_normalized, unique_id, full_name, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(document_number_normalized) DO UPDATE SET
                unique_id = excluded.unique_id,
                full_name = COALESCE(excluded.full_name, identity_registry.full_name),
                updated_at = excluded.updated_at
            """,
            (str(id_type).strip().upper(), normalized, unique_id, full_name, now, now),
        )
        connection.commit()
    finally:
        connection.close()


def normalize_document_holder_name(
    full_name,
):
    if full_name is None:
        return ""

    value = str(full_name).strip().upper()

    return "".join(
        character
        for character in value
        if character.isalnum()
    )


def find_user_document_by_name_and_type(
    unique_id,
    id_type,
    full_name,
):
    normalized_name = normalize_document_holder_name(full_name)

    if not unique_id or not id_type or not normalized_name:
        return None

    connection = get_connection()

    try:
        rows = connection.execute(
            """
            SELECT
                id,
                unique_id,
                id_type,
                document_number,
                document_number_normalized,
                full_name,
                date_of_birth,
                address,
                risk_score,
                final_status,
                created_at,
                verification_id,
                details,
                reverification_count
            FROM user_documents
            WHERE unique_id = ?
              AND UPPER(id_type) = ?
            ORDER BY id DESC
            """,
            (unique_id, str(id_type).strip().upper()),
        ).fetchall()

        for row in rows:
            document = dict(row)
            if normalize_document_holder_name(document.get("full_name")) == normalized_name:
                return document

        return None

    finally:
        connection.close()


def delete_user_document(
    unique_id,
    document_id,
):
    connection = get_connection()

    try:
        row = connection.execute(
            """
            SELECT
                id,
                unique_id,
                verification_id,
                details,
                reverification_count
            FROM user_documents
            WHERE id = ? AND unique_id = ?
            """,
            (int(document_id), unique_id),
        ).fetchone()

        if row is None:
            return None

        document = dict(row)

        identity_row = connection.execute(
            """
            SELECT id_type, document_number_normalized
            FROM user_documents
            WHERE id = ? AND unique_id = ?
            """,
            (int(document_id), unique_id),
        ).fetchone()

        connection.execute(
            "DELETE FROM user_documents WHERE id = ? AND unique_id = ?",
            (int(document_id), unique_id),
        )


        if identity_row:
            connection.execute(
                """
                DELETE FROM identity_registry
                WHERE id_type = ? AND document_number_normalized = ?
                """,
                (identity_row["id_type"], identity_row["document_number_normalized"]),
            )

        verification_id = document.get("verification_id")
        if verification_id:
            connection.execute(
                "DELETE FROM identity_verifications WHERE id = ? AND subject_id = ?",
                (int(verification_id), unique_id),
            )

        connection.commit()
        return document

    finally:
        connection.close()


def find_document_by_number(
    document_number,
):

    normalized = (
        normalize_document_number(
            document_number,
        )
    )

    if not normalized:
        return None

    connection = get_connection()

    try:
        row = connection.execute(
            """
            SELECT
                id,
                unique_id,
                id_type,
                document_number,
                document_number_normalized,
                full_name,
                date_of_birth,
                address,
                risk_score,
                final_status,
                created_at,
                verification_id,
                details,
                reverification_count
            FROM user_documents
            WHERE document_number_normalized = ?
            """,
            (
                normalized,
            ),
        ).fetchone()

        return (
            dict(row)
            if row
            else None
        )

    finally:
        connection.close()


                                                           
                   
                                                           

def increment_user_document_reverification(unique_id, document_id):
    connection = get_connection()
    try:
        cursor = connection.cursor()
        row = cursor.execute(
            "SELECT reverification_count FROM user_documents WHERE id = ? AND unique_id = ?",
            (int(document_id), unique_id),
        ).fetchone()
        if row is None:
            return None
        new_count = int(row["reverification_count"] or 0) + 1
        cursor.execute(
            "UPDATE user_documents SET reverification_count = ? WHERE id = ? AND unique_id = ?",
            (new_count, int(document_id), unique_id),
        )
        connection.commit()
        return new_count
    finally:
        connection.close()


def add_user_document(
    unique_id,
    id_type,
    document_number,
    full_name,
    date_of_birth,
    address,
    risk_score,
    final_status,
    verification_id=None,
    details=None,
):

    normalized_document_number = (
        normalize_document_number(
            document_number,
        )
    )

    if not normalized_document_number:
        raise ValueError(
            "Document number cannot be empty."
        )

    if isinstance(
        details,
        (dict, list),
    ):
        details = json.dumps(
            details,
        )

    connection = get_connection()

    try:
        cursor = connection.cursor()

        existing = cursor.execute(
            """
            SELECT id, unique_id, id_type
            FROM user_documents
            WHERE document_number_normalized = ?
            """,
            (normalized_document_number,),
        ).fetchone()

        if existing is not None:
            if str(existing["unique_id"]) != str(unique_id):
                raise ValueError("This document number is already registered to another account.")

            cursor.execute(
                """
                UPDATE user_documents
                SET id_type = ?, full_name = ?, date_of_birth = ?, address = ?,
                    risk_score = ?, final_status = ?, created_at = ?,
                    verification_id = ?, details = ?
                WHERE id = ? AND unique_id = ?
                """,
                (
                    id_type, full_name, date_of_birth, address, risk_score,
                    final_status, datetime.now().isoformat(), verification_id, details,
                    existing["id"], unique_id,
                ),
            )
            connection.commit()
            return existing["id"]

        cursor.execute(
            """
            INSERT INTO user_documents
            (
                unique_id,
                id_type,
                document_number,
                document_number_normalized,
                full_name,
                date_of_birth,
                address,
                risk_score,
                final_status,
                created_at,
                verification_id,
                details
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                unique_id,
                id_type,
                document_number,
                normalized_document_number,
                full_name,
                date_of_birth,
                address,
                risk_score,
                final_status,
                datetime.now().isoformat(),
                verification_id,
                details,
            ),
        )

        document_id = (
            cursor.lastrowid
        )

        connection.commit()

        return document_id

    finally:
        connection.close()


                                                           
                    
                                                           

def get_user_documents(
    unique_id,
):

    connection = get_connection()

    try:
        rows = connection.execute(
            """
            SELECT
                id,
                unique_id,
                id_type,
                document_number,
                document_number_normalized,
                full_name,
                date_of_birth,
                address,
                risk_score,
                final_status,
                created_at,
                verification_id,
                details,
                reverification_count
            FROM user_documents
            WHERE unique_id = ?
            ORDER BY id DESC
            """,
            (
                unique_id,
            ),
        ).fetchall()

        return [
            dict(row)
            for row in rows
        ]

    finally:
        connection.close()


def search_verified_documents(query, limit=30):
    search_text = str(query or "").strip()
    if not search_text:
        return []

    normalized_query = normalize_document_number(search_text)
    like_query = f"%{search_text.lower()}%"
    normalized_like_query = f"%{normalized_query}%" if normalized_query else ""
    connection = get_connection()

    try:
        rows = connection.execute(
            """
            SELECT id, id_type, document_number, full_name, final_status, created_at
            FROM user_documents
            WHERE LOWER(COALESCE(full_name, '')) LIKE ?
               OR LOWER(COALESCE(id_type, '')) LIKE ?
               OR LOWER(COALESCE(document_number, '')) LIKE ?
               OR LOWER(COALESCE(document_number_normalized, '')) LIKE ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (like_query, like_query, like_query, normalized_like_query or like_query, int(limit)),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


                                                           
      
                                                           


def migrate_legacy_user_ids():
    connection = get_connection()
    try:
        users = connection.execute("SELECT unique_id, email FROM verified_users").fetchall()
        for row in users:
            old_id = str(row["unique_id"] or "").strip()
            email = str(row["email"] or "").strip().lower()
            if not email or old_id != email:
                continue
            new_id = generate_unique_user_id()
            connection.execute("UPDATE identity_verifications SET subject_id = ? WHERE subject_id = ?", (new_id, old_id))
            connection.execute("UPDATE user_documents SET unique_id = ? WHERE unique_id = ?", (new_id, old_id))
            connection.execute("UPDATE identity_registry SET unique_id = ? WHERE unique_id = ?", (new_id, old_id))
            connection.execute("UPDATE password_reset_tokens SET unique_id = ? WHERE unique_id = ?", (new_id, old_id))
            connection.execute("UPDATE audit_logs SET subject_id = ? WHERE subject_id = ?", (new_id, old_id))
            connection.execute("UPDATE verified_users SET unique_id = ? WHERE unique_id = ?", (new_id, old_id))
        connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_verified_users_email_unique ON verified_users(email) WHERE email IS NOT NULL AND email != ''")
        connection.commit()
    finally:
        connection.close()

init_database()
migrate_legacy_user_ids()


def add_face_capture(
    unique_id,
    stored_filename,
    stored_path,
    sha256,
    file_size,
    original_filename="camera-capture.jpg",
    mime_type="image/jpeg",
    liveness_status="PASSED",
    motion_score=None,
    motion_samples=0,
):
    connection = get_connection()
    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO face_captures
            (
                unique_id,
                captured_at,
                original_filename,
                stored_filename,
                stored_path,
                mime_type,
                sha256,
                file_size,
                source,
                liveness_status,
                motion_score,
                motion_samples
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                unique_id,
                datetime.now().isoformat(),
                original_filename,
                stored_filename,
                stored_path,
                mime_type,
                sha256,
                int(file_size),
                "BROWSER_CAMERA",
                str(liveness_status or "NOT_CHECKED"),
                float(motion_score) if motion_score is not None else None,
                int(motion_samples or 0),
            ),
        )
        capture_id = cursor.lastrowid
        connection.commit()
        return capture_id
    finally:
        connection.close()


def get_face_captures(unique_id, limit=20):
    connection = get_connection()
    try:
        rows = connection.execute(
            """
            SELECT id, unique_id, captured_at, original_filename,
                   stored_filename, stored_path, mime_type, sha256,
                   file_size, source, liveness_status, motion_score, motion_samples
            FROM face_captures
            WHERE unique_id = ?
            ORDER BY captured_at DESC, id DESC
            LIMIT ?
            """,
            (unique_id, int(limit)),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def get_face_capture(unique_id, capture_id):
    connection = get_connection()
    try:
        row = connection.execute(
            """
            SELECT id, unique_id, captured_at, original_filename,
                   stored_filename, stored_path, mime_type, sha256,
                   file_size, source, liveness_status, motion_score, motion_samples
            FROM face_captures
            WHERE unique_id = ? AND id = ?
            """,
            (unique_id, int(capture_id)),
        ).fetchone()
        return dict(row) if row else None
    finally:
        connection.close()
