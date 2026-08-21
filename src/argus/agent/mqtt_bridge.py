"""Publishes device events to MQTT for external consumers (design.md decision #7) — entirely optional."""

import concurrent.futures
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
    # publish.single() has no timeout parameter — a broker that accepts the TCP connection but never
    # sends CONNACK would otherwise block this call forever. Bound it with a worker thread instead.
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = executor.submit(mqtt_publish.single, topic, payload=payload, hostname=broker["host"], port=broker["port"])
    try:
        future.result(timeout=_PUBLISH_TIMEOUT_SECONDS)
    except concurrent.futures.TimeoutError:
        logger.error(
            "Timed out publishing to MQTT broker %s:%s after %ss", broker["host"], broker["port"], _PUBLISH_TIMEOUT_SECONDS
        )
        _record_attempt(session, ok=False, error=f"Publish timed out after {_PUBLISH_TIMEOUT_SECONDS}s")
    except Exception as exc:
        logger.exception("Failed to publish device event to MQTT broker %s:%s", broker["host"], broker["port"])
        _record_attempt(session, ok=False, error=str(exc)[:_MAX_ERROR_LENGTH])
    else:
        _record_attempt(session, ok=True, error=None)
    finally:
        # ponytail: on a real timeout the worker thread is left running/leaked (paho has no way to cancel
        # an in-flight connect); acceptable for a rare broker-hang edge case. Revisit if this ever recurs.
        executor.shutdown(wait=False)


def _record_attempt(session: Session, ok: bool, error: str | None) -> None:
    settings = profiles.get_settings(session)
    settings.mqtt_last_publish_at = datetime.now(timezone.utc)
    settings.mqtt_last_publish_ok = ok
    settings.mqtt_last_error = error
    session.commit()
