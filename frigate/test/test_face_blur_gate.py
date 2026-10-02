"""The blur gate, which rejects a face crop outright.

Distinct from the pre-existing blur_confidence_filter, which only subtracts a
few points of confidence from a soft face. For access control that penalty is
not enough: a motion-blurred face carries very little identity information, and
whatever it scores against is closer to chance than to recognition. A crop that
never reaches the embedder cannot open a door on a coin flip.

Uses the real FaceRecognitionConfig so the defaults under test are the ones
that ship, not a stub's.
"""

import unittest

import cv2
import numpy as np

from frigate.config.classification import FaceRecognitionConfig
from frigate.data_processing.common.face.recognizer import FaceRecognizer


class Recognizer(FaceRecognizer):
    """Concrete subclass: is_too_blurry lives on the abstract base."""

    def __init__(self, face_recognition: FaceRecognitionConfig) -> None:
        # deliberately not calling super().__init__ -- a full FrigateConfig
        # needs cameras, detectors and paths that say nothing about blur
        self.config = type("Config", (), {"face_recognition": face_recognition})()

    def build(self) -> None: ...
    def clear(self) -> None: ...
    def classify(self, face_image): ...


def sharp_face(size: int = 112) -> np.ndarray:
    """High-frequency detail, as a real in-focus face has."""
    rng = np.random.default_rng(1234)
    return rng.integers(0, 256, (size, size), dtype=np.uint8)


def blurred(image: np.ndarray, radius: int = 21) -> np.ndarray:
    return cv2.GaussianBlur(image, (radius, radius), 0)


class TestIsTooBlurry(unittest.TestCase):
    def recognizer(self, **overrides) -> Recognizer:
        return Recognizer(FaceRecognitionConfig(**overrides))

    def test_a_sharp_face_passes(self) -> None:
        self.assertFalse(self.recognizer().is_too_blurry(sharp_face()))

    def test_a_blurred_face_is_rejected(self) -> None:
        self.assertTrue(self.recognizer().is_too_blurry(blurred(sharp_face())))

    def test_a_flat_crop_is_rejected(self) -> None:
        """No detail at all -- an overexposed or fully defocused frame."""
        self.assertTrue(
            self.recognizer().is_too_blurry(np.full((112, 112), 128, dtype=np.uint8))
        )

    def test_threshold_of_zero_disables_the_gate(self) -> None:
        """The opt-out, for anyone who would rather score a soft face than
        drop it."""
        recognizer = self.recognizer(min_blur_variance=0)

        self.assertFalse(recognizer.is_too_blurry(blurred(sharp_face())))
        self.assertFalse(
            recognizer.is_too_blurry(np.zeros((112, 112), dtype=np.uint8))
        )

    def test_the_threshold_is_what_decides(self) -> None:
        image = blurred(sharp_face(), radius=9)
        variance = cv2.Laplacian(image, cv2.CV_64F).var()

        self.assertTrue(
            self.recognizer(min_blur_variance=int(variance) + 50).is_too_blurry(image)
        )
        self.assertFalse(
            self.recognizer(min_blur_variance=max(1, int(variance) - 50)).is_too_blurry(
                image
            )
        )

    def test_progressive_blur_is_ordered(self) -> None:
        """Sanity check on the metric itself: more blur, less variance. If this
        ever inverts, the threshold means the opposite of what it says."""
        base = sharp_face()
        variances = [
            cv2.Laplacian(img, cv2.CV_64F).var()
            for img in (base, blurred(base, 5), blurred(base, 15), blurred(base, 31))
        ]

        self.assertEqual(sorted(variances, reverse=True), variances)


class TestShippedDefault(unittest.TestCase):
    def test_default_threshold_is_active(self) -> None:
        """A default of 0 would ship the gate switched off."""
        self.assertGreater(FaceRecognitionConfig().min_blur_variance, 0)

    def test_default_separates_sharp_from_blurred(self) -> None:
        """Pins the shipped 120 between the two cases, so a later tweak that
        rejects every face (or none) fails here rather than in the field."""
        threshold = FaceRecognitionConfig().min_blur_variance
        base = sharp_face()

        self.assertGreater(cv2.Laplacian(base, cv2.CV_64F).var(), threshold)
        self.assertLess(cv2.Laplacian(blurred(base), cv2.CV_64F).var(), threshold)


if __name__ == "__main__":
    unittest.main()
