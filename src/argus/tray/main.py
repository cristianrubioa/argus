from pystray import Icon

from .icon import load_icon
from .menu import build_menu


def main() -> None:
    icon = Icon("argus-tray", load_icon(), menu=build_menu())
    icon.run()


if __name__ == "__main__":
    main()
