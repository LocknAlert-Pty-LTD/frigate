"""The plate OCR models on TensorRT, through shape profiles.

They were kept off TensorRT because their inputs changed size from plate to
plate, and TensorRT compiles an engine per shape. With the inputs fixed, a
profile describing the whole range lets one engine serve every input. Measured
on an Ampere GPU, TensorRT FP32 then roughly halves both models against CUDA:
text detection 10.6ms to 5.7ms, recognition of two crops 10.7ms to 5.3ms.

What these tests guard is mostly the failure handling, because on a gate the
plate reader working matters more than which backend it runs on:

* a model that cannot run on TensorRT falls back to CUDA on its own, without
  taking every other model in the process off TensorRT with it
* the recogniser's batch size and its TensorRT profile cannot drift apart,
  since a batch outside the profile is an input the engine cannot serve
"""

import unittest
from unittest.mock import patch

from frigate.detectors import detection_runners
from frigate.detectors.detection_runners import TensorRtShapes
from frigate.embeddings.onnx import lpr_embedding
from frigate.embeddings.types import EnrichmentModelTypeEnum

PROVIDERS = "frigate.util.model.ort.get_available_providers"
GPU = ["TensorrtExecutionProvider", "CUDAExecutionProvider", "CPUExecutionProvider"]


class TestProfileOptions(unittest.TestCase):
    def test_the_onnx_runtime_option_format(self) -> None:
        shapes = TensorRtShapes("x", (1, 3, 48, 320), (1, 3, 48, 320), (6, 3, 48, 640))

        self.assertEqual(
            {
                "trt_profile_min_shapes": "x:1x3x48x320",
                "trt_profile_opt_shapes": "x:1x3x48x320",
                "trt_profile_max_shapes": "x:6x3x48x640",
            },
            shapes.provider_options(),
        )


class CapturedSession:
    """Records what a session was created with instead of loading a model."""

    calls: list[tuple] = []

    def __init__(self, path, sess_options=None, providers=None, provider_options=None):
        CapturedSession.calls.append((list(providers), [dict(o) for o in provider_options]))
        self.providers = list(providers)

    def get_providers(self):
        return self.providers

    def get_inputs(self):
        return []


class TestRunnerSelection(unittest.TestCase):
    def setUp(self) -> None:
        CapturedSession.calls = []
        detection_runners._tensorrt_unusable = False
        self.addCleanup(setattr, detection_runners, "_tensorrt_unusable", False)

    def build(self, **kwargs):
        with patch(PROVIDERS, return_value=GPU), patch(
            "frigate.detectors.detection_runners.ort.InferenceSession", CapturedSession
        ), patch(
            "frigate.detectors.detection_runners.is_rknn_compatible", return_value=False
        ):
            return detection_runners.get_optimized_runner(
                "/model.onnx",
                "GPU",
                model_type=EnrichmentModelTypeEnum.paddleocr.value,
                **kwargs,
            )

    def test_without_a_profile_the_ocr_models_stay_on_cuda(self) -> None:
        """Unchanged behaviour for anything that has not described its shapes."""
        self.build()

        providers, _ = CapturedSession.calls[-1]
        self.assertEqual("CUDAExecutionProvider", providers[0])

    def test_with_a_profile_they_go_on_tensorrt(self) -> None:
        shape = (1, 3, 128, 512)
        self.build(tensorrt_shapes=TensorRtShapes("x", shape, shape, shape))

        providers, options = CapturedSession.calls[-1]
        self.assertEqual("TensorrtExecutionProvider", providers[0])
        self.assertEqual("x:1x3x128x512", options[0]["trt_profile_max_shapes"])

    def test_the_profile_does_not_leak_into_other_providers(self) -> None:
        shape = (1, 3, 128, 512)
        self.build(tensorrt_shapes=TensorRtShapes("x", shape, shape, shape))

        _, options = CapturedSession.calls[-1]
        for other in options[1:]:
            self.assertNotIn("trt_profile_min_shapes", other)

    def test_ocr_stays_fp32(self) -> None:
        """FP16 measured no faster and built several times slower, and OCR reads
        characters that open a gate. The profile must not switch it on."""
        shape = (1, 3, 128, 512)
        self.build(tensorrt_shapes=TensorRtShapes("x", shape, shape, shape))

        _, options = CapturedSession.calls[-1]
        self.assertFalse(options[0]["trt_fp16_enable"])


class FailingTensorRtSession(CapturedSession):
    def __init__(self, path, sess_options=None, providers=None, provider_options=None):
        if "TensorrtExecutionProvider" in providers:
            raise RuntimeError("engine build failed")
        super().__init__(path, sess_options, providers, provider_options)


class TestFailureIsIsolated(unittest.TestCase):
    def setUp(self) -> None:
        CapturedSession.calls = []
        detection_runners._tensorrt_unusable = False
        self.addCleanup(setattr, detection_runners, "_tensorrt_unusable", False)

    def create(self, isolate: bool):
        with patch(
            "frigate.detectors.detection_runners.ort.InferenceSession",
            FailingTensorRtSession,
        ):
            return detection_runners._create_session(
                "/model.onnx",
                EnrichmentModelTypeEnum.paddleocr.value,
                list(GPU),
                [{}, {}, {}],
                isolate_tensorrt_failure=isolate,
            )

    def test_an_opted_in_model_falls_back_on_its_own(self) -> None:
        """A PaddleOCR engine failing says something about that model, not the
        GPU. ArcFace and the plate detector share this process and must keep
        TensorRT."""
        session = self.create(isolate=True)

        self.assertEqual("CUDAExecutionProvider", session.providers[0])
        self.assertFalse(detection_runners._tensorrt_unusable)

    def test_an_ordinary_failure_still_disables_tensorrt_process_wide(self) -> None:
        """The original behaviour, for a GPU TensorRT cannot serve at all."""
        session = self.create(isolate=False)

        self.assertEqual("CUDAExecutionProvider", session.providers[0])
        self.assertTrue(detection_runners._tensorrt_unusable)


class Runner:
    def __init__(self, device_name: str, fail: bool) -> None:
        self.device_name = device_name
        self.fail = fail
        self.ran: list[tuple] = []

    def get_input_names(self):
        return ["x"]

    def run(self, inputs):
        if self.fail:
            raise RuntimeError("TensorRT cannot serve this input")
        self.ran.append(inputs["x"].shape)


class TestFallbackAtFirstRun(unittest.TestCase):
    """An engine can fail when it is first run rather than when the session is
    created. Without this the warmup would fail, and then so would every real
    call -- the plate reader returning nothing, on every car, silently."""

    def load(self, first: Runner, second: Runner):
        runners = iter([first, second])
        calls: list[dict] = []

        def fake_runner(model_path, device, model_type, **kwargs):
            calls.append(kwargs)
            return next(runners)

        with patch.object(lpr_embedding, "get_optimized_runner", fake_runner):
            result = lpr_embedding.load_fixed_shape_runner(
                "/model.onnx",
                "GPU",
                TensorRtShapes("x", (1, 3, 4, 4), (1, 3, 4, 4), (1, 3, 4, 4)),
                [(1, 3, 4, 4)],
                "test",
            )

        return result, calls

    def test_tensorrt_that_works_is_kept(self) -> None:
        trt = Runner("TensorRT", fail=False)

        result, calls = self.load(trt, Runner("CUDA", fail=False))

        self.assertIs(trt, result)
        self.assertEqual(1, len(calls))

    def test_tensorrt_that_fails_falls_back_to_cuda(self) -> None:
        cuda = Runner("CUDA", fail=False)

        result, calls = self.load(Runner("TensorRT", fail=True), cuda)

        self.assertIs(cuda, result)
        self.assertIn("tensorrt_shapes", calls[0])
        self.assertNotIn("tensorrt_shapes", calls[1], "the retry must not ask for TensorRT")
        self.assertEqual([(1, 3, 4, 4)], cuda.ran, "the fallback is prepared too")

    def test_a_non_tensorrt_runner_is_not_retried(self) -> None:
        """If the GPU has no TensorRT at all the first runner is already CUDA.
        A failed warmup there is not a reason to rebuild the same thing."""
        cuda = Runner("CUDA", fail=True)

        result, calls = self.load(cuda, Runner("CUDA", fail=False))

        self.assertIs(cuda, result)
        self.assertEqual(1, len(calls))


class TestBatchAndProfileAgree(unittest.TestCase):
    def test_the_pipeline_batches_with_the_profile_maximum(self) -> None:
        import inspect

        from frigate.data_processing.common.license_plate import mixin

        source = inspect.getsource(mixin.LicensePlateProcessingMixin.__init__)

        self.assertIn("self.batch_size = LPR_RECOGNITION_MAX_BATCH", source)

    def test_warmup_stays_inside_the_profile(self) -> None:
        self.assertLessEqual(
            max(lpr_embedding.LPR_RECOGNITION_WARMUP_BATCHES),
            lpr_embedding.LPR_RECOGNITION_MAX_BATCH,
        )


if __name__ == "__main__":
    unittest.main()
