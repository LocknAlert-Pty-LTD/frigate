"""Tests for the persisted alarm event log.

Needs frigate.models (peewee), which needs frigate.config's cv2 chain to
import (same gap as test_alarm_config.py); run inside the real container.
Binds AlarmEventLog to a fresh in-memory sqlite database per test rather
than going through the full migration runner -- this is testing the ORM
shape record_alarm_event_log() writes, not migration history. Mirrors
test_alarm_audit.py's exact structure.
"""

import unittest
from datetime import UTC, datetime, timedelta

from peewee import SqliteDatabase

from frigate.alarm.event import AlarmEvent, AlarmEventType
from frigate.alarm.event_log import record_alarm_event_log
from frigate.models import AlarmEventLog

test_db = SqliteDatabase(":memory:")


def _event(**overrides) -> AlarmEvent:
    defaults = dict(
        event_type=AlarmEventType.burglary,
        camera_id="front",
        timestamp=1_700_000_000.0,
        zone_id="driveway",
        object_type="person",
        confidence=0.87,
    )
    defaults.update(overrides)
    return AlarmEvent(**defaults)


class TestRecordAlarmEventLog(unittest.TestCase):
    def setUp(self) -> None:
        AlarmEventLog.bind(test_db, bind_refs=False, bind_backrefs=False)
        test_db.connect()
        test_db.create_tables([AlarmEventLog])

    def tearDown(self) -> None:
        test_db.drop_tables([AlarmEventLog])
        test_db.close()

    def test_records_a_basic_event(self) -> None:
        record_alarm_event_log(_event())

        entries = list(AlarmEventLog.select())
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].event_type, "burglary")
        self.assertEqual(entries[0].camera, "front")
        self.assertEqual(entries[0].zone, "driveway")
        self.assertEqual(entries[0].object_type, "person")
        self.assertEqual(entries[0].confidence, 0.87)
        self.assertFalse(entries[0].false_alarm)

    def test_defaults_false_alarm_to_false(self) -> None:
        record_alarm_event_log(_event())
        self.assertFalse(AlarmEventLog.get().false_alarm)

    def test_handles_missing_zone_and_confidence(self) -> None:
        record_alarm_event_log(_event(zone_id=None, object_type=None, confidence=None))

        entry = AlarmEventLog.get()
        self.assertIsNone(entry.zone)
        self.assertIsNone(entry.object_type)
        self.assertIsNone(entry.confidence)

    def test_timestamp_round_trips_as_a_real_datetime_close_to_now(self) -> None:
        """Regression guard: same tz-aware-datetime pitfall test_alarm_audit.py
        guards against -- a tz-aware datetime.now(UTC) stores with a "+00:00"
        suffix peewee's DateTimeField can't parse back out."""
        before = datetime.now(UTC).replace(tzinfo=None)

        record_alarm_event_log(_event())

        entry = AlarmEventLog.get()
        after = datetime.now(UTC).replace(tzinfo=None)
        self.assertIsInstance(entry.timestamp, datetime)
        self.assertLessEqual(before - timedelta(seconds=1), entry.timestamp)
        self.assertLessEqual(entry.timestamp, after + timedelta(seconds=1))

    def test_multiple_events_are_all_recorded_independently(self) -> None:
        record_alarm_event_log(_event(camera_id="front"))
        record_alarm_event_log(_event(camera_id="back"))
        record_alarm_event_log(_event(camera_id="side"))

        entries = list(AlarmEventLog.select().order_by(AlarmEventLog.id))
        self.assertEqual([e.camera for e in entries], ["front", "back", "side"])

    def test_false_alarm_can_be_toggled_after_the_fact(self) -> None:
        record_alarm_event_log(_event())

        entry = AlarmEventLog.get()
        entry.false_alarm = True
        entry.save()

        self.assertTrue(AlarmEventLog.get().false_alarm)

    def test_records_object_id_for_trail_lookup(self) -> None:
        record_alarm_event_log(_event(object_id="1700000000.123456-abc123"))

        self.assertEqual(AlarmEventLog.get().object_id, "1700000000.123456-abc123")

    def test_object_id_defaults_to_none(self) -> None:
        """Non-detection alarm events (arm/disarm/fault/etc) never carry an
        object_id -- must stay nullable, not required."""
        record_alarm_event_log(_event())

        self.assertIsNone(AlarmEventLog.get().object_id)


if __name__ == "__main__":
    unittest.main()
