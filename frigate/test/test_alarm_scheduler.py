"""Tests for AlarmScheduler._check_and_fire (time-based auto arm/disarm).

Needs frigate.alarm.audit -> frigate.models -> peewee, not available in
this bare sandbox (same tier as test_alarm_dispatcher_command.py); run
inside the real container. record_alarm_audit is patched in every test,
mirroring test_alarm_dispatcher_command.py's exact technique, since these
tests are about firing/dedup/day logic, not persistence (see
test_alarm_audit.py for that).
"""

import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

from frigate.alarm.rules import ZoneAlarmRule
from frigate.alarm.schedule import ScheduleEntry
from frigate.alarm.scheduler import AlarmScheduler
from frigate.alarm.state import ArmedMode
from frigate.alarm.system import AlarmSystem


def _alarm_system() -> AlarmSystem:
    rule = ZoneAlarmRule(camera="front", zone="driveway", objects=frozenset({"person"}))
    return AlarmSystem({("front", "driveway"): rule}, default_exit_delay_seconds=0)


def _scheduler(
    entries: list[ScheduleEntry], alarm_system: AlarmSystem | None = None
) -> AlarmScheduler:
    return AlarmScheduler(
        alarm_system or _alarm_system(), entries, MagicMock(), poll_interval_seconds=30
    )


class TestAlarmSchedulerFiring(unittest.TestCase):
    def setUp(self) -> None:
        patcher = patch("frigate.alarm.scheduler.record_alarm_audit")
        self.mock_record_audit = patcher.start()
        self.addCleanup(patcher.stop)

    def test_arms_at_matching_time(self) -> None:
        system = _alarm_system()
        scheduler = _scheduler(
            [ScheduleEntry(time="23:00", mode=ArmedMode.away)], system
        )
        scheduler._check_and_fire(datetime(2026, 1, 5, 23, 0))
        self.assertEqual(system.state_machine.state.value, "armed_away")
        self.mock_record_audit.assert_called_once_with(
            "arm", "schedule", details={"mode": "away"}
        )

    def test_disarms_when_mode_is_none(self) -> None:
        system = _alarm_system()
        system.arm(ArmedMode.away)
        self.assertEqual(system.state_machine.state.value, "armed_away")

        scheduler = _scheduler([ScheduleEntry(time="07:00", mode=None)], system)
        scheduler._check_and_fire(datetime(2026, 1, 5, 7, 0))
        self.assertEqual(system.state_machine.state.value, "disarmed")
        self.mock_record_audit.assert_called_once_with("disarm", "schedule")

    def test_does_not_fire_outside_matching_minute(self) -> None:
        system = _alarm_system()
        scheduler = _scheduler(
            [ScheduleEntry(time="23:00", mode=ArmedMode.away)], system
        )
        scheduler._check_and_fire(datetime(2026, 1, 5, 22, 59))
        self.assertEqual(system.state_machine.state.value, "disarmed")
        self.mock_record_audit.assert_not_called()

    def test_only_fires_once_per_day(self) -> None:
        system = _alarm_system()
        scheduler = _scheduler(
            [ScheduleEntry(time="23:00", mode=ArmedMode.away)], system
        )
        scheduler._check_and_fire(datetime(2026, 1, 5, 23, 0))
        system.disarm()
        # A second poll within the same matching minute (the real-world
        # reason for the dedup: a 30s interval checks each minute twice).
        scheduler._check_and_fire(datetime(2026, 1, 5, 23, 0))
        self.assertEqual(system.state_machine.state.value, "disarmed")
        self.mock_record_audit.assert_called_once()

    def test_fires_again_on_a_new_day(self) -> None:
        system = _alarm_system()
        scheduler = _scheduler(
            [ScheduleEntry(time="23:00", mode=ArmedMode.away)], system
        )
        scheduler._check_and_fire(datetime(2026, 1, 5, 23, 0))
        system.disarm()
        scheduler._check_and_fire(datetime(2026, 1, 6, 23, 0))
        self.assertEqual(system.state_machine.state.value, "armed_away")
        self.assertEqual(self.mock_record_audit.call_count, 2)

    def test_respects_days_filter(self) -> None:
        system = _alarm_system()
        # 2026-01-05 is a Monday (weekday() == 0); restrict to weekends.
        scheduler = _scheduler(
            [ScheduleEntry(time="23:00", mode=ArmedMode.away, days=frozenset({5, 6}))],
            system,
        )
        scheduler._check_and_fire(datetime(2026, 1, 5, 23, 0))
        self.assertEqual(system.state_machine.state.value, "disarmed")
        self.mock_record_audit.assert_not_called()

    def test_empty_days_means_every_day(self) -> None:
        system = _alarm_system()
        scheduler = _scheduler(
            [ScheduleEntry(time="23:00", mode=ArmedMode.away)], system
        )
        scheduler._check_and_fire(datetime(2026, 1, 5, 23, 0))
        self.assertEqual(system.state_machine.state.value, "armed_away")

    def test_invalid_transition_is_swallowed(self) -> None:
        system = _alarm_system()
        system.arm(ArmedMode.away)
        scheduler = _scheduler(
            [ScheduleEntry(time="23:00", mode=ArmedMode.away)], system
        )
        # Already armed_away -- arming again is not a valid transition.
        scheduler._check_and_fire(datetime(2026, 1, 5, 23, 0))
        self.assertEqual(system.state_machine.state.value, "armed_away")
        self.mock_record_audit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
