from datetime import datetime
from datetime import timedelta
from datetime import timezone

from argus import config
from argus import profiles
from argus.factories import DeviceEventFactory
from argus.factories import DeviceFactory
from argus.models import DeviceEvent
from argus.models import PendingUsbguardAction
from argus.models import UsbguardAction


def _days_ago(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


def test_log_retention_days_defaults_to_none(monkeypatch):
    # Setup
    monkeypatch.delenv("ARGUS_LOG_RETENTION_DAYS", raising=False)
    # Action & Expected
    assert config.log_retention_days() is None


def test_log_retention_days_returns_configured_value(monkeypatch):
    # Setup
    monkeypatch.setenv("ARGUS_LOG_RETENTION_DAYS", "30")
    # Action & Expected
    assert config.log_retention_days() == 30


def test_prune_does_nothing_when_retention_unset(session, monkeypatch):
    # Setup
    monkeypatch.delenv("ARGUS_LOG_RETENTION_DAYS", raising=False)
    DeviceEventFactory(occurred_at=_days_ago(9999))
    # Action
    profiles.prune_old_events(session)
    # Expected
    assert session.query(DeviceEvent).count() == 1


def test_prune_deletes_events_older_than_retention_and_keeps_recent(session, monkeypatch):
    # Setup
    monkeypatch.setenv("ARGUS_LOG_RETENTION_DAYS", "30")
    DeviceEventFactory(occurred_at=_days_ago(31))
    recent = DeviceEventFactory(occurred_at=_days_ago(1))
    # Action
    profiles.prune_old_events(session)
    # Expected
    remaining = session.query(DeviceEvent).all()
    assert [event.id for event in remaining] == [recent.id]


def test_prune_never_deletes_unapplied_pending_actions(session, monkeypatch):
    # Setup
    monkeypatch.setenv("ARGUS_LOG_RETENTION_DAYS", "30")
    device = DeviceFactory()
    session.add(
        PendingUsbguardAction(device=device, action=UsbguardAction.ALLOW, created_at=_days_ago(9999), applied_at=None)
    )
    session.commit()
    # Action
    profiles.prune_old_events(session)
    # Expected
    assert session.query(PendingUsbguardAction).count() == 1


def test_prune_deletes_applied_pending_actions_older_than_retention(session, monkeypatch):
    # Setup
    monkeypatch.setenv("ARGUS_LOG_RETENTION_DAYS", "30")
    device = DeviceFactory()
    session.add(
        PendingUsbguardAction(
            device=device, action=UsbguardAction.ALLOW, created_at=_days_ago(40), applied_at=_days_ago(31)
        )
    )
    session.commit()
    # Action
    profiles.prune_old_events(session)
    # Expected
    assert session.query(PendingUsbguardAction).count() == 0


def test_second_prune_within_a_day_is_a_no_op(session, monkeypatch):
    # Setup
    monkeypatch.setenv("ARGUS_LOG_RETENTION_DAYS", "30")
    DeviceEventFactory(occurred_at=_days_ago(31))
    # Action
    profiles.prune_old_events(session)
    first_prune_at = profiles.get_settings(session).last_log_prune_at
    DeviceEventFactory(occurred_at=_days_ago(31))
    profiles.prune_old_events(session)
    # Expected
    assert session.query(DeviceEvent).count() == 1
    assert profiles.get_settings(session).last_log_prune_at == first_prune_at
