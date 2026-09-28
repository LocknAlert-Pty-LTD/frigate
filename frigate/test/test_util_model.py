"""Tests for frigate.util.model.get_ort_providers.

Needs cv2/onnxruntime installed (frigate.util.model imports both at module
scope), so this only runs in a real dev/CI container, not the bare sandbox.
"""

import os
import unittest
from unittest.mock import patch

from pathlib import Path

from frigate.util.model import get_ort_providers

REPO_ROOT = Path(__file__).resolve().parents[2]


class TestGetOrtProviders(unittest.TestCase):
    def test_tensorrt_used_automatically_with_cuda_fallback(self):
        """TensorRT should be picked up with no explicit device config, and
        CUDA should stay registered right after it as the fallback provider."""
        with patch(
            "frigate.util.model.ort.get_available_providers",
            return_value=[
                "TensorrtExecutionProvider",
                "CUDAExecutionProvider",
                "CPUExecutionProvider",
            ],
        ):
            providers, options = get_ort_providers(force_cpu=False, device="AUTO")

        self.assertEqual(
            providers,
            [
                "TensorrtExecutionProvider",
                "CUDAExecutionProvider",
                "CPUExecutionProvider",
            ],
        )
        self.assertIn("trt_max_workspace_size", options[0])
        self.assertGreater(options[0]["trt_max_workspace_size"], 0)
        self.assertFalse(options[0]["trt_fp16_enable"])

    def test_trt_max_workspace_size_env_override(self):
        with patch(
            "frigate.util.model.ort.get_available_providers",
            return_value=["TensorrtExecutionProvider"],
        ):
            with patch.dict(os.environ, {"TRT_MAX_WORKSPACE_MB": "512"}):
                _, options = get_ort_providers(force_cpu=False, device="AUTO")

        self.assertEqual(options[0]["trt_max_workspace_size"], 512 * 1024 * 1024)

    def test_no_tensorrt_falls_back_to_cuda_only(self):
        with patch(
            "frigate.util.model.ort.get_available_providers",
            return_value=["CUDAExecutionProvider", "CPUExecutionProvider"],
        ):
            providers, _ = get_ort_providers(force_cpu=False, device="AUTO")

        self.assertEqual(providers, ["CUDAExecutionProvider", "CPUExecutionProvider"])


class TestTensorrtFp16(unittest.TestCase):
    """FP16 is opt-in per model, and must stay that way.

    get_optimized_runner serves the object detector, the face and semantic
    search models, and the license plate models. Only the detector opts in:
    LPR is OCR feeding the ParkPow integration, where trading character
    accuracy for milliseconds is the wrong call.
    """

    def providers(self, requires_fp16: bool, env: dict | None = None):
        with patch(
            "frigate.util.model.ort.get_available_providers",
            return_value=["TensorrtExecutionProvider", "CUDAExecutionProvider"],
        ):
            with patch.dict(os.environ, env or {}, clear=False):
                return get_ort_providers(
                    force_cpu=False, device="AUTO", requires_fp16=requires_fp16
                )

    def test_fp16_on_when_the_caller_asks(self):
        _, options = self.providers(True)
        self.assertTrue(options[0]["trt_fp16_enable"])

    def test_fp16_off_by_default(self):
        """Callers that do not opt in keep full FP32 precision."""
        _, options = self.providers(False)
        self.assertFalse(options[0]["trt_fp16_enable"])

    def test_use_fp16_false_overrides_the_opt_in(self):
        """The runtime escape hatch, for reverting without a rebuild."""
        _, options = self.providers(True, {"USE_FP16": "False"})
        self.assertFalse(options[0]["trt_fp16_enable"])


class TestOnlyTheDetectorOptsIntoFp16(unittest.TestCase):
    def test_detector_passes_requires_fp16(self):
        source = (REPO_ROOT / "frigate/detectors/plugins/onnx.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("requires_fp16=True", source)

    def test_embedding_models_do_not(self):
        for rel in (
            "frigate/embeddings/onnx/lpr_embedding.py",
            "frigate/embeddings/onnx/face_embedding.py",
            "frigate/embeddings/onnx/jina_v1_embedding.py",
            "frigate/embeddings/onnx/jina_v2_embedding.py",
        ):
            source = (REPO_ROOT / rel).read_text(encoding="utf-8")
            self.assertNotIn(
                "requires_fp16=True",
                source,
                f"{rel} opted into FP16; LPR and embedding accuracy should not "
                f"be traded for detector speed",
            )


if __name__ == "__main__":
    unittest.main()
