import pytest

from argus import config


def test_session_secret_raises_when_unset(monkeypatch):
    # Setup
    monkeypatch.delenv("ARGUS_SESSION_SECRET", raising=False)
    # Action & Expected
    with pytest.raises(RuntimeError):
        config.session_secret()


def test_session_secret_returns_configured_value(monkeypatch):
    # Setup
    monkeypatch.setenv("ARGUS_SESSION_SECRET", "a-real-secret")
    # Action & Expected
    assert config.session_secret() == "a-real-secret"


def test_session_https_only_defaults_to_false(monkeypatch):
    # Setup
    monkeypatch.delenv("ARGUS_SESSION_HTTPS_ONLY", raising=False)
    # Action & Expected
    assert config.session_https_only() is False


def test_session_https_only_true_when_set(monkeypatch):
    # Setup
    monkeypatch.setenv("ARGUS_SESSION_HTTPS_ONLY", "true")
    # Action & Expected
    assert config.session_https_only() is True
