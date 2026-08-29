import re
from pathlib import Path

from .config import DEFAULT_PORT
from .config import PORT_FILE

_PORT_RE = re.compile(r"ARGUS_WEB_PORT=(\d+)")


def resolve_port() -> int:
    try:
        content = Path(PORT_FILE).read_text()
    except OSError:
        return DEFAULT_PORT
    match = _PORT_RE.search(content)
    return int(match.group(1)) if match else DEFAULT_PORT
