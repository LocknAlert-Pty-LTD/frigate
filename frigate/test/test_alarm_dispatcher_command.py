"""Tests for Dispatcher._on_alarm_command (inbound MQTT alarm/set routing).

Like test_dispatcher_runtime_state.py, this needs frigate.config (via
frigate.comms.dispatcher's own imports), which pulls in cv2 -- not
available in this sandbox, so this could not be executed here. Written to
match test_dispatcher_runtime_state.py's precedent exactly (same
_build_dispatcher helper shape), not by memory.
"""

import unittest
from unittest.mock import MagicMock, patch

from frigate.alarm.rules import ZoneAlarmRule
from frigate.alarm.state import ArmedMode
from frigate.alarm.system import AlarmSystem
from frigate.comms.dispatcher import Dispatcher


def _build_dispatcher() -> Dispatcher:
    config = MagicMock()
    config.cameras = {}
    config_updater = MagicMock()
    onvif = MagicMock()
    ptz_metrics: dict = {}
    communicators: list = []

    with (
        patch("frigate.comms.dispatcher.CameraActivityManager"),
        patch("frigate.comms.dispatcher.AudioActivityManager"),
    ):
        return Dispatcher(config, config_updater, onvif, ptz_metrics, communicators)


def _alarm_system() -> AlarmSystem:
    rule = ZoneAlarmRule(camera="front", zone="driveway", objects=frozenset({"person"}))
    return AlarmSystem({("front", "driveway"): rule})


class TestAlarmCommandRouting(unittest.TestCase):
    def setUp(self) -> None:
        # These tests are about command routing/state transitions, not
        # persistence -- record_alarm_audit needs a real bound database
        # (see test_alarm_audit.py for that), which this lightweight
        # MagicMock-config dispatcher doesn't have.
        patcher = patch("frigate.comms.dispatcher.record_alarm_audit")
        self.mock_record_audit = patcher.start()
        self.addCleanup(patcher.stop)

    def test_receive_routes_alarm_set_topic_to_handler(self) -> None:
        dispatcher = _build_dispatcher()
        dispatcher.alarm_system = _alarm_system()
        dispatcher._receive("alarm/set", "ARM_AWAY")
        self.assertEqual(
            dispatcher.alarm_system.state_machine.armed_mode, ArmedMode.away
        )

    def test_arm_away_command(self) -> None:
        dispatcher = _build_dispatcher()
        dispatcher.alarm_system = _alarm_system()
        dispatcher._on_alarm_command("ARM_AWAY")
        self.assertEqual(
            dispatcher.alarm_system.state_machine.state.value, "armed_away"
        )

    def test_arm_home_command(self) -> None:
        dispatcher = _build_dispatcher()
        dispatcher.alarm_system = _alarm_system()
        dispatcher._on_alarm_command("ARM_HOME")
        self.assertEqual(
            dispatcher.alarm_system.state_machine.state.value, "armed_home"
        )

    def test_arm_night_command(self) -> None:
        dispatcher = _build_dispatcher()
        dispatcher.alarm_system = _alarm_system()
        dispatcher._on_alarm_command("ARM_NIGHT")
        self.assertEqual(
            dispatcher.alarm_system.state_machine.state.value, "armed_night"
        )

    def test_disarm_command(self) -> None:
        dispatcher = _build_dispatcher()
        dispatcher.alarm_system = _alarm_system()
        dispatcher.alarm_system.arm(ArmedMode.away, exit_delay_seconds=0)
        dispatcher._on_alarm_command("DISARM")
        self.assertEqual(dispatcher.alarm_system.state_machine.state.value, "disarmed")

    def test_command_is_case_insensitive(self) -> None:
        dispatcher = _build_dispatcher()
        dispatcher.alarm_system = _alarm_system()
        dispatcher._on_alarm_command("arm_away")
        self.assertEqual(
            dispatcher.alarm_system.state_machine.state.value, "armed_away"
        )

    def test_unrecognized_command_does_not_raise(self) -> None:
        dispatcher = _build_dispatcher()
        dispatcher.alarm_system = _alarm_system()
        dispatcher._on_alarm_command("SOMETHING_ELSE")
        self.assertEqual(dispatcher.alarm_system.state_machine.state.value, "disarmed")

    def test_invalid_transition_does_not_raise(self) -> None:
        """e.g. a stray ARM_HOME while already armed away shouldn't crash
        the MQTT message loop."""
        dispatcher = _build_dispatcher()
        dispatcher.alarm_system = _alarm_system()
        dispatcher.alarm_system.arm(ArmedMode.away, exit_delay_seconds=0)
        dispatcher._on_alarm_command("ARM_HOME")
        self.assertEqual(
            dispatcher.alarm_system.state_machine.state.value, "armed_away"
        )

    def test_no_alarm_system_configured_does_not_raise(self) -> None:
        dispatcher = _build_dispatcher()
        dispatcher._on_alarm_command("ARM_AWAY")

    def test_arm_command_invokes_on_change(self) -> None:
        dispatcher = _build_dispatcher()
        dispatcher.alarm_system = _alarm_system()
        calls = []
        dispatcher.alarm_system.on_change = lambda: calls.append(1)
        dispatcher._on_alarm_command("ARM_AWAY")
        self.assertEqual(len(calls), 1)

    def test_arm_command_records_audit_entry(self) -> None:
        dispatcher = _build_dispatcher()
        dispatcher.alarm_system = _alarm_system()
        dispatcher._on_alarm_command("ARM_NIGHT")
        self.mock_record_audit.assert_called_once_with(
            "arm", "mqtt", details={"mode": "night"}
        )

    def test_disarm_command_records_audit_entry(self) -> None:
        dispatcher = _build_dispatcher()
        dispatcher.alarm_system = _alarm_system()
        dispatcher.alarm_system.arm(ArmedMode.away, exit_delay_seconds=0)
        self.mock_record_audit.reset_mock()
        dispatcher._on_alarm_command("DISARM")
        self.mock_record_audit.assert_called_once_with("disarm", "mqtt")

    def test_invalid_transition_records_no_audit_entry(self) -> None:
        dispatcher = _build_dispatcher()
        dispatcher.alarm_system = _alarm_system()
        dispatcher.alarm_system.arm(ArmedMode.away, exit_delay_seconds=0)
        self.mock_record_audit.reset_mock()
        dispatcher._on_alarm_command("ARM_HOME")
        self.mock_record_audit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
