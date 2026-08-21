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
from argus.models import AdminAction
from argus.models import AdminActionType
from argus.models import Device
from argus.models import DeviceEvent
from argus.models import PendingUsbguardAction
from argus.models import Profile
from argus.models import UsbguardAction
from argus.models import WhitelistEntry
from argus.web.auth import authenticate
from argus.web.auth import is_locked_out
from argus.web.auth import record_failure
from argus.web.auth import record_success
from argus.web.auth import require_admin
from argus.web.i18n import LANGUAGE_NAMES
from argus.web.i18n import SUPPORTED_LANGUAGES
from argus.web.i18n import t as translate

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

_RECENT_EVENTS_LIMIT = 20
_ADMIN_ACTIONS_LIMIT = 20
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
        "font_size": profiles.get_font_size(session),
        "agent_status": profiles.agent_status(session),
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
    source = request.client.host if request.client else "unknown"
    if is_locked_out(source):
        return render(request, session, "login.html", {"error": "login_error_locked_out"})
    if not authenticate(session, username, password):
        record_failure(source)
        return render(request, session, "login.html", {"error": "login_error_invalid"})
    record_success(source)
    request.session["admin"] = username
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)


# --- Agent status ---


@router.get("/agent-status/partial")
def agent_status_partial(request: Request, admin: str = Depends(require_admin), session: Session = Depends(get_session)):
    return render(request, session, "_agent_status_badge.html", {})


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
        profiles.record_admin_action(
            session,
            admin,
            AdminActionType.WHITELIST_AUTHORIZE,
            device.display_name,
            vid_pid=device.vid_pid,
            serial=device.serial,
        )
    return RedirectResponse(url="/whitelist", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/whitelist/revoke/{device_id}")
def revoke_device(device_id: int, admin: str = Depends(require_admin), session: Session = Depends(get_session)):
    device = session.get(Device, device_id)
    if device is not None and device.whitelist_entry is not None:
        vid_pid, serial, target = device.vid_pid, device.serial, device.display_name
        session.delete(device.whitelist_entry)
        if profiles.get_active_profile(session) == Profile.ENFORCE:
            session.add(PendingUsbguardAction(device_id=device.id, action=UsbguardAction.BLOCK))
        session.commit()
        profiles.record_admin_action(
            session, admin, AdminActionType.WHITELIST_REVOKE, target, vid_pid=vid_pid, serial=serial
        )
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
        old_name = device.display_name
        new_name = custom_name.strip() or None
        if new_name != old_name:
            device.custom_name = new_name
            session.commit()
            profiles.record_admin_action(
                session,
                admin,
                AdminActionType.DEVICE_RENAME,
                new_name or device.name,
                vid_pid=device.vid_pid,
                serial=device.serial,
                source=old_name,
            )
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
    "serial": Device.serial,
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
        query = query.filter(or_(Device.name.ilike(like), vid_pid.ilike(like), Device.serial.ilike(like)))
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


_ADMIN_ACTIONS_SORT_COLUMNS = {
    "action_type": AdminAction.action_type,
    "vid_pid": AdminAction.vid_pid,
    "serial": AdminAction.serial,
    "source": AdminAction.source,
    "target": AdminAction.target,
    "occurred_at": AdminAction.occurred_at,
}
_ADMIN_ACTIONS_DEFAULT_SORT = "occurred_at"


def _filtered_admin_actions(
    session: Session,
    q: str,
    action_types: list[str],
    date_from: datetime,
    date_to: datetime,
    sort: str,
    direction: str,
    page: int,
) -> tuple[list[AdminAction], int]:
    query = session.query(AdminAction)
    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(
                AdminAction.actor.ilike(like),
                AdminAction.vid_pid.ilike(like),
                AdminAction.serial.ilike(like),
                AdminAction.source.ilike(like),
                AdminAction.target.ilike(like),
            )
        )
    if action_types:
        query = query.filter(AdminAction.action_type.in_(action_types))
    query = query.filter(AdminAction.occurred_at >= date_from, AdminAction.occurred_at <= date_to)
    total = query.count()
    column = _ADMIN_ACTIONS_SORT_COLUMNS[sort]
    ordered = column.asc() if direction == "asc" else column.desc()
    actions = query.order_by(ordered).offset((page - 1) * _ADMIN_ACTIONS_LIMIT).limit(_ADMIN_ACTIONS_LIMIT).all()
    return actions, total


def _admin_actions_filter_query_string(q: str, action_types: list[str], date_from: datetime, date_to: datetime) -> str:
    params = [("a_q", q)] if q else []
    params += [("a_action", a) for a in action_types]
    params += [("a_from", date_from.strftime(_LOGS_DATE_FORMAT)), ("a_to", date_to.strftime(_LOGS_DATE_FORMAT))]
    return urlencode(params)


def _admin_actions_sort_links(filter_query_string: str, sort: str, direction: str) -> dict[str, str]:
    links = {}
    for column in _ADMIN_ACTIONS_SORT_COLUMNS:
        next_dir = "desc" if sort == column and direction == "asc" else "asc"
        links[column] = f"/logs?{filter_query_string}&a_sort={column}&a_dir={next_dir}&tab=actions"
    return links


def _admin_actions_context(
    session: Session,
    q: str,
    action_types: list[str],
    date_from: str | None,
    date_to: str | None,
    sort: str,
    direction: str,
    page: int,
) -> dict:
    effective_from, effective_to = _effective_logs_range(date_from, date_to)
    sort = sort if sort in _ADMIN_ACTIONS_SORT_COLUMNS else _ADMIN_ACTIONS_DEFAULT_SORT
    direction = direction if direction in ("asc", "desc") else "desc"
    page = max(page, 1)
    actions, total = _filtered_admin_actions(session, q, action_types, effective_from, effective_to, sort, direction, page)
    total_pages = max((total + _ADMIN_ACTIONS_LIMIT - 1) // _ADMIN_ACTIONS_LIMIT, 1)
    filter_query_string = _admin_actions_filter_query_string(q, action_types, effective_from, effective_to)
    page_link_base = f"/logs?{filter_query_string}&a_sort={sort}&a_dir={direction}&tab=actions"
    return {
        "admin_actions": actions,
        "a_q": q,
        "a_selected_actions": action_types,
        "a_date_from": effective_from,
        "a_date_to": effective_to,
        "a_sort": sort,
        "a_dir": direction,
        "a_page": page,
        "a_total_pages": total_pages,
        "a_total_count": total,
        "a_range_start": (page - 1) * _ADMIN_ACTIONS_LIMIT + 1 if total > 0 else 0,
        "a_range_end": min(page * _ADMIN_ACTIONS_LIMIT, total),
        "a_sort_links": _admin_actions_sort_links(filter_query_string, sort, direction),
        "a_prev_page_link": f"{page_link_base}&a_page={max(page - 1, 1)}",
        "a_next_page_link": f"{page_link_base}&a_page={min(page + 1, total_pages)}",
    }


_LOGS_TABS = ("events", "actions")


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
    a_q: str = "",
    a_action: list[str] = Query(default=[]),
    a_from: str | None = Query(default=None),
    a_to: str | None = Query(default=None),
    a_sort: str = _ADMIN_ACTIONS_DEFAULT_SORT,
    a_dir: str = "desc",
    a_page: int = 1,
    tab: str = "events",
    admin: str = Depends(require_admin),
    session: Session = Depends(get_session),
):
    context = _logs_context(session, q, decision, profile, date_from, date_to, sort, dir, page)
    admin_actions_context = _admin_actions_context(session, a_q, a_action, a_from, a_to, a_sort, a_dir, a_page)
    tab = tab if tab in _LOGS_TABS else "events"
    return render(
        request,
        session,
        "logs.html",
        {"admin": admin, "active": "logs", "tab": tab, **context, **admin_actions_context},
    )


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


@router.post("/ajustes")
def update_settings(
    request: Request,
    profile: str = Form(...),
    language: str = Form(...),
    theme: str = Form(...),
    font_size: str = Form(...),
    admin: str = Depends(require_admin),
    session: Session = Depends(get_session),
):
    """Single confirm gate for the whole Ajustes form — every field commits together, or not at all."""
    old_profile = profiles.get_active_profile(session)
    new_profile = Profile(profile)
    profiles.request_profile(session, new_profile)
    if new_profile != old_profile:
        profiles.record_admin_action(
            session, admin, AdminActionType.PROFILE_SWITCH, new_profile.value, source=old_profile.value
        )
    if language in SUPPORTED_LANGUAGES:
        profiles.set_language(session, language)
    if theme in ("light", "dark"):
        profiles.set_theme(session, theme)
    if font_size in ("md", "lg"):
        profiles.set_font_size(session, font_size)
    return RedirectResponse(url="/ajustes", status_code=status.HTTP_303_SEE_OTHER)
