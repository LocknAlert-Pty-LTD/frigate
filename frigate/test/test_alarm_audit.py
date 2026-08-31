"""Tests for the operator-action audit log.

Needs frigate.models (peewee), which needs frigate.config's cv2 chain to
import (same gap as test_alarm_config.py); run inside the real container.
Binds AlarmAuditLog to a fresh in-memory sqlite database per test rather
than going through the full migration runner -- this is testing the ORM
shape record_alarm_audit() writes, not migration history.
"""

import unittest
from datetime import UTC, datetime, timedelta

from peewee import SqliteDatabase

from frigate.alarm.audit import record_alarm_audit
from frigate.models import AlarmAuditLog

test_db = SqliteDatabase(":memory:")


class TestRecordAlarmAudit(unittest.TestCase):
    def setUp(self) -> None:
        AlarmAuditLog.bind(test_db, bind_refs=False, bind_backrefs=False)
        test_db.connect()
        test_db.create_tables([AlarmAuditLog])

    def tearDown(self) -> None:
        test_db.drop_tables([AlarmAuditLog])
        test_db.close()

    def test_records_a_basic_action(self) -> None:
        record_alarm_audit("disarm", "api", actor="admin")

        entries = list(AlarmAuditLog.select())
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].action, "disarm")
        self.assertEqual(entries[0].source, "api")
        self.assertEqual(entries[0].actor, "admin")
        self.assertIsNone(entries[0].camera)
        self.assertIsNone(entries[0].zone)
        self.assertIsNone(entries[0].details)

    def test_mqtt_action_has_no_actor(self) -> None:
        record_alarm_audit("arm", "mqtt", details={"mode": "away"})

        entry = AlarmAuditLog.get()
        self.assertEqual(entry.source, "mqtt")
        self.assertIsNone(entry.actor)
        self.assertEqual(entry.details, {"mode": "away"})

    def test_bypass_action_carries_camera_and_zone(self) -> None:
        record_alarm_audit(
            "bypass", "api", actor="admin", camera="front", zone="driveway"
        )

        entry = AlarmAuditLog.get()
        self.assertEqual(entry.camera, "front")
        self.assertEqual(entry.zone, "driveway")

    def test_timestamp_round_trips_as_a_real_datetime_close_to_now(self) -> None:
        """Regression guard: a tz-aware datetime.now(UTC) stores with a
        "+00:00" suffix that peewee's DateTimeField can't parse back out
        (see audit.py) -- reads would silently come back as a raw str
        instead of a datetime, which .replace(tzinfo=UTC) below would
        raise AttributeError on immediately, catching a regression here
        rather than only when GET /alarm/audit runs against a real
        non-UTC-local container (which is what actually caught this)."""
        before = datetime.now(UTC).replace(tzinfo=None)

        record_alarm_audit("clear", "api")

        entry = AlarmAuditLog.get()
        after = datetime.now(UTC).replace(tzinfo=None)
        self.assertIsInstance(entry.timestamp, datetime)
        self.assertLessEqual(before - timedelta(seconds=1), entry.timestamp)
        self.assertLessEqual(entry.timestamp, after + timedelta(seconds=1))

    def test_multiple_actions_are_all_recorded_independently(self) -> None:
        record_alarm_audit("arm", "api", actor="admin", details={"mode": "away"})
        record_alarm_audit("disarm", "api", actor="admin")
        record_alarm_audit("bypass", "api", actor="admin", camera="front", zone="yard")

        entries = list(AlarmAuditLog.select().order_by(AlarmAuditLog.id))
        self.assertEqual([e.action for e in entries], ["arm", "disarm", "bypass"])


if __name__ == "__main__":
    unittest.main()
