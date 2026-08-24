import subprocess

import pytest

from argus.agent import usbguard_cli
from argus.models import Device


def test_run_raises_on_ipc_error_despite_exit_code_zero(monkeypatch):
    # Setup
    fake_result = subprocess.CompletedProcess(
        args=["usbguard"], returncode=0, stdout="IPC ERROR: Permission denied", stderr=""
    )
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: fake_result)
    # Action & Expected
    with pytest.raises(usbguard_cli.UsbguardCliError):
        usbguard_cli._run("append-rule", "allow id 1234:5678")


def test_list_devices_parses_hotplug_and_hardwired_entries(monkeypatch):
    # Setup
    output = (
        '8: allow id 1d6b:0002 serial "0000:00:0d.0" name "xHCI Host Controller" hash "x" parent-hash "y" '
        'via-port "usb1" with-interface 09:00:00 with-connect-type ""\n'
        '12: block id 046d:c542 serial "" name "Wireless Receiver" hash "x" parent-hash "y" via-port "3-5" '
        'with-interface 03:01:02 with-connect-type "hotplug"\n'
    )
    monkeypatch.setattr(usbguard_cli, "_run", lambda *a: output)
    # Action
    devices = usbguard_cli.list_devices()
    # Expected
    assert devices == [
        usbguard_cli.ListedDevice(vid="1d6b", pid="0002", serial="0000:00:0d.0", target="allow", hotplug=False),
        usbguard_cli.ListedDevice(vid="046d", pid="c542", serial=None, target="block", hotplug=True),
    ]


def test_list_rules_parses_id_and_target(monkeypatch):
    # Setup
    output = (
        '5: allow id 046d:c542 serial "" name "Wireless Receiver" hash "x" parent-hash "y" via-port "3-5" '
        'with-interface 03:01:02 with-connect-type "hotplug"\n'
        '16: block id 058f:6387 serial "AAE9055C" name "Mass Storage" hash "x" with-interface 08:06:50 '
        'with-connect-type "hotplug"\n'
    )
    monkeypatch.setattr(usbguard_cli, "_run", lambda *a: output)
    # Action
    rules = usbguard_cli.list_rules()
    # Expected
    assert rules == [
        usbguard_cli.ListedRule(id=5, vid="046d", pid="c542", serial=None, target="allow"),
        usbguard_cli.ListedRule(id=16, vid="058f", pid="6387", serial="AAE9055C", target="block"),
    ]


def test_remove_rule_passes_id_as_string(monkeypatch):
    # Setup
    calls = []
    monkeypatch.setattr(usbguard_cli, "_run", lambda *a: calls.append(a))
    # Action
    usbguard_cli.remove_rule(16)
    # Expected
    assert calls == [("remove-rule", "16")]


def test_deauthorize_device_removes_every_matching_rule(monkeypatch):
    # Setup
    device = Device(vid="058f", pid="6387", name="Mass Storage", serial="AAE9055C")
    rules = [
        usbguard_cli.ListedRule(id=16, vid="058f", pid="6387", serial="AAE9055C", target="allow"),
        usbguard_cli.ListedRule(id=22, vid="058f", pid="6387", serial="AAE9055C", target="allow"),
        usbguard_cli.ListedRule(id=5, vid="046d", pid="c542", serial=None, target="allow"),
    ]
    monkeypatch.setattr(usbguard_cli, "list_rules", lambda: rules)
    removed = []
    monkeypatch.setattr(usbguard_cli, "remove_rule", lambda rule_id: removed.append(rule_id))
    # Action
    usbguard_cli.deauthorize_device(device)
    # Expected
    assert removed == [16, 22]


def test_deauthorize_device_is_a_no_op_when_nothing_matches(monkeypatch):
    # Setup
    device = Device(vid="058f", pid="6387", name="Mass Storage", serial="AAE9055C")
    other_rule = usbguard_cli.ListedRule(id=5, vid="046d", pid="c542", serial=None, target="allow")
    monkeypatch.setattr(usbguard_cli, "list_rules", lambda: [other_rule])
    removed = []
    monkeypatch.setattr(usbguard_cli, "remove_rule", lambda rule_id: removed.append(rule_id))
    # Action
    usbguard_cli.deauthorize_device(device)
    # Expected
    assert removed == []


def test_allow_device_live_omits_permanent_flag(monkeypatch):
    # Setup
    calls = []
    monkeypatch.setattr(usbguard_cli, "_run", lambda *a: calls.append(a))
    device = Device(vid="046d", pid="c542", name="Wireless Receiver")
    # Action
    usbguard_cli.allow_device_live(device)
    # Expected
    assert calls == [("allow-device", "id 046d:c542")]


def test_get_implicit_policy_target_strips_and_lowercases(monkeypatch):
    # Setup
    monkeypatch.setattr(usbguard_cli, "_run", lambda *a: "Block\n")
    # Action & Expected
    assert usbguard_cli.get_implicit_policy_target() == "block"


def test_warn_if_untested_version_logs_on_mismatch(monkeypatch, caplog):
    # Setup
    monkeypatch.setattr(usbguard_cli, "_run", lambda *a: "usbguard 9.9.9\n")
    # Action
    with caplog.at_level("WARNING"):
        usbguard_cli.warn_if_untested_version()
    # Expected
    assert "differs from the tested version" in caplog.text


def test_warn_if_untested_version_silent_on_match(monkeypatch, caplog):
    # Setup
    monkeypatch.setattr(usbguard_cli, "_run", lambda *a: f"usbguard {usbguard_cli.TESTED_VERSION}\n")
    # Action
    with caplog.at_level("WARNING"):
        usbguard_cli.warn_if_untested_version()
    # Expected
    assert caplog.text == ""
