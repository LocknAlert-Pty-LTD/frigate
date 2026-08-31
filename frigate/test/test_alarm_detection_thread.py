"""Tests for AlarmDetectionThread.

frigate.comms.events_updater needs pyzmq, not installed in this sandbox, so
it's mocked out before import, following the same pattern as
frigate/test/test_maintainer.py. Unlike the original version of this file,
AlarmDetectionThread now imports frigate.config (for the FrigateConfig type
hint) and frigate.util.image (for the thumbnail crop used by AI
verification) -- both pull in cv2, so this file no longer runs in the bare
local sandbox and needs the real container (`docker exec frigate python3 -u
-m unittest frigate.test.test_alarm_detection_thread`), same as
test_alarm_config.py already does.
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

from frigate.alarm.ai_verification import AlarmVerificationResult  # noqa: E402
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


def _thread(system: AlarmSystem, ai_verifier=None) -> AlarmDetectionThread:
    return AlarmDetectionThread(
        system, MagicMock(), MagicMock(), ai_verifier=ai_verifier
    )


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
        "box": (0, 0, 10, 10),
    }
    base.update(overrides)
    return base


class TestEvaluate(unittest.TestCase):
    def test_qualifying_detection_triggers_alarm_and_records_event(self) -> None:
        system = _system()
        system.arm(ArmedMode.away, exit_delay_seconds=0)
        thread = _thread(system)

        thread._evaluate("front", "frame1", _tracked_object_dict())

        self.assertEqual(system.state_machine.state.value, "alarm")
        self.assertEqual(len(system.recent_events()), 1)
        self.assertEqual(system.recent_events()[0].event_type, AlarmEventType.burglary)

    def test_disarmed_system_does_not_trigger_or_record(self) -> None:
        system = _system()
        thread = _thread(system)

        thread._evaluate("front", "frame1", _tracked_object_dict())

        self.assertEqual(system.state_machine.state.value, "disarmed")
        self.assertEqual(len(system.recent_events()), 0)

    def test_second_qualifying_detection_while_already_alarming_is_recorded(
        self,
    ) -> None:
        system = _system()
        system.arm(ArmedMode.away, exit_delay_seconds=0)
        thread = _thread(system)

        thread._evaluate("front", "frame1", _tracked_object_dict(id="obj1"))
        # should not raise even though the state machine rejects a second trigger
        thread._evaluate("front", "frame2", _tracked_object_dict(id="obj2"))

        self.assertEqual(system.state_machine.state.value, "alarm")
        self.assertEqual(len(system.recent_events()), 2)

    def test_uses_entry_delay_from_matching_rule(self) -> None:
        system = _system(entry_delay_seconds=30)
        system.arm(ArmedMode.away, exit_delay_seconds=0)
        thread = _thread(system)

        thread._evaluate("front", "frame1", _tracked_object_dict())

        self.assertEqual(system.state_machine.state.value, "entry_delay")

    def test_triggering_invokes_alarm_system_on_change_and_on_event(self) -> None:
        """AlarmSystem itself owns notification (see system.py); this thread
        just needs to drive state through it, not remember to publish."""
        system = _system()
        system.arm(ArmedMode.away, exit_delay_seconds=0)
        on_change = MagicMock()
        on_event = MagicMock()
        system.on_change = on_change
        system.on_event = on_event
        thread = _thread(system)

        thread._evaluate("front", "frame1", _tracked_object_dict())

        on_change.assert_called()
        on_event.assert_called_once()

    def test_no_callbacks_configured_does_not_raise(self) -> None:
        system = _system()
        system.arm(ArmedMode.away, exit_delay_seconds=0)
        thread = _thread(system)

        thread._evaluate("front", "frame1", _tracked_object_dict())

    def test_bypassed_zone_never_reaches_the_adapter(self) -> None:
        system = _system()
        system.arm(ArmedMode.away, exit_delay_seconds=0)
        system.bypass_zone("front", "driveway")
        thread = _thread(system)

        thread._evaluate("front", "frame1", _tracked_object_dict())

        self.assertEqual(system.state_machine.state.value, "armed_away")
        self.assertEqual(len(system.recent_events()), 0)

    def test_unbypassed_zone_triggers_normally(self) -> None:
        system = _system()
        system.arm(ArmedMode.away, exit_delay_seconds=0)
        system.bypass_zone("front", "driveway")
        system.unbypass_zone("front", "driveway")
        thread = _thread(system)

        thread._evaluate("front", "frame1", _tracked_object_dict())

        self.assertEqual(system.state_machine.state.value, "alarm")


class TestAiVerification(unittest.TestCase):
    """AI verification is opt-in per zone (ZoneAlarmRule.ai_verification) and
    always fails open: no verifier configured, no thumbnail available, or a
    rejected result should never silently swallow a real trigger except in
    the one case that's the entire point -- a confirmed=False result."""

    def test_disabled_by_default_ignores_verifier_and_triggers_immediately(
        self,
    ) -> None:
        system = _system()  # ai_verification defaults to False
        system.arm(ArmedMode.away, exit_delay_seconds=0)
        verifier = MagicMock()
        thread = _thread(system, ai_verifier=verifier)

        thread._evaluate("front", "frame1", _tracked_object_dict())

        verifier.verify_async.assert_not_called()
        self.assertEqual(system.state_machine.state.value, "alarm")

    def test_no_verifier_configured_ignores_flag_and_triggers_immediately(
        self,
    ) -> None:
        system = _system(ai_verification=True)
        system.arm(ArmedMode.away, exit_delay_seconds=0)
        thread = _thread(system, ai_verifier=None)

        thread._evaluate("front", "frame1", _tracked_object_dict())

        self.assertEqual(system.state_machine.state.value, "alarm")

    def test_enabled_defers_trigger_until_verifier_confirms(self) -> None:
        system = _system(ai_verification=True)
        system.arm(ArmedMode.away, exit_delay_seconds=0)
        verifier = MagicMock()
        thread = _thread(system, ai_verifier=verifier)
        thread._build_thumbnail = MagicMock(return_value=b"fake-jpeg")

        thread._evaluate("front", "frame1", _tracked_object_dict())

        # Not triggered yet -- verify_async was called but its callback
        # hasn't run (it's async in real use; here we control it directly).
        # Still just "armed_away" (arm()'s own effect), not "alarm".
        verifier.verify_async.assert_called_once()
        self.assertEqual(system.state_machine.state.value, "armed_away")

        _event, _thumbnail, on_result = verifier.verify_async.call_args[0]
        on_result(_event, AlarmVerificationResult(confirmed=True))

        self.assertEqual(system.state_machine.state.value, "alarm")
        self.assertEqual(len(system.recent_events()), 1)

    def test_enabled_and_rejected_never_triggers(self) -> None:
        system = _system(ai_verification=True)
        system.arm(ArmedMode.away, exit_delay_seconds=0)
        verifier = MagicMock()
        thread = _thread(system, ai_verifier=verifier)
        thread._build_thumbnail = MagicMock(return_value=b"fake-jpeg")

        thread._evaluate("front", "frame1", _tracked_object_dict())
        _event, _thumbnail, on_result = verifier.verify_async.call_args[0]
        on_result(_event, AlarmVerificationResult(confirmed=False, reason="a cat"))

        self.assertEqual(system.state_machine.state.value, "armed_away")
        self.assertEqual(len(system.recent_events()), 0)

    def test_no_thumbnail_available_fails_open_and_triggers_immediately(self) -> None:
        system = _system(ai_verification=True)
        system.arm(ArmedMode.away, exit_delay_seconds=0)
        verifier = MagicMock()
        thread = _thread(system, ai_verifier=verifier)
        thread._build_thumbnail = MagicMock(return_value=None)

        thread._evaluate("front", "frame1", _tracked_object_dict())

        verifier.verify_async.assert_not_called()
        self.assertEqual(system.state_machine.state.value, "alarm")


class TestRunLoop(unittest.TestCase):
    def test_end_event_clears_persistence_tracking(self) -> None:
        system = _system(verification_seconds=5.0)
        system.arm(ArmedMode.away, exit_delay_seconds=0)
        thread = _thread(system)

        # start dwell tracking (doesn't qualify yet, verification_seconds=5)
        thread._evaluate("front", "frame1", _tracked_object_dict())
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
        thread = _thread(system)
        stop_event = MagicMock()
        stop_event.is_set.side_effect = [False, True]
        thread.event_subscriber.check_for_update = MagicMock(
            return_value=(EventTypeEnum.api, EventStateEnum.start, "front", "f", {})
        )
        thread.stop_event = stop_event

        thread.run()  # should not raise despite empty event_data

    def test_none_update_is_skipped(self) -> None:
        system = _system()
        thread = _thread(system)
        stop_event = MagicMock()
        stop_event.is_set.side_effect = [False, False, True]
        thread.event_subscriber.check_for_update = MagicMock(side_effect=[None, None])
        thread.stop_event = stop_event

        thread.run()  # should not raise


if __name__ == "__main__":
    unittest.main()
