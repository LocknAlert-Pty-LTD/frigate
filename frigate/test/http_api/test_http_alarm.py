"""Tests for the alarm API endpoints.

Like the rest of frigate/test/http_api/, this needs fastapi/peewee/etc.
installed to even import; it could not be executed in the dev sandbox this
was written in (see AGENTS.md). Written to match existing http_api test
conventions (BaseTestHttp, AuthTestClient) precisely; run it in a full
dev/CI environment before trusting it.
"""

from frigate.alarm.event import AlarmEvent, AlarmEventType
from frigate.alarm.rules import ZoneAlarmRule
from frigate.alarm.system import AlarmSystem
from frigate.test.http_api.base_http_test import AuthTestClient, BaseTestHttp


def _alarm_system(**overrides) -> AlarmSystem:
    rule = ZoneAlarmRule(camera="front", zone="driveway", objects=frozenset({"person"}))
    system = AlarmSystem({("front", "driveway"): rule}, **overrides)
    return system


class TestAlarmStatus(BaseTestHttp):
    def setUp(self):
        super().setUp([])
        self.app = super().create_app()

    def test_status_when_alarm_disabled(self):
        self.app.alarm_system = None
        with AuthTestClient(self.app) as client:
            response = client.get("/alarm/status")
            self.assertEqual(response.status_code, 400)
            self.assertFalse(response.json()["success"])

    def test_status_when_enabled(self):
        self.app.alarm_system = _alarm_system()
        with AuthTestClient(self.app) as client:
            response = client.get("/alarm/status")
            self.assertEqual(response.status_code, 200)
            body = response.json()
            self.assertEqual(body["state"], "disarmed")
            self.assertIsNone(body["armed_mode"])
            self.assertEqual(len(body["zones"]), 1)


class TestAlarmEvents(BaseTestHttp):
    def setUp(self):
        super().setUp([])
        self.app = super().create_app()

    def test_events_returns_recorded_events(self):
        system = _alarm_system()
        system.record_event(
            AlarmEvent(
                event_type=AlarmEventType.burglary,
                camera_id="front",
                timestamp=1_700_000_000.0,
                zone_id="driveway",
            )
        )
        self.app.alarm_system = system
        with AuthTestClient(self.app) as client:
            response = client.get("/alarm/events")
            self.assertEqual(response.status_code, 200)
            events = response.json()
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["camera_id"], "front")


class TestAlarmArmDisarmClear(BaseTestHttp):
    def setUp(self):
        super().setUp([])
        self.app = super().create_app()
        self.app.alarm_system = _alarm_system()

    def test_arm_away(self):
        with AuthTestClient(self.app) as client:
            response = client.post(
                "/alarm/arm", json={"mode": "away", "exit_delay_seconds": 0}
            )
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json()["success"])
            self.assertEqual(
                self.app.alarm_system.state_machine.state.value, "armed_away"
            )

    def test_arm_rejects_double_arm(self):
        with AuthTestClient(self.app) as client:
            client.post("/alarm/arm", json={"mode": "away", "exit_delay_seconds": 0})
            response = client.post(
                "/alarm/arm", json={"mode": "stay", "exit_delay_seconds": 0}
            )
            self.assertEqual(response.status_code, 400)
            self.assertFalse(response.json()["success"])

    def test_disarm(self):
        with AuthTestClient(self.app) as client:
            client.post("/alarm/arm", json={"mode": "away", "exit_delay_seconds": 0})
            response = client.post("/alarm/disarm")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                self.app.alarm_system.state_machine.state.value, "disarmed"
            )

    def test_arm_requires_admin_role(self):
        with AuthTestClient(self.app) as client:
            response = client.post(
                "/alarm/arm",
                json={"mode": "away", "exit_delay_seconds": 0},
                headers={"remote-user": "viewer", "remote-role": "viewer"},
            )
            self.assertEqual(response.status_code, 403)

    def test_status_endpoint_allows_viewer_role(self):
        with AuthTestClient(self.app) as client:
            response = client.get(
                "/alarm/status",
                headers={"remote-user": "viewer", "remote-role": "viewer"},
            )
            self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    import unittest

    unittest.main()
