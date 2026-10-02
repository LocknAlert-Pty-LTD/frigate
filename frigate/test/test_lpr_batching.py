"""Every text crop of a plate has to reach the OCR models.

The batching loops in `_classify` and `_recognize` reset their input list at the
top of each iteration but called the model after the loop had finished, so with
more crops than `batch_size` only the final batch was ever run. Earlier crops
were dropped in silence -- no warning, no error, just a plate missing the
characters those crops held. `_process_classification_output` had the mirror
problem: it walked every output once per batch, indexing past the end.

That matters most where it is least visible. A plate read as "ABC" instead of
"ABC123" is not obviously wrong, and if the gate opens on a prefix match or a
fuzzy `match_distance`, a truncated read can still let a vehicle in.

The models are replaced with recorders. What is under test is which crops reach
them and how the answers are mapped back, which is arithmetic, not inference.
"""

import unittest

import numpy as np

from frigate.data_processing.common.license_plate.mixin import (
    LicensePlateProcessingMixin,
)
from frigate.util.builtin import StageTimings


class InnerRunner:
    """The width the recognition preprocessor asks the session for.

    Defaults to the string the real recognition_v4.onnx reports, because its
    width is a dynamic dimension. That is what makes the preprocessor fall back
    to a width derived from the batch, which is the behaviour under test.
    """

    def __init__(self, input_width="DynamicDimension.1") -> None:
        self.input_width = input_width

    def get_input_width(self):
        return self.input_width


class RecordingModel:
    """Returns one output row per input and remembers the batches it saw."""

    def __init__(self, rows: int = 4, columns: int = 8, input_width=None) -> None:
        self.batches: list[int] = []
        self.rows = rows
        self.columns = columns
        self.runner = (
            InnerRunner() if input_width is None else InnerRunner(input_width)
        )

    def __call__(self, images):
        self.batches.append(len(images))
        return [
            np.full((self.rows, self.columns), 0.1, dtype=np.float32)
            for _ in images
        ]

    @property
    def total_seen(self) -> int:
        return sum(self.batches)


class ClassificationModel(RecordingModel):
    """Two logits per crop: index 0 is upright, index 1 is upside down."""

    def __init__(self, upside_down: set[int] | None = None) -> None:
        super().__init__()  # noqa: F841
        self.upside_down = upside_down or set()
        self.seen = 0

    def __call__(self, images):
        self.batches.append(len(images))
        outputs = []

        for _ in images:
            flip = self.seen in self.upside_down
            outputs.append(
                np.array([0.1, 0.99] if flip else [0.99, 0.1], dtype=np.float32)
            )
            self.seen += 1

        return outputs


class Runner:
    def __init__(self, classification=None, recognition=None) -> None:
        self.classification_model = classification
        self.recognition_model = recognition


class Decoder:
    """Stands in for the CTC decoder: one short string per output row."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, outputs):
        start = self.calls
        self.calls += len(outputs)
        return (
            [f"P{start + i}" for i in range(len(outputs))],
            [[0.9] for _ in outputs],
        )


class Camera:
    """Minimal config: the recognition preprocessor reads lpr.enhancement."""

    class _Lpr:
        enhancement = 0

    lpr = _Lpr()


def mixin(batch_size: int = 6, classification=None, recognition=None):
    instance = LicensePlateProcessingMixin.__new__(LicensePlateProcessingMixin)
    instance.batch_size = batch_size
    instance.model_runner = Runner(classification, recognition)
    instance.ctc_decoder = Decoder()
    instance.config = type("Config", (), {"cameras": {"gate": Camera()}})()
    # The model calls are wrapped in stage timers. Leaving this off does not
    # fail loudly: the AttributeError lands in the same `except Exception` that
    # guards inference, so the stage would simply report no plate.
    instance.stage_timings = StageTimings({}, prefix="plate_")
    return instance


def crops(count: int, width: int = 90, height: int = 30) -> list[np.ndarray]:
    """Crops of varying width, so the aspect-ratio sort actually reorders them."""
    rng = np.random.default_rng(4)
    return [
        rng.integers(
            0, 256, (height, width + index * 7, 3), dtype=np.uint8
        ).astype(np.uint8)
        for index in range(count)
    ]


class TestRecognizeRunsEveryBatch(unittest.TestCase):
    def recognize(self, count: int, batch_size: int = 6):
        recognition = RecordingModel()
        instance = mixin(batch_size=batch_size, recognition=recognition)
        texts, confidences = instance._recognize("gate", crops(count))
        return recognition, texts, confidences

    def test_a_single_batch(self) -> None:
        recognition, texts, _ = self.recognize(4)

        self.assertEqual([4], recognition.batches)
        self.assertEqual(4, len(texts))

    def test_every_crop_reaches_the_model_across_batches(self) -> None:
        """The regression. With batch_size 6 and 14 crops the old code ran one
        batch of 2 and returned 2 results for 14 crops."""
        recognition, texts, _ = self.recognize(14)

        self.assertEqual([6, 6, 2], recognition.batches)
        self.assertEqual(14, recognition.total_seen)
        self.assertEqual(14, len(texts))

    def test_one_result_per_crop_at_every_size(self) -> None:
        for count in range(1, 20):
            _, texts, confidences = self.recognize(count)

            self.assertEqual(count, len(texts), f"{count} crops")
            self.assertEqual(count, len(confidences), f"{count} crops")

    def test_results_stay_in_the_order_of_the_crops(self) -> None:
        """`_recognize` does not sort, and the caller pairs these with the boxes
        positionally, so a reordering would attach text to the wrong box."""
        _, texts, _ = self.recognize(8)

        self.assertEqual([f"P{i}" for i in range(8)], texts)

    def test_a_batch_size_of_one(self) -> None:
        recognition, texts, _ = self.recognize(5, batch_size=1)

        self.assertEqual([1, 1, 1, 1, 1], recognition.batches)
        self.assertEqual(5, len(texts))

    def test_no_crops_runs_nothing(self) -> None:
        recognition, texts, confidences = self.recognize(0)

        self.assertEqual([], recognition.batches)
        self.assertEqual(([], []), (texts, confidences))

    def test_a_model_with_a_fixed_width_is_honoured(self) -> None:
        """When a session reports a real width, the preprocessor uses it instead
        of deriving one. recognition_v4.onnx does not -- its width is a dynamic
        dimension -- but a future model might, and then every batch pads to the
        same size."""
        recognition = RecordingModel(input_width=320)
        instance = mixin(recognition=recognition)

        texts, _ = instance._recognize("gate", crops(9))

        self.assertEqual([6, 3], recognition.batches)
        self.assertEqual(9, len(texts))


class TestRecognizeHandlesFailure(unittest.TestCase):
    class Failing(RecordingModel):
        def __call__(self, images):
            self.batches.append(len(images))
            raise RuntimeError("inference failed")

    def test_a_failed_batch_gives_up_rather_than_returning_a_partial_plate(
        self,
    ) -> None:
        """Half a plate is worse than none when a gate may act on it."""
        instance = mixin(recognition=self.Failing())

        self.assertEqual(([], []), instance._recognize("gate", crops(9)))

    def test_failure_on_a_later_batch_still_returns_nothing(self) -> None:
        class FailsOnSecond(RecordingModel):
            def __call__(self, images):
                self.batches.append(len(images))
                if len(self.batches) > 1:
                    raise RuntimeError("inference failed")
                return [np.full((4, 8), 0.1, dtype=np.float32) for _ in images]

        instance = mixin(recognition=FailsOnSecond())

        self.assertEqual(([], []), instance._recognize("gate", crops(9)))


class TestClassifyRunsEveryBatch(unittest.TestCase):
    def test_every_crop_reaches_the_model_across_batches(self) -> None:
        classification = ClassificationModel()
        instance = mixin(classification=classification)

        images, results = instance._classify(crops(14))

        self.assertEqual([6, 6, 2], classification.batches)
        self.assertEqual(14, classification.total_seen)
        self.assertEqual(14, len(results))

    def test_one_result_per_crop_at_every_size(self) -> None:
        """The old nested output loop raised IndexError past one batch, so this
        covers the sizes that used to crash as well as the ones that truncated."""
        for count in range(1, 20):
            instance = mixin(classification=ClassificationModel())

            images, results = instance._classify(crops(count))

            self.assertEqual(count, len(results), f"{count} crops")
            self.assertEqual(count, len(images), f"{count} crops")

    def test_a_failed_batch_returns_none(self) -> None:
        class Failing(RecordingModel):
            def __call__(self, images):
                raise RuntimeError("inference failed")

        instance = mixin(classification=Failing())

        self.assertIsNone(instance._classify(crops(9)))

    def test_no_crops(self) -> None:
        classification = ClassificationModel()
        instance = mixin(classification=classification)

        images, results = instance._classify([])

        self.assertEqual([], classification.batches)
        self.assertEqual([], results)
        self.assertEqual([], images)


class TestClassificationMapsBackToTheRightCrop(unittest.TestCase):
    """`_classify` sorts crops by aspect ratio before batching, so the outputs
    arrive in a different order from the caller list. Mapping them back wrongly
    would rotate the wrong plate."""

    def test_an_upright_batch_rotates_nothing(self) -> None:
        instance = mixin(classification=ClassificationModel())
        original = crops(9)
        before = [image.copy() for image in original]

        images, results = instance._classify(original)

        self.assertTrue(all(label == "0" for label, _ in results))
        for index, (was, now) in enumerate(zip(before, images)):
            np.testing.assert_array_equal(was, now, f"crop {index} was rotated")

    def test_only_the_flagged_crop_is_rotated(self) -> None:
        """The crop flagged upside down is identified by its position in the
        sorted order, and the rotation has to land on the matching entry of the
        caller list."""
        images = crops(9)
        # widths increase with index, so the aspect-ratio sort is the identity
        # here and sorted position 3 is caller index 3
        instance = mixin(classification=ClassificationModel(upside_down={3}))
        before = [image.copy() for image in images]

        rotated, results = instance._classify(images)

        self.assertEqual("180", results[3][0])
        np.testing.assert_array_equal(
            cv2_rotate_180(before[3]), rotated[3], "crop 3 should be flipped"
        )

        for index in range(9):
            if index == 3:
                continue
            self.assertEqual("0", results[index][0], f"crop {index}")
            np.testing.assert_array_equal(before[index], rotated[index], f"crop {index}")

    def test_a_low_confidence_flip_is_not_applied(self) -> None:
        """Rotating on a weak signal would corrupt a readable plate."""

        class Unsure(RecordingModel):
            def __call__(self, images):
                self.batches.append(len(images))
                return [np.array([0.45, 0.55], dtype=np.float32) for _ in images]

        images = crops(4)
        before = [image.copy() for image in images]
        instance = mixin(classification=Unsure())

        rotated, results = instance._classify(images)

        self.assertTrue(all(label == "180" for label, _ in results))
        for index, (was, now) in enumerate(zip(before, rotated)):
            np.testing.assert_array_equal(was, now, f"crop {index} was rotated")


def cv2_rotate_180(image: np.ndarray) -> np.ndarray:
    import cv2

    return cv2.rotate(image, cv2.ROTATE_180)


if __name__ == "__main__":
    unittest.main()
