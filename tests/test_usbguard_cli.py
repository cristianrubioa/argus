import subprocess

import pytest

from argus import usbguard_cli


def test_run_raises_on_ipc_error_despite_exit_code_zero(monkeypatch):
    # Setup — usbguard append-rule prints "IPC ERROR: ... Permission denied" but exits 0
    fake_result = subprocess.CompletedProcess(
        args=["usbguard"], returncode=0, stdout="IPC ERROR: Permission denied", stderr=""
    )
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: fake_result)
    # Action & Expected
    with pytest.raises(usbguard_cli.UsbguardCliError):
        usbguard_cli._run("append-rule", "allow id 1234:5678")


def test_generate_policy_applies_every_line_via_append_rule(monkeypatch):
    # Setup
    policy_text = (
        'allow id 058f:6387 serial "AAE9055C" name "Mass Storage"\nallow id 046d:c542 serial "" name "Wireless Receiver"\n'
    )
    calls = []

    def fake_run(*args):
        calls.append(args)
        return policy_text if args[0] == "generate-policy" else ""

    monkeypatch.setattr(usbguard_cli, "_run", fake_run)
    # Action
    usbguard_cli.generate_policy()
    # Expected
    assert calls[0] == ("generate-policy",)
    assert calls[1] == ("append-rule", 'allow id 058f:6387 serial "AAE9055C" name "Mass Storage"')
    assert calls[2] == ("append-rule", 'allow id 046d:c542 serial "" name "Wireless Receiver"')
