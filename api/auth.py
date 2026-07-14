"""Authentication for Commute OS.

Email/phone + password accounts with email OTP verification on signup,
plus Google sign-in. Prototype notes:

- Users and sessions persist in SQLite (data/users.db).
- OTPs are kept in memory and expire after 10 minutes.
- If SMTP_* env vars are set, the OTP is emailed for real; otherwise it is
  printed to the backend console and echoed in the API response as
  ``dev_otp`` so the flow stays testable during development.
- Google credentials (JWT from Google Identity Services) are decoded without
  signature verification — wire google-auth before any production use.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import smtplib
import sqlite3
import threading
import time
from email.message import EmailMessage
from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field, field_validator

router = APIRouter(prefix="/auth", tags=["auth"])

USERS_DB = os.environ.get("COMMUTE_USERS_DB", "data/users.db")

OTP_TTL_SECONDS = 10 * 60
OTP_MAX_ATTEMPTS = 5
PHONE_RE = re.compile(r"^\+?[0-9]{10,13}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

_otp_lock = threading.Lock()
_pending_otps: dict[str, dict[str, Any]] = {}
_signup_tokens: dict[str, dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(USERS_DB) or ".", exist_ok=True)
    conn = sqlite3.connect(USERS_DB)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            phone TEXT UNIQUE,
            name TEXT,
            password_hash TEXT,
            salt TEXT,
            provider TEXT NOT NULL DEFAULT 'password',
            created_at REAL NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            created_at REAL NOT NULL
        )
        """
    )
    return conn


def _hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt), 200_000
    ).hex()


def _public_user(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "email": row["email"],
        "phone": row["phone"],
        "name": row["name"],
        "provider": row["provider"],
    }


def _create_session(conn: sqlite3.Connection, user_id: str) -> str:
    token = secrets.token_urlsafe(32)
    conn.execute(
        "INSERT INTO sessions (token, user_id, created_at) VALUES (?, ?, ?)",
        (token, user_id, time.time()),
    )
    conn.commit()
    return token


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------


def _send_otp_email(email: str, code: str) -> bool:
    """Send the OTP via SMTP. Returns False when SMTP is not configured."""
    host = os.environ.get("SMTP_HOST")
    if not host:
        print(f"[auth] SMTP not configured — OTP for {email}: {code}")
        return False
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASS")
    sender = os.environ.get("SMTP_FROM", user or "no-reply@commute-os.local")

    msg = EmailMessage()
    msg["Subject"] = "Your Commute OS verification code"
    msg["From"] = sender
    msg["To"] = email
    msg.set_content(
        f"Your Commute OS verification code is {code}.\n"
        f"It expires in 10 minutes. If you didn't request this, ignore this email."
    )
    with smtplib.SMTP(host, port, timeout=15) as server:
        server.starttls()
        if user and password:
            server.login(user, password)
        server.send_message(msg)
    return True


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class _EmailModel(BaseModel):
    @field_validator("email", check_fields=False)
    @classmethod
    def _valid_email(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and not EMAIL_RE.match(value.strip()):
            raise ValueError("Enter a valid email address.")
        return value


class RequestOtpBody(_EmailModel):
    email: str
    phone: str = Field(min_length=10, max_length=14)
    name: Optional[str] = None


class VerifyOtpBody(_EmailModel):
    email: str
    code: str = Field(min_length=6, max_length=6)


class CompleteSignupBody(_EmailModel):
    email: str
    signup_token: str
    password: str = Field(min_length=8, max_length=128)
    confirm_password: str


class LoginBody(BaseModel):
    identifier: str  # email or phone number
    password: str


class UpdateAccountBody(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None


class ChangePasswordBody(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)
    confirm_password: str


class GoogleBody(_EmailModel):
    credential: Optional[str] = None  # GIS ID token (JWT)
    email: Optional[str] = None  # demo fallback when GIS isn't configured
    name: Optional[str] = None


# ---------------------------------------------------------------------------
# Signup: request OTP -> verify OTP -> set password
# ---------------------------------------------------------------------------


@router.post("/signup/request-otp")
def signup_request_otp(body: RequestOtpBody) -> dict[str, Any]:
    email = body.email.lower().strip()
    phone = body.phone.strip().replace(" ", "")
    if not PHONE_RE.match(phone):
        raise HTTPException(status_code=400, detail="Enter a valid mobile number (10 digits).")

    conn = _connect()
    try:
        existing = conn.execute(
            "SELECT email, phone FROM users WHERE email = ? OR phone = ?",
            (email, phone),
        ).fetchone()
        if existing:
            field = "email" if existing["email"] == email else "mobile number"
            raise HTTPException(
                status_code=409,
                detail=f"An account with this {field} already exists. Please log in instead.",
            )
    finally:
        conn.close()

    code = f"{secrets.randbelow(1_000_000):06d}"
    with _otp_lock:
        _pending_otps[email] = {
            "code": code,
            "phone": phone,
            "name": (body.name or "").strip() or None,
            "expires_at": time.time() + OTP_TTL_SECONDS,
            "attempts": 0,
        }

    emailed = _send_otp_email(email, code)
    response: dict[str, Any] = {
        "message": f"Verification code sent to {email}."
        if emailed
        else "SMTP is not configured; using development OTP.",
        "email_sent": emailed,
    }
    if not emailed:
        response["dev_otp"] = code
    return response


@router.post("/signup/verify-otp")
def signup_verify_otp(body: VerifyOtpBody) -> dict[str, Any]:
    email = body.email.lower().strip()
    with _otp_lock:
        entry = _pending_otps.get(email)
        if entry is None:
            raise HTTPException(status_code=400, detail="No pending verification for this email. Request a new code.")
        if time.time() > entry["expires_at"]:
            _pending_otps.pop(email, None)
            raise HTTPException(status_code=400, detail="This code has expired. Request a new one.")
        if entry["attempts"] >= OTP_MAX_ATTEMPTS:
            _pending_otps.pop(email, None)
            raise HTTPException(status_code=429, detail="Too many incorrect attempts. Request a new code.")
        if not secrets.compare_digest(entry["code"], body.code.strip()):
            entry["attempts"] += 1
            remaining = OTP_MAX_ATTEMPTS - entry["attempts"]
            raise HTTPException(status_code=400, detail=f"Incorrect code. {remaining} attempts left.")

        _pending_otps.pop(email, None)
        signup_token = secrets.token_urlsafe(24)
        _signup_tokens[signup_token] = {
            "email": email,
            "phone": entry["phone"],
            "name": entry["name"],
            "expires_at": time.time() + OTP_TTL_SECONDS,
        }
    return {"message": "Email verified. Create your password.", "signup_token": signup_token}


@router.post("/signup/complete")
def signup_complete(body: CompleteSignupBody) -> dict[str, Any]:
    if body.password != body.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match.")

    with _otp_lock:
        pending = _signup_tokens.get(body.signup_token)
        if pending is None or pending["email"] != body.email.lower().strip():
            raise HTTPException(status_code=400, detail="Signup session is invalid. Start again.")
        if time.time() > pending["expires_at"]:
            _signup_tokens.pop(body.signup_token, None)
            raise HTTPException(status_code=400, detail="Signup session expired. Start again.")
        _signup_tokens.pop(body.signup_token, None)

    salt = secrets.token_hex(16)
    user_id = f"user-{secrets.token_hex(6)}"
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO users (id, email, phone, name, password_hash, salt, provider, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, 'password', ?)",
            (
                user_id,
                pending["email"],
                pending["phone"],
                pending["name"],
                _hash_password(body.password, salt),
                salt,
                time.time(),
            ),
        )
        conn.commit()
        token = _create_session(conn, user_id)
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return {"token": token, "user": _public_user(row)}
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Account already exists. Please log in.") from exc
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Login / Google / session
# ---------------------------------------------------------------------------


@router.post("/login")
def login(body: LoginBody) -> dict[str, Any]:
    identifier = body.identifier.lower().strip().replace(" ", "")
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE email = ? OR phone = ?",
            (identifier, identifier),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=401, detail="No account found for this email or mobile number.")
        if row["provider"] == "google" and not row["password_hash"]:
            raise HTTPException(status_code=400, detail="This account uses Google sign-in. Use 'Continue with Google'.")
        if not secrets.compare_digest(row["password_hash"], _hash_password(body.password, row["salt"])):
            raise HTTPException(status_code=401, detail="Incorrect password.")
        token = _create_session(conn, row["id"])
        return {"token": token, "user": _public_user(row)}
    finally:
        conn.close()


def _decode_google_credential(credential: str) -> dict[str, Any]:
    """Decode a GIS ID token payload. Prototype only: signature NOT verified."""
    try:
        payload_b64 = credential.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        return json.loads(base64.urlsafe_b64decode(payload_b64))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="Invalid Google credential.") from exc


@router.post("/google")
def google_sign_in(body: GoogleBody) -> dict[str, Any]:
    if body.credential:
        payload = _decode_google_credential(body.credential)
        email = (payload.get("email") or "").lower()
        name = payload.get("name")
        if not email:
            raise HTTPException(status_code=400, detail="Google credential has no email.")
    elif body.email:
        # Demo fallback when Google OAuth isn't configured on the frontend.
        email = body.email.lower().strip()
        name = body.name or "Google Demo User"
    else:
        raise HTTPException(status_code=400, detail="Provide a Google credential.")

    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if row is None:
            user_id = f"user-{secrets.token_hex(6)}"
            conn.execute(
                "INSERT INTO users (id, email, name, provider, created_at) VALUES (?, ?, ?, 'google', ?)",
                (user_id, email, name, time.time()),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        token = _create_session(conn, row["id"])
        return {"token": token, "user": _public_user(row)}
    finally:
        conn.close()


def _session_user(conn: sqlite3.Connection, authorization: Optional[str]) -> sqlite3.Row:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not signed in.")
    token = authorization.removeprefix("Bearer ").strip()
    row = conn.execute(
        "SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token = ?",
        (token,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=401, detail="Session expired. Sign in again.")
    return row


@router.get("/me")
def me(authorization: Optional[str] = Header(default=None)) -> dict[str, Any]:
    conn = _connect()
    try:
        return {"user": _public_user(_session_user(conn, authorization))}
    finally:
        conn.close()


@router.patch("/me")
def update_account(
    body: UpdateAccountBody, authorization: Optional[str] = Header(default=None)
) -> dict[str, Any]:
    conn = _connect()
    try:
        row = _session_user(conn, authorization)
        name = body.name.strip() if body.name is not None else row["name"]
        phone = row["phone"]
        if body.phone is not None:
            candidate = body.phone.strip().replace(" ", "")
            if candidate:
                if not PHONE_RE.match(candidate):
                    raise HTTPException(status_code=400, detail="Enter a valid mobile number (10 digits).")
                taken = conn.execute(
                    "SELECT 1 FROM users WHERE phone = ? AND id != ?", (candidate, row["id"])
                ).fetchone()
                if taken:
                    raise HTTPException(status_code=409, detail="This mobile number is used by another account.")
                phone = candidate
        conn.execute(
            "UPDATE users SET name = ?, phone = ? WHERE id = ?", (name or None, phone, row["id"])
        )
        conn.commit()
        updated = conn.execute("SELECT * FROM users WHERE id = ?", (row["id"],)).fetchone()
        return {"user": _public_user(updated), "message": "Account updated."}
    finally:
        conn.close()


@router.post("/change-password")
def change_password(
    body: ChangePasswordBody, authorization: Optional[str] = Header(default=None)
) -> dict[str, str]:
    if body.new_password != body.confirm_password:
        raise HTTPException(status_code=400, detail="New passwords do not match.")
    conn = _connect()
    try:
        row = _session_user(conn, authorization)
        if not row["password_hash"]:
            raise HTTPException(
                status_code=400,
                detail="This account uses Google sign-in and has no password.",
            )
        if not secrets.compare_digest(
            row["password_hash"], _hash_password(body.current_password, row["salt"])
        ):
            raise HTTPException(status_code=401, detail="Current password is incorrect.")
        salt = secrets.token_hex(16)
        conn.execute(
            "UPDATE users SET password_hash = ?, salt = ? WHERE id = ?",
            (_hash_password(body.new_password, salt), salt, row["id"]),
        )
        conn.commit()
        return {"message": "Password changed."}
    finally:
        conn.close()


@router.post("/logout")
def logout(authorization: Optional[str] = Header(default=None)) -> dict[str, str]:
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
        conn = _connect()
        try:
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
            conn.commit()
        finally:
            conn.close()
    return {"message": "Signed out."}
