"""Reporting which execution provider the detector actually loaded on.

The dashboard could not say. The Object detection card showed the GPU name and
an inference time, and the only backend named anywhere on that screen was the
ffmpeg hwaccel row -- which says CUDA because it decodes video there. Reading
that as the detector backend is an easy and wrong conclusion, and it was reached
twice on a machine whose detector was really on TensorRT.

It cannot be derived from config. ONNX Runtime tries providers in order and the
winner is only known once the session exists, which happens in the detector
subprocess. So the subprocess reports it through a shared slot, and the stats
pass it on.

Best effort by design: a detector that does not load through
get_optimized_runner registers nothing, and the field is omitted rather than
guessed at.
"""

import unittest
from multiprocessing import Array
from unittest.mock import patch

from frigate.object_detection.base import AsyncDetectorRunner, DetectorRunner
from frigate.stats.util import get_detector_stats

SNAPSHOT = "frigate.detectors.detection_runners.snapshot_loaded_devices"


def runner(device=None) -> DetectorRunner:
    """A DetectorRunner without starting a process or loading a model."""
    instance = DetectorRunner.__new__(DetectorRunner)
    instance.device = device
    return instance


class TestBothRunnersAcceptTheSlot(unittest.TestCase):
    """start_or_restart passes it positionally to whichever runner it builds, so
    a signature mismatch is a TypeError at detector startup."""

    def test_the_sync_runner_takes_it(self) -> None:
        import inspect

        self.assertIn("device", inspect.signature(DetectorRunner.__init__).parameters)

    def test_the_async_runner_takes_it(self) -> None:
        import inspect

        self.assertIn(
            "device", inspect.signature(AsyncDetectorRunner.__init__).parameters
        )

    def test_it_is_optional_on_both(self) -> None:
        """Defaulted so a caller constructing a runner directly is unaffected."""
        import inspect

        for cls in (DetectorRunner, AsyncDetectorRunner):
            parameter = inspect.signature(cls.__init__).parameters["device"]
            self.assertIsNot(parameter.default, inspect.Parameter.empty, cls.__name__)


class TestReportDevice(unittest.TestCase):
    def test_the_loaded_provider_is_written_to_the_slot(self) -> None:
        slot = Array("c", 32)

        with patch(SNAPSHOT, return_value={"/model.onnx": ("yologeneric", "TensorRT")}):
            runner(slot).report_device()

        self.assertEqual(b"TensorRT", slot.value)

    def test_cuda_is_reported_just_as_plainly(self) -> None:
        """The point is to show what is true, not to flatter the setup."""
        slot = Array("c", 32)

        with patch(SNAPSHOT, return_value={"/model.onnx": ("yologeneric", "CUDA")}):
            runner(slot).report_device()

        self.assertEqual(b"CUDA", slot.value)

    def test_nothing_registered_leaves_the_slot_empty(self) -> None:
        """A detector that does not load through get_optimized_runner -- edgetpu,
        hailo, memryx. The stats then omit the field instead of inventing one."""
        slot = Array("c", 32)

        with patch(SNAPSHOT, return_value={}):
            runner(slot).report_device()

        self.assertEqual(b"", slot.value)

    def test_no_slot_at_all_is_harmless(self) -> None:
        """The parameter is optional, so a runner built without one must not
        raise on the way to serving detections."""
        with patch(SNAPSHOT, return_value={"/m.onnx": ("yologeneric", "TensorRT")}):
            runner(None).report_device()

    def test_a_failure_does_not_take_the_detector_down(self) -> None:
        """This is diagnostics. It runs between loading the model and serving
        the first frame, and must never be what stops that happening."""
        slot = Array("c", 32)

        with patch(SNAPSHOT, side_effect=RuntimeError("boom")):
            runner(slot).report_device()

        self.assertEqual(b"", slot.value)

    def test_a_long_provider_name_is_truncated_rather_than_overflowing(self) -> None:
        """A fixed 32 byte slot; an unmapped provider falls back to its raw ONNX
        Runtime name, which can be longer."""
        slot = Array("c", 32)
        long_name = "SomeVeryLongExecutionProviderName" * 2

        with patch(SNAPSHOT, return_value={"/m.onnx": ("yologeneric", long_name)}):
            runner(slot).report_device()

        self.assertEqual(31, len(slot.value))
        self.assertTrue(long_name.startswith(slot.value.decode()))


class Detector:
    """Stands in for ObjectDetectProcess in the stats call."""

    def __init__(self, device=None) -> None:
        self.avg_inference_speed = type("V", (), {"value": 0.00482})()
        self.detection_start = type("V", (), {"value": 0.0})()
        self.detect_process = type("P", (), {"pid": 1234})()
        self.detector_config = type("C", (), {"type": "onnx"})()

        if device is not None:
            self.device = device


def detector_stats(detector: Detector) -> dict:
    with patch("frigate.stats.util.get_hardware_temperatures", return_value=[]):
        return get_detector_stats({"detectors": {"onnx": detector}})["onnx"]


class TestStatsCarryTheProvider(unittest.TestCase):
    def test_a_reported_provider_reaches_the_stats(self) -> None:
        slot = Array("c", 32)
        slot.value = b"TensorRT"

        self.assertEqual("TensorRT", detector_stats(Detector(slot))["device"])

    def test_an_empty_slot_omits_the_field(self) -> None:
        """Absent rather than empty, so the UI can simply not render it."""
        self.assertNotIn("device", detector_stats(Detector(Array("c", 32))))

    def test_a_detector_without_the_attribute_omits_the_field(self) -> None:
        """Covers an older process object, or a detector type that never gained
        the slot."""
        self.assertNotIn("device", detector_stats(Detector()))

    def test_the_rest_of_the_stats_are_unchanged(self) -> None:
        stats = detector_stats(Detector(Array("c", 32)))

        self.assertEqual(4.82, stats["inference_speed"])
        self.assertEqual(1234, stats["pid"])


class TestDashboardShowsIt(unittest.TestCase):
    """The row is assembled in health.ts, so this pins the contract it needs."""

    def setUp(self) -> None:
        import pathlib

        source = pathlib.Path("/opt/frigate/web/src/utils/health.ts")

        if not source.is_file():
            self.skipTest("web sources are not present in this image")

        self.source = source.read_text(encoding="utf-8")

    def test_the_detail_includes_the_reported_provider(self) -> None:
        self.assertIn("stats.detectors[name]?.device", self.source)

    def test_duplicates_are_collapsed(self) -> None:
        """Several runners of one model usually share a provider, and repeating
        it once per runner would read as noise."""
        self.assertIn("new Set(", self.source)

    def test_an_absent_provider_leaves_the_row_as_it_was(self) -> None:
        """filter(Boolean) on the assembled parts, so no stray separator."""
        self.assertIn(".filter(Boolean)", self.source)


if __name__ == "__main__":
    unittest.main()
