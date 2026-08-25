import enum

from fastapi import Request


class ToastKind(enum.StrEnum):
    SUCCESS = "success"
    ERROR = "error"


class ToastMessage(enum.StrEnum):
    SETTINGS_SAVED = "toast_settings_saved"
    MQTT_PORT_INVALID = "mqtt_port_error"
    PASSWORD_CHANGED = "settings_password_changed"
    PASSWORD_CURRENT_INCORRECT = "settings_password_error_current_incorrect"
    PASSWORD_MISMATCH = "password_error_mismatch"
    PASSWORD_TOO_SHORT = "password_error_too_short"
    DEVICE_AUTHORIZED = "toast_device_authorized"
    DEVICE_AUTHORIZE_FAILED = "toast_device_authorize_failed"
    DEVICE_REVOKED = "toast_device_revoked"
    DEVICE_REVOKE_FAILED = "toast_device_revoke_failed"
    DEVICE_RENAMED = "toast_device_renamed"
    DEVICE_RENAME_FAILED = "toast_device_rename_failed"


def flash(request: Request, kind: ToastKind, message: ToastMessage, *, inline: bool = False) -> None:
    """inline routes the message to a spot next to the control that triggered it (currently only the
    Change password button) instead of the shared corner toast — used for the 3 password-change failure
    reasons, where the admin's attention is already on that button."""
    request.session["_toast"] = {"kind": kind.value, "message_key": message.value, "inline": inline}
