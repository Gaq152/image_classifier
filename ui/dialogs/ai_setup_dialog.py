"""Project-level AI initialization and model selection dialog."""

from pathlib import Path
from typing import Dict, Optional

from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
)

from core.ai import iter_ai_model_profiles
from utils.paths import get_ai_model_dir

from ..components.dialog_utils import configure_dialog, style_button
from ..components.styles.theme import default_theme


class AIProjectSetupDialog(QDialog):
    """Collect a base model and cold-start/import strategy for one project."""

    def __init__(
        self,
        project_dir: Path,
        ai_state: Dict,
        existing_sample_count: int,
        removed_sample_count: int = 0,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.project_dir = Path(project_dir)
        self.ai_state = ai_state
        self.existing_sample_count = existing_sample_count
        self.removed_sample_count = removed_sample_count
        self.import_state_path: Optional[Path] = None
        self.model_buttons: Dict[str, QRadioButton] = {}

        self.setWindowTitle("初始化项目 AI")
        self.setModal(True)
        self.setMinimumWidth(600)

        layout = QVBoxLayout(self)
        configure_dialog(self, layout)
        self._build_intro(layout)
        self._build_model_options(layout)
        self._build_reinitialize_option(layout)
        self._build_source_options(layout)
        self._build_learning_options(layout)
        self._build_actions(layout)
        self._refresh_selection_details()

    def _build_intro(self, layout: QVBoxLayout) -> None:
        title = QLabel("为当前目录配置 AI 辅助分类")
        title.setProperty("uiRole", "title")
        layout.addWidget(title)
        description = QLabel(
            "基础模型只负责提取通用视觉特征；本项目学习出的样本库会与 "
            "classification_state.json 保存在同一目录。"
        )
        description.setWordWrap(True)
        layout.addWidget(description)

    def _build_model_options(self, layout: QVBoxLayout) -> None:
        group = QGroupBox("1. 选择基础模型")
        group_layout = QVBoxLayout(group)
        self.model_group = QButtonGroup(self)
        active_model = self.ai_state.get("active_model", "balanced")
        model_records = self.ai_state.get("models", {})

        for profile in iter_ai_model_profiles():
            installed = (
                get_ai_model_dir(profile.model_dir_name) / "manifest.json"
            ).is_file()
            initialized = bool(
                isinstance(model_records.get(profile.key), dict)
                and model_records[profile.key].get("initialized")
                and (self.project_dir / profile.project_model_file).is_file()
            )
            flags = []
            if initialized:
                flags.append("本项目已初始化")
            if not installed:
                flags.append("基础模型未安装")
            suffix = f"（{' · '.join(flags)}）" if flags else ""
            button = QRadioButton(
                f"{profile.display_name}{suffix}\n"
                f"{profile.description}\n{profile.cpu_note}"
            )
            button.setProperty("modelKey", profile.key)
            button.setEnabled(installed)
            button.toggled.connect(self._refresh_selection_details)
            self.model_group.addButton(button)
            self.model_buttons[profile.key] = button
            group_layout.addWidget(button)
            if profile.key == active_model and installed:
                button.setChecked(True)

        if not any(button.isChecked() for button in self.model_buttons.values()):
            for button in self.model_buttons.values():
                if button.isEnabled():
                    button.setChecked(True)
                    break
        layout.addWidget(group)

    def _build_reinitialize_option(self, layout: QVBoxLayout) -> None:
        self.reinitialize_checkbox = QCheckBox(
            "重新初始化所选模型（旧模型保留到新模型构建成功）"
        )
        self.reinitialize_checkbox.toggled.connect(
            self._refresh_selection_details
        )
        layout.addWidget(self.reinitialize_checkbox)

    def _build_source_options(self, layout: QVBoxLayout) -> None:
        self.source_group_box = QGroupBox("2. 选择样本来源")
        source_layout = QVBoxLayout(self.source_group_box)
        self.source_group = QButtonGroup(self)

        self.existing_radio = QRadioButton()
        self.existing_radio.setProperty("sourceKind", "existing")
        self.existing_radio.setEnabled(self.existing_sample_count > 0)
        self.cold_start_radio = QRadioButton("从零开始，由后续人工分类逐步学习")
        self.cold_start_radio.setProperty("sourceKind", "cold_start")
        self.import_radio = QRadioButton("导入其他 classification_state.json")
        self.import_radio.setProperty("sourceKind", "import")
        for button in (
            self.existing_radio,
            self.cold_start_radio,
            self.import_radio,
        ):
            self.source_group.addButton(button)
            source_layout.addWidget(button)

        if self.existing_sample_count > 0:
            self.existing_radio.setChecked(True)
        else:
            self.cold_start_radio.setChecked(True)

        import_row = QHBoxLayout()
        self.import_path_label = QLabel("尚未选择文件")
        self.import_path_label.setWordWrap(True)
        self.import_button = QPushButton("选择 JSON…")
        style_button(self.import_button, "secondary", "compact")
        self.import_button.clicked.connect(self._choose_import_file)
        import_row.addWidget(self.import_path_label, 1)
        import_row.addWidget(self.import_button)
        source_layout.addLayout(import_row)

        self.source_hint = QLabel(
            "冷启动阶段每个类别至少需要 5 张有效样本；建议达到每类 20 张后再依赖预测。"
        )
        self.source_hint.setWordWrap(True)
        source_layout.addWidget(self.source_hint)
        layout.addWidget(self.source_group_box)

    def _build_learning_options(self, layout: QVBoxLayout) -> None:
        group = QGroupBox("3. 选择学习范围")
        group_layout = QVBoxLayout(group)
        self.learn_removed_checkbox = QCheckBox(
            "让 AI 学习“移除”目录，并提供移除建议"
        )
        self.learn_removed_checkbox.setChecked(
            bool(self.ai_state.get("learn_removed_images", False))
        )
        self.learn_removed_checkbox.toggled.connect(
            self._refresh_existing_sample_details
        )
        group_layout.addWidget(self.learn_removed_checkbox)

        hint = QLabel(
            "默认关闭。移除通常表示跳过或暂不分类，不一定具有统一视觉特征；"
            "关闭后，已有和之后移除的图片都不会参与学习。"
        )
        hint.setWordWrap(True)
        group_layout.addWidget(hint)
        layout.addWidget(group)
        self._refresh_existing_sample_details()

    def _refresh_existing_sample_details(self) -> None:
        include_removed = self.selected_learn_removed_images
        total = self.existing_sample_count
        removed_note = f"，忽略移除 {self.removed_sample_count} 张"
        if include_removed:
            total += self.removed_sample_count
            removed_note = f"，含移除 {self.removed_sample_count} 张"
        self.existing_radio.setText(
            f"使用本目录已有人工标注（分类 {self.existing_sample_count} 张"
            f"{removed_note}）"
        )
        self.existing_radio.setEnabled(total > 0)
        if total == 0 and self.existing_radio.isChecked():
            self.cold_start_radio.setChecked(True)

    def _build_actions(self, layout: QVBoxLayout) -> None:
        self.warning_label = QLabel()
        self.warning_label.setWordWrap(True)
        self.warning_label.setStyleSheet(
            f"color: {default_theme.colors.WARNING}; font-weight: 600;"
        )
        layout.addWidget(self.warning_label)

        actions = QHBoxLayout()
        actions.addStretch()
        cancel_button = QPushButton("取消")
        self.confirm_button = QPushButton("初始化 AI")
        style_button(cancel_button, "secondary")
        style_button(self.confirm_button, "primary")
        cancel_button.clicked.connect(self.reject)
        self.confirm_button.clicked.connect(self.accept)
        actions.addWidget(cancel_button)
        actions.addWidget(self.confirm_button)
        layout.addLayout(actions)

    def _choose_import_file(self) -> None:
        file_name, _ = QFileDialog.getOpenFileName(
            self,
            "选择旧的人工分类状态",
            str(self.project_dir),
            "分类状态 (classification_state.json *.json)",
        )
        if not file_name:
            return
        self.import_state_path = Path(file_name)
        self.import_path_label.setText(str(self.import_state_path))
        self.import_radio.setChecked(True)

    def _refresh_selection_details(self) -> None:
        key = self.selected_model_key
        if not key or not hasattr(self, "source_group_box"):
            return
        record = self.ai_state.get("models", {}).get(key, {})
        initialized = bool(
            isinstance(record, dict)
            and record.get("initialized")
            and (self.project_dir / record.get("project_model_file", "")).is_file()
        )
        self.reinitialize_checkbox.blockSignals(True)
        if not initialized:
            self.reinitialize_checkbox.setChecked(False)
        self.reinitialize_checkbox.setEnabled(initialized)
        self.reinitialize_checkbox.blockSignals(False)
        reinitialize = initialized and self.selected_reinitialize
        self.source_group_box.setEnabled(not initialized or reinitialize)
        if reinitialize:
            self.confirm_button.setText("重新初始化 AI")
        else:
            self.confirm_button.setText("切换并加载" if initialized else "初始化 AI")
        profile = next(
            profile for profile in iter_ai_model_profiles() if profile.key == key
        )
        if profile.recommended_gpu:
            self.warning_label.setText(
                "⚠ 当前版本仅使用 CPU。精度优先模型推理和首次建库可能明显较慢；"
                "无 GPU 时不建议在大量图片上使用。"
            )
        else:
            self.warning_label.setText(profile.cpu_note)

    @property
    def selected_model_key(self) -> Optional[str]:
        for key, button in self.model_buttons.items():
            if button.isChecked():
                return key
        return None

    @property
    def selected_source_kind(self) -> str:
        checked = self.source_group.checkedButton()
        return checked.property("sourceKind") if checked else "cold_start"

    @property
    def selected_import_path(self) -> Optional[Path]:
        return self.import_state_path

    @property
    def selected_learn_removed_images(self) -> bool:
        checkbox = getattr(self, "learn_removed_checkbox", None)
        return bool(checkbox and checkbox.isChecked())

    @property
    def selected_reinitialize(self) -> bool:
        checkbox = getattr(self, "reinitialize_checkbox", None)
        return bool(checkbox and checkbox.isEnabled() and checkbox.isChecked())

    def accept(self) -> None:
        key = self.selected_model_key
        if key is None:
            return
        record = self.ai_state.get("models", {}).get(key, {})
        initialized = bool(
            isinstance(record, dict)
            and record.get("initialized")
            and (self.project_dir / record.get("project_model_file", "")).is_file()
        )
        if (
            (not initialized or self.selected_reinitialize)
            and self.selected_source_kind == "import"
        ):
            if self.import_state_path is None or not self.import_state_path.is_file():
                self.import_path_label.setText("请先选择有效的 classification_state.json")
                self.import_path_label.setStyleSheet(
                    f"color: {default_theme.colors.ERROR};"
                )
                return
        super().accept()
