from fastapi import status

from argus import profiles
from argus import version_check
from argus.web import i18n


def test_sidebar_shows_bare_version_with_no_pill_by_default(logged_in_client):
    # Action
    response = logged_in_client.get("/")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert f"v{version_check.installed_version()}" in response.text
    assert i18n.TRANSLATIONS["en"]["version_up_to_date"] not in response.text
    assert i18n.TRANSLATIONS["en"]["version_update_available"] not in response.text


def test_sidebar_shows_up_to_date_pill(logged_in_client, session, monkeypatch):
    # Setup — logged_in_client's login already consumed the first (unset) check, so force a re-check
    monkeypatch.setattr(version_check, "fetch_latest_version", lambda: version_check.installed_version())
    profiles.get_settings(session).version_checked_at = None
    session.commit()
    # Action
    response = logged_in_client.get("/")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert i18n.TRANSLATIONS["en"]["version_up_to_date"] in response.text
    assert 'href="/settings#software"' not in response.text


def test_sidebar_shows_update_available_pill_linking_to_settings(logged_in_client, session, monkeypatch):
    # Setup — logged_in_client's login already consumed the first (unset) check, so force a re-check
    monkeypatch.setattr(version_check, "fetch_latest_version", lambda: "99.0.0")
    profiles.get_settings(session).version_checked_at = None
    session.commit()
    # Action
    response = logged_in_client.get("/")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert i18n.TRANSLATIONS["en"]["version_update_available"] in response.text
    assert 'href="/settings#software"' in response.text


def test_footer_renders_after_version_badge(logged_in_client):
    # Action
    response = logged_in_client.get("/")
    # Expected — the footer signature must appear after the version badge in document order,
    # confirming it's still the last sidebar element (mt-auto keeps it pinned to the bottom)
    text = response.text
    version_index = text.index(f"v{version_check.installed_version()}")
    footer_index = text.index(i18n.TRANSLATIONS["en"]["footer_made_with"])
    assert version_index < footer_index


def test_stale_cache_is_refreshed_on_page_load(logged_in_client, session, monkeypatch):
    # Setup — logged_in_client's login already consumed the first (unset) check, so force a re-check
    monkeypatch.setattr(version_check, "fetch_latest_version", lambda: "0.9.0")
    profiles.get_settings(session).version_checked_at = None
    session.commit()
    # Action
    logged_in_client.get("/")
    # Expected
    settings = profiles.get_settings(session)
    assert settings.latest_version_available == "0.9.0"
    assert settings.version_checked_at is not None
