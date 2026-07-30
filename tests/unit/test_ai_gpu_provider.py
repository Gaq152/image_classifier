"""NVIDIA GPU provider selection and CPU fallback tests."""

import logging

import cv2
import numpy as np
import pytest

from core.ai.feature_extractor import (
    AIModelUnavailableError,
    OnnxEmbeddingExtractor,
    spatial_color_features,
)


def _bare_extractor(requested_provider="auto"):
    extractor = object.__new__(OnnxEmbeddingExtractor)
    extractor.logger = logging.getLogger(__name__)
    extractor.requested_provider = requested_provider
    extractor.provider_fallback_reason = None
    extractor.cv_net = None
    extractor.ort_session = None
    return extractor


def test_auto_prefers_onnx_runtime_cuda_for_opencv_profile(
    monkeypatch, tmp_path
):
    extractor = _bare_extractor("auto")
    calls = []

    def load_ort(self, model_path, use_cuda):
        calls.append(("ort", use_cuda))
        self.provider = "ONNXRuntimeCUDA"

    monkeypatch.setattr(OnnxEmbeddingExtractor, "_load_onnx_runtime", load_ort)
    monkeypatch.setattr(
        OnnxEmbeddingExtractor,
        "_load_opencv_runtime",
        lambda *_args: calls.append(("opencv", False)),
    )

    extractor._load_runtime(tmp_path / "model.onnx", "opencv")

    assert calls == [("ort", True)]
    assert extractor.provider == "ONNXRuntimeCUDA"


def test_auto_falls_back_to_profile_cpu_runtime(monkeypatch, tmp_path):
    extractor = _bare_extractor("auto")
    calls = []

    def fail_cuda(self, model_path, use_cuda):
        calls.append(("ort", use_cuda))
        raise AIModelUnavailableError("CUDA DLL 缺失")

    def load_opencv(self, model_path):
        calls.append(("opencv", False))
        self.provider = "OpenCVDNNCPU"

    monkeypatch.setattr(
        OnnxEmbeddingExtractor,
        "_load_onnx_runtime",
        fail_cuda,
    )
    monkeypatch.setattr(
        OnnxEmbeddingExtractor,
        "_load_opencv_runtime",
        load_opencv,
    )

    extractor._load_runtime(tmp_path / "model.onnx", "opencv")

    assert calls == [("ort", True), ("opencv", False)]
    assert extractor.provider == "OpenCVDNNCPU"
    assert extractor.provider_fallback_reason == "CUDA DLL 缺失"


def test_cpu_choice_never_attempts_cuda(monkeypatch, tmp_path):
    extractor = _bare_extractor("cpu")
    calls = []

    def load_ort(self, model_path, use_cuda):
        calls.append(("ort", use_cuda))
        self.provider = "ONNXRuntimeCPU"

    monkeypatch.setattr(OnnxEmbeddingExtractor, "_load_onnx_runtime", load_ort)

    extractor._load_runtime(tmp_path / "model.onnx", "onnxruntime")

    assert calls == [("ort", False)]
    assert extractor.provider == "ONNXRuntimeCPU"


def test_cuda_session_must_really_activate_cuda(monkeypatch, tmp_path):
    extractor = _bare_extractor("auto")

    class FakeSession:
        def get_providers(self):
            return ["CPUExecutionProvider"]

    class FakeOrt:
        @staticmethod
        def preload_dlls():
            return None

        @staticmethod
        def get_available_providers():
            return ["CUDAExecutionProvider", "CPUExecutionProvider"]

        @staticmethod
        def InferenceSession(_path, providers):
            assert providers[0] == "CUDAExecutionProvider"
            return FakeSession()

    monkeypatch.setattr(
        "core.ai.feature_extractor.importlib.import_module",
        lambda _name: FakeOrt,
    )

    with pytest.raises(AIModelUnavailableError, match="未启用 NVIDIA GPU"):
        extractor._load_onnx_runtime(tmp_path / "model.onnx", use_cuda=True)


def test_vectorized_spatial_color_features_keep_historical_order():
    rgb = np.random.default_rng(42).integers(
        0, 256, size=(173, 291, 3), dtype=np.uint8
    )
    actual = spatial_color_features(rgb)

    small = cv2.resize(rgb, (64, 64), interpolation=cv2.INTER_AREA)
    lab = cv2.cvtColor(small, cv2.COLOR_RGB2LAB).astype(np.float32) / 255.0
    hsv = cv2.cvtColor(small, cv2.COLOR_RGB2HSV).astype(np.float32)
    hsv[..., 0] /= 179.0
    hsv[..., 1:] /= 255.0
    expected = []
    for grid_y in range(8):
        for grid_x in range(8):
            rows = slice(grid_y * 8, (grid_y + 1) * 8)
            columns = slice(grid_x * 8, (grid_x + 1) * 8)
            patch_lab = lab[rows, columns]
            patch_hsv = hsv[rows, columns]
            expected.extend(patch_lab.mean((0, 1)))
            expected.extend(patch_lab.std((0, 1)))
            hue = patch_hsv[..., 0] * 179.0
            saturation = patch_hsv[..., 1]
            value = patch_hsv[..., 2]
            expected.extend(
                (
                    (
                        (hue >= 15)
                        & (hue <= 40)
                        & (saturation >= 0.25)
                        & (value >= 0.25)
                    ).mean(),
                    ((saturation <= 0.20) & (value >= 0.55)).mean(),
                )
            )

    np.testing.assert_allclose(
        actual,
        np.asarray(expected, dtype=np.float32),
        rtol=1e-6,
        atol=1e-6,
    )
