"""State definitions and the valid transition table for the alarm engine."""

from enum import Enum


class AlarmState(str, Enum):
    disarmed = "disarmed"
    arming = "arming"
    exit_delay = "exit_delay"
    armed_away = "armed_away"
    armed_home = "armed_home"
    armed_night = "armed_night"
    entry_delay = "entry_delay"
    alarm = "alarm"
    alarm_memory = "alarm_memory"
    fault = "fault"


class ArmedMode(str, Enum):
    """Matches Home Assistant's alarm_control_panel arm modes (away/home/
    night) so the MQTT bridge can map 1:1 with no translation table for
    these three. "night" is what's surfaced to users as "Sleep" in the UI
    -- same concept, HA's literal name for it."""

    away = "away"
    home = "home"
    night = "night"


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
            AlarmState.armed_home,
            AlarmState.armed_night,
            AlarmState.disarmed,
        }
    ),
    AlarmState.exit_delay: frozenset(
        {
            AlarmState.armed_away,
            AlarmState.armed_home,
            AlarmState.armed_night,
            AlarmState.disarmed,
        }
    ),
    AlarmState.armed_away: frozenset(
        {AlarmState.entry_delay, AlarmState.alarm, AlarmState.disarmed}
    ),
    AlarmState.armed_home: frozenset(
        {AlarmState.entry_delay, AlarmState.alarm, AlarmState.disarmed}
    ),
    AlarmState.armed_night: frozenset(
        {AlarmState.entry_delay, AlarmState.alarm, AlarmState.disarmed}
    ),
    AlarmState.entry_delay: frozenset({AlarmState.alarm, AlarmState.disarmed}),
    AlarmState.alarm: frozenset({AlarmState.alarm_memory}),
    AlarmState.alarm_memory: frozenset({AlarmState.disarmed, AlarmState.arming}),
}
