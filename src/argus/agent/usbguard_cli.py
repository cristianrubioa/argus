"""Thin wrapper around the `usbguard` CLI — writes go through IPC, never rules.conf directly (decision #3)."""

import logging
import re
import subprocess
from dataclasses import dataclass

from argus.models import Device

logger = logging.getLogger(__name__)

# e.g. `12: allow id 046d:c542 serial "" name "Wireless Receiver" hash "..." ... with-connect-type "hotplug"`
# Shared by list-devices and list-rules — both usbguard subcommands emit the same line shape.
_RULE_LINE_RE = re.compile(
    r"^(?P<id>\d+):\s+(?P<target>\w+)\s+id\s+(?P<vid>[0-9a-fA-F]{4}):(?P<pid>[0-9a-fA-F]{4})"
    r'.*?\bserial\s+"(?P<serial>[^"]*)".*?\bwith-connect-type\s+"(?P<connect_type>[^"]*)"'
)

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


def allow_device_live(device: Device) -> None:
    """Non-permanent allow — corrects live runtime authorization without touching the saved rule.
    Accepts the same vid:pid/serial partial-rule spec as the --permanent form (confirmed via
    `usbguard allow-device --help` on the tested version: both take `<id> | <rule> | <partial-rule>`)."""
    _run("allow-device", _partial_rule(device))


def block_device_live(device: Device) -> None:
    """Non-permanent block — see allow_device_live()."""
    _run("block-device", _partial_rule(device))


@dataclass(frozen=True)
class ListedDevice:
    vid: str
    pid: str
    serial: str | None
    target: str
    hotplug: bool


def list_devices() -> list[ListedDevice]:
    """Runs `usbguard list-devices` once, for reconciling live authorization against saved rules
    without one subprocess call per whitelist entry."""
    devices = []
    for line in _run("list-devices").splitlines():
        match = _RULE_LINE_RE.match(line.strip())
        if match is None:
            continue
        devices.append(
            ListedDevice(
                vid=match.group("vid").lower(),
                pid=match.group("pid").lower(),
                serial=match.group("serial") or None,
                target=match.group("target").lower(),
                hotplug=match.group("connect_type") == "hotplug",
            )
        )
    return devices


@dataclass(frozen=True)
class ListedRule:
    id: int
    vid: str
    pid: str
    serial: str | None
    target: str


def list_rules() -> list[ListedRule]:
    """Runs `usbguard list-rules` once, for finding a device's existing permanent rule(s) to remove."""
    rules = []
    for line in _run("list-rules").splitlines():
        match = _RULE_LINE_RE.match(line.strip())
        if match is None:
            continue
        rules.append(
            ListedRule(
                id=int(match.group("id")),
                vid=match.group("vid").lower(),
                pid=match.group("pid").lower(),
                serial=match.group("serial") or None,
                target=match.group("target").lower(),
            )
        )
    return rules


def remove_rule(rule_id: int) -> None:
    _run("remove-rule", str(rule_id))


def deauthorize_device(device: Device) -> None:
    """Removes every existing permanent rule matching this device's identity, instead of writing an
    explicit block rule: confirmed live that `block-device --permanent` silently no-ops against a
    pre-existing conflicting `allow` rule (no error, rule left unchanged). With no rule left matching
    the device, Enforce's ImplicitPolicyTarget blocks it by default on its next connection.

    Also cuts the device's live authorization immediately if it's currently connected — confirmed live
    that removing the backing rule alone doesn't affect an already-authorized connection, only the next
    one. Unlike the drift-reconcile's external-only restriction, this isn't filtered by connect-type:
    revoke is always a direct admin decision about one specific already-whitelisted device."""
    for rule in list_rules():
        if rule.vid == device.vid and rule.pid == device.pid and rule.serial == device.serial:
            remove_rule(rule.id)

    is_connected = any(d.vid == device.vid and d.pid == device.pid and d.serial == device.serial for d in list_devices())
    if is_connected:
        block_device_live(device)


def set_implicit_policy_target(target: str) -> None:
    """target is 'allow' (Monitor profile) or 'block' (Enforce profile)."""
    _run("set-parameter", "ImplicitPolicyTarget", target)


def get_implicit_policy_target() -> str:
    """set-parameter is runtime-only — a restart of usbguard.service outside of us reverts
    this to whatever's in usbguard-daemon.conf, regardless of what Argus last applied."""
    return _run("get-parameter", "ImplicitPolicyTarget").strip().lower()


def warn_if_untested_version() -> None:
    """Best-effort startup check — logs a warning if the installed usbguard differs from TESTED_VERSION."""
    try:
        installed = _run("--version").strip()
    except UsbguardCliError:
        logger.warning("Could not determine installed usbguard version")
        return
    if TESTED_VERSION not in installed:
        logger.warning("Installed usbguard (%s) differs from the tested version (%s)", installed, TESTED_VERSION)
