from datetime import datetime
from datetime import timedelta
from datetime import timezone

from fastapi import status

from argus.factories import DeviceEventFactory
from argus.factories import DeviceFactory
from argus.models import Decision
from argus.models import Profile


def test_search_matches_device_name(logged_in_client, session):
    # Setup
    DeviceEventFactory(device=DeviceFactory(name="Kingston Flash Drive"))
    DeviceEventFactory(device=DeviceFactory(name="Logitech Mouse"))
    # Action
    response = logged_in_client.get("/logs", params={"q": "Kingston"})
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert "Kingston Flash Drive" in response.text
    assert "Logitech Mouse" not in response.text


def test_search_matches_vid_pid(logged_in_client, session):
    # Setup
    DeviceEventFactory(device=DeviceFactory(name="Kingston Flash Drive", vid="1d6b", pid="0002"))
    DeviceEventFactory(device=DeviceFactory(name="Logitech Mouse", vid="046d", pid="c542"))
    # Action
    response = logged_in_client.get("/logs", params={"q": "1d6b"})
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert "Kingston Flash Drive" in response.text
    assert "Logitech Mouse" not in response.text


def test_search_matches_serial(logged_in_client, session):
    # Setup
    DeviceEventFactory(device=DeviceFactory(name="Kingston Flash Drive", serial="AAE9055C"))
    DeviceEventFactory(device=DeviceFactory(name="Logitech Mouse", serial="0000:00:0d.0"))
    # Action
    response = logged_in_client.get("/logs", params={"q": "AAE9055C"})
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert "Kingston Flash Drive" in response.text
    assert "Logitech Mouse" not in response.text


def test_profile_badge_is_localized_not_raw_enum_value(logged_in_client, session):
    # Setup
    DeviceEventFactory(device=DeviceFactory(name="Monitored Device"), profile=Profile.MONITOR)
    # Action
    response = logged_in_client.get("/logs")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert "Monitor" in response.text
    assert ">monitor<" not in response.text


def test_decision_tag_filter_narrows_results(logged_in_client, session):
    # Setup
    DeviceEventFactory(device=DeviceFactory(name="Allowed Device"), decision=Decision.AUTHORIZED)
    DeviceEventFactory(device=DeviceFactory(name="Blocked Device"), decision=Decision.BLOCKED)
    # Action
    response = logged_in_client.get("/logs", params={"decision": "authorized"})
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert "Allowed Device" in response.text
    assert "Blocked Device" not in response.text


def test_profile_tag_filter_narrows_results(logged_in_client, session):
    # Setup
    DeviceEventFactory(device=DeviceFactory(name="Monitor Device"), profile=Profile.MONITOR)
    DeviceEventFactory(device=DeviceFactory(name="Enforce Device"), profile=Profile.ENFORCE)
    # Action
    response = logged_in_client.get("/logs", params={"profile": "enforce"})
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert "Enforce Device" in response.text
    assert "Monitor Device" not in response.text


def test_default_date_range_excludes_events_older_than_7_days(logged_in_client, session):
    # Setup
    old_device = DeviceFactory(name="Old Device")
    DeviceEventFactory(device=old_device, occurred_at=datetime.now(timezone.utc) - timedelta(days=10))
    recent_device = DeviceFactory(name="Recent Device")
    DeviceEventFactory(device=recent_device, occurred_at=datetime.now(timezone.utc) - timedelta(days=1))
    # Action
    response = logged_in_client.get("/logs")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert "Recent Device" in response.text
    assert "Old Device" not in response.text


def test_explicit_date_range_overrides_the_default(logged_in_client, session):
    # Setup
    old_device = DeviceFactory(name="Old Device")
    DeviceEventFactory(device=old_device, occurred_at=datetime.now(timezone.utc) - timedelta(days=10))
    date_from = (datetime.now(timezone.utc) - timedelta(days=15)).strftime("%Y-%m-%dT%H:%M")
    date_to = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M")
    # Action
    response = logged_in_client.get("/logs", params={"from": date_from, "to": date_to})
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert "Old Device" in response.text


def test_logs_partial_applies_the_same_filters_as_logs(logged_in_client, session):
    # Setup
    DeviceEventFactory(device=DeviceFactory(name="Allowed Device"), decision=Decision.AUTHORIZED)
    DeviceEventFactory(device=DeviceFactory(name="Blocked Device"), decision=Decision.BLOCKED)
    # Action
    response = logged_in_client.get("/logs/partial", params={"decision": "authorized"})
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert "Allowed Device" in response.text
    assert "Blocked Device" not in response.text


def test_dashboard_is_unaffected_by_logs_filters(logged_in_client, session):
    # Setup
    old_device = DeviceFactory(name="Old Device")
    DeviceEventFactory(device=old_device, occurred_at=datetime.now(timezone.utc) - timedelta(days=10))
    # Action
    response = logged_in_client.get("/")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert "Old Device" in response.text
