from datetime import datetime
from datetime import timedelta
from datetime import timezone
from pathlib import Path

from fastapi import APIRouter
from fastapi import Depends
from fastapi import Form
from fastapi import Query
from fastapi import Request
from fastapi import status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_
from sqlalchemy.orm import Session

from argus import profiles
from argus.db import get_session
from argus.models import Device
from argus.models import DeviceEvent
from argus.models import PendingUsbguardAction
from argus.models import Profile
from argus.models import UsbguardAction
from argus.models import WhitelistEntry
from argus.web.auth import authenticate
from argus.web.auth import require_admin
from argus.web.i18n import LANGUAGE_NAMES
from argus.web.i18n import SUPPORTED_LANGUAGES
from argus.web.i18n import t as translate

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

_RECENT_EVENTS_LIMIT = 20
_LOGS_DEFAULT_RANGE_DAYS = 7
_LOGS_DATE_FORMAT = "%Y-%m-%dT%H:%M"


def render(request: Request, session: Session, name: str, context: dict):
    language = profiles.get_language(session)
    full_context = {
        **context,
        "t": lambda key: translate(key, language),
        "language": language,
        "language_names": LANGUAGE_NAMES,
        "supported_languages": SUPPORTED_LANGUAGES,
        "theme": profiles.get_theme(session),
    }
    return templates.TemplateResponse(request, name, full_context)


# --- Auth ---


@router.get("/login")
def login_form(request: Request, session: Session = Depends(get_session)):
    return render(request, session, "login.html", {"error": None})


@router.post("/login")
def login_submit(
    request: Request, username: str = Form(...), password: str = Form(...), session: Session = Depends(get_session)
):
    if not authenticate(session, username, password):
        return render(request, session, "login.html", {"error": "Invalid username or password"})
    request.session["admin"] = username
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)


# --- Dashboard ---


@router.get("/")
def dashboard(request: Request, admin: str = Depends(require_admin), session: Session = Depends(get_session)):
    events = _recent_events(session)
    return render(request, session, "dashboard.html", {"admin": admin, "events": events, "active": "dashboard"})


@router.get("/dashboard/partial")
def dashboard_partial(request: Request, admin: str = Depends(require_admin), session: Session = Depends(get_session)):
    events = _recent_events(session)
    return render(request, session, "_events_table.html", {"events": events})


def _recent_events(session: Session) -> list[DeviceEvent]:
    return session.query(DeviceEvent).order_by(DeviceEvent.occurred_at.desc()).limit(_RECENT_EVENTS_LIMIT).all()


# --- Dispositivos ---


@router.get("/dispositivos")
def devices(request: Request, admin: str = Depends(require_admin), session: Session = Depends(get_session)):
    all_devices = session.query(Device).order_by(Device.last_seen_at.desc()).all()
    whitelisted_ids = {w.device_id for w in session.query(WhitelistEntry).all()}
    return render(
        request,
        session,
        "devices.html",
        {"admin": admin, "devices": all_devices, "whitelisted_ids": whitelisted_ids, "active": "dispositivos"},
    )


# --- Whitelist ---


@router.get("/whitelist")
def whitelist(request: Request, admin: str = Depends(require_admin), session: Session = Depends(get_session)):
    entries = session.query(WhitelistEntry).order_by(WhitelistEntry.added_at.desc()).all()
    return render(request, session, "whitelist.html", {"admin": admin, "entries": entries, "active": "whitelist"})


@router.post("/whitelist/authorize/{device_id}")
def authorize_device(device_id: int, admin: str = Depends(require_admin), session: Session = Depends(get_session)):
    device = session.get(Device, device_id)
    if device is not None and device.whitelist_entry is None:
        session.add(WhitelistEntry(device_id=device.id, added_by=admin))
        if profiles.get_active_profile(session) == Profile.ENFORCE:
            session.add(PendingUsbguardAction(device_id=device.id, action=UsbguardAction.ALLOW))
        session.commit()
    return RedirectResponse(url="/whitelist", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/whitelist/revoke/{device_id}")
def revoke_device(device_id: int, admin: str = Depends(require_admin), session: Session = Depends(get_session)):
    device = session.get(Device, device_id)
    if device is not None and device.whitelist_entry is not None:
        session.delete(device.whitelist_entry)
        if profiles.get_active_profile(session) == Profile.ENFORCE:
            session.add(PendingUsbguardAction(device_id=device.id, action=UsbguardAction.BLOCK))
        session.commit()
    return RedirectResponse(url="/whitelist", status_code=status.HTTP_303_SEE_OTHER)


# --- Logs ---


def _parse_logs_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.strptime(value, _LOGS_DATE_FORMAT).replace(tzinfo=timezone.utc)


def _effective_logs_range(date_from: str | None, date_to: str | None) -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    parsed_from = _parse_logs_datetime(date_from)
    parsed_to = _parse_logs_datetime(date_to)
    return parsed_from or now - timedelta(days=_LOGS_DEFAULT_RANGE_DAYS), parsed_to or now


def _filtered_events(
    session: Session,
    q: str,
    decisions: list[str],
    event_profiles: list[str],
    date_from: datetime,
    date_to: datetime,
) -> list[DeviceEvent]:
    query = session.query(DeviceEvent).join(Device)
    if q:
        like = f"%{q}%"
        vid_pid = Device.vid.op("||")(":").op("||")(Device.pid)
        query = query.filter(or_(Device.name.ilike(like), vid_pid.ilike(like)))
    if decisions:
        query = query.filter(DeviceEvent.decision.in_(decisions))
    if event_profiles:
        query = query.filter(DeviceEvent.profile.in_(event_profiles))
    query = query.filter(DeviceEvent.occurred_at >= date_from, DeviceEvent.occurred_at <= date_to)
    return query.order_by(DeviceEvent.occurred_at.desc()).all()


def _logs_context(
    session: Session,
    q: str,
    decision: list[str],
    profile: list[str],
    date_from: str | None,
    date_to: str | None,
) -> dict:
    effective_from, effective_to = _effective_logs_range(date_from, date_to)
    events = _filtered_events(session, q, decision, profile, effective_from, effective_to)
    return {
        "events": events,
        "q": q,
        "selected_decisions": decision,
        "selected_profiles": profile,
        "date_from": effective_from,
        "date_to": effective_to,
    }


@router.get("/logs")
def logs(
    request: Request,
    q: str = "",
    decision: list[str] = Query(default=[]),
    profile: list[str] = Query(default=[]),
    date_from: str | None = Query(default=None, alias="from"),
    date_to: str | None = Query(default=None, alias="to"),
    admin: str = Depends(require_admin),
    session: Session = Depends(get_session),
):
    context = _logs_context(session, q, decision, profile, date_from, date_to)
    return render(request, session, "logs.html", {"admin": admin, "active": "logs", **context})


@router.get("/logs/partial")
def logs_partial(
    request: Request,
    q: str = "",
    decision: list[str] = Query(default=[]),
    profile: list[str] = Query(default=[]),
    date_from: str | None = Query(default=None, alias="from"),
    date_to: str | None = Query(default=None, alias="to"),
    admin: str = Depends(require_admin),
    session: Session = Depends(get_session),
):
    context = _logs_context(session, q, decision, profile, date_from, date_to)
    return render(request, session, "_events_table.html", context)


# --- Ajustes ---


@router.get("/ajustes")
def settings_page(request: Request, admin: str = Depends(require_admin), session: Session = Depends(get_session)):
    current = profiles.get_settings(session)
    return render(request, session, "settings.html", {"admin": admin, "settings": current, "active": "ajustes"})


@router.post("/ajustes/profile")
def update_profile(
    request: Request,
    profile: str = Form(...),
    admin: str = Depends(require_admin),
    session: Session = Depends(get_session),
):
    profiles.request_profile(session, Profile(profile))
    return RedirectResponse(url="/ajustes", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/ajustes/language")
def update_language(
    request: Request,
    language: str = Form(...),
    admin: str = Depends(require_admin),
    session: Session = Depends(get_session),
):
    if language in SUPPORTED_LANGUAGES:
        profiles.set_language(session, language)
    return RedirectResponse(url="/ajustes", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/ajustes/theme")
def update_theme(
    request: Request,
    theme: str = Form(...),
    admin: str = Depends(require_admin),
    session: Session = Depends(get_session),
):
    if theme in ("light", "dark"):
        profiles.set_theme(session, theme)
    return RedirectResponse(url="/ajustes", status_code=status.HTTP_303_SEE_OTHER)
