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
    """The admin's desired profile — used to tag events, independent of whether
    argus-agent has finished reconciling it with USBGuard yet.
    """
    return get_settings(session).profile


def request_profile(session: Session, profile: Profile) -> Settings:
    """Called from argus-web (Ajustes page). Only records what the admin wants —
    argus-web has no path to USBGuard's host-local IPC socket, so it cannot apply
    the change itself (design.md decision #1a). argus-agent's poller reconciles it.
    """
    settings = get_settings(session)
    settings.profile = profile
    session.commit()
    return settings


def reconcile_profile(session: Session) -> None:
    """Called from argus-agent's poll loop. If the desired profile differs from what
    was last applied, does the actual USBGuard work: bootstrap the whitelist on the
    first-ever switch to Enforce (design.md decision #6), then push
    ImplicitPolicyTarget.
    """
    settings = get_settings(session)
    if settings.profile == settings.applied_profile:
        return

    if settings.profile == Profile.ENFORCE and settings.enforce_bootstrapped_at is None:
        usbguard_cli.generate_policy()
        settings.enforce_bootstrapped_at = _utcnow()

    usbguard_cli.set_implicit_policy_target("block" if settings.profile == Profile.ENFORCE else "allow")
    settings.applied_profile = settings.profile
    session.commit()
