from datetime import datetime
from datetime import timedelta
from datetime import timezone

from fastapi import status

from argus.factories import DeviceEventFactory
from argus.factories import DeviceFactory


def _seed_events(count: int):
    now = datetime.now(timezone.utc)
    for i in range(count):
        device = DeviceFactory(name=f"Device {i:02d}")
        DeviceEventFactory(device=device, occurred_at=now - timedelta(minutes=i))


def test_sort_by_name_ascending(logged_in_client, session):
    # Setup
    DeviceEventFactory(device=DeviceFactory(name="Zebra Drive"))
    DeviceEventFactory(device=DeviceFactory(name="Apple Drive"))
    # Action
    response = logged_in_client.get("/logs", params={"sort": "name", "dir": "asc"})
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert response.text.index("Apple Drive") < response.text.index("Zebra Drive")


def test_sort_by_name_descending(logged_in_client, session):
    # Setup
    DeviceEventFactory(device=DeviceFactory(name="Zebra Drive"))
    DeviceEventFactory(device=DeviceFactory(name="Apple Drive"))
    # Action
    response = logged_in_client.get("/logs", params={"sort": "name", "dir": "desc"})
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert response.text.index("Zebra Drive") < response.text.index("Apple Drive")


def test_sort_by_serial_ascending(logged_in_client, session):
    # Setup
    DeviceEventFactory(device=DeviceFactory(name="Zebra Drive", serial="ZZZ"))
    DeviceEventFactory(device=DeviceFactory(name="Apple Drive", serial="AAA"))
    # Action
    response = logged_in_client.get("/logs", params={"sort": "serial", "dir": "asc"})
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert response.text.index("Apple Drive") < response.text.index("Zebra Drive")


def test_sort_by_serial_descending(logged_in_client, session):
    # Setup
    DeviceEventFactory(device=DeviceFactory(name="Zebra Drive", serial="ZZZ"))
    DeviceEventFactory(device=DeviceFactory(name="Apple Drive", serial="AAA"))
    # Action
    response = logged_in_client.get("/logs", params={"sort": "serial", "dir": "desc"})
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert response.text.index("Zebra Drive") < response.text.index("Apple Drive")


def test_second_page_returns_the_next_20_excluding_the_first_page(logged_in_client, session):
    # Setup — 25 events, newest (Device 0) first under the default occurred_at desc sort
    _seed_events(25)
    # Action
    first_page = logged_in_client.get("/logs")
    second_page = logged_in_client.get("/logs", params={"page": 2})
    # Expected
    assert "Device 00" in first_page.text
    assert "Device 19" in first_page.text
    assert "Device 20" not in first_page.text
    assert "Device 00" not in second_page.text
    assert "Device 20" in second_page.text
    assert "Device 24" in second_page.text


def test_request_without_page_param_defaults_to_page_1(logged_in_client, session):
    # Setup
    _seed_events(25)
    # Action
    response = logged_in_client.get("/logs", params={"q": "Device"})
    # Expected — a filter submission (no page param) always lands on page 1
    assert response.status_code == status.HTTP_200_OK
    assert "Device 00" in response.text
    assert "Device 20" not in response.text


def test_sort_is_preserved_on_the_next_page(logged_in_client, session):
    # Setup — zero-padded names 00..24 so ascending lexical order matches numeric order
    _seed_events(25)
    # Action
    response = logged_in_client.get("/logs", params={"sort": "name", "dir": "asc", "page": 2})
    # Expected — page 2 of an ascending sort holds the last 5 (20..24), not the first 20
    assert response.status_code == status.HTTP_200_OK
    assert "Device 20" in response.text
    assert "Device 24" in response.text
    assert "Device 00" not in response.text
    assert "Device 19" not in response.text


def test_logs_partial_applies_the_same_sort_and_page_as_logs(logged_in_client, session):
    # Setup
    DeviceEventFactory(device=DeviceFactory(name="Zebra Drive"))
    DeviceEventFactory(device=DeviceFactory(name="Apple Drive"))
    # Action
    response = logged_in_client.get("/logs/partial", params={"sort": "name", "dir": "asc"})
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert response.text.index("Apple Drive") < response.text.index("Zebra Drive")


def test_dashboard_has_no_sort_links_or_pagination(logged_in_client, session):
    # Setup
    _seed_events(25)
    # Action
    response = logged_in_client.get("/")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert "fa-arrow-" not in response.text
    assert "Device 00" in response.text
    assert "Device 20" not in response.text
