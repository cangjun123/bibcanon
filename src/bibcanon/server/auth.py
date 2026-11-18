"""Lightweight authentication helpers (30-day HMAC cookie + HTTP Basic Auth) for cloud mode."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass

from fastapi import Request

SESSION_COOKIE_NAME = "bibcanon_session"
SESSION_TTL_SECONDS = 30 * 86400  # 30 days


@dataclass
class CloudSecurityConfig:
    """Security configuration when running bibcanon on a shared cloud server."""

    enabled: bool = False
    username: str = "admin"
    password: str = ""
    auto_generated_password: bool = False
    secret_key: str = ""

    def __post_init__(self) -> None:
        if self.enabled and not self.password:
            self.password = secrets.token_urlsafe(12)
            self.auto_generated_password = True
        if not self.secret_key:
            seed = f"bibcanon-cloud-v1:{self.username}:{self.password}"
            self.secret_key = hashlib.sha256(seed.encode("utf-8")).hexdigest()


def create_session_token(sec: CloudSecurityConfig) -> str:
    """Create a signed session token `<username>:<issued_ts>:<hmac_hex>`."""
    issued = str(int(time.time()))
    msg = f"{sec.username}:{issued}".encode("utf-8")
    sig = hmac.new(sec.secret_key.encode("utf-8"), msg, hashlib.sha256).hexdigest()
    return f"{sec.username}:{issued}:{sig}"


def verify_session_token(token: str | None, sec: CloudSecurityConfig) -> bool:
    """Verify an HMAC-signed session cookie token in constant time."""
    if not token:
        return False
    parts = token.split(":")
    if len(parts) != 3:
        return False
    user, issued_str, sig = parts
    if not secrets.compare_digest(user, sec.username):
        return False
    if not issued_str.isdigit():
        return False
    issued = int(issued_str)
    if time.time() - issued > SESSION_TTL_SECONDS:
        return False
    expected_msg = f"{user}:{issued_str}".encode("utf-8")
    expected_sig = hmac.new(
        sec.secret_key.encode("utf-8"), expected_msg, hashlib.sha256
    ).hexdigest()
    return secrets.compare_digest(sig, expected_sig)


def verify_basic_auth_header(auth_header: str | None, sec: CloudSecurityConfig) -> bool:
    """Verify standard `Authorization: Basic <base64>` header in constant time."""
    if not auth_header or not auth_header.lower().startswith("basic "):
        return False
    b64_part = auth_header[6:].strip()
    try:
        decoded = base64.b64decode(b64_part).decode("utf-8")
    except Exception:
        return False
    if ":" not in decoded:
        return False
    user, pw = decoded.split(":", 1)
    user_ok = secrets.compare_digest(user, sec.username)
    pw_ok = secrets.compare_digest(pw, sec.password)
    return user_ok and pw_ok


def is_request_authenticated(request: Request, sec: CloudSecurityConfig) -> bool:
    """Return True if cloud auth is disabled OR request carries valid cookie/Basic credentials."""
    if not sec.enabled:
        return True
    cookie_token = request.cookies.get(SESSION_COOKIE_NAME)
    if verify_session_token(cookie_token, sec):
        return True
    auth_header = request.headers.get("Authorization")
    if verify_basic_auth_header(auth_header, sec):
        return True
    return False
