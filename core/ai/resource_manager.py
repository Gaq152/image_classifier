"""Download and activate optional AI runtimes and base-model packs."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import shutil
import sys
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Optional

from core.update_utils import download_with_progress
from utils.paths import (
    get_ai_download_dir,
    get_ai_model_dir,
    get_ai_runtime_dir,
)

from .model_registry import AIModelProfile, get_ai_model_profile


AI_RESOURCE_RELEASE_BASE = (
    "https://github.com/Gaq152/image_classifier/releases/download/"
    "ai-resources-v1"
)
ONNXRUNTIME_VERSION = "1.23.2"


@dataclass(frozen=True)
class AIResourceSpec:
    """One downloadable, checksummed AI resource."""

    key: str
    kind: str
    display_name: str
    version: str
    filename: str
    url: str
    size_bytes: int
    sha256: str
    target_name: str
    expected_model_id: str = ""


RUNTIME_RESOURCES: Dict[str, AIResourceSpec] = {
    "cpu": AIResourceSpec(
        key="runtime_cpu",
        kind="runtime",
        display_name="CPU 推理运行时",
        version=ONNXRUNTIME_VERSION,
        filename="onnxruntime-1.23.2-cp310-cp310-win_amd64.whl",
        url=(
            "https://files.pythonhosted.org/packages/cd/6d/"
            "738e50c47c2fd285b1e6c8083f15dac1a5f6199213378a5f14092497296d/"
            "onnxruntime-1.23.2-cp310-cp310-win_amd64.whl"
        ),
        size_bytes=13_467_651,
        sha256="0be6a37a45e6719db5120e9986fcd30ea205ac8103fd1fb74b6c33348327a0cc",
        target_name="cpu",
    ),
    "gpu": AIResourceSpec(
        key="runtime_gpu",
        kind="runtime",
        display_name="NVIDIA GPU 推理运行时",
        version=ONNXRUNTIME_VERSION,
        filename="onnxruntime_gpu-1.23.2-cp310-cp310-win_amd64.whl",
        url=(
            "https://files.pythonhosted.org/packages/21/c9/"
            "47abd3ec1f34498224d2a8f5cc4d1445eb5cc7dee8e3644b1a972619c0d2/"
            "onnxruntime_gpu-1.23.2-cp310-cp310-win_amd64.whl"
        ),
        size_bytes=244_505_340,
        sha256="deba091e15357355aa836fd64c6c4ac97dd0c4609c38b08a69675073ea46b321",
        target_name="gpu",
    ),
}


MODEL_RESOURCES: Dict[str, AIResourceSpec] = {
    "speed": AIResourceSpec(
        key="model_speed",
        kind="model",
        display_name="速度优先基础模型",
        version="1",
        filename="ai-model-speed-v1.zip",
        url=f"{AI_RESOURCE_RELEASE_BASE}/ai-model-speed-v1.zip",
        size_bytes=11_014_104,
        sha256="103f843a29c8b441733dced1e4edf574ecc4a63f93f6a2c696d244e6c0e67994",
        target_name="mobilenet_v3_large_embedding_v1",
        expected_model_id="mobilenet-v3-large-imagenet-embedding-v1",
    ),
    "balanced": AIResourceSpec(
        key="model_balanced",
        kind="model",
        display_name="均衡版本基础模型",
        version="1",
        filename="ai-model-balanced-v1.zip",
        url=f"{AI_RESOURCE_RELEASE_BASE}/ai-model-balanced-v1.zip",
        size_bytes=41_468_422,
        sha256="41a5f659e92f8255ee6e7a2f87bddd158a8ac1d252474267601c568171469486",
        target_name="resnet18_embedding_v1",
        expected_model_id="resnet18-imagenet-embedding-v1",
    ),
    "accuracy": AIResourceSpec(
        key="model_accuracy",
        kind="model",
        display_name="精度优先基础模型",
        version="1",
        filename="ai-model-accuracy-v1.zip",
        url=f"{AI_RESOURCE_RELEASE_BASE}/ai-model-accuracy-v1.zip",
        size_bytes=81_896_890,
        sha256="29f3b87748dd1dfebb2b63080f54ed86227c46c096b75c9060df91e3acc84140",
        target_name="dinov2_vits14_embedding_v1",
        expected_model_id="dinov2-vits14-embedding-v1",
    ),
}


def format_resource_size(size_bytes: int) -> str:
    """Return a compact binary-size label for the model configuration page."""
    return f"{size_bytes / (1024 * 1024):.1f} MiB"


def get_runtime_resource(runtime_kind: str) -> AIResourceSpec:
    """Return the versioned CPU or NVIDIA runtime resource."""
    return RUNTIME_RESOURCES["gpu" if runtime_kind == "gpu" else "cpu"]


def get_model_resource(model_key: str) -> AIResourceSpec:
    """Return the base-model resource for a built-in profile."""
    return MODEL_RESOURCES[get_ai_model_profile(model_key).key]


def required_runtime_kind(
    profile: AIModelProfile, execution_provider: str
) -> Optional[str]:
    """Return the external runtime needed by this model/device selection."""
    if execution_provider in ("auto", "cuda"):
        return "gpu"
    if profile.cpu_backend == "onnxruntime":
        return "cpu"
    return None


def resource_target_dir(spec: AIResourceSpec) -> Path:
    """Return the final external installation directory for a resource."""
    if spec.kind == "runtime":
        return get_ai_runtime_dir(spec.target_name, spec.version)
    return get_ai_model_dir(spec.target_name)


def _marker_path(spec: AIResourceSpec) -> Path:
    return resource_target_dir(spec) / ".resource.json"


def _read_model_manifest(target: Path) -> Optional[dict]:
    manifest_path = target / "manifest.json"
    try:
        value = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    return value if isinstance(value, dict) else None


def is_resource_installed(spec: AIResourceSpec) -> bool:
    """Check installation markers and the files required for inference."""
    target = resource_target_dir(spec)
    if spec.kind == "model":
        manifest = _read_model_manifest(target)
        if not manifest or manifest.get("model_id") != spec.expected_model_id:
            return False
        model_file = manifest.get("model_file")
        return bool(model_file and (target / str(model_file)).is_file())

    marker_path = _marker_path(spec)
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return False
    package_dir = target / "onnxruntime"
    capi_dir = package_dir / "capi"
    return bool(
        marker.get("sha256") == spec.sha256
        and marker.get("version") == spec.version
        and (package_dir / "__init__.py").is_file()
        and capi_dir.is_dir()
        and any(capi_dir.glob("onnxruntime_pybind11_state*.pyd"))
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_extract(archive: Path, destination: Path) -> None:
    destination = destination.resolve()
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            member_path = (destination / member.filename).resolve()
            try:
                member_path.relative_to(destination)
            except ValueError as error:
                raise RuntimeError("AI 资源包包含不安全的文件路径") from error
        bundle.extractall(destination)


def _validate_extracted_resource(spec: AIResourceSpec, directory: Path) -> None:
    if spec.kind == "runtime":
        package_dir = directory / "onnxruntime"
        capi_dir = package_dir / "capi"
        if not (package_dir / "__init__.py").is_file() or not any(
            capi_dir.glob("onnxruntime_pybind11_state*.pyd")
        ):
            raise RuntimeError("下载的 ONNX Runtime 资源包结构不完整")
        return

    manifest = _read_model_manifest(directory)
    if not manifest or manifest.get("model_id") != spec.expected_model_id:
        raise RuntimeError("下载的基础模型与所选模型不匹配")
    model_file = manifest.get("model_file")
    if not model_file or not (directory / str(model_file)).is_file():
        raise RuntimeError("下载的基础模型文件不完整")


def install_downloaded_resource(spec: AIResourceSpec, archive: Path) -> Path:
    """Verify and atomically install one downloaded wheel/ZIP resource."""
    archive = Path(archive)
    if not archive.is_file() or archive.stat().st_size != spec.size_bytes:
        raise RuntimeError("AI 资源下载大小校验失败")
    if _sha256(archive).lower() != spec.sha256.lower():
        raise RuntimeError("AI 资源 SHA-256 校验失败")

    target = resource_target_dir(spec)
    target.parent.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    staging = target.with_name(f".{target.name}.installing-{token}")
    backup = target.with_name(f".{target.name}.backup-{token}")
    try:
        staging.mkdir(parents=True)
        _safe_extract(archive, staging)
        _validate_extracted_resource(spec, staging)
        marker = {
            "schema_version": 1,
            "key": spec.key,
            "kind": spec.kind,
            "version": spec.version,
            "sha256": spec.sha256,
            "source_url": spec.url,
        }
        (staging / ".resource.json").write_text(
            json.dumps(marker, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if target.exists():
            target.replace(backup)
        staging.replace(target)
        if backup.exists():
            shutil.rmtree(backup)
        return target
    except Exception:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        if backup.exists() and not target.exists():
            backup.replace(target)
        raise


def download_and_install_resource(
    spec: AIResourceSpec,
    progress_cb: Optional[Callable[[int, Optional[int]], None]] = None,
    cancel_cb: Optional[Callable[[], bool]] = None,
    status_cb: Optional[Callable[[str], None]] = None,
    proxy: str = "",
) -> Path:
    """Download with resume support, verify, and atomically install a resource."""
    download_dir = get_ai_download_dir()
    partial = download_dir / f"{spec.filename}.part"
    if status_cb:
        status_cb(f"正在下载 {spec.display_name}…")
    download_with_progress(
        spec.url,
        partial,
        progress_cb=progress_cb,
        cancel_cb=cancel_cb,
        expected_size=spec.size_bytes,
        retries=5,
        retry_delay=1.0,
        proxy=proxy,
    )
    if status_cb:
        status_cb(f"正在校验并安装 {spec.display_name}…")
    try:
        target = install_downloaded_resource(spec, partial)
    except Exception:
        # A complete but invalid archive would otherwise be treated as a
        # finished resumable download forever and every retry would fail again.
        partial.unlink(missing_ok=True)
        raise
    partial.unlink(missing_ok=True)
    return target


_ACTIVE_RUNTIME_KIND: Optional[str] = None
_DLL_DIRECTORY_HANDLES = []


def load_onnxruntime(runtime_kind: str):
    """Load an installed external ONNX Runtime into this process."""
    global _ACTIVE_RUNTIME_KIND
    runtime_kind = "gpu" if runtime_kind == "gpu" else "cpu"
    spec = get_runtime_resource(runtime_kind)

    loaded = sys.modules.get("onnxruntime")
    if loaded is not None:
        if _ACTIVE_RUNTIME_KIND == "cpu" and runtime_kind == "gpu":
            raise RuntimeError("CPU 运行时已加载，切换 NVIDIA GPU 后需重启软件")
        return loaded

    target = resource_target_dir(spec)
    if not is_resource_installed(spec):
        # Source checkouts may use their Python environment. Frozen releases
        # intentionally require a verified external resource installation.
        if not getattr(sys, "frozen", False):
            module = importlib.import_module("onnxruntime")
            _ACTIVE_RUNTIME_KIND = runtime_kind
            return module
        raise RuntimeError(f"{spec.display_name}尚未下载")

    target_text = str(target)
    if target_text not in sys.path:
        sys.path.insert(0, target_text)
    capi_dir = target / "onnxruntime" / "capi"
    if os.name == "nt" and hasattr(os, "add_dll_directory"):
        _DLL_DIRECTORY_HANDLES.append(os.add_dll_directory(str(capi_dir)))
    importlib.invalidate_caches()
    module = importlib.import_module("onnxruntime")
    _ACTIVE_RUNTIME_KIND = runtime_kind
    return module
