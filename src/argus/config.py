import os
from pathlib import Path


def db_path() -> Path:
    return Path(os.environ.get("ARGUS_DB_PATH", "./data/argus.db"))


def session_secret() -> str:
    secret = os.environ.get("ARGUS_SESSION_SECRET")
    if not secret:
        raise RuntimeError("ARGUS_SESSION_SECRET is required — set it (see .env.example)")
    return secret


def session_https_only() -> bool:
    return os.environ.get("ARGUS_SESSION_HTTPS_ONLY", "").lower() in ("1", "true", "yes")


def admin_bootstrap_credentials() -> tuple[str, str] | None:
    """Admin seed from the environment, or None if unconfigured (falls back to the stored admin)."""
    username = os.environ.get("ARGUS_ADMIN_USERNAME")
    password = os.environ.get("ARGUS_ADMIN_PASSWORD")
    if not username or not password:
        return None
    return username, password


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
