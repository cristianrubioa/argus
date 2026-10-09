import os
import secrets
from pathlib import Path


def db_path() -> Path:
    return Path(os.environ.get("ARGUS_DB_PATH", "./data/argus.db"))


def session_secret() -> str:
    """Cookie signing key. ARGUS_SESSION_SECRET overrides; otherwise generated once and
    persisted next to the database, so a fresh install never needs to set it by hand."""
    env_secret = os.environ.get("ARGUS_SESSION_SECRET")
    if env_secret:
        return env_secret
    secret_path = db_path().parent / "session_secret"
    if secret_path.exists():
        return secret_path.read_text().strip()
    secret_path.parent.mkdir(parents=True, exist_ok=True)
    secret_path.write_text(secrets.token_hex(32))
    secret_path.chmod(0o600)
    return secret_path.read_text().strip()


def session_https_only() -> bool:
    return os.environ.get("ARGUS_SESSION_HTTPS_ONLY", "").lower() in ("1", "true", "yes")


def setup_token() -> str:
    """Required once, to complete first-run registration — closes the window where whoever
    visits /register first (not necessarily whoever installed Argus) becomes the admin.
    ARGUS_SETUP_TOKEN overrides; otherwise generated once and persisted next to the database,
    same pattern as session_secret()."""
    env_token = os.environ.get("ARGUS_SETUP_TOKEN")
    if env_token:
        return env_token
    token_path = db_path().parent / "setup_token"
    if token_path.exists():
        return token_path.read_text().strip()
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(secrets.token_hex(16))
    token_path.chmod(0o600)
    return token_path.read_text().strip()
