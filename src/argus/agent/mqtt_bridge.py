"""Publishes device events to MQTT for external consumers (design.md decision #7) — entirely optional."""

import json
import logging

import paho.mqtt.publish as mqtt_publish

from argus import config
from argus.models import Decision
from argus.models import Device

logger = logging.getLogger(__name__)

_PUBLISH_TIMEOUT_SECONDS = 3


def publish_event(device: Device, decision: Decision) -> None:
    settings = config.mqtt_config()
    if settings is None:
        return

    topic = f"{settings['topic_prefix']}/device/{decision.value}"
    payload = json.dumps(
        {
            "vid": device.vid,
            "pid": device.pid,
            "name": device.name,
            "serial": device.serial,
            "decision": decision.value,
        }
    )
    try:
        mqtt_publish.single(
            topic,
            payload=payload,
            hostname=settings["host"],
            port=settings["port"],
        )
    except Exception:
        logger.exception("Failed to publish device event to MQTT broker %s:%s", settings["host"], settings["port"])
