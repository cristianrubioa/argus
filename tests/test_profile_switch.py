import pytest

from argus import profiles
from argus.agent import usbguard_cli
from argus.factories import WhitelistEntryFactory
from argus.models import Profile


def _stub_usbguard(monkeypatch, calls):
    monkeypatch.setattr(usbguard_cli, "allow_device", lambda device: calls.append(f"allow:{device.vid_pid}"))
    monkeypatch.setattr(usbguard_cli, "set_implicit_policy_target", lambda target: calls.append(f"set:{target}"))
    monkeypatch.setattr(usbguard_cli, "get_implicit_policy_target", lambda: "block")
    monkeypatch.setattr(usbguard_cli, "list_devices", lambda: [])


def test_switching_to_enforce_does_not_generate_policy(session, monkeypatch):
    # Setup
    calls = []
    _stub_usbguard(monkeypatch, calls)
    profiles.request_profile(session, Profile.ENFORCE)
    # Action
    profiles.reconcile_profile(session)
    # Expected
    assert "generate" not in calls
    settings = profiles.get_settings(session)
    assert settings.applied_profile == Profile.ENFORCE


def test_switching_to_enforce_syncs_every_whitelist_entry(session, monkeypatch):
    # Setup
    calls = []
    _stub_usbguard(monkeypatch, calls)
    WhitelistEntryFactory()
    WhitelistEntryFactory()
    profiles.request_profile(session, Profile.ENFORCE)
    # Action
    profiles.reconcile_profile(session)
    # Expected
    assert calls.count("set:block") == 1
    assert len([c for c in calls if c.startswith("allow:")]) == 2


def test_reconcile_reapplies_when_usbguard_state_drifted(session, monkeypatch):
    # Setup
    calls = []
    _stub_usbguard(monkeypatch, calls)
    profiles.request_profile(session, Profile.MONITOR)
    profiles.reconcile_profile(session)
    # Action
    profiles.reconcile_profile(session)
    # Expected
    assert calls == ["set:allow", "set:allow"]


def test_switching_back_to_monitor_does_not_resync_whitelist(session, monkeypatch):
    # Setup
    calls = []
    _stub_usbguard(monkeypatch, calls)
    entry = WhitelistEntryFactory()
    profiles.request_profile(session, Profile.ENFORCE)
    profiles.reconcile_profile(session)
    # Action
    profiles.request_profile(session, Profile.MONITOR)
    profiles.reconcile_profile(session)
    # Expected
    assert calls == [f"allow:{entry.device.vid_pid}", "set:block", "set:allow"]


def test_switching_to_enforce_blocks_connected_non_whitelisted_devices_live(session, monkeypatch):
    # Setup
    calls = []
    monkeypatch.setattr(usbguard_cli, "allow_device", lambda device: None)
    monkeypatch.setattr(usbguard_cli, "set_implicit_policy_target", lambda target: None)
    monkeypatch.setattr(usbguard_cli, "block_live_devices_except", lambda whitelisted: calls.append(whitelisted))
    monkeypatch.setattr(usbguard_cli, "list_devices", lambda: [])
    entry = WhitelistEntryFactory()
    profiles.request_profile(session, Profile.ENFORCE)
    # Action
    profiles.reconcile_profile(session)
    # Expected
    device = entry.device
    assert calls == [{(device.vid, device.pid, device.serial)}]


def test_switching_to_monitor_restores_live_access(session, monkeypatch):
    # Setup
    calls = []
    monkeypatch.setattr(usbguard_cli, "set_implicit_policy_target", lambda target: None)
    monkeypatch.setattr(usbguard_cli, "allow_live_devices", lambda: calls.append("allow_live"))
    monkeypatch.setattr(usbguard_cli, "list_devices", lambda: [])
    profiles.request_profile(session, Profile.MONITOR)
    # Action
    profiles.reconcile_profile(session)
    # Expected
    assert calls == ["allow_live"]


def test_reconcile_failure_during_whitelist_sync_does_not_partially_apply(session, monkeypatch):
    # Setup
    def _fail(device):
        raise usbguard_cli.UsbguardCliError("denied")

    monkeypatch.setattr(usbguard_cli, "allow_device", _fail)
    WhitelistEntryFactory()
    profiles.request_profile(session, Profile.ENFORCE)
    # Action
    with pytest.raises(usbguard_cli.UsbguardCliError):
        profiles.reconcile_profile(session)
    # Expected
    settings = profiles.get_settings(session)
    assert settings.applied_profile is None


def _stub_reconcile_noop(monkeypatch):
    monkeypatch.setattr(usbguard_cli, "allow_device", lambda device: None)
    monkeypatch.setattr(usbguard_cli, "set_implicit_policy_target", lambda target: None)
    monkeypatch.setattr(usbguard_cli, "get_implicit_policy_target", lambda: "allow")
    monkeypatch.setattr(usbguard_cli, "allow_live_devices", lambda: None)


def test_reconcile_reasserts_drifted_hotplug_device(session, monkeypatch):
    # Setup
    calls = []
    _stub_reconcile_noop(monkeypatch)
    monkeypatch.setattr(usbguard_cli, "allow_device_live", lambda device: calls.append(device.vid_pid))
    entry = WhitelistEntryFactory()
    device = entry.device
    listed = usbguard_cli.ListedDevice(vid=device.vid, pid=device.pid, serial=device.serial, target="block", hotplug=True)
    monkeypatch.setattr(usbguard_cli, "list_devices", lambda: [listed])
    # Action
    profiles.reconcile_profile(session)
    # Expected
    assert calls == [device.vid_pid]


def test_reconcile_never_touches_internal_device_drift(session, monkeypatch):
    # Setup
    calls = []
    _stub_reconcile_noop(monkeypatch)
    monkeypatch.setattr(usbguard_cli, "allow_device_live", lambda device: calls.append(device.vid_pid))
    entry = WhitelistEntryFactory()
    device = entry.device
    listed = usbguard_cli.ListedDevice(vid=device.vid, pid=device.pid, serial=device.serial, target="block", hotplug=False)
    monkeypatch.setattr(usbguard_cli, "list_devices", lambda: [listed])
    # Action
    profiles.reconcile_profile(session)
    # Expected
    assert calls == []


def test_reconcile_skips_whitelisted_device_not_currently_connected(session, monkeypatch):
    # Setup
    calls = []
    _stub_reconcile_noop(monkeypatch)
    monkeypatch.setattr(usbguard_cli, "allow_device_live", lambda device: calls.append(device.vid_pid))
    WhitelistEntryFactory()
    monkeypatch.setattr(usbguard_cli, "list_devices", lambda: [])
    # Action
    profiles.reconcile_profile(session)
    # Expected
    assert calls == []
