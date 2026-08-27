"""Product-edition identity and isolated updater tests."""

import io
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import _build_channel_
import build as build_module
from _version_ import get_download_urls, get_manifest_url
from build import _build_channel_source
from core.update_utils import ensure_persistent_updater, fetch_manifest
from product_channel import get_current_edition, get_product_info
from utils.paths import get_update_dir


class JsonResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


def test_standard_and_ai_release_urls_are_isolated():
    assert get_manifest_url(edition="standard").endswith(
        "/releases/latest/download/manifest.json"
    )
    assert get_manifest_url(edition="ai").endswith(
        "/releases/download/ai-latest/manifest.json"
    )

    standard = get_download_urls("standard")
    ai = get_download_urls("ai")
    assert standard["release_tag"].startswith("v")
    assert standard["exe_name"].startswith("ImageClassifier_v")
    assert ai["release_tag"].startswith("ai-v")
    assert ai["exe_name"].startswith("ImageClassifierAI_v")
    assert ai["rolling_exe_name"] == "ImageClassifierAI_latest.exe"
    assert get_product_info("standard")["icon_basename"] == "icon"
    assert get_product_info("ai")["icon_basename"] == "icon-ai"


def test_embedded_ai_edition_changes_identity_and_update_directory(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(_build_channel_, "APP_EDITION", "ai")
    monkeypatch.setattr("utils.paths.get_app_data_dir", lambda: tmp_path)

    assert get_current_edition() == "ai"
    assert get_product_info()["application_name"] == "图像分类工具 AI版"
    assert get_update_dir() == tmp_path / "update" / "ai"


def test_standard_manifest_keeps_legacy_compatibility(monkeypatch):
    monkeypatch.setattr(_build_channel_, "APP_EDITION", "standard")
    response = JsonResponse(json.dumps({"version": "9.9.9"}).encode())

    with patch("core.update_utils.urlopen", return_value=response):
        manifest = fetch_manifest("https://example.invalid/manifest.json", retries=0)

    assert manifest["version"] == "9.9.9"


def test_ai_build_rejects_standard_manifest(monkeypatch):
    monkeypatch.setattr(_build_channel_, "APP_EDITION", "ai")
    response = JsonResponse(
        json.dumps(
            {
                "version": "9.9.9",
                "edition": "standard",
                "channel": "stable",
            }
        ).encode()
    )

    with (
        patch("core.update_utils.urlopen", return_value=response),
        pytest.raises(RuntimeError, match="非 AI 更新清单"),
    ):
        fetch_manifest("https://example.invalid/manifest.json", retries=0)


def test_ai_manifest_and_persistent_updater_use_ai_latest(monkeypatch, tmp_path):
    monkeypatch.setattr(_build_channel_, "APP_EDITION", "ai")
    monkeypatch.setattr(
        "core.update_utils.get_update_dir", lambda: tmp_path / "update" / "ai"
    )
    response = JsonResponse(
        json.dumps(
            {"version": "9.9.9", "edition": "ai", "channel": "ai"}
        ).encode()
    )
    with patch("core.update_utils.urlopen", return_value=response):
        manifest = fetch_manifest("https://example.invalid/manifest.json", retries=0)
    assert manifest["edition"] == "ai"

    updater = ensure_persistent_updater(tmp_path / "ImageClassifierAI.exe")
    content = updater.read_text(encoding="utf-8")
    assert "/releases/download/ai-latest/manifest.json" in content


def test_build_channel_source_is_deterministic():
    assert 'APP_EDITION = "standard"' in _build_channel_source("unknown")
    assert 'APP_EDITION = "ai"' in _build_channel_source("ai")


def test_ai_build_embeds_edition_and_restores_source(monkeypatch, tmp_path):
    channel_file = tmp_path / "_build_channel_.py"
    original = 'APP_EDITION = "standard"\n'
    channel_file.write_text(original, encoding="utf-8")
    (tmp_path / "dist").mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(build_module, "BUILD_CHANNEL_FILE", channel_file)

    def fake_pyinstaller(_command, **_kwargs):
        assert 'APP_EDITION = "ai"' in channel_file.read_text(encoding="utf-8")
        icon_index = _command.index("--icon") + 1
        assert _command[icon_index] == "assets/icon-ai.ico"
        output = (
            tmp_path
            / "dist"
            / f"ImageClassifierAI_v{build_module.__version__}.exe"
        )
        output.write_bytes(b"fake-ai-executable")
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(build_module.subprocess, "run", fake_pyinstaller)

    assert build_module.build_executable("ai") is True
    assert channel_file.read_text(encoding="utf-8") == original
    assert (
        tmp_path
        / "dist"
        / f"图像分类工具AI版_v{build_module.__version__}.exe"
    ).is_file()


def test_ai_workflow_uses_distinct_tag_and_rolling_channel():
    workflow = Path(".github/workflows/build-ai-release.yml").read_text(
        encoding="utf-8"
    )
    assert "ai-v*" in workflow
    assert "python build.py --edition ai" in workflow
    assert "tag_name: ai-latest" in workflow
    assert 'edition = "ai"' in workflow
    assert 'channel = "ai"' in workflow
