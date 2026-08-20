"""Parses `usbguard watch` stdout lines into device events.

UNVERIFIED FORMAT: USBGuard's public docs and man pages don't document watch's
exact line format (see design.md risk + tasks.md 3.2/10.1 — this needs
confirming against a real host with USBGuard installed). This parser assumes
the same attribute=value / attribute="value" grammar USBGuard uses elsewhere
(usbguard-rules.conf, generate-policy output), with attribute names id, name,
serial, and a target keyword (allow/block/reject) as documented for its
D-Bus device-attribute dictionary. Adjust the regexes below once real output
is available — everything else in the agent is independent of this format.
"""

import re
from dataclasses import dataclass

_ID_RE = re.compile(r"\bid\s+([0-9a-fA-F]{4}):([0-9a-fA-F]{4})\b")
_NAME_RE = re.compile(r'\bname\s+"([^"]*)"')
_SERIAL_RE = re.compile(r'\bserial\s+"([^"]*)"')
_TARGET_RE = re.compile(r"\b(allow|block|reject)\b", re.IGNORECASE)


@dataclass(frozen=True)
class ParsedEvent:
    vid: str
    pid: str
    name: str
    serial: str | None
    usbguard_blocked: bool


def parse_event_line(line: str) -> ParsedEvent | None:
    """Returns None for lines that aren't device events (e.g. connection status
    messages usbguard watch prints while waiting for the IPC connection).
    """
    id_match = _ID_RE.search(line)
    if id_match is None:
        return None

    target_match = _TARGET_RE.search(line)
    target = target_match.group(1).lower() if target_match else "allow"

    name_match = _NAME_RE.search(line)
    serial_match = _SERIAL_RE.search(line)

    return ParsedEvent(
        vid=id_match.group(1).lower(),
        pid=id_match.group(2).lower(),
        name=name_match.group(1) if name_match else "Unknown device",
        serial=serial_match.group(1) if serial_match else None,
        usbguard_blocked=target in ("block", "reject"),
    )
