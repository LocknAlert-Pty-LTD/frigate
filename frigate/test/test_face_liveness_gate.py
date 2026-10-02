"""The gate: what the face processor does with a liveness verdict.

Deciding is the analyzer's job; this is about acting on the decision, and the
property under test is that it fails closed. Every way of not knowing -- no
landmarks, landmarks too imprecise, too few frames yet -- has to withhold the
name, because the alternative is a photograph opening a gate.

`__is_live` is exercised directly. Constructing a FaceRealTimeProcessor loads the
detection, landmark and embedding models and opens MQTT and inter-process
channels, none of which has anything to do with the decision being tested.
"""

import unittest

import numpy as np

from frigate.config.classification import FaceLivenessConfig, FaceRecognitionConfig
from frigate.data_processing.common.face.liveness import (
    LivenessAnalyzer,
    LivenessSignals,
    LivenessVerdict,
)
from frigate.data_processing.real_time.face import FaceRealTimeProcessor


class Detector:
    def __init__(self, landmarks) -> None:
        self.landmarks = landmarks
        self.calls = 0

    def get_dense_landmarks(self, _frame):
        self.calls += 1
        return self.landmarks


class Analyzer:
    """Stands in for LivenessAnalyzer so each verdict can be forced."""

    def __init__(self, forced: LivenessVerdict) -> None:
        self.forced = forced
        self.seen: list[tuple] = []
        self.forgotten: list[str] = []

    def observe(self, object_id, landmarks, crop, model_score=None):
        self.seen.append((object_id, landmarks, crop))
        return self.forced

    def forget(self, object_id):
        self.forgotten.append(object_id)


def verdict(is_live: bool, conclusive: bool, reason: str = "test") -> LivenessVerdict:
    return LivenessVerdict(
        is_live=is_live,
        score=1.0 if is_live else 0.0,
        conclusive=conclusive,
        reason=reason,
        signals=LivenessSignals(),
    )


# A default of None could not express "the detector returned nothing", which is
# one of the cases under test.
DEFAULT_LANDMARKS = object()


def processor(analyzer, landmarks=DEFAULT_LANDMARKS) -> FaceRealTimeProcessor:
    instance = FaceRealTimeProcessor.__new__(FaceRealTimeProcessor)
    instance.liveness = analyzer
    instance.face_detector = Detector(
        np.zeros((68, 2)) if landmarks is DEFAULT_LANDMARKS else landmarks
    )
    return instance


def is_live(instance, object_id="obj") -> bool:
    return instance._FaceRealTimeProcessor__is_live(
        object_id, np.zeros((112, 112, 3), dtype=np.uint8)
    )


class TestFailsClosed(unittest.TestCase):
    def test_a_live_conclusive_verdict_passes(self) -> None:
        self.assertTrue(is_live(processor(Analyzer(verdict(True, True)))))

    def test_a_conclusive_spoof_is_withheld(self) -> None:
        self.assertFalse(is_live(processor(Analyzer(verdict(False, True)))))

    def test_an_inconclusive_verdict_is_withheld(self) -> None:
        """Not yet knowing is not permission. A photo held still lands here."""
        self.assertFalse(is_live(processor(Analyzer(verdict(False, False)))))

    def test_live_but_inconclusive_is_still_withheld(self) -> None:
        """Both halves are required. A verdict should never be live without being
        conclusive, and if one is ever constructed this must not accept it."""
        self.assertFalse(is_live(processor(Analyzer(verdict(True, False)))))


class TestWiring(unittest.TestCase):
    def test_the_analyzer_sees_the_object_id_and_the_crop(self) -> None:
        """Evidence has to accumulate against the right person. Keying on
        anything shared would let one live face vouch for everyone in frame."""
        analyzer = Analyzer(verdict(True, True))
        instance = processor(analyzer)

        is_live(instance, object_id="person-42")

        self.assertEqual(1, len(analyzer.seen))
        object_id, landmarks, crop = analyzer.seen[0]
        self.assertEqual("person-42", object_id)
        self.assertEqual((68, 2), landmarks.shape)
        self.assertIsNotNone(crop, "the crop is needed for the appearance check")

    def test_landmarks_come_from_the_face_crop(self) -> None:
        analyzer = Analyzer(verdict(True, True))
        instance = processor(analyzer)

        is_live(instance)

        self.assertEqual(1, instance.face_detector.calls)

    def test_absent_landmarks_are_passed_along_not_swallowed(self) -> None:
        """The analyzer decides what missing landmarks mean, so the processor must
        not quietly skip the check when the detector returns nothing."""
        analyzer = Analyzer(verdict(False, False))
        instance = processor(analyzer, landmarks=None)

        self.assertFalse(is_live(instance))
        self.assertEqual(1, len(analyzer.seen))
        self.assertIsNone(analyzer.seen[0][1])


class TestDisabled(unittest.TestCase):
    def test_disabling_liveness_passes_everything(self) -> None:
        """The documented escape hatch, and the one case that does not fail
        closed. A photo is recognised exactly like a real face here."""
        self.assertTrue(is_live(processor(None)))

    def test_disabled_config_is_expressible(self) -> None:
        config = FaceRecognitionConfig(liveness=FaceLivenessConfig(enabled=False))

        self.assertFalse(config.liveness.enabled)

    def test_liveness_is_on_by_default(self) -> None:
        self.assertTrue(FaceRecognitionConfig().liveness.enabled)


class TestConfigReachesTheAnalyzer(unittest.TestCase):
    """A threshold that silently failed to reach the analyzer would leave the
    operator tuning a number that does nothing."""

    def test_every_configured_threshold_is_applied(self) -> None:
        config = FaceLivenessConfig(
            min_frames=7,
            depth_growth_threshold=0.5,
            min_viewpoint=0.6,
            max_noise_floor=0.7,
            deformation_threshold=0.8,
            appearance_threshold=0.9,
        )

        analyzer = LivenessAnalyzer(
            min_frames=config.min_frames,
            depth_growth_threshold=config.depth_growth_threshold,
            min_viewpoint=config.min_viewpoint,
            max_noise_floor=config.max_noise_floor,
            deformation_threshold=config.deformation_threshold,
            appearance_threshold=config.appearance_threshold,
        )

        self.assertEqual(7, analyzer.min_frames)
        self.assertEqual(0.5, analyzer.depth_growth_threshold)
        self.assertEqual(0.6, analyzer.min_viewpoint)
        self.assertEqual(0.7, analyzer.max_noise_floor)
        self.assertEqual(0.8, analyzer.deformation_threshold)
        self.assertEqual(0.9, analyzer.appearance_threshold)

    def test_the_config_defaults_match_the_analyzer_defaults(self) -> None:
        """Two places hold the same measured numbers; a drift between them would
        mean the documented default is not the one in force."""
        config = FaceLivenessConfig()
        analyzer = LivenessAnalyzer()

        self.assertEqual(analyzer.min_frames, config.min_frames)
        self.assertEqual(analyzer.depth_growth_threshold, config.depth_growth_threshold)
        self.assertEqual(analyzer.min_viewpoint, config.min_viewpoint)
        self.assertEqual(analyzer.max_noise_floor, config.max_noise_floor)
        self.assertEqual(analyzer.deformation_threshold, config.deformation_threshold)
        self.assertEqual(analyzer.appearance_threshold, config.appearance_threshold)


class TestReleasesState(unittest.TestCase):
    def test_an_ended_object_is_forgotten(self) -> None:
        """Landmark history is held per object; without this it grows for the life
        of the process."""
        analyzer = Analyzer(verdict(True, True))
        instance = processor(analyzer)
        instance.person_face_history = {}
        instance.camera_current_people = {}

        instance.expire_object("obj", "front_door")

        self.assertEqual(["obj"], analyzer.forgotten)

    def test_expiry_works_with_liveness_disabled(self) -> None:
        instance = processor(None)
        instance.person_face_history = {}
        instance.camera_current_people = {}

        instance.expire_object("obj", "front_door")


if __name__ == "__main__":
    unittest.main()
