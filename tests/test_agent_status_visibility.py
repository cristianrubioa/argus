from datetime import datetime
from datetime import timedelta
from datetime import timezone

from fastapi import status

from argus import profiles
from argus.web import i18n

_PAGES = ("/", "/devices", "/whitelist", "/logs", "/settings")


def test_pages_show_never_seen_badge_by_default(logged_in_client, session):
    # Action & Expected
    for page in _PAGES:
        response = logged_in_client.get(page)
        assert response.status_code == status.HTTP_200_OK
        assert i18n.TRANSLATIONS["en"]["agent_status_never"] in response.text


def test_pages_show_live_badge_after_heartbeat(logged_in_client, session):
    # Setup
    profiles.record_agent_heartbeat(session)
    # Action & Expected
    for page in _PAGES:
        response = logged_in_client.get(page)
        assert response.status_code == status.HTTP_200_OK
        assert i18n.TRANSLATIONS["en"]["agent_status_live"] in response.text


def test_pages_show_stale_badge_past_threshold(logged_in_client, session):
    # Setup
    profiles.record_agent_heartbeat(session)
    settings = profiles.get_settings(session)
    settings.agent_last_heartbeat_at = datetime.now(timezone.utc) - timedelta(seconds=profiles._HEARTBEAT_STALE_SECONDS + 1)
    session.commit()
    # Action & Expected
    for page in _PAGES:
        response = logged_in_client.get(page)
        assert response.status_code == status.HTTP_200_OK
        assert i18n.TRANSLATIONS["en"]["agent_status_stale"] in response.text


def test_agent_status_partial_reflects_live_state(logged_in_client, session):
    # Setup
    profiles.record_agent_heartbeat(session)
    # Action
    response = logged_in_client.get("/agent-status/partial")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert i18n.TRANSLATIONS["en"]["agent_status_live"] in response.text


def test_agent_status_partial_reflects_stale_state(logged_in_client, session):
    # Setup
    profiles.record_agent_heartbeat(session)
    settings = profiles.get_settings(session)
    settings.agent_last_heartbeat_at = datetime.now(timezone.utc) - timedelta(seconds=profiles._HEARTBEAT_STALE_SECONDS + 1)
    session.commit()
    # Action
    response = logged_in_client.get("/agent-status/partial")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert i18n.TRANSLATIONS["en"]["agent_status_stale"] in response.text


def test_settings_hides_restart_hint_when_live(logged_in_client, session):
    # Setup
    profiles.record_agent_heartbeat(session)
    # Action
    response = logged_in_client.get("/settings")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert "restart-agent" not in response.text


def test_settings_shows_restart_hint_when_never_seen(logged_in_client, session):
    # Action
    response = logged_in_client.get("/settings")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert "restart-agent" in response.text


def test_settings_shows_restart_hint_when_stale(logged_in_client, session):
    # Setup
    profiles.record_agent_heartbeat(session)
    settings = profiles.get_settings(session)
    settings.agent_last_heartbeat_at = datetime.now(timezone.utc) - timedelta(seconds=profiles._HEARTBEAT_STALE_SECONDS + 1)
    session.commit()
    # Action
    response = logged_in_client.get("/settings")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert "restart-agent" in response.text


def test_settings_shows_precise_last_heartbeat_timestamp(logged_in_client, session):
    # Setup
    profiles.record_agent_heartbeat(session)
    settings = profiles.get_settings(session)
    expected = settings.agent_last_heartbeat_at.strftime("%Y-%m-%d %H:%M:%S")
    # Action
    response = logged_in_client.get("/settings")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert expected in response.text
