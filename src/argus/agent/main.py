import logging
import threading
import time
from datetime import datetime
from datetime import timedelta
from datetime import timezone

from sqlalchemy.orm import Session

from argus import profiles
from argus.agent import usbguard_cli
from argus.agent import watcher
from argus.agent.mqtt_bridge import publish_event
from argus.agent.parser import ParsedEvent
from argus.agent.parser import ParsedPolicySettled
from argus.agent.parser import parse_event_block
from argus.agent.parser import parse_policy_settled_block
from argus.db import SessionLocal
from argus.db import init_db
from argus.models import Device
from argus.models import DeviceEvent
from argus.models import PendingUsbguardAction
from argus.models import Profile
from argus.models import UsbguardAction

logger = logging.getLogger(__name__)

_PENDING_ACTIONS_POLL_SECONDS = 2

# Covers composite-device bursts (~20-50ms) and slow storage enumeration (observed: 805ms).
_DEDUPE_WINDOW_SECONDS = 1.5


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _get_or_create_device(session: Session, parsed: ParsedEvent) -> Device:
    device = session.query(Device).filter_by(vid=parsed.vid, pid=parsed.pid, serial=parsed.serial).first()
    if device is None:
        device = Device(
            vid=parsed.vid, pid=parsed.pid, name=parsed.name, serial=parsed.serial, connect_type=parsed.connect_type
        )
        session.add(device)
        session.flush()
    else:
        device.last_seen_at = _utcnow()
        device.name = parsed.name
        device.connect_type = parsed.connect_type
    return device


def handle_event(session: Session, block: str) -> None:
    parsed = parse_event_block(block)
    if parsed is not None:
        _handle_insert(session, parsed)
        return

    settled = parse_policy_settled_block(block)
    if settled is not None:
        _handle_policy_settled(session, settled)


def _handle_insert(session: Session, parsed: ParsedEvent) -> None:
    device = _get_or_create_device(session, parsed)
    if _recently_recorded(session, device):
        session.commit()
        return

    decision = profiles.decide(session, device, parsed.usbguard_blocked)
    event = profiles.record_event(session, device, decision, parsed.connection_id)
    session.commit()
    publish_event(event, session)


def _handle_policy_settled(session: Session, settled: ParsedPolicySettled) -> None:
    """The first PolicyChanged/PolicyApplied for a connection settles its still-provisional Insert
    decision in place. Once settled, a row is never mutated again by this path — a later change caused
    by an admin action is recorded synchronously by apply_pending_actions() instead (not reactively here),
    since nothing guarantees this watch-stream notification arrives in the same order Argus issued the
    IPC calls that caused it (confirmed live: it doesn't)."""
    event = (
        session.query(DeviceEvent)
        .filter_by(usbguard_connection_id=settled.connection_id)
        .order_by(DeviceEvent.id.desc())
        .first()
    )
    if event is None or event.settled_at is not None:
        return

    decision = profiles.decide(session, event.device, settled.usbguard_blocked)
    event.settled_at = _utcnow()
    if event.decision != decision:
        event.decision = decision
        session.commit()
        publish_event(event, session)
    else:
        session.commit()


def _recently_recorded(session: Session, device: Device) -> bool:
    cutoff = _utcnow() - timedelta(seconds=_DEDUPE_WINDOW_SECONDS)
    return (
        session.query(DeviceEvent).filter(DeviceEvent.device_id == device.id, DeviceEvent.occurred_at > cutoff).first()
        is not None
    )


def apply_pending_actions(session: Session) -> None:
    pending = session.query(PendingUsbguardAction).filter_by(applied_at=None).all()
    for action in pending:
        try:
            if profiles.get_active_profile(session) == Profile.ENFORCE:
                if action.action == UsbguardAction.ALLOW:
                    usbguard_cli.allow_device(action.device)
                else:
                    usbguard_cli.deauthorize_device(action.device)
            event = profiles.record_resulting_event(session, action.device)
            if event is not None:
                publish_event(event, session)
            action.applied_at = _utcnow()
        except usbguard_cli.UsbguardCliError:
            logger.exception("Failed to apply pending USBGuard action for device %s", action.device.vid_pid)
    session.commit()


def _watch_loop() -> None:
    while True:
        for block in watcher.watch_events():
            with SessionLocal() as session:
                try:
                    handle_event(session, block)
                except Exception:
                    logger.exception("Failed to handle usbguard watch event: %s", block)
        logger.warning("usbguard watch exited; restarting")


def _reconcile_and_publish(session: Session) -> None:
    for event in profiles.reconcile_profile(session):
        publish_event(event, session)


def _reconcile_loop() -> None:
    while True:
        with SessionLocal() as session:
            profiles.record_agent_heartbeat(session)
            profiles.prune_old_events(session)
            apply_pending_actions(session)
            try:
                _reconcile_and_publish(session)
            except usbguard_cli.UsbguardCliError:
                logger.exception("Failed to reconcile security profile")
        time.sleep(_PENDING_ACTIONS_POLL_SECONDS)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    init_db()
    usbguard_cli.warn_if_untested_version()
    with SessionLocal() as session:
        try:
            _reconcile_and_publish(session)
        except usbguard_cli.UsbguardCliError:
            logger.exception("Failed to reconcile security profile at startup")
    threading.Thread(target=_watch_loop, daemon=True).start()
    _reconcile_loop()


if __name__ == "__main__":
    main()
