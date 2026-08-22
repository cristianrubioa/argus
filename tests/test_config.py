from argus import config


def test_session_secret_generates_and_persists_when_unset(monkeypatch, tmp_path):
    # Setup
    monkeypatch.delenv("ARGUS_SESSION_SECRET", raising=False)
    monkeypatch.setenv("ARGUS_DB_PATH", str(tmp_path / "argus.db"))
    # Action
    first = config.session_secret()
    second = config.session_secret()
    # Expected
    assert first == second
    assert (tmp_path / "session_secret").read_text().strip() == first


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
