import socket

from .config import REACHABILITY_TIMEOUT_SECONDS


def is_dashboard_reachable(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=REACHABILITY_TIMEOUT_SECONDS):
            return True
    except OSError:
        return False
