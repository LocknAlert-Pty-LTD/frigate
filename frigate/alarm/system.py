"""Top-level alarm orchestrator: the object the API (and, in a later phase,
the detection wiring) talks to. Bundles the state machine, the zone rules
via a DetectionAlarmAdapter, an in-memory recent-event history, and an
optional reporting queue.

Kept separate from AlarmStateMachine (frigate/alarm/engine.py) on purpose:
the state machine only knows about states and transitions, this class only
knows about wiring those pieces together and answering "what's the current
status" -- neither one needs to know about Frigate detections or FastAPI.
"""

from collections import deque
from dataclasses import dataclass

from frigate.alarm.adapter import DetectionAlarmAdapter
from frigate.alarm.engine import AlarmStateMachine
from frigate.alarm.event import AlarmEvent
from frigate.alarm.queue import ReportingQueue
from frigate.alarm.rules import ZoneAlarmRule
from frigate.alarm.state import AlarmState, ArmedMode


@dataclass(frozen=True)
class ZoneStatus:
    camera: str
    zone: str
    enabled: bool
    armed: bool


class AlarmSystem:
    def __init__(
        self,
        rules: dict[tuple[str, str], ZoneAlarmRule],
        *,
        default_exit_delay_seconds: int = 30,
        reporting_queue: ReportingQueue | None = None,
        event_history_size: int = 100,
    ) -> None:
        self.state_machine = AlarmStateMachine()
        self.adapter = DetectionAlarmAdapter(rules)
        self._rules = rules
        self.default_exit_delay_seconds = default_exit_delay_seconds
        self.reporting_queue = reporting_queue
        self._events: deque[AlarmEvent] = deque(maxlen=event_history_size)

    def arm(self, mode: ArmedMode, exit_delay_seconds: int | None = None) -> AlarmState:
        delay = (
            self.default_exit_delay_seconds
            if exit_delay_seconds is None
            else exit_delay_seconds
        )
        return self.state_machine.arm(mode, exit_delay_seconds=delay)

    def disarm(self) -> AlarmState:
        return self.state_machine.disarm()

    def clear(self) -> AlarmState:
        return self.state_machine.clear()

    def record_event(self, event: AlarmEvent) -> None:
        """Log an event and hand it to the reporting queue, if configured.

        Does not itself call state_machine.trigger() -- the caller already
        has the qualifying ZoneAlarmRule (via self.adapter.get_rule) and
        knows whether/what entry delay to apply.
        """
        self._events.append(event)
        if self.reporting_queue is not None:
            self.reporting_queue.enqueue(event)

    def recent_events(self, limit: int = 50) -> list[AlarmEvent]:
        return list(self._events)[-limit:][::-1]

    def zone_status(self) -> list[ZoneStatus]:
        armed_mode = (
            self.state_machine.armed_mode
            if self.state_machine.state
            in (
                AlarmState.armed_away,
                AlarmState.armed_stay,
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
                ),
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
            "zones": [
                {
                    "camera": z.camera,
                    "zone": z.zone,
                    "enabled": z.enabled,
                    "armed": z.armed,
                }
                for z in self.zone_status()
            ],
        }
