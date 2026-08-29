import importlib.resources

import gi
from PIL import Image

gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf  # noqa: E402

_ICON_SIZE = 64


def load_icon() -> Image.Image:
    svg_path = importlib.resources.files("argus.web").joinpath("static", "icon.svg")
    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(str(svg_path), _ICON_SIZE, _ICON_SIZE)
    mode = "RGBA" if pixbuf.get_has_alpha() else "RGB"
    image = Image.frombuffer(
        mode,
        (pixbuf.get_width(), pixbuf.get_height()),
        pixbuf.get_pixels(),
        "raw",
        mode,
        pixbuf.get_rowstride(),
        1,
    )
    return image.convert("RGBA")
