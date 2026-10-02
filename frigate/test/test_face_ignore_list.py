"""Faces that are recognized and deliberately not reported.

For people who live or work somewhere and would rather the cameras did not keep
a record of them. They stay enrolled -- a name has to be matched before it can be
suppressed -- but nothing about them leaves the recognizer.

The guarantee has two halves, and both matter:

* **Nothing is published.** No sub label, so no event, no MQTT message and no
  notification carries the name.
* **Nothing is written.** The attempt image is not saved, so the Face Library
  does not accumulate crops of someone who asked not to be recorded. A list that
  only hid the name while still filling a folder with their face would be worse
  than useless, because it would look like privacy.
"""

import unittest

import pydantic

from frigate.config.classification import FaceRecognitionConfig


class TestMatching(unittest.TestCase):
    """Enrolled names come from directory names in the face library, where
    "Jane Doe", "jane_doe" and "jane-doe" are three folders but one person to
    whoever writes the config."""

    def setUp(self) -> None:
        self.config = FaceRecognitionConfig(ignored_faces=["Jane_Doe"])

    def test_the_exact_name(self) -> None:
        self.assertTrue(self.config.is_ignored("Jane_Doe"))

    def test_case_is_ignored(self) -> None:
        self.assertTrue(self.config.is_ignored("JANE_DOE"))
        self.assertTrue(self.config.is_ignored("jane_doe"))

    def test_separators_are_interchangeable(self) -> None:
        self.assertTrue(self.config.is_ignored("Jane Doe"))
        self.assertTrue(self.config.is_ignored("jane-doe"))

    def test_surrounding_space_is_ignored(self) -> None:
        self.assertTrue(self.config.is_ignored("  Jane Doe  "))

    def test_a_different_person_is_still_reported(self) -> None:
        self.assertFalse(self.config.is_ignored("Franco"))

    def test_a_similar_name_is_not_swept_up(self) -> None:
        """Normalization folds spelling, not identity. Matching a prefix or a
        substring would silence people who never asked to be."""
        self.assertFalse(self.config.is_ignored("Jane"))
        self.assertFalse(self.config.is_ignored("Jane Doe Jr"))
        self.assertFalse(self.config.is_ignored("Mary Jane Doe"))

    def test_nothing_is_ignored_by_default(self) -> None:
        """Opt-in. A default that hid anyone would be a surprise."""
        config = FaceRecognitionConfig()

        self.assertFalse(config.is_ignored("Franco"))
        self.assertFalse(config.is_ignored("unknown"))

    def test_absent_and_empty_names(self) -> None:
        self.assertFalse(self.config.is_ignored(None))
        self.assertFalse(self.config.is_ignored(""))

    def test_several_people_can_be_listed(self) -> None:
        config = FaceRecognitionConfig(ignored_faces=["Jane Doe", "Franco", "Lorrein"])

        for name in ("jane_doe", "FRANCO", "lorrein"):
            self.assertTrue(config.is_ignored(name), name)

        self.assertFalse(config.is_ignored("Someone Else"))

    def test_unknown_can_be_listed(self) -> None:
        """Coherent -- "do not tell me about strangers" -- and the operator's
        call, so it is allowed rather than special-cased. Worth knowing it works,
        since on a camera that gates access it is almost certainly a mistake."""
        config = FaceRecognitionConfig(ignored_faces=["unknown"])

        self.assertTrue(config.is_ignored("unknown"))


class TestConfigValidation(unittest.TestCase):
    def test_a_blank_entry_is_rejected(self) -> None:
        """Easy to leave behind when editing YAML, and the only symptom would be
        that someone believed to be ignored is still being reported."""
        with self.assertRaises(pydantic.ValidationError):
            FaceRecognitionConfig(ignored_faces=[""])

        with self.assertRaises(pydantic.ValidationError):
            FaceRecognitionConfig(ignored_faces=["Jane Doe", "   "])

    def test_an_empty_list_is_fine(self) -> None:
        self.assertEqual([], FaceRecognitionConfig(ignored_faces=[]).ignored_faces)

    def test_the_configured_spelling_is_kept(self) -> None:
        """Normalization happens at comparison time, so the UI shows the operator
        what they typed."""
        config = FaceRecognitionConfig(ignored_faces=["Jane_Doe"])

        self.assertEqual(["Jane_Doe"], config.ignored_faces)


class TestSuppressionOrder(unittest.TestCase):
    """Where the check sits in process_frame decides whether it works.

    Reading the source rather than driving the processor: constructing one loads
    the detection, landmark and embedding models and opens MQTT channels, none of
    which bears on ordering.
    """

    def setUp(self) -> None:
        import inspect

        from frigate.data_processing.real_time.face import FaceRealTimeProcessor

        self.source = inspect.getsource(FaceRealTimeProcessor.process_frame)

    def position(self, needle: str) -> int:
        index = self.source.find(needle)
        self.assertNotEqual(-1, index, f"not found in process_frame: {needle}")
        return index

    def test_the_check_runs_before_the_unknown_threshold(self) -> None:
        """A low-scoring match would otherwise be relabelled "unknown" and
        published as a stranger, which is the opposite of staying silent."""
        self.assertLess(
            self.position("is_ignored"),
            self.position("sub_label = \"unknown\""),
        )

    def test_the_check_runs_before_the_attempt_image_is_written(self) -> None:
        """Otherwise the Face Library fills with crops of someone who asked not
        to be recorded."""
        self.assertLess(
            self.position("is_ignored"), self.position("self.write_face_attempt")
        )

    def test_the_check_runs_before_any_history_is_kept(self) -> None:
        """Anchored on the append, not on the first mention of the dict: the
        method reads person_face_history much earlier to apply its attempt
        limits, and that read is not a write."""
        self.assertLess(
            self.position("is_ignored"),
            self.position("self.person_face_history[id].append"),
        )

    def test_the_check_runs_before_the_name_is_published(self) -> None:
        self.assertLess(
            self.position("is_ignored"), self.position("tracked_object_update")
        )

    def test_it_returns_rather_than_falling_through(self) -> None:
        """A branch that logged and continued would publish anyway."""
        start = self.position("is_ignored")
        branch = self.source[start : self.position("self.write_face_attempt")]

        self.assertIn("return", branch)

    def test_inference_time_is_still_recorded(self) -> None:
        """The work was done, so it belongs in the metrics. Skipping it would
        quietly bias the reported average downward."""
        branch = self.source[
            self.position("is_ignored") : self.position("self.write_face_attempt")
        ]

        self.assertIn("__update_metrics", branch)


if __name__ == "__main__":
    unittest.main()
