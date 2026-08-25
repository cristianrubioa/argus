import enum
from datetime import datetime
from datetime import timezone

from sqlalchemy import DateTime
from sqlalchemy import Enum
from sqlalchemy import ForeignKey
from sqlalchemy import String
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from argus.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Decision(enum.StrEnum):
    AUTHORIZED = "authorized"
    BLOCKED = "blocked"
    UNRECOGNIZED = "unrecognized"


class Profile(enum.StrEnum):
    MONITOR = "monitor"
    ENFORCE = "enforce"


class UsbguardAction(enum.StrEnum):
    ALLOW = "allow"
    BLOCK = "block"


class AgentStatus(enum.StrEnum):
    LIVE = "live"
    STALE = "stale"
    NEVER = "never"


class AdminActionType(enum.StrEnum):
    WHITELIST_AUTHORIZE = "whitelist_authorize"
    WHITELIST_REVOKE = "whitelist_revoke"
    DEVICE_RENAME = "device_rename"
    PROFILE_SWITCH = "profile_switch"
    RETENTION_CHANGE = "retention_change"


class Theme(enum.StrEnum):
    LIGHT = "light"
    DARK = "dark"


class FontSize(enum.StrEnum):
    MD = "md"
    LG = "lg"


class VersionStatus(enum.StrEnum):
    UNKNOWN = "unknown"
    UPDATE_AVAILABLE = "update_available"
    UP_TO_DATE = "up_to_date"


class LogRetention(enum.StrEnum):
    NINETY_DAYS = "90_days"
    ONE_YEAR = "1_year"
    TWO_YEARS = "2_years"
    FOREVER = "forever"


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(primary_key=True)
    vid: Mapped[str] = mapped_column(String(4))
    pid: Mapped[str] = mapped_column(String(4))
    name: Mapped[str] = mapped_column(String(255))
    serial: Mapped[str | None] = mapped_column(String(255), nullable=True)
    custom_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # USBGuard's own with-connect-type ("hotplug"/"hardwired"/""), captured from an Insert event.
    connect_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    events: Mapped[list["DeviceEvent"]] = relationship(back_populates="device")
    whitelist_entry: Mapped["WhitelistEntry | None"] = relationship(back_populates="device", uselist=False)

    @property
    def vid_pid(self) -> str:
        return f"{self.vid}:{self.pid}"

    @property
    def display_name(self) -> str:
        return self.custom_name or self.name


class DeviceEvent(Base):
    __tablename__ = "device_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"))
    decision: Mapped[Decision] = mapped_column(Enum(Decision))
    profile: Mapped[Profile] = mapped_column(Enum(Profile))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    # USBGuard's own per-connection id — how PolicyApplied finds the row its Insert already created.
    usbguard_connection_id: Mapped[int | None] = mapped_column(nullable=True)
    # Null until the provisional Insert decision is corrected once; after that, never touched again —
    # a later policy change for the same connection creates a new row instead (main.py::_handle_policy_settled).
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    device: Mapped["Device"] = relationship(back_populates="events")


class WhitelistEntry(Base):
    """The whitelist, source of truth for both profiles (design.md decision #6a)."""

    __tablename__ = "whitelist_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), unique=True)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    added_by: Mapped[str] = mapped_column(String(64))

    device: Mapped["Device"] = relationship(back_populates="whitelist_entry")


class PendingUsbguardAction(Base):
    """A whitelist write queued by argus-web for argus-agent to apply (design.md decision #1a)."""

    __tablename__ = "pending_usbguard_actions"

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"))
    action: Mapped[UsbguardAction] = mapped_column(Enum(UsbguardAction))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    device: Mapped["Device"] = relationship()


class AdminAction(Base):
    """Append-only audit trail of security-relevant admin actions. vid_pid/serial/source/target are
    human-readable snapshots, not foreign keys, so a record stays meaningful after the thing it
    describes changes or is deleted. source is the "before" value for a genuine transition
    (rename, profile switch) and null otherwise; target is always populated. vid_pid/serial are
    null for actions not tied to a specific device (profile switches)."""

    __tablename__ = "admin_actions"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor: Mapped[str] = mapped_column(String(64))
    action_type: Mapped[AdminActionType] = mapped_column(Enum(AdminActionType))
    vid_pid: Mapped[str | None] = mapped_column(String(9), nullable=True)
    serial: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    target: Mapped[str] = mapped_column(String(255))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class AdminUser(Base):
    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))


class Settings(Base):
    """Singleton row (id=1). `profile` is desired (argus-web); `applied_profile` is what argus-agent applied."""

    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    profile: Mapped[Profile] = mapped_column(Enum(Profile), default=Profile.MONITOR)
    applied_profile: Mapped[Profile | None] = mapped_column(Enum(Profile), nullable=True)
    enforce_bootstrapped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    language: Mapped[str] = mapped_column(String(2), default="en")
    mqtt_last_publish_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    mqtt_last_publish_ok: Mapped[bool | None] = mapped_column(nullable=True)
    mqtt_last_error: Mapped[str | None] = mapped_column(String(255), nullable=True)
    theme: Mapped[str] = mapped_column(String(5), default="dark")
    font_size: Mapped[str] = mapped_column(String(2), default="md")
    agent_last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_log_prune_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    latest_version_available: Mapped[str | None] = mapped_column(String(32), nullable=True)
    version_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    log_retention: Mapped[LogRetention] = mapped_column(Enum(LogRetention), default=LogRetention.ONE_YEAR)
