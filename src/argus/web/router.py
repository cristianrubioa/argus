import logging
from pathlib import Path

from fastapi import APIRouter
from fastapi import Depends
from fastapi import Form
from fastapi import Query
from fastapi import Request
from fastapi import status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from argus import profiles
from argus import version_check
from argus.agent import usbguard_cli
from argus.db import get_session
from argus.models import AdminAction
from argus.models import AdminActionType
from argus.models import Device
from argus.models import DeviceEvent
from argus.models import FontSize
from argus.models import LogRetention
from argus.models import PendingUsbguardAction
from argus.models import Profile
from argus.models import Theme
from argus.models import UsbguardAction
from argus.models import VersionStatus
from argus.models import WhitelistEntry
from argus.web import listing
from argus.web.auth import admin_exists
from argus.web.auth import authenticate
from argus.web.auth import change_password
from argus.web.auth import create_admin_account
from argus.web.auth import is_locked_out
from argus.web.auth import is_password_valid
from argus.web.auth import record_failure
from argus.web.auth import record_success
from argus.web.auth import require_admin
from argus.web.i18n import LANGUAGE_NAMES
from argus.web.i18n import SUPPORTED_LANGUAGES
from argus.web.i18n import t as translate

logger = logging.getLogger(__name__)

router = APIRouter()
register_router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

_RECENT_EVENTS_LIMIT = 20
_ADMIN_ACTIONS_LIMIT = 20


def _version_state(session: Session) -> dict:
    profiles.refresh_version_check(session)
    settings = profiles.get_settings(session)
    installed = version_check.installed_version()
    if settings.latest_version_available is None:
        version_status = VersionStatus.UNKNOWN
    elif version_check.is_newer(settings.latest_version_available, installed):
        version_status = VersionStatus.UPDATE_AVAILABLE
    else:
        version_status = VersionStatus.UP_TO_DATE
    return {"installed": installed, "status": version_status, "latest": settings.latest_version_available}


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
        "version_state": _version_state(session),
    }
    return templates.TemplateResponse(request, name, full_context)


# --- Auth ---


@register_router.get("/register")
def register_form(request: Request, session: Session = Depends(get_session)):
    if admin_exists(session):
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    return render(request, session, "register.html", {"error": None})


@register_router.post("/register")
def register_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    session: Session = Depends(get_session),
):
    if admin_exists(session):
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    if not is_password_valid(password, confirm_password):
        error = "password_error_mismatch" if password != confirm_password else "password_error_too_short"
        return render(request, session, "register.html", {"error": error})
    create_admin_account(session, username, password)
    request.session["admin"] = username
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)


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
def agent_status_partial(request: Request, _admin: str = Depends(require_admin), session: Session = Depends(get_session)):
    return render(request, session, "_agent_status_badge.html", {})


# --- Dashboard ---


@router.get("/")
def dashboard(request: Request, admin: str = Depends(require_admin), session: Session = Depends(get_session)):
    events = _recent_events(session)
    return render(request, session, "dashboard.html", {"admin": admin, "events": events, "active": "dashboard"})


@router.get("/dashboard/partial")
def dashboard_partial(request: Request, _admin: str = Depends(require_admin), session: Session = Depends(get_session)):
    events = _recent_events(session)
    return render(request, session, "_events_table.html", {"events": events})


def _recent_events(session: Session) -> list[DeviceEvent]:
    return session.query(DeviceEvent).order_by(DeviceEvent.occurred_at.desc()).limit(_RECENT_EVENTS_LIMIT).all()


# --- Devices ---


@router.get("/devices")
def devices(request: Request, admin: str = Depends(require_admin), session: Session = Depends(get_session)):
    all_devices = session.query(Device).order_by(Device.last_seen_at.desc()).all()
    whitelisted_ids = {w.device_id for w in session.query(WhitelistEntry).all()}
    return render(
        request,
        session,
        "devices.html",
        {"admin": admin, "devices": all_devices, "whitelisted_ids": whitelisted_ids, "active": "devices"},
    )


# --- Whitelist ---


@router.get("/whitelist")
def whitelist(request: Request, admin: str = Depends(require_admin), session: Session = Depends(get_session)):
    entries = session.query(WhitelistEntry).order_by(WhitelistEntry.added_at.desc()).all()
    return render(request, session, "whitelist.html", {"admin": admin, "entries": entries, "active": "whitelist"})


def _authorize_device(session: Session, admin: str, device_id: int) -> None:
    device = session.get(Device, device_id)
    if device is not None and device.whitelist_entry is None:
        session.add(WhitelistEntry(device_id=device.id, added_by=admin))
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


@router.post("/whitelist/authorize/{device_id}")
def authorize_device(device_id: int, admin: str = Depends(require_admin), session: Session = Depends(get_session)):
    _authorize_device(session, admin, device_id)
    return RedirectResponse(url="/whitelist", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/whitelist/revoke/{device_id}")
def revoke_device(device_id: int, admin: str = Depends(require_admin), session: Session = Depends(get_session)):
    device = session.get(Device, device_id)
    if device is not None and device.whitelist_entry is not None:
        vid_pid, serial, target = device.vid_pid, device.serial, device.display_name
        session.delete(device.whitelist_entry)
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


_LOGS_SORT_COLUMNS = {
    "name": Device.name,
    "vid_pid": Device.vid.op("||")(":").op("||")(Device.pid),
    "serial": Device.serial,
    "decision": DeviceEvent.decision,
    "profile": DeviceEvent.profile,
    "occurred_at": DeviceEvent.occurred_at,
}
_LOGS_DEFAULT_SORT = "occurred_at"

_ADMIN_ACTIONS_SORT_COLUMNS = {
    "action_type": AdminAction.action_type,
    "vid_pid": AdminAction.vid_pid,
    "serial": AdminAction.serial,
    "source": AdminAction.source,
    "target": AdminAction.target,
    "occurred_at": AdminAction.occurred_at,
}
_ADMIN_ACTIONS_DEFAULT_SORT = "occurred_at"

_LOGS_TABS = ("events", "actions")


def _events_listing(session: Session) -> listing.ListingSpec:
    vid_pid = Device.vid.op("||")(":").op("||")(Device.pid)
    return listing.ListingSpec(
        prefix="",
        base_path="/logs",
        tab_suffix="",
        items_key="events",
        query=session.query(DeviceEvent).join(Device),
        search_columns=(Device.name, vid_pid, Device.serial),
        category_filters=(
            listing.CategoryFilter("decision", "selected_decisions", DeviceEvent.decision),
            listing.CategoryFilter("profile", "selected_profiles", DeviceEvent.profile),
        ),
        date_column=DeviceEvent.occurred_at,
        sort_columns=_LOGS_SORT_COLUMNS,
        default_sort=_LOGS_DEFAULT_SORT,
        page_size=_RECENT_EVENTS_LIMIT,
    )


def _admin_actions_listing(session: Session) -> listing.ListingSpec:
    return listing.ListingSpec(
        prefix="a_",
        base_path="/logs",
        tab_suffix="&tab=actions",
        items_key="admin_actions",
        query=session.query(AdminAction),
        search_columns=(
            AdminAction.actor,
            AdminAction.vid_pid,
            AdminAction.serial,
            AdminAction.source,
            AdminAction.target,
        ),
        category_filters=(listing.CategoryFilter("a_action", "a_selected_actions", AdminAction.action_type),),
        date_column=AdminAction.occurred_at,
        sort_columns=_ADMIN_ACTIONS_SORT_COLUMNS,
        default_sort=_ADMIN_ACTIONS_DEFAULT_SORT,
        page_size=_ADMIN_ACTIONS_LIMIT,
    )


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
    context = listing.build_context(
        _events_listing(session), q, {"decision": decision, "profile": profile}, date_from, date_to, sort, dir, page
    )
    admin_actions_context = listing.build_context(
        _admin_actions_listing(session), a_q, {"a_action": a_action}, a_from, a_to, a_sort, a_dir, a_page
    )
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
    tab = tab if tab in _LOGS_TABS else "events"
    if tab == "actions":
        spec = _admin_actions_listing(session)
        context = listing.build_context(spec, a_q, {"a_action": a_action}, a_from, a_to, a_sort, a_dir, a_page)
        template_name = "_admin_actions_table.html"
        push_query_string = listing.filter_query_string(
            spec,
            context["a_q"],
            {"a_action": context["a_selected_actions"]},
            context["a_date_from"],
            context["a_date_to"],
        )
        push_url = (
            f"/logs?{push_query_string}&a_sort={context['a_sort']}&a_dir={context['a_dir']}"
            f"&a_page={context['a_page']}&tab=actions"
        )
    else:
        spec = _events_listing(session)
        context = listing.build_context(
            spec, q, {"decision": decision, "profile": profile}, date_from, date_to, sort, dir, page
        )
        template_name = "_events_table.html"
        push_query_string = listing.filter_query_string(
            spec,
            context["q"],
            {"decision": context["selected_decisions"], "profile": context["selected_profiles"]},
            context["date_from"],
            context["date_to"],
        )
        push_url = (
            f"/logs?{push_query_string}&sort={context['sort']}&dir={context['dir']}&page={context['page']}&tab=events"
        )

    response = render(request, session, template_name, context)
    is_poll = request.headers.get("X-Argus-Poll") == "true"
    if request.headers.get("HX-Request") == "true" and not is_poll:
        response.headers["HX-Push-Url"] = push_url
    return response


# --- Settings ---


def _settings_context(
    admin: str,
    session: Session,
    *,
    review_devices=None,
    password_error: str | None = None,
    password_success: bool = False,
) -> dict:
    return {
        "admin": admin,
        "settings": profiles.get_settings(session),
        "active": "settings",
        "password_error": password_error,
        "password_success": password_success,
        "review_devices": review_devices,
    }


@router.get("/settings")
def settings_page(request: Request, admin: str = Depends(require_admin), session: Session = Depends(get_session)):
    return render(request, session, "settings.html", _settings_context(admin, session))


def _connected_identities() -> set[tuple[str, str, str | None]]:
    try:
        return {(d.vid, d.pid, d.serial) for d in usbguard_cli.list_devices()}
    except usbguard_cli.UsbguardCliError:
        logger.warning("Could not list live USBGuard devices for the enforce-review connected-status check")
        return set()


@router.post("/settings")
def update_settings(
    request: Request,
    profile: str = Form(...),
    language: str = Form(...),
    theme: str = Form(...),
    font_size: str = Form(...),
    log_retention: str = Form(...),
    admin: str = Depends(require_admin),
    session: Session = Depends(get_session),
):
    """Single confirm gate for the whole Settings form — every field commits together, or not at all.
    Switching to Enforce with unreviewed devices in Monitor's history interrupts that gate: nothing in
    this submission is saved yet, and the review modal is shown instead (design.md decision #2)."""
    old_profile = profiles.get_active_profile(session)
    new_profile = Profile(profile)
    if new_profile == Profile.ENFORCE and old_profile != Profile.ENFORCE:
        pending_review = profiles.unreviewed_devices(session)
        if pending_review:
            connected = _connected_identities()
            review_devices = [(d, (d.vid, d.pid, d.serial) in connected) for d in pending_review]
            return render(
                request, session, "settings.html", _settings_context(admin, session, review_devices=review_devices)
            )

    profiles.request_profile(session, new_profile)
    if new_profile != old_profile:
        profiles.record_admin_action(
            session, admin, AdminActionType.PROFILE_SWITCH, new_profile.value, source=old_profile.value
        )
    if language in SUPPORTED_LANGUAGES:
        profiles.set_language(session, language)
    if theme in Theme:
        profiles.set_theme(session, theme)
    if font_size in FontSize:
        profiles.set_font_size(session, font_size)
    if log_retention in LogRetention:
        old_retention = profiles.get_log_retention(session)
        new_retention = LogRetention(log_retention)
        if new_retention != old_retention:
            profiles.set_log_retention(session, new_retention)
            profiles.record_admin_action(
                session, admin, AdminActionType.RETENTION_CHANGE, new_retention.value, source=old_retention.value
            )
    return RedirectResponse(url="/settings", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/settings/enforce-review")
def enforce_review(
    request: Request,
    device_ids: list[int] = Form(default=[]),
    admin: str = Depends(require_admin),
    session: Session = Depends(get_session),
):
    """Resolves the Enforce-transition review modal: authorizes whatever the admin checked (same path
    as /whitelist/authorize), then applies the switch to Enforce. No second confirmation step."""
    old_profile = profiles.get_active_profile(session)
    for device_id in device_ids:
        _authorize_device(session, admin, device_id)
    profiles.request_profile(session, Profile.ENFORCE)
    profiles.record_admin_action(
        session, admin, AdminActionType.PROFILE_SWITCH, Profile.ENFORCE.value, source=old_profile.value
    )
    return RedirectResponse(url="/settings", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/settings/password")
def update_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    admin: str = Depends(require_admin),
    session: Session = Depends(get_session),
):
    password_error = None
    password_success = False
    if not is_password_valid(new_password, confirm_password):
        password_error = "password_error_mismatch" if new_password != confirm_password else "password_error_too_short"
    elif not change_password(session, admin, current_password, new_password):
        password_error = "settings_password_error_current_incorrect"
    else:
        password_success = True

    return render(
        request,
        session,
        "settings.html",
        _settings_context(admin, session, password_error=password_error, password_success=password_success),
    )
