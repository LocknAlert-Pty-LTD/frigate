"""Publishes AlarmSystem state changes to MQTT + WebSocket via the Dispatcher.

Optional glue: only constructed by the wiring layer when there's a
Dispatcher to publish through. Takes a plain publish callable rather than
importing frigate.comms.dispatcher.Dispatcher, so this stays testable
without constructing a real Dispatcher and without adding frigate.comms to
this module's own import graph -- Dispatcher.publish's signature
(topic, payload, retain) is all this needs to know about it.

Topics (see AGENTS.md phase 1 architecture note for the reasoning):
- "alarm/state": global, retained. Published on every state change.
- "alarm/fault": global, retained. Published alongside alarm/state.
- "alarm/event": published per qualifying detection event, not retained.
- "<camera>/alarm_zone/<zone>/state": per zone, so it piggybacks on the
  existing camera-prefix auto-scoping in frigate/comms/ws.py instead of
  needing a new classifier entry there (the original spec's bare
  "alarm/zone/<zone>/state" doesn't start with a camera name, so it would
  be silently dropped by ws.py's fail-closed classifier without one).
"""

import json
import logging
from collections.abc import Callable

from frigate.alarm.event import AlarmEvent
from frigate.alarm.system import AlarmSystem

logger = logging.getLogger(__name__)

# (topic, payload, retain) -> None, matching Dispatcher.publish's signature.
Publish = Callable[[str, str, bool], None]


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
