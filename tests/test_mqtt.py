from argus import config
from argus.agent import mqtt_bridge
from argus.factories import DeviceFactory
from argus.models import Decision


def test_publish_skipped_when_no_broker_configured(session, monkeypatch):
    # Setup
    device = DeviceFactory()
    monkeypatch.setattr(config, "mqtt_config", lambda: None)
    calls = []
    monkeypatch.setattr(mqtt_bridge.mqtt_publish, "single", lambda *a, **k: calls.append((a, k)))
    # Action
    mqtt_bridge.publish_event(device, Decision.UNRECOGNIZED)
    # Expected
    assert calls == []


def test_publish_failure_does_not_raise(session, monkeypatch):
    # Setup
    device = DeviceFactory()
    monkeypatch.setattr(config, "mqtt_config", lambda: {"host": "localhost", "port": 1883, "topic_prefix": "argus"})

    def _boom(*args, **kwargs):
        raise ConnectionError("broker unreachable")

    monkeypatch.setattr(mqtt_bridge.mqtt_publish, "single", _boom)
    # Action & Expected: must not raise
    mqtt_bridge.publish_event(device, Decision.BLOCKED)
