from argus.agent import usbguard_cli
from argus.agent.main import apply_pending_actions
from argus.factories import DeviceFactory
from argus.models import PendingUsbguardAction
from argus.models import UsbguardAction


def test_apply_pending_actions_calls_allow_device_for_allow(session, monkeypatch):
    # Setup
    calls = []
    monkeypatch.setattr(usbguard_cli, "allow_device", lambda device: calls.append(("allow", device.id)))
    device = DeviceFactory()
    session.add(PendingUsbguardAction(device=device, action=UsbguardAction.ALLOW))
    session.commit()
    # Action
    apply_pending_actions(session)
    # Expected
    assert calls == [("allow", device.id)]
    pending = session.query(PendingUsbguardAction).one()
    assert pending.applied_at is not None


def test_apply_pending_actions_calls_deauthorize_device_for_block(session, monkeypatch):
    # Setup
    calls = []
    monkeypatch.setattr(usbguard_cli, "deauthorize_device", lambda device: calls.append(("deauthorize", device.id)))
    device = DeviceFactory()
    session.add(PendingUsbguardAction(device=device, action=UsbguardAction.BLOCK))
    session.commit()
    # Action
    apply_pending_actions(session)
    # Expected
    assert calls == [("deauthorize", device.id)]
    pending = session.query(PendingUsbguardAction).one()
    assert pending.applied_at is not None


def test_apply_pending_actions_leaves_applied_at_null_on_failure(session, monkeypatch):
    # Setup
    def _fail(device):
        raise usbguard_cli.UsbguardCliError("denied")

    monkeypatch.setattr(usbguard_cli, "deauthorize_device", _fail)
    device = DeviceFactory()
    session.add(PendingUsbguardAction(device=device, action=UsbguardAction.BLOCK))
    session.commit()
    # Action
    apply_pending_actions(session)
    # Expected
    pending = session.query(PendingUsbguardAction).one()
    assert pending.applied_at is None
