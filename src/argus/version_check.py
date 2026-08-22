"""Best-effort GitHub release check — no runtime HTTP client dependency, stdlib only."""

import json
import logging
from importlib.metadata import version
from urllib.request import urlopen

logger = logging.getLogger(__name__)

_RELEASES_URL = "https://api.github.com/repos/cristianrubioa/argus/releases/latest"
_FETCH_TIMEOUT_SECONDS = 2


def installed_version() -> str:
    return version("argus")


def fetch_latest_version() -> str | None:
    """The latest published release's version (no leading 'v'), or None on any failure."""
    try:
        with urlopen(_RELEASES_URL, timeout=_FETCH_TIMEOUT_SECONDS) as response:
            data = json.loads(response.read())
        return data["tag_name"].lstrip("v")
    except Exception:
        logger.info("Version check failed", exc_info=True)
        return None


def is_newer(latest: str, installed: str) -> bool:
    try:
        return tuple(int(part) for part in latest.split(".")) > tuple(int(part) for part in installed.split("."))
    except ValueError:
        return False
