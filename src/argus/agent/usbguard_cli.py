"""Thin wrapper around the `usbguard` CLI — writes go through IPC, never rules.conf directly (decision #3)."""

import logging
import subprocess

from argus.models import Device

logger = logging.getLogger(__name__)

# Ubuntu Noble's usbguard 1.1.2+ds-6build2 — the version parser.py and this module were validated against.
TESTED_VERSION = "1.1.2"


class UsbguardCliError(RuntimeError):
    pass


def _run(*args: str) -> str:
    try:
        result = subprocess.run(["usbguard", *args], capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as exc:
        raise UsbguardCliError(f"usbguard {' '.join(args)} failed: {exc.stderr.strip()}") from exc
    except FileNotFoundError as exc:
        raise UsbguardCliError("usbguard CLI not found on this host") from exc
    # Not every usbguard subcommand signals an IPC failure via exit code (e.g. append-rule exits 0 on "Permission denied").
    if "ERROR" in result.stdout or "ERROR" in result.stderr:
        raise UsbguardCliError(f"usbguard {' '.join(args)} failed: {(result.stdout + result.stderr).strip()}")
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


def generate_policy() -> None:
    """Authorizes every connected device via IPC — bootstraps the whitelist on first switch to Enforce (decision #6)."""
    for line in _run("generate-policy").splitlines():
        line = line.strip()
        if line:
            _run("append-rule", line)


def warn_if_untested_version() -> None:
    """Best-effort startup check — logs a warning if the installed usbguard differs from TESTED_VERSION."""
    try:
        installed = _run("--version").strip()
    except UsbguardCliError:
        logger.warning("Could not determine installed usbguard version")
        return
    if TESTED_VERSION not in installed:
        logger.warning("Installed usbguard (%s) differs from the tested version (%s)", installed, TESTED_VERSION)
