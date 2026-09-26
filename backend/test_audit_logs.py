import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def test_audit_and_auth_rows_keep_distinct_log_sources(tmp_path, monkeypatch):
    from app import database

    db_path = tmp_path / "audit-test.db"
    monkeypatch.setattr(database, "DATABASE_PATH", db_path)
    database.init_database()
    database.create_verified_user(
        "1234567890", "Test User", "01/01/2000", "Sample City", 5,
        email="test@example.com", password_hash="hash", email_verified=True,
    )
    audit_id = database.create_audit_event(
        "DOCUMENT_SCREENING", "1234567890", "DOCUMENT_ADDED", {"idType": "PAN"}
    )
    database.create_auth_event("test@example.com", "LOGIN", True, {"ok": True})

    rows = database.get_audit_logs("1234567890")
    screening = [row for row in rows if row["event_type"] in {"DOCUMENT_SCREENING", "LOGIN"}]
    assert {row["log_source"] for row in screening} == {"AUDIT", "AUTH"}
    assert any(row["log_source"] == "AUDIT" and row["log_id"] == audit_id for row in screening)
