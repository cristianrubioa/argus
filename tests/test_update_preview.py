from fastapi import status

from argus import profiles
from argus import version_check


def _set_latest_available(session, value):
    settings = profiles.get_settings(session)
    settings.latest_version_available = value
    session.commit()


def test_update_preview_renders_fetched_notes_for_latest_available(logged_in_client, session, monkeypatch):
    # Setup
    requested = []
    monkeypatch.setattr(
        version_check,
        "fetch_release_notes",
        lambda version_tag: requested.append(version_tag)
        or {"body": "### Backend\n- Did a thing", "html_url": "https://example.com/release"},
    )
    _set_latest_available(session, "99.0.0")
    # Action
    response = logged_in_client.get("/settings/update-preview")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert "Did a thing" in response.text
    assert requested == ["99.0.0"]


def test_update_preview_has_close_action_not_dismiss(logged_in_client, session, monkeypatch):
    # Setup
    monkeypatch.setattr(version_check, "fetch_release_notes", lambda version_tag: {"body": "", "html_url": ""})
    _set_latest_available(session, "99.0.0")
    # Action
    response = logged_in_client.get("/settings/update-preview")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert 'id="release-notes-close"' in response.text
    assert 'id="release-notes-dismiss"' not in response.text


def test_update_preview_does_not_mark_notes_as_seen(logged_in_client, session, monkeypatch):
    # Setup
    monkeypatch.setattr(version_check, "fetch_release_notes", lambda version_tag: {"body": "", "html_url": ""})
    _set_latest_available(session, "99.0.0")
    seen_before = profiles.get_settings(session).release_notes_seen_version
    # Action
    logged_in_client.get("/settings/update-preview")
    # Expected
    assert profiles.get_settings(session).release_notes_seen_version == seen_before


def test_update_preview_renders_nothing_when_no_update_available(logged_in_client, session):
    # Setup
    _set_latest_available(session, None)
    # Action
    response = logged_in_client.get("/settings/update-preview")
    # Expected
    assert (response.status_code, response.text) == (status.HTTP_200_OK, "")


def test_update_preview_renders_nothing_when_fetch_fails(logged_in_client, session, monkeypatch):
    # Setup
    monkeypatch.setattr(version_check, "fetch_release_notes", lambda version_tag: None)
    _set_latest_available(session, "99.0.0")
    # Action
    response = logged_in_client.get("/settings/update-preview")
    # Expected
    assert (response.status_code, response.text) == (status.HTTP_200_OK, "")
