"""Tests for optional AI runtime and base-model resources."""

import hashlib
import json
import zipfile

import pytest

from core.ai.model_registry import get_ai_model_profile
from core.ai.resource_manager import (
    AIResourceSpec,
    RUNTIME_RESOURCES,
    download_and_install_resource,
    install_downloaded_resource,
    required_runtime_kind,
)


def _model_bundle(path, model_id="test-model"):
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr(
            "manifest.json",
            json.dumps({"model_id": model_id, "model_file": "model.onnx"}),
        )
        bundle.writestr("model.onnx", b"fake-onnx")


def _resource_for(path, sha256):
    return AIResourceSpec(
        key="model_test",
        kind="model",
        display_name="测试模型",
        version="1",
        filename=path.name,
        url="https://example.invalid/model.zip",
        size_bytes=path.stat().st_size,
        sha256=sha256,
        target_name="test-model",
        expected_model_id="test-model",
    )


def test_runtime_download_sizes_are_explicit():
    assert RUNTIME_RESOURCES["cpu"].size_bytes == 13_467_651
    assert RUNTIME_RESOURCES["gpu"].size_bytes == 244_505_340
    assert len(RUNTIME_RESOURCES["gpu"].sha256) == 64


def test_runtime_requirement_depends_on_model_and_provider():
    balanced = get_ai_model_profile("balanced")
    accuracy = get_ai_model_profile("accuracy")

    assert required_runtime_kind(balanced, "cpu") is None
    assert required_runtime_kind(balanced, "auto") == "gpu"
    assert required_runtime_kind(accuracy, "cpu") == "cpu"
    assert required_runtime_kind(accuracy, "cuda") == "gpu"


def test_model_resource_is_verified_and_installed_atomically(monkeypatch, tmp_path):
    archive = tmp_path / "model.zip"
    _model_bundle(archive)
    sha256 = hashlib.sha256(archive.read_bytes()).hexdigest()
    resource = _resource_for(archive, sha256)
    target = tmp_path / "installed"
    monkeypatch.setattr(
        "core.ai.resource_manager.resource_target_dir", lambda _spec: target
    )

    result = install_downloaded_resource(resource, archive)

    assert result == target
    assert (target / "model.onnx").read_bytes() == b"fake-onnx"
    marker = json.loads((target / ".resource.json").read_text(encoding="utf-8"))
    assert marker["sha256"] == sha256


def test_bad_resource_hash_is_rejected(monkeypatch, tmp_path):
    archive = tmp_path / "model.zip"
    _model_bundle(archive)
    resource = _resource_for(archive, "0" * 64)
    target = tmp_path / "installed"
    monkeypatch.setattr(
        "core.ai.resource_manager.resource_target_dir", lambda _spec: target
    )

    with pytest.raises(RuntimeError, match="SHA-256"):
        install_downloaded_resource(resource, archive)

    assert not target.exists()


def test_corrupt_complete_download_is_removed_before_retry(monkeypatch, tmp_path):
    archive = tmp_path / "source.zip"
    _model_bundle(archive)
    resource = _resource_for(archive, "0" * 64)
    download_dir = tmp_path / "downloads"
    download_dir.mkdir()

    def fake_download(_url, destination, **_kwargs):
        destination.write_bytes(archive.read_bytes())

    monkeypatch.setattr(
        "core.ai.resource_manager.get_ai_download_dir", lambda: download_dir
    )
    monkeypatch.setattr(
        "core.ai.resource_manager.download_with_progress", fake_download
    )

    with pytest.raises(RuntimeError, match="SHA-256"):
        download_and_install_resource(resource)

    assert not (download_dir / f"{resource.filename}.part").exists()
