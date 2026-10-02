import logging
import os
import queue
import threading
from abc import ABC, abstractmethod

import cv2
import numpy as np
from scipy import stats

from frigate.config import FrigateConfig
from frigate.const import FACE_DIR
from frigate.data_processing.common.face.detector import (
    FACE_TEMPLATE,
    FACE_TEMPLATE_SIZE,
    FaceDetector,
)
from frigate.embeddings.onnx.face_embedding import (
    ARCFACE_INPUT_SIZE,
    FACENET_INPUT_SIZE,
    ArcfaceEmbedding,
    FaceNetEmbedding,
)

logger = logging.getLogger(__name__)


class FaceRecognizer(ABC):
    """Face recognition runner."""

    def __init__(self, config: FrigateConfig, detector: FaceDetector) -> None:
        self.config = config
        self.detector = detector

    @abstractmethod
    def build(self) -> None:
        """Build face recognition model."""
        pass

    @abstractmethod
    def clear(self) -> None:
        """Clear current built model."""
        pass

    @abstractmethod
    def classify(self, face_image: np.ndarray) -> tuple[str, float] | None:
        pass

    def align_face(self, image: np.ndarray, output_size: int) -> np.ndarray | None:
        """Warp a face onto the template the embedding model was trained on.

        Args:
            image: The face crop to align
            output_size: Width and height of the model input

        Returns:
            The aligned face, or None if it could not be aligned
        """
        landmarks = self.detector.get_face_landmarks(image)

        if landmarks is None:
            return None

        # fitting all 5 points constrains rotation, scale, and position, an eye
        # line alone leaves them free to slip on the small faces from a camera
        matrix, _ = cv2.estimateAffinePartial2D(
            np.array(landmarks, dtype=np.float32),
            FACE_TEMPLATE * (output_size / FACE_TEMPLATE_SIZE),
            method=cv2.LMEDS,
        )

        # the fit fails on degenerate landmarks even though the stub says
        # otherwise, for example when every point collapses onto one pixel
        if matrix is None:
            return None  # type: ignore[unreachable]

        # the output is already the model input size, so the embedder's resize
        # and letterbox padding are a no op
        return cv2.warpAffine(
            image, matrix, (output_size, output_size), flags=cv2.INTER_CUBIC
        )

    def is_too_blurry(self, input: np.ndarray) -> bool:
        """Whether this crop is too soft to identify anyone from.

        get_blur_confidence_reduction only ever shaved up to 0.06 off the
        score, which a strong-but-wrong match absorbs easily. A motion-blurred
        face carries little identity information, so the honest answer is to
        decline rather than to guess slightly less confidently.
        """
        threshold = self.config.face_recognition.min_blur_variance

        if threshold <= 0:
            return False

        variance = cv2.Laplacian(input, cv2.CV_64F).var()

        if variance < threshold:
            logger.debug(
                "Rejecting blurry face: variance %.1f below %d", variance, threshold
            )
            return True

        return False

    def get_blur_confidence_reduction(self, input: np.ndarray) -> float:
        """Calculates the reduction in confidence based on the blur of the image."""
        if not self.config.face_recognition.blur_confidence_filter:
            return 0.0

        variance = cv2.Laplacian(input, cv2.CV_64F).var()
        logger.debug(f"face detected with blurriness {variance}")

        if variance < 120:  # image is very blurry
            return 0.06
        elif variance < 160:  # image moderately blurry
            return 0.04
        elif variance < 200:  # image is slightly blurry
            return 0.02
        elif variance < 250:  # image is mostly clear
            return 0.01
        else:
            return 0.0


def keep_inlier_embeddings(
    embs: list,
    trim: float = 0.15,
    outlier_threshold: float = 0.30,
    min_keep_frac: float = 0.7,
    max_iters: int = 3,
):
    """Return the enrolled embeddings worth keeping, L2-normalised.

    Same iterative outlier rejection build_class_mean used -- drop whole
    embeddings whose cosine similarity to the running class centre is too low,
    which catches a wrong face in the folder or a full-frame screenshot -- but
    it returns the survivors instead of averaging them away.

    Averaging was the core accuracy problem. One centroid per person cannot
    represent someone with and without glasses, or lit from either side: the
    mean lands between the modes and matches neither well, while sitting closer
    to other people's means. Keeping the samples lets a probe match whichever
    enrolled image it actually resembles.
    """
    arr = np.stack(embs, axis=0)
    arr = arr / (np.linalg.norm(arr, axis=1, keepdims=True) + 1e-9)

    if len(arr) < 5:
        # too few samples to tell an outlier from natural variation
        return arr

    keep = np.ones(len(arr), dtype=bool)
    floor = max(5, int(np.ceil(min_keep_frac * len(arr))))

    for _ in range(max_iters):
        mean = stats.trim_mean(arr[keep], trim, axis=0)
        m_norm = mean / (np.linalg.norm(mean) + 1e-9)
        cos = arr @ m_norm
        new_keep = cos >= outlier_threshold

        if new_keep.sum() < floor:
            top = np.argsort(-cos)[:floor]
            new_keep = np.zeros(len(arr), dtype=bool)
            new_keep[top] = True

        if np.array_equal(new_keep, keep):
            break

        keep = new_keep

    dropped = int((~keep).sum())

    if dropped:
        logger.debug(
            f"Vector-wise outlier filter dropped {dropped}/{len(arr)} embeddings"
        )

    return arr[keep]


def score_classes(embedding, class_embs: dict, top_k: int) -> list:
    """Rank enrolled people against one probe embedding.

    Each person scores as the mean of their ``top_k`` most similar enrolled
    images. k>1 stops a single lucky frame from carrying a match; k below the
    enrolment count stops unrelated poses from diluting a genuine one.

    Returns (name, similarity) sorted best first.
    """
    probe = embedding / (np.linalg.norm(embedding) + 1e-9)
    scored = []

    for name, embs in class_embs.items():
        if embs is None or len(embs) == 0:
            continue

        sims = embs @ probe
        k = max(1, min(top_k, len(sims)))
        top = np.sort(sims)[-k:]
        scored.append((name, float(top.mean())))

    scored.sort(key=lambda item: item[1], reverse=True)
    return scored


def apply_margin(scored: list, margin: float) -> tuple:
    """Reject a match the runner-up is too close to.

    A probe scoring 0.91 against one person and 0.90 against another is not a
    confident identification, however high the absolute number looks. Without
    this the top score wins outright, which is how look-alikes -- and family
    members especially -- get confidently mislabelled. That is the failure mode
    that matters when a match opens a door.

    Returns (name, similarity, rejected_because_ambiguous).
    """
    if not scored:
        return None, 0.0, False

    best_name, best_sim = scored[0]

    if margin <= 0 or len(scored) < 2:
        return best_name, best_sim, False

    runner_up = scored[1][1]

    if best_sim - runner_up < margin:
        logger.debug(
            "Rejecting ambiguous face: %s %.3f vs %s %.3f (margin %.3f < %.3f)",
            best_name,
            best_sim,
            scored[1][0],
            runner_up,
            best_sim - runner_up,
            margin,
        )
        return None, best_sim, True

    return best_name, best_sim, False


def similarity_to_confidence(
    cosine_similarity: float,
    median: float = 0.3,
    range_width: float = 0.6,
    slope_factor: float = 12,
) -> float:
    """
    Default sigmoid function to map cosine similarity to confidence.

    Args:
        cosine_similarity (float): The input cosine similarity.
        median (float): Assumed median of cosine similarity distribution.
        range_width (float): Assumed range of cosine similarity distribution (90th percentile - 10th percentile).
        slope_factor (float): Adjusts the steepness of the curve.

    Returns:
        float: The confidence score.
    """

    # Calculate slope and bias
    slope = slope_factor / range_width
    bias = median

    # Calculate confidence
    confidence: float = 1 / (1 + np.exp(-slope * (cosine_similarity - bias)))
    return confidence


class FaceNetRecognizer(FaceRecognizer):
    def __init__(self, config: FrigateConfig, detector: FaceDetector):
        super().__init__(config, detector)
        self.mean_embs: dict[str, np.ndarray] = {}
        self.face_embedder: FaceNetEmbedding = FaceNetEmbedding()
        self.model_builder_queue: queue.Queue | None = None

    def clear(self) -> None:
        self.mean_embs = {}

    def run_build_task(self) -> None:
        self.model_builder_queue = queue.Queue()

        def build_model() -> None:
            face_embeddings_map: dict[str, list[np.ndarray]] = {}
            idx = 0

            dir = FACE_DIR
            for name in os.listdir(dir):
                if name == "train":
                    continue

                face_folder = os.path.join(dir, name)

                if not os.path.isdir(face_folder):
                    continue

                face_embeddings_map[name] = []
                for image in os.listdir(face_folder):
                    img = cv2.imread(os.path.join(face_folder, image))

                    if img is None:
                        continue  # type: ignore[unreachable]

                    aligned = self.align_face(img, FACENET_INPUT_SIZE)

                    if aligned is None:
                        continue

                    emb = self.face_embedder([aligned])[0].squeeze()
                    face_embeddings_map[name].append(emb)

                idx += 1

            assert self.model_builder_queue is not None
            self.model_builder_queue.put(face_embeddings_map)

        thread = threading.Thread(target=build_model, daemon=True)
        thread.start()

    def build(self) -> None:
        if not self.detector.is_ready:
            return None

        if self.model_builder_queue is not None:
            try:
                face_embeddings_map: dict[str, list[np.ndarray]] = (
                    self.model_builder_queue.get(timeout=0.1)
                )
                self.model_builder_queue = None
            except queue.Empty:
                return
        else:
            self.run_build_task()
            return

        if not face_embeddings_map:
            return

        for name, embs in face_embeddings_map.items():
            if embs:
                self.mean_embs[name] = keep_inlier_embeddings(embs)

        logger.debug("Finished building ArcFace model")

    def classify(self, face_image: np.ndarray) -> tuple[str, float] | None:
        if not self.detector.is_ready:
            return None

        if not self.mean_embs:
            self.build()

            if not self.mean_embs:
                return None

        # judged before alignment, which resamples and hides real softness
        if self.is_too_blurry(face_image):
            return None

        blur_reduction = self.get_blur_confidence_reduction(face_image)

        img = self.align_face(face_image, FACENET_INPUT_SIZE)

        if img is None:
            return None

        embedding = self.face_embedder([img])[0].squeeze()

        scored = score_classes(
            embedding, self.mean_embs, self.config.face_recognition.knn_top_k
        )
        label, similarity, ambiguous = apply_margin(
            scored, self.config.face_recognition.recognition_margin
        )

        if label is None:
            # ambiguous, or nobody enrolled; either way not an identification
            return None if ambiguous else ("", 0.0)

        confidence = similarity_to_confidence(
            similarity, median=0.5, range_width=0.6
        )

        return label, max(0, round(confidence - blur_reduction, 2))


class ArcFaceRecognizer(FaceRecognizer):
    def __init__(self, config: FrigateConfig, detector: FaceDetector):
        super().__init__(config, detector)
        self.mean_embs: dict[str, np.ndarray] = {}
        self.face_embedder: ArcfaceEmbedding = ArcfaceEmbedding(config.face_recognition)
        self.model_builder_queue: queue.Queue | None = None

    def clear(self) -> None:
        self.mean_embs = {}

    def run_build_task(self) -> None:
        self.model_builder_queue = queue.Queue()

        def build_model() -> None:
            face_embeddings_map: dict[str, list[np.ndarray]] = {}
            idx = 0

            dir = FACE_DIR
            for name in os.listdir(dir):
                if name == "train":
                    continue

                face_folder = os.path.join(dir, name)

                if not os.path.isdir(face_folder):
                    continue

                face_embeddings_map[name] = []
                for image in os.listdir(face_folder):
                    img = cv2.imread(os.path.join(face_folder, image))

                    if img is None:
                        continue  # type: ignore[unreachable]

                    aligned = self.align_face(img, ARCFACE_INPUT_SIZE)

                    if aligned is None:
                        continue

                    emb = self.face_embedder([aligned])[0].squeeze()  # type: ignore[arg-type]
                    face_embeddings_map[name].append(emb)

                idx += 1

            assert self.model_builder_queue is not None
            self.model_builder_queue.put(face_embeddings_map)

        thread = threading.Thread(target=build_model, daemon=True)
        thread.start()

    def build(self) -> None:
        if not self.detector.is_ready:
            return None

        if self.model_builder_queue is not None:
            try:
                face_embeddings_map: dict[str, list[np.ndarray]] = (
                    self.model_builder_queue.get(timeout=0.1)
                )
                self.model_builder_queue = None
            except queue.Empty:
                return
        else:
            self.run_build_task()
            return

        if not face_embeddings_map:
            return

        for name, embs in face_embeddings_map.items():
            if embs:
                self.mean_embs[name] = keep_inlier_embeddings(embs)

        logger.debug("Finished building ArcFace model")

    def classify(self, face_image: np.ndarray) -> tuple[str, float] | None:
        if not self.detector.is_ready:
            return None

        if not self.mean_embs:
            self.build()

            if not self.mean_embs:
                return None

        # judged before alignment, which resamples and hides real softness
        if self.is_too_blurry(face_image):
            return None

        blur_reduction = self.get_blur_confidence_reduction(face_image)

        img = self.align_face(face_image, ARCFACE_INPUT_SIZE)

        if img is None:
            return None

        embedding = self.face_embedder([img])[0].squeeze()  # type: ignore[arg-type]

        scored = score_classes(
            embedding, self.mean_embs, self.config.face_recognition.knn_top_k
        )
        label, similarity, ambiguous = apply_margin(
            scored, self.config.face_recognition.recognition_margin
        )

        if label is None:
            # ambiguous, or nobody enrolled; either way not an identification
            return None if ambiguous else ("", 0.0)

        confidence = similarity_to_confidence(similarity)

        return label, max(0, round(confidence - blur_reduction, 2))
