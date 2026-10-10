from fastapi import status

from argus import profiles
from argus.agent import usbguard_cli
from argus.factories import DeviceEventFactory
from argus.factories import DeviceFactory
from argus.models import AdminUser
from argus.models import WhitelistEntry
from argus.web.auth import hash_password

_VALID_SETUP_TOKEN = "test-setup-token-not-for-production"


def _register(client):
    return client.post(
        "/register",
        data={
            "username": "admin",
            "password": "longenough",
            "confirm_password": "longenough",
            "setup_token": _VALID_SETUP_TOKEN,
        },
    )


def test_successful_registration_shows_device_review_container(client, session, monkeypatch):
    # Setup
    monkeypatch.setattr(usbguard_cli, "list_devices", lambda: [])
    # Action
    response = _register(client)
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert 'id="device-review-modal-container"' in response.text
    assert 'hx-get="/register/device-review"' in response.text


def test_device_review_container_absent_on_a_later_visit(client, session, monkeypatch):
    # Setup
    monkeypatch.setattr(usbguard_cli, "list_devices", lambda: [])
    _register(client)
    # Action
    response = client.get("/")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert 'id="device-review-modal-container"' not in response.text


def test_device_review_splits_internal_and_external_devices(logged_in_client, session, monkeypatch):
    # Setup
    internal = DeviceFactory(connect_type="hardwired")
    external = DeviceFactory(connect_type="hotplug")
    monkeypatch.setattr(
        usbguard_cli,
        "list_devices",
        lambda: [
            usbguard_cli.ListedDevice(
                vid=internal.vid, pid=internal.pid, serial=internal.serial, target="allow", hotplug=False
            ),
            usbguard_cli.ListedDevice(
                vid=external.vid, pid=external.pid, serial=external.serial, target="block", hotplug=True
            ),
        ],
    )
    # Action
    response = logged_in_client.get("/register/device-review")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert internal.name in response.text
    assert external.name in response.text
    assert f'value="{internal.id}"' not in response.text
    assert f'value="{external.id}"' in response.text


def test_device_review_submit_whitelists_only_checked_devices(logged_in_client, session, monkeypatch):
    # Setup
    monkeypatch.setattr(usbguard_cli, "list_devices", lambda: [])
    checked = DeviceFactory(connect_type="hotplug")
    unchecked = DeviceFactory(connect_type="hotplug")
    # Action
    response = logged_in_client.post("/register/device-review", data={"device_ids": [checked.id]})
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert session.query(WhitelistEntry).filter_by(device_id=checked.id).count() == 1
    assert session.query(WhitelistEntry).filter_by(device_id=unchecked.id).count() == 0


def test_unchecked_device_remains_eligible_for_enforce_review(logged_in_client, session, monkeypatch):
    # Setup
    monkeypatch.setattr(usbguard_cli, "list_devices", lambda: [])
    event = DeviceEventFactory()
    # Action
    logged_in_client.post("/register/device-review", data={})
    # Expected
    assert event.device in profiles.unreviewed_devices(session)


def test_device_review_degrades_to_empty_when_usbguard_unavailable(logged_in_client, session, monkeypatch):
    # Setup
    def _raise():
        raise usbguard_cli.UsbguardCliError("usbguard not ready")

    monkeypatch.setattr(usbguard_cli, "list_devices", _raise)
    # Action
    response = logged_in_client.get("/register/device-review")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert response.text.count("None detected") == 2


def test_device_review_route_requires_login(client, session):
    # Setup
    session.add(AdminUser(username="admin", password_hash=hash_password("secret")))
    session.commit()
    # Action
    response = client.get("/register/device-review", follow_redirects=False)
    # Expected
    assert (response.status_code, response.headers["location"]) == (status.HTTP_303_SEE_OTHER, "/login")
