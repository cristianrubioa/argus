"""Single-admin session-cookie login (design.md decision #9) — no JWT, no roles."""

import hashlib
import hmac
import logging
import secrets
import threading
from datetime import datetime
from datetime import timedelta
from datetime import timezone

from fastapi import Depends
from fastapi import HTTPException
from fastapi import Request
from fastapi import status
from sqlalchemy.orm import Session

from argus.db import get_session
from argus.models import AdminUser

logger = logging.getLogger(__name__)

_PBKDF2_ITERATIONS = 600_000
_MIN_PASSWORD_LENGTH = 8

_admin_exists_cache = False

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


def is_password_valid(password: str, confirmation: str) -> bool:
    return password == confirmation and len(password) >= _MIN_PASSWORD_LENGTH


def admin_exists(session: Session) -> bool:
    return session.query(AdminUser).first() is not None


def create_admin_account(session: Session, username: str, password: str) -> None:
    session.add(AdminUser(username=username, password_hash=hash_password(password)))
    session.commit()


def change_password(session: Session, admin_username: str, current_password: str, new_password: str) -> bool:
    """Verifies current_password before writing; returns False (no write) on mismatch."""
    admin = session.query(AdminUser).filter_by(username=admin_username).first()
    if admin is None or not verify_password(current_password, admin.password_hash):
        return False
    admin.password_hash = hash_password(new_password)
    session.commit()
    return True


def authenticate(session: Session, username: str, password: str) -> bool:
    admin = session.query(AdminUser).filter_by(username=username).first()
    return admin is not None and verify_password(password, admin.password_hash)


def _redirect_exception(request: Request, location: str) -> HTTPException:
    """A plain 303 makes a normal browser navigate. HTMX's fetch instead follows a 303 automatically and
    swaps the resulting page into the polling target — so an HTMX-originated request gets an HX-Redirect
    on a 200 instead, which tells htmx to navigate the whole browser rather than swap a fragment."""
    if request.headers.get("HX-Request") == "true":
        return HTTPException(status_code=status.HTTP_200_OK, headers={"HX-Redirect": location})
    return HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": location})


def require_admin(request: Request) -> str:
    username = request.session.get("admin")
    if not username:
        raise _redirect_exception(request, "/login")
    return username


def require_registered(request: Request, session: Session = Depends(get_session)) -> None:
    """No admin account exists yet — redirect every route except /register there. Caches True forever
    once an account exists, since nothing in this app ever deletes it, to skip the query afterward."""
    global _admin_exists_cache
    if _admin_exists_cache:
        return
    if admin_exists(session):
        _admin_exists_cache = True
        return
    raise _redirect_exception(request, "/register")


def _reset_admin_exists_cache() -> None:
    """Test-only: clears the process-local cache between tests sharing the same app instance."""
    global _admin_exists_cache
    _admin_exists_cache = False
