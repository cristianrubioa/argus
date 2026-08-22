from fastapi import status

from argus import profiles


def test_theme_defaults_to_dark(session):
    # Action & Expected
    assert profiles.get_theme(session) == "dark"


def test_theme_persists_via_profiles(session):
    # Setup
    assert profiles.get_theme(session) == "dark"
    # Action
    profiles.set_theme(session, "light")
    # Expected
    assert profiles.get_theme(session) == "light"


_BASE_SETTINGS_FORM = {"profile": "monitor", "language": "en", "theme": "dark", "font_size": "md"}


def test_theme_persists_via_settings_route(logged_in_client, session):
    # Action
    response = logged_in_client.post("/settings", data={**_BASE_SETTINGS_FORM, "theme": "light"})
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert profiles.get_theme(session) == "light"


def test_settings_route_ignores_unsupported_theme(logged_in_client, session):
    # Action
    logged_in_client.post("/settings", data={**_BASE_SETTINGS_FORM, "theme": "solarized"})
    # Expected
    assert profiles.get_theme(session) == "dark"


def test_dashboard_renders_dark_class_by_default(logged_in_client, session):
    # Action
    response = logged_in_client.get("/")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert '<html lang="en" class="dark" data-font-size="md">' in response.text


def test_dashboard_omits_dark_class_when_theme_is_light(logged_in_client, session):
    # Setup
    profiles.set_theme(session, "light")
    # Action
    response = logged_in_client.get("/")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert '<html lang="en" class="" data-font-size="md">' in response.text


def test_all_pages_render_without_error_in_both_themes(logged_in_client, session):
    # Setup
    pages = ("/", "/devices", "/whitelist", "/logs", "/settings")
    # Action & Expected
    for theme in ("dark", "light"):
        profiles.set_theme(session, theme)
        for page in pages:
            response = logged_in_client.get(page)
            assert response.status_code == status.HTTP_200_OK
