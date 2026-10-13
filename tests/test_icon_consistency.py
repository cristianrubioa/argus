import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

_SVG_RE = re.compile(r"<svg\b[^>]*>.*?</svg>", re.DOTALL)
_PATH_RE = re.compile(r'<path d="([^"]+)"')
_CIRCLE_RE = re.compile(r'<circle cx="([^"]+)" cy="([^"]+)" r="([^"]+)"')
_EYE_PATH_PREFIX = "M12 4C5 4 1 12"

# _icon_eye.html is the canonical source: the only copy reused via {% include %}.
# icon.svg and tray-icon.svg (src/argus/web/static/icons/) can't reference it
# directly — a standalone favicon and a native tray icon loaded via
# importlib.resources can't carry Tailwind classes or CSS custom properties.
# docs/favicon.svg and docs/index.html's inline <svg> (it appears twice there —
# header brand mark and hero section) live in the separately-deployed docs/
# site (GitHub Pages root, argus.crubio.fyi) and can't reference src/ at all.
# So all four keep hand-synced geometry — this test is what catches drift.
_CANONICAL = _ROOT / "src/argus/web/templates/_icon_eye.html"

_COPIES = (
    _ROOT / "src/argus/web/static/icons/icon.svg",
    _ROOT / "src/argus/web/static/icons/tray-icon.svg",
    _ROOT / "docs/favicon.svg",
    _ROOT / "docs/index.html",
)


def _eye_icon_instances(text):
    instances = []
    for svg in _SVG_RE.findall(text):
        path_match = _PATH_RE.search(svg)
        if not path_match or _EYE_PATH_PREFIX not in path_match.group(1):
            continue
        instances.append((path_match.group(1), _CIRCLE_RE.findall(svg)))
    return instances


def test_eye_icon_geometry_matches_across_all_copies():
    # Setup
    canonical_instances = _eye_icon_instances(_CANONICAL.read_text())
    assert len(canonical_instances) == 1
    canonical_geometry = canonical_instances[0]
    # Action & Expected
    for copy in _COPIES:
        instances = _eye_icon_instances(copy.read_text())
        assert instances, copy
        for geometry in instances:
            assert geometry == canonical_geometry, copy
