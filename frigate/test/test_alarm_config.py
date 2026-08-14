"""Tests for the alarm engine config schema and validation.

NOTE: like the rest of the frigate.config.* test suite, this module needs
Frigate's full runtime dependency set (opencv, etc.) to import
`frigate.config`, since `frigate/config/__init__.py` eagerly imports the
whole config tree. It could not be executed in the dev sandbox this was
written in (see AGENTS.md); run it in a full dev/CI environment.
"""

import os
import unittest

from pydantic import ValidationError

from frigate.alarm.event import AlarmEventType
from frigate.alarm.state import ArmedMode
from frigate.config import FrigateConfig
from frigate.const import MODEL_CACHE_DIR

DRIVEWAY_ZONE = {"coordinates": "0,0,1,0,1,1,0,1"}


def _minimal(camera_overrides: dict | None = None, global_alarm: dict | None = None):
    camera = {
        "ffmpeg": {
            "inputs": [{"path": "rtsp://10.0.0.1:554/video", "roles": ["detect"]}]
        },
        "detect": {"height": 1080, "width": 1920, "fps": 5},
    }
    if camera_overrides:
        camera.update(camera_overrides)
    config = {"mqtt": {"host": "mqtt"}, "cameras": {"back": camera}}
    if global_alarm is not None:
        config["alarm"] = global_alarm
    return config


def _config_with_valid_alarm_zone(**zone_overrides):
    zone = {"objects": ["person"]}
    zone.update(zone_overrides)
    return _minimal(
        camera_overrides={
            "zones": {"driveway": DRIVEWAY_ZONE},
            "alarm": {"enabled": True, "zones": {"driveway": zone}},
        },
        global_alarm={"enabled": True},
    )


class TestAlarmConfigBackwardsCompat(unittest.TestCase):
    def setUp(self) -> None:
        if not os.path.exists(MODEL_CACHE_DIR) and not os.path.islink(MODEL_CACHE_DIR):
            os.makedirs(MODEL_CACHE_DIR)

    def test_missing_alarm_section_defaults_to_disabled(self) -> None:
        config = FrigateConfig(**_minimal())
        self.assertFalse(config.alarm.enabled)
        self.assertFalse(config.cameras["back"].alarm.enabled)
        self.assertEqual(config.cameras["back"].alarm.zones, {})

    def test_alarm_enabled_in_config_snapshots_file_value(self) -> None:
        config = FrigateConfig(**_minimal(global_alarm={"enabled": True}))
        self.assertTrue(config.alarm.enabled_in_config)


class TestAlarmZoneValidation(unittest.TestCase):
    def setUp(self) -> None:
        if not os.path.exists(MODEL_CACHE_DIR) and not os.path.islink(MODEL_CACHE_DIR):
            os.makedirs(MODEL_CACHE_DIR)

    def test_valid_alarm_zone_config(self) -> None:
        config = FrigateConfig(**_config_with_valid_alarm_zone())
        zone_config = config.cameras["back"].alarm.zones["driveway"]
        rule = zone_config.to_rule("back", "driveway")
        self.assertEqual(rule.camera, "back")
        self.assertEqual(rule.zone, "driveway")
        self.assertEqual(rule.event_type, AlarmEventType.burglary)
        self.assertIn(ArmedMode.away, rule.arm_modes)
        self.assertIn(ArmedMode.home, rule.arm_modes)
        self.assertIn(ArmedMode.night, rule.arm_modes)

    def test_alarm_zone_must_reference_existing_zone(self) -> None:
        config = _minimal(
            camera_overrides={
                "alarm": {
                    "enabled": True,
                    "zones": {"nonexistent": {"objects": ["person"]}},
                },
            },
            global_alarm={"enabled": True},
        )
        self.assertRaises(ValidationError, lambda: FrigateConfig(**config))

    def test_alarm_zone_object_must_be_tracked(self) -> None:
        config = _config_with_valid_alarm_zone(objects=["dog"])
        self.assertRaises(ValidationError, lambda: FrigateConfig(**config))

    def test_camera_alarm_requires_global_alarm_enabled(self) -> None:
        config = _minimal(
            camera_overrides={
                "zones": {"driveway": DRIVEWAY_ZONE},
                "alarm": {
                    "enabled": True,
                    "zones": {"driveway": {"objects": ["person"]}},
                },
            },
        )
        self.assertRaises(ValidationError, lambda: FrigateConfig(**config))


class TestBuildRules(unittest.TestCase):
    def setUp(self) -> None:
        if not os.path.exists(MODEL_CACHE_DIR) and not os.path.islink(MODEL_CACHE_DIR):
            os.makedirs(MODEL_CACHE_DIR)

    def test_build_rules_produces_expected_mapping(self) -> None:
        config = FrigateConfig(**_config_with_valid_alarm_zone())
        rules = config.cameras["back"].alarm.build_rules("back")
        self.assertIn(("back", "driveway"), rules)

    def test_build_rules_empty_when_camera_alarm_disabled(self) -> None:
        config_dict = _minimal(
            camera_overrides={"zones": {"driveway": DRIVEWAY_ZONE}},
            global_alarm={"enabled": True},
        )
        config = FrigateConfig(**config_dict)
        self.assertEqual(config.cameras["back"].alarm.build_rules("back"), {})


class TestReportingConfig(unittest.TestCase):
    def setUp(self) -> None:
        if not os.path.exists(MODEL_CACHE_DIR) and not os.path.islink(MODEL_CACHE_DIR):
            os.makedirs(MODEL_CACHE_DIR)

    def test_reporting_disabled_by_default(self) -> None:
        config = FrigateConfig(**_minimal(global_alarm={"enabled": True}))
        self.assertEqual(config.alarm.reporting.protocol, "none")

    def test_reporting_requires_receiver_details_when_enabled(self) -> None:
        config_dict = _minimal(
            global_alarm={
                "enabled": True,
                "reporting": {"protocol": "contact_id"},
            }
        )
        self.assertRaises(ValidationError, lambda: FrigateConfig(**config_dict))

    def test_reporting_valid_with_receiver_details(self) -> None:
        config = FrigateConfig(
            **_minimal(
                global_alarm={
                    "enabled": True,
                    "reporting": {
                        "protocol": "contact_id",
                        "host": "monitoring.example.com",
                        "port": 4025,
                        "account": "1234",
                    },
                }
            )
        )
        self.assertEqual(config.alarm.reporting.host, "monitoring.example.com")


if __name__ == "__main__":
    unittest.main()
