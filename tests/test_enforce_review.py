from fastapi import status

from argus import profiles
from argus.agent import usbguard_cli
from argus.factories import DeviceEventFactory
from argus.factories import WhitelistEntryFactory
from argus.models import LogRetention
from argus.models import Profile
from argus.models import WhitelistEntry

_BASE_SETTINGS_FORM = {
    "language": "en",
    "theme": "dark",
    "font_size": "md",
    "log_retention": "1_year",
    "mqtt_port": "1883",
}


def test_enforce_review_devices_lists_unreviewed_device(logged_in_client, session, monkeypatch):
    # Setup
    monkeypatch.setattr(usbguard_cli, "list_devices", lambda: [])
    DeviceEventFactory()
    # Action
    response = logged_in_client.get("/settings/enforce-review-devices")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert "Not connected" in response.text


def test_enforce_review_devices_shows_connected_status_for_a_live_device(logged_in_client, session, monkeypatch):
    # Setup
    event = DeviceEventFactory()
    device = event.device
    monkeypatch.setattr(
        usbguard_cli,
        "list_devices",
        lambda: [
            usbguard_cli.ListedDevice(vid=device.vid, pid=device.pid, serial=device.serial, target="allow", hotplug=True)
        ],
    )
    # Action
    response = logged_in_client.get("/settings/enforce-review-devices")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert "Connected now" in response.text


def test_enforce_review_devices_empty_when_nothing_unreviewed(logged_in_client, session):
    # Setup
    WhitelistEntryFactory()
    # Action
    response = logged_in_client.get("/settings/enforce-review-devices")
    # Expected
    assert (response.status_code, response.text) == (status.HTTP_200_OK, "")


def test_switching_to_enforce_applies_immediately_regardless_of_unreviewed_devices(logged_in_client, session):
    # Setup
    DeviceEventFactory()
    # Action
    response = logged_in_client.post("/settings", data={**_BASE_SETTINGS_FORM, "profile": "enforce"})
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert profiles.get_active_profile(session) == Profile.ENFORCE


def test_settings_save_whitelists_selected_devices_and_switches_profile_together(logged_in_client, session):
    # Setup
    event = DeviceEventFactory()
    # Action
    response = logged_in_client.post(
        "/settings",
        data={
            **_BASE_SETTINGS_FORM,
            "profile": "enforce",
            "log_retention": "2_years",
            "device_ids": [event.device_id],
        },
    )
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert session.query(WhitelistEntry).filter_by(device_id=event.device_id).count() == 1
    assert profiles.get_active_profile(session) == Profile.ENFORCE
    assert profiles.get_log_retention(session) == LogRetention.TWO_YEARS


def test_settings_save_with_no_devices_checked_still_switches_profile(logged_in_client, session):
    # Setup
    DeviceEventFactory()
    # Action
    response = logged_in_client.post("/settings", data={**_BASE_SETTINGS_FORM, "profile": "enforce"})
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert session.query(WhitelistEntry).count() == 0
    assert profiles.get_active_profile(session) == Profile.ENFORCE
