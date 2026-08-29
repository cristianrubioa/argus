from pystray import Icon

from .icon import load_icon
from .lock import acquire_lock
from .lock import release_lock
from .menu import build_menu


def main() -> None:
    acquire_lock()
    try:
        icon = Icon("argus-tray", load_icon(), menu=build_menu())
        icon.run()
    finally:
        release_lock()


if __name__ == "__main__":
    main()
