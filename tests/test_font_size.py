from fastapi import status

from argus import profiles


def test_font_size_defaults_to_md(session):
    # Action & Expected
    assert profiles.get_font_size(session) == "md"


def test_font_size_persists_via_profiles(session):
    # Setup
    assert profiles.get_font_size(session) == "md"
    # Action
    profiles.set_font_size(session, "lg")
    # Expected
    assert profiles.get_font_size(session) == "lg"


_BASE_AJUSTES_FORM = {"profile": "monitor", "language": "en", "theme": "dark", "font_size": "md"}


def test_font_size_persists_via_ajustes_route(logged_in_client, session):
    # Action
    response = logged_in_client.post("/ajustes", data={**_BASE_AJUSTES_FORM, "font_size": "lg"})
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert profiles.get_font_size(session) == "lg"


def test_ajustes_route_ignores_unsupported_font_size(logged_in_client, session):
    # Action
    logged_in_client.post("/ajustes", data={**_BASE_AJUSTES_FORM, "font_size": "xl"})
    # Expected
    assert profiles.get_font_size(session) == "md"


def test_dashboard_renders_md_attribute_by_default(logged_in_client, session):
    # Action
    response = logged_in_client.get("/")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert 'data-font-size="md"' in response.text


def test_dashboard_renders_lg_attribute_when_font_size_is_lg(logged_in_client, session):
    # Setup
    profiles.set_font_size(session, "lg")
    # Action
    response = logged_in_client.get("/")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert 'data-font-size="lg"' in response.text


def test_all_pages_render_without_error_in_both_font_sizes(logged_in_client, session):
    # Setup
    pages = ("/", "/dispositivos", "/whitelist", "/logs", "/ajustes")
    # Action & Expected
    for font_size in ("md", "lg"):
        profiles.set_font_size(session, font_size)
        for page in pages:
            response = logged_in_client.get(page)
            assert response.status_code == status.HTTP_200_OK
