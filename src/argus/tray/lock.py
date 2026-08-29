import os
import sys
from pathlib import Path

_CACHE_DIR = Path.home() / ".cache" / "argus-tray"
_PID_FILE = _CACHE_DIR / "argus-tray.pid"


def _pid_is_alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def acquire_lock():
    """Acquires the single-instance PID lock, exiting if another instance is alive."""
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if _PID_FILE.exists():
        content = _PID_FILE.read_text().strip()
        if content.isdigit() and _pid_is_alive(int(content)):
            print(f"argus-tray is already running (PID {content}).", file=sys.stderr)
            sys.exit(1)
    _PID_FILE.write_text(str(os.getpid()))


def release_lock():
    _PID_FILE.unlink(missing_ok=True)
