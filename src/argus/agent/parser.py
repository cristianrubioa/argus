"""Parses `usbguard watch` event blocks (format confirmed on a real host, see tests/test_events.py for a sample).
Only `PresenceChanged`/`event=Insert` blocks are a connection; `PolicyChanged`/`PolicyApplied`/`Remove` are ignored.
"""

import re
from dataclasses import dataclass

_PRESENCE_CHANGED_RE = re.compile(r"^\[device\] PresenceChanged:")
_EVENT_RE = re.compile(r"^\s*event=(\w+)", re.MULTILINE)
_TARGET_RE = re.compile(r"^\s*target=(\w+)", re.MULTILINE)
_ID_RE = re.compile(r"\bid\s+([0-9a-fA-F]{4}):([0-9a-fA-F]{4})\b")
_NAME_RE = re.compile(r'\bname\s+"([^"]*)"')
_SERIAL_RE = re.compile(r'\bserial\s+"([^"]*)"')


@dataclass(frozen=True)
class ParsedEvent:
    vid: str
    pid: str
    name: str
    serial: str | None
    usbguard_blocked: bool


def parse_event_block(block: str) -> ParsedEvent | None:
    """None for anything that isn't a device connecting (status lines, PolicyChanged/PolicyApplied, Remove)."""
    first_line = block.splitlines()[0]
    if not _PRESENCE_CHANGED_RE.match(first_line):
        return None

    event_match = _EVENT_RE.search(block)
    if event_match is None or event_match.group(1) != "Insert":
        return None

    id_match = _ID_RE.search(block)
    if id_match is None:
        return None

    target_match = _TARGET_RE.search(block)
    target = target_match.group(1).lower() if target_match else "allow"
    name_match = _NAME_RE.search(block)
    serial_match = _SERIAL_RE.search(block)
    serial = serial_match.group(1) if serial_match else None

    return ParsedEvent(
        vid=id_match.group(1).lower(),
        pid=id_match.group(2).lower(),
        name=name_match.group(1) if name_match else "Unknown device",
        serial=serial if serial else None,
        usbguard_blocked=target in ("block", "reject"),
    )
