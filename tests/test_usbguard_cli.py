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
