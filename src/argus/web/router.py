from pathlib import Path

from fastapi import APIRouter
from fastapi import Depends
from fastapi import Form
from fastapi import Request
from fastapi import status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
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

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

_RECENT_EVENTS_LIMIT = 20


# --- Auth ---


@router.get("/login")
def login_form(request: Request):
    return templates.TemplateResponse(request, "login.html", {"error": None})


@router.post("/login")
def login_submit(
    request: Request, username: str = Form(...), password: str = Form(...), session: Session = Depends(get_session)
):
    if not authenticate(session, username, password):
        return templates.TemplateResponse(request, "login.html", {"error": "Invalid username or password"})
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
    return templates.TemplateResponse(request, "dashboard.html", {"admin": admin, "events": events, "active": "dashboard"})


@router.get("/dashboard/partial")
def dashboard_partial(request: Request, admin: str = Depends(require_admin), session: Session = Depends(get_session)):
    events = _recent_events(session)
    return templates.TemplateResponse(request, "_events_table.html", {"events": events})


def _recent_events(session: Session) -> list[DeviceEvent]:
    return session.query(DeviceEvent).order_by(DeviceEvent.occurred_at.desc()).limit(_RECENT_EVENTS_LIMIT).all()


# --- Dispositivos ---


@router.get("/dispositivos")
def devices(request: Request, admin: str = Depends(require_admin), session: Session = Depends(get_session)):
    all_devices = session.query(Device).order_by(Device.last_seen_at.desc()).all()
    whitelisted_ids = {w.device_id for w in session.query(WhitelistEntry).all()}
    return templates.TemplateResponse(
        request,
        "devices.html",
        {"admin": admin, "devices": all_devices, "whitelisted_ids": whitelisted_ids, "active": "dispositivos"},
    )


# --- Whitelist ---


@router.get("/whitelist")
def whitelist(request: Request, admin: str = Depends(require_admin), session: Session = Depends(get_session)):
    entries = session.query(WhitelistEntry).order_by(WhitelistEntry.added_at.desc()).all()
    return templates.TemplateResponse(
        request, "whitelist.html", {"admin": admin, "entries": entries, "active": "whitelist"}
    )


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


@router.get("/logs")
def logs(request: Request, admin: str = Depends(require_admin), session: Session = Depends(get_session)):
    events = session.query(DeviceEvent).order_by(DeviceEvent.occurred_at.desc()).all()
    return templates.TemplateResponse(request, "logs.html", {"admin": admin, "events": events, "active": "logs"})


@router.get("/logs/partial")
def logs_partial(request: Request, admin: str = Depends(require_admin), session: Session = Depends(get_session)):
    events = session.query(DeviceEvent).order_by(DeviceEvent.occurred_at.desc()).all()
    return templates.TemplateResponse(request, "_events_table.html", {"events": events})


# --- Ajustes ---


@router.get("/ajustes")
def settings_page(request: Request, admin: str = Depends(require_admin), session: Session = Depends(get_session)):
    current = profiles.get_settings(session)
    return templates.TemplateResponse(request, "settings.html", {"admin": admin, "settings": current, "active": "ajustes"})


@router.post("/ajustes/profile")
def update_profile(
    request: Request,
    profile: str = Form(...),
    admin: str = Depends(require_admin),
    session: Session = Depends(get_session),
):
    profiles.request_profile(session, Profile(profile))
    return RedirectResponse(url="/ajustes", status_code=status.HTTP_303_SEE_OTHER)
