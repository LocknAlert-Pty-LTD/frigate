"""TensorRT must degrade to CUDA, never take startup down.

Registering TensorRT unconditionally assumed ONNX Runtime would fall back for
anything it could not handle. That holds for individual *operators*: the graph
is partitioned and unsupported nodes go to the next provider. It does not hold
for an engine build that fails outright, which raises out of InferenceSession.

TensorRT 10 dropped Pascal (SM 6.1), so on a GTX 10-series card every build
fails with "Target GPU SM 61 is not supported by this TensorRT release", and
before this fallback the detector and embeddings processes died on startup and
the watchdog restarted them forever.
"""

import sys
import types
import unittest
from unittest.mock import MagicMock, patch

# detection_runners pulls in onnxruntime and, transitively, POSIX-only modules
# at import time. Stub only what is missing, so this still runs natively in the
# container where the real ones exist.
if "onnxruntime" not in sys.modules:
    stub = types.ModuleType("onnxruntime")
    stub.get_available_providers = lambda: []
    stub.SessionOptions = object
    stub.InferenceSession = object
    sys.modules["onnxruntime"] = stub

if "resource" not in sys.modules:
    try:
        import resource  # noqa: F401
    except ImportError:
        _res = types.ModuleType("resource")
        _res.RLIMIT_NOFILE = 7
        _res.getrlimit = lambda _r: (1024, 4096)
        _res.setrlimit = lambda _r, _l: None
        sys.modules["resource"] = _res

if "fcntl" not in sys.modules:
    try:
        import fcntl  # noqa: F401
    except ImportError:
        _fcntl = types.ModuleType("fcntl")
        _fcntl.LOCK_EX = 2
        _fcntl.LOCK_UN = 8
        _fcntl.LOCK_NB = 4
        _fcntl.flock = lambda *_a, **_k: None
        sys.modules["fcntl"] = _fcntl

import os as _os

if not hasattr(_os, "register_at_fork"):
    _os.register_at_fork = lambda **_k: None

from frigate.detectors import detection_runners  # noqa: E402

SM61 = (
    "[ONNXRuntimeError] : 1 : FAIL : TensorRT EP failed to create engine from "
    "network for fused node: TensorrtExecutionProvider_TRTKernel_graph_main_graph_1_0_0"
)

PROVIDERS = ["TensorrtExecutionProvider", "CUDAExecutionProvider", "CPUExecutionProvider"]
OPTIONS = [{"device_id": 0, "trt_fp16_enable": True}, {"device_id": 0}, {}]


class TensorrtFallbackTestCase(unittest.TestCase):
    def setUp(self) -> None:
        detection_runners._tensorrt_unusable = False
        self.addCleanup(setattr, detection_runners, "_tensorrt_unusable", False)
        patcher = patch.object(
            detection_runners, "get_ort_session_options", return_value=None
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def session(self, side_effect):
        calls = []

        def factory(model_path, sess_options=None, providers=None, provider_options=None):
            calls.append(list(providers))
            result = side_effect(providers)
            if isinstance(result, Exception):
                raise result
            return result

        return factory, calls


class TestEngineBuildFailure(TensorrtFallbackTestCase):
    def test_falls_back_to_cuda_when_the_engine_cannot_build(self) -> None:
        sentinel = MagicMock(name="session")

        def side_effect(providers):
            if "TensorrtExecutionProvider" in providers:
                return Exception(SM61)
            return sentinel

        factory, calls = self.session(side_effect)
        with patch.object(detection_runners.ort, "InferenceSession", factory):
            result = detection_runners._create_session("m.onnx", "yologeneric", PROVIDERS, OPTIONS)

        self.assertIs(sentinel, result)
        self.assertEqual(2, len(calls), "expected one retry")
        self.assertNotIn("TensorrtExecutionProvider", calls[1])
        self.assertEqual(["CUDAExecutionProvider", "CPUExecutionProvider"], calls[1])

    def test_later_models_skip_tensorrt_entirely(self) -> None:
        """One doomed build per process, not one per model."""
        def side_effect(providers):
            if "TensorrtExecutionProvider" in providers:
                return Exception(SM61)
            return MagicMock()

        factory, calls = self.session(side_effect)
        with patch.object(detection_runners.ort, "InferenceSession", factory):
            detection_runners._create_session("a.onnx", "yologeneric", PROVIDERS, OPTIONS)
            detection_runners._create_session("b.onnx", "yologeneric", PROVIDERS, OPTIONS)

        # first model: attempt + retry; second: straight to CUDA
        self.assertEqual(3, len(calls))
        self.assertNotIn("TensorrtExecutionProvider", calls[2])

    def test_options_stay_aligned_with_providers(self) -> None:
        """A mismatched pair would make ORT apply CUDA options to CPU."""
        providers, options = detection_runners._drop_tensorrt(PROVIDERS, OPTIONS)

        self.assertEqual(["CUDAExecutionProvider", "CPUExecutionProvider"], providers)
        self.assertEqual([{"device_id": 0}, {}], options)
        self.assertEqual(len(providers), len(options))


class TestUnrelatedFailuresStillRaise(TensorrtFallbackTestCase):
    def test_a_failure_without_tensorrt_is_not_swallowed(self) -> None:
        """Only TensorRT gets a second chance; a genuinely broken model must
        still surface rather than be retried into a confusing error."""
        def side_effect(providers):
            return Exception("corrupt model file")

        factory, calls = self.session(side_effect)
        with patch.object(detection_runners.ort, "InferenceSession", factory):
            with self.assertRaises(Exception) as ctx:
                detection_runners._create_session(
                    "m.onnx", "yologeneric", ["CUDAExecutionProvider"], [{}]
                )

        self.assertIn("corrupt model file", str(ctx.exception))
        self.assertEqual(1, len(calls), "must not retry when TensorRT was not involved")

    def test_a_second_failure_is_not_retried_forever(self) -> None:
        def side_effect(providers):
            return Exception("GPU on fire")

        factory, calls = self.session(side_effect)
        with patch.object(detection_runners.ort, "InferenceSession", factory):
            with self.assertRaises(Exception):
                detection_runners._create_session("m.onnx", "yologeneric", PROVIDERS, OPTIONS)

        self.assertEqual(2, len(calls), "one retry, then give up")


class TestHealthyTensorrtIsUntouched(TensorrtFallbackTestCase):
    def test_no_retry_when_the_engine_builds(self) -> None:
        sentinel = MagicMock()
        factory, calls = self.session(lambda providers: sentinel)

        with patch.object(detection_runners.ort, "InferenceSession", factory):
            result = detection_runners._create_session("m.onnx", "yologeneric", PROVIDERS, OPTIONS)

        self.assertIs(sentinel, result)
        self.assertEqual(1, len(calls))
        self.assertEqual(PROVIDERS, calls[0])
        self.assertFalse(detection_runners._tensorrt_unusable)


if __name__ == "__main__":
    unittest.main()
