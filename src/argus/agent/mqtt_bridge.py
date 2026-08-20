"""Publishes device events to MQTT for external consumers (design.md decision #7) — entirely optional."""

import json
import logging
import socket
from datetime import datetime
from datetime import timezone

import paho.mqtt.publish as mqtt_publish
from sqlalchemy.orm import Session

from argus import config
from argus import profiles
from argus.models import DeviceEvent

logger = logging.getLogger(__name__)

_PUBLISH_TIMEOUT_SECONDS = 3
_MAX_ERROR_LENGTH = 255


def publish_event(event: DeviceEvent, session: Session) -> None:
    broker = config.mqtt_config()
    if broker is None:
        return

    device = event.device
    topic = f"{broker['topic_prefix']}/{socket.gethostname()}/device/{event.decision.value}"
    payload = json.dumps(
        {
            "vid": device.vid,
            "pid": device.pid,
            "name": device.name,
            "serial": device.serial,
            "decision": event.decision.value,
            "profile": event.profile.value,
            "occurred_at": event.occurred_at.isoformat(),
        }
    )
    try:
        mqtt_publish.single(topic, payload=payload, hostname=broker["host"], port=broker["port"])
    except Exception as exc:
        logger.exception("Failed to publish device event to MQTT broker %s:%s", broker["host"], broker["port"])
        _record_attempt(session, ok=False, error=str(exc)[:_MAX_ERROR_LENGTH])
    else:
        _record_attempt(session, ok=True, error=None)


def _record_attempt(session: Session, ok: bool, error: str | None) -> None:
    settings = profiles.get_settings(session)
    settings.mqtt_last_publish_at = datetime.now(timezone.utc)
    settings.mqtt_last_publish_ok = ok
    settings.mqtt_last_error = error
    session.commit()
