"""Core alarm panel state machine.

Protocol-agnostic: has no dependency on MQTT, ZMQ, or Frigate detections.
Entry/exit delay countdowns are not timed internally. Callers start a delay
state (`arm` with exit_delay_seconds > 0, `trigger` with entry_delay_seconds
> 0) and are responsible for calling `complete_exit_delay` /
`complete_entry_delay` when the countdown elapses, or `disarm` to cancel it.
This keeps the state machine pure and independent of any particular
timer/event loop implementation.
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from frigate.alarm.state import (
    ALLOWED_TRANSITIONS,
    AlarmState,
    ArmedMode,
    InvalidAlarmTransition,
)

logger = logging.getLogger(__name__)


@dataclass
class AlarmStateMachine:
    """Tracks the current state of the alarm panel and enforces valid transitions."""

    state: AlarmState = AlarmState.disarmed
    armed_mode: ArmedMode | None = None
    fault_reason: str | None = None
    last_transition: datetime = field(default_factory=lambda: datetime.now(UTC))
    _pre_fault_state: AlarmState | None = field(default=None, repr=False)

    def _transition(self, target: AlarmState) -> None:
        allowed = ALLOWED_TRANSITIONS.get(self.state, frozenset())
        if target not in allowed:
            raise InvalidAlarmTransition(self.state, target)
        logger.debug("alarm state %s -> %s", self.state.value, target.value)
        self.state = target
        self.last_transition = datetime.now(UTC)

    def arm(self, mode: ArmedMode, exit_delay_seconds: int = 0) -> AlarmState:
        """Begin arming in the given mode, optionally starting an exit delay.

        Valid from DISARMED and ALARM_MEMORY (re-arming implicitly clears memory).
        """
        self._transition(AlarmState.arming)
        self.armed_mode = mode
        if exit_delay_seconds > 0:
            self._transition(AlarmState.exit_delay)
        else:
            self._complete_arming()
        return self.state

    def _complete_arming(self) -> None:
        # arm() always sets armed_mode immediately before calling this.
        assert self.armed_mode is not None
        target = {
            ArmedMode.away: AlarmState.armed_away,
            ArmedMode.home: AlarmState.armed_home,
            ArmedMode.night: AlarmState.armed_night,
        }[self.armed_mode]
        self._transition(target)

    def complete_exit_delay(self) -> AlarmState:
        """Called when the exit delay countdown elapses without cancellation."""
        if self.state != AlarmState.exit_delay:
            raise InvalidAlarmTransition(self.state, AlarmState.armed_away)
        self._complete_arming()
        return self.state

    def trigger(self, entry_delay_seconds: int = 0) -> AlarmState:
        """Record a qualified alarm-worthy detection while armed.

        Only valid while armed (or already in entry delay). Raises for any
        other state, since a detection is never sufficient on its own to
        cause an alarm.
        """
        if self.state == AlarmState.entry_delay:
            self._transition(AlarmState.alarm)
        elif entry_delay_seconds > 0:
            self._transition(AlarmState.entry_delay)
        else:
            self._transition(AlarmState.alarm)
        return self.state

    def complete_entry_delay(self) -> AlarmState:
        """Called when the entry delay countdown elapses without disarming."""
        if self.state != AlarmState.entry_delay:
            raise InvalidAlarmTransition(self.state, AlarmState.alarm)
        self._transition(AlarmState.alarm)
        return self.state

    def disarm(self) -> AlarmState:
        """Disarm the system.

        Silences an active alarm into alarm memory rather than clearing it
        outright (use `clear` for that). A no-op if already disarmed or in
        alarm memory.
        """
        if self.state == AlarmState.alarm:
            self._transition(AlarmState.alarm_memory)
        elif self.state not in (AlarmState.disarmed, AlarmState.alarm_memory):
            self._transition(AlarmState.disarmed)
            self.armed_mode = None
        return self.state

    def clear(self) -> AlarmState:
        """Clear alarm memory after an operator has acknowledged the alarm."""
        if self.state != AlarmState.alarm_memory:
            raise InvalidAlarmTransition(self.state, AlarmState.disarmed)
        self._transition(AlarmState.disarmed)
        self.armed_mode = None
        return self.state

    def enter_fault(self, reason: str) -> AlarmState:
        """Enter the fault state from any non-fault state.

        Remembers the prior state so `clear_fault` can restore it.
        """
        if self.state != AlarmState.fault:
            self._pre_fault_state = self.state
            self.state = AlarmState.fault
            self.last_transition = datetime.now(UTC)
            logger.warning("alarm entered fault state: %s", reason)
        self.fault_reason = reason
        return self.state

    def clear_fault(self) -> AlarmState:
        """Restore whatever state was active before the fault occurred."""
        if self.state != AlarmState.fault:
            raise InvalidAlarmTransition(
                self.state, self._pre_fault_state or AlarmState.disarmed
            )
        self.state = self._pre_fault_state or AlarmState.disarmed
        self._pre_fault_state = None
        self.fault_reason = None
        self.last_transition = datetime.now(UTC)
        return self.state
