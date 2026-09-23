"""Tests for the alarm API endpoints.

Like the rest of frigate/test/http_api/, this needs fastapi/peewee/etc.
installed to even import; it could not be executed in the dev sandbox this
was written in (see AGENTS.md). Written to match existing http_api test
conventions (BaseTestHttp, AuthTestClient) precisely; run it in a full
dev/CI environment before trusting it.
"""

import time
from datetime import datetime, timedelta
from unittest.mock import Mock

from frigate.alarm.event import AlarmEvent, AlarmEventType
from frigate.alarm.rules import ZoneAlarmRule
from frigate.alarm.system import AlarmSystem
from frigate.models import AlarmAuditLog, AlarmEventLog, Event
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
                object_id="1700000000.123456-abc123",
            )
        )
        self.app.alarm_system = system
        with AuthTestClient(self.app) as client:
            response = client.get("/alarm/events")
            self.assertEqual(response.status_code, 200)
            events = response.json()
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["camera_id"], "front")
            self.assertEqual(events[0]["object_id"], "1700000000.123456-abc123")


class TestAlarmArmDisarmClear(BaseTestHttp):
    def setUp(self):
        super().setUp([AlarmAuditLog])
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

    def test_arm_writes_audit_entry(self):
        with AuthTestClient(self.app) as client:
            client.post(
                "/alarm/arm",
                json={"mode": "away", "exit_delay_seconds": 0},
                headers={"remote-user": "raine"},
            )
            entry = AlarmAuditLog.get()
            self.assertEqual(entry.action, "arm")
            self.assertEqual(entry.source, "api")
            self.assertEqual(entry.actor, "raine")
            self.assertEqual(entry.details, {"mode": "away"})

    def test_rejected_arm_writes_no_audit_entry(self):
        with AuthTestClient(self.app) as client:
            client.post("/alarm/arm", json={"mode": "away", "exit_delay_seconds": 0})
            client.post("/alarm/arm", json={"mode": "home", "exit_delay_seconds": 0})
            self.assertEqual(
                AlarmAuditLog.select().where(AlarmAuditLog.action == "arm").count(),
                1,
            )

    def test_arm_rejects_double_arm(self):
        with AuthTestClient(self.app) as client:
            client.post("/alarm/arm", json={"mode": "away", "exit_delay_seconds": 0})
            response = client.post(
                "/alarm/arm", json={"mode": "home", "exit_delay_seconds": 0}
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

    def test_disarm_writes_audit_entry(self):
        with AuthTestClient(self.app) as client:
            client.post("/alarm/arm", json={"mode": "away", "exit_delay_seconds": 0})
            client.post("/alarm/disarm", headers={"remote-user": "raine"})
            entry = AlarmAuditLog.select().where(AlarmAuditLog.action == "disarm").get()
            self.assertEqual(entry.actor, "raine")

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


class TestAlarmZoneBypass(BaseTestHttp):
    def setUp(self):
        super().setUp([AlarmAuditLog])
        self.app = super().create_app()
        self.app.alarm_system = _alarm_system()

    def test_bypass_zone(self):
        with AuthTestClient(self.app) as client:
            response = client.post(
                "/alarm/zones/front/driveway/bypass", json={"bypassed": True}
            )
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json()["success"])
            self.assertTrue(self.app.alarm_system.is_bypassed("front", "driveway"))

    def test_bypass_zone_writes_audit_entry(self):
        with AuthTestClient(self.app) as client:
            client.post(
                "/alarm/zones/front/driveway/bypass",
                json={"bypassed": True},
                headers={"remote-user": "raine"},
            )
            entry = AlarmAuditLog.get()
            self.assertEqual(entry.action, "bypass")
            self.assertEqual(entry.camera, "front")
            self.assertEqual(entry.zone, "driveway")
            self.assertEqual(entry.actor, "raine")

    def test_unbypass_zone(self):
        self.app.alarm_system.bypass_zone("front", "driveway")
        with AuthTestClient(self.app) as client:
            response = client.post(
                "/alarm/zones/front/driveway/bypass", json={"bypassed": False}
            )
            self.assertEqual(response.status_code, 200)
            self.assertFalse(self.app.alarm_system.is_bypassed("front", "driveway"))

    def test_bypass_unknown_zone_returns_404(self):
        with AuthTestClient(self.app) as client:
            response = client.post(
                "/alarm/zones/front/nonexistent/bypass", json={"bypassed": True}
            )
            self.assertEqual(response.status_code, 404)
            self.assertFalse(response.json()["success"])

    def test_bypass_requires_admin_role(self):
        with AuthTestClient(self.app) as client:
            response = client.post(
                "/alarm/zones/front/driveway/bypass",
                json={"bypassed": True},
                headers={"remote-user": "viewer", "remote-role": "viewer"},
            )
            self.assertEqual(response.status_code, 403)

    def test_bypass_when_alarm_disabled(self):
        self.app.alarm_system = None
        with AuthTestClient(self.app) as client:
            response = client.post(
                "/alarm/zones/front/driveway/bypass", json={"bypassed": True}
            )
            self.assertEqual(response.status_code, 400)
            self.assertFalse(response.json()["success"])

    def test_status_reflects_bypass(self):
        self.app.alarm_system.bypass_zone("front", "driveway")
        with AuthTestClient(self.app) as client:
            response = client.get("/alarm/status")
            zone = response.json()["zones"][0]
            self.assertTrue(zone["bypassed"])
            self.assertFalse(zone["armed"])


class TestAlarmAuditLog(BaseTestHttp):
    def setUp(self):
        super().setUp([AlarmAuditLog])
        self.app = super().create_app()
        self.app.alarm_system = _alarm_system()

    def test_audit_log_when_alarm_disabled(self):
        self.app.alarm_system = None
        with AuthTestClient(self.app) as client:
            response = client.get("/alarm/audit")
            self.assertEqual(response.status_code, 400)

    def test_audit_log_empty_by_default(self):
        with AuthTestClient(self.app) as client:
            response = client.get("/alarm/audit")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), [])

    def test_audit_log_reflects_real_actions_newest_first(self):
        with AuthTestClient(self.app) as client:
            client.post(
                "/alarm/arm",
                json={"mode": "away", "exit_delay_seconds": 0},
                headers={"remote-user": "raine"},
            )
            client.post("/alarm/disarm", headers={"remote-user": "raine"})

            response = client.get("/alarm/audit")
            entries = response.json()
            self.assertEqual(len(entries), 2)
            self.assertEqual(entries[0]["action"], "disarm")
            self.assertEqual(entries[1]["action"], "arm")
            self.assertEqual(entries[1]["details"], {"mode": "away"})
            # Regression guard for the naive-UTC-vs-local-time bug caught
            # live: the API's timestamp conversion must match wall-clock
            # "now" regardless of the container's local timezone, not be
            # off by a fixed UTC-offset amount.
            self.assertAlmostEqual(entries[0]["timestamp"], time.time(), delta=5)

    def test_audit_log_allows_viewer_role(self):
        with AuthTestClient(self.app) as client:
            response = client.get(
                "/alarm/audit",
                headers={"remote-user": "viewer", "remote-role": "viewer"},
            )
            self.assertEqual(response.status_code, 200)


class TestAlarmEventLog(BaseTestHttp):
    def setUp(self):
        super().setUp([AlarmEventLog, AlarmAuditLog])
        self.app = super().create_app()
        self.app.alarm_system = _alarm_system()

    def test_event_log_when_alarm_disabled(self):
        self.app.alarm_system = None
        with AuthTestClient(self.app) as client:
            response = client.get("/alarm/event_log")
            self.assertEqual(response.status_code, 400)

    def test_event_log_empty_by_default(self):
        with AuthTestClient(self.app) as client:
            response = client.get("/alarm/event_log")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), [])

    def test_event_log_lists_persisted_events_newest_first(self):
        AlarmEventLog.create(
            timestamp="2026-01-01 10:00:00",
            event_type="burglary",
            camera="front",
            zone="driveway",
            object_type="person",
            confidence=0.9,
            source="detection",
        )
        AlarmEventLog.create(
            timestamp="2026-01-02 10:00:00",
            event_type="tamper",
            camera="back",
            source="detection",
        )
        with AuthTestClient(self.app) as client:
            response = client.get("/alarm/event_log")
            entries = response.json()
            self.assertEqual(len(entries), 2)
            self.assertEqual(entries[0]["camera"], "back")
            self.assertEqual(entries[1]["camera"], "front")
            self.assertFalse(entries[1]["false_alarm"])

    def test_event_log_filters_by_camera(self):
        AlarmEventLog.create(
            timestamp="2026-01-01 10:00:00",
            event_type="burglary",
            camera="front",
            source="detection",
        )
        AlarmEventLog.create(
            timestamp="2026-01-01 10:00:00",
            event_type="burglary",
            camera="back",
            source="detection",
        )
        with AuthTestClient(self.app) as client:
            response = client.get("/alarm/event_log", params={"camera": "front"})
            entries = response.json()
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["camera"], "front")

    def test_false_alarm_toggle_requires_admin(self):
        entry = AlarmEventLog.create(
            timestamp="2026-01-01 10:00:00",
            event_type="burglary",
            camera="front",
            source="detection",
        )
        with AuthTestClient(self.app) as client:
            response = client.post(
                f"/alarm/event_log/{entry.id}/false_alarm",
                json={"false_alarm": True},
                headers={"remote-user": "viewer", "remote-role": "viewer"},
            )
            self.assertEqual(response.status_code, 403)

    def test_false_alarm_toggle_marks_and_unmarks(self):
        entry = AlarmEventLog.create(
            timestamp="2026-01-01 10:00:00",
            event_type="burglary",
            camera="front",
            source="detection",
        )
        with AuthTestClient(self.app) as client:
            response = client.post(
                f"/alarm/event_log/{entry.id}/false_alarm",
                json={"false_alarm": True},
                headers={"remote-user": "raine"},
            )
            self.assertEqual(response.status_code, 200)
            self.assertTrue(AlarmEventLog.get_by_id(entry.id).false_alarm)

            response = client.post(
                f"/alarm/event_log/{entry.id}/false_alarm",
                json={"false_alarm": False},
                headers={"remote-user": "raine"},
            )
            self.assertEqual(response.status_code, 200)
            self.assertFalse(AlarmEventLog.get_by_id(entry.id).false_alarm)

    def test_false_alarm_toggle_records_audit_entry(self):
        entry = AlarmEventLog.create(
            timestamp="2026-01-01 10:00:00",
            event_type="burglary",
            camera="front",
            source="detection",
        )
        with AuthTestClient(self.app) as client:
            client.post(
                f"/alarm/event_log/{entry.id}/false_alarm",
                json={"false_alarm": True},
                headers={"remote-user": "raine"},
            )
            audit_entry = AlarmAuditLog.get()
            self.assertEqual(audit_entry.action, "false_alarm")
            self.assertEqual(audit_entry.details["event_log_id"], entry.id)

    def test_false_alarm_toggle_unknown_id_is_404(self):
        with AuthTestClient(self.app) as client:
            response = client.post(
                "/alarm/event_log/99999/false_alarm",
                json={"false_alarm": True},
                headers={"remote-user": "raine"},
            )
            self.assertEqual(response.status_code, 404)

    def test_summary_empty_by_default(self):
        with AuthTestClient(self.app) as client:
            response = client.get("/alarm/event_log/summary")
            self.assertEqual(response.status_code, 200)
            body = response.json()
            self.assertEqual(body["total"], 0)
            self.assertIsNone(body["false_alarm_rate"])
            self.assertEqual(body["daily"], [])

    def test_summary_computes_rate_and_daily_breakdown(self):
        today = datetime.now().replace(hour=10, minute=0, second=0, microsecond=0)
        yesterday = today - timedelta(days=1)
        AlarmEventLog.create(
            timestamp=yesterday,
            event_type="burglary",
            camera="front",
            source="detection",
            false_alarm=True,
        )
        AlarmEventLog.create(
            timestamp=yesterday + timedelta(hours=2),
            event_type="burglary",
            camera="front",
            source="detection",
            false_alarm=False,
        )
        AlarmEventLog.create(
            timestamp=today,
            event_type="burglary",
            camera="front",
            source="detection",
            false_alarm=False,
        )
        with AuthTestClient(self.app) as client:
            response = client.get("/alarm/event_log/summary", params={"days": 7})
            body = response.json()
            self.assertEqual(body["total"], 3)
            self.assertEqual(body["false_alarm_count"], 1)
            self.assertAlmostEqual(body["false_alarm_rate"], 1 / 3)
            self.assertEqual(len(body["daily"]), 2)
            yesterday_bucket = next(
                d for d in body["daily"] if d["date"] == yesterday.date().isoformat()
            )
            self.assertEqual(yesterday_bucket["total"], 2)
            self.assertEqual(yesterday_bucket["false_alarm_count"], 1)


class TestAlarmTrail(BaseTestHttp):
    def setUp(self):
        super().setUp([Event])
        self.app = super().create_app()
        self.app.alarm_system = _alarm_system()

    def test_trail_when_alarm_disabled(self):
        self.app.alarm_system = None
        with AuthTestClient(self.app) as client:
            response = client.get("/alarm/trail/some-id")
            self.assertEqual(response.status_code, 400)

    def test_trail_for_unknown_event_id_is_empty(self):
        with AuthTestClient(self.app) as client:
            response = client.get("/alarm/trail/missing")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["matches"], [])

    def test_trail_returns_named_match_from_another_camera(self):
        now = datetime.now().timestamp()
        super().insert_mock_event("trigger", start_time=now, camera="front_door")
        super().insert_mock_event("match", start_time=now + 30, camera="back_door")
        Event.update(sub_label="raine").where(
            Event.id << ["trigger", "match"]
        ).execute()

        with AuthTestClient(self.app) as client:
            response = client.get("/alarm/trail/trigger")
            self.assertEqual(response.status_code, 200)
            matches = response.json()["matches"]
            self.assertEqual(len(matches), 1)
            self.assertEqual(matches[0]["event_id"], "match")
            self.assertEqual(matches[0]["camera"], "back_door")
            self.assertEqual(matches[0]["match_type"], "named")
            self.assertEqual(matches[0]["label"], "raine")

    def test_trail_returns_visual_match_when_semantic_search_enabled(self):
        now = datetime.now().timestamp()
        super().insert_mock_event("trigger", start_time=now, camera="front_door")
        super().insert_mock_event("candidate", start_time=now + 30, camera="back_door")

        mock_embeddings = Mock()
        mock_embeddings.search_thumbnail.return_value = [("candidate", 0.1)]
        self.app.embeddings = mock_embeddings

        with AuthTestClient(self.app) as client:
            response = client.get("/alarm/trail/trigger")
            self.assertEqual(response.status_code, 200)
            matches = response.json()["matches"]
            self.assertEqual(len(matches), 1)
            self.assertEqual(matches[0]["event_id"], "candidate")
            self.assertEqual(matches[0]["match_type"], "visual")
            self.assertAlmostEqual(matches[0]["score"], 0.1)

    def test_trail_respects_window_seconds_param(self):
        now = datetime.now().timestamp()
        super().insert_mock_event("trigger", start_time=now, camera="front_door")
        super().insert_mock_event("too_far", start_time=now + 500, camera="back_door")
        Event.update(sub_label="raine").where(
            Event.id << ["trigger", "too_far"]
        ).execute()

        with AuthTestClient(self.app) as client:
            response = client.get("/alarm/trail/trigger", params={"window_seconds": 60})
            self.assertEqual(response.json()["matches"], [])


if __name__ == "__main__":
    import unittest

    unittest.main()
