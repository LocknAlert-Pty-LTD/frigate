"""End-to-end decisions made by classify(), for both recognizers.

The unit tests cover each gate in isolation; these check that classify actually
consults them, and in the right order.

The distinction that matters is between declining to answer and answering
"nobody I know". classify returns ``None`` to decline, and otherwise returns
whoever ranked top with a score that the caller compares against
``unknown_score`` -- so a stranger comes back as an enrolled name carrying a
score too low to survive that comparison.

An ambiguous face has to decline rather than return a low score. A low score
becomes the label "unknown", which reads as "a stranger was at the gate" when
what happened is "two enrolled people could not be told apart" -- a different
conclusion, and one that would stop anyone looking into it.

Both recognizers are covered because they are separate implementations of the
same pipeline, and a gate added to one is easy to forget in the other.
"""

import unittest

import cv2
import numpy as np

from frigate.config.classification import FaceRecognitionConfig
from frigate.data_processing.common.face.recognizer import (
    ArcFaceRecognizer,
    FaceNetRecognizer,
    keep_inlier_embeddings,
)


def unit(*values) -> np.ndarray:
    vec = np.array(values, dtype=np.float32)
    return vec / np.linalg.norm(vec)


def sharp_face(size: int = 112) -> np.ndarray:
    rng = np.random.default_rng(7)
    return rng.integers(0, 256, (size, size, 3), dtype=np.uint8)


def blurred_face() -> np.ndarray:
    return cv2.GaussianBlur(sharp_face(), (31, 31), 0)


class Embedder:
    """Returns a fixed embedding, so the test controls what classify sees."""

    def __init__(self, embedding: np.ndarray) -> None:
        self.embedding = embedding
        self.calls = 0

    def __call__(self, images):
        self.calls += 1
        return [self.embedding.reshape(1, -1)]


class RecognizerHarness:
    """Builds a recognizer with the models replaced.

    __init__ downloads and loads ONNX models, so the instance is constructed
    without it and only the attributes classify() touches are filled in.
    """

    recognizer_class: type

    def make(self, enrolled: dict, probe: np.ndarray, **config_overrides):
        recognizer = self.recognizer_class.__new__(self.recognizer_class)
        recognizer.config = type(
            "Config",
            (),
            {"face_recognition": FaceRecognitionConfig(**config_overrides)},
        )()
        recognizer.detector = type("Detector", (), {"is_ready": True})()
        recognizer.mean_embs = {
            name: keep_inlier_embeddings(embs) for name, embs in enrolled.items()
        }
        recognizer.face_embedder = Embedder(probe)
        # align_face needs landmarks from a real detector; the crop is already
        # square and face-shaped for these tests
        recognizer.align_face = lambda image, size: cv2.resize(image, (size, size))
        return recognizer

    def test_a_confident_match_is_named(self) -> None:
        recognizer = self.make({"alice": [unit(1, 0, 0)]}, unit(1, 0, 0))

        result = recognizer.classify(sharp_face())

        self.assertIsNotNone(result)
        name, score = result
        self.assertEqual("alice", name)
        self.assertGreater(score, 0)

    def test_a_blurry_face_is_declined_before_the_model_runs(self) -> None:
        """Not merely scored lower -- the embedder must not even be called, or
        the cost of a rejected frame is paid for nothing."""
        recognizer = self.make({"alice": [unit(1, 0, 0)]}, unit(1, 0, 0))

        self.assertIsNone(recognizer.classify(blurred_face()))
        self.assertEqual(0, recognizer.face_embedder.calls)

    def test_a_blurry_face_is_accepted_once_the_gate_is_disabled(self) -> None:
        """Confirms the previous result came from the gate and not from the
        harness failing to reach the model."""
        recognizer = self.make(
            {"alice": [unit(1, 0, 0)]}, unit(1, 0, 0), min_blur_variance=0
        )

        self.assertIsNotNone(recognizer.classify(blurred_face()))

    def test_two_near_equal_people_give_no_answer(self) -> None:
        """The look-alike case. Must be None (no answer), never ("", 0)
        (a stranger) -- see the module docstring."""
        recognizer = self.make(
            {"alice": [unit(1, 0.02, 0)], "bob": [unit(1, 0, 0.02)]},
            unit(1, 0.01, 0.01),
            recognition_margin=0.1,
        )

        self.assertIsNone(recognizer.classify(sharp_face()))

    def test_the_same_pair_resolves_once_the_margin_is_disabled(self) -> None:
        """Shows the rejection above is the margin's doing, not a coincidence
        of the fixture."""
        recognizer = self.make(
            {"alice": [unit(1, 0.02, 0)], "bob": [unit(1, 0, 0.02)]},
            unit(1, 0.01, 0.01),
            recognition_margin=0,
        )

        result = recognizer.classify(sharp_face())

        self.assertIsNotNone(result)
        self.assertIn(result[0], ("alice", "bob"))

    def test_a_stranger_scores_below_the_unknown_threshold(self) -> None:
        """classify always returns whoever ranked top, even when nothing
        matched; it is the score that says so.

        Every caller then applies `if score <= unknown_score: "unknown"`
        (frigate/data_processing/real_time/face.py). So the guarantee that
        matters is not the returned name but that the score stays under that
        threshold -- otherwise a stranger is published under an enrolled
        person's name.
        """
        config = FaceRecognitionConfig()
        recognizer = self.make({"alice": [unit(1, 0, 0)]}, unit(-1, 0, 0))

        _, score = recognizer.classify(sharp_face())

        self.assertLessEqual(score, config.unknown_score)

    def test_a_stranger_scores_well_below_a_genuine_match(self) -> None:
        """Pins the gap, so a scoring change cannot quietly close it while
        still passing the threshold test above."""
        stranger = self.make({"alice": [unit(1, 0, 0)]}, unit(-1, 0, 0))
        genuine = self.make({"alice": [unit(1, 0, 0)]}, unit(1, 0, 0))

        _, stranger_score = stranger.classify(sharp_face())
        _, genuine_score = genuine.classify(sharp_face())

        self.assertGreater(genuine_score - stranger_score, 0.5)

    def test_nothing_enrolled_gives_no_answer(self) -> None:
        recognizer = self.make({}, unit(1, 0, 0))
        recognizer.build = lambda: None  # would otherwise read FACE_DIR

        self.assertIsNone(recognizer.classify(sharp_face()))

    def test_an_unready_detector_gives_no_answer(self) -> None:
        recognizer = self.make({"alice": [unit(1, 0, 0)]}, unit(1, 0, 0))
        recognizer.detector = type("Detector", (), {"is_ready": False})()

        self.assertIsNone(recognizer.classify(sharp_face()))


class TestArcFaceClassify(RecognizerHarness, unittest.TestCase):
    recognizer_class = ArcFaceRecognizer


class TestFaceNetClassify(RecognizerHarness, unittest.TestCase):
    recognizer_class = FaceNetRecognizer


if __name__ == "__main__":
    unittest.main()
