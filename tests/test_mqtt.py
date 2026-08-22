import json
import socket
import time

from argus import config
from argus import profiles
from argus.agent import mqtt_bridge
from argus.factories import DeviceEventFactory
from argus.models import Decision
from argus.models import Profile


def test_publish_skipped_when_no_broker_configured(session, monkeypatch):
    # Setup
    event = DeviceEventFactory()
    monkeypatch.setattr(config, "mqtt_config", lambda: None)
    calls = []
    monkeypatch.setattr(mqtt_bridge.mqtt_publish, "single", lambda *a, **k: calls.append((a, k)))
    # Action
    mqtt_bridge.publish_event(event, session)
    # Expected
    assert calls == []


def test_publish_failure_does_not_raise(session, monkeypatch):
    # Setup
    event = DeviceEventFactory()
    monkeypatch.setattr(config, "mqtt_config", lambda: {"host": "localhost", "port": 1883, "topic_prefix": "argus"})

    def _boom(*args, **kwargs):
        raise ConnectionError("broker unreachable")

    monkeypatch.setattr(mqtt_bridge.mqtt_publish, "single", _boom)
    # Action & Expected: must not raise
    mqtt_bridge.publish_event(event, session)


def test_topic_includes_hostname(session, monkeypatch):
    # Setup
    event = DeviceEventFactory(decision=Decision.BLOCKED)
    monkeypatch.setattr(config, "mqtt_config", lambda: {"host": "localhost", "port": 1883, "topic_prefix": "argus"})
    calls = []
    monkeypatch.setattr(mqtt_bridge.mqtt_publish, "single", lambda topic, **k: calls.append(topic))
    # Action
    mqtt_bridge.publish_event(event, session)
    # Expected
    assert calls == [f"argus/{socket.gethostname()}/device/blocked"]


def test_payload_includes_timestamp_and_profile(session, monkeypatch):
    # Setup
    event = DeviceEventFactory(decision=Decision.AUTHORIZED, profile=Profile.ENFORCE)
    monkeypatch.setattr(config, "mqtt_config", lambda: {"host": "localhost", "port": 1883, "topic_prefix": "argus"})
    calls = []
    monkeypatch.setattr(mqtt_bridge.mqtt_publish, "single", lambda topic, payload, **k: calls.append(payload))
    # Action
    mqtt_bridge.publish_event(event, session)
    # Expected
    body = json.loads(calls[0])
    assert body["profile"] == "enforce"
    assert body["occurred_at"] == event.occurred_at.isoformat()
    assert body["vid"] == event.device.vid


def test_successful_publish_records_ok_status(session, monkeypatch):
    # Setup
    event = DeviceEventFactory()
    monkeypatch.setattr(config, "mqtt_config", lambda: {"host": "localhost", "port": 1883, "topic_prefix": "argus"})
    monkeypatch.setattr(mqtt_bridge.mqtt_publish, "single", lambda *a, **k: None)
    # Action
    mqtt_bridge.publish_event(event, session)
    # Expected
    settings = profiles.get_settings(session)
    assert settings.mqtt_last_publish_ok is True
    assert settings.mqtt_last_error is None
    assert settings.mqtt_last_publish_at is not None


def test_failed_publish_records_error(session, monkeypatch):
    # Setup
    event = DeviceEventFactory()
    monkeypatch.setattr(config, "mqtt_config", lambda: {"host": "localhost", "port": 1883, "topic_prefix": "argus"})

    def _boom(*args, **kwargs):
        raise ConnectionError("broker unreachable")

    monkeypatch.setattr(mqtt_bridge.mqtt_publish, "single", _boom)
    # Action
    mqtt_bridge.publish_event(event, session)
    # Expected
    settings = profiles.get_settings(session)
    assert settings.mqtt_last_publish_ok is False
    assert "broker unreachable" in settings.mqtt_last_error


def test_publish_timeout_does_not_block_and_records_failure(session, monkeypatch):
    # Setup
    event = DeviceEventFactory()
    monkeypatch.setattr(config, "mqtt_config", lambda: {"host": "localhost", "port": 1883, "topic_prefix": "argus"})
    monkeypatch.setattr(mqtt_bridge, "_PUBLISH_TIMEOUT_SECONDS", 0.05)

    def _hang(*args, **kwargs):
        time.sleep(2)

    monkeypatch.setattr(mqtt_bridge.mqtt_publish, "single", _hang)
    # Action
    started_at = time.monotonic()
    mqtt_bridge.publish_event(event, session)
    elapsed = time.monotonic() - started_at
    # Expected — returns promptly instead of blocking for the full hang duration
    assert elapsed < 1
    settings = profiles.get_settings(session)
    assert settings.mqtt_last_publish_ok is False
    assert "timed out" in settings.mqtt_last_error.lower()


def test_settings_shows_never_attempted_by_default(logged_in_client):
    # Action
    response = logged_in_client.get("/settings")
    # Expected
    assert "No publish attempted yet" in response.text


def test_settings_shows_success_status(logged_in_client, session, monkeypatch):
    # Setup
    event = DeviceEventFactory()
    monkeypatch.setattr(config, "mqtt_config", lambda: {"host": "localhost", "port": 1883, "topic_prefix": "argus"})
    monkeypatch.setattr(mqtt_bridge.mqtt_publish, "single", lambda *a, **k: None)
    mqtt_bridge.publish_event(event, session)
    # Action
    response = logged_in_client.get("/settings")
    # Expected
    assert "Last publish (OK):" in response.text


def test_settings_shows_failure_status(logged_in_client, session, monkeypatch):
    # Setup
    event = DeviceEventFactory()
    monkeypatch.setattr(config, "mqtt_config", lambda: {"host": "localhost", "port": 1883, "topic_prefix": "argus"})

    def _boom(*args, **kwargs):
        raise ConnectionError("broker unreachable")

    monkeypatch.setattr(mqtt_bridge.mqtt_publish, "single", _boom)
    mqtt_bridge.publish_event(event, session)
    # Action
    response = logged_in_client.get("/settings")
    # Expected
    assert "Last publish (failed):" in response.text
    assert "broker unreachable" in response.text
