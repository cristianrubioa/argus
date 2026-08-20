from argus import profiles
from argus import usbguard_cli
from argus.models import Profile


def test_enforce_bootstrap_runs_exactly_once(session, monkeypatch):
    # Setup
    calls = []
    monkeypatch.setattr(usbguard_cli, "generate_policy", lambda: calls.append("generate"))
    monkeypatch.setattr(usbguard_cli, "set_implicit_policy_target", lambda target: calls.append(f"set:{target}"))
    profiles.request_profile(session, Profile.ENFORCE)
    # Action
    profiles.reconcile_profile(session)
    profiles.reconcile_profile(session)
    # Expected
    assert calls == ["generate", "set:block"]
    settings = profiles.get_settings(session)
    assert settings.applied_profile == Profile.ENFORCE
    assert settings.enforce_bootstrapped_at is not None


def test_switching_back_to_monitor_does_not_rebootstrap(session, monkeypatch):
    # Setup
    calls = []
    monkeypatch.setattr(usbguard_cli, "generate_policy", lambda: calls.append("generate"))
    monkeypatch.setattr(usbguard_cli, "set_implicit_policy_target", lambda target: calls.append(f"set:{target}"))
    profiles.request_profile(session, Profile.ENFORCE)
    profiles.reconcile_profile(session)
    # Action
    profiles.request_profile(session, Profile.MONITOR)
    profiles.reconcile_profile(session)
    # Expected
    assert calls == ["generate", "set:block", "set:allow"]
