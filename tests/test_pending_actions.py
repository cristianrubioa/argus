from argus import profiles
from argus.agent import main
from argus.agent import usbguard_cli
from argus.agent.main import apply_pending_actions
from argus.factories import DeviceFactory
from argus.factories import WhitelistEntryFactory
from argus.models import Decision
from argus.models import DeviceEvent
from argus.models import PendingUsbguardAction
from argus.models import Profile
from argus.models import UsbguardAction


def _listed(device, target):
    return usbguard_cli.ListedDevice(
        vid=device.vid, pid=device.pid, serial=device.serial, target=target, hotplug=True, id=1
    )


def _fail_if_called(device):
    raise AssertionError("should not run")


def test_enforce_allow_calls_allow_device_and_records_authorized(session, monkeypatch):
    # Setup
    calls = []
    published = []
    monkeypatch.setattr(usbguard_cli, "allow_device", lambda device: calls.append(("allow", device.id)))
    monkeypatch.setattr(main, "publish_event", lambda event, session: published.append(event))
    entry = WhitelistEntryFactory()
    device = entry.device
    monkeypatch.setattr(usbguard_cli, "list_devices", lambda: [_listed(device, "allow")])
    profiles.request_profile(session, Profile.ENFORCE)
    session.add(PendingUsbguardAction(device=device, action=UsbguardAction.ALLOW))
    session.commit()
    # Action
    apply_pending_actions(session)
    # Expected
    assert calls == [("allow", device.id)]
    pending = session.query(PendingUsbguardAction).one()
    assert pending.applied_at is not None
    event = session.query(DeviceEvent).one()
    assert event.decision == Decision.AUTHORIZED
    assert event.settled_at is not None
    assert published == [event]


def test_enforce_block_calls_deauthorize_device_and_records_blocked(session, monkeypatch):
    # Setup
    calls = []
    monkeypatch.setattr(usbguard_cli, "deauthorize_device", lambda device: calls.append(("deauthorize", device.id)))
    device = DeviceFactory()
    monkeypatch.setattr(usbguard_cli, "list_devices", lambda: [_listed(device, "block")])
    profiles.request_profile(session, Profile.ENFORCE)
    session.add(PendingUsbguardAction(device=device, action=UsbguardAction.BLOCK))
    session.commit()
    # Action
    apply_pending_actions(session)
    # Expected
    assert calls == [("deauthorize", device.id)]
    pending = session.query(PendingUsbguardAction).one()
    assert pending.applied_at is not None
    event = session.query(DeviceEvent).one()
    assert event.decision == Decision.BLOCKED


def test_monitor_allow_writes_no_rule_and_records_authorized(session, monkeypatch):
    # Setup
    monkeypatch.setattr(usbguard_cli, "allow_device", _fail_if_called)
    entry = WhitelistEntryFactory()
    device = entry.device
    monkeypatch.setattr(usbguard_cli, "list_devices", lambda: [_listed(device, "allow")])
    session.add(PendingUsbguardAction(device=device, action=UsbguardAction.ALLOW))
    session.commit()
    # Action
    apply_pending_actions(session)
    # Expected
    pending = session.query(PendingUsbguardAction).one()
    assert pending.applied_at is not None
    event = session.query(DeviceEvent).one()
    assert event.decision == Decision.AUTHORIZED


def test_monitor_revoke_writes_no_rule_and_records_unrecognized(session, monkeypatch):
    # Setup
    monkeypatch.setattr(usbguard_cli, "deauthorize_device", _fail_if_called)
    device = DeviceFactory()
    monkeypatch.setattr(usbguard_cli, "list_devices", lambda: [_listed(device, "allow")])
    session.add(PendingUsbguardAction(device=device, action=UsbguardAction.BLOCK))
    session.commit()
    # Action
    apply_pending_actions(session)
    # Expected
    pending = session.query(PendingUsbguardAction).one()
    assert pending.applied_at is not None
    event = session.query(DeviceEvent).one()
    assert event.decision == Decision.UNRECOGNIZED


def test_no_event_recorded_for_a_disconnected_device(session, monkeypatch):
    # Setup
    monkeypatch.setattr(usbguard_cli, "allow_device", lambda device: None)
    entry = WhitelistEntryFactory()
    device = entry.device
    monkeypatch.setattr(usbguard_cli, "list_devices", lambda: [])
    profiles.request_profile(session, Profile.ENFORCE)
    session.add(PendingUsbguardAction(device=device, action=UsbguardAction.ALLOW))
    session.commit()
    # Action
    apply_pending_actions(session)
    # Expected
    pending = session.query(PendingUsbguardAction).one()
    assert pending.applied_at is not None
    assert session.query(DeviceEvent).count() == 0


def test_no_duplicate_event_when_decision_already_matches(session, monkeypatch):
    # Setup
    published = []
    monkeypatch.setattr(usbguard_cli, "allow_device", lambda device: None)
    monkeypatch.setattr(main, "publish_event", lambda event, session: published.append(event))
    entry = WhitelistEntryFactory()
    device = entry.device
    monkeypatch.setattr(usbguard_cli, "list_devices", lambda: [_listed(device, "allow")])
    profiles.request_profile(session, Profile.ENFORCE)
    session.add(DeviceEvent(device=device, decision=Decision.AUTHORIZED, profile=Profile.ENFORCE, usbguard_connection_id=1))
    session.add(PendingUsbguardAction(device=device, action=UsbguardAction.ALLOW))
    session.commit()
    # Action
    apply_pending_actions(session)
    # Expected
    assert session.query(DeviceEvent).count() == 1
    assert published == []


def test_leaves_applied_at_null_on_failure(session, monkeypatch):
    # Setup
    def _fail(device):
        raise usbguard_cli.UsbguardCliError("denied")

    monkeypatch.setattr(usbguard_cli, "deauthorize_device", _fail)
    device = DeviceFactory()
    profiles.request_profile(session, Profile.ENFORCE)
    session.add(PendingUsbguardAction(device=device, action=UsbguardAction.BLOCK))
    session.commit()
    # Action
    apply_pending_actions(session)
    # Expected
    pending = session.query(PendingUsbguardAction).one()
    assert pending.applied_at is None
