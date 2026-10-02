import logging
import os
import time
import warnings

import cv2
import numpy as np

from frigate.comms.inter_process import InterProcessRequestor
from frigate.const import MODEL_CACHE_DIR
from frigate.detectors.detection_runners import BaseModelRunner, get_optimized_runner
from frigate.embeddings.types import EnrichmentModelTypeEnum
from frigate.types import ModelStatusTypesEnum
from frigate.util.downloader import ModelDownloader

from .base_embedding import BaseEmbedding

warnings.filterwarnings(
    "ignore",
    category=FutureWarning,
    message="The class CLIPFeatureExtractor is deprecated",
)

logger = logging.getLogger(__name__)

LPR_EMBEDDING_SIZE = 256


# Fixed input shapes for the PaddleOCR models.
#
# Both models declare dynamic inputs, and the pipeline used to feed them
# whatever size each plate happened to produce: the text detector got the plate
# crop rounded to its own multiple of 32, and the recogniser got a width derived
# from the widest crop in the batch. On CUDA, ONNX Runtime picks a convolution
# algorithm per input shape by benchmarking every candidate (the EXHAUSTIVE
# search), so nearly every car paid for a fresh benchmark of every layer.
# Measured on a gate camera that put plate text detection at 61ms for a model
# that takes under 6ms on a CPU at plate size.
#
# Pinning the shapes turns that into a one-off cost, paid at load by
# warm_fixed_shapes rather than by the first car at the gate.

# The text detector sees the plate letterboxed into this canvas. It only has to
# find the lines of text; the recogniser reads them from the full-resolution
# plate image, so detecting on a smaller copy costs no reading accuracy. 128px
# tall leaves the characters of a two-line plate around 40px each, well inside
# what the detector handles. (height, width), both multiples of 32 as the
# detector requires.
LPR_DETECTION_CANVAS = (128, 512)

LPR_RECOGNITION_HEIGHT = 48

# Recognition widths a text crop is padded up to. 320 is the PaddleOCR default;
# the wider buckets keep a long line from being squeezed. Anything wider than
# the last bucket is squeezed into it rather than given a shape of its own.
LPR_RECOGNITION_WIDTHS = (320, 480, 640)

# Batch sizes tuned at load. A plate rarely yields more than three text regions;
# larger batches still work and are tuned the first time they appear.
LPR_RECOGNITION_WARMUP_BATCHES = (1, 2, 3)


def recognition_width_bucket(width: int) -> int:
    """The fixed recognition width a crop of this width is padded to."""
    for bucket in LPR_RECOGNITION_WIDTHS:
        if width <= bucket:
            return bucket

    return LPR_RECOGNITION_WIDTHS[-1]


def warm_fixed_shapes(
    runner: BaseModelRunner, shapes: list[tuple[int, ...]], label: str
) -> None:
    """Run each fixed shape once so its convolution algorithms are chosen now.

    Best effort: a failure here only means the first real call pays the tuning
    cost instead, so it is logged and never raised.
    """
    start = time.perf_counter()

    try:
        input_name = runner.get_input_names()[0]

        for shape in shapes:
            runner.run({input_name: np.zeros(shape, dtype=np.float32)})
    except Exception as err:
        logger.debug(f"Could not pre-tune {label}: {err}")
        return

    logger.info(
        f"Pre-tuned {label} for {len(shapes)} input shape(s) in "
        f"{(time.perf_counter() - start) * 1000:.0f}ms"
    )


class PaddleOCRDetection(BaseEmbedding):
    def __init__(
        self,
        model_size: str,
        requestor: InterProcessRequestor,
        device: str = "AUTO",
    ):
        model_file = (
            "detection_v3-large.onnx"
            if model_size == "large"
            else "detection_v5-small.onnx"
        )
        GITHUB_ENDPOINT = os.environ.get("GITHUB_ENDPOINT", "https://github.com")
        super().__init__(
            model_name="paddleocr-onnx",
            model_file=model_file,
            download_urls={
                model_file: f"{GITHUB_ENDPOINT}/hawkeye217/paddleocr-onnx/raw/refs/heads/master/models/{'v3' if model_size == 'large' else 'v5'}/{model_file}"
            },
        )
        self.requestor = requestor
        self.model_size = model_size
        self.device = device
        self.download_path = os.path.join(MODEL_CACHE_DIR, self.model_name)
        self.runner: BaseModelRunner | None = None
        files_names = list(self.download_urls.keys())
        if not all(
            os.path.exists(os.path.join(self.download_path, n)) for n in files_names
        ):
            logger.debug(f"starting model download for {self.model_name}")
            self.downloader = ModelDownloader(
                model_name=self.model_name,
                download_path=self.download_path,
                file_names=files_names,
                download_func=self._download_model,
            )
            self.downloader.ensure_model_files()
        else:
            self.downloader = None
            ModelDownloader.mark_files_state(
                self.requestor,
                self.model_name,
                files_names,
                ModelStatusTypesEnum.downloaded,
            )
            self._load_model_and_utils()
            logger.debug(f"models are already downloaded for {self.model_name}")

    def _load_model_and_utils(self):
        if self.runner is None:
            if self.downloader:
                self.downloader.wait_for_download()

            self.runner = get_optimized_runner(
                os.path.join(self.download_path, self.model_file),
                self.device,
                model_type=EnrichmentModelTypeEnum.paddleocr.value,
            )
            warm_fixed_shapes(
                self.runner,
                [(1, 3, *LPR_DETECTION_CANVAS)],
                "LPR text detection",
            )

    def _preprocess_inputs(self, raw_inputs):
        preprocessed = []
        for x in raw_inputs:
            preprocessed.append(x)
        return [{"x": preprocessed[0]}]


class PaddleOCRClassification(BaseEmbedding):
    def __init__(
        self,
        model_size: str,
        requestor: InterProcessRequestor,
        device: str = "AUTO",
    ):
        GITHUB_ENDPOINT = os.environ.get("GITHUB_ENDPOINT", "https://github.com")
        super().__init__(
            model_name="paddleocr-onnx",
            model_file="classification.onnx",
            download_urls={
                "classification.onnx": f"{GITHUB_ENDPOINT}/hawkeye217/paddleocr-onnx/raw/refs/heads/master/models/classification.onnx"
            },
        )
        self.requestor = requestor
        self.model_size = model_size
        self.device = device
        self.download_path = os.path.join(MODEL_CACHE_DIR, self.model_name)
        self.runner: BaseModelRunner | None = None
        files_names = list(self.download_urls.keys())
        if not all(
            os.path.exists(os.path.join(self.download_path, n)) for n in files_names
        ):
            logger.debug(f"starting model download for {self.model_name}")
            self.downloader = ModelDownloader(
                model_name=self.model_name,
                download_path=self.download_path,
                file_names=files_names,
                download_func=self._download_model,
            )
            self.downloader.ensure_model_files()
        else:
            self.downloader = None
            ModelDownloader.mark_files_state(
                self.requestor,
                self.model_name,
                files_names,
                ModelStatusTypesEnum.downloaded,
            )
            self._load_model_and_utils()
            logger.debug(f"models are already downloaded for {self.model_name}")

    def _load_model_and_utils(self):
        if self.runner is None:
            if self.downloader:
                self.downloader.wait_for_download()

            self.runner = get_optimized_runner(
                os.path.join(self.download_path, self.model_file),
                self.device,
                model_type=EnrichmentModelTypeEnum.paddleocr.value,
            )

    def _preprocess_inputs(self, raw_inputs):
        processed = []
        for img in raw_inputs:
            processed.append({"x": img})
        return processed


class PaddleOCRRecognition(BaseEmbedding):
    def __init__(
        self,
        model_size: str,
        requestor: InterProcessRequestor,
        device: str = "AUTO",
    ):
        GITHUB_ENDPOINT = os.environ.get("GITHUB_ENDPOINT", "https://github.com")
        super().__init__(
            model_name="paddleocr-onnx",
            model_file="recognition_v4.onnx",
            download_urls={
                "recognition_v4.onnx": f"{GITHUB_ENDPOINT}/hawkeye217/paddleocr-onnx/raw/refs/heads/master/models/v4/recognition_v4.onnx",
                "ppocr_keys_v1.txt": f"{GITHUB_ENDPOINT}/hawkeye217/paddleocr-onnx/raw/refs/heads/master/models/v4/ppocr_keys_v1.txt",
            },
        )
        self.requestor = requestor
        self.model_size = model_size
        self.device = device
        self.download_path = os.path.join(MODEL_CACHE_DIR, self.model_name)
        self.runner: BaseModelRunner | None = None
        files_names = list(self.download_urls.keys())
        if not all(
            os.path.exists(os.path.join(self.download_path, n)) for n in files_names
        ):
            logger.debug(f"starting model download for {self.model_name}")
            self.downloader = ModelDownloader(
                model_name=self.model_name,
                download_path=self.download_path,
                file_names=files_names,
                download_func=self._download_model,
            )
            self.downloader.ensure_model_files()
        else:
            self.downloader = None
            ModelDownloader.mark_files_state(
                self.requestor,
                self.model_name,
                files_names,
                ModelStatusTypesEnum.downloaded,
            )
            self._load_model_and_utils()
            logger.debug(f"models are already downloaded for {self.model_name}")

    def _load_model_and_utils(self):
        if self.runner is None:
            if self.downloader:
                self.downloader.wait_for_download()

            self.runner = get_optimized_runner(
                os.path.join(self.download_path, self.model_file),
                self.device,
                model_type=EnrichmentModelTypeEnum.paddleocr.value,
            )
            warm_fixed_shapes(
                self.runner,
                [
                    (batch, 3, LPR_RECOGNITION_HEIGHT, width)
                    for batch in LPR_RECOGNITION_WARMUP_BATCHES
                    for width in LPR_RECOGNITION_WIDTHS
                ],
                "LPR character recognition",
            )

    def _preprocess_inputs(self, raw_inputs):
        processed = []
        for img in raw_inputs:
            processed.append({"x": img})
        return processed


class LicensePlateDetector(BaseEmbedding):
    def __init__(
        self,
        model_size: str,
        requestor: InterProcessRequestor,
        device: str = "AUTO",
    ):
        GITHUB_ENDPOINT = os.environ.get("GITHUB_ENDPOINT", "https://github.com")
        super().__init__(
            model_name="yolov9_license_plate",
            model_file="yolov9-256-license-plates.onnx",
            download_urls={
                "yolov9-256-license-plates.onnx": f"{GITHUB_ENDPOINT}/hawkeye217/yolov9-license-plates/raw/refs/heads/master/models/yolov9-256-license-plates.onnx"
            },
        )

        self.requestor = requestor
        self.model_size = model_size
        self.device = device
        self.download_path = os.path.join(MODEL_CACHE_DIR, self.model_name)
        self.runner: BaseModelRunner | None = None
        files_names = list(self.download_urls.keys())
        if not all(
            os.path.exists(os.path.join(self.download_path, n)) for n in files_names
        ):
            logger.debug(f"starting model download for {self.model_name}")
            self.downloader = ModelDownloader(
                model_name=self.model_name,
                download_path=self.download_path,
                file_names=files_names,
                download_func=self._download_model,
            )
            self.downloader.ensure_model_files()
        else:
            self.downloader = None
            ModelDownloader.mark_files_state(
                self.requestor,
                self.model_name,
                files_names,
                ModelStatusTypesEnum.downloaded,
            )
            self._load_model_and_utils()
            logger.debug(f"models are already downloaded for {self.model_name}")

    def _load_model_and_utils(self):
        if self.runner is None:
            if self.downloader:
                self.downloader.wait_for_download()

            self.runner = get_optimized_runner(
                os.path.join(self.download_path, self.model_file),
                self.device,
                model_type=EnrichmentModelTypeEnum.yolov9_license_plate.value,
            )

    def _preprocess_inputs(self, raw_inputs):
        if isinstance(raw_inputs, list):
            raise ValueError("License plate embedding does not support batch inputs.")

        img = raw_inputs
        height, width, channels = img.shape

        # Resize maintaining aspect ratio
        if width > height:
            new_height = int(((height / width) * LPR_EMBEDDING_SIZE) // 4 * 4)
            img = cv2.resize(img, (LPR_EMBEDDING_SIZE, new_height))
        else:
            new_width = int(((width / height) * LPR_EMBEDDING_SIZE) // 4 * 4)
            img = cv2.resize(img, (new_width, LPR_EMBEDDING_SIZE))

        # Get new dimensions after resize
        og_h, og_w, channels = img.shape

        # Create black square frame
        frame = np.full(
            (LPR_EMBEDDING_SIZE, LPR_EMBEDDING_SIZE, channels),
            (0, 0, 0),
            dtype=np.float32,
        )

        # Center the resized image in the square frame
        x_center = (LPR_EMBEDDING_SIZE - og_w) // 2
        y_center = (LPR_EMBEDDING_SIZE - og_h) // 2
        frame[y_center : y_center + og_h, x_center : x_center + og_w] = img

        # Normalize to 0-1
        frame = frame / 255.0

        # Convert from HWC to CHW format and add batch dimension
        frame = np.transpose(frame, (2, 0, 1))
        frame = np.expand_dims(frame, axis=0)
        return [{"images": frame}]
