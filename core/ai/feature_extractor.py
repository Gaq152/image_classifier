"""ONNX image embedding extraction and shared image preprocessing."""

import importlib
import json
import logging
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

import cv2
import numpy as np


class AIModelUnavailableError(RuntimeError):
    """Raised when the optional model runtime or model pack is unavailable."""


def is_cuda_execution_available() -> bool:
    """Return whether ONNX Runtime exposes the NVIDIA CUDA provider."""
    try:
        ort = importlib.import_module("onnxruntime")
        return "CUDAExecutionProvider" in ort.get_available_providers()
    except (ImportError, OSError, RuntimeError):
        return False


def read_rgb_image(path: str) -> np.ndarray:
    """Read an image as RGB while supporting UNC and Chinese paths."""
    encoded = np.fromfile(path, dtype=np.uint8)
    bgr = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    if bgr is None or bgr.size == 0:
        raise ValueError(f"无法解码图片: {path}")
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


def letterbox_rgb(
    rgb: np.ndarray,
    width: int,
    height: int,
    padding_rgb: Iterable[int],
) -> np.ndarray:
    """Resize without cropping, preserving small cues near image edges."""
    source_height, source_width = rgb.shape[:2]
    scale = min(width / source_width, height / source_height)
    resized_width = max(1, round(source_width * scale))
    resized_height = max(1, round(source_height * scale))
    interpolation = cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR
    resized = cv2.resize(
        rgb, (resized_width, resized_height), interpolation=interpolation
    )

    canvas = np.empty((height, width, 3), dtype=np.uint8)
    canvas[:] = tuple(padding_rgb)
    left = (width - resized_width) // 2
    top = (height - resized_height) // 2
    canvas[top : top + resized_height, left : left + resized_width] = resized
    return canvas


def spatial_color_features(rgb: np.ndarray) -> np.ndarray:
    """Return spatial color statistics that retain white/yellow edge cues."""
    small = cv2.resize(rgb, (64, 64), interpolation=cv2.INTER_AREA)
    lab = cv2.cvtColor(small, cv2.COLOR_RGB2LAB).astype(np.float32) / 255.0
    hsv = cv2.cvtColor(small, cv2.COLOR_RGB2HSV).astype(np.float32)
    hsv[..., 0] /= 179.0
    hsv[..., 1:] /= 255.0

    # (grid_y, patch_y, grid_x, patch_x, channel) ->
    # (grid_y, grid_x, patch_y, patch_x, channel).  This keeps the exact
    # historical feature order while removing 64 Python-level patch loops.
    lab_patches = lab.reshape(8, 8, 8, 8, 3).transpose(0, 2, 1, 3, 4)
    hsv_patches = hsv.reshape(8, 8, 8, 8, 3).transpose(0, 2, 1, 3, 4)
    lab_mean = lab_patches.mean(axis=(2, 3))
    lab_std = lab_patches.std(axis=(2, 3))

    hue = hsv_patches[..., 0] * 179.0
    saturation = hsv_patches[..., 1]
    value = hsv_patches[..., 2]
    yellow_ratio = (
        (hue >= 15)
        & (hue <= 40)
        & (saturation >= 0.25)
        & (value >= 0.25)
    ).mean(axis=(2, 3))
    white_ratio = (
        (saturation <= 0.20) & (value >= 0.55)
    ).mean(axis=(2, 3))

    features = np.concatenate(
        (
            lab_mean,
            lab_std,
            yellow_ratio[..., None],
            white_ratio[..., None],
        ),
        axis=-1,
    )
    return np.ascontiguousarray(features.reshape(-1), dtype=np.float32)


class OnnxEmbeddingExtractor:
    """Extract normalized deep and spatial-color features from RGB images."""

    def __init__(
        self,
        model_dir: Path,
        preferred_provider: str = "auto",
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.logger = logger or logging.getLogger(__name__)
        self.model_dir = Path(model_dir)
        manifest_path = self.model_dir / "manifest.json"
        if not manifest_path.exists():
            raise AIModelUnavailableError(f"未找到 AI 模型清单: {manifest_path}")
        self.manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        model_path = self.model_dir / self.manifest["model_file"]
        if not model_path.exists():
            raise AIModelUnavailableError(f"未找到 AI 模型文件: {model_path}")

        input_config = self.manifest["input"]
        self.input_width = int(input_config["width"])
        self.input_height = int(input_config["height"])
        self.padding_rgb = tuple(input_config.get("padding_rgb", (124, 116, 104)))
        self.scale = float(input_config.get("scale", 1.0 / 255.0))
        self.mean = np.asarray(input_config["mean"], dtype=np.float32).reshape(
            1, 3, 1, 1
        )
        self.std = np.asarray(input_config["std"], dtype=np.float32).reshape(1, 3, 1, 1)
        self.input_name = input_config.get("name", "images")
        self.output_name = self.manifest["output"].get("name", "embeddings")
        self.model_id = str(self.manifest["model_id"])

        self.cv_net = None
        self.ort_session = None
        self.requested_provider = (
            preferred_provider
            if preferred_provider in ("auto", "cpu", "cuda")
            else "auto"
        )
        self.provider_fallback_reason: Optional[str] = None
        runtime = self.manifest.get("runtime", "opencv")
        self._load_runtime(model_path, runtime)

        # 初始化在线程中完成一次热身，避免第一张图片承担图优化开销。
        warmup = np.zeros((1, 3, self.input_height, self.input_width), dtype=np.float32)
        self._forward(warmup)
        spatial_color_features(
            np.zeros((self.input_height, self.input_width, 3), dtype=np.uint8)
        )

    def _load_runtime(self, model_path: Path, manifest_runtime: str) -> None:
        """Prefer NVIDIA CUDA for every ONNX encoder, then safely use CPU."""
        if self.requested_provider in ("auto", "cuda"):
            try:
                self._load_onnx_runtime(model_path, use_cuda=True)
                return
            except AIModelUnavailableError as error:
                self.provider_fallback_reason = str(error)
                self.logger.warning(
                    "NVIDIA GPU 推理不可用，准备回退 CPU: %s", error
                )

        if manifest_runtime == "onnxruntime":
            self._load_onnx_runtime(model_path, use_cuda=False)
        else:
            self._load_opencv_runtime(model_path)

    def _load_opencv_runtime(self, model_path: Path) -> None:
        try:
            self.cv_net = cv2.dnn.readNetFromONNX(str(model_path))
            self.cv_net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
            self.cv_net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
            self.provider = "OpenCVDNNCPU"
        except Exception as error:
            raise AIModelUnavailableError(
                f"OpenCV 无法加载 AI 模型: {error}"
            ) from error

    def _load_onnx_runtime(self, model_path: Path, use_cuda: bool) -> None:
        try:
            ort = importlib.import_module("onnxruntime")
        except (ImportError, OSError) as error:
            raise AIModelUnavailableError(
                "需要安装 ONNX Runtime 推理运行库"
            ) from error

        if use_cuda and hasattr(ort, "preload_dlls"):
            try:
                # ONNX Runtime 1.21+ 可从 PyTorch 或 nvidia-* Python 包加载
                # CUDA/cuDNN DLL，源码运行和打包环境都能复用同一逻辑。
                ort.preload_dlls()
            except Exception as error:
                self.logger.debug("预加载 CUDA DLL 失败: %s", error)

        available = ort.get_available_providers()
        if use_cuda and "CUDAExecutionProvider" not in available:
            raise AIModelUnavailableError("ONNX Runtime 未检测到 CUDA 执行器")
        providers = (
            ["CUDAExecutionProvider", "CPUExecutionProvider"]
            if use_cuda
            else ["CPUExecutionProvider"]
        )
        try:
            session = ort.InferenceSession(
                str(model_path), providers=providers
            )
        except Exception as error:
            raise AIModelUnavailableError(
                f"ONNX Runtime 无法加载 AI 模型: {error}"
            ) from error
        active_providers = session.get_providers()
        if use_cuda and "CUDAExecutionProvider" not in active_providers:
            raise AIModelUnavailableError(
                "ONNX Runtime CUDA 会话创建失败，未启用 NVIDIA GPU"
            )
        self.ort_session = session
        self.provider = "ONNXRuntimeCUDA" if use_cuda else "ONNXRuntimeCPU"

    def _forward(self, batch: np.ndarray) -> np.ndarray:
        if self.ort_session is not None:
            return self.ort_session.run(
                [self.output_name], {self.input_name: batch}
            )[0]
        self.cv_net.setInput(batch)
        return self.cv_net.forward()

    @property
    def provider_label(self) -> str:
        if self.provider == "OpenCVDNNCUDA":
            return "NVIDIA GPU"
        if self.provider == "OpenCVDNNCPU":
            return "CPU (OpenCV)"
        if self.provider == "ONNXRuntimeCUDA":
            return "NVIDIA GPU (ONNX Runtime)"
        if self.provider == "ONNXRuntimeCPU":
            return "CPU (ONNX Runtime)"
        return "CPU"

    @property
    def uses_gpu(self) -> bool:
        """Whether the active execution provider runs inference on NVIDIA GPU."""
        return self.provider in ("OpenCVDNNCUDA", "ONNXRuntimeCUDA")

    def prepare_batch(self, rgb_images: List[np.ndarray]) -> np.ndarray:
        prepared = [
            letterbox_rgb(
                image,
                self.input_width,
                self.input_height,
                self.padding_rgb,
            )
            for image in rgb_images
        ]
        batch = np.stack(prepared).astype(np.float32)
        batch = np.transpose(batch, (0, 3, 1, 2)) * self.scale
        return np.ascontiguousarray((batch - self.mean) / self.std)

    def extract_batch(
        self, rgb_images: List[np.ndarray]
    ) -> Tuple[np.ndarray, np.ndarray]:
        batch = self.prepare_batch(rgb_images)
        embeddings = self._forward(batch).astype(np.float32)
        embeddings /= np.maximum(
            np.linalg.norm(embeddings, axis=1, keepdims=True), 1e-8
        )
        colors = np.stack([spatial_color_features(image) for image in rgb_images])
        return embeddings, colors

    def extract(self, rgb: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        embeddings, colors = self.extract_batch([rgb])
        return embeddings[0], colors[0]
