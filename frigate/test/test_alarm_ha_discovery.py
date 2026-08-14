"""Tests for Home Assistant MQTT discovery config generation.

Like factory.py, ha_discovery.py imports frigate.config.config (via
build_alarm_rules from factory.py), which pulls in cv2 -- not available in
this sandbox, so this could not be executed here. Written to match the
_build_dispatcher-style MagicMock config pattern used elsewhere in this
test suite.
"""

import json
import unittest
from unittest.mock import MagicMock

from frigate.alarm.ha_discovery import publish_ha_discovery
from frigate.alarm.mqtt_bridge import HA_FAULT_TOPIC, HA_REPORTING_TOPIC, HA_STATE_TOPIC
from frigate.alarm.rules import ZoneAlarmRule


def _mock_config(
    topic_prefix: str = "frigate", *, camera_alarm_enabled: bool = True
) -> MagicMock:
    """build_alarm_rules() (factory.py) calls camera_config.alarm.build_rules()
    for real, so the mock needs to return real ZoneAlarmRule data from that
    call rather than mocking the whole Pydantic model chain."""
    config = MagicMock()
    config.mqtt.topic_prefix = topic_prefix

    rules = (
        {("front", "driveway"): ZoneAlarmRule(camera="front", zone="driveway")}
        if camera_alarm_enabled
        else {}
    )
    camera = MagicMock()
    camera.alarm.build_rules = MagicMock(return_value=rules)

    config.cameras = {"front": camera}
    return config


class TestPublishHaDiscovery(unittest.TestCase):
    def setUp(self) -> None:
        self.calls: list[tuple[str, str, bool]] = []
        self.publish_absolute = lambda topic, payload, retain: self.calls.append(
            (topic, payload, retain)
        )

    def test_publishes_panel_config_topic(self) -> None:
        publish_ha_discovery(_mock_config(), self.publish_absolute)
        topics = [c[0] for c in self.calls]
        self.assertIn(
            "homeassistant/alarm_control_panel/frigate_alarm/panel/config", topics
        )

    def test_panel_config_command_and_state_topics_are_fully_qualified(self) -> None:
        publish_ha_discovery(
            _mock_config(topic_prefix="frigate"), self.publish_absolute
        )
        panel_payload = json.loads(
            next(
                c[1]
                for c in self.calls
                if c[0]
                == "homeassistant/alarm_control_panel/frigate_alarm/panel/config"
            )
        )
        self.assertEqual(panel_payload["state_topic"], f"frigate/{HA_STATE_TOPIC}")
        self.assertEqual(panel_payload["command_topic"], "frigate/alarm/set")

    def test_panel_config_respects_custom_topic_prefix(self) -> None:
        publish_ha_discovery(
            _mock_config(topic_prefix="myfrigate"), self.publish_absolute
        )
        panel_payload = json.loads(
            next(
                c[1]
                for c in self.calls
                if c[0]
                == "homeassistant/alarm_control_panel/frigate_alarm/panel/config"
            )
        )
        self.assertEqual(panel_payload["state_topic"], f"myfrigate/{HA_STATE_TOPIC}")

    def test_panel_config_has_all_three_arm_payloads(self) -> None:
        publish_ha_discovery(_mock_config(), self.publish_absolute)
        panel_payload = json.loads(
            next(
                c[1]
                for c in self.calls
                if c[0]
                == "homeassistant/alarm_control_panel/frigate_alarm/panel/config"
            )
        )
        self.assertEqual(panel_payload["payload_arm_away"], "ARM_AWAY")
        self.assertEqual(panel_payload["payload_arm_home"], "ARM_HOME")
        self.assertEqual(panel_payload["payload_arm_night"], "ARM_NIGHT")
        self.assertEqual(panel_payload["payload_disarm"], "DISARM")

    def test_panel_config_does_not_require_a_code(self) -> None:
        publish_ha_discovery(_mock_config(), self.publish_absolute)
        panel_payload = json.loads(
            next(
                c[1]
                for c in self.calls
                if c[0]
                == "homeassistant/alarm_control_panel/frigate_alarm/panel/config"
            )
        )
        self.assertFalse(panel_payload["code_arm_required"])
        self.assertFalse(panel_payload["code_disarm_required"])

    def test_publishes_fault_and_reporting_sensor_configs(self) -> None:
        publish_ha_discovery(_mock_config(), self.publish_absolute)
        topics = [c[0] for c in self.calls]
        self.assertIn("homeassistant/binary_sensor/frigate_alarm/fault/config", topics)
        self.assertIn(
            "homeassistant/binary_sensor/frigate_alarm/reporting/config", topics
        )

    def test_fault_sensor_uses_problem_device_class(self) -> None:
        publish_ha_discovery(_mock_config(), self.publish_absolute)
        payload = json.loads(
            next(
                c[1]
                for c in self.calls
                if c[0] == "homeassistant/binary_sensor/frigate_alarm/fault/config"
            )
        )
        self.assertEqual(payload["device_class"], "problem")
        self.assertEqual(payload["state_topic"], f"frigate/{HA_FAULT_TOPIC}")

    def test_reporting_sensor_uses_connectivity_device_class(self) -> None:
        publish_ha_discovery(_mock_config(), self.publish_absolute)
        payload = json.loads(
            next(
                c[1]
                for c in self.calls
                if c[0] == "homeassistant/binary_sensor/frigate_alarm/reporting/config"
            )
        )
        self.assertEqual(payload["device_class"], "connectivity")
        self.assertEqual(payload["state_topic"], f"frigate/{HA_REPORTING_TOPIC}")

    def test_publishes_zone_sensor_config_for_each_enabled_zone(self) -> None:
        publish_ha_discovery(_mock_config(), self.publish_absolute)
        topics = [c[0] for c in self.calls]
        self.assertIn(
            "homeassistant/binary_sensor/frigate_alarm/zone_front_driveway/config",
            topics,
        )

    def test_zone_sensor_uses_safety_device_class(self) -> None:
        publish_ha_discovery(_mock_config(), self.publish_absolute)
        payload = json.loads(
            next(
                c[1]
                for c in self.calls
                if c[0]
                == "homeassistant/binary_sensor/frigate_alarm/zone_front_driveway/config"
            )
        )
        self.assertEqual(payload["device_class"], "safety")

    def test_disabled_camera_alarm_produces_no_zone_sensors(self) -> None:
        config = _mock_config(camera_alarm_enabled=False)
        publish_ha_discovery(config, self.publish_absolute)
        topics = [c[0] for c in self.calls]
        self.assertFalse(any("zone_front_driveway" in t for t in topics))

    def test_all_discovery_configs_are_retained(self) -> None:
        publish_ha_discovery(_mock_config(), self.publish_absolute)
        self.assertTrue(all(c[2] for c in self.calls))

    def test_all_entities_share_the_same_device_identifier(self) -> None:
        publish_ha_discovery(_mock_config(), self.publish_absolute)
        for _topic, payload, _retain in self.calls:
            self.assertEqual(
                json.loads(payload)["device"]["identifiers"], ["frigate_alarm"]
            )


if __name__ == "__main__":
    unittest.main()
