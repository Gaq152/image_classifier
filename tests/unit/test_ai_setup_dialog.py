"""Tests for project AI learning-scope choices."""

import json
import threading
from unittest.mock import patch

import numpy as np

from core.ai import default_ai_project_state
from ui.ai_resource_download import AIResourceDownloadManager
from ui.dialogs.ai_setup_dialog import AIProjectSetupDialog


def _write_balanced_base_model(directory):
    (directory / "manifest.json").write_text(
        json.dumps(
            {
                "model_id": "resnet18-imagenet-embedding-v1",
                "model_file": "model.onnx",
            }
        ),
        encoding="utf-8",
    )
    (directory / "model.onnx").touch()


def _write_feature_store(path, model_id="resnet18-imagenet-embedding-v1"):
    np.savez_compressed(
        path,
        store_version=np.asarray([1]),
        model_id=np.asarray([model_id]),
        paths=np.asarray(["old/a.jpg"]),
        labels=np.asarray(["类别A"]),
        deep=np.zeros((1, 512), dtype=np.float16),
        colors=np.zeros((1, 512), dtype=np.float16),
    )


def test_removed_directory_learning_is_off_by_default(qtbot, tmp_path):
    _write_balanced_base_model(tmp_path)
    with patch(
        "ui.dialogs.ai_setup_dialog.get_ai_model_dir",
        return_value=tmp_path,
    ), patch(
        "ui.dialogs.ai_setup_dialog.is_resource_installed",
        return_value=True,
    ):
        dialog = AIProjectSetupDialog(
            project_dir=tmp_path,
            ai_state=default_ai_project_state(),
            existing_sample_count=12,
            removed_sample_count=7,
        )
    qtbot.addWidget(dialog)

    assert dialog.selected_learn_removed_images is False
    assert "忽略移除 7 张" in dialog.existing_radio.text()

    dialog.learn_removed_checkbox.setChecked(True)

    assert dialog.selected_learn_removed_images is True
    assert "含移除 7 张" in dialog.existing_radio.text()


def test_existing_npz_can_be_selected_without_old_images(qtbot, tmp_path):
    _write_balanced_base_model(tmp_path)
    store_path = tmp_path / "old-model.npz"
    _write_feature_store(store_path)
    with patch(
        "ui.dialogs.ai_setup_dialog.get_ai_model_dir",
        return_value=tmp_path,
    ), patch(
        "ui.dialogs.ai_setup_dialog.is_resource_installed",
        return_value=True,
    ):
        dialog = AIProjectSetupDialog(
            project_dir=tmp_path,
            ai_state=default_ai_project_state(),
            existing_sample_count=0,
        )
    qtbot.addWidget(dialog)
    dialog.import_model_path = store_path
    dialog.model_store_radio.setChecked(True)

    dialog.accept()

    assert dialog.result() == dialog.DialogCode.Accepted
    assert dialog.selected_model_store_path == store_path


def test_npz_from_another_base_model_is_rejected(qtbot, tmp_path):
    _write_balanced_base_model(tmp_path)
    store_path = tmp_path / "speed-model.npz"
    _write_feature_store(
        store_path,
        model_id="mobilenet-v3-large-imagenet-embedding-v1",
    )
    with patch(
        "ui.dialogs.ai_setup_dialog.get_ai_model_dir",
        return_value=tmp_path,
    ), patch(
        "ui.dialogs.ai_setup_dialog.is_resource_installed",
        return_value=True,
    ):
        dialog = AIProjectSetupDialog(
            project_dir=tmp_path,
            ai_state=default_ai_project_state(),
            existing_sample_count=0,
        )
    qtbot.addWidget(dialog)
    dialog.import_model_path = store_path
    dialog.model_store_radio.setChecked(True)

    dialog.accept()

    assert dialog.result() != dialog.DialogCode.Accepted
    assert "基础模型不匹配" in dialog.model_store_path_label.text()


def test_initialized_model_can_be_safely_reinitialized(qtbot, tmp_path):
    _write_balanced_base_model(tmp_path)
    (tmp_path / "ai_model_balanced_v1.npz").touch()
    state = default_ai_project_state()
    state["models"]["balanced"] = {
        "initialized": True,
        "project_model_file": "ai_model_balanced_v1.npz",
    }
    with patch(
        "ui.dialogs.ai_setup_dialog.get_ai_model_dir",
        return_value=tmp_path,
    ), patch(
        "ui.dialogs.ai_setup_dialog.is_resource_installed",
        return_value=True,
    ):
        dialog = AIProjectSetupDialog(
            project_dir=tmp_path,
            ai_state=state,
            existing_sample_count=12,
        )
    qtbot.addWidget(dialog)

    assert dialog.reinitialize_checkbox.isEnabled()
    assert not dialog.source_group_box.isEnabled()
    assert dialog.confirm_button.text() == "切换并加载"

    with patch(
        "ui.dialogs.ai_setup_dialog.get_ai_model_dir",
        return_value=tmp_path,
    ), patch(
        "ui.dialogs.ai_setup_dialog.is_resource_installed",
        return_value=True,
    ):
        dialog.reinitialize_checkbox.setChecked(True)

        assert dialog.selected_reinitialize is True
        assert dialog.source_group_box.isEnabled()
        assert dialog.confirm_button.text() == "重新初始化 AI"


def test_gpu_auto_selection_is_explained_without_blocking_model(qtbot, tmp_path):
    _write_balanced_base_model(tmp_path)
    with patch(
        "ui.dialogs.ai_setup_dialog.get_ai_model_dir",
        return_value=tmp_path,
    ), patch(
        "ui.dialogs.ai_setup_dialog.is_resource_installed",
        return_value=True,
    ):
        dialog = AIProjectSetupDialog(
            project_dir=tmp_path,
            ai_state=default_ai_project_state(),
            existing_sample_count=6,
        )
    qtbot.addWidget(dialog)

    assert dialog.model_buttons["balanced"].isEnabled()
    assert "NVIDIA GPU" in dialog.warning_label.text()

    dialog.provider_combo.setCurrentIndex(
        dialog.provider_combo.findData("cpu")
    )

    assert dialog.selected_execution_provider == "cpu"
    assert "CPU" in dialog.warning_label.text()


def test_missing_resources_are_shown_with_separate_progress_bars(qtbot, tmp_path):
    with patch(
        "ui.dialogs.ai_setup_dialog.get_ai_model_dir",
        return_value=tmp_path / "missing-model",
    ), patch(
        "ui.dialogs.ai_setup_dialog.is_resource_installed",
        return_value=False,
    ):
        dialog = AIProjectSetupDialog(
            project_dir=tmp_path,
            ai_state=default_ai_project_state(),
            existing_sample_count=0,
        )
    qtbot.addWidget(dialog)

    assert dialog.confirm_button.text() == "下载并初始化 AI"
    assert "需要下载" in dialog.runtime_status_label.text()
    assert "需要下载" in dialog.model_status_label.text()
    assert dialog.runtime_progress.format() == "等待下载"
    assert dialog.model_progress.format() == "等待下载"


def test_closing_setup_dialog_keeps_main_window_download_running(qtbot, tmp_path):
    """The dialog observes downloads but no longer owns their lifetime."""
    started = threading.Event()
    release = threading.Event()

    def fake_download(resource, progress_cb, cancel_cb, status_cb, proxy):
        status_cb(f"正在下载 {resource.display_name}…")
        progress_cb(1024, resource.size_bytes)
        started.set()
        release.wait(timeout=5)

    manager = AIResourceDownloadManager()
    with patch(
        "ui.dialogs.ai_setup_dialog.get_ai_model_dir",
        return_value=tmp_path / "missing-model",
    ), patch(
        "ui.dialogs.ai_setup_dialog.is_resource_installed",
        return_value=False,
    ), patch(
        "ui.ai_resource_download.download_and_install_resource",
        side_effect=fake_download,
    ):
        dialog = AIProjectSetupDialog(
            project_dir=tmp_path,
            ai_state=default_ai_project_state(),
            existing_sample_count=0,
            resource_download_manager=manager,
        )
        qtbot.addWidget(dialog)
        dialog.show()

        dialog._download_model()
        qtbot.waitUntil(started.is_set, timeout=2000)
        assert "后台下载中" in dialog.model_download_button.text()

        dialog.reject()

        assert not dialog.isVisible()
        assert manager.has_active_downloads

        release.set()
        qtbot.waitUntil(
            lambda: not manager.has_active_downloads, timeout=3000
        )
