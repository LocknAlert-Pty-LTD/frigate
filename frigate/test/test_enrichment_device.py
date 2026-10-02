"""Where the enrichment models run, and which execution provider they use.

Two separate mistakes cost real inference time here, and both were invisible:
nothing crashed, a model just quietly ran somewhere slow.

1. The image embedding device was chosen from `model_size`, so the default small
   model was pinned to "CPU" even on a machine with a GPU. `get_optimized_runner`
   turns a device of "CPU" into force_cpu, so no execution provider could rescue
   it afterwards. One image embedding took 820ms.

2. The PaddleOCR models were handed to TensorRT, which compiles an engine for a
   concrete input shape. All three declare dynamic input dimensions, and the
   recognition width is recomputed per batch, so TensorRT rebuilt an engine over
   and over -- paying the compile cost that is the only reason to use it.
"""

import unittest
from unittest.mock import patch

from frigate.detectors.detection_runners import prefers_cuda_over_tensorrt
from frigate.embeddings.embeddings import default_embedding_device
from frigate.embeddings.types import EnrichmentModelTypeEnum
from frigate.util.model import (
    GPU_EXECUTION_PROVIDERS,
    gpu_execution_provider_available,
)

PROVIDERS = "frigate.util.model.ort.get_available_providers"


class TestGpuDetection(unittest.TestCase):
    def test_a_cpu_only_build(self) -> None:
        with patch(PROVIDERS, return_value=["CPUExecutionProvider"]):
            self.assertFalse(gpu_execution_provider_available())

    def test_each_gpu_provider_counts(self) -> None:
        for provider in GPU_EXECUTION_PROVIDERS:
            with patch(PROVIDERS, return_value=[provider, "CPUExecutionProvider"]):
                self.assertTrue(gpu_execution_provider_available(), provider)

    def test_openvino_alone_does_not_count(self) -> None:
        """OpenVINO is present on any Intel host and reports CPU as a device, so
        its presence says nothing about an accelerator existing. Counting it would
        send embeddings to a device that may not be there."""
        with patch(
            PROVIDERS,
            return_value=["OpenVINOExecutionProvider", "CPUExecutionProvider"],
        ):
            self.assertFalse(gpu_execution_provider_available())

    def test_no_providers_at_all(self) -> None:
        with patch(PROVIDERS, return_value=[]):
            self.assertFalse(gpu_execution_provider_available())


class TestDefaultEmbeddingDevice(unittest.TestCase):
    def test_a_gpu_machine_gets_the_gpu(self) -> None:
        """The fix for the 820ms. Independent of model_size, which is about which
        weights are downloaded and not about where they run."""
        with patch(PROVIDERS, return_value=["CUDAExecutionProvider"]):
            self.assertEqual("GPU", default_embedding_device())

    def test_a_cpu_machine_gets_the_cpu(self) -> None:
        with patch(PROVIDERS, return_value=["CPUExecutionProvider"]):
            self.assertEqual("CPU", default_embedding_device())

    def test_it_never_returns_a_device_that_forces_cpu_on_a_gpu_box(self) -> None:
        """"CPU" is not just a preference: get_optimized_runner passes
        force_cpu=True for it, which drops every other provider. Returning it on a
        GPU machine is the bug this replaced."""
        with patch(PROVIDERS, return_value=["TensorrtExecutionProvider"]):
            self.assertNotEqual("CPU", default_embedding_device())


class TestTensorRtIsSkippedForDynamicShapes(unittest.TestCase):
    """Which models should avoid TensorRT, and which should keep it.

    Verified against the real model files. PaddleOCR detection, classification and
    recognition all declare dynamic input dimensions; the license plate detector is
    a fixed [1, 3, 256, 256].
    """

    def test_the_paddleocr_models_skip_it(self) -> None:
        self.assertTrue(prefers_cuda_over_tensorrt(EnrichmentModelTypeEnum.paddleocr.value))

    def test_the_jina_embedding_models_skip_it(self) -> None:
        """Dynamic sequence length, same problem by a different route."""
        self.assertTrue(prefers_cuda_over_tensorrt(EnrichmentModelTypeEnum.jina_v1.value))
        self.assertTrue(prefers_cuda_over_tensorrt(EnrichmentModelTypeEnum.jina_v2.value))

    def test_the_license_plate_detector_keeps_it(self) -> None:
        """Static input shape, so it builds one engine and keeps it. Skipping
        TensorRT here would give up a real speed-up for nothing."""
        self.assertFalse(
            prefers_cuda_over_tensorrt(EnrichmentModelTypeEnum.yolov9_license_plate.value)
        )

    def test_the_object_detector_keeps_it(self) -> None:
        """The detector runs at a fixed configured resolution, and TensorRT FP16
        there measured 5.84ms against 10ms on CUDA."""
        self.assertFalse(prefers_cuda_over_tensorrt("yologeneric"))

    def test_an_unknown_model_type_keeps_it(self) -> None:
        """Opt-out, not opt-in: a new model is only excluded once its shapes are
        known to vary."""
        self.assertFalse(prefers_cuda_over_tensorrt("something-new"))


class TestProviderOrderAfterExclusion(unittest.TestCase):
    """The exclusion drops TensorRT and must leave CUDA in front of CPU, with
    each provider still paired with its own options."""

    def build(self, model_type: str):
        from frigate.util.model import get_ort_providers

        with patch(
            PROVIDERS,
            return_value=[
                "TensorrtExecutionProvider",
                "CUDAExecutionProvider",
                "CPUExecutionProvider",
            ],
        ):
            providers, options = get_ort_providers(False, "AUTO")

        if providers and providers[0] == "TensorrtExecutionProvider":
            if prefers_cuda_over_tensorrt(model_type):
                providers.pop(0)
                options.pop(0)

        return providers, options

    def test_ocr_lands_on_cuda(self) -> None:
        providers, options = self.build(EnrichmentModelTypeEnum.paddleocr.value)

        self.assertEqual("CUDAExecutionProvider", providers[0])
        self.assertEqual(len(providers), len(options))
        self.assertIn("device_id", options[0], "CUDA options must survive the pop")

    def test_cpu_remains_the_last_resort(self) -> None:
        providers, _ = self.build(EnrichmentModelTypeEnum.paddleocr.value)

        self.assertEqual("CPUExecutionProvider", providers[-1])

    def test_the_plate_detector_stays_on_tensorrt(self) -> None:
        providers, options = self.build(
            EnrichmentModelTypeEnum.yolov9_license_plate.value
        )

        self.assertEqual("TensorrtExecutionProvider", providers[0])
        self.assertEqual(len(providers), len(options))


class TestCudaAlgorithmSearchIsLeftAlone(unittest.TestCase):
    """cudnn_conv_algo_search must stay at the ONNX Runtime default, EXHAUSTIVE.

    It was once set to HEURISTIC for the dynamic-shape OCR models, on the
    reasoning that benchmarking every convolution algorithm for each new input
    shape would cost more than it saved. Measured on a live gate camera it did
    the reverse: plate text detection went from 61ms to 328ms and the whole
    plate pipeline from 73ms to 400ms. EXHAUSTIVE pays once per shape and then
    runs the fastest kernel; HEURISTIC skips the benchmark and runs a worse
    kernel on every call.

    These tests exist so the setting cannot quietly return. Changing it needs a
    before-and-after measurement of the pipeline, not an argument.
    """

    def options_for(self, model_type: str):
        from frigate.detectors.detection_runners import prefers_cuda_over_tensorrt
        from frigate.util.model import get_ort_providers

        with patch(
            PROVIDERS,
            return_value=[
                "TensorrtExecutionProvider",
                "CUDAExecutionProvider",
                "CPUExecutionProvider",
            ],
        ):
            providers, options = get_ort_providers(False, "AUTO")

        if prefers_cuda_over_tensorrt(model_type):
            providers.pop(0)
            options.pop(0)

        return dict(zip(providers, options))

    def test_the_ocr_models_do_not_override_it(self) -> None:
        cuda = self.options_for(EnrichmentModelTypeEnum.paddleocr.value)[
            "CUDAExecutionProvider"
        ]

        self.assertNotIn("cudnn_conv_algo_search", cuda)

    def test_no_model_overrides_it(self) -> None:
        for model_type in (
            EnrichmentModelTypeEnum.paddleocr.value,
            EnrichmentModelTypeEnum.jina_v1.value,
            EnrichmentModelTypeEnum.jina_v2.value,
            EnrichmentModelTypeEnum.yolov9_license_plate.value,
            "yologeneric",
        ):
            cuda = self.options_for(model_type).get("CUDAExecutionProvider", {})

            self.assertNotIn("cudnn_conv_algo_search", cuda, model_type)

    def test_the_runner_source_does_not_set_it(self) -> None:
        """Catches the setting being reintroduced in get_optimized_runner, which
        the provider-options tests above do not exercise."""
        import inspect

        from frigate.detectors import detection_runners

        source = inspect.getsource(detection_runners.get_optimized_runner)

        self.assertNotIn('["cudnn_conv_algo_search"] =', source)


class TestEngineCacheIsPerGpu(unittest.TestCase):
    """TensorRT engines are compiled for one specific device.

    Handed an engine built elsewhere, TensorRT warns and then runs it anyway:

        Using an engine plan file across different models of devices is not
        supported and is likely to affect performance or even cause errors or
        deadlock.

    This showed up on a live install whose /config had been moved between
    machines. The cache lives under /config, which is exactly the directory
    people copy, back up and restore, so keying it on the GPU is the difference
    between a different card building its own engines and silently running
    something elses.
    """

    def setUp(self) -> None:
        import frigate.util.model

        frigate.util.model._GPU_CACHE_NAMESPACE = None
        self.addCleanup(setattr, frigate.util.model, "_GPU_CACHE_NAMESPACE", None)

    def smi(self, output: str, returncode: int = 0):
        return patch(
            "frigate.util.model.subprocess.run",
            return_value=type(
                "Result", (), {"returncode": returncode, "stdout": output}
            )(),
        )

    def namespace(self, output: str, returncode: int = 0) -> str:
        from frigate.util.model import tensorrt_cache_namespace

        with self.smi(output, returncode):
            return tensorrt_cache_namespace()

    def test_the_gpu_name_and_compute_capability_are_used(self) -> None:
        self.assertEqual(
            "nvidia-geforce-rtx-3060-8.6",
            self.namespace("NVIDIA GeForce RTX 3060, 8.6"),
        )

    def test_two_different_cards_get_different_namespaces(self) -> None:
        """The case that matters. A Pascal card and an Ampere card must not
        share engines."""
        import frigate.util.model

        ampere = self.namespace("NVIDIA GeForce RTX 3060, 8.6")
        frigate.util.model._GPU_CACHE_NAMESPACE = None
        pascal = self.namespace("NVIDIA GeForce GTX 1080, 6.1")

        self.assertNotEqual(ampere, pascal)

    def test_the_namespace_is_safe_as_a_directory_name(self) -> None:
        namespace = self.namespace("Weird /../ Name!, 8.6")

        self.assertNotIn("/", namespace)
        self.assertNotIn("..", namespace)

    def test_it_is_only_probed_once(self) -> None:
        """Called on every session creation; a subprocess each time would be
        paid for nothing."""
        from frigate.util.model import tensorrt_cache_namespace

        with self.smi("NVIDIA GeForce RTX 3060, 8.6") as run:
            tensorrt_cache_namespace()
            tensorrt_cache_namespace()
            tensorrt_cache_namespace()

        self.assertEqual(1, run.call_count)

    def test_an_unidentifiable_gpu_falls_back(self) -> None:
        """No worse than before: a shared directory, which is what it was."""
        self.assertEqual("unknown-gpu", self.namespace("", returncode=9))

    def test_a_missing_nvidia_smi_falls_back(self) -> None:
        from frigate.util.model import tensorrt_cache_namespace

        with patch(
            "frigate.util.model.subprocess.run", side_effect=FileNotFoundError()
        ):
            self.assertEqual("unknown-gpu", tensorrt_cache_namespace())

    def test_a_hanging_nvidia_smi_falls_back(self) -> None:
        """It runs while models load, so it cannot be allowed to block startup."""
        import subprocess

        from frigate.util.model import tensorrt_cache_namespace

        with patch(
            "frigate.util.model.subprocess.run",
            side_effect=subprocess.TimeoutExpired("nvidia-smi", 5),
        ):
            self.assertEqual("unknown-gpu", tensorrt_cache_namespace())

    def test_both_caches_land_under_the_namespace(self) -> None:
        """The timing cache is device-specific too, not just the engines."""
        from frigate.util.model import get_ort_providers

        with self.smi("NVIDIA GeForce RTX 3060, 8.6"):
            with patch(PROVIDERS, return_value=["TensorrtExecutionProvider"]):
                _, options = get_ort_providers(False, "AUTO")

        for key in ("trt_engine_cache_path", "trt_timing_cache_path"):
            self.assertTrue(
                options[0][key].endswith("nvidia-geforce-rtx-3060-8.6"), key
            )


class TestOcrPrecisionIsUnchanged(unittest.TestCase):
    def test_fp16_is_not_requested_for_the_ocr_models(self) -> None:
        """OCR reads characters that gate access and feed ParkPow, so precision is
        not traded for milliseconds here. Only the object detector passes
        requires_fp16, and this pins the default so a later caller cannot enable
        it for OCR by accident."""
        from frigate.util.model import get_ort_providers

        with patch(
            PROVIDERS,
            return_value=["TensorrtExecutionProvider", "CPUExecutionProvider"],
        ):
            _, options = get_ort_providers(False, "AUTO")

        self.assertFalse(options[0]["trt_fp16_enable"])


if __name__ == "__main__":
    unittest.main()
