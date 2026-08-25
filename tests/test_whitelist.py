from fastapi import status

from argus import profiles
from argus.factories import DeviceFactory
from argus.models import PendingUsbguardAction
from argus.models import Profile
from argus.models import UsbguardAction
from argus.models import WhitelistEntry


def test_whitelist_page_shows_device_serial(logged_in_client, session):
    # Setup
    device = DeviceFactory(serial="AAE9055C")
    session.add(WhitelistEntry(device_id=device.id, added_by="test-admin"))
    session.commit()
    # Action
    response = logged_in_client.get("/whitelist")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert "AAE9055C" in response.text


def test_whitelist_page_labels_the_action_column(logged_in_client, session):
    # Setup
    device = DeviceFactory()
    session.add(WhitelistEntry(device_id=device.id, added_by="test-admin"))
    session.commit()
    # Action
    response = logged_in_client.get("/whitelist")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert '<th class="py-2 pr-4"></th>' not in response.text


def test_authorize_in_monitor_profile_still_enqueues_an_action(logged_in_client, session):
    # Setup
    device = DeviceFactory()
    # Action
    response = logged_in_client.post(f"/whitelist/authorize/{device.id}")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert session.query(WhitelistEntry).filter_by(device_id=device.id).count() == 1
    pending = session.query(PendingUsbguardAction).filter_by(device_id=device.id).one()
    assert pending.action == UsbguardAction.ALLOW
    assert "Device authorized." in response.text


def test_authorizing_an_already_whitelisted_device_shows_a_failure_toast(logged_in_client, session):
    # Setup
    device = DeviceFactory()
    session.add(WhitelistEntry(device_id=device.id, added_by="test-admin"))
    session.commit()
    # Action
    response = logged_in_client.post(f"/whitelist/authorize/{device.id}")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert "Couldn&#39;t authorize the device." in response.text


def test_authorize_in_enforce_profile_enqueues_allow_action(logged_in_client, session):
    # Setup
    device = DeviceFactory()
    profiles.request_profile(session, Profile.ENFORCE)
    # Action
    response = logged_in_client.post(f"/whitelist/authorize/{device.id}")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    pending = session.query(PendingUsbguardAction).filter_by(device_id=device.id).one()
    assert pending.action == UsbguardAction.ALLOW
    assert pending.applied_at is None


def test_revoke_in_enforce_profile_enqueues_block_action(logged_in_client, session):
    # Setup
    device = DeviceFactory()
    profiles.request_profile(session, Profile.ENFORCE)
    logged_in_client.post(f"/whitelist/authorize/{device.id}")
    # Action
    response = logged_in_client.post(f"/whitelist/revoke/{device.id}")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert session.query(WhitelistEntry).filter_by(device_id=device.id).count() == 0
    block_actions = session.query(PendingUsbguardAction).filter_by(device_id=device.id, action=UsbguardAction.BLOCK)
    assert block_actions.count() == 1
    assert "Device revoked." in response.text


def test_revoking_a_device_that_is_not_whitelisted_shows_a_failure_toast(logged_in_client, session):
    # Setup
    device = DeviceFactory()
    # Action
    response = logged_in_client.post(f"/whitelist/revoke/{device.id}")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert "Couldn&#39;t revoke the device." in response.text
