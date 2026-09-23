"""Tests for EventZone/ReviewSegmentZone: the join-table sync pattern
(insert_many + on_conflict_ignore, upsert-safe since zones only ever get
added, never removed) and the migration's json_each() backfill SQL.

Needs frigate.models (peewee), which needs frigate.config's cv2 chain to
import; run inside the real container, same tier as test_alarm_config.py.
Binds models to a fresh in-memory sqlite database per test rather than
going through the full migration runner for the model-level tests, but
the backfill test runs the actual migration SQL (copied inline rather
than imported, since migration modules aren't meant to be imported as
library code -- peewee_migrate loads them by path) against hand-built
rows to prove the json_each() approach actually works against Event's
real "zones" JSON list shape and ReviewSegment's real "data" JSON object
shape, not just a plausible-looking guess.
"""

import unittest

from peewee import SqliteDatabase

from frigate.models import Event, EventZone, ReviewSegment, ReviewSegmentZone

test_db = SqliteDatabase(":memory:")

_MODELS = [Event, EventZone, ReviewSegment, ReviewSegmentZone]

# Mirrors the INSERT ... SELECT ... json_each(...) statements in
# migrations/041_create_zone_join_tables.py exactly -- kept here as a
# literal copy (not imported) since peewee_migrate migration files are
# loaded by the migration runner, not meant to be imported as a module.
_BACKFILL_EVENT_ZONES_SQL = """
    INSERT OR IGNORE INTO "eventzone" ("event_id", "zone")
    SELECT "event"."id", "je"."value"
    FROM "event", json_each("event"."zones") AS "je"
    WHERE json_valid("event"."zones")
      AND json_type("event"."zones") = 'array'
"""

_BACKFILL_REVIEW_ZONES_SQL = """
    INSERT OR IGNORE INTO "reviewsegmentzone" ("review_segment_id", "zone")
    SELECT "reviewsegment"."id", "je"."value"
    FROM "reviewsegment", json_each("reviewsegment"."data", '$.zones') AS "je"
    WHERE json_valid("reviewsegment"."data")
      AND json_extract("reviewsegment"."data", '$.zones') IS NOT NULL
"""


def _minimal_event(id: str, zones: list) -> dict:
    return dict(
        id=id,
        label="person",
        camera="front",
        start_time=1_700_000_000.0,
        end_time=1_700_000_010.0,
        top_score=0.9,
        score=0.9,
        false_positive=False,
        zones=zones,
        thumbnail="",
        has_clip=True,
        has_snapshot=True,
        region=[],
        box=[],
        area=0,
        retain_indefinitely=False,
        ratio=1.0,
        plus_id="",
        model_hash="",
        detector_type="",
        model_type="",
        data={},
    )


def _minimal_review(id: str, zones: list) -> dict:
    return dict(
        id=id,
        camera="front",
        start_time=1_700_000_000.0,
        end_time=1_700_000_010.0,
        severity="alert",
        thumb_path=f"thumb-{id}",
        data={"zones": zones},
    )


class BaseZoneTableTest(unittest.TestCase):
    def setUp(self) -> None:
        test_db.bind(_MODELS, bind_refs=False, bind_backrefs=False)
        test_db.connect()
        test_db.create_tables(_MODELS)

    def tearDown(self) -> None:
        test_db.drop_tables(_MODELS)
        test_db.close()


class TestEventZoneUpsertSync(BaseZoneTableTest):
    def test_insert_many_populates_one_row_per_zone(self) -> None:
        Event.create(**_minimal_event("evt1", ["driveway", "yard"]))
        (
            EventZone.insert_many(
                [{"event": "evt1", "zone": z} for z in ["driveway", "yard"]]
            )
            .on_conflict_ignore()
            .execute()
        )

        zones = {r.zone for r in EventZone.select().where(EventZone.event == "evt1")}
        self.assertEqual(zones, {"driveway", "yard"})

    def test_re_upserting_the_same_zone_is_a_safe_no_op(self) -> None:
        """Matches real usage: the same Event row gets upserted repeatedly
        as a tracked object moves through the scene, so the same zone
        can be "added" again on a later call."""
        Event.create(**_minimal_event("evt1", ["driveway"]))
        for _ in range(3):
            (
                EventZone.insert_many([{"event": "evt1", "zone": "driveway"}])
                .on_conflict_ignore()
                .execute()
            )

        self.assertEqual(EventZone.select().where(EventZone.event == "evt1").count(), 1)

    def test_a_new_zone_added_later_is_additive(self) -> None:
        Event.create(**_minimal_event("evt1", ["driveway"]))
        EventZone.insert_many(
            [{"event": "evt1", "zone": "driveway"}]
        ).on_conflict_ignore().execute()

        # object continues moving, entered a second zone
        EventZone.insert_many(
            [{"event": "evt1", "zone": "driveway"}, {"event": "evt1", "zone": "yard"}]
        ).on_conflict_ignore().execute()

        zones = {r.zone for r in EventZone.select().where(EventZone.event == "evt1")}
        self.assertEqual(zones, {"driveway", "yard"})


class TestBackfillSql(BaseZoneTableTest):
    def test_event_zones_backfilled_from_existing_json(self) -> None:
        Event.create(**_minimal_event("evt1", ["driveway", "yard"]))
        Event.create(**_minimal_event("evt2", []))
        Event.create(**_minimal_event("evt3", ["driveway"]))

        test_db.execute_sql(_BACKFILL_EVENT_ZONES_SQL)

        self.assertEqual(
            {r.zone for r in EventZone.select().where(EventZone.event == "evt1")},
            {"driveway", "yard"},
        )
        self.assertEqual(EventZone.select().where(EventZone.event == "evt2").count(), 0)
        self.assertEqual(
            {r.zone for r in EventZone.select().where(EventZone.event == "evt3")},
            {"driveway"},
        )

    def test_review_segment_zones_backfilled_from_existing_json(self) -> None:
        ReviewSegment.create(**_minimal_review("rev1", ["driveway", "porch"]))
        ReviewSegment.create(**_minimal_review("rev2", []))

        test_db.execute_sql(_BACKFILL_REVIEW_ZONES_SQL)

        self.assertEqual(
            {
                r.zone
                for r in ReviewSegmentZone.select().where(
                    ReviewSegmentZone.review_segment == "rev1"
                )
            },
            {"driveway", "porch"},
        )
        self.assertEqual(
            ReviewSegmentZone.select()
            .where(ReviewSegmentZone.review_segment == "rev2")
            .count(),
            0,
        )

    def test_backfill_is_idempotent(self) -> None:
        """The migration uses INSERT OR IGNORE against the unique
        (event_id, zone) index -- running it twice must not duplicate or
        error, in case a migration is ever re-run against a partially
        migrated database."""
        Event.create(**_minimal_event("evt1", ["driveway"]))

        test_db.execute_sql(_BACKFILL_EVENT_ZONES_SQL)
        test_db.execute_sql(_BACKFILL_EVENT_ZONES_SQL)

        self.assertEqual(EventZone.select().where(EventZone.event == "evt1").count(), 1)


class TestCleanupRemovesOrphans(BaseZoneTableTest):
    def test_deleting_event_removes_its_zone_rows(self) -> None:
        """Mirrors the explicit-delete pattern used in
        frigate/events/cleanup.py and frigate/util/camera_cleanup.py --
        there is no FK cascade in effect (sqlite foreign_keys pragma
        isn't enabled in this app), so this must be done explicitly."""
        Event.create(**_minimal_event("evt1", ["driveway"]))
        Event.create(**_minimal_event("evt2", ["yard"]))
        EventZone.insert_many(
            [{"event": "evt1", "zone": "driveway"}, {"event": "evt2", "zone": "yard"}]
        ).on_conflict_ignore().execute()

        chunk = ["evt1"]
        Event.delete().where(Event.id << chunk).execute()
        EventZone.delete().where(EventZone.event << chunk).execute()

        self.assertEqual(EventZone.select().where(EventZone.event == "evt1").count(), 0)
        self.assertEqual(EventZone.select().where(EventZone.event == "evt2").count(), 1)

    def test_camera_wide_delete_removes_zone_rows_via_subquery(self) -> None:
        """Mirrors frigate/util/camera_cleanup.py's subquery-based delete
        (camera isn't a column on EventZone itself, so it has to look up
        which events belong to that camera first)."""
        Event.create(**_minimal_event("evt1", ["driveway"]))
        e2 = _minimal_event("evt2", ["yard"])
        e2["camera"] = "back"
        Event.create(**e2)
        EventZone.insert_many(
            [{"event": "evt1", "zone": "driveway"}, {"event": "evt2", "zone": "yard"}]
        ).on_conflict_ignore().execute()

        EventZone.delete().where(
            EventZone.event.in_(Event.select(Event.id).where(Event.camera == "front"))
        ).execute()
        Event.delete().where(Event.camera == "front").execute()

        self.assertEqual(EventZone.select().where(EventZone.event == "evt1").count(), 0)
        self.assertEqual(EventZone.select().where(EventZone.event == "evt2").count(), 1)


if __name__ == "__main__":
    unittest.main()
