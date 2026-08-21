from datetime import datetime
from datetime import timedelta
from datetime import timezone

from sqlalchemy.orm import Session

from argus import config
from argus.agent import usbguard_cli
from argus.models import AdminAction
from argus.models import AdminActionType
from argus.models import AgentStatus
from argus.models import DeviceEvent
from argus.models import PendingUsbguardAction
from argus.models import Profile
from argus.models import Settings

_SETTINGS_ID = 1
_HEARTBEAT_STALE_SECONDS = 30
_LOG_PRUNE_CHECK_INTERVAL = timedelta(hours=24)


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
    source: str | None = None,
) -> None:
    session.add(AdminAction(actor=actor, action_type=action_type, vid_pid=vid_pid, source=source, target=target))
    session.commit()


def recent_admin_actions(session: Session, limit: int) -> list[AdminAction]:
    return session.query(AdminAction).order_by(AdminAction.occurred_at.desc()).limit(limit).all()


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


def reconcile_profile(session: Session) -> None:
    """Called from argus-agent's poll loop; applies a pending profile change to USBGuard."""
    settings = get_settings(session)
    if settings.profile == settings.applied_profile:
        return

    if settings.profile == Profile.ENFORCE and settings.enforce_bootstrapped_at is None:
        usbguard_cli.generate_policy()
        settings.enforce_bootstrapped_at = _utcnow()

    usbguard_cli.set_implicit_policy_target("block" if settings.profile == Profile.ENFORCE else "allow")
    settings.applied_profile = settings.profile
    session.commit()
