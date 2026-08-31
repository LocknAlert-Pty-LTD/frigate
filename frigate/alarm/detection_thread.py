"""Background thread that feeds Frigate's internal detection stream into the
alarm engine.

Subscribes to EventUpdateSubscriber, the same MQTT-independent internal ZMQ
event bus every other Frigate subsystem (review, events, timeline) already
uses -- not MQTT -- so the alarm engine's "no MQTT dependency" constraint
holds even in the piece that's wired into the live process. Modeled on
EventProcessor (frigate/events/maintainer.py).

Field names (event_data["current_zones"], ["entered_zones"], ["id"],
["label"], ["top_score"], ["score"], ["false_positive"], ["frame_time"],
["box"]) are read directly from TrackedObject.to_dict()
(frigate/track/tracked_object.py), not guessed. frame_name (the shared-
memory frame this update refers to) comes from the same ZMQ tuple every
other consumer of EventUpdateSubscriber uses to fetch pixels -- see
frigate/embeddings/maintainer.py for the precedent this thread's thumbnail
fetch mirrors (SharedMemoryFrameManager.get(frame_name, ...)).

Does not publish to MQTT/WS itself -- AlarmSystem.trigger()/record_event()
call alarm_system.on_change/on_event automatically (see system.py), so this
thread only needs to drive state, not remember to publish it too.

Not executable/testable in this sandbox: needs pyzmq, not installed here
(see AGENTS.md phase 9 caveat).
"""

import functools
import logging
import threading
from multiprocessing.synchronize import Event as MpEvent
from typing import Any

from frigate.alarm.ai_verification import AlarmAiVerifier, AlarmVerificationResult
from frigate.alarm.event import AlarmEvent
from frigate.alarm.state import InvalidAlarmTransition
from frigate.alarm.system import AlarmSystem
from frigate.comms.events_updater import EventUpdateSubscriber
from frigate.config.config import FrigateConfig
from frigate.events.types import EventStateEnum, EventTypeEnum
from frigate.util.image import SharedMemoryFrameManager, create_thumbnail

logger = logging.getLogger(__name__)


class AlarmDetectionThread(threading.Thread):
    def __init__(
        self,
        alarm_system: AlarmSystem,
        stop_event: MpEvent,
        config: FrigateConfig,
        ai_verifier: AlarmAiVerifier | None = None,
    ) -> None:
        super().__init__(name="alarm_detection")
        self.alarm_system = alarm_system
        self.stop_event = stop_event
        self.config = config
        self.ai_verifier = ai_verifier
        self.event_subscriber = EventUpdateSubscriber()
        self.frame_manager = SharedMemoryFrameManager()

    def run(self) -> None:
        while not self.stop_event.is_set():
            update = self.event_subscriber.check_for_update(timeout=1.0)
            if update is None:
                continue

            event_type, event_state, camera, frame_name, event_data = update
            if event_type != EventTypeEnum.tracked_object or camera is None:
                continue

            if event_state == EventStateEnum.end:
                for zone in event_data.get("entered_zones", []):
                    self.alarm_system.adapter.clear_object(
                        camera, zone, event_data["id"]
                    )
                continue

            self._evaluate(camera, frame_name, event_data)

        self.event_subscriber.stop()

    def _evaluate(
        self, camera: str, frame_name: str, event_data: dict[str, Any]
    ) -> None:
        armed_mode = self.alarm_system.armed_mode_for_evaluation
        for zone in event_data.get("current_zones", []):
            if self.alarm_system.is_bypassed(camera, zone):
                continue

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

            if (
                self.ai_verifier is not None
                and rule is not None
                and rule.ai_verification
            ):
                thumbnail = self._build_thumbnail(camera, frame_name, event_data)
                if thumbnail is not None:
                    self.ai_verifier.verify_async(
                        alarm_event,
                        thumbnail,
                        functools.partial(self._on_verified, entry_delay=entry_delay),
                    )
                    continue
                # No frame available to verify against -- fail open and
                # trigger immediately rather than lose the detection.
                logger.debug(
                    "No frame available for AI verification on %s/%s; "
                    "triggering without it",
                    camera,
                    zone,
                )

            self._trigger_and_record(alarm_event, entry_delay)

    def _build_thumbnail(
        self, camera: str, frame_name: str, event_data: dict[str, Any]
    ) -> bytes | None:
        """Crop a JPEG thumbnail from the live frame this update refers to.

        Must run synchronously (not from the AI-verification background
        thread) since the shared-memory frame is only valid for the
        lifetime of this update.
        """
        camera_config = self.config.cameras.get(camera)
        if camera_config is None:
            return None

        yuv_frame = self.frame_manager.get(frame_name, camera_config.frame_shape_yuv)
        if yuv_frame is None:
            return None

        try:
            return create_thumbnail(yuv_frame, event_data["box"])
        finally:
            self.frame_manager.close(frame_name)

    def _on_verified(
        self, event: AlarmEvent, result: AlarmVerificationResult, entry_delay: int
    ) -> None:
        if not result.confirmed:
            return
        self._trigger_and_record(event, entry_delay)

    def _trigger_and_record(self, alarm_event: AlarmEvent, entry_delay: int) -> None:
        try:
            self.alarm_system.trigger(entry_delay_seconds=entry_delay)
        except InvalidAlarmTransition:
            # Expected when e.g. an alarm is already active and another
            # qualifying detection comes in; still record/report it.
            logger.debug(
                "alarm state machine did not accept trigger for %s/%s (state=%s)",
                alarm_event.camera_id,
                alarm_event.zone_id,
                self.alarm_system.state_machine.state.value,
            )

        self.alarm_system.record_event(alarm_event)

    def stop(self) -> None:
        self.join()
