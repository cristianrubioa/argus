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


def log_retention_days() -> int | None:
    """Days of device_events/applied whitelist actions to keep, or None to keep forever (default)."""
    days = os.environ.get("ARGUS_LOG_RETENTION_DAYS")
    return int(days) if days else None


def mqtt_config() -> dict | None:
    """MQTT broker settings, or None when unconfigured — the bridge is fully optional."""
    host = os.environ.get("ARGUS_MQTT_HOST")
    if not host:
        return None
    return {
        "host": host,
        "port": int(os.environ.get("ARGUS_MQTT_PORT", "1883")),
        "topic_prefix": os.environ.get("ARGUS_MQTT_TOPIC_PREFIX", "argus"),
    }
