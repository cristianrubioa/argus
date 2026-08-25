import socket
import time

from fastapi import status

from argus import profiles
from argus.agent import mqtt_bridge
from argus.models import AdminAction
from argus.models import AdminActionType

_BASE_SETTINGS_FORM = {
    "profile": "monitor",
    "language": "en",
    "theme": "dark",
    "font_size": "md",
    "log_retention": "1_year",
    "mqtt_port": "1883",
}


def test_out_of_range_port_is_rejected_and_settings_unchanged(logged_in_client, session):
    # Action
    response = logged_in_client.post("/settings", data={**_BASE_SETTINGS_FORM, "mqtt_port": "70000"})
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert profiles.get_mqtt_settings(session).port == 1883
    assert "Port must be between 1 and 65535" in response.text


def test_non_numeric_port_is_rejected_and_settings_unchanged(logged_in_client, session):
    # Action
    response = logged_in_client.post("/settings", data={**_BASE_SETTINGS_FORM, "mqtt_port": "notanumber"})
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert profiles.get_mqtt_settings(session).port == 1883
    assert "Port must be between 1 and 65535" in response.text


def test_enabling_mqtt_records_one_toggle_action_with_before_and_after(logged_in_client, session):
    # Action
    logged_in_client.post(
        "/settings", data={**_BASE_SETTINGS_FORM, "mqtt_enabled": "on", "mqtt_host": "localhost", "mqtt_port": "1883"}
    )
    # Expected
    action = session.query(AdminAction).filter_by(action_type=AdminActionType.MQTT_TOGGLE).one()
    assert (action.source, action.target) == ("disabled", "enabled")
    assert profiles.get_mqtt_settings(session).enabled is True


def test_saving_without_changing_the_toggle_records_no_action(logged_in_client, session):
    # Setup
    logged_in_client.post(
        "/settings", data={**_BASE_SETTINGS_FORM, "mqtt_enabled": "on", "mqtt_host": "localhost", "mqtt_port": "1883"}
    )
    # Action
    logged_in_client.post(
        "/settings", data={**_BASE_SETTINGS_FORM, "mqtt_enabled": "on", "mqtt_host": "broker.local", "mqtt_port": "8883"}
    )
    # Expected
    assert session.query(AdminAction).filter_by(action_type=AdminActionType.MQTT_TOGGLE).count() == 1
    assert (profiles.get_mqtt_settings(session).host, profiles.get_mqtt_settings(session).port) == ("broker.local", 8883)


def test_connection_test_success_does_not_touch_last_publish_status(logged_in_client, session, monkeypatch):
    # Setup
    monkeypatch.setattr(mqtt_bridge.mqtt_publish, "single", lambda *a, **k: None)
    # Action
    response = logged_in_client.post(
        "/settings/mqtt-test", data={"mqtt_host": "localhost", "mqtt_port": "1883", "mqtt_topic_prefix": "argus"}
    )
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert "Connection successful" in response.text
    settings = profiles.get_settings(session)
    assert (settings.mqtt_last_publish_at, settings.mqtt_last_publish_ok, settings.mqtt_last_error) == (None, None, None)


def test_connection_test_timeout_does_not_touch_last_publish_status(logged_in_client, session, monkeypatch):
    # Setup
    monkeypatch.setattr(mqtt_bridge, "_PUBLISH_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(mqtt_bridge.mqtt_publish, "single", lambda *a, **k: time.sleep(2))
    # Action
    response = logged_in_client.post(
        "/settings/mqtt-test", data={"mqtt_host": "localhost", "mqtt_port": "1883", "mqtt_topic_prefix": "argus"}
    )
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert "Timed out" in response.text
    settings = profiles.get_settings(session)
    assert (settings.mqtt_last_publish_at, settings.mqtt_last_publish_ok, settings.mqtt_last_error) == (None, None, None)


def test_connection_test_error_does_not_touch_last_publish_status(logged_in_client, session, monkeypatch):
    # Setup
    def _boom(*args, **kwargs):
        raise ConnectionError("broker unreachable")

    monkeypatch.setattr(mqtt_bridge.mqtt_publish, "single", _boom)
    # Action
    response = logged_in_client.post(
        "/settings/mqtt-test", data={"mqtt_host": "localhost", "mqtt_port": "1883", "mqtt_topic_prefix": "argus"}
    )
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert "broker unreachable" in response.text
    settings = profiles.get_settings(session)
    assert (settings.mqtt_last_publish_at, settings.mqtt_last_publish_ok, settings.mqtt_last_error) == (None, None, None)


def test_connection_test_with_unresolvable_host_reports_a_friendly_message(logged_in_client, session, monkeypatch):
    # Setup
    def _boom(*args, **kwargs):
        raise socket.gaierror(-2, "Name or service not known")

    monkeypatch.setattr(mqtt_bridge.mqtt_publish, "single", _boom)
    # Action
    response = logged_in_client.post(
        "/settings/mqtt-test", data={"mqtt_host": "not-a-real-host", "mqtt_port": "1883", "mqtt_topic_prefix": "argus"}
    )
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert "Host not found" in response.text
    assert "Errno" not in response.text


def test_connection_test_with_refused_connection_reports_a_friendly_message(logged_in_client, session, monkeypatch):
    # Setup
    def _boom(*args, **kwargs):
        raise ConnectionRefusedError(111, "Connection refused")

    monkeypatch.setattr(mqtt_bridge.mqtt_publish, "single", _boom)
    # Action
    response = logged_in_client.post(
        "/settings/mqtt-test", data={"mqtt_host": "localhost", "mqtt_port": "1883", "mqtt_topic_prefix": "argus"}
    )
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert "Connection refused" in response.text
    assert "Errno" not in response.text


def test_connection_test_with_invalid_port_reports_invalid_port(logged_in_client, session):
    # Action
    response = logged_in_client.post(
        "/settings/mqtt-test", data={"mqtt_host": "localhost", "mqtt_port": "notanumber", "mqtt_topic_prefix": "argus"}
    )
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert "Invalid port" in response.text
