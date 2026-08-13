"""Tests for AlarmDetectionThread.

frigate.comms.events_updater needs pyzmq, not installed in this sandbox, so
it's mocked out before import, following the same pattern as
frigate/test/test_maintainer.py. Unlike that precedent (which still needs
frigate.config -> cv2 and can't run here), AlarmDetectionThread doesn't
import frigate.config at all, so this actually runs in this sandbox.
"""

import sys
import unittest
from unittest.mock import MagicMock

_MOCKED_MODULES = ["frigate.comms.events_updater"]
_originals = {name: sys.modules.get(name) for name in _MOCKED_MODULES}
for _name in _MOCKED_MODULES:
    sys.modules[_name] = MagicMock()

from frigate.alarm.detection_thread import AlarmDetectionThread  # noqa: E402

for _name, _orig in _originals.items():
    if _orig is None:
        sys.modules.pop(_name, None)
    else:
        sys.modules[_name] = _orig

from frigate.alarm.event import AlarmEventType  # noqa: E402
from frigate.alarm.rules import ZoneAlarmRule  # noqa: E402
from frigate.alarm.state import ArmedMode  # noqa: E402
from frigate.alarm.system import AlarmSystem  # noqa: E402
from frigate.events.types import EventStateEnum, EventTypeEnum  # noqa: E402


def _system(**rule_overrides) -> AlarmSystem:
    defaults = {"camera": "front", "zone": "driveway", "objects": frozenset({"person"})}
    defaults.update(rule_overrides)
    rule = ZoneAlarmRule(**defaults)
    return AlarmSystem({("front", "driveway"): rule})


def _tracked_object_dict(**overrides) -> dict:
    base = {
        "id": "obj1",
        "label": "person",
        "score": 0.9,
        "top_score": 0.95,
        "false_positive": False,
        "frame_time": 1_700_000_000.0,
        "current_zones": ["driveway"],
        "entered_zones": ["driveway"],
    }
    base.update(overrides)
    return base


class TestEvaluate(unittest.TestCase):
    def test_qualifying_detection_triggers_alarm_and_records_event(self) -> None:
        system = _system()
        system.arm(ArmedMode.away, exit_delay_seconds=0)
        thread = AlarmDetectionThread(system, MagicMock())

        thread._evaluate("front", _tracked_object_dict())

        self.assertEqual(system.state_machine.state.value, "alarm")
        self.assertEqual(len(system.recent_events()), 1)
        self.assertEqual(system.recent_events()[0].event_type, AlarmEventType.burglary)

    def test_disarmed_system_does_not_trigger_or_record(self) -> None:
        system = _system()
        thread = AlarmDetectionThread(system, MagicMock())

        thread._evaluate("front", _tracked_object_dict())

        self.assertEqual(system.state_machine.state.value, "disarmed")
        self.assertEqual(len(system.recent_events()), 0)

    def test_second_qualifying_detection_while_already_alarming_is_recorded(
        self,
    ) -> None:
        system = _system()
        system.arm(ArmedMode.away, exit_delay_seconds=0)
        thread = AlarmDetectionThread(system, MagicMock())

        thread._evaluate("front", _tracked_object_dict(id="obj1"))
        # should not raise even though the state machine rejects a second trigger
        thread._evaluate("front", _tracked_object_dict(id="obj2"))

        self.assertEqual(system.state_machine.state.value, "alarm")
        self.assertEqual(len(system.recent_events()), 2)

    def test_uses_entry_delay_from_matching_rule(self) -> None:
        system = _system(entry_delay_seconds=30)
        system.arm(ArmedMode.away, exit_delay_seconds=0)
        thread = AlarmDetectionThread(system, MagicMock())

        thread._evaluate("front", _tracked_object_dict())

        self.assertEqual(system.state_machine.state.value, "entry_delay")

    def test_publishes_via_mqtt_bridge_when_provided(self) -> None:
        system = _system()
        system.arm(ArmedMode.away, exit_delay_seconds=0)
        bridge = MagicMock()
        thread = AlarmDetectionThread(system, MagicMock(), mqtt_bridge=bridge)

        thread._evaluate("front", _tracked_object_dict())

        bridge.publish_event.assert_called_once()
        bridge.publish_status.assert_called_once()

    def test_no_mqtt_bridge_does_not_raise(self) -> None:
        system = _system()
        system.arm(ArmedMode.away, exit_delay_seconds=0)
        thread = AlarmDetectionThread(system, MagicMock(), mqtt_bridge=None)

        thread._evaluate("front", _tracked_object_dict())


class TestRunLoop(unittest.TestCase):
    def test_end_event_clears_persistence_tracking(self) -> None:
        system = _system(verification_seconds=5.0)
        system.arm(ArmedMode.away, exit_delay_seconds=0)
        thread = AlarmDetectionThread(system, MagicMock())

        # start dwell tracking (doesn't qualify yet, verification_seconds=5)
        thread._evaluate("front", _tracked_object_dict())
        self.assertIn(("front", "driveway", "obj1"), system.adapter._pending)

        stop_event = MagicMock()
        stop_event.is_set.side_effect = [False, True]
        thread.event_subscriber.check_for_update = MagicMock(
            return_value=(
                EventTypeEnum.tracked_object,
                EventStateEnum.end,
                "front",
                "front-123",
                _tracked_object_dict(),
            )
        )
        thread.stop_event = stop_event

        thread.run()

        self.assertNotIn(("front", "driveway", "obj1"), system.adapter._pending)

    def test_ignores_non_tracked_object_events(self) -> None:
        system = _system()
        thread = AlarmDetectionThread(system, MagicMock())
        stop_event = MagicMock()
        stop_event.is_set.side_effect = [False, True]
        thread.event_subscriber.check_for_update = MagicMock(
            return_value=(EventTypeEnum.api, EventStateEnum.start, "front", "f", {})
        )
        thread.stop_event = stop_event

        thread.run()  # should not raise despite empty event_data

    def test_none_update_is_skipped(self) -> None:
        system = _system()
        thread = AlarmDetectionThread(system, MagicMock())
        stop_event = MagicMock()
        stop_event.is_set.side_effect = [False, False, True]
        thread.event_subscriber.check_for_update = MagicMock(side_effect=[None, None])
        thread.stop_event = stop_event

        thread.run()  # should not raise


if __name__ == "__main__":
    unittest.main()
