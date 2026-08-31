"""Tests for the cross-camera trail lookup (frigate/alarm/trail.py).

Needs frigate.models (peewee), same gap as test_alarm_event_log.py; run
inside the real container. Binds Event to a fresh in-memory sqlite database
per test, same approach as test_alarm_event_log.py -- this is testing
find_trail()'s query logic, not migration history.
"""

import unittest
from unittest.mock import Mock

from peewee import SqliteDatabase

from frigate.alarm.trail import find_trail
from frigate.models import Event

test_db = SqliteDatabase(":memory:")

BASE_TIME = 1_700_000_000.0


def _event(id: str, **overrides) -> Event:
    defaults = dict(
        id=id,
        label="person",
        sub_label=None,
        camera="front",
        start_time=BASE_TIME,
        end_time=BASE_TIME + 10,
        top_score=0.9,
        score=0.9,
        false_positive=False,
        zones=[],
        thumbnail="thumb.jpg",
        region=[],
        box=[],
        area=0,
        plus_id="",
        model_hash="",
        detector_type="",
        model_type="",
        data={},
    )
    defaults.update(overrides)
    return Event.create(**defaults)


class TestFindTrail(unittest.TestCase):
    def setUp(self) -> None:
        Event.bind(test_db, bind_refs=False, bind_backrefs=False)
        test_db.connect()
        test_db.create_tables([Event])

    def tearDown(self) -> None:
        test_db.drop_tables([Event])
        test_db.close()

    def test_trigger_event_not_found_returns_empty(self) -> None:
        self.assertEqual(find_trail("missing", embeddings=None), [])

    def test_no_signals_enabled_returns_empty(self) -> None:
        _event("trigger")
        self.assertEqual(find_trail("trigger", embeddings=None), [])

    def test_named_match_on_other_camera_within_window(self) -> None:
        _event("trigger", sub_label="raine", camera="front")
        _event(
            "match",
            sub_label="raine",
            camera="back",
            start_time=BASE_TIME + 30,
        )

        results = find_trail("trigger", embeddings=None, window_seconds=120)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].event_id, "match")
        self.assertEqual(results[0].camera, "back")
        self.assertEqual(results[0].match_type, "named")
        self.assertEqual(results[0].label, "raine")

    def test_named_match_excludes_same_camera(self) -> None:
        _event("trigger", sub_label="raine", camera="front")
        _event(
            "same_camera",
            sub_label="raine",
            camera="front",
            start_time=BASE_TIME + 30,
        )

        self.assertEqual(find_trail("trigger", embeddings=None), [])

    def test_named_match_excludes_outside_window(self) -> None:
        _event("trigger", sub_label="raine", camera="front")
        _event(
            "too_late",
            sub_label="raine",
            camera="back",
            start_time=BASE_TIME + 1000,
        )

        results = find_trail("trigger", embeddings=None, window_seconds=120)
        self.assertEqual(results, [])

    def test_unknown_sub_label_is_not_a_named_match(self) -> None:
        _event("trigger", sub_label="unknown", camera="front")
        _event(
            "other_unknown",
            sub_label="unknown",
            camera="back",
            start_time=BASE_TIME + 10,
        )

        self.assertEqual(find_trail("trigger", embeddings=None), [])

    def test_visual_match_via_search_thumbnail(self) -> None:
        trigger = _event("trigger", camera="front")
        _event("candidate", camera="back", start_time=BASE_TIME + 10)

        embeddings = Mock()
        embeddings.search_thumbnail.return_value = [("candidate", 0.1)]

        results = find_trail("trigger", embeddings=embeddings, window_seconds=120)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].event_id, "candidate")
        self.assertEqual(results[0].match_type, "visual")
        self.assertEqual(results[0].score, 0.1)
        embeddings.search_thumbnail.assert_called_once()
        self.assertEqual(embeddings.search_thumbnail.call_args[0][0].id, trigger.id)

    def test_visual_match_above_distance_threshold_is_dropped(self) -> None:
        _event("trigger", camera="front")
        _event("far", camera="back", start_time=BASE_TIME + 10)

        embeddings = Mock()
        embeddings.search_thumbnail.return_value = [("far", 1.9)]

        self.assertEqual(
            find_trail("trigger", embeddings=embeddings, window_seconds=120), []
        )

    def test_visual_match_ignores_ids_outside_candidate_set(self) -> None:
        """Regression guard: search_thumbnail's event_ids filter is
        documented as unreliable on the pinned sqlite-vec version, so
        find_trail must not trust an id it didn't ask about -- e.g. one
        from the wrong camera or outside the time window."""
        _event("trigger", camera="front")
        _event("out_of_window", camera="back", start_time=BASE_TIME + 10_000)

        embeddings = Mock()
        embeddings.search_thumbnail.return_value = [("out_of_window", 0.05)]

        self.assertEqual(
            find_trail("trigger", embeddings=embeddings, window_seconds=120), []
        )

    def test_named_match_takes_priority_over_visual_match_for_same_event(self) -> None:
        _event("trigger", sub_label="raine", camera="front")
        _event(
            "match",
            sub_label="raine",
            camera="back",
            start_time=BASE_TIME + 10,
        )

        embeddings = Mock()
        embeddings.search_thumbnail.return_value = [("match", 0.05)]

        results = find_trail("trigger", embeddings=embeddings, window_seconds=120)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].match_type, "named")

    def test_results_sorted_by_timestamp_and_capped(self) -> None:
        _event("trigger", sub_label="raine", camera="front")
        for i in range(15):
            _event(
                f"match{i}",
                sub_label="raine",
                camera="back",
                start_time=BASE_TIME + 100 - i,
            )

        results = find_trail("trigger", embeddings=None, window_seconds=200)

        self.assertEqual(len(results), 10)
        self.assertEqual(
            [r.timestamp for r in results], sorted(r.timestamp for r in results)
        )


if __name__ == "__main__":
    unittest.main()
