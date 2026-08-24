from datetime import datetime
from datetime import timedelta
from datetime import timezone

from fastapi import status

from argus.factories import DeviceEventFactory
from argus.factories import DeviceFactory
from argus.models import AdminAction
from argus.models import AdminActionType


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
    # Setup
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
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert "Device 00" in response.text
    assert "Device 20" not in response.text


def test_sort_is_preserved_on_the_next_page(logged_in_client, session):
    # Setup
    _seed_events(25)
    # Action
    response = logged_in_client.get("/logs", params={"sort": "name", "dir": "asc", "page": 2})
    # Expected
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


def test_logs_partial_with_tab_actions_returns_admin_actions_table(logged_in_client, session):
    # Setup
    session.add_all(
        [
            AdminAction(actor="admin", action_type=AdminActionType.WHITELIST_AUTHORIZE, target="Zebra Drive"),
            AdminAction(actor="admin", action_type=AdminActionType.WHITELIST_AUTHORIZE, target="Apple Drive"),
        ]
    )
    session.commit()
    # Action
    response = logged_in_client.get("/logs/partial", params={"tab": "actions", "a_sort": "target", "a_dir": "asc"})
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert response.text.index("Apple Drive") < response.text.index("Zebra Drive")


def test_logs_partial_sets_hx_push_url_header_reflecting_current_state(logged_in_client, session):
    # Setup
    DeviceEventFactory(device=DeviceFactory(name="Zebra Drive"))
    # Action
    response = logged_in_client.get("/logs/partial", params={"sort": "name", "dir": "asc"}, headers={"HX-Request": "true"})
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert response.headers["HX-Push-Url"].startswith("/logs?")
    assert "sort=name" in response.headers["HX-Push-Url"]
    assert "dir=asc" in response.headers["HX-Push-Url"]


def test_logs_partial_without_hx_request_header_omits_push_url_header(logged_in_client, session):
    # Setup
    DeviceEventFactory(device=DeviceFactory(name="Zebra Drive"))
    # Action
    response = logged_in_client.get("/logs/partial")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert "HX-Push-Url" not in response.headers


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
