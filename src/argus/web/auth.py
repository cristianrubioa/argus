"""Single-admin session-cookie login — no JWT, no roles, no registration
(design.md decision #9). Password hashing uses stdlib PBKDF2-HMAC-SHA256 at an
OWASP-recommended iteration count, avoiding an extra dependency (bcrypt/passlib)
for a single low-throughput login.
"""

import hashlib
import hmac
import secrets

from fastapi import HTTPException
from fastapi import Request
from sqlalchemy.orm import Session

from argus import config
from argus.models import AdminUser

_PBKDF2_ITERATIONS = 600_000


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
    """On startup, if ARGUS_ADMIN_USERNAME/PASSWORD are set and no matching admin
    exists yet, seed (or update) the single admin account from them.
    """
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
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return username
