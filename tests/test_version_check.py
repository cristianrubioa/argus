from datetime import datetime
from datetime import timedelta
from datetime import timezone

from argus import profiles
from argus import version_check


def test_is_newer_when_latest_is_greater():
    assert version_check.is_newer("0.2.0", "0.1.1") is True


def test_is_newer_when_latest_is_older():
    assert version_check.is_newer("0.1.0", "0.1.1") is False


def test_is_newer_when_versions_are_equal():
    assert version_check.is_newer("0.1.1", "0.1.1") is False


def test_is_newer_returns_false_for_malformed_input():
    assert version_check.is_newer("not-a-version", "0.1.1") is False


def test_refresh_skips_when_cache_is_fresh(session, monkeypatch):
    # Setup
    settings = profiles.get_settings(session)
    settings.latest_version_available = "0.1.1"
    settings.version_checked_at = datetime.now(timezone.utc)
    session.commit()
    fetch_called = []
    monkeypatch.setattr(version_check, "fetch_latest_version", lambda: fetch_called.append(1) or "0.9.9")
    # Action
    profiles.refresh_version_check(session)
    # Expected
    assert fetch_called == []
    assert profiles.get_settings(session).latest_version_available == "0.1.1"


def test_refresh_runs_when_cache_is_stale(session, monkeypatch):
    # Setup
    settings = profiles.get_settings(session)
    settings.version_checked_at = datetime.now(timezone.utc) - timedelta(hours=25)
    session.commit()
    monkeypatch.setattr(version_check, "fetch_latest_version", lambda: "0.5.0")
    # Action
    profiles.refresh_version_check(session)
    # Expected
    assert profiles.get_settings(session).latest_version_available == "0.5.0"


def test_refresh_runs_when_never_checked(session, monkeypatch):
    # Setup
    monkeypatch.setattr(version_check, "fetch_latest_version", lambda: "0.3.0")
    # Action
    profiles.refresh_version_check(session)
    # Expected
    settings = profiles.get_settings(session)
    assert settings.latest_version_available == "0.3.0"
    assert settings.version_checked_at is not None


def test_refresh_failure_preserves_previous_value(session, monkeypatch):
    # Setup
    settings = profiles.get_settings(session)
    settings.latest_version_available = "0.4.0"
    settings.version_checked_at = datetime.now(timezone.utc) - timedelta(hours=25)
    session.commit()
    monkeypatch.setattr(version_check, "fetch_latest_version", lambda: None)
    # Action
    profiles.refresh_version_check(session)
    # Expected — the failed attempt didn't clear the last known good value, but did record the attempt
    settings = profiles.get_settings(session)
    assert settings.latest_version_available == "0.4.0"
    assert profiles._as_aware(settings.version_checked_at) > datetime.now(timezone.utc) - timedelta(seconds=5)
