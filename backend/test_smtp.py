from __future__ import annotations

import os
import socket
import smtplib
import ssl
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


def run_diagnostic() -> int:
    base_dir = Path(__file__).resolve().parent
    env_file = base_dir / ".env"
    if load_dotenv is not None and env_file.exists():
        load_dotenv(env_file)

    host = os.getenv("VERIFYSHIELD_SMTP_HOST", "smtp.gmail.com").strip()
    port = int(os.getenv("VERIFYSHIELD_SMTP_PORT", "587") or "587")
    username = os.getenv("VERIFYSHIELD_SMTP_USERNAME", "").strip()
    password = os.getenv("VERIFYSHIELD_SMTP_PASSWORD", "").strip()
    from_email = os.getenv("VERIFYSHIELD_SMTP_FROM_EMAIL", username).strip()
    use_tls = os.getenv("VERIFYSHIELD_SMTP_USE_TLS", "true").strip().lower() in {"1", "true", "yes", "on"}

    print("=" * 60)
    print("SMTP DIAGNOSTIC TEST")
    print("=" * 60)
    print(f"SMTP Host      : {host}")
    print(f"SMTP Port      : {port}")
    print(f"SMTP Username  : {username}")
    print(f"From Email     : {from_email}")
    print(f"TLS Enabled    : {use_tls}")
    print(f"Password Set   : {'YES' if password else 'NO'}")

    if not username or not password:
        print("SMTP credentials are not configured; nothing to test.")
        print("Set VERIFYSHIELD_SMTP_USERNAME / VERIFYSHIELD_SMTP_PASSWORD in backend/.env first.")
        return 0

    try:
        resolved = socket.gethostbyname_ex(host)
        print(f"PASS: DNS resolved {resolved[0]} -> {resolved[2]}")
    except socket.gaierror as exc:
        print(f"FAIL: DNS resolution failed: {exc}")
        return 1

    context = ssl.create_default_context()
    try:
        if port == 465 and not use_tls:
            with smtplib.SMTP_SSL(host, port, timeout=20, context=context) as server:
                server.ehlo()
                server.login(username, password)
        else:
            with smtplib.SMTP(host, port, timeout=20) as server:
                server.ehlo()
                if use_tls:
                    server.starttls(context=context)
                    server.ehlo()
                server.login(username, password)
        print("PASS: SMTP authentication succeeded.")
        return 0
    except Exception as exc:
        print(f"FAIL: SMTP test failed: {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(run_diagnostic())
