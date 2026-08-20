import logging
import threading
import time
from datetime import datetime
from datetime import timezone

from sqlalchemy.orm import Session

from argus import profiles
from argus import usbguard_cli
from argus.agent import watcher
from argus.agent.mqtt_bridge import publish_event
from argus.agent.parser import parse_event_line
from argus.db import SessionLocal
from argus.db import init_db
from argus.models import Decision
from argus.models import Device
from argus.models import DeviceEvent
from argus.models import PendingUsbguardAction
from argus.models import UsbguardAction
from argus.models import WhitelistEntry

logger = logging.getLogger(__name__)

_PENDING_ACTIONS_POLL_SECONDS = 2


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _get_or_create_device(session: Session, parsed) -> Device:
    device = session.query(Device).filter_by(vid=parsed.vid, pid=parsed.pid, serial=parsed.serial).first()
    if device is None:
        device = Device(vid=parsed.vid, pid=parsed.pid, name=parsed.name, serial=parsed.serial)
        session.add(device)
        session.flush()
    else:
        device.last_seen_at = _utcnow()
        device.name = parsed.name
    return device


def handle_line(session: Session, line: str) -> None:
    parsed = parse_event_line(line)
    if parsed is None:
        return

    device = _get_or_create_device(session, parsed)
    is_whitelisted = session.query(WhitelistEntry).filter_by(device_id=device.id).first() is not None

    if is_whitelisted:
        decision = Decision.AUTHORIZED
    elif parsed.usbguard_blocked:
        decision = Decision.BLOCKED
    else:
        decision = Decision.UNRECOGNIZED

    event = _record_event(session, device, decision)
    session.commit()
    publish_event(device, event.decision)


def _record_event(session: Session, device: Device, decision: Decision) -> DeviceEvent:
    active_profile = profiles.get_active_profile(session)
    event = DeviceEvent(device=device, decision=decision, profile=active_profile)
    session.add(event)
    session.flush()
    return event


def apply_pending_actions(session: Session) -> None:
    pending = session.query(PendingUsbguardAction).filter_by(applied_at=None).all()
    for action in pending:
        try:
            if action.action == UsbguardAction.ALLOW:
                usbguard_cli.allow_device(action.device)
            else:
                usbguard_cli.block_device(action.device)
            action.applied_at = _utcnow()
        except usbguard_cli.UsbguardCliError:
            logger.exception("Failed to apply pending USBGuard action for device %s", action.device.vid_pid)
    session.commit()


def _watch_loop() -> None:
    while True:
        for line in watcher.watch_events():
            with SessionLocal() as session:
                try:
                    handle_line(session, line)
                except Exception:
                    logger.exception("Failed to handle usbguard watch line: %s", line)
        logger.warning("usbguard watch exited; restarting")


def _reconcile_loop() -> None:
    while True:
        with SessionLocal() as session:
            apply_pending_actions(session)
            profiles.reconcile_profile(session)
        time.sleep(_PENDING_ACTIONS_POLL_SECONDS)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    init_db()
    threading.Thread(target=_watch_loop, daemon=True).start()
    _reconcile_loop()


if __name__ == "__main__":
    main()
