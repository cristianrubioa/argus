import pytest

try:
    # pystray isn't installed at all in a headless-only environment, and even when it is,
    # it picks its backend (and tries to connect to a real display) at import time — so
    # both failure modes need to be caught here, not just a missing-module ImportError.
    from argus.tray import menu
except Exception as exc:
    pytest.skip(f"pystray has no usable backend here: {exc}", allow_module_level=True)


def test_menu_shows_settings_when_reachable(monkeypatch):
    # Setup
    monkeypatch.setattr(menu, "resolve_port", lambda: 8420)
    monkeypatch.setattr(menu, "is_dashboard_reachable", lambda port: True)
    # Action
    items = list(menu._build_items())
    # Expected
    assert (items[0].text, items[0].enabled, items[-1].text) == ("Settings", True, "Quit")


def test_menu_shows_disabled_state_when_unreachable(monkeypatch):
    # Setup
    monkeypatch.setattr(menu, "resolve_port", lambda: 8420)
    monkeypatch.setattr(menu, "is_dashboard_reachable", lambda port: False)
    # Action
    items = list(menu._build_items())
    # Expected
    assert (items[0].text, items[0].enabled, items[-1].text) == ("Argus isn't running", False, "Quit")
