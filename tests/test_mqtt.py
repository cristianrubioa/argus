import json
import socket
import time

from argus import profiles
from argus.agent import mqtt_bridge
from argus.factories import DeviceEventFactory
from argus.models import Decision
from argus.models import Profile


def test_publish_skipped_when_mqtt_disabled(session, monkeypatch):
    # Setup
    event = DeviceEventFactory()
    profiles.set_mqtt_settings(session, enabled=False, host="localhost", port=1883, topic_prefix="argus")
    calls = []
    monkeypatch.setattr(mqtt_bridge.mqtt_publish, "single", lambda *a, **k: calls.append((a, k)))
    # Action
    mqtt_bridge.publish_event(event, session)
    # Expected
    assert calls == []


def test_publish_skipped_when_no_host_configured(session, monkeypatch):
    # Setup
    event = DeviceEventFactory()
    profiles.set_mqtt_settings(session, enabled=True, host=None, port=1883, topic_prefix="argus")
    calls = []
    monkeypatch.setattr(mqtt_bridge.mqtt_publish, "single", lambda *a, **k: calls.append((a, k)))
    # Action
    mqtt_bridge.publish_event(event, session)
    # Expected
    assert calls == []


def test_publish_failure_does_not_raise(session, monkeypatch):
    # Setup
    event = DeviceEventFactory()
    profiles.set_mqtt_settings(session, enabled=True, host="localhost", port=1883, topic_prefix="argus")

    def _boom(*args, **kwargs):
        raise ConnectionError("broker unreachable")

    monkeypatch.setattr(mqtt_bridge.mqtt_publish, "single", _boom)
    # Action & Expected
    mqtt_bridge.publish_event(event, session)


def test_topic_includes_hostname(session, monkeypatch):
    # Setup
    event = DeviceEventFactory(decision=Decision.BLOCKED)
    profiles.set_mqtt_settings(session, enabled=True, host="localhost", port=1883, topic_prefix="argus")
    calls = []
    monkeypatch.setattr(mqtt_bridge.mqtt_publish, "single", lambda topic, **k: calls.append(topic))
    # Action
    mqtt_bridge.publish_event(event, session)
    # Expected
    assert calls == [f"argus/{socket.gethostname()}/device/blocked"]


def test_publish_reads_host_port_and_topic_prefix_from_settings(session, monkeypatch):
    # Setup
    event = DeviceEventFactory(decision=Decision.AUTHORIZED)
    profiles.set_mqtt_settings(session, enabled=True, host="broker.local", port=8883, topic_prefix="custom")
    calls = []
    monkeypatch.setattr(
        mqtt_bridge.mqtt_publish, "single", lambda topic, payload, hostname, port: calls.append((topic, hostname, port))
    )
    # Action
    mqtt_bridge.publish_event(event, session)
    # Expected
    assert calls == [(f"custom/{socket.gethostname()}/device/authorized", "broker.local", 8883)]


def test_payload_includes_timestamp_and_profile(session, monkeypatch):
    # Setup
    event = DeviceEventFactory(decision=Decision.AUTHORIZED, profile=Profile.ENFORCE)
    profiles.set_mqtt_settings(session, enabled=True, host="localhost", port=1883, topic_prefix="argus")
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
    profiles.set_mqtt_settings(session, enabled=True, host="localhost", port=1883, topic_prefix="argus")
    monkeypatch.setattr(mqtt_bridge.mqtt_publish, "single", lambda *a, **k: None)
    # Action
    mqtt_bridge.publish_event(event, session)
    # Expected
    settings = profiles.get_settings(session)
    assert (settings.mqtt_last_publish_ok, settings.mqtt_last_error) == (True, None)
    assert settings.mqtt_last_publish_at is not None


def test_failed_publish_records_error(session, monkeypatch):
    # Setup
    event = DeviceEventFactory()
    profiles.set_mqtt_settings(session, enabled=True, host="localhost", port=1883, topic_prefix="argus")

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
    profiles.set_mqtt_settings(session, enabled=True, host="localhost", port=1883, topic_prefix="argus")
    monkeypatch.setattr(mqtt_bridge, "_PUBLISH_TIMEOUT_SECONDS", 0.05)

    def _hang(*args, **kwargs):
        time.sleep(2)

    monkeypatch.setattr(mqtt_bridge.mqtt_publish, "single", _hang)
    # Action
    started_at = time.monotonic()
    mqtt_bridge.publish_event(event, session)
    elapsed = time.monotonic() - started_at
    # Expected
    assert elapsed < 1
    settings = profiles.get_settings(session)
    assert settings.mqtt_last_publish_ok is False
    assert "timed out" in settings.mqtt_last_error.lower()


def test_settings_shows_never_attempted_when_enabled_with_no_publish_yet(logged_in_client, session):
    # Setup
    profiles.set_mqtt_settings(session, enabled=True, host="localhost", port=1883, topic_prefix="argus")
    # Action
    response = logged_in_client.get("/settings")
    # Expected
    assert "No publish attempted yet" in response.text


def test_settings_hides_publish_status_when_mqtt_disabled(logged_in_client):
    # Action
    response = logged_in_client.get("/settings")
    # Expected
    assert "No publish attempted yet" not in response.text


def test_settings_shows_success_status(logged_in_client, session, monkeypatch):
    # Setup
    event = DeviceEventFactory()
    profiles.set_mqtt_settings(session, enabled=True, host="localhost", port=1883, topic_prefix="argus")
    monkeypatch.setattr(mqtt_bridge.mqtt_publish, "single", lambda *a, **k: None)
    mqtt_bridge.publish_event(event, session)
    # Action
    response = logged_in_client.get("/settings")
    # Expected
    assert "Last publish (OK):" in response.text


def test_settings_shows_failure_status(logged_in_client, session, monkeypatch):
    # Setup
    event = DeviceEventFactory()
    profiles.set_mqtt_settings(session, enabled=True, host="localhost", port=1883, topic_prefix="argus")

    def _boom(*args, **kwargs):
        raise ConnectionError("broker unreachable")

    monkeypatch.setattr(mqtt_bridge.mqtt_publish, "single", _boom)
    mqtt_bridge.publish_event(event, session)
    # Action
    response = logged_in_client.get("/settings")
    # Expected
    assert "Last publish (failed):" in response.text
    assert "broker unreachable" in response.text
