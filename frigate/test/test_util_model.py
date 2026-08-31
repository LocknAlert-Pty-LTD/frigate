"""Tests for frigate.util.model.get_ort_providers.

Needs cv2/onnxruntime installed (frigate.util.model imports both at module
scope), so this only runs in a real dev/CI container, not the bare sandbox.
"""

import os
import unittest
from unittest.mock import patch

from frigate.util.model import get_ort_providers


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


if __name__ == "__main__":
    unittest.main()
