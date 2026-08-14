"""Tests for the AlarmSystem orchestrator."""

import time
import unittest

from frigate.alarm.event import AlarmEvent, AlarmEventType
from frigate.alarm.queue import ReportingQueue
from frigate.alarm.rules import ZoneAlarmRule
from frigate.alarm.state import AlarmState, ArmedMode
from frigate.alarm.system import AlarmSystem


def _rules(**overrides) -> dict[tuple[str, str], ZoneAlarmRule]:
    defaults = {"camera": "front", "zone": "driveway", "objects": frozenset({"person"})}
    defaults.update(overrides)
    rule = ZoneAlarmRule(**defaults)
    return {(rule.camera, rule.zone): rule}


def _event() -> AlarmEvent:
    return AlarmEvent(
        event_type=AlarmEventType.burglary,
        camera_id="front",
        timestamp=1_700_000_000.0,
        zone_id="driveway",
    )


class TestArmDisarmClear(unittest.TestCase):
    def test_arm_uses_default_exit_delay(self) -> None:
        system = AlarmSystem(_rules(), default_exit_delay_seconds=15)
        state = system.arm(ArmedMode.away)
        self.assertEqual(state, AlarmState.exit_delay)
        self.assertEqual(
            system.state_machine.complete_exit_delay(), AlarmState.armed_away
        )

    def test_arm_can_override_exit_delay(self) -> None:
        system = AlarmSystem(_rules(), default_exit_delay_seconds=15)
        state = system.arm(ArmedMode.stay, exit_delay_seconds=0)
        self.assertEqual(state, AlarmState.armed_stay)

    def test_disarm_and_clear(self) -> None:
        system = AlarmSystem(_rules())
        system.arm(ArmedMode.away, exit_delay_seconds=0)
        system.state_machine.trigger(entry_delay_seconds=0)
        self.assertEqual(system.disarm(), AlarmState.alarm_memory)
        self.assertEqual(system.clear(), AlarmState.disarmed)


class TestDelayTimers(unittest.TestCase):
    """AlarmStateMachine deliberately doesn't time its own delay states
    (callers own the timer, see engine.py); these tests prove AlarmSystem
    is actually that caller, not just documentation saying it should be.
    A live end-to-end test against a real running instance caught this as
    a real bug: arm() -> exit_delay never auto-completed because nothing
    called complete_exit_delay()."""

    def test_exit_delay_completes_automatically(self) -> None:
        system = AlarmSystem(_rules(), default_exit_delay_seconds=0.05)
        system.arm(ArmedMode.away)
        self.assertEqual(system.state_machine.state, AlarmState.exit_delay)
        time.sleep(0.3)
        self.assertEqual(system.state_machine.state, AlarmState.armed_away)

    def test_disarm_during_exit_delay_cancels_the_timer(self) -> None:
        system = AlarmSystem(_rules(), default_exit_delay_seconds=0.05)
        system.arm(ArmedMode.away)
        system.disarm()
        time.sleep(0.3)
        self.assertEqual(system.state_machine.state, AlarmState.disarmed)

    def test_entry_delay_completes_automatically(self) -> None:
        system = AlarmSystem(_rules())
        system.arm(ArmedMode.away, exit_delay_seconds=0)
        system.trigger(entry_delay_seconds=0.05)
        self.assertEqual(system.state_machine.state, AlarmState.entry_delay)
        time.sleep(0.3)
        self.assertEqual(system.state_machine.state, AlarmState.alarm)

    def test_disarm_during_entry_delay_cancels_the_timer(self) -> None:
        system = AlarmSystem(_rules())
        system.arm(ArmedMode.away, exit_delay_seconds=0)
        system.trigger(entry_delay_seconds=0.05)
        system.disarm()
        time.sleep(0.3)
        self.assertEqual(system.state_machine.state, AlarmState.disarmed)

    def test_stop_cancels_pending_exit_delay_timer(self) -> None:
        system = AlarmSystem(_rules(), default_exit_delay_seconds=0.05)
        system.arm(ArmedMode.away)
        system.stop()
        time.sleep(0.3)
        self.assertEqual(system.state_machine.state, AlarmState.exit_delay)


class TestEventHistory(unittest.TestCase):
    def test_record_event_appends_to_history(self) -> None:
        system = AlarmSystem(_rules())
        system.record_event(_event())
        events = system.recent_events()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].camera_id, "front")

    def test_recent_events_most_recent_first(self) -> None:
        system = AlarmSystem(_rules())
        for i in range(3):
            system.record_event(
                AlarmEvent(
                    event_type=AlarmEventType.burglary,
                    camera_id="front",
                    timestamp=float(i),
                )
            )
        events = system.recent_events()
        self.assertEqual([e.timestamp for e in events], [2.0, 1.0, 0.0])

    def test_history_is_bounded(self) -> None:
        system = AlarmSystem(_rules(), event_history_size=2)
        for i in range(5):
            system.record_event(
                AlarmEvent(
                    event_type=AlarmEventType.burglary,
                    camera_id="front",
                    timestamp=float(i),
                )
            )
        self.assertEqual(len(system.recent_events()), 2)

    def test_record_event_enqueues_to_reporting_queue(self) -> None:
        sent = []
        rq = ReportingQueue(
            send=lambda e: sent.append(e) or True, retry_delay_seconds=0
        )
        system = AlarmSystem(_rules(), reporting_queue=rq)
        system.record_event(_event())
        rq._deliver_with_retry(rq._queue.get_nowait())
        self.assertEqual(len(sent), 1)

    def test_record_event_without_reporting_queue_does_not_raise(self) -> None:
        system = AlarmSystem(_rules(), reporting_queue=None)
        system.record_event(_event())  # should not raise


class TestArmedModeForEvaluation(unittest.TestCase):
    def test_none_when_disarmed(self) -> None:
        system = AlarmSystem(_rules())
        self.assertIsNone(system.armed_mode_for_evaluation)

    def test_none_during_exit_delay(self) -> None:
        system = AlarmSystem(_rules())
        system.arm(ArmedMode.away, exit_delay_seconds=30)
        self.assertIsNone(system.armed_mode_for_evaluation)

    def test_set_when_armed_away(self) -> None:
        system = AlarmSystem(_rules())
        system.arm(ArmedMode.away, exit_delay_seconds=0)
        self.assertEqual(system.armed_mode_for_evaluation, ArmedMode.away)

    def test_set_during_entry_delay(self) -> None:
        system = AlarmSystem(_rules())
        system.arm(ArmedMode.stay, exit_delay_seconds=0)
        system.state_machine.trigger(entry_delay_seconds=30)
        self.assertEqual(system.armed_mode_for_evaluation, ArmedMode.stay)

    def test_set_during_active_alarm(self) -> None:
        system = AlarmSystem(_rules())
        system.arm(ArmedMode.away, exit_delay_seconds=0)
        system.state_machine.trigger(entry_delay_seconds=0)
        self.assertEqual(system.armed_mode_for_evaluation, ArmedMode.away)

    def test_none_in_alarm_memory(self) -> None:
        system = AlarmSystem(_rules())
        system.arm(ArmedMode.away, exit_delay_seconds=0)
        system.state_machine.trigger(entry_delay_seconds=0)
        system.disarm()
        self.assertIsNone(system.armed_mode_for_evaluation)


class TestZoneStatus(unittest.TestCase):
    def test_zone_not_armed_when_system_disarmed(self) -> None:
        system = AlarmSystem(_rules())
        statuses = system.zone_status()
        self.assertEqual(len(statuses), 1)
        self.assertFalse(statuses[0].armed)

    def test_zone_armed_when_system_armed_in_matching_mode(self) -> None:
        system = AlarmSystem(_rules(arm_modes=frozenset({ArmedMode.away})))
        system.arm(ArmedMode.away, exit_delay_seconds=0)
        statuses = system.zone_status()
        self.assertTrue(statuses[0].armed)

    def test_zone_not_armed_when_mode_does_not_match(self) -> None:
        system = AlarmSystem(_rules(arm_modes=frozenset({ArmedMode.away})))
        system.arm(ArmedMode.stay, exit_delay_seconds=0)
        statuses = system.zone_status()
        self.assertFalse(statuses[0].armed)

    def test_disabled_zone_never_armed(self) -> None:
        system = AlarmSystem(_rules(enabled=False))
        system.arm(ArmedMode.away, exit_delay_seconds=0)
        statuses = system.zone_status()
        self.assertFalse(statuses[0].armed)


class TestStatus(unittest.TestCase):
    def test_status_reflects_disarmed_defaults(self) -> None:
        system = AlarmSystem(_rules())
        status = system.status()
        self.assertEqual(status["state"], "disarmed")
        self.assertIsNone(status["armed_mode"])
        self.assertFalse(status["is_alarm_active"])
        self.assertFalse(status["is_alarm_memory"])
        self.assertIsNone(status["reporting_healthy"])
        self.assertEqual(len(status["zones"]), 1)

    def test_status_reflects_alarm_state(self) -> None:
        system = AlarmSystem(_rules())
        system.arm(ArmedMode.away, exit_delay_seconds=0)
        system.state_machine.trigger(entry_delay_seconds=0)
        status = system.status()
        self.assertEqual(status["state"], "alarm")
        self.assertTrue(status["is_alarm_active"])

    def test_status_reflects_reporting_health(self) -> None:
        rq = ReportingQueue(send=lambda e: True, retry_delay_seconds=0)
        system = AlarmSystem(_rules(), reporting_queue=rq)
        self.assertTrue(system.status()["reporting_healthy"])


if __name__ == "__main__":
    unittest.main()
