from fastapi import status

from argus import profiles
from argus import version_check


def _set_seen_version(session, value):
    settings = profiles.get_settings(session)
    settings.release_notes_seen_version = value
    session.commit()


def test_modal_container_present_when_version_unseen(logged_in_client, session):
    # Setup
    _set_seen_version(session, "0.0.1")
    # Action
    response = logged_in_client.get("/")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert 'id="release-notes-modal-container"' in response.text


def test_modal_container_absent_when_version_already_seen(logged_in_client, session):
    # Setup
    _set_seen_version(session, version_check.installed_version())
    # Action
    response = logged_in_client.get("/")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert 'id="release-notes-modal-container"' not in response.text


def test_modal_endpoint_renders_fetched_notes(logged_in_client, session, monkeypatch):
    # Setup
    monkeypatch.setattr(
        version_check,
        "fetch_release_notes",
        lambda version_tag: {"body": "### Backend\n- Did a thing", "html_url": "https://example.com/release"},
    )
    _set_seen_version(session, "0.0.1")
    # Action
    response = logged_in_client.get("/release-notes/modal")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert "Did a thing" in response.text
    assert 'href="https://example.com/release"' in response.text


def test_modal_endpoint_renders_nothing_when_fetch_fails(logged_in_client, session, monkeypatch):
    # Setup
    monkeypatch.setattr(version_check, "fetch_release_notes", lambda version_tag: None)
    _set_seen_version(session, "0.0.1")
    # Action
    response = logged_in_client.get("/release-notes/modal")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert response.text == ""


def test_modal_endpoint_fetches_installed_version_not_latest(logged_in_client, session, monkeypatch):
    # Setup
    requested = []
    monkeypatch.setattr(
        version_check,
        "fetch_release_notes",
        lambda version_tag: requested.append(version_tag) or {"body": "", "html_url": ""},
    )
    settings = profiles.get_settings(session)
    settings.release_notes_seen_version = "0.0.1"
    settings.latest_version_available = "99.0.0"
    session.commit()
    # Action
    logged_in_client.get("/release-notes/modal")
    # Expected
    assert requested == [version_check.installed_version()]


def test_dismiss_marks_installed_version_as_seen(logged_in_client, session):
    # Setup
    _set_seen_version(session, "0.0.1")
    # Action
    response = logged_in_client.post("/release-notes/dismiss")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert profiles.get_settings(session).release_notes_seen_version == version_check.installed_version()


def test_dismiss_response_is_empty_for_htmx_swap(logged_in_client, session):
    # Setup
    _set_seen_version(session, "0.0.1")
    # Action
    response = logged_in_client.post("/release-notes/dismiss")
    # Expected
    assert response.text == ""
