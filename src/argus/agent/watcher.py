"""Subprocess wrapper around `usbguard watch` — USBGuard's native-IPC event stream (design.md decision #2)."""

import subprocess
from collections.abc import Iterator


def watch_events() -> Iterator[str]:
    """Yields one joined event block per device event. Restart the loop on exit — this runs until the subprocess exits."""
    # usbguard fully block-buffers its stdout when it isn't a tty (i.e. always, piped here) — stdbuf
    # forces line buffering so events arrive as they happen instead of whenever its internal buffer fills.
    process = subprocess.Popen(
        ["stdbuf", "-oL", "usbguard", "watch", "-w"],
        stdout=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    assert process.stdout is not None
    block: list[str] = []
    try:
        for raw_line in process.stdout:
            line = raw_line.rstrip("\n")
            if not line:
                continue
            if not line.startswith(" ") and block:
                yield "\n".join(block)
                block = []
            block.append(line)
        if block:
            yield "\n".join(block)
    finally:
        process.terminate()
