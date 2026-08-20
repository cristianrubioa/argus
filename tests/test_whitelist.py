from argus import profiles
from argus.factories import DeviceFactory
from argus.models import PendingUsbguardAction
from argus.models import Profile
from argus.models import UsbguardAction
from argus.models import WhitelistEntry


def test_authorize_in_monitor_profile_does_not_enqueue_usbguard_action(logged_in_client, session):
    # Setup
    device = DeviceFactory()
    # Action
    response = logged_in_client.post(f"/whitelist/authorize/{device.id}")
    # Expected
    assert response.status_code == 200
    assert session.query(WhitelistEntry).filter_by(device_id=device.id).count() == 1
    assert session.query(PendingUsbguardAction).count() == 0


def test_authorize_in_enforce_profile_enqueues_allow_action(logged_in_client, session):
    # Setup
    device = DeviceFactory()
    profiles.request_profile(session, Profile.ENFORCE)
    # Action
    response = logged_in_client.post(f"/whitelist/authorize/{device.id}")
    # Expected
    assert response.status_code == 200
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
    assert response.status_code == 200
    assert session.query(WhitelistEntry).filter_by(device_id=device.id).count() == 0
    block_actions = session.query(PendingUsbguardAction).filter_by(device_id=device.id, action=UsbguardAction.BLOCK)
    assert block_actions.count() == 1
