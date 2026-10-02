"""Liveness checks: evidence that a face belongs to a person who is present.

Face recognition on its own cannot tell a person from a picture of them. A
printed photo or a phone screen held up to the camera produces an embedding close
enough to the real thing to match at full confidence, so recognition alone must
never open a gate.

What separates a photo from a person is not how the face *looks* -- a good photo
looks right -- but what it *is*:

1. **A photo is flat.** Any planar surface, seen from any angle, maps between two
   views by a homography. A real face is not planar, so when the head turns, the
   nose and the ears shift by different amounts and no single homography accounts
   for all of it. That leftover is parallax, and parallax is structure.

2. **A photo does not move by itself.** Faces blink and change expression. A
   still image's landmarks hold their shape no matter how the paper is waved.

3. **A photo has been through a display or a printer**, which leaves traces:
   halftone dots, a screen's pixel grid beating against the sensor grid.

The first two are measured here from landmark geometry across frames and need no
extra model. The third is what an optional trained anti-spoofing model is for;
`screen_artifact_score` is a weaker stand-in when none is configured.

None of 1-3 is defeated by holding the photo still. A still photo simply never
produces the evidence, and no evidence means not live: these checks prove presence
rather than hunt for fakery, so the safe answer is the default rather than
something an attacker can arrange.

## Why growth, and not the residual itself

The obvious test is "is the planar-fit residual large?". It does not survive
contact with a real landmark detector. Landmark jitter is itself unexplainable by
a homography, so it inflates the residual for a photo exactly as depth does for a
face. Measured on projected geometry with 1px of jitter, a photo's residual
reaches 0.022 while a real face turned 8 degrees sits at 0.030 -- no usable
margin. Normalising by the total observed change fares worse still: that ratio
climbs to ~0.9 for both, and at 1px a photo can outscore a real face.

What does survive is how the residual *grows* as the baseline widens. Jitter
contributes a roughly constant offset at every baseline, so it cancels in the
difference, while genuine parallax grows with the change in viewing angle:

    jitter    face, 20 deg turn    photo, 20 deg turn    still face
    0px             0.029                0.000             0.000
    1px             0.025               -0.000             0.002
    2px             0.020                0.001             0.003
    3px             0.014                0.003             0.005

The narrowest baseline in a track acts as that track's own noise floor, measured
on the spot from the same camera, lens and crop size as the signal it is compared
against. That is what makes a single default threshold defensible at all.

## Limits, stated plainly

This raises the cost of an attack from "print a photo" to "replay video of the
person's face moving, on a display good enough to beat the frequency check". It is
not certified presentation-attack detection (ISO/IEC 30107-3). Specifically:

- **A video replay defeats the geometry.** A screen showing a real face turning
  displays genuine parallax, because the recorded projection already contains it.
- **A curved or bent photo is not planar** and will show some residual growth. A
  mask, or a photo wrapped around a head, is out of scope entirely.
- **Discrimination degrades with landmark precision.** Small faces, low light and
  motion blur all inflate jitter; beyond roughly 3px the margin closes.

Every signal is logged at debug level. Before relying on this, hold a photo up to
your own camera and walk past it yourself, and compare what the log reports.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# 68 point landmark model indices
LEFT_EYE = slice(36, 42)
RIGHT_EYE = slice(42, 48)
MOUTH = slice(48, 68)

DENSE_LANDMARK_COUNT = 68


@dataclass
class LivenessSignals:
    """What each check measured. Logged, so thresholds can be tuned on a site."""

    # How much the planar-fit residual grows between the narrowest and the widest
    # baseline in the track. The primary signal; see the module docstring.
    depth_growth: float = 0.0
    # The planar-fit residual at the widest baseline, in inter-ocular units. Not a
    # verdict on its own -- jitter inflates it -- but the number to look at when a
    # depth_growth reading needs explaining.
    parallax: float = 0.0
    # The same residual at the *narrowest* baseline, where two near-identical
    # views leave only jitter. The track's own measure of how precise its
    # landmarks are, and so of whether any of this can be trusted.
    noise_floor: float = 0.0
    # Shape change independent of pose: blinks, speech.
    deformation: float = 0.0
    # The widest baseline seen, as change beyond a flat face-on shift. Decides
    # whether a failure to show depth means anything.
    viewpoint: float = 0.0
    # 1.0 = looks like a direct view, 0.0 = looks like it came via a screen.
    appearance: float = 1.0
    frames: int = 0

    def __str__(self) -> str:
        return (
            f"depth_growth={self.depth_growth:.4f} parallax={self.parallax:.4f} "
            f"noise_floor={self.noise_floor:.4f} viewpoint={self.viewpoint:.4f} "
            f"deformation={self.deformation:.4f} "
            f"appearance={self.appearance:.3f} frames={self.frames}"
        )


@dataclass
class LivenessVerdict:
    """The answer, and why."""

    is_live: bool
    # 0..1, only meaningful once `conclusive` is true.
    score: float
    # Whether enough was seen to decide at all. An inconclusive verdict is not a
    # pass; callers must fail closed.
    conclusive: bool
    reason: str
    signals: LivenessSignals

    @property
    def blocks_recognition(self) -> bool:
        """Whether a name must be withheld for this face."""
        return not (self.is_live and self.conclusive)


@dataclass
class Baseline:
    """One earlier view compared against the latest one."""

    # change beyond a flat face-on shift, i.e. how much new angle was seen
    viewpoint: float
    # what a single flat surface could not explain about that change
    parallax: float


@dataclass
class _Observation:
    landmarks: np.ndarray  # (68, 2)
    appearance: float


@dataclass
class _Track:
    """Per tracked object, since liveness is a property of a sequence."""

    observations: list[_Observation] = field(default_factory=list)
    # Once a track has proven itself there is no reason to keep re-testing it; a
    # person does not stop being real while they walk to the gate.
    established: bool = False


def _interocular(landmarks: np.ndarray) -> float:
    """Distance between eye centres: the natural scale for a face."""
    left = landmarks[LEFT_EYE].mean(axis=0)
    right = landmarks[RIGHT_EYE].mean(axis=0)
    return float(np.linalg.norm(right - left))


def _openness(points: np.ndarray, scale: float) -> float:
    """How far open an eye or a mouth is, against inter-ocular distance.

    Scaled by inter-ocular distance rather than by the group's own width, which is
    the obvious choice and a bad one. An eye is some 20px wide against 85px
    between the eyes, so dividing by its own width multiplies landmark jitter by
    about four. Measured that way a photo with 1px of jitter produced a
    "deformation" of 0.12 against a real blink's 0.43, and by 3px the two were
    0.39 and 0.48 -- near enough to let a still photo pass as blinking.

    Against inter-ocular distance the same photo reads 0.038 while a real blink
    holds at 0.14 whatever the jitter, because the divisor is large and stable.
    """
    if scale <= 1e-6:
        return 0.0

    return float((points[:, 1].max() - points[:, 1].min()) / scale)


def planar_residual(first: np.ndarray, second: np.ndarray) -> float:
    """What a single flat surface cannot explain about the motion between views.

    Fits the homography that best maps `first` onto `second` and returns the mean
    leftover error, scaled by inter-ocular distance so the answer does not depend
    on how close the face was to the camera.

    On clean geometry a photo returns zero however it was tilted, because a plane
    under perspective *is* a homography. On real landmarks it returns the jitter
    instead, which is why this is never read as a verdict on its own -- see
    `parallax_growth`.
    """
    if len(first) < 4 or len(second) != len(first):
        return 0.0

    scale = _interocular(second)

    if scale <= 1e-6:
        return 0.0

    # method=0 is a plain least squares fit over every point. RANSAC would be
    # wrong here: it discards the points that fit worst, which are exactly the
    # ones carrying the parallax this is trying to measure.
    matrix, _ = cv2.findHomography(first.reshape(-1, 1, 2), second.reshape(-1, 1, 2), 0)

    if matrix is None:
        return 0.0

    projected = cv2.perspectiveTransform(first.reshape(-1, 1, 2), matrix)
    error = np.linalg.norm(projected.reshape(-1, 2) - second, axis=1)
    return float(error.mean() / scale)


def viewpoint_change(first: np.ndarray, second: np.ndarray) -> float:
    """How much changed beyond a flat, face-on shift of the whole face.

    Fits the best similarity transform -- rotation, uniform scale, translation --
    and returns what is left. Sliding a face across the frame or walking it toward
    the camera is fully explained by that transform and leaves nothing: no new
    angle was seen, so nothing was revealed about depth.

    Turning a face, or a photo of one, foreshortens it, which a uniform scale
    cannot absorb, so this rises for both. That is intended: it measures how
    informative a comparison is, not whether the subject is real.

    Fitted over the same points as `planar_residual`, so the two are comparable.
    Comparing residuals from different point sets was an early bug here: their
    difference then mixes two noise floors and means nothing.
    """
    if len(first) < 3 or len(second) != len(first):
        return 0.0

    scale = _interocular(second)

    if scale <= 1e-6:
        return 0.0

    matrix, _ = cv2.estimateAffinePartial2D(
        first.astype(np.float32), second.astype(np.float32)
    )

    if matrix is None:
        return float(np.linalg.norm(second.mean(axis=0) - first.mean(axis=0)) / scale)

    fitted = first @ matrix[:, :2].T + matrix[:, 2]
    return float(np.linalg.norm(fitted - second, axis=1).mean() / scale)


def measure_baselines(shapes: list[np.ndarray]) -> list[Baseline]:
    """Compare every earlier view in a track against the latest one."""
    if len(shapes) < 2:
        return []

    latest = shapes[-1]
    return [
        Baseline(
            viewpoint=viewpoint_change(earlier, latest),
            parallax=planar_residual(earlier, latest),
        )
        for earlier in shapes[:-1]
    ]


def parallax_growth(baselines: list[Baseline]) -> float:
    """How much the planar-fit residual grows as the baseline widens.

    The narrowest baseline is the track's own noise floor: two nearly identical
    views, where anything a flat fit cannot explain is landmark jitter rather than
    depth. Subtracting it from the widest baseline's residual removes that jitter,
    because it contributes about equally at both, and leaves parallax -- which
    only grows with the change in viewing angle.

    A flat surface returns about zero at any noise level. A real face returns
    0.014 to 0.029 for a 20 degree turn, degrading as jitter rises. See the module
    docstring for the measurements.
    """
    if len(baselines) < 2:
        return 0.0

    ordered = sorted(baselines, key=lambda baseline: baseline.viewpoint)
    return ordered[-1].parallax - ordered[0].parallax


def noise_floor(baselines: list[Baseline]) -> float:
    """How imprecise this track's landmarks are, in the units of the signal.

    The planar residual at the narrowest baseline. Those two views are nearly the
    same, so depth has had no chance to show itself and what is left is landmark
    jitter -- measured on this camera, at this distance, on this crop size, rather
    than assumed.

    It is what makes the method able to say "I cannot tell". Projected geometry
    puts it at roughly 0.02 per pixel of jitter, and the separation between a real
    face and a photo closes as it rises:

        floor    face, 20 deg turn    photo    separation
        0.021          0.025          0.000        12x
        0.061          0.015          0.003       4.6x
        0.120          0.008          0.008         none

    Past that last row the two are indistinguishable, so a verdict there would be
    a coin toss dressed up as a security control.
    """
    if not baselines:
        return 0.0

    return min(baselines, key=lambda baseline: baseline.viewpoint).parallax


def shape_deformation(landmarks: list[np.ndarray]) -> float:
    """How much the face changed shape, independently of where it moved.

    Blinks and speech open and close the eyes and mouth. A photograph's do not
    change, whatever is done with the photograph, so real variation here is
    evidence of a working face -- and unlike parallax it needs no head movement at
    all, which is what lets someone standing still be recognised.
    """
    if len(landmarks) < 2:
        return 0.0

    ratios = np.array(
        [
            [
                _openness(points[LEFT_EYE], scale),
                _openness(points[RIGHT_EYE], scale),
                _openness(points[MOUTH], scale),
            ]
            for points, scale in ((p, _interocular(p)) for p in landmarks)
        ]
    )

    # Range rather than variance: one blink in ten frames is the signal, and
    # averaging over the other nine would bury it.
    return float((ratios.max(axis=0) - ratios.min(axis=0)).max())


def screen_artifact_score(crop: np.ndarray | None) -> float:
    """Whether a crop looks like it came through a display or a printer.

    A screen's pixel grid and a printer's halftone both repeat, and repetition is a
    peak in the frequency domain. Skin has no such periodicity; its spectrum falls
    off smoothly. This compares the strongest isolated component in the mid and
    high band against the typical one, reporting 1.0 for a clean crop down to 0.0
    for a strongly periodic one.

    Deliberately conservative. It is the weakest check here: a high-resolution
    screen at the right distance produces no visible beat at all. A trained
    anti-spoofing model does this far better, and this exists so that something is
    looking at appearance when no model is configured.
    """
    if crop is None or crop.size == 0:
        return 1.0

    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop

    if min(gray.shape[:2]) < 32:
        # too small for the spectrum to mean anything
        return 1.0

    # A window stops the crop's own edges from producing a cross in the spectrum
    # that would look exactly like the periodicity being hunted.
    window = np.outer(np.hanning(gray.shape[0]), np.hanning(gray.shape[1]))
    spectrum = np.abs(np.fft.fftshift(np.fft.fft2(gray.astype(np.float64) * window)))

    centre_y, centre_x = (dim // 2 for dim in spectrum.shape[:2])
    y, x = np.ogrid[: spectrum.shape[0], : spectrum.shape[1]]
    radius = np.hypot(y - centre_y, x - centre_x)
    limit = min(centre_y, centre_x)

    if limit < 8:
        return 1.0

    # The low band is the face itself; periodic artefacts live further out.
    band = (radius > limit * 0.35) & (radius < limit * 0.95)

    if not band.any():
        return 1.0

    values = spectrum[band]
    median = float(np.median(values))

    if median <= 1e-9:
        return 1.0

    peak_ratio = float(values.max() / median)

    # A smooth natural spectrum sits in the tens; a visible screen or halftone
    # beat pushes one component far above its neighbours.
    if peak_ratio <= 40:
        return 1.0

    if peak_ratio >= 200:
        return 0.0

    return float(1.0 - (peak_ratio - 40) / 160)


class LivenessAnalyzer:
    """Accumulates liveness evidence per tracked object.

    A single frame cannot show parallax or a blink, so evidence is gathered over
    the frames of one tracked person and the verdict sharpens as they approach.
    State is keyed by tracked object id and must be dropped with `forget` when the
    object ends, or this grows without bound.
    """

    def __init__(
        self,
        # Three frames give two baselines, the minimum for a growth measurement:
        # one to serve as the noise floor and one to measure against it.
        min_frames: int = 3,
        # Growth threshold. Measurements put a real face at 0.014-0.029 for a 20
        # degree turn and a photo at 0.000-0.003, so this sits clear of both with
        # the margin on the safe side: a real face that has barely turned falls
        # below it and is withheld rather than waved through.
        depth_growth_threshold: float = 0.008,
        # Below this widest baseline, too little new angle was seen for a failure
        # to show depth to mean anything. Advisory: it only distinguishes the two
        # ways of failing in the log, since both withhold the name.
        min_viewpoint: float = 0.04,
        # Refuse to judge at all once the track's own landmark jitter reaches
        # this, because a real face and a photo stop being distinguishable. 0.05
        # is about 2.5px of jitter. Depth alone would tolerate 3px, where the
        # separation is still around 4x, but a photo's apparent blinking reaches
        # the deformation threshold there, so the tighter of the two limits sets
        # this. By 0.12 nothing is distinguishable at all. Small faces, low light
        # and motion blur are what push a track over it.
        max_noise_floor: float = 0.05,
        # A real blink or a spoken word measures 0.12 to 0.15 and holds there
        # whatever the jitter; a photo reaches 0.08 at 2px and 0.12 at 3px. This
        # sits above the first and below the second.
        deformation_threshold: float = 0.11,
        appearance_threshold: float = 0.5,
        max_observations: int = 12,
    ) -> None:
        self.min_frames = min_frames
        self.depth_growth_threshold = depth_growth_threshold
        self.min_viewpoint = min_viewpoint
        self.max_noise_floor = max_noise_floor
        self.deformation_threshold = deformation_threshold
        self.appearance_threshold = appearance_threshold
        self.max_observations = max_observations
        self.tracks: dict[str, _Track] = {}

    def forget(self, object_id: str) -> None:
        self.tracks.pop(object_id, None)

    def observe(
        self,
        object_id: str,
        landmarks: np.ndarray | None,
        crop: np.ndarray | None,
        model_score: float | None = None,
    ) -> LivenessVerdict:
        """Record one frame of a tracked face and judge what is known so far.

        `model_score` is a trained anti-spoofing model's probability that the crop
        is live, when one is configured. It replaces the frequency heuristic
        rather than being averaged with it: the model is strictly better at the
        same job, and mixing them would let the weaker one veto the stronger.
        """
        track = self.tracks.setdefault(object_id, _Track())

        appearance = (
            model_score if model_score is not None else screen_artifact_score(crop)
        )

        if landmarks is None or len(landmarks) < DENSE_LANDMARK_COUNT:
            # Cannot reason about shape from this frame. Not a pass: a face that
            # never yields landmarks never earns one.
            return LivenessVerdict(
                is_live=False,
                score=0.0,
                conclusive=False,
                reason="no landmarks for this frame",
                signals=LivenessSignals(
                    appearance=appearance, frames=len(track.observations)
                ),
            )

        track.observations.append(
            _Observation(
                landmarks=np.asarray(landmarks, dtype=np.float64),
                appearance=appearance,
            )
        )
        # Keep a bounded window; older frames say little about who is there now.
        del track.observations[: -self.max_observations]

        verdict = self._judge(track)
        logger.debug("liveness %s: %s (%s)", object_id, verdict.reason, verdict.signals)
        return verdict

    def _judge(self, track: _Track) -> LivenessVerdict:
        observations = track.observations
        shapes = [observation.landmarks for observation in observations]
        # The worst frame decides. A photo held next to a real face, or a single
        # frame that looks screen-like, should not be averaged away.
        appearance = min(observation.appearance for observation in observations)

        baselines = measure_baselines(shapes)
        widest = max(baselines, key=lambda baseline: baseline.viewpoint, default=None)

        signals = LivenessSignals(
            depth_growth=parallax_growth(baselines),
            parallax=widest.parallax if widest else 0.0,
            noise_floor=noise_floor(baselines),
            deformation=shape_deformation(shapes),
            viewpoint=widest.viewpoint if widest else 0.0,
            appearance=appearance,
            frames=len(observations),
        )

        if appearance < self.appearance_threshold:
            # A positive finding rather than absent evidence, so it is conclusive:
            # something about this image looks reproduced. Checked before
            # `established` so a track cannot carry an earlier pass over a frame
            # that now looks like a screen.
            track.established = False
            return LivenessVerdict(
                False, 0.0, True, "looks like a screen or a print", signals
            )

        if track.established:
            return LivenessVerdict(True, 1.0, True, "already established", signals)

        if len(observations) < self.min_frames:
            return LivenessVerdict(False, 0.0, False, "not enough frames yet", signals)

        if signals.noise_floor > self.max_noise_floor:
            # The landmarks are too imprecise for any of this to mean something.
            # Placed ahead of both positive tests, since jitter this large can
            # manufacture apparent depth *and* apparent blinking. Saying "I
            # cannot tell" is the only honest answer, and it withholds the name.
            return LivenessVerdict(
                False, 0.0, False, "landmarks too imprecise to judge", signals
            )

        # A working face is enough on its own: paper does not blink.
        if signals.deformation >= self.deformation_threshold:
            track.established = True
            return LivenessVerdict(True, 1.0, True, "face changed shape", signals)

        if signals.depth_growth >= self.depth_growth_threshold:
            track.established = True
            return LivenessVerdict(True, 1.0, True, "face has depth", signals)

        if signals.viewpoint < self.min_viewpoint:
            # Too little new angle for the absence of depth to mean anything. NOT a
            # pass: a photo held still reaches exactly here, and so does a real
            # person standing motionless.
            return LivenessVerdict(
                False, 0.0, False, "view has not changed enough to judge", signals
            )

        # Turned far enough to have shown depth, and showed none. This is what a
        # photo being waved at the camera looks like.
        return LivenessVerdict(
            False, 0.0, True, "face moved as a flat surface would", signals
        )
