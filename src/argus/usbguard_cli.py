"""Thin wrapper around the `usbguard` CLI.

Every write goes through USBGuard's own IPC commands — never by editing
/etc/usbguard/rules.conf or reloading the daemon ourselves (see design.md
decision #3). Requires the running user to hold an IPC access grant from
`usbguard add-user` (see design.md decision #4) — no root needed.
"""

import subprocess

from argus.models import Device


class UsbguardCliError(RuntimeError):
    pass


def _run(*args: str) -> str:
    try:
        result = subprocess.run(["usbguard", *args], capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as exc:
        raise UsbguardCliError(f"usbguard {' '.join(args)} failed: {exc.stderr.strip()}") from exc
    except FileNotFoundError as exc:
        raise UsbguardCliError("usbguard CLI not found on this host") from exc
    return result.stdout


def _partial_rule(device: Device) -> str:
    rule = f"id {device.vid}:{device.pid}"
    if device.serial:
        rule += f' serial "{device.serial}"'
    return rule


def allow_device(device: Device) -> None:
    _run("allow-device", "--permanent", _partial_rule(device))


def block_device(device: Device) -> None:
    _run("block-device", "--permanent", _partial_rule(device))


def set_implicit_policy_target(target: str) -> None:
    """target is 'allow' (Monitor profile) or 'block' (Enforce profile)."""
    _run("set-parameter", "ImplicitPolicyTarget", target)


def generate_policy() -> str:
    """Returns a rule set authorizing currently connected devices, as text
    (usbguard-rules.conf(5) format) — used to bootstrap the whitelist on
    first switch to Enforce (design.md decision #6).
    """
    return _run("generate-policy")
