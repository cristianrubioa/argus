from fastapi import status

from argus import profiles
from argus.agent import usbguard_cli
from argus.factories import DeviceEventFactory
from argus.models import AdminUser
from argus.models import Device
from argus.models import WhitelistEntry
from argus.web import router
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
    monkeypatch.setattr(
        usbguard_cli,
        "list_devices",
        lambda: [
            usbguard_cli.ListedDevice(
                vid="1d6b", pid="0002", serial=None, target="allow", hotplug=False, name="xHCI Host Controller"
            ),
            usbguard_cli.ListedDevice(
                vid="046d", pid="c542", serial=None, target="block", hotplug=True, name="Wireless Mouse"
            ),
        ],
    )
    # Action
    response = logged_in_client.get("/register/device-review")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert "xHCI Host Controller" in response.text
    assert "Wireless Mouse" in response.text
    assert 'value="1d6b:0002:"' not in response.text
    assert 'value="046d:c542:"' in response.text


def test_device_review_submit_whitelists_only_checked_devices(logged_in_client, session, monkeypatch):
    # Setup
    monkeypatch.setattr(
        usbguard_cli,
        "list_devices",
        lambda: [
            usbguard_cli.ListedDevice(
                vid="046d", pid="c542", serial=None, target="allow", hotplug=True, name="Wireless Mouse"
            ),
            usbguard_cli.ListedDevice(
                vid="058f", pid="6387", serial="AAE9055C", target="allow", hotplug=True, name="Mass Storage"
            ),
        ],
    )
    # Action
    response = logged_in_client.post("/register/device-review", data={"device_ids": ["046d:c542:"]})
    # Expected
    assert response.status_code == status.HTTP_200_OK
    checked = session.query(Device).filter_by(vid="046d", pid="c542").one()
    assert session.query(WhitelistEntry).filter_by(device_id=checked.id).count() == 1
    assert session.query(Device).filter_by(vid="058f", pid="6387").count() == 0


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


def test_device_review_resolves_empty_name_via_usb_ids(logged_in_client, session, monkeypatch, tmp_path):
    # Setup
    usb_ids_file = tmp_path / "usb.ids"
    usb_ids_file.write_text("8087  Intel Corp.\n\t0033  AX211 Bluetooth\n")
    monkeypatch.setattr(router, "_USB_IDS_PATHS", (str(usb_ids_file),))
    monkeypatch.setattr(
        usbguard_cli,
        "list_devices",
        lambda: [usbguard_cli.ListedDevice(vid="8087", pid="0033", serial=None, target="allow", hotplug=False, name="")],
    )
    # Action
    response = logged_in_client.get("/register/device-review")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert "Intel Corp. AX211 Bluetooth" in response.text
    assert "Unnamed device" not in response.text


def test_device_review_falls_back_to_unnamed_when_usb_ids_has_no_match(logged_in_client, session, monkeypatch, tmp_path):
    # Setup
    usb_ids_file = tmp_path / "usb.ids"
    usb_ids_file.write_text("1234  Some Other Vendor\n\t5678  Some Other Product\n")
    monkeypatch.setattr(router, "_USB_IDS_PATHS", (str(usb_ids_file),))
    monkeypatch.setattr(
        usbguard_cli,
        "list_devices",
        lambda: [usbguard_cli.ListedDevice(vid="8087", pid="0033", serial=None, target="allow", hotplug=False, name="")],
    )
    # Action
    response = logged_in_client.get("/register/device-review")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert "Unnamed device" in response.text


def test_device_review_route_requires_login(client, session):
    # Setup
    session.add(AdminUser(username="admin", password_hash=hash_password("secret")))
    session.commit()
    # Action
    response = client.get("/register/device-review", follow_redirects=False)
    # Expected
    assert (response.status_code, response.headers["location"]) == (status.HTTP_303_SEE_OTHER, "/login")
