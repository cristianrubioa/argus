from datetime import datetime
from datetime import timedelta
from datetime import timezone

from sqlalchemy.orm import Session

from argus import config
from argus import version_check
from argus.agent import usbguard_cli
from argus.models import AdminAction
from argus.models import AdminActionType
from argus.models import AgentStatus
from argus.models import Device
from argus.models import DeviceEvent
from argus.models import PendingUsbguardAction
from argus.models import Profile
from argus.models import Settings
from argus.models import WhitelistEntry

_SETTINGS_ID = 1
_HEARTBEAT_STALE_SECONDS = 30
_LOG_PRUNE_CHECK_INTERVAL = timedelta(hours=24)
_VERSION_CHECK_INTERVAL = timedelta(hours=24)


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
    """Called from argus-agent's reconcile loop, every cycle; no-ops unless retention is configured and due."""
    retention_days = config.log_retention_days()
    if retention_days is None:
        return

    settings = get_settings(session)
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


def reconcile_profile(session: Session) -> None:
    """Called from argus-agent's poll loop; applies a pending profile change to USBGuard (syncing every
    whitelist entry to a real rule and cutting live access for every connected non-whitelisted device on
    switch to Enforce), re-applies the implicit policy target if USBGuard's live state has drifted from
    it, and reconciles live authorization drift for whitelisted external devices."""
    settings = get_settings(session)
    desired_target = "block" if settings.profile == Profile.ENFORCE else "allow"

    if settings.profile != settings.applied_profile:
        if settings.profile == Profile.ENFORCE:
            entries = session.query(WhitelistEntry).all()
            for entry in entries:
                usbguard_cli.allow_device(entry.device)
            # USBGuard doesn't retroactively re-evaluate an already-connected device just because the
            # implicit target changed (same finding as deauthorize_device) — cut live access for
            # anything connected and not whitelisted before flipping the target, same ordering reason.
            whitelisted_identities = {(e.device.vid, e.device.pid, e.device.serial) for e in entries}
            usbguard_cli.block_live_devices_except(whitelisted_identities)

        usbguard_cli.set_implicit_policy_target(desired_target)
        settings.applied_profile = settings.profile
        session.commit()
    elif usbguard_cli.get_implicit_policy_target() != desired_target:
        usbguard_cli.set_implicit_policy_target(desired_target)

    _reconcile_whitelist_drift(session)


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
    """Devices with at least one DeviceEvent but no WhitelistEntry — surfaced by the Enforce-transition
    review modal before switching to Enforce."""
    return (
        session.query(Device)
        .filter(Device.events.any())
        .filter(~Device.whitelist_entry.has())
        .order_by(Device.last_seen_at.desc())
        .all()
    )
