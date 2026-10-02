"""Can the liveness geometry tell a flat photo from a real face?

The whole approach rests on one claim: a plane maps between two views by a
homography and a 3D face does not. That claim is testable without a camera, by
projecting known geometry -- a flat sheet and a face-shaped point cloud -- through
the same pair of viewpoints and checking which one the planar fit explains.

These are the tests that decide whether the feature works at all. If the
separation here is small, no threshold will save it in the field.

Real-world calibration is still the operator's job: landmark detector noise on an
actual camera is not modelled here, and it eats into the margin these tests
measure.
"""

import unittest

import cv2
import numpy as np

from frigate.data_processing.common.face.liveness import (
    LivenessAnalyzer,
    measure_baselines,
    noise_floor,
    parallax_growth,
    planar_residual,
    screen_artifact_score,
    shape_deformation,
    viewpoint_change,
)

# A 68 point face, laid out to match the landmark model's ordering closely
# enough for the indices the code uses (eyes 36:48, mouth 48:68, nose 27:31).
# Coordinates are millimetres on a real head, z increasing toward the camera, so
# the nose genuinely stands proud of the cheeks.
def face_points_3d() -> np.ndarray:
    rng = np.random.default_rng(11)
    points = np.zeros((68, 3))

    # jaw and cheeks, a broad arc that recedes at the edges
    for i in range(17):
        angle = np.pi * (i / 16)
        points[i] = [-70 * np.cos(angle), 40 + 45 * np.sin(angle), -25 * abs(np.cos(angle))]

    # eyebrows
    for i in range(17, 27):
        side = -1 if i < 22 else 1
        points[i] = [side * (20 + (i % 5) * 8), -35, -5]

    # nose bridge down to the tip: the part that sticks out
    for i, offset in enumerate(range(27, 31)):
        points[offset] = [0, -25 + i * 12, 10 + i * 9]

    # nostrils
    for i, offset in enumerate(range(31, 36)):
        points[offset] = [-12 + i * 6, 18, 22]

    # eyes, left then right, each a small ring
    for eye, centre in ((range(36, 42), -32), (range(42, 48), 32)):
        for i, offset in enumerate(eye):
            angle = 2 * np.pi * (i / 6)
            points[offset] = [centre + 11 * np.cos(angle), -12 + 5 * np.sin(angle), -6]

    # mouth
    for i, offset in enumerate(range(48, 68)):
        angle = 2 * np.pi * (i / 20)
        points[offset] = [22 * np.cos(angle), 52 + 9 * np.sin(angle), 4]

    # a little asymmetry, so nothing passes by symmetry alone
    return points + rng.normal(0, 0.4, points.shape)


def photo_points_3d() -> np.ndarray:
    """The same face, printed: identical in x and y, flat in z."""
    points = face_points_3d()
    points[:, 2] = 0.0
    return points


def project(points: np.ndarray, yaw: float, pitch: float = 0.0, distance: float = 900.0) -> np.ndarray:
    """Perspective-project 3D points after rotating the subject.

    Perspective is the point: under an orthographic camera even a real face maps
    between views affinely, and there would be no parallax to find.
    """
    cy, sy = np.cos(yaw), np.sin(yaw)
    cp, sp = np.cos(pitch), np.sin(pitch)
    r_yaw = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    r_pitch = np.array([[1, 0, 0], [0, cp, -sp], [0, sp, cp]])

    rotated = points @ r_yaw.T @ r_pitch.T
    depth = distance - rotated[:, 2]
    focal = 1200.0

    return np.column_stack(
        [focal * rotated[:, 0] / depth, focal * rotated[:, 1] / depth]
    )


class TestPlanarResidualSeparatesFlatFromSolid(unittest.TestCase):
    """The core claim of the whole feature."""

    def setUp(self) -> None:
        self.face = face_points_3d()
        self.photo = photo_points_3d()

    def test_a_turned_photo_is_explained_by_a_flat_fit(self) -> None:
        """A plane under perspective *is* a homography, so the residual should be
        essentially zero no matter how far it is turned."""
        before = project(self.photo, yaw=0.0)
        after = project(self.photo, yaw=0.45)

        self.assertLess(planar_residual(before, after), 1e-6)

    def test_a_tilted_and_turned_photo_is_still_flat(self) -> None:
        """Waving the photo about on two axes does not create depth."""
        before = project(self.photo, yaw=-0.2, pitch=0.1)
        after = project(self.photo, yaw=0.4, pitch=-0.15)

        self.assertLess(planar_residual(before, after), 1e-6)

    def test_a_turned_face_is_not_explained_by_a_flat_fit(self) -> None:
        before = project(self.face, yaw=0.0)
        after = project(self.face, yaw=0.45)

        self.assertGreater(planar_residual(before, after), 0.012)

    def test_the_gap_between_face_and_photo_is_large(self) -> None:
        """The margin the default threshold sits inside. A narrow gap here means
        landmark noise on a real camera would swamp the signal."""
        face = planar_residual(project(self.face, 0.0), project(self.face, 0.45))
        photo = planar_residual(project(self.photo, 0.0), project(self.photo, 0.45))

        self.assertGreater(face, photo * 100)

    def test_parallax_grows_with_the_angle_turned(self) -> None:
        """More viewpoint change, more depth revealed -- which is why the code
        compares against the most distant view it has, not the last frame."""
        residuals = [
            planar_residual(project(self.face, 0.0), project(self.face, yaw))
            for yaw in (0.1, 0.25, 0.5)
        ]

        self.assertEqual(sorted(residuals), residuals)

    def test_a_face_that_only_moves_closer_reveals_little(self) -> None:
        """Approaching the camera head-on is close to a scale change, so it is
        weak evidence. The motion precondition exists for this case."""
        before = project(self.face, 0.0, distance=1200)
        after = project(self.face, 0.0, distance=700)

        self.assertLess(planar_residual(before, after), 0.012)

    def test_mismatched_or_tiny_inputs_are_not_treated_as_evidence(self) -> None:
        points = project(self.face, 0.0)

        self.assertEqual(0.0, planar_residual(points[:3], points[:3]))
        self.assertEqual(0.0, planar_residual(points, points[:10]))


class TestViewpointChange(unittest.TestCase):
    """The precondition: has anything informative happened yet?"""

    def setUp(self) -> None:
        self.face = face_points_3d()
        self.photo = photo_points_3d()

    def test_a_still_face_shows_no_change(self) -> None:
        points = project(self.face, 0.0)

        self.assertLess(viewpoint_change(points, points), 1e-9)

    def test_sliding_across_the_frame_is_not_a_change_of_view(self) -> None:
        """Translation reveals no new angle, so it must not license a verdict.
        Otherwise a photo carried past the camera would look conclusive."""
        before = project(self.face, 0.0)
        after = before + np.array([60.0, 25.0])

        self.assertLess(viewpoint_change(before, after), 0.02)

    def test_walking_toward_the_camera_is_barely_a_change_of_view(self) -> None:
        """Approaching head-on is close to a uniform scale, so it reveals little
        and must not be enough on its own."""
        before = project(self.face, 0.0, distance=1200)
        after = project(self.face, 0.0, distance=700)

        self.assertLess(viewpoint_change(before, after), 0.02)

    def test_turning_the_head_is_a_change_of_view(self) -> None:
        before = project(self.face, 0.0)
        after = project(self.face, 0.4)

        self.assertGreater(viewpoint_change(before, after), 0.02)

    def test_turning_a_photo_also_counts_as_a_change_of_view(self) -> None:
        """Deliberate. This says only "the view changed enough to be
        informative"; whether depth was revealed is depth_ratio's job. If a
        turning photo scored zero here it would be filed as inconclusive, and a
        clear-cut spoof would look like missing data.
        """
        before = project(self.photo, 0.0)
        after = project(self.photo, 0.45)

        self.assertGreater(viewpoint_change(before, after), 0.02)


class TestParallaxGrowth(unittest.TestCase):
    """The primary signal, and the reason it is a growth rather than a level.

    Landmark jitter is not explainable by a homography either, so it inflates the
    planar residual for a photo exactly as depth does for a face. Growth between
    two baselines cancels that offset. These tests pin both the separation and
    the noise robustness that motivated the design.
    """

    def setUp(self) -> None:
        self.face = face_points_3d()
        self.photo = photo_points_3d()
        self.threshold = LivenessAnalyzer().depth_growth_threshold

    def track(self, points_3d: np.ndarray, yaws, noise: float = 0.0, seed: int = 0):
        rng = np.random.default_rng(seed)
        return [
            project(points_3d, yaw) + rng.normal(0, noise, (68, 2)) for yaw in yaws
        ]

    def growth(self, points_3d: np.ndarray, yaws, noise: float = 0.0, seed: int = 0):
        return parallax_growth(
            measure_baselines(self.track(points_3d, yaws, noise, seed))
        )

    TURN = (0.0, 0.1, 0.2, 0.35)

    def test_a_turning_face_grows(self) -> None:
        self.assertGreater(self.growth(self.face, self.TURN), self.threshold)

    def test_a_turning_photo_does_not_grow(self) -> None:
        """The attack. A plane's residual is zero at every baseline, so widening
        the baseline adds nothing."""
        self.assertLess(self.growth(self.photo, self.TURN), self.threshold)

    def test_a_still_face_does_not_grow(self) -> None:
        """No new angle, no parallax to find. Correctly withheld rather than
        passed -- the cost of proving presence instead of detecting fakery."""
        self.assertLess(self.growth(self.face, (0.0, 0.0, 0.0, 0.0)), self.threshold)

    def test_separation_holds_under_landmark_jitter(self) -> None:
        """The test that rejected the previous design.

        An earlier version divided the planar residual by the total observed
        change. That ratio reached ~0.9 for a photo at 1px of jitter, above a real
        face, so a photo would have been accepted. Growth keeps the two apart
        across the range a real detector produces.
        """
        for noise in (0.0, 0.5, 1.0, 2.0, 3.0):
            for seed in range(6):
                face = self.growth(self.face, self.TURN, noise, seed)
                photo = self.growth(self.photo, self.TURN, noise, seed)

                self.assertGreater(face, self.threshold, f"face at {noise}px, seed {seed}")
                self.assertLess(photo, self.threshold, f"photo at {noise}px, seed {seed}")

    def test_jitter_alone_never_manufactures_depth_while_measurable(self) -> None:
        """The dangerous direction, over the range where a verdict is allowed.

        Beyond that range growth alone is *not* sufficient -- at 4px of jitter a
        photo was measured at 0.012, above the threshold -- which is exactly why
        the analyzer refuses to judge once the noise floor is too high. That
        refusal is covered in TestRefusesToJudgeWhenTooNoisy; here the claim is
        only that growth is trustworthy while the instrument is.
        """
        analyzer = LivenessAnalyzer()

        for yaws in (self.TURN, (0.0, 0.0, 0.0, 0.0), (0.0, 0.05, 0.1, 0.15)):
            for noise in (1.0, 2.0, 3.0):
                for seed in range(6):
                    baselines = measure_baselines(
                        self.track(self.photo, yaws, noise, seed)
                    )

                    if noise_floor(baselines) > analyzer.max_noise_floor:
                        continue  # would be refused as unmeasurable, not passed

                    self.assertLess(
                        parallax_growth(baselines),
                        self.threshold,
                        f"photo yaws={yaws} noise={noise} seed={seed}",
                    )


    def test_growth_needs_two_baselines(self) -> None:
        """Two frames give one baseline, which is a level and not a growth: there
        is no noise floor to subtract."""
        self.assertEqual(0.0, parallax_growth([]))
        self.assertEqual(
            0.0, parallax_growth(measure_baselines(self.track(self.face, (0.0, 0.35))))
        )

    def test_measure_baselines_needs_a_pair(self) -> None:
        self.assertEqual([], measure_baselines([]))
        self.assertEqual([], measure_baselines([project(self.face, 0.0)]))

    def test_every_earlier_view_is_compared_against_the_latest(self) -> None:
        baselines = measure_baselines(self.track(self.face, self.TURN))

        self.assertEqual(3, len(baselines))
        # The earliest frame differs most from the latest, so baselines narrow as
        # the list advances. The pair at each end is what growth is taken between.
        viewpoints = [b.viewpoint for b in baselines]
        self.assertEqual(sorted(viewpoints, reverse=True), viewpoints)


class TestNoiseFloor(unittest.TestCase):
    """The track's own estimate of how precise its landmarks are."""

    def setUp(self) -> None:
        self.face = face_points_3d()

    def baselines(self, noise: float, seed: int = 0):
        rng = np.random.default_rng(seed)
        shapes = [
            project(self.face, yaw) + rng.normal(0, noise, (68, 2))
            for yaw in (0.0, 0.1, 0.2, 0.35)
        ]
        return measure_baselines(shapes)

    def test_clean_landmarks_report_a_low_floor(self) -> None:
        """With no jitter the narrowest baseline still holds a little real
        parallax, so this is not exactly zero -- but it is small."""
        self.assertLess(noise_floor(self.baselines(0.0)), 0.03)

    def test_the_floor_rises_with_jitter(self) -> None:
        floors = [noise_floor(self.baselines(n, seed=3)) for n in (0.0, 1.0, 2.0, 4.0)]

        self.assertEqual(sorted(floors), floors)

    def test_the_floor_grows_with_jitter_at_a_usable_rate(self) -> None:
        """Roughly 0.02 per pixel of jitter on top of whatever real parallax the
        narrowest baseline already holds, which is what makes a fixed cap
        meaningful. Pinned loosely: the exact rate depends on the face geometry,
        and only the order of magnitude justifies the default."""
        clean = noise_floor(self.baselines(0.0))

        self.assertAlmostEqual(
            clean + 0.02, noise_floor(self.baselines(1.0, seed=9)), delta=0.02
        )
        self.assertAlmostEqual(
            clean + 0.08, noise_floor(self.baselines(4.0, seed=9)), delta=0.04
        )

    def test_no_baselines_means_no_floor(self) -> None:
        self.assertEqual(0.0, noise_floor([]))


class TestRefusesToJudgeWhenTooNoisy(unittest.TestCase):
    """The guard that keeps the feature honest.

    At 6px of landmark jitter a real face and a photo both grow by about 0.008:
    no separation whatsoever. A verdict there would be a coin toss presented as a
    security control, so the analyzer declines instead -- and declining withholds
    the name.
    """

    def setUp(self) -> None:
        self.analyzer = LivenessAnalyzer()
        self.face = face_points_3d()
        self.photo = photo_points_3d()

    def feed(self, points_3d: np.ndarray, noise: float, seed: int = 0):
        rng = np.random.default_rng(seed)
        verdict = None

        for yaw in (0.0, 0.1, 0.2, 0.35):
            verdict = self.analyzer.observe(
                "obj",
                project(points_3d, yaw) + rng.normal(0, noise, (68, 2)),
                crop=None,
            )

        return verdict

    def test_a_clean_real_face_is_accepted(self) -> None:
        """Four frames, so the verdict reads "already established": depth was
        proven on the third and is not re-litigated on the fourth."""
        verdict = self.feed(self.face, noise=0.5)

        self.assertTrue(verdict.is_live)
        self.assertTrue(verdict.conclusive)
        self.assertFalse(verdict.blocks_recognition)

    def test_a_very_noisy_real_face_is_refused_rather_than_guessed(self) -> None:
        verdict = self.feed(self.face, noise=6.0)

        self.assertFalse(verdict.conclusive)
        self.assertEqual("landmarks too imprecise to judge", verdict.reason)
        self.assertTrue(verdict.blocks_recognition)

    def test_a_very_noisy_photo_is_refused_not_accepted(self) -> None:
        """The attack this guard closes: at high jitter a photo's growth can clear
        the threshold on its own."""
        verdict = self.feed(self.photo, noise=6.0)

        self.assertTrue(verdict.blocks_recognition)
        self.assertEqual("landmarks too imprecise to judge", verdict.reason)

    def test_no_photo_is_ever_accepted_at_any_jitter_level(self) -> None:
        """The property that actually matters, swept over the whole range: either
        the photo is caught, or the analyzer admits it cannot tell. It is never
        called live."""
        for noise in (0.0, 1.0, 2.0, 3.0, 4.0, 6.0, 9.0):
            for seed in range(5):
                self.analyzer = LivenessAnalyzer()
                verdict = self.feed(self.photo, noise, seed)

                self.assertTrue(
                    verdict.blocks_recognition,
                    f"photo passed at noise={noise} seed={seed}: {verdict.reason} "
                    f"({verdict.signals})",
                )

class TestShapeDeformation(unittest.TestCase):
    def test_a_rigid_sequence_does_not_deform(self) -> None:
        """A photo moved around: every frame the same shape, so no deformation
        however much it is waved."""
        face = face_points_3d()
        frames = [project(face, yaw) for yaw in (0.0, 0.1, 0.2)]

        self.assertLess(shape_deformation(frames), 0.05)

    def test_a_blink_deforms(self) -> None:
        face = face_points_3d()
        frames = [project(face, 0.0)]

        blinked = face.copy()
        blinked[36:48, 1] = blinked[36:48, 1].mean()  # eyelids together
        frames.append(project(blinked, 0.0))

        self.assertGreater(shape_deformation(frames), 0.05)

    def test_an_open_mouth_deforms(self) -> None:
        face = face_points_3d()
        frames = [project(face, 0.0)]

        talking = face.copy()
        talking[58:66, 1] += 22  # lower lip drops
        frames.append(project(talking, 0.0))

        self.assertGreater(shape_deformation(talking_frames := frames), 0.05)

    def test_a_single_frame_cannot_show_deformation(self) -> None:
        self.assertEqual(0.0, shape_deformation([project(face_points_3d(), 0.0)]))


class TestScreenArtifactScore(unittest.TestCase):
    def test_natural_texture_scores_clean(self) -> None:
        rng = np.random.default_rng(3)
        # 1/f-ish noise, as natural images have
        image = cv2.GaussianBlur(
            rng.integers(0, 256, (112, 112), dtype=np.uint8), (5, 5), 0
        )

        self.assertGreater(screen_artifact_score(image), 0.9)

    def test_a_strong_pixel_grid_scores_dirty(self) -> None:
        """A display's grid beating against the sensor: a single dominant
        frequency far above its neighbours."""
        y, x = np.mgrid[0:112, 0:112]
        grid = 128 + 100 * np.sin(2 * np.pi * x / 4) * np.sin(2 * np.pi * y / 4)

        self.assertLess(screen_artifact_score(grid.astype(np.uint8)), 0.5)

    def test_a_crop_too_small_to_judge_is_not_condemned(self) -> None:
        """Absent evidence must not read as a spoof here; the geometry checks are
        what fail closed."""
        self.assertEqual(1.0, screen_artifact_score(np.zeros((16, 16), dtype=np.uint8)))

    def test_missing_and_empty_input(self) -> None:
        self.assertEqual(1.0, screen_artifact_score(None))
        self.assertEqual(1.0, screen_artifact_score(np.zeros((0, 0), dtype=np.uint8)))

    def test_a_colour_crop_is_accepted(self) -> None:
        rng = np.random.default_rng(5)
        colour = rng.integers(0, 256, (112, 112, 3), dtype=np.uint8)

        self.assertIsInstance(screen_artifact_score(colour), float)


class TestAnalyzerDecisions(unittest.TestCase):
    """The verdicts, which are what the caller acts on."""

    def setUp(self) -> None:
        self.analyzer = LivenessAnalyzer()
        self.face = face_points_3d()
        self.photo = photo_points_3d()

    def feed(self, points_3d: np.ndarray, yaws, object_id: str = "obj"):
        verdict = None
        for yaw in yaws:
            verdict = self.analyzer.observe(
                object_id, project(points_3d, yaw), crop=None
            )
        return verdict

    def test_a_moving_face_is_judged_live(self) -> None:
        verdict = self.feed(self.face, (0.0, 0.2, 0.45))

        self.assertTrue(verdict.is_live)
        self.assertTrue(verdict.conclusive)
        self.assertFalse(verdict.blocks_recognition)

    def test_a_photo_waved_at_the_camera_is_judged_not_live(self) -> None:
        """The attack this feature exists to stop."""
        verdict = self.feed(self.photo, (0.0, 0.2, 0.45))

        self.assertFalse(verdict.is_live)
        self.assertTrue(verdict.conclusive, "moved enough to have shown depth")
        self.assertEqual("face moved as a flat surface would", verdict.reason)
        self.assertTrue(verdict.blocks_recognition)

    def test_a_photo_held_perfectly_still_is_not_a_pass(self) -> None:
        """Holding still avoids being *caught*, but it cannot produce a pass:
        the checks prove presence rather than detect fakery, so absent evidence
        stays closed. This is the property an attacker cannot work around."""
        verdict = self.feed(self.photo, (0.0, 0.0, 0.0, 0.0))

        self.assertFalse(verdict.is_live)
        self.assertFalse(verdict.conclusive)
        self.assertTrue(verdict.blocks_recognition)

    def test_a_still_real_face_is_also_withheld(self) -> None:
        """The cost of failing closed, stated as a test so it is not a surprise:
        someone standing motionless is not recognised either. A trained
        anti-spoofing model is what resolves this case from a single frame."""
        verdict = self.feed(self.face, (0.0, 0.0, 0.0, 0.0))

        self.assertTrue(verdict.blocks_recognition)
        self.assertFalse(verdict.conclusive)

    def test_one_frame_is_never_enough(self) -> None:
        verdict = self.feed(self.face, (0.0,))

        self.assertFalse(verdict.conclusive)
        self.assertEqual("not enough frames yet", verdict.reason)

    def test_a_blink_alone_establishes_liveness(self) -> None:
        """No head movement needed: paper does not blink."""
        blinked = self.face.copy()
        blinked[36:48, 1] = blinked[36:48, 1].mean()

        for points in (self.face, self.face, blinked):
            verdict = self.analyzer.observe("obj", project(points, 0.0), crop=None)

        self.assertTrue(verdict.is_live)
        self.assertEqual("face changed shape", verdict.reason)

    def test_liveness_once_established_is_not_relitigated(self) -> None:
        """A person who has proven themselves should not be dropped the moment
        they stop moving on the walk to the gate."""
        self.feed(self.face, (0.0, 0.2, 0.45))

        verdict = self.analyzer.observe("obj", project(self.face, 0.45), crop=None)

        self.assertTrue(verdict.is_live)
        self.assertEqual("already established", verdict.reason)

    def test_a_screen_looking_frame_overrides_an_established_track(self) -> None:
        """Appearance is checked before the established shortcut, so a track
        cannot carry an earlier pass over a frame that now looks reproduced."""
        self.feed(self.face, (0.0, 0.2, 0.45))

        verdict = self.analyzer.observe(
            "obj", project(self.face, 0.45), crop=None, model_score=0.01
        )

        self.assertFalse(verdict.is_live)
        self.assertTrue(verdict.conclusive)
        self.assertEqual("looks like a screen or a print", verdict.reason)

    def test_a_model_verdict_of_spoof_blocks_a_real_looking_face(self) -> None:
        verdict = self.analyzer.observe(
            "obj", project(self.face, 0.0), crop=None, model_score=0.02
        )

        self.assertTrue(verdict.blocks_recognition)
        self.assertEqual("looks like a screen or a print", verdict.reason)

    def test_a_model_verdict_of_live_still_needs_the_geometry(self) -> None:
        """The model is not a bypass: a high model score on a flat, moving
        surface is still refused."""
        for yaw in (0.0, 0.2, 0.45):
            verdict = self.analyzer.observe(
                "obj", project(self.photo, yaw), crop=None, model_score=0.99
            )

        self.assertFalse(verdict.is_live)
        self.assertEqual("face moved as a flat surface would", verdict.reason)

    def test_missing_landmarks_are_inconclusive_not_a_pass(self) -> None:
        verdict = self.analyzer.observe("obj", None, crop=None)

        self.assertFalse(verdict.conclusive)
        self.assertTrue(verdict.blocks_recognition)

    def test_too_few_landmarks_are_refused(self) -> None:
        """A 5 point set cannot support this: 4 points define a homography
        exactly, so a plane and a face would fit equally well."""
        verdict = self.analyzer.observe("obj", np.zeros((5, 2)), crop=None)

        self.assertFalse(verdict.conclusive)
        self.assertEqual("no landmarks for this frame", verdict.reason)

    def test_tracks_are_independent(self) -> None:
        self.feed(self.face, (0.0, 0.2, 0.45), object_id="live-person")
        verdict = self.feed(self.photo, (0.0, 0.2, 0.45), object_id="photo")

        self.assertFalse(verdict.is_live)
        self.assertTrue(self.analyzer.tracks["live-person"].established)

    def test_forget_releases_the_track(self) -> None:
        """Called when an object ends. Without it this dict grows for the life of
        the process."""
        self.feed(self.face, (0.0, 0.2, 0.45))
        self.assertIn("obj", self.analyzer.tracks)

        self.analyzer.forget("obj")

        self.assertNotIn("obj", self.analyzer.tracks)

    def test_forgetting_an_unknown_track_is_harmless(self) -> None:
        self.analyzer.forget("never-seen")

    def test_observations_are_bounded(self) -> None:
        """A person loitering in frame must not grow this without limit."""
        analyzer = LivenessAnalyzer(max_observations=4)

        for i in range(40):
            analyzer.observe("obj", project(self.face, 0.01 * i), crop=None)

        self.assertEqual(4, len(analyzer.tracks["obj"].observations))


if __name__ == "__main__":
    unittest.main()
