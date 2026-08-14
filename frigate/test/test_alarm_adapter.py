"""Tests for the Frigate detection -> canonical alarm event adapter."""

import unittest

from frigate.alarm.adapter import DetectionAlarmAdapter
from frigate.alarm.event import AlarmEventType
from frigate.alarm.rules import ZoneAlarmRule
from frigate.alarm.state import ArmedMode


def _rule(**overrides) -> ZoneAlarmRule:
    defaults = {"camera": "front", "zone": "driveway"}
    defaults.update(overrides)
    return ZoneAlarmRule(**defaults)


class TestBasicQualification(unittest.TestCase):
    def test_qualifying_detection_produces_event(self) -> None:
        rule = _rule(objects=frozenset({"person"}))
        adapter = DetectionAlarmAdapter({("front", "driveway"): rule})
        event = adapter.evaluate(
            camera="front",
            zone="driveway",
            object_id="1",
            label="person",
            score=0.9,
            timestamp=100.0,
            armed_mode=ArmedMode.away,
        )
        self.assertIsNotNone(event)
        self.assertEqual(event.event_type, AlarmEventType.burglary)
        self.assertEqual(event.camera_id, "front")
        self.assertEqual(event.zone_id, "driveway")
        self.assertEqual(event.object_type, "person")
        self.assertEqual(event.confidence, 0.9)

    def test_disarmed_never_qualifies(self) -> None:
        rule = _rule(objects=frozenset({"person"}))
        adapter = DetectionAlarmAdapter({("front", "driveway"): rule})
        event = adapter.evaluate(
            camera="front",
            zone="driveway",
            object_id="1",
            label="person",
            score=0.9,
            timestamp=100.0,
            armed_mode=None,
        )
        self.assertIsNone(event)

    def test_unconfigured_zone_never_qualifies(self) -> None:
        adapter = DetectionAlarmAdapter({})
        event = adapter.evaluate(
            camera="front",
            zone="driveway",
            object_id="1",
            label="person",
            score=0.9,
            timestamp=100.0,
            armed_mode=ArmedMode.away,
        )
        self.assertIsNone(event)

    def test_disabled_zone_never_qualifies(self) -> None:
        rule = _rule(objects=frozenset({"person"}), enabled=False)
        adapter = DetectionAlarmAdapter({("front", "driveway"): rule})
        event = adapter.evaluate(
            camera="front",
            zone="driveway",
            object_id="1",
            label="person",
            score=0.9,
            timestamp=100.0,
            armed_mode=ArmedMode.away,
        )
        self.assertIsNone(event)

    def test_false_positive_never_qualifies(self) -> None:
        rule = _rule(objects=frozenset({"person"}))
        adapter = DetectionAlarmAdapter({("front", "driveway"): rule})
        event = adapter.evaluate(
            camera="front",
            zone="driveway",
            object_id="1",
            label="person",
            score=0.9,
            timestamp=100.0,
            armed_mode=ArmedMode.away,
            false_positive=True,
        )
        self.assertIsNone(event)


class TestObjectFiltering(unittest.TestCase):
    def test_unlisted_object_ignored(self) -> None:
        rule = _rule(objects=frozenset({"person"}))
        adapter = DetectionAlarmAdapter({("front", "driveway"): rule})
        event = adapter.evaluate(
            camera="front",
            zone="driveway",
            object_id="1",
            label="cat",
            score=0.9,
            timestamp=100.0,
            armed_mode=ArmedMode.away,
        )
        self.assertIsNone(event)

    def test_empty_object_whitelist_ignores_everything(self) -> None:
        rule = _rule()
        adapter = DetectionAlarmAdapter({("front", "driveway"): rule})
        event = adapter.evaluate(
            camera="front",
            zone="driveway",
            object_id="1",
            label="person",
            score=0.9,
            timestamp=100.0,
            armed_mode=ArmedMode.away,
        )
        self.assertIsNone(event)


class TestConfidenceThreshold(unittest.TestCase):
    def test_below_threshold_ignored(self) -> None:
        rule = _rule(objects=frozenset({"person"}), min_confidence=0.8)
        adapter = DetectionAlarmAdapter({("front", "driveway"): rule})
        event = adapter.evaluate(
            camera="front",
            zone="driveway",
            object_id="1",
            label="person",
            score=0.5,
            timestamp=100.0,
            armed_mode=ArmedMode.away,
        )
        self.assertIsNone(event)

    def test_at_threshold_qualifies(self) -> None:
        rule = _rule(objects=frozenset({"person"}), min_confidence=0.8)
        adapter = DetectionAlarmAdapter({("front", "driveway"): rule})
        event = adapter.evaluate(
            camera="front",
            zone="driveway",
            object_id="1",
            label="person",
            score=0.8,
            timestamp=100.0,
            armed_mode=ArmedMode.away,
        )
        self.assertIsNotNone(event)


class TestVerificationPersistence(unittest.TestCase):
    def test_instant_trigger_qualifies_immediately(self) -> None:
        rule = _rule(objects=frozenset({"person"}), verification_seconds=0)
        adapter = DetectionAlarmAdapter({("front", "driveway"): rule})
        event = adapter.evaluate(
            camera="front",
            zone="driveway",
            object_id="1",
            label="person",
            score=0.9,
            timestamp=100.0,
            armed_mode=ArmedMode.away,
        )
        self.assertIsNotNone(event)

    def test_persistence_mode_requires_dwell_time(self) -> None:
        rule = _rule(objects=frozenset({"person"}), verification_seconds=5.0)
        adapter = DetectionAlarmAdapter({("front", "driveway"): rule})
        common = {
            "camera": "front",
            "zone": "driveway",
            "object_id": "1",
            "label": "person",
            "score": 0.9,
            "armed_mode": ArmedMode.away,
        }
        self.assertIsNone(adapter.evaluate(timestamp=100.0, **common))
        self.assertIsNone(adapter.evaluate(timestamp=103.0, **common))
        event = adapter.evaluate(timestamp=105.0, **common)
        self.assertIsNotNone(event)

    def test_different_objects_tracked_independently(self) -> None:
        rule = _rule(objects=frozenset({"person"}), verification_seconds=5.0)
        adapter = DetectionAlarmAdapter({("front", "driveway"): rule})
        common = {
            "camera": "front",
            "zone": "driveway",
            "label": "person",
            "score": 0.9,
            "armed_mode": ArmedMode.away,
        }
        adapter.evaluate(object_id="1", timestamp=100.0, **common)
        adapter.evaluate(object_id="2", timestamp=103.0, **common)
        # object 1 has dwelt 5s by now, object 2 only 2s
        event1 = adapter.evaluate(object_id="1", timestamp=105.0, **common)
        event2 = adapter.evaluate(object_id="2", timestamp=105.0, **common)
        self.assertIsNotNone(event1)
        self.assertIsNone(event2)

    def test_clear_object_resets_persistence_tracking(self) -> None:
        rule = _rule(objects=frozenset({"person"}), verification_seconds=5.0)
        adapter = DetectionAlarmAdapter({("front", "driveway"): rule})
        common = {
            "camera": "front",
            "zone": "driveway",
            "object_id": "1",
            "label": "person",
            "score": 0.9,
            "armed_mode": ArmedMode.away,
        }
        adapter.evaluate(timestamp=100.0, **common)
        adapter.clear_object("front", "driveway", "1")
        event = adapter.evaluate(timestamp=103.0, **common)
        self.assertIsNone(event)


class TestArmModeGating(unittest.TestCase):
    def test_zone_not_armed_in_current_mode_ignored(self) -> None:
        rule = _rule(
            objects=frozenset({"person"}), arm_modes=frozenset({ArmedMode.away})
        )
        adapter = DetectionAlarmAdapter({("front", "driveway"): rule})
        event = adapter.evaluate(
            camera="front",
            zone="driveway",
            object_id="1",
            label="person",
            score=0.9,
            timestamp=100.0,
            armed_mode=ArmedMode.home,
        )
        self.assertIsNone(event)

    def test_zone_armed_in_current_mode_qualifies(self) -> None:
        rule = _rule(
            objects=frozenset({"person"}), arm_modes=frozenset({ArmedMode.away})
        )
        adapter = DetectionAlarmAdapter({("front", "driveway"): rule})
        event = adapter.evaluate(
            camera="front",
            zone="driveway",
            object_id="1",
            label="person",
            score=0.9,
            timestamp=100.0,
            armed_mode=ArmedMode.away,
        )
        self.assertIsNotNone(event)

    def test_interior_zone_excluded_from_night_mode_ignored(self) -> None:
        """An interior zone configured to skip 'night' (e.g. bypassed while
        occupants sleep) must not qualify when armed night."""
        rule = _rule(
            objects=frozenset({"person"}),
            arm_modes=frozenset({ArmedMode.away, ArmedMode.home}),
        )
        adapter = DetectionAlarmAdapter({("front", "driveway"): rule})
        event = adapter.evaluate(
            camera="front",
            zone="driveway",
            object_id="1",
            label="person",
            score=0.9,
            timestamp=100.0,
            armed_mode=ArmedMode.night,
        )
        self.assertIsNone(event)

    def test_zone_armed_by_default_in_all_three_modes(self) -> None:
        rule = _rule(objects=frozenset({"person"}))
        adapter = DetectionAlarmAdapter({("front", "driveway"): rule})
        for mode in (ArmedMode.away, ArmedMode.home, ArmedMode.night):
            event = adapter.evaluate(
                camera="front",
                zone="driveway",
                object_id="1",
                label="person",
                score=0.9,
                timestamp=100.0,
                armed_mode=mode,
            )
            self.assertIsNotNone(event, f"expected zone armed in {mode}")


class TestEventTypeOverrides(unittest.TestCase):
    def test_object_specific_event_type_override(self) -> None:
        rule = _rule(
            objects=frozenset({"person", "car"}),
            event_type=AlarmEventType.burglary,
            object_event_overrides={"car": AlarmEventType.supervision},
        )
        adapter = DetectionAlarmAdapter({("front", "driveway"): rule})
        person_event = adapter.evaluate(
            camera="front",
            zone="driveway",
            object_id="1",
            label="person",
            score=0.9,
            timestamp=100.0,
            armed_mode=ArmedMode.away,
        )
        car_event = adapter.evaluate(
            camera="front",
            zone="driveway",
            object_id="2",
            label="car",
            score=0.9,
            timestamp=100.0,
            armed_mode=ArmedMode.away,
        )
        self.assertEqual(person_event.event_type, AlarmEventType.burglary)
        self.assertEqual(car_event.event_type, AlarmEventType.supervision)


class TestGetRule(unittest.TestCase):
    def test_get_rule_returns_configured_rule(self) -> None:
        rule = _rule()
        adapter = DetectionAlarmAdapter({("front", "driveway"): rule})
        self.assertIs(adapter.get_rule("front", "driveway"), rule)

    def test_get_rule_returns_none_for_unconfigured_zone(self) -> None:
        adapter = DetectionAlarmAdapter({})
        self.assertIsNone(adapter.get_rule("front", "driveway"))


if __name__ == "__main__":
    unittest.main()
