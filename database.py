import os
import re
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone

from werkzeug.security import check_password_hash, generate_password_hash

DB_PATH = os.path.join(os.path.dirname(__file__), "users.db")

DEFAULT_USER = {
    "name": "Shahzeb",
    "email": "shahzeb2003@gmail.com",
    "phone": "03000000000",
    "password": "12340000",
}


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                phone TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        row = conn.execute(
            "SELECT id FROM users WHERE email = ?", (DEFAULT_USER["email"],)
        ).fetchone()
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS password_otps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                otp_hash TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        row = conn.execute(
            "SELECT id FROM users WHERE email = ?", (DEFAULT_USER["email"],)
        ).fetchone()
        if not row:
            conn.execute(
                """
                INSERT INTO users (name, email, phone, password_hash, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    DEFAULT_USER["name"],
                    DEFAULT_USER["email"],
                    DEFAULT_USER["phone"],
                    generate_password_hash(DEFAULT_USER["password"]),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def normalize_phone(phone: str) -> str:
    return re.sub(r"\D", "", phone or "")


def validate_signup(name, email, phone, password, confirm_password):
    errors = []
    name = (name or "").strip()
    email = normalize_email(email)
    phone_digits = normalize_phone(phone)

    if len(name) < 2:
        errors.append("Name must be at least 2 characters.")
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        errors.append("Enter a valid email address.")
    if len(phone_digits) < 10:
        errors.append("Phone number must be at least 10 digits.")
    if len(password or "") < 8:
        errors.append("Password must be at least 8 characters.")
    if password != confirm_password:
        errors.append("Passwords do not match.")

    return errors, name, email, phone_digits


def create_user(name, email, phone, password, confirm_password):
    errors, name, email, phone_digits = validate_signup(
        name, email, phone, password, confirm_password
    )
    if errors:
        return False, errors[0]

    with get_conn() as conn:
        exists = conn.execute(
            "SELECT id FROM users WHERE email = ?", (email,)
        ).fetchone()
        if exists:
            return False, "An account with this email already exists."

        conn.execute(
            """
            INSERT INTO users (name, email, phone, password_hash, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                name,
                email,
                phone_digits,
                generate_password_hash(password),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
    return True, None


def authenticate(email, password):
    email = normalize_email(email)
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, name, email, phone, password_hash FROM users WHERE email = ?",
            (email,),
        ).fetchone()
    if not row or not check_password_hash(row["password_hash"], password):
        return None
    return dict(row)


def get_user_by_email(email):
    email = normalize_email(email)
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, name, email, phone FROM users WHERE email = ?", (email,)
        ).fetchone()
    return dict(row) if row else None


def _generate_otp_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def create_password_otp(email: str) -> tuple[bool, str | None, str | None]:
    """Create OTP for email. Returns (ok, error_message, plain_otp_for_sending)."""
    email = normalize_email(email)
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        return False, "Enter a valid email address.", None

    user = get_user_by_email(email)
    if not user:
        return False, "No account found with this email.", None

    otp = _generate_otp_code()
    expires = datetime.now(timezone.utc) + timedelta(minutes=10)
    now = datetime.now(timezone.utc).isoformat()
    expires_iso = expires.isoformat()

    with get_conn() as conn:
        conn.execute("DELETE FROM password_otps WHERE email = ?", (email,))
        conn.execute(
            """
            INSERT INTO password_otps (email, otp_hash, expires_at, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (email, generate_password_hash(otp), expires_iso, now),
        )

    return True, None, otp


def verify_otp_and_reset_password(email, otp, password, confirm_password):
    email = normalize_email(email)
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        return False, "Enter a valid email address."
    otp = (otp or "").strip()
    if not re.match(r"^\d{6}$", otp):
        return False, "Enter the 6-digit OTP from your email."
    if len(password or "") < 8:
        return False, "Password must be at least 8 characters."
    if password != confirm_password:
        return False, "Passwords do not match."

    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT otp_hash, expires_at FROM password_otps
            WHERE email = ? ORDER BY id DESC LIMIT 1
            """,
            (email,),
        ).fetchone()
        if not row:
            return False, "No OTP found. Request a new code from the forgot password page."

        expires = datetime.fromisoformat(row["expires_at"])
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > expires:
            conn.execute("DELETE FROM password_otps WHERE email = ?", (email,))
            return False, "OTP has expired. Please request a new one."

        if not check_password_hash(row["otp_hash"], otp):
            return False, "Invalid OTP. Check the code in your email."

        user = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if not user:
            return False, "Account not found."

        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (generate_password_hash(password), user["id"]),
        )
        conn.execute("DELETE FROM password_otps WHERE email = ?", (email,))

    return True, None


def get_user_by_id(user_id):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, name, email, phone FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    return dict(row) if row else None
