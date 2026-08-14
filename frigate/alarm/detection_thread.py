"""Background thread that feeds Frigate's internal detection stream into the
alarm engine.

Subscribes to EventUpdateSubscriber, the same MQTT-independent internal ZMQ
event bus every other Frigate subsystem (review, events, timeline) already
uses -- not MQTT -- so the alarm engine's "no MQTT dependency" constraint
holds even in the piece that's wired into the live process. Modeled on
EventProcessor (frigate/events/maintainer.py).

Field names (event_data["current_zones"], ["entered_zones"], ["id"],
["label"], ["top_score"], ["score"], ["false_positive"], ["frame_time"])
are read directly from TrackedObject.to_dict()
(frigate/track/tracked_object.py), not guessed.

Not executable/testable in this sandbox: needs pyzmq, not installed here
(see AGENTS.md phase 9 caveat).
"""

import logging
import threading
from multiprocessing.synchronize import Event as MpEvent
from typing import Any

from frigate.alarm.mqtt_bridge import AlarmMqttBridge
from frigate.alarm.state import InvalidAlarmTransition
from frigate.alarm.system import AlarmSystem
from frigate.comms.events_updater import EventUpdateSubscriber
from frigate.events.types import EventStateEnum, EventTypeEnum

logger = logging.getLogger(__name__)


class AlarmDetectionThread(threading.Thread):
    def __init__(
        self,
        alarm_system: AlarmSystem,
        stop_event: MpEvent,
        mqtt_bridge: AlarmMqttBridge | None = None,
    ) -> None:
        super().__init__(name="alarm_detection")
        self.alarm_system = alarm_system
        self.mqtt_bridge = mqtt_bridge
        self.stop_event = stop_event
        self.event_subscriber = EventUpdateSubscriber()

    def run(self) -> None:
        while not self.stop_event.is_set():
            update = self.event_subscriber.check_for_update(timeout=1.0)
            if update is None:
                continue

            event_type, event_state, camera, _frame_name, event_data = update
            if event_type != EventTypeEnum.tracked_object or camera is None:
                continue

            if event_state == EventStateEnum.end:
                for zone in event_data.get("entered_zones", []):
                    self.alarm_system.adapter.clear_object(
                        camera, zone, event_data["id"]
                    )
                continue

            self._evaluate(camera, event_data)

        self.event_subscriber.stop()

    def _evaluate(self, camera: str, event_data: dict[str, Any]) -> None:
        armed_mode = self.alarm_system.armed_mode_for_evaluation
        for zone in event_data.get("current_zones", []):
            alarm_event = self.alarm_system.adapter.evaluate(
                camera=camera,
                zone=zone,
                object_id=event_data["id"],
                label=event_data["label"],
                score=event_data.get("top_score") or event_data["score"],
                timestamp=event_data["frame_time"],
                armed_mode=armed_mode,
                false_positive=event_data.get("false_positive", False),
            )
            if alarm_event is None:
                continue

            rule = self.alarm_system.adapter.get_rule(camera, zone)
            entry_delay = rule.entry_delay_seconds if rule else 0
            try:
                self.alarm_system.trigger(entry_delay_seconds=entry_delay)
            except InvalidAlarmTransition:
                # Expected when e.g. an alarm is already active and another
                # qualifying detection comes in; still record/report it.
                logger.debug(
                    "alarm state machine did not accept trigger for %s/%s (state=%s)",
                    camera,
                    zone,
                    self.alarm_system.state_machine.state.value,
                )

            self.alarm_system.record_event(alarm_event)
            if self.mqtt_bridge is not None:
                self.mqtt_bridge.publish_event(alarm_event)
                self.mqtt_bridge.publish_status()

    def stop(self) -> None:
        self.join()
