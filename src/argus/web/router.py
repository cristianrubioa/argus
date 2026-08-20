from datetime import datetime
from datetime import timedelta
from datetime import timezone
from pathlib import Path
from urllib.parse import urlencode

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


@router.post("/whitelist/rename/{device_id}")
def rename_device(
    device_id: int,
    custom_name: str = Form(""),
    admin: str = Depends(require_admin),
    session: Session = Depends(get_session),
):
    device = session.get(Device, device_id)
    if device is not None and device.whitelist_entry is not None:
        device.custom_name = custom_name.strip() or None
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


_LOGS_SORT_COLUMNS = {
    "name": Device.name,
    "vid_pid": Device.vid.op("||")(":").op("||")(Device.pid),
    "decision": DeviceEvent.decision,
    "profile": DeviceEvent.profile,
    "occurred_at": DeviceEvent.occurred_at,
}
_LOGS_DEFAULT_SORT = "occurred_at"


def _filtered_events(
    session: Session,
    q: str,
    decisions: list[str],
    event_profiles: list[str],
    date_from: datetime,
    date_to: datetime,
    sort: str,
    direction: str,
    page: int,
) -> tuple[list[DeviceEvent], int]:
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
    total = query.count()
    column = _LOGS_SORT_COLUMNS[sort]
    ordered = column.asc() if direction == "asc" else column.desc()
    events = query.order_by(ordered).offset((page - 1) * _RECENT_EVENTS_LIMIT).limit(_RECENT_EVENTS_LIMIT).all()
    return events, total


def _logs_filter_query_string(
    q: str, decision: list[str], profile: list[str], date_from: datetime, date_to: datetime
) -> str:
    params = [("q", q)] if q else []
    params += [("decision", d) for d in decision]
    params += [("profile", p) for p in profile]
    params += [("from", date_from.strftime(_LOGS_DATE_FORMAT)), ("to", date_to.strftime(_LOGS_DATE_FORMAT))]
    return urlencode(params)


def _logs_sort_links(filter_query_string: str, sort: str, direction: str) -> dict[str, str]:
    links = {}
    for column in _LOGS_SORT_COLUMNS:
        next_dir = "desc" if sort == column and direction == "asc" else "asc"
        links[column] = f"/logs?{filter_query_string}&sort={column}&dir={next_dir}"
    return links


def _logs_context(
    session: Session,
    q: str,
    decision: list[str],
    profile: list[str],
    date_from: str | None,
    date_to: str | None,
    sort: str,
    direction: str,
    page: int,
) -> dict:
    effective_from, effective_to = _effective_logs_range(date_from, date_to)
    sort = sort if sort in _LOGS_SORT_COLUMNS else _LOGS_DEFAULT_SORT
    direction = direction if direction in ("asc", "desc") else "desc"
    page = max(page, 1)
    events, total = _filtered_events(session, q, decision, profile, effective_from, effective_to, sort, direction, page)
    total_pages = max((total + _RECENT_EVENTS_LIMIT - 1) // _RECENT_EVENTS_LIMIT, 1)
    filter_query_string = _logs_filter_query_string(q, decision, profile, effective_from, effective_to)
    page_link_base = f"/logs?{filter_query_string}&sort={sort}&dir={direction}"
    return {
        "events": events,
        "q": q,
        "selected_decisions": decision,
        "selected_profiles": profile,
        "date_from": effective_from,
        "date_to": effective_to,
        "sort": sort,
        "dir": direction,
        "page": page,
        "total_pages": total_pages,
        "total_count": total,
        "range_start": (page - 1) * _RECENT_EVENTS_LIMIT + 1 if total > 0 else 0,
        "range_end": min(page * _RECENT_EVENTS_LIMIT, total),
        "sort_links": _logs_sort_links(filter_query_string, sort, direction),
        "prev_page_link": f"{page_link_base}&page={max(page - 1, 1)}",
        "next_page_link": f"{page_link_base}&page={min(page + 1, total_pages)}",
    }


@router.get("/logs")
def logs(
    request: Request,
    q: str = "",
    decision: list[str] = Query(default=[]),
    profile: list[str] = Query(default=[]),
    date_from: str | None = Query(default=None, alias="from"),
    date_to: str | None = Query(default=None, alias="to"),
    sort: str = _LOGS_DEFAULT_SORT,
    dir: str = "desc",
    page: int = 1,
    admin: str = Depends(require_admin),
    session: Session = Depends(get_session),
):
    context = _logs_context(session, q, decision, profile, date_from, date_to, sort, dir, page)
    return render(request, session, "logs.html", {"admin": admin, "active": "logs", **context})


@router.get("/logs/partial")
def logs_partial(
    request: Request,
    q: str = "",
    decision: list[str] = Query(default=[]),
    profile: list[str] = Query(default=[]),
    date_from: str | None = Query(default=None, alias="from"),
    date_to: str | None = Query(default=None, alias="to"),
    sort: str = _LOGS_DEFAULT_SORT,
    dir: str = "desc",
    page: int = 1,
    admin: str = Depends(require_admin),
    session: Session = Depends(get_session),
):
    context = _logs_context(session, q, decision, profile, date_from, date_to, sort, dir, page)
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
