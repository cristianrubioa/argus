from datetime import datetime
from datetime import timedelta
from datetime import timezone

import pytest

from argus import profiles
from argus.agent import usbguard_cli
from argus.models import Profile


def test_agent_status_is_never_when_unset(session):
    # Action & Expected
    assert profiles.agent_status(session) == "never"


def test_agent_status_is_live_just_after_heartbeat(session):
    # Action
    profiles.record_agent_heartbeat(session)
    # Expected
    assert profiles.agent_status(session) == "live"


def test_agent_status_is_stale_after_threshold(session):
    # Setup
    profiles.record_agent_heartbeat(session)
    settings = profiles.get_settings(session)
    # Action — backdate the stored heartbeat past the staleness threshold
    settings.agent_last_heartbeat_at = datetime.now(timezone.utc) - timedelta(seconds=profiles._HEARTBEAT_STALE_SECONDS + 1)
    session.commit()
    # Expected
    assert profiles.agent_status(session) == "stale"


def test_reconcile_failure_does_not_prevent_heartbeat(session, monkeypatch):
    # Setup
    def _fail():
        raise usbguard_cli.UsbguardCliError("denied")

    monkeypatch.setattr(usbguard_cli, "generate_policy", _fail)
    profiles.request_profile(session, Profile.ENFORCE)
    # Action
    profiles.record_agent_heartbeat(session)
    with pytest.raises(usbguard_cli.UsbguardCliError):
        profiles.reconcile_profile(session)
    # Expected
    assert profiles.agent_status(session) == "live"
