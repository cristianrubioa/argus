"""Subprocess wrapper around `usbguard watch` — USBGuard's own native-IPC event
stream (design.md decision #2). No D-Bus, no extra service.
"""

import subprocess
from collections.abc import Iterator


def watch_events() -> Iterator[str]:
    """Yields raw stdout lines from `usbguard watch -w` (-w: wait for the IPC
    connection instead of exiting if the daemon isn't up yet). Runs until the
    subprocess exits; the caller is expected to restart the loop on exit.
    """
    process = subprocess.Popen(
        ["usbguard", "watch", "-w"],
        stdout=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    assert process.stdout is not None
    try:
        for line in process.stdout:
            line = line.strip()
            if line:
                yield line
    finally:
        process.terminate()
