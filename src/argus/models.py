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


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(primary_key=True)
    vid: Mapped[str] = mapped_column(String(4))
    pid: Mapped[str] = mapped_column(String(4))
    name: Mapped[str] = mapped_column(String(255))
    serial: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    events: Mapped[list["DeviceEvent"]] = relationship(back_populates="device")
    whitelist_entry: Mapped["WhitelistEntry | None"] = relationship(back_populates="device", uselist=False)

    @property
    def vid_pid(self) -> str:
        return f"{self.vid}:{self.pid}"


class DeviceEvent(Base):
    __tablename__ = "device_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"))
    decision: Mapped[Decision] = mapped_column(Enum(Decision))
    profile: Mapped[Profile] = mapped_column(Enum(Profile))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    device: Mapped["Device"] = relationship(back_populates="events")


class WhitelistEntry(Base):
    """The whitelist. Source of truth for both profiles — see design.md decision on
    whitelist source of truth: Argus owns this table in SQLite; in Enforce profile,
    every mutation here is also pushed to USBGuard via its own IPC commands
    (usbguard_cli.allow_device/block_device), but reads never go back to USBGuard live.
    """

    __tablename__ = "whitelist_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), unique=True)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    added_by: Mapped[str] = mapped_column(String(64))

    device: Mapped["Device"] = relationship(back_populates="whitelist_entry")


class PendingUsbguardAction(Base):
    """A whitelist write queued by argus-web (Docker, no access to USBGuard's host
    IPC socket) for argus-agent (host) to apply. See design.md decision #1a: the
    already-shared SQLite file doubles as the hand-off point, instead of adding a
    new channel across the host/container boundary.
    """

    __tablename__ = "pending_usbguard_actions"

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"))
    action: Mapped[UsbguardAction] = mapped_column(Enum(UsbguardAction))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    device: Mapped["Device"] = relationship()


class AdminUser(Base):
    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))


class Settings(Base):
    """Singleton row (id is always 1) holding the security profile.

    `profile` is the admin's desired profile, writable from argus-web. `applied_profile`
    is what argus-agent has actually pushed to USBGuard via IPC — only argus-agent writes
    it, since only argus-agent can reach USBGuard's host-local socket (design.md decision
    #1a). When the two differ, argus-agent's poller reconciles them.
    """

    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    profile: Mapped[Profile] = mapped_column(Enum(Profile), default=Profile.MONITOR)
    applied_profile: Mapped[Profile | None] = mapped_column(Enum(Profile), nullable=True)
    enforce_bootstrapped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
