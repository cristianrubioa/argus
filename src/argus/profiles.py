from datetime import datetime
from datetime import timezone

from sqlalchemy.orm import Session

from argus import usbguard_cli
from argus.models import Profile
from argus.models import Settings


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def get_settings(session: Session) -> Settings:
    settings = session.get(Settings, 1)
    if settings is None:
        settings = Settings(id=1, profile=Profile.MONITOR)
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
