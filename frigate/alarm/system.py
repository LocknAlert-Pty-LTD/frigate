"""Top-level alarm orchestrator: the object the API (and, in a later phase,
the detection wiring) talks to. Bundles the state machine, the zone rules
via a DetectionAlarmAdapter, an in-memory recent-event history, and an
optional reporting queue.

Kept separate from AlarmStateMachine (frigate/alarm/engine.py) on purpose:
the state machine only knows about states and transitions, this class only
knows about wiring those pieces together and answering "what's the current
status" -- neither one needs to know about Frigate detections or FastAPI.
"""

import logging
import threading
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

from frigate.alarm.adapter import DetectionAlarmAdapter
from frigate.alarm.engine import AlarmStateMachine
from frigate.alarm.event import AlarmEvent
from frigate.alarm.queue import ReportingQueue
from frigate.alarm.rules import ZoneAlarmRule
from frigate.alarm.state import AlarmState, ArmedMode, InvalidAlarmTransition

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ZoneStatus:
    camera: str
    zone: str
    enabled: bool
    armed: bool
    bypassed: bool


class AlarmSystem:
    def __init__(
        self,
        rules: dict[tuple[str, str], ZoneAlarmRule],
        *,
        default_exit_delay_seconds: int = 30,
        reporting_queue: ReportingQueue | None = None,
        whatsapp_queue: ReportingQueue | None = None,
        event_history_size: int = 100,
    ) -> None:
        self.state_machine = AlarmStateMachine()
        self.adapter = DetectionAlarmAdapter(rules)
        self._rules = rules
        self.default_exit_delay_seconds = default_exit_delay_seconds
        self.reporting_queue = reporting_queue
        # Same shape as reporting_queue -- both are plain ReportingQueue
        # instances (frigate/alarm/queue.py), just delivering to a
        # different channel. Given first-class treatment here (rather than
        # being held only on FrigateApp, as it briefly was) so its health
        # can be exposed via status() the same way reporting_healthy is.
        self.whatsapp_queue = whatsapp_queue
        self._events: deque[AlarmEvent] = deque(maxlen=event_history_size)
        # Per-arm-cycle zone bypass: cleared automatically once the system
        # is actually stood down (see disarm()/clear()), never persisted
        # beyond that, so a bypassed zone can never be silently forgotten.
        self._bypassed_zones: set[tuple[str, str]] = set()

        # AlarmStateMachine deliberately doesn't time its own delay states
        # (see engine.py) -- this is the caller that owns the timers, using
        # plain stdlib threading.Timer since these are simple one-shot
        # delays, not something that needs a scheduler.
        self._exit_delay_timer: threading.Timer | None = None
        self._entry_delay_timer: threading.Timer | None = None

        # Set by the wiring layer once it exists (e.g. an AlarmMqttBridge's
        # publish_status/publish_event) so every mutator -- HTTP API, an
        # inbound MQTT command, or a real detection -- keeps external state
        # in sync the same way, instead of each caller having to remember
        # to publish after calling arm()/disarm()/etc itself.
        self.on_change: Callable[[], None] | None = None
        self.on_event: Callable[[AlarmEvent], None] | None = None

    def arm(self, mode: ArmedMode, exit_delay_seconds: int | None = None) -> AlarmState:
        self._cancel_timers()
        delay = (
            self.default_exit_delay_seconds
            if exit_delay_seconds is None
            else exit_delay_seconds
        )
        state = self.state_machine.arm(mode, exit_delay_seconds=delay)
        if state == AlarmState.exit_delay:
            self._exit_delay_timer = threading.Timer(delay, self._complete_exit_delay)
            self._exit_delay_timer.daemon = True
            self._exit_delay_timer.start()
        self._notify()
        return state

    def _complete_exit_delay(self) -> None:
        try:
            self.state_machine.complete_exit_delay()
        except InvalidAlarmTransition:
            # Already disarmed or otherwise moved on before the timer fired.
            pass
        else:
            self._notify()

    def trigger(self, entry_delay_seconds: int = 0) -> AlarmState:
        """Record a qualifying detection while armed. Raises
        InvalidAlarmTransition under the same conditions as
        AlarmStateMachine.trigger() (e.g. not armed) -- callers already
        handle that (see AlarmDetectionThread)."""
        state = self.state_machine.trigger(entry_delay_seconds=entry_delay_seconds)
        if state == AlarmState.entry_delay:
            self._entry_delay_timer = threading.Timer(
                entry_delay_seconds, self._complete_entry_delay
            )
            self._entry_delay_timer.daemon = True
            self._entry_delay_timer.start()
        self._notify()
        return state

    def _complete_entry_delay(self) -> None:
        try:
            self.state_machine.complete_entry_delay()
        except InvalidAlarmTransition:
            # Already disarmed before the timer fired.
            pass
        else:
            logger.warning("alarm entry delay expired without disarming")
            self._notify()

    def disarm(self) -> AlarmState:
        self._cancel_timers()
        state = self.state_machine.disarm()
        if state == AlarmState.disarmed:
            # Only when actually stood down -- disarm() during an active
            # alarm silences into alarm_memory instead, and bypass should
            # survive until the operator genuinely clears/re-disarms.
            self._bypassed_zones.clear()
        self._notify()
        return state

    def clear(self) -> AlarmState:
        self._cancel_timers()
        state = self.state_machine.clear()
        self._bypassed_zones.clear()
        self._notify()
        return state

    def bypass_zone(self, camera: str, zone: str) -> None:
        """Temporarily exclude a zone from alarm evaluation for the rest of
        this arm cycle. Auto-clears on disarm()/clear() -- see there."""
        self._bypassed_zones.add((camera, zone))
        self._notify()

    def unbypass_zone(self, camera: str, zone: str) -> None:
        self._bypassed_zones.discard((camera, zone))
        self._notify()

    def is_bypassed(self, camera: str, zone: str) -> bool:
        return (camera, zone) in self._bypassed_zones

    def stop(self) -> None:
        """Cancel any pending delay timers. Safe to call even if none are
        pending."""
        self._cancel_timers()

    def _cancel_timers(self) -> None:
        if self._exit_delay_timer is not None:
            self._exit_delay_timer.cancel()
            self._exit_delay_timer = None
        if self._entry_delay_timer is not None:
            self._entry_delay_timer.cancel()
            self._entry_delay_timer = None

    def _notify(self) -> None:
        if self.on_change is not None:
            self.on_change()

    def record_event(self, event: AlarmEvent) -> None:
        """Log an event and hand it to the reporting queue, if configured.

        Does not itself call state_machine.trigger() -- the caller already
        has the qualifying ZoneAlarmRule (via self.adapter.get_rule) and
        knows whether/what entry delay to apply.
        """
        self._events.append(event)
        if self.reporting_queue is not None:
            self.reporting_queue.enqueue(event)
        if self.whatsapp_queue is not None:
            self.whatsapp_queue.enqueue(event)
        if self.on_event is not None:
            self.on_event(event)

    def recent_events(self, limit: int = 50) -> list[AlarmEvent]:
        return list(self._events)[-limit:][::-1]

    @property
    def armed_mode_for_evaluation(self) -> ArmedMode | None:
        """Armed mode to use when evaluating new detections against alarm
        rules. Stricter than zone_status's display logic in one direction
        (EXIT_DELAY does not count: the system isn't fully armed yet, so
        motion while walking out shouldn't trigger) and looser in another
        (ALARM does count: further qualifying detections while an alarm is
        already sounding should still be recorded/reported, e.g. a second
        zone violation during the same episode, even though the state
        machine itself will reject the redundant trigger() call).
        """
        if self.state_machine.state in (
            AlarmState.armed_away,
            AlarmState.armed_home,
            AlarmState.armed_night,
            AlarmState.entry_delay,
            AlarmState.alarm,
        ):
            return self.state_machine.armed_mode
        return None

    def zone_status(self) -> list[ZoneStatus]:
        armed_mode = (
            self.state_machine.armed_mode
            if self.state_machine.state
            in (
                AlarmState.armed_away,
                AlarmState.armed_home,
                AlarmState.armed_night,
                AlarmState.entry_delay,
                AlarmState.exit_delay,
            )
            else None
        )
        return [
            ZoneStatus(
                camera=rule.camera,
                zone=rule.zone,
                enabled=rule.enabled,
                armed=bool(
                    rule.enabled
                    and armed_mode is not None
                    and armed_mode in rule.arm_modes
                    and not self.is_bypassed(rule.camera, rule.zone)
                ),
                bypassed=self.is_bypassed(rule.camera, rule.zone),
            )
            for rule in self._rules.values()
        ]

    def status(self) -> dict:
        machine = self.state_machine
        return {
            "state": machine.state.value,
            "armed_mode": machine.armed_mode.value if machine.armed_mode else None,
            "is_alarm_active": machine.state == AlarmState.alarm,
            "is_alarm_memory": machine.state == AlarmState.alarm_memory,
            "fault_reason": machine.fault_reason,
            "last_transition": machine.last_transition.isoformat(),
            "reporting_healthy": (
                self.reporting_queue.healthy
                if self.reporting_queue is not None
                else None
            ),
            "whatsapp_healthy": (
                self.whatsapp_queue.healthy if self.whatsapp_queue is not None else None
            ),
            "zones": [
                {
                    "camera": z.camera,
                    "zone": z.zone,
                    "enabled": z.enabled,
                    "armed": z.armed,
                    "bypassed": z.bypassed,
                }
                for z in self.zone_status()
            ],
        }
