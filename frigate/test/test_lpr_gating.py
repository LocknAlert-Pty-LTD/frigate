"""When LPR runs on a tracked object, and when it stops.

Two changes, both driven by a gate that has to open before the driver reaches
it.

**It no longer waits for the tracker.** Every newly tracked object starts with
`position_changes` at 0 and `stationary` false, and LPR used to skip exactly that
state -- so nothing happened until a couple of frames after
`detect.min_initialized`. On a gate camera those are the frames worth having: the
plate is square-on and growing, and by the time the tracker has made up its mind
the car can already be at the barrier waiting on a read that never started. The
observed symptom was a log line per frame:

    Skipping LPR for non-stationary car object ... with no position changes.
    (Detected in 5 concurrent frames, threshold to run is 6 frames)

**It stops once a known plate matches.** Everything downstream has its answer at
that point, and a car waiting at a gate would otherwise be re-read on every frame
for as long as it sat there.

These tests drive `lpr_process` far enough to see whether it returned early,
using the plate detector as the tripwire: if it was called, the gating let the
frame through.
"""

import unittest

import numpy as np

from frigate.data_processing.common.license_plate.mixin import (
    LicensePlateProcessingMixin,
)


class PlateDetector:
    """Stands in for the YOLOv9 plate detector, and records being reached."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, image):
        self.calls += 1
        return []  # no plate, so the pass ends here


class Counter:
    """EventsPerSecond / InferenceSpeed stand-in."""

    def eps(self) -> float:
        return 0.0

    def update(self, *args) -> None:
        pass


class Value:
    value = 0.0


class Mixin(LicensePlateProcessingMixin):
    def __init__(self, camera: str = "gate_camera") -> None:
        self.camera = camera
        self.detector = PlateDetector()
        self.detected_license_plates = {}
        self.lp_objects = ["car", "motorcycle"]
        self.stationary_scan_duration = 5
        self.config = self.build_config(camera)
        self.lpr_config = self.config.lpr

        # metrics the method touches before any gating
        self.metrics = type(
            "Metrics", (), {"alpr_pps": Value(), "yolov9_lpr_pps": Value()}
        )()
        self.plates_rec_second = Counter()
        self.plates_det_second = Counter()
        self.plate_det_speed = Counter()
        self.plate_rec_speed = Counter()

    def build_config(self, camera: str):
        stationary = type("Stationary", (), {"threshold": 50})()
        detect = type(
            "Detect", (), {"fps": 5, "min_initialized": 4, "stationary": stationary}
        )()
        lpr = type("Lpr", (), {"min_area": 1000, "enabled": True})()
        objects = type("Objects", (), {"track": ["car"]})()
        motion = type("Motion", (), {"rasterized_mask": None})()
        camera_config = type(
            "Camera",
            (),
            {"detect": detect, "lpr": lpr, "objects": objects, "motion": motion},
        )()
        return type(
            "Config", (), {"cameras": {camera: camera_config}, "lpr": lpr}
        )()

    # the detector is reached only if the gating let the frame through
    def _detect_license_plate(self, camera, image):
        return self.detector(image)


def run(mixin: Mixin, **obj_data) -> None:
    """Drive lpr_process with one tracked object update."""
    data = {
        "id": "car-1",
        "camera": mixin.camera,
        "label": "car",
        "box": (100, 100, 400, 300),
        "position_changes": 0,
        "stationary": False,
        "motionless_count": 0,
        "frame_time": 1790923769.1,
    }
    data.update(obj_data)

    # a YUV frame large enough to crop the box out of
    frame = np.zeros((720 * 3 // 2, 1280), dtype=np.uint8)
    mixin.lpr_process(data, frame)


class TestStartsImmediately(unittest.TestCase):
    """The reported bug: nothing ran while the car was approaching."""

    def test_a_brand_new_moving_object_is_processed(self) -> None:
        """position_changes 0 and not stationary is the state every tracked
        object starts in, and is exactly what used to be skipped."""
        mixin = Mixin()

        run(mixin, position_changes=0, stationary=False)

        self.assertEqual(1, mixin.detector.calls)

    def test_every_frame_of_the_approach_is_processed(self) -> None:
        """Not once, and not every other one: a plate readable for only a few
        frames has to be read in those frames."""
        mixin = Mixin()

        for _ in range(8):
            run(mixin, position_changes=0, stationary=False)

        self.assertEqual(8, mixin.detector.calls)

    def test_a_moving_object_the_tracker_has_confirmed_is_processed(self) -> None:
        mixin = Mixin()

        run(mixin, position_changes=3, stationary=False)

        self.assertEqual(1, mixin.detector.calls)

    def test_a_stationary_object_is_processed(self) -> None:
        """A car stopped at the barrier is the best view there is."""
        mixin = Mixin()

        run(mixin, stationary=True, motionless_count=10)

        self.assertEqual(1, mixin.detector.calls)


class TestStopsOnceMatched(unittest.TestCase):
    def test_reading_stops_after_a_known_plate_matches(self) -> None:
        mixin = Mixin()
        run(mixin)
        self.assertEqual(1, mixin.detector.calls)

        mixin.detected_license_plates["car-1"] = {"known_match": "Raine"}
        run(mixin)

        self.assertEqual(1, mixin.detector.calls, "should not have read it again")

    def test_it_stays_stopped(self) -> None:
        """A car can wait at a gate for a long time."""
        mixin = Mixin()
        mixin.detected_license_plates["car-1"] = {"known_match": "Raine"}

        for _ in range(20):
            run(mixin)

        self.assertEqual(0, mixin.detector.calls)

    def test_an_unmatched_plate_does_not_stop_reading(self) -> None:
        """A plate that was read but matched nobody keeps being retried, which is
        the point: the next frame may be the readable one."""
        mixin = Mixin()
        mixin.detected_license_plates["car-1"] = {"plates": ["XYZ999"]}

        run(mixin)
        run(mixin)

        self.assertEqual(2, mixin.detector.calls)

    def test_another_car_is_unaffected(self) -> None:
        """State is per tracked object. Keyed on anything shared, one matched car
        would stop the gate reading every car behind it."""
        mixin = Mixin()
        mixin.detected_license_plates["car-1"] = {"known_match": "Raine"}

        run(mixin, id="car-2")

        self.assertEqual(1, mixin.detector.calls)


class TestOtherGatesStillApply(unittest.TestCase):
    def test_a_non_vehicle_is_ignored(self) -> None:
        mixin = Mixin()

        run(mixin, label="person")

        self.assertEqual(0, mixin.detector.calls)

    def test_a_long_stationary_object_is_dropped(self) -> None:
        """The existing limit: keep reading for stationary_scan_duration seconds
        after a car stops, then give up rather than grind on a parked car
        forever. At 5fps with a threshold of 50 this is 50 + 5*5 frames."""
        mixin = Mixin()

        run(mixin, stationary=True, motionless_count=50 + 5 * 5 + 1)

        self.assertEqual(0, mixin.detector.calls)

    def test_a_recently_stopped_object_is_still_read(self) -> None:
        """The window that covers a car stopped at the barrier."""
        mixin = Mixin()

        run(mixin, stationary=True, motionless_count=50 + 1)

        self.assertEqual(1, mixin.detector.calls)


if __name__ == "__main__":
    unittest.main()
