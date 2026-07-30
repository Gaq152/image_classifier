"""Tests for project AI learning-scope choices."""

from unittest.mock import patch

from core.ai import default_ai_project_state
from ui.dialogs.ai_setup_dialog import AIProjectSetupDialog


def test_removed_directory_learning_is_off_by_default(qtbot, tmp_path):
    (tmp_path / "manifest.json").write_text("{}", encoding="utf-8")
    with patch(
        "ui.dialogs.ai_setup_dialog.get_ai_model_dir",
        return_value=tmp_path,
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


def test_initialized_model_can_be_safely_reinitialized(qtbot, tmp_path):
    (tmp_path / "manifest.json").write_text("{}", encoding="utf-8")
    (tmp_path / "ai_model_balanced_v1.npz").touch()
    state = default_ai_project_state()
    state["models"]["balanced"] = {
        "initialized": True,
        "project_model_file": "ai_model_balanced_v1.npz",
    }
    with patch(
        "ui.dialogs.ai_setup_dialog.get_ai_model_dir",
        return_value=tmp_path,
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

    dialog.reinitialize_checkbox.setChecked(True)

    assert dialog.selected_reinitialize is True
    assert dialog.source_group_box.isEnabled()
    assert dialog.confirm_button.text() == "重新初始化 AI"
