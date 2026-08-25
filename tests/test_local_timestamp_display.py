from datetime import datetime

from fastapi import status

from argus import profiles
from argus.factories import DeviceEventFactory
from argus.factories import DeviceFactory
from argus.factories import WhitelistEntryFactory
from argus.web.router import _utc_iso


def test_utc_iso_normalizes_a_naive_datetime_to_an_aware_utc_isoformat():
    # Setup
    naive = datetime(2026, 8, 25, 12, 30, 0)
    # Action
    result = _utc_iso(naive)
    # Expected
    assert result == "2026-08-25T12:30:00+00:00"


def test_devices_page_shows_last_seen_as_a_local_time_element(logged_in_client, session):
    # Setup
    DeviceFactory(name="Mass Storage")
    # Action
    response = logged_in_client.get("/devices")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert "data-local" in response.text
    assert "UTC" in response.text


def test_whitelist_page_shows_added_at_as_a_local_time_element(logged_in_client, session):
    # Setup
    WhitelistEntryFactory()
    # Action
    response = logged_in_client.get("/whitelist")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert "data-local" in response.text
    assert "UTC" in response.text


def test_dashboard_events_table_shows_occurred_at_as_a_local_time_element(logged_in_client, session):
    # Setup
    DeviceEventFactory()
    # Action
    response = logged_in_client.get("/")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert "data-local" in response.text
    assert "UTC" in response.text


def test_admin_actions_table_shows_occurred_at_as_a_local_time_element(logged_in_client, session):
    # Setup
    device = DeviceFactory()
    logged_in_client.post(f"/whitelist/authorize/{device.id}")
    # Action
    response = logged_in_client.get("/logs")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert "data-local" in response.text
    assert "UTC" in response.text


def test_settings_shows_agent_heartbeat_as_a_local_time_element(logged_in_client, session):
    # Setup
    profiles.record_agent_heartbeat(session)
    # Action
    response = logged_in_client.get("/settings")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert "data-local" in response.text
    assert "UTC" in response.text
