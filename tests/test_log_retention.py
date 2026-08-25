from datetime import datetime
from datetime import timedelta
from datetime import timezone

from argus import profiles
from argus.factories import DeviceEventFactory
from argus.factories import DeviceFactory
from argus.models import DeviceEvent
from argus.models import LogRetention
from argus.models import PendingUsbguardAction
from argus.models import UsbguardAction


def _days_ago(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


def test_default_retention_is_one_year(session):
    # Setup & Action
    settings = profiles.get_settings(session)
    # Expected
    assert settings.log_retention == LogRetention.ONE_YEAR


def test_prune_does_nothing_when_retention_is_forever(session):
    # Setup
    profiles.set_log_retention(session, LogRetention.FOREVER)
    DeviceEventFactory(occurred_at=_days_ago(9999))
    # Action
    profiles.prune_old_events(session)
    # Expected
    assert session.query(DeviceEvent).count() == 1


def test_prune_deletes_events_older_than_retention_and_keeps_recent(session):
    # Setup
    profiles.set_log_retention(session, LogRetention.NINETY_DAYS)
    DeviceEventFactory(occurred_at=_days_ago(91))
    recent = DeviceEventFactory(occurred_at=_days_ago(1))
    # Action
    profiles.prune_old_events(session)
    # Expected
    remaining = session.query(DeviceEvent).all()
    assert [event.id for event in remaining] == [recent.id]


def test_prune_respects_one_year_retention(session):
    # Setup
    profiles.set_log_retention(session, LogRetention.ONE_YEAR)
    DeviceEventFactory(occurred_at=_days_ago(366))
    recent = DeviceEventFactory(occurred_at=_days_ago(1))
    # Action
    profiles.prune_old_events(session)
    # Expected
    remaining = session.query(DeviceEvent).all()
    assert [event.id for event in remaining] == [recent.id]


def test_prune_respects_two_year_retention(session):
    # Setup
    profiles.set_log_retention(session, LogRetention.TWO_YEARS)
    DeviceEventFactory(occurred_at=_days_ago(731))
    recent = DeviceEventFactory(occurred_at=_days_ago(1))
    # Action
    profiles.prune_old_events(session)
    # Expected
    remaining = session.query(DeviceEvent).all()
    assert [event.id for event in remaining] == [recent.id]


def test_prune_never_deletes_unapplied_pending_actions(session):
    # Setup
    profiles.set_log_retention(session, LogRetention.NINETY_DAYS)
    device = DeviceFactory()
    session.add(
        PendingUsbguardAction(device=device, action=UsbguardAction.ALLOW, created_at=_days_ago(9999), applied_at=None)
    )
    session.commit()
    # Action
    profiles.prune_old_events(session)
    # Expected
    assert session.query(PendingUsbguardAction).count() == 1


def test_prune_deletes_applied_pending_actions_older_than_retention(session):
    # Setup
    profiles.set_log_retention(session, LogRetention.NINETY_DAYS)
    device = DeviceFactory()
    session.add(
        PendingUsbguardAction(
            device=device, action=UsbguardAction.ALLOW, created_at=_days_ago(100), applied_at=_days_ago(91)
        )
    )
    session.commit()
    # Action
    profiles.prune_old_events(session)
    # Expected
    assert session.query(PendingUsbguardAction).count() == 0


def test_second_prune_within_a_day_is_a_no_op(session):
    # Setup
    profiles.set_log_retention(session, LogRetention.NINETY_DAYS)
    DeviceEventFactory(occurred_at=_days_ago(91))
    # Action
    profiles.prune_old_events(session)
    first_prune_at = profiles.get_settings(session).last_log_prune_at
    DeviceEventFactory(occurred_at=_days_ago(91))
    profiles.prune_old_events(session)
    # Expected
    assert session.query(DeviceEvent).count() == 1
    assert profiles.get_settings(session).last_log_prune_at == first_prune_at


def test_changing_retention_between_runs_uses_only_the_current_value(session):
    # Setup
    profiles.set_log_retention(session, LogRetention.ONE_YEAR)
    old_enough_for_narrower_window_only_id = DeviceEventFactory(occurred_at=_days_ago(100)).id
    profiles.prune_old_events(session)
    # Action
    profiles.get_settings(session).last_log_prune_at = None
    profiles.set_log_retention(session, LogRetention.NINETY_DAYS)
    profiles.prune_old_events(session)
    # Expected
    assert session.query(DeviceEvent).filter_by(id=old_enough_for_narrower_window_only_id).count() == 0
