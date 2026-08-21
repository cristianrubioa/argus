"""Single-admin session-cookie login (design.md decision #9) — no JWT, no roles."""

import hashlib
import hmac
import logging
import secrets
import threading
from datetime import datetime
from datetime import timedelta
from datetime import timezone

from fastapi import HTTPException
from fastapi import Request
from fastapi import status
from sqlalchemy.orm import Session

from argus import config
from argus.models import AdminUser

logger = logging.getLogger(__name__)

_PBKDF2_ITERATIONS = 600_000

_LOGIN_MAX_ATTEMPTS = 5
_LOGIN_LOCKOUT_SECONDS = 300
_LOGIN_ATTEMPT_TTL = timedelta(hours=1)

_login_attempts: dict[str, tuple[int, datetime | None, datetime]] = {}
_login_attempts_lock = threading.Lock()


def is_locked_out(source: str) -> bool:
    with _login_attempts_lock:
        _, locked_until, _ = _login_attempts.get(source, (0, None, datetime.min.replace(tzinfo=timezone.utc)))
        return locked_until is not None and datetime.now(timezone.utc) < locked_until


def _prune_stale_attempts(now: datetime) -> None:
    """Caller holds _login_attempts_lock. Drops sources untouched for _LOGIN_ATTEMPT_TTL, so a flood of
    distinct source IPs that each fail once and never return doesn't grow this dict forever."""
    stale = [
        source for source, (_, _, last_attempt_at) in _login_attempts.items() if now - last_attempt_at > _LOGIN_ATTEMPT_TTL
    ]
    for source in stale:
        del _login_attempts[source]


def record_failure(source: str) -> None:
    now = datetime.now(timezone.utc)
    with _login_attempts_lock:
        _prune_stale_attempts(now)
        count, _, _ = _login_attempts.get(source, (0, None, now))
        count += 1
        locked_until = now + timedelta(seconds=_LOGIN_LOCKOUT_SECONDS) if count >= _LOGIN_MAX_ATTEMPTS else None
        _login_attempts[source] = (count, locked_until, now)
    logger.warning("Failed login attempt from %s (%d/%d)", source, count, _LOGIN_MAX_ATTEMPTS)


def record_success(source: str) -> None:
    with _login_attempts_lock:
        _login_attempts.pop(source, None)


def _reset_login_attempts() -> None:
    """Test-only: clears rate-limit state between tests sharing the same TestClient source."""
    with _login_attempts_lock:
        _login_attempts.clear()


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${_PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        _, iterations, salt_hex, digest_hex = stored_hash.split("$")
    except ValueError:
        return False
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations))
    return hmac.compare_digest(candidate.hex(), digest_hex)


def ensure_admin_seeded(session: Session) -> None:
    """Seeds or updates the single admin account from ARGUS_ADMIN_USERNAME/PASSWORD, if set."""
    seed = config.admin_bootstrap_credentials()
    if seed is None:
        return
    username, password = seed

    admin = session.query(AdminUser).filter_by(username=username).first()
    if admin is None:
        session.add(AdminUser(username=username, password_hash=hash_password(password)))
    else:
        admin.password_hash = hash_password(password)
    session.commit()


def authenticate(session: Session, username: str, password: str) -> bool:
    admin = session.query(AdminUser).filter_by(username=username).first()
    return admin is not None and verify_password(password, admin.password_hash)


def require_admin(request: Request) -> str:
    username = request.session.get("admin")
    if not username:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/login"})
    return username
