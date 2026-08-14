"""Publishes AlarmSystem state changes to MQTT + WebSocket via the Dispatcher.

Optional glue: only constructed by the wiring layer when there's a
Dispatcher to publish through. Takes a plain publish callable rather than
importing frigate.comms.dispatcher.Dispatcher, so this stays testable
without constructing a real Dispatcher and without adding frigate.comms to
this module's own import graph -- Dispatcher.publish's signature
(topic, payload, retain) is all this needs to know about it.

Topics (see AGENTS.md phase 1 architecture note for the reasoning):
- "alarm/state": global, retained. Rich JSON status, for Frigate's own
  frontend/API. Published on every state change.
- "alarm/fault": global, retained. Published alongside alarm/state.
- "alarm/event": published per qualifying detection event, not retained.
- "<camera>/alarm_zone/<zone>/state": per zone, so it piggybacks on the
  existing camera-prefix auto-scoping in frigate/comms/ws.py instead of
  needing a new classifier entry there (the original spec's bare
  "alarm/zone/<zone>/state" doesn't start with a camera name, so it would
  be silently dropped by ws.py's fail-closed classifier without one).

A second set of topics under "alarm/ha/" are dedicated bare-value topics
(plain strings, not JSON) for Home Assistant's MQTT discovery
(frigate/alarm/ha_discovery.py) to point at directly -- deliberately
separate from the JSON topics above rather than reusing them with a Jinja2
value_template, since that can't be verified against a real HA instance
from here and a plain string topic can be unit tested exactly.
"""

import json
import logging
from collections.abc import Callable

from frigate.alarm.event import AlarmEvent
from frigate.alarm.state import AlarmState
from frigate.alarm.system import AlarmSystem

logger = logging.getLogger(__name__)

# (topic, payload, retain) -> None, matching Dispatcher.publish's signature.
Publish = Callable[[str, str, bool], None]

HA_STATE_TOPIC = "alarm/ha/state"
HA_FAULT_TOPIC = "alarm/ha/fault"
HA_REPORTING_TOPIC = "alarm/ha/reporting"

# Home Assistant's alarm_control_panel state vocabulary. Frigate's own
# AlarmState is richer (needed for the state machine itself); this is the
# one place that translates down to what HA actually recognizes.
# alarm_memory has no HA equivalent (HA doesn't model "disarmed but
# remembers the last alarm"), so it maps to disarmed -- that detail is
# still available through the API/frontend, just not the HA panel entity.
_HA_STATE_MAP: dict[AlarmState, str] = {
    AlarmState.disarmed: "disarmed",
    AlarmState.arming: "arming",
    AlarmState.exit_delay: "arming",
    AlarmState.armed_away: "armed_away",
    AlarmState.armed_home: "armed_home",
    AlarmState.armed_night: "armed_night",
    AlarmState.entry_delay: "pending",
    AlarmState.alarm: "triggered",
    AlarmState.alarm_memory: "disarmed",
    AlarmState.fault: "disarmed",
}


def translate_state_for_ha(state: AlarmState) -> str:
    """Map Frigate's internal AlarmState to Home Assistant's
    alarm_control_panel state vocabulary."""
    return _HA_STATE_MAP[state]


def ha_zone_topic(camera: str, zone: str) -> str:
    return f"alarm/ha/zone/{camera}_{zone}"


class AlarmMqttBridge:
    def __init__(self, alarm_system: AlarmSystem, publish: Publish) -> None:
        self._alarm_system = alarm_system
        self._publish = publish

    def publish_status(self) -> None:
        status = self._alarm_system.status()
        self._publish("alarm/state", json.dumps(status), True)
        self._publish(
            "alarm/fault",
            json.dumps({"fault_reason": status["fault_reason"]}),
            True,
        )
        for zone in status["zones"]:
            self._publish(
                f"{zone['camera']}/alarm_zone/{zone['zone']}/state",
                json.dumps(zone),
                True,
            )

        self._publish(
            HA_STATE_TOPIC,
            translate_state_for_ha(self._alarm_system.state_machine.state),
            True,
        )
        self._publish(HA_FAULT_TOPIC, "ON" if status["fault_reason"] else "OFF", True)
        if status["reporting_healthy"] is not None:
            self._publish(
                HA_REPORTING_TOPIC,
                "ON" if status["reporting_healthy"] else "OFF",
                True,
            )
        for zone in status["zones"]:
            self._publish(
                ha_zone_topic(zone["camera"], zone["zone"]),
                "ON" if zone["armed"] else "OFF",
                True,
            )

    def publish_event(self, event: AlarmEvent) -> None:
        self._publish(
            "alarm/event",
            json.dumps(
                {
                    "event_type": event.event_type.value,
                    "camera_id": event.camera_id,
                    "timestamp": event.timestamp,
                    "zone_id": event.zone_id,
                    "object_type": event.object_type,
                    "confidence": event.confidence,
                    "source": event.source,
                    "message": event.message,
                }
            ),
            False,
        )
