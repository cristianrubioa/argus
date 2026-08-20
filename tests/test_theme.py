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


def test_theme_persists_via_ajustes_route(logged_in_client, session):
    # Action
    response = logged_in_client.post("/ajustes/theme", data={"theme": "light"})
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert profiles.get_theme(session) == "light"


def test_ajustes_route_ignores_unsupported_theme(logged_in_client, session):
    # Action
    logged_in_client.post("/ajustes/theme", data={"theme": "solarized"})
    # Expected
    assert profiles.get_theme(session) == "dark"


def test_dashboard_renders_dark_class_by_default(logged_in_client, session):
    # Action
    response = logged_in_client.get("/")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert '<html lang="en" class="dark">' in response.text


def test_dashboard_omits_dark_class_when_theme_is_light(logged_in_client, session):
    # Setup
    profiles.set_theme(session, "light")
    # Action
    response = logged_in_client.get("/")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert '<html lang="en" class="">' in response.text


def test_all_pages_render_without_error_in_both_themes(logged_in_client, session):
    # Setup
    pages = ("/", "/dispositivos", "/whitelist", "/logs", "/ajustes")
    # Action & Expected
    for theme in ("dark", "light"):
        profiles.set_theme(session, theme)
        for page in pages:
            response = logged_in_client.get(page)
            assert response.status_code == status.HTTP_200_OK
