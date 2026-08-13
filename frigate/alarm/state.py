"""State definitions and the valid transition table for the alarm engine."""

from enum import Enum


class AlarmState(str, Enum):
    disarmed = "disarmed"
    arming = "arming"
    exit_delay = "exit_delay"
    armed_away = "armed_away"
    armed_stay = "armed_stay"
    entry_delay = "entry_delay"
    alarm = "alarm"
    alarm_memory = "alarm_memory"
    fault = "fault"


class ArmedMode(str, Enum):
    away = "away"
    stay = "stay"


class InvalidAlarmTransition(Exception):
    """Raised when an alarm state transition is not allowed from the current state."""

    def __init__(self, current: AlarmState, target: AlarmState) -> None:
        super().__init__(f"cannot transition from {current.value} to {target.value}")
        self.current = current
        self.target = target


# Valid direct transitions while not faulted. FAULT is handled separately by
# AlarmStateMachine since it can be entered from any state and always returns
# to whichever state was active when the fault occurred, rather than having a
# fixed set of predecessors/successors.
ALLOWED_TRANSITIONS: dict[AlarmState, frozenset[AlarmState]] = {
    AlarmState.disarmed: frozenset({AlarmState.arming}),
    AlarmState.arming: frozenset(
        {
            AlarmState.exit_delay,
            AlarmState.armed_away,
            AlarmState.armed_stay,
            AlarmState.disarmed,
        }
    ),
    AlarmState.exit_delay: frozenset(
        {AlarmState.armed_away, AlarmState.armed_stay, AlarmState.disarmed}
    ),
    AlarmState.armed_away: frozenset(
        {AlarmState.entry_delay, AlarmState.alarm, AlarmState.disarmed}
    ),
    AlarmState.armed_stay: frozenset(
        {AlarmState.entry_delay, AlarmState.alarm, AlarmState.disarmed}
    ),
    AlarmState.entry_delay: frozenset({AlarmState.alarm, AlarmState.disarmed}),
    AlarmState.alarm: frozenset({AlarmState.alarm_memory}),
    AlarmState.alarm_memory: frozenset({AlarmState.disarmed, AlarmState.arming}),
}
