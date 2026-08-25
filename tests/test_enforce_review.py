from fastapi import status

from argus import profiles
from argus.agent import usbguard_cli
from argus.factories import DeviceEventFactory
from argus.factories import WhitelistEntryFactory
from argus.models import Profile
from argus.models import WhitelistEntry


def test_switching_to_enforce_with_unreviewed_device_shows_review_modal(logged_in_client, session, monkeypatch):
    # Setup
    monkeypatch.setattr(usbguard_cli, "list_devices", lambda: [])
    DeviceEventFactory()
    # Action
    response = logged_in_client.post(
        "/settings",
        data={"profile": "enforce", "language": "en", "theme": "dark", "font_size": "md", "log_retention": "1_year"},
    )
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert profiles.get_active_profile(session) == Profile.MONITOR
    assert "enforce-review" in response.text
    modal_form = response.text.split('action="/settings/enforce-review"')[1].split("</form>")[0]
    assert modal_form.count('type="submit"') == 1
    assert "Not connected" in response.text


def test_switching_to_enforce_shows_connected_status_for_a_live_device(logged_in_client, session, monkeypatch):
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
    response = logged_in_client.post(
        "/settings",
        data={"profile": "enforce", "language": "en", "theme": "dark", "font_size": "md", "log_retention": "1_year"},
    )
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert "Connected now" in response.text


def test_switching_to_enforce_with_nothing_unreviewed_applies_immediately(logged_in_client, session):
    # Setup
    WhitelistEntryFactory()
    # Action
    response = logged_in_client.post(
        "/settings",
        data={"profile": "enforce", "language": "en", "theme": "dark", "font_size": "md", "log_retention": "1_year"},
    )
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert profiles.get_active_profile(session) == Profile.ENFORCE


def test_enforce_review_whitelists_checked_devices_and_switches_profile(logged_in_client, session):
    # Setup
    event = DeviceEventFactory()
    # Action
    response = logged_in_client.post("/settings/enforce-review", data={"device_ids": [event.device_id]})
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert session.query(WhitelistEntry).filter_by(device_id=event.device_id).count() == 1
    assert profiles.get_active_profile(session) == Profile.ENFORCE


def test_enforce_review_with_nothing_checked_still_switches_profile(logged_in_client, session):
    # Setup
    DeviceEventFactory()
    # Action
    response = logged_in_client.post("/settings/enforce-review", data={})
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert session.query(WhitelistEntry).count() == 0
    assert profiles.get_active_profile(session) == Profile.ENFORCE
