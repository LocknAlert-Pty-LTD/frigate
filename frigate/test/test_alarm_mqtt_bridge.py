"""Tests for the AlarmMqttBridge. Uses a plain mock publish callable, no
real Dispatcher/MQTT client needed -- proving the bridge is usable without
the comms stack, which is the whole point of it taking a Callable instead
of importing Dispatcher directly.
"""

import json
import unittest

from frigate.alarm.event import AlarmEvent, AlarmEventType
from frigate.alarm.mqtt_bridge import AlarmMqttBridge
from frigate.alarm.rules import ZoneAlarmRule
from frigate.alarm.state import ArmedMode
from frigate.alarm.system import AlarmSystem


def _system() -> AlarmSystem:
    rule = ZoneAlarmRule(camera="front", zone="driveway", objects=frozenset({"person"}))
    return AlarmSystem({("front", "driveway"): rule})


class _RecordingPublisher:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, bool]] = []

    def __call__(self, topic: str, payload: str, retain: bool) -> None:
        self.calls.append((topic, payload, retain))


class TestPublishStatus(unittest.TestCase):
    def test_publishes_global_state_and_fault_topics(self) -> None:
        publisher = _RecordingPublisher()
        bridge = AlarmMqttBridge(_system(), publisher)
        bridge.publish_status()

        topics = [call[0] for call in publisher.calls]
        self.assertIn("alarm/state", topics)
        self.assertIn("alarm/fault", topics)

    def test_state_and_fault_topics_are_retained(self) -> None:
        publisher = _RecordingPublisher()
        bridge = AlarmMqttBridge(_system(), publisher)
        bridge.publish_status()

        retained = {call[0]: call[2] for call in publisher.calls}
        self.assertTrue(retained["alarm/state"])
        self.assertTrue(retained["alarm/fault"])

    def test_state_payload_is_valid_json_matching_status(self) -> None:
        publisher = _RecordingPublisher()
        system = _system()
        bridge = AlarmMqttBridge(system, publisher)
        bridge.publish_status()

        state_payload = next(c[1] for c in publisher.calls if c[0] == "alarm/state")
        self.assertEqual(json.loads(state_payload), system.status())

    def test_zone_topic_uses_camera_prefix_not_bare_alarm_prefix(self) -> None:
        """Regression guard for the ws.py fail-closed classifier: a bare
        "alarm/zone/<zone>/state" topic would be silently dropped since it
        doesn't start with a camera name."""
        publisher = _RecordingPublisher()
        bridge = AlarmMqttBridge(_system(), publisher)
        bridge.publish_status()

        topics = [call[0] for call in publisher.calls]
        self.assertIn("front/alarm_zone/driveway/state", topics)
        self.assertNotIn("alarm/zone/driveway/state", topics)


class TestPublishEvent(unittest.TestCase):
    def test_publishes_alarm_event_topic_not_retained(self) -> None:
        publisher = _RecordingPublisher()
        bridge = AlarmMqttBridge(_system(), publisher)
        event = AlarmEvent(
            event_type=AlarmEventType.burglary,
            camera_id="front",
            timestamp=1_700_000_000.0,
            zone_id="driveway",
        )
        bridge.publish_event(event)

        self.assertEqual(len(publisher.calls), 1)
        topic, payload, retain = publisher.calls[0]
        self.assertEqual(topic, "alarm/event")
        self.assertFalse(retain)
        self.assertEqual(json.loads(payload)["camera_id"], "front")


class TestIntegrationWithArm(unittest.TestCase):
    def test_status_reflects_armed_state_after_arm(self) -> None:
        publisher = _RecordingPublisher()
        system = _system()
        bridge = AlarmMqttBridge(system, publisher)

        system.arm(ArmedMode.away, exit_delay_seconds=0)
        bridge.publish_status()

        state_payload = next(c[1] for c in publisher.calls if c[0] == "alarm/state")
        self.assertEqual(json.loads(state_payload)["state"], "armed_away")


if __name__ == "__main__":
    unittest.main()
