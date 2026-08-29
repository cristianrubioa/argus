import webbrowser

from pystray import Menu
from pystray import MenuItem

from .port import resolve_port
from .reachability import is_dashboard_reachable


def _open_dashboard(icon, item=None):
    webbrowser.open(f"http://localhost:{resolve_port()}")


def _quit(icon, item=None):
    icon.stop()


def _build_items():
    if is_dashboard_reachable(resolve_port()):
        yield MenuItem("Settings", _open_dashboard)
    else:
        yield MenuItem("Argus isn't running", None, enabled=False)
    yield Menu.SEPARATOR
    yield MenuItem("Quit", _quit)


def build_menu() -> Menu:
    return Menu(_build_items)
