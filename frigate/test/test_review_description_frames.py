"""Which recording a review description is written from, and what it logs.

Two problems, both visible as a wall of warnings on a camera that was working
fine:

    No recording found for gate_camera at timestamp 1790924817.4799004
    No recording found for gate_camera at timestamp 1790924818.5910115
    ... (one per sampled frame)
    No recording frames found for gate_camera, falling back to preview frames

The lookup asked only for main stream segments. This fork also records a sub
stream, so a camera recording only that found nothing and fell all the way back
to preview frames -- which are small and heavily compressed, so the description
was written from a far worse picture than the one already on disk.

And a 30 second review item samples dozens of timestamps, so a camera that is
simply not recording produced dozens of identical warnings per event. That is
enough noise to bury whatever else was in the log while saying no more than one
line would.
"""

import unittest
from unittest.mock import patch

from frigate.const import STREAM_TYPE_MAIN, STREAM_TYPE_SUB


class Segment:
    """A row from the recordings table."""

    def __init__(self, path: str, start_time: float) -> None:
        self.path = path
        self.start_time = start_time


class RecordingIndex:
    """Stands in for the Recordings query, answering per stream type.

    The real lookup chains peewee calls; what matters here is which stream types
    are consulted, in what order, and what happens when one has no segment.
    """

    def __init__(self, available: dict[str, Segment]) -> None:
        self.available = available
        self.queried: list[str] = []

    def get(self, stream_type: str) -> Segment | None:
        self.queried.append(stream_type)
        return self.available.get(stream_type)


def extract(index: RecordingIndex, decodable=lambda segment: b"jpeg-bytes"):
    """Reimplements the lookup under test over the stand-in index.

    The production function is a closure inside a method that needs a config, a
    GenAI client and a database. Mirrored here so the ordering and fallback can
    be driven directly; the behaviour it mirrors is pinned by
    TestProductionSourceMatches below.
    """
    for stream_type in (STREAM_TYPE_MAIN, STREAM_TYPE_SUB):
        segment = index.get(stream_type)

        if segment is None:
            continue

        image = decodable(segment)

        if image:
            return image

    return None


class TestPrefersMainThenFallsBackToSub(unittest.TestCase):
    def test_the_main_stream_is_used_when_present(self) -> None:
        index = RecordingIndex({STREAM_TYPE_MAIN: Segment("/main.mp4", 100.0)})

        self.assertEqual(b"jpeg-bytes", extract(index))
        self.assertEqual([STREAM_TYPE_MAIN], index.queried)

    def test_the_sub_stream_is_not_consulted_when_main_works(self) -> None:
        """A sub segment is a worse picture, so it is a fallback and not a
        preference."""
        index = RecordingIndex(
            {
                STREAM_TYPE_MAIN: Segment("/main.mp4", 100.0),
                STREAM_TYPE_SUB: Segment("/sub.mp4", 100.0),
            }
        )

        extract(index)

        self.assertNotIn(STREAM_TYPE_SUB, index.queried)

    def test_the_sub_stream_is_used_when_there_is_no_main_segment(self) -> None:
        """The case that was falling through to preview frames."""
        index = RecordingIndex({STREAM_TYPE_SUB: Segment("/sub.mp4", 100.0)})

        self.assertEqual(b"jpeg-bytes", extract(index))
        self.assertEqual([STREAM_TYPE_MAIN, STREAM_TYPE_SUB], index.queried)

    def test_an_undecodable_main_segment_falls_through_to_sub(self) -> None:
        """A segment row can exist while the file is truncated, which is normal
        for the segment being written when a camera dropped out."""
        index = RecordingIndex(
            {
                STREAM_TYPE_MAIN: Segment("/truncated.mp4", 100.0),
                STREAM_TYPE_SUB: Segment("/sub.mp4", 100.0),
            }
        )

        image = extract(
            index,
            decodable=lambda segment: None if "truncated" in segment.path else b"ok",
        )

        self.assertEqual(b"ok", image)

    def test_nothing_recorded_at_all(self) -> None:
        index = RecordingIndex({})

        self.assertIsNone(extract(index))
        self.assertEqual([STREAM_TYPE_MAIN, STREAM_TYPE_SUB], index.queried)


class TestProductionSourceMatches(unittest.TestCase):
    """Keeps the stand-in above honest about the real implementation."""

    def setUp(self) -> None:
        import inspect

        from frigate.data_processing.post.review_descriptions import (
            ReviewDescriptionProcessor,
        )

        self.source = inspect.getsource(
            ReviewDescriptionProcessor.get_recording_frames
        )

    def test_both_stream_types_are_tried(self) -> None:
        self.assertIn("STREAM_TYPE_MAIN, STREAM_TYPE_SUB", self.source)

    def test_main_is_tried_first(self) -> None:
        self.assertLess(
            self.source.index("STREAM_TYPE_MAIN"),
            self.source.index("STREAM_TYPE_SUB"),
        )

    def test_a_missing_segment_continues_rather_than_returning(self) -> None:
        """A `return None` in the DoesNotExist handler would skip the sub stream
        entirely, which is the bug this replaced."""
        handler = self.source[self.source.index("except DoesNotExist") :]

        self.assertTrue(
            handler.lstrip().startswith("except DoesNotExist:\n                    continue"),
            "a missing main segment must fall through to the next stream type",
        )


class TestWarningIsSummarised(unittest.TestCase):
    def setUp(self) -> None:
        import inspect

        from frigate.data_processing.post.review_descriptions import (
            ReviewDescriptionProcessor,
        )

        self.source = inspect.getsource(
            ReviewDescriptionProcessor.get_recording_frames
        )

    def test_the_warning_is_outside_the_per_timestamp_loop(self) -> None:
        """One line per review item, not one per sampled frame."""
        self.assertIn("if missing:", self.source)
        self.assertNotIn(
            'logger.warning(\n                        f"No recording found for',
            self.source,
        )

    def test_it_reports_how_many_of_how_many(self) -> None:
        """A partial gap and a camera recording nothing at all are different
        problems, and the count is what separates them."""
        self.assertIn("len(missing)", self.source)
        self.assertIn("len(timestamps)", self.source)

    def test_it_names_what_to_check(self) -> None:
        """The warning is usually configuration, not a fault, so it should say
        where to look instead of only reporting the symptom."""
        self.assertIn("record role", self.source)


if __name__ == "__main__":
    unittest.main()
