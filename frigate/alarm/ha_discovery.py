"""Home Assistant MQTT discovery for the alarm engine.

Publishes retained discovery config payloads to
homeassistant/<component>/<node_id>/<object_id>/config so Home Assistant's
MQTT integration auto-creates entities for the alarm panel and its zones.
This is a stable, well-documented public protocol
(https://www.home-assistant.io/integrations/mqtt/#mqtt-discovery), unlike
SIA DC-09/Contact ID -- there's no "unverified stub" caveat here.

Needs frigate.config, so like factory.py this is glue, not core; the alarm
engine itself still has zero MQTT dependency (see
test_alarm_no_mqtt_dependency.py).

Discovery config topics must be under the literal "homeassistant/" tree
regardless of Frigate's own mqtt.topic_prefix, so this publishes them via
Dispatcher.publish_absolute (bypassing MqttClient's normal prefixing), not
the regular Dispatcher.publish every other alarm topic uses.
"""

import json
from collections.abc import Callable

from frigate.alarm.factory import build_alarm_rules
from frigate.alarm.mqtt_bridge import (
    HA_FAULT_TOPIC,
    HA_REPORTING_TOPIC,
    HA_STATE_TOPIC,
    ha_zone_topic,
)
from frigate.config.config import FrigateConfig
from frigate.version import VERSION

DISCOVERY_PREFIX = "homeassistant"
NODE_ID = "frigate_alarm"

# (topic, payload, retain) -> None, matching Dispatcher.publish_absolute's
# signature.
PublishAbsolute = Callable[[str, str, bool], None]


def _device_info() -> dict:
    # One shared "device" block groups every entity below under a single
    # device in Home Assistant's UI instead of listing them separately.
    return {
        "identifiers": [NODE_ID],
        "name": "Frigate Alarm",
        "manufacturer": "Frigate",
        "model": "Alarm Engine",
        "sw_version": VERSION,
    }


def _availability(topic_prefix: str) -> list[dict]:
    # Frigate's MqttClient already publishes this exact topic (LWT +
    # on-connect), so this reuses it rather than inventing a new one.
    return [
        {
            "topic": f"{topic_prefix}/available",
            "payload_available": "online",
            "payload_not_available": "offline",
        }
    ]


def _config_topic(component: str, object_id: str) -> str:
    return f"{DISCOVERY_PREFIX}/{component}/{NODE_ID}/{object_id}/config"


def _panel_config(topic_prefix: str) -> dict:
    return {
        "name": "Frigate Alarm",
        "unique_id": f"{NODE_ID}_panel",
        "state_topic": f"{topic_prefix}/{HA_STATE_TOPIC}",
        "command_topic": f"{topic_prefix}/alarm/set",
        "payload_arm_away": "ARM_AWAY",
        "payload_arm_home": "ARM_HOME",
        "payload_arm_night": "ARM_NIGHT",
        "payload_disarm": "DISARM",
        # No PIN concept here -- access control is Frigate's own auth, not
        # a code the panel entity itself would prompt for.
        "code_arm_required": False,
        "code_disarm_required": False,
        "availability": _availability(topic_prefix),
        "device": _device_info(),
    }


def _binary_sensor_config(
    topic_prefix: str,
    *,
    object_id: str,
    name: str,
    state_topic: str,
    device_class: str,
) -> dict:
    return {
        "name": name,
        "unique_id": f"{NODE_ID}_{object_id}",
        "state_topic": f"{topic_prefix}/{state_topic}",
        "payload_on": "ON",
        "payload_off": "OFF",
        "device_class": device_class,
        "availability": _availability(topic_prefix),
        "device": _device_info(),
    }


def publish_ha_discovery(
    config: FrigateConfig, publish_absolute: PublishAbsolute
) -> None:
    """Publish retained Home Assistant MQTT discovery configs for the alarm
    panel and its zones. Safe to call even if MQTT is disabled --
    Dispatcher.publish_absolute already no-ops in that case.
    """
    topic_prefix = config.mqtt.topic_prefix

    publish_absolute(
        _config_topic("alarm_control_panel", "panel"),
        json.dumps(_panel_config(topic_prefix)),
        True,
    )
    publish_absolute(
        _config_topic("binary_sensor", "fault"),
        json.dumps(
            _binary_sensor_config(
                topic_prefix,
                object_id="fault",
                name="Frigate Alarm Fault",
                state_topic=HA_FAULT_TOPIC,
                device_class="problem",
            )
        ),
        True,
    )
    publish_absolute(
        _config_topic("binary_sensor", "reporting"),
        json.dumps(
            _binary_sensor_config(
                topic_prefix,
                object_id="reporting",
                name="Frigate Alarm Reporting",
                state_topic=HA_REPORTING_TOPIC,
                device_class="connectivity",
            )
        ),
        True,
    )

    for camera, zone in build_alarm_rules(config):
        publish_absolute(
            _config_topic("binary_sensor", f"zone_{camera}_{zone}"),
            json.dumps(
                _binary_sensor_config(
                    topic_prefix,
                    object_id=f"zone_{camera}_{zone}",
                    name=f"Frigate Alarm {camera} {zone}",
                    state_topic=ha_zone_topic(camera, zone),
                    device_class="safety",
                )
            ),
            True,
        )
