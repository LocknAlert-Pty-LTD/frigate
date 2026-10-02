"""The PaddleOCR models are fed a small, fixed set of input shapes.

Both models declare dynamic inputs, and the pipeline used to give them whatever
size each plate produced: the text detector got the plate rounded to its own
multiple of 32, the recogniser a width derived from its widest crop. On CUDA,
ONNX Runtime chooses convolution algorithms per input shape by benchmarking all
of them, so nearly every car paid for a fresh benchmark of every layer. Over 150
plate sizes the detector saw 32 distinct shapes; it now sees one.

Measured against the old pipeline with the real models over 72 synthetic plates,
the final plate string was identical on all 72, with 60 exact reads and no empty
reads on both. That comparison is the guarantee that matters, and it depended on
one detail these tests pin: padding the canvas with a flat colour put a hard edge
against the plate and cost the detector the text on 14 of the 72, so the border
is replicated instead.
"""

import types
import unittest

import cv2
import numpy as np

from frigate.data_processing.common.license_plate.mixin import (
    LicensePlateProcessingMixin,
)
from frigate.embeddings.onnx.lpr_embedding import (
    LPR_DETECTION_CANVAS,
    LPR_RECOGNITION_HEIGHT,
    LPR_RECOGNITION_WARMUP_BATCHES,
    LPR_RECOGNITION_WIDTHS,
    recognition_width_bucket,
    warm_fixed_shapes,
)
from frigate.util.builtin import StageTimings

CANVAS_H, CANVAS_W = LPR_DETECTION_CANVAS


class DetectionModel:
    """Records the shapes it is fed and returns a probability map with one
    rectangle of high probability, placed in resized-image coordinates."""

    def __init__(self, blob=None) -> None:
        self.shapes: list[tuple] = []
        self.inputs: list[np.ndarray] = []
        self.blob = blob

    def __call__(self, inputs):
        batch = inputs[0]
        self.shapes.append(batch.shape)
        self.inputs.append(batch)
        h, w = batch.shape[2:]
        out = np.zeros((1, h, w), dtype=np.float32)

        if self.blob is not None:
            x1, y1, x2, y2 = self.blob
            out[0, y1:y2, x1:x2] = 0.95

        return [out]


def mixin(detection) -> LicensePlateProcessingMixin:
    instance = LicensePlateProcessingMixin.__new__(LicensePlateProcessingMixin)
    instance.min_size = 8
    instance.box_thresh = 0.6
    instance.mask_thresh = 0.6
    instance.model_runner = types.SimpleNamespace(detection_model=detection)
    instance.stage_timings = StageTimings({})
    return instance


def plate(width: int, height: int) -> np.ndarray:
    rng = np.random.default_rng(width * 31 + height)
    return rng.integers(0, 256, (height, width, 3), dtype=np.uint8)


class TestDetectionSeesOneShape(unittest.TestCase):
    def test_every_plate_size_is_fed_as_the_canvas(self) -> None:
        """The whole point: one shape, tuned once."""
        detection = DetectionModel()
        instance = mixin(detection)

        for width, height in [(280, 64), (400, 92), (600, 136), (880, 204),
                              (330, 220), (1200, 300), (60, 40)]:
            instance._detect(plate(width, height), 0)

        self.assertEqual({(1, 3, CANVAS_H, CANVAS_W)}, set(detection.shapes))

    def test_the_canvas_is_a_valid_detector_input(self) -> None:
        """The DB detector needs both sides divisible by 32."""
        self.assertEqual(0, CANVAS_H % 32)
        self.assertEqual(0, CANVAS_W % 32)


class TestFitDetectionCanvas(unittest.TestCase):
    fit = staticmethod(LicensePlateProcessingMixin._fit_detection_canvas)

    def test_a_large_plate_is_scaled_down_to_fit(self) -> None:
        fitted = self.fit(plate(880, 204))

        self.assertLessEqual(fitted.shape[0], CANVAS_H)
        self.assertLessEqual(fitted.shape[1], CANVAS_W)

    def test_the_aspect_ratio_is_kept(self) -> None:
        """The old resize rounded each side independently, which distorted the
        plate. A stretched plate is a different input to the detector."""
        original = plate(880, 204)
        fitted = self.fit(original)

        self.assertAlmostEqual(
            original.shape[1] / original.shape[0],
            fitted.shape[1] / fitted.shape[0],
            delta=0.05,
        )

    def test_a_small_plate_is_never_enlarged(self) -> None:
        """Measured: allowing upscaling cost an exact read and produced an empty
        one. Small plates are padded at their own scale instead."""
        small = plate(280, 64)

        self.assertEqual(small.shape, self.fit(small).shape)

    def test_a_tall_two_line_plate_fits_by_height(self) -> None:
        fitted = self.fit(plate(330, 220))

        self.assertEqual(CANVAS_H, fitted.shape[0])
        self.assertLessEqual(fitted.shape[1], CANVAS_W)


class TestPaddingAndMapping(unittest.TestCase):
    def test_the_padding_repeats_the_plate_edge(self) -> None:
        """Flat padding left a hard edge against the plate and cost the detector
        the text on 14 of 72 plates. The padded columns must repeat the last
        real column, not be a constant."""
        detection = DetectionModel()
        image = plate(280, 64)
        mixin(detection)._detect(image, 0)

        fed = detection.inputs[0][0]  # (3, H, W), normalised
        last_real = fed[:, :64, 279]
        padded = fed[:, :64, 400]

        np.testing.assert_allclose(last_real, padded, rtol=1e-5)

    def test_a_box_maps_back_to_original_coordinates(self) -> None:
        """An 800x200 plate fits the 512x128 canvas at 0.64. A detection in the
        canvas must come back scaled to the plate it was found on, because the
        recogniser crops from that full-resolution plate."""
        blob = (100, 30, 300, 90)  # resized coordinates
        boxes = mixin(DetectionModel(blob))._detect(plate(800, 200), 0)

        self.assertEqual(1, len(boxes))
        xs, ys = boxes[0][:, 0], boxes[0][:, 1]
        # 100/0.64 = 156, 300/0.64 = 469, 30/0.64 = 47, 90/0.64 = 141, before
        # the detector's own unclip expansion
        self.assertLess(xs.min(), 170)
        self.assertGreater(xs.max(), 455)
        self.assertLess(ys.min(), 60)
        self.assertGreater(ys.max(), 130)

    def test_an_unscaled_plate_maps_back_one_to_one(self) -> None:
        # vertical margin matters: the detector expands each region before
        # returning it, and a polygon reaching both edges of a 64px plate is
        # rejected by the existing bounds filter, in the old pipeline too
        blob = (50, 20, 200, 44)
        boxes = mixin(DetectionModel(blob))._detect(plate(280, 64), 0)

        self.assertEqual(1, len(boxes))
        self.assertLess(boxes[0][:, 0].min(), 55)
        self.assertGreater(boxes[0][:, 0].max(), 195)

    def test_detections_in_the_padding_are_discarded(self) -> None:
        """Only the region holding the plate is read back. Anything the model
        finds in the padding is not on the plate."""
        blob = (350, 20, 480, 60)  # entirely right of a 280-wide plate
        boxes = mixin(DetectionModel(blob))._detect(plate(280, 64), 0)

        self.assertEqual(0, len(boxes))


class TestRecognitionWidthBuckets(unittest.TestCase):
    def test_narrow_crops_use_the_default_width(self) -> None:
        self.assertEqual(320, recognition_width_bucket(100))
        self.assertEqual(320, recognition_width_bucket(320))

    def test_crops_round_up_to_the_next_bucket(self) -> None:
        self.assertEqual(480, recognition_width_bucket(321))
        self.assertEqual(640, recognition_width_bucket(481))

    def test_wider_than_the_last_bucket_stays_in_it(self) -> None:
        """Squeezed into the widest bucket rather than given its own shape."""
        self.assertEqual(640, recognition_width_bucket(2000))

    def test_buckets_are_ascending(self) -> None:
        self.assertEqual(sorted(LPR_RECOGNITION_WIDTHS), list(LPR_RECOGNITION_WIDTHS))

    def test_the_recogniser_only_ever_sees_bucket_widths(self) -> None:
        widths = set()

        class Recognition:
            class runner:
                @staticmethod
                def get_input_width():
                    return "DynamicDimension.1"

            def __call__(self, inputs):
                for x in inputs:
                    widths.add(x.shape[-1])
                return [np.full((8, 10), 0.1, dtype=np.float32) for _ in inputs]

        instance = LicensePlateProcessingMixin.__new__(LicensePlateProcessingMixin)
        instance.batch_size = 6
        instance.model_runner = types.SimpleNamespace(recognition_model=Recognition())
        instance.ctc_decoder = lambda outputs: (["X"] * len(outputs), [[0.9]] * len(outputs))
        instance.config = types.SimpleNamespace(
            cameras={"gate": types.SimpleNamespace(lpr=types.SimpleNamespace(enhancement=0))}
        )
        instance.stage_timings = StageTimings({})

        rng = np.random.default_rng(3)
        for width in range(60, 1400, 37):
            crop = rng.integers(0, 256, (48, width, 3), dtype=np.uint8)
            instance._recognize("gate", [crop])

        self.assertTrue(widths <= set(LPR_RECOGNITION_WIDTHS), widths)


class TestWarmup(unittest.TestCase):
    class Runner:
        device_name = "CUDA"

        def __init__(self, fail: bool = False) -> None:
            self.shapes: list[tuple] = []
            self.fail = fail

        def get_input_names(self):
            return ["x"]

        def run(self, inputs):
            if self.fail:
                raise RuntimeError("cuda out of memory")
            self.shapes.append(inputs["x"].shape)

    def test_every_shape_is_run_once(self) -> None:
        runner = self.Runner()
        shapes = [(1, 3, 48, 320), (2, 3, 48, 480)]

        self.assertTrue(warm_fixed_shapes(runner, shapes, "test"))
        self.assertEqual(shapes, runner.shapes)

    def test_a_failure_is_reported_not_raised(self) -> None:
        """Loading the model must not crash over a warmup. The result tells the
        caller whether to fall back to another backend."""
        self.assertFalse(
            warm_fixed_shapes(self.Runner(fail=True), [(1, 3, 48, 320)], "test")
        )

    def test_the_warmed_recognition_shapes_cover_every_bucket(self) -> None:
        """A bucket missing from warmup would put its tuning cost on a car."""
        warmed = {
            (batch, 3, LPR_RECOGNITION_HEIGHT, width)
            for batch in LPR_RECOGNITION_WARMUP_BATCHES
            for width in LPR_RECOGNITION_WIDTHS
        }

        for width in LPR_RECOGNITION_WIDTHS:
            self.assertIn((1, 3, LPR_RECOGNITION_HEIGHT, width), warmed)


if __name__ == "__main__":
    unittest.main()
