import logging
from datetime import datetime
from datetime import timedelta
from datetime import timezone

from sqlalchemy.orm import Session

from argus import version_check
from argus.agent import usbguard_cli
from argus.models import AdminAction
from argus.models import AdminActionType
from argus.models import AgentStatus
from argus.models import Decision
from argus.models import Device
from argus.models import DeviceEvent
from argus.models import LogRetention
from argus.models import PendingUsbguardAction
from argus.models import Profile
from argus.models import Settings
from argus.models import UsbguardAction
from argus.models import WhitelistEntry

logger = logging.getLogger(__name__)

_SETTINGS_ID = 1
_HEARTBEAT_STALE_SECONDS = 30
_LOG_PRUNE_CHECK_INTERVAL = timedelta(hours=24)
_VERSION_CHECK_INTERVAL = timedelta(hours=24)

_RETENTION_DAYS = {
    LogRetention.NINETY_DAYS: 90,
    LogRetention.ONE_YEAR: 365,
    LogRetention.TWO_YEARS: 730,
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware(dt: datetime) -> datetime:
    """SQLite drops tzinfo on round-trip; every timestamp this module writes is UTC (_utcnow())."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def get_settings(session: Session) -> Settings:
    settings = session.get(Settings, _SETTINGS_ID)
    if settings is None:
        settings = Settings(id=_SETTINGS_ID, profile=Profile.MONITOR)
        session.add(settings)
        session.commit()
    return settings


def get_active_profile(session: Session) -> Profile:
    """The admin's desired profile, used to tag events (may not be applied yet)."""
    return get_settings(session).profile


def request_profile(session: Session, profile: Profile) -> Settings:
    """Called from argus-web. Only records the desired profile — argus-agent applies it (design.md decision #1a)."""
    settings = get_settings(session)
    settings.profile = profile
    session.commit()
    return settings


def get_language(session: Session) -> str:
    return get_settings(session).language


def set_language(session: Session, language: str) -> Settings:
    settings = get_settings(session)
    settings.language = language
    session.commit()
    return settings


def get_theme(session: Session) -> str:
    return get_settings(session).theme


def set_theme(session: Session, theme: str) -> Settings:
    settings = get_settings(session)
    settings.theme = theme
    session.commit()
    return settings


def get_font_size(session: Session) -> str:
    return get_settings(session).font_size


def set_font_size(session: Session, font_size: str) -> Settings:
    settings = get_settings(session)
    settings.font_size = font_size
    session.commit()
    return settings


def get_log_retention(session: Session) -> LogRetention:
    return get_settings(session).log_retention


def set_log_retention(session: Session, log_retention: LogRetention) -> Settings:
    settings = get_settings(session)
    settings.log_retention = log_retention
    session.commit()
    return settings


def record_agent_heartbeat(session: Session) -> None:
    """Called from argus-agent's reconcile loop, every cycle, regardless of what else the cycle does."""
    settings = get_settings(session)
    settings.agent_last_heartbeat_at = _utcnow()
    session.commit()


def agent_status(session: Session) -> AgentStatus:
    last_heartbeat = get_settings(session).agent_last_heartbeat_at
    if last_heartbeat is None:
        return AgentStatus.NEVER
    if _utcnow() - _as_aware(last_heartbeat) > timedelta(seconds=_HEARTBEAT_STALE_SECONDS):
        return AgentStatus.STALE
    return AgentStatus.LIVE


def record_admin_action(
    session: Session,
    actor: str,
    action_type: AdminActionType,
    target: str,
    vid_pid: str | None = None,
    serial: str | None = None,
    source: str | None = None,
) -> None:
    session.add(
        AdminAction(actor=actor, action_type=action_type, vid_pid=vid_pid, serial=serial, source=source, target=target)
    )
    session.commit()


def prune_old_events(session: Session) -> None:
    """Called from argus-agent's reconcile loop, every cycle; no-ops unless retention is finite and due."""
    settings = get_settings(session)
    retention_days = _RETENTION_DAYS.get(settings.log_retention)
    if retention_days is None:
        return

    if settings.last_log_prune_at is not None:
        if _utcnow() - _as_aware(settings.last_log_prune_at) < _LOG_PRUNE_CHECK_INTERVAL:
            return

    cutoff = _utcnow() - timedelta(days=retention_days)
    session.query(DeviceEvent).filter(DeviceEvent.occurred_at < cutoff).delete()
    session.query(PendingUsbguardAction).filter(
        PendingUsbguardAction.applied_at.is_not(None), PendingUsbguardAction.applied_at < cutoff
    ).delete()
    session.query(AdminAction).filter(AdminAction.occurred_at < cutoff).delete()
    settings.last_log_prune_at = _utcnow()
    session.commit()


def refresh_version_check(session: Session) -> None:
    """No-ops unless the cached check is missing or stale (_VERSION_CHECK_INTERVAL). A failed fetch
    still updates version_checked_at (so a down/unreachable source isn't retried every request), but
    leaves the last successfully fetched latest_version_available in place rather than clearing it."""
    settings = get_settings(session)
    if settings.version_checked_at is not None:
        if _utcnow() - _as_aware(settings.version_checked_at) < _VERSION_CHECK_INTERVAL:
            return

    latest = version_check.fetch_latest_version()
    if latest is not None:
        settings.latest_version_available = latest
    settings.version_checked_at = _utcnow()
    session.commit()


def decide(session: Session, device: Device, usbguard_blocked: bool) -> Decision:
    is_whitelisted = session.query(WhitelistEntry).filter_by(device_id=device.id).first() is not None
    if is_whitelisted:
        return Decision.AUTHORIZED
    return Decision.BLOCKED if usbguard_blocked else Decision.UNRECOGNIZED


def record_event(
    session: Session, device: Device, decision: Decision, connection_id: int, settled_at: datetime | None = None
) -> DeviceEvent:
    event = DeviceEvent(
        device=device,
        decision=decision,
        profile=get_active_profile(session),
        usbguard_connection_id=connection_id,
        settled_at=settled_at,
    )
    session.add(event)
    session.flush()
    return event


def record_event_for_listed(session: Session, device: Device, listed: usbguard_cli.ListedDevice) -> DeviceEvent | None:
    """Given an already-known live match, decide and record the resulting event — correcting a still-
    provisional row in place, creating a new settled row if the most recent one already settled to a
    different decision, or no-op if it already matches. Returns the event created/updated, or None."""
    computed = decide(session, device, listed.target in ("block", "reject"))
    event = session.query(DeviceEvent).filter_by(usbguard_connection_id=listed.id).order_by(DeviceEvent.id.desc()).first()

    if event is not None and event.decision == computed:
        return None

    if event is not None and event.settled_at is None:
        event.decision = computed
        event.settled_at = _utcnow()
        session.commit()
        return event

    new_event = record_event(session, device, computed, listed.id, settled_at=_utcnow())
    session.commit()
    return new_event


def record_resulting_event(session: Session, device: Device) -> DeviceEvent | None:
    """After an admin authorize/revoke has been applied — a real USBGuard write in Enforce, or nothing
    at all in Monitor — find the device's current live connection (if any) and record the resulting
    event, rather than waiting for a usbguard watch notification (confirmed live: its arrival order
    relative to the IPC calls that caused it isn't guaranteed). Returns None if not currently connected —
    nothing happened at the USB level to log yet."""
    live = next(
        (
            d
            for d in usbguard_cli.list_devices()
            if d.vid == device.vid and d.pid == device.pid and d.serial == device.serial
        ),
        None,
    )
    if live is None:
        return None
    return record_event_for_listed(session, device, live)


def reconcile_profile(session: Session) -> list[DeviceEvent]:
    """Called from argus-agent's poll loop; applies a pending profile change to USBGuard (syncing every
    whitelist entry to a real rule and cutting live access for every connected non-whitelisted device on
    switch to Enforce, or restoring live access to everything connected on switch to Monitor), re-applies
    the implicit policy target if USBGuard's live state has drifted from it, and reconciles live
    authorization drift for whitelisted external devices. Returns every event recorded as a result of the
    sweep, for the caller to publish — this module can't import publish_event (mqtt_bridge already
    imports profiles, so the reverse import would cycle)."""
    settings = get_settings(session)
    desired_target = UsbguardAction.BLOCK if settings.profile == Profile.ENFORCE else UsbguardAction.ALLOW
    events: list[DeviceEvent] = []

    if settings.profile != settings.applied_profile:
        if settings.profile == Profile.ENFORCE:
            entries = session.query(WhitelistEntry).all()
            for entry in entries:
                usbguard_cli.allow_device(entry.device)
            # USBGuard doesn't retroactively re-evaluate an already-connected device just because the
            # implicit target changed (same finding as deauthorize_device) — cut live access for
            # anything connected and not whitelisted before flipping the target, same ordering reason.
            whitelisted_identities = {(e.device.vid, e.device.pid, e.device.serial) for e in entries}
            touched = usbguard_cli.block_live_devices_except(whitelisted_identities)
        else:
            # Same reasoning, mirrored: Monitor never blocks, so restore live access to everything
            # connected before flipping the target — nothing should stay blocked from a prior Enforce
            # session just because it hasn't reconnected yet.
            touched = usbguard_cli.allow_live_devices()

        for listed in touched:
            device = session.query(Device).filter_by(vid=listed.vid, pid=listed.pid, serial=listed.serial).first()
            if device is None:
                continue
            event = record_event_for_listed(session, device, listed)
            if event is not None:
                events.append(event)

        usbguard_cli.set_implicit_policy_target(desired_target)
        settings.applied_profile = settings.profile
        session.commit()
    elif usbguard_cli.get_implicit_policy_target() != desired_target:
        usbguard_cli.set_implicit_policy_target(desired_target)

    _reconcile_whitelist_drift(session)
    return events


def _reconcile_whitelist_drift(session: Session) -> None:
    """Re-asserts live authorization for whitelisted external (hotplug) devices whose runtime state has
    drifted from `allow`, without touching their saved rule. Internal/hardwired devices are never
    touched, whitelisted or not (design.md decision #4)."""
    entries = session.query(WhitelistEntry).all()
    if not entries:
        return

    listed_by_identity = {(d.vid, d.pid, d.serial): d for d in usbguard_cli.list_devices()}
    for entry in entries:
        device = entry.device
        listed = listed_by_identity.get((device.vid, device.pid, device.serial))
        if listed is None or not listed.hotplug:
            continue
        if listed.target != "allow":
            usbguard_cli.allow_device_live(device)


def unreviewed_devices(session: Session) -> list[Device]:
    """Devices with at least one DeviceEvent but no WhitelistEntry, and known (or currently confirmed) to
    be external (hotplug) — internal/hardwired devices, and devices whose connect-type is unknown and not
    currently connected, are never surfaced for review. Argus has no business managing authorization for
    hardware that isn't a removable peripheral."""
    candidates = (
        session.query(Device)
        .filter(Device.events.any())
        .filter(~Device.whitelist_entry.has())
        .order_by(Device.last_seen_at.desc())
        .all()
    )
    unknown = [d for d in candidates if d.connect_type is None]
    live_hotplug_identities: set[tuple[str, str, str | None]] = set()
    if unknown:
        try:
            live_hotplug_identities = {(d.vid, d.pid, d.serial) for d in usbguard_cli.list_devices() if d.hotplug}
        except usbguard_cli.UsbguardCliError:
            logger.warning("Could not list live USBGuard devices while checking unreviewed devices")

    return [
        device
        for device in candidates
        if device.connect_type == "hotplug"
        or (device.connect_type is None and (device.vid, device.pid, device.serial) in live_hotplug_identities)
    ]
