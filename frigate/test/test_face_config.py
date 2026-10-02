"""Defaults and bounds for the face-recognition settings.

Defaults are what almost every install runs on, and these particular ones
decide whether recognition is strict enough to gate access. A silent change to
one of them is the kind of regression nobody notices until the wrong person is
recognised, so the shipped values are pinned here with the reasoning attached.
"""

import unittest

import pydantic

from frigate.config.classification import FaceRecognitionConfig, ModelSizeEnum


class TestShippedDefaults(unittest.TestCase):
    def setUp(self) -> None:
        self.config = FaceRecognitionConfig()

    def test_uses_arcface(self) -> None:
        """'large' is ArcFace, 'small' is FaceNet. ArcFace separates faces
        considerably better, which is the point when a match opens a door."""
        self.assertEqual(ModelSizeEnum.large, self.config.model_size)

    def test_retains_400_attempts(self) -> None:
        self.assertEqual(400, self.config.save_attempts)

    def test_blur_gate_is_on(self) -> None:
        self.assertGreater(self.config.min_blur_variance, 0)

    def test_margin_is_on(self) -> None:
        self.assertGreater(self.config.recognition_margin, 0)

    def test_scores_against_several_neighbours(self) -> None:
        """k=1 would make one lucky enrolment photo enough on its own."""
        self.assertGreater(self.config.knn_top_k, 1)


class TestBounds(unittest.TestCase):
    def assert_rejected(self, **overrides) -> None:
        with self.assertRaises(pydantic.ValidationError):
            FaceRecognitionConfig(**overrides)

    def test_zero_disables_rather_than_erroring(self) -> None:
        """Both gates are opt-out, so 0 has to validate."""
        self.assertEqual(0, FaceRecognitionConfig(min_blur_variance=0).min_blur_variance)
        self.assertEqual(
            0.0, FaceRecognitionConfig(recognition_margin=0).recognition_margin
        )

    def test_negative_values_are_rejected(self) -> None:
        self.assert_rejected(min_blur_variance=-1)
        self.assert_rejected(recognition_margin=-0.1)

    def test_margin_cannot_exceed_a_cosine_similarity(self) -> None:
        """Similarities live in [0, 1]; a margin above 1 rejects everything."""
        self.assert_rejected(recognition_margin=1.5)

    def test_knn_top_k_must_be_at_least_one(self) -> None:
        self.assert_rejected(knn_top_k=0)

    def test_save_attempts_may_be_zero(self) -> None:
        """0 means keep nothing, for installs that would rather not store
        crops of people's faces at all."""
        self.assertEqual(0, FaceRecognitionConfig(save_attempts=0).save_attempts)

    def test_unknown_fields_are_refused(self) -> None:
        """extra='forbid' -- a typo in a threshold must fail loudly, not leave
        the default silently in place."""
        self.assert_rejected(min_blur_varience=120)


if __name__ == "__main__":
    unittest.main()
