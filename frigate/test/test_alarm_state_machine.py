"""Tests for the alarm engine state machine."""

import unittest

from frigate.alarm.engine import AlarmStateMachine
from frigate.alarm.state import AlarmState, ArmedMode, InvalidAlarmTransition


class TestArming(unittest.TestCase):
    def test_arm_away_immediate(self) -> None:
        machine = AlarmStateMachine()
        state = machine.arm(ArmedMode.away, exit_delay_seconds=0)
        self.assertEqual(state, AlarmState.armed_away)
        self.assertEqual(machine.armed_mode, ArmedMode.away)

    def test_arm_stay_immediate(self) -> None:
        machine = AlarmStateMachine()
        state = machine.arm(ArmedMode.stay, exit_delay_seconds=0)
        self.assertEqual(state, AlarmState.armed_stay)

    def test_arm_with_exit_delay_waits_for_completion(self) -> None:
        machine = AlarmStateMachine()
        state = machine.arm(ArmedMode.away, exit_delay_seconds=30)
        self.assertEqual(state, AlarmState.exit_delay)
        self.assertEqual(machine.complete_exit_delay(), AlarmState.armed_away)

    def test_disarm_cancels_exit_delay(self) -> None:
        machine = AlarmStateMachine()
        machine.arm(ArmedMode.stay, exit_delay_seconds=30)
        state = machine.disarm()
        self.assertEqual(state, AlarmState.disarmed)
        self.assertIsNone(machine.armed_mode)

    def test_cannot_rearm_while_already_armed(self) -> None:
        machine = AlarmStateMachine()
        machine.arm(ArmedMode.away, exit_delay_seconds=0)
        with self.assertRaises(InvalidAlarmTransition):
            machine.arm(ArmedMode.stay, exit_delay_seconds=0)

    def test_complete_exit_delay_requires_exit_delay_state(self) -> None:
        machine = AlarmStateMachine()
        with self.assertRaises(InvalidAlarmTransition):
            machine.complete_exit_delay()


class TestTriggerAndEntryDelay(unittest.TestCase):
    def test_trigger_requires_armed_system(self) -> None:
        machine = AlarmStateMachine()
        with self.assertRaises(InvalidAlarmTransition):
            machine.trigger()

    def test_trigger_immediate_goes_to_alarm(self) -> None:
        machine = AlarmStateMachine()
        machine.arm(ArmedMode.away, exit_delay_seconds=0)
        state = machine.trigger(entry_delay_seconds=0)
        self.assertEqual(state, AlarmState.alarm)

    def test_trigger_with_entry_delay_waits_for_completion(self) -> None:
        machine = AlarmStateMachine()
        machine.arm(ArmedMode.stay, exit_delay_seconds=0)
        state = machine.trigger(entry_delay_seconds=30)
        self.assertEqual(state, AlarmState.entry_delay)
        self.assertEqual(machine.complete_entry_delay(), AlarmState.alarm)

    def test_disarm_during_entry_delay_cancels_alarm(self) -> None:
        machine = AlarmStateMachine()
        machine.arm(ArmedMode.away, exit_delay_seconds=0)
        machine.trigger(entry_delay_seconds=30)
        state = machine.disarm()
        self.assertEqual(state, AlarmState.disarmed)

    def test_complete_entry_delay_requires_entry_delay_state(self) -> None:
        machine = AlarmStateMachine()
        with self.assertRaises(InvalidAlarmTransition):
            machine.complete_entry_delay()


class TestAlarmMemory(unittest.TestCase):
    def test_disarm_during_alarm_goes_to_memory_not_disarmed(self) -> None:
        machine = AlarmStateMachine()
        machine.arm(ArmedMode.away, exit_delay_seconds=0)
        machine.trigger(entry_delay_seconds=0)
        state = machine.disarm()
        self.assertEqual(state, AlarmState.alarm_memory)

    def test_clear_acknowledges_alarm_memory(self) -> None:
        machine = AlarmStateMachine()
        machine.arm(ArmedMode.away, exit_delay_seconds=0)
        machine.trigger(entry_delay_seconds=0)
        machine.disarm()
        state = machine.clear()
        self.assertEqual(state, AlarmState.disarmed)
        self.assertIsNone(machine.armed_mode)

    def test_clear_requires_alarm_memory_state(self) -> None:
        machine = AlarmStateMachine()
        with self.assertRaises(InvalidAlarmTransition):
            machine.clear()

    def test_rearming_from_alarm_memory_implicitly_clears_it(self) -> None:
        machine = AlarmStateMachine()
        machine.arm(ArmedMode.away, exit_delay_seconds=0)
        machine.trigger(entry_delay_seconds=0)
        machine.disarm()
        state = machine.arm(ArmedMode.stay, exit_delay_seconds=0)
        self.assertEqual(state, AlarmState.armed_stay)


class TestFault(unittest.TestCase):
    def test_fault_restores_prior_state_on_clear(self) -> None:
        machine = AlarmStateMachine()
        machine.arm(ArmedMode.away, exit_delay_seconds=0)
        state = machine.enter_fault("camera offline")
        self.assertEqual(state, AlarmState.fault)
        self.assertEqual(machine.fault_reason, "camera offline")
        self.assertEqual(machine.clear_fault(), AlarmState.armed_away)
        self.assertIsNone(machine.fault_reason)

    def test_fault_from_disarmed_restores_disarmed(self) -> None:
        machine = AlarmStateMachine()
        machine.enter_fault("comms down")
        self.assertEqual(machine.clear_fault(), AlarmState.disarmed)

    def test_repeated_fault_updates_reason_without_losing_prior_state(self) -> None:
        machine = AlarmStateMachine()
        machine.arm(ArmedMode.stay, exit_delay_seconds=0)
        machine.enter_fault("camera offline")
        machine.enter_fault("comms down")
        self.assertEqual(machine.fault_reason, "comms down")
        self.assertEqual(machine.clear_fault(), AlarmState.armed_stay)

    def test_clear_fault_requires_fault_state(self) -> None:
        machine = AlarmStateMachine()
        with self.assertRaises(InvalidAlarmTransition):
            machine.clear_fault()

    def test_no_transitions_allowed_while_faulted(self) -> None:
        machine = AlarmStateMachine()
        machine.enter_fault("comms down")
        with self.assertRaises(InvalidAlarmTransition):
            machine.arm(ArmedMode.away, exit_delay_seconds=0)


if __name__ == "__main__":
    unittest.main()
