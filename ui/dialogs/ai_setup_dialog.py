"""Project-level AI initialization and model selection dialog."""

from pathlib import Path
from typing import Dict, Optional

from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
)

from core.ai import (
    format_resource_size,
    get_ai_model_profile,
    get_model_resource,
    get_runtime_resource,
    is_resource_installed,
    iter_ai_model_profiles,
    required_runtime_kind,
)
from utils.app_config import get_app_config
from utils.paths import get_ai_model_dir

from ..ai_resource_download import AIResourceDownloadThread
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
        self._download_workers: Dict[str, AIResourceDownloadThread] = {}
        self._download_errors: Dict[str, tuple[str, str]] = {}
        self._pending_accept = False
        self._close_after_download_cancel = False

        self.setWindowTitle("初始化项目 AI")
        self.setModal(True)
        self.setMinimumWidth(600)

        layout = QVBoxLayout(self)
        configure_dialog(self, layout)
        self._build_intro(layout)
        self._build_model_options(layout)
        self._build_resource_downloads(layout)
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
        group = QGroupBox("1. 选择基础模型和推理设备")
        group_layout = QVBoxLayout(group)
        self.model_group = QButtonGroup(self)
        active_model = self.ai_state.get("active_model", "balanced")
        model_records = self.ai_state.get("models", {})

        for profile in iter_ai_model_profiles():
            installed = self._is_model_installed(profile.key)
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
            button.toggled.connect(self._refresh_selection_details)
            self.model_group.addButton(button)
            self.model_buttons[profile.key] = button
            group_layout.addWidget(button)
            if profile.key == active_model:
                button.setChecked(True)

        provider_row = QHBoxLayout()
        provider_row.addWidget(QLabel("推理设备："))
        self.provider_combo = QComboBox()
        self.provider_combo.addItem("自动（NVIDIA GPU 优先）", "auto")
        self.provider_combo.addItem("NVIDIA GPU 优先（失败回退 CPU）", "cuda")
        self.provider_combo.addItem("仅 CPU", "cpu")
        current_provider = get_app_config().ai_execution_provider
        current_index = self.provider_combo.findData(current_provider)
        self.provider_combo.setCurrentIndex(max(0, current_index))
        self.provider_combo.currentIndexChanged.connect(
            self._refresh_selection_details
        )
        provider_row.addWidget(self.provider_combo, 1)
        group_layout.addLayout(provider_row)

        if not any(button.isChecked() for button in self.model_buttons.values()):
            for button in self.model_buttons.values():
                button.setChecked(True)
                break
        layout.addWidget(group)

    def _build_resource_downloads(self, layout: QVBoxLayout) -> None:
        group = QGroupBox("2. 下载所需资源（保存在软件配置目录）")
        group_layout = QVBoxLayout(group)

        runtime_title = QHBoxLayout()
        runtime_title.addWidget(QLabel("推理运行时"), 1)
        self.runtime_download_button = QPushButton("下载")
        style_button(self.runtime_download_button, "secondary", "compact")
        self.runtime_download_button.clicked.connect(self._download_runtime)
        runtime_title.addWidget(self.runtime_download_button)
        group_layout.addLayout(runtime_title)
        self.runtime_status_label = QLabel()
        self.runtime_status_label.setWordWrap(True)
        group_layout.addWidget(self.runtime_status_label)
        self.runtime_progress = QProgressBar()
        self.runtime_progress.setRange(0, 100)
        self.runtime_progress.setValue(0)
        self.runtime_progress.setFormat("等待下载")
        group_layout.addWidget(self.runtime_progress)

        model_title = QHBoxLayout()
        model_title.addWidget(QLabel("基础模型"), 1)
        self.model_download_button = QPushButton("下载")
        style_button(self.model_download_button, "secondary", "compact")
        self.model_download_button.clicked.connect(self._download_model)
        model_title.addWidget(self.model_download_button)
        group_layout.addLayout(model_title)
        self.model_status_label = QLabel()
        self.model_status_label.setWordWrap(True)
        group_layout.addWidget(self.model_status_label)
        self.model_progress = QProgressBar()
        self.model_progress.setRange(0, 100)
        self.model_progress.setValue(0)
        self.model_progress.setFormat("等待下载")
        group_layout.addWidget(self.model_progress)

        hint = QLabel(
            "仅在首次使用或切换资源版本时下载。下载支持断点续传、"
            "大小校验和 SHA-256 校验；项目学习结果不会上传。"
        )
        hint.setWordWrap(True)
        group_layout.addWidget(hint)
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
        self.source_group_box = QGroupBox("3. 选择样本来源")
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
        group = QGroupBox("4. 选择学习范围")
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

    def _is_model_installed(self, model_key: str) -> bool:
        profile = get_ai_model_profile(model_key)
        manifest_path = get_ai_model_dir(profile.model_dir_name) / "manifest.json"
        if not manifest_path.is_file():
            return False
        # Existing manually exported packs remain valid; downloaded packs add
        # stronger checksum metadata through the resource manager.
        return is_resource_installed(get_model_resource(model_key))

    def _selected_runtime_resource(self):
        key = self.selected_model_key
        if not key:
            return None
        profile = get_ai_model_profile(key)
        runtime_kind = required_runtime_kind(
            profile, self.selected_execution_provider
        )
        return get_runtime_resource(runtime_kind) if runtime_kind else None

    def _required_resources(self):
        resources = []
        runtime = self._selected_runtime_resource()
        if runtime is not None and not is_resource_installed(runtime):
            resources.append(runtime)
        key = self.selected_model_key
        if key and not self._is_model_installed(key):
            resources.append(get_model_resource(key))
        return resources

    def _refresh_model_button_labels(self) -> None:
        records = self.ai_state.get("models", {})
        for profile in iter_ai_model_profiles():
            initialized = bool(
                isinstance(records.get(profile.key), dict)
                and records[profile.key].get("initialized")
                and (self.project_dir / profile.project_model_file).is_file()
            )
            flags = []
            if initialized:
                flags.append("本项目已初始化")
            if not self._is_model_installed(profile.key):
                flags.append("需下载")
            suffix = f"（{' · '.join(flags)}）" if flags else ""
            self.model_buttons[profile.key].setText(
                f"{profile.display_name}{suffix}\n"
                f"{profile.description}\n{profile.cpu_note}"
            )

    def _refresh_resource_panels(self) -> None:
        if not hasattr(self, "runtime_progress"):
            return
        self._refresh_model_button_labels()

        runtime_worker = self._download_workers.get("runtime")
        if runtime_worker is None:
            runtime = self._selected_runtime_resource()
            if runtime is None:
                self.runtime_status_label.setStyleSheet("")
                self.runtime_status_label.setText(
                    "当前组合使用程序已有的 OpenCV CPU 后端，无需额外下载。"
                )
                self.runtime_progress.setValue(100)
                self.runtime_progress.setFormat("无需下载")
                self.runtime_download_button.setText("无需下载")
                self.runtime_download_button.setEnabled(False)
            elif is_resource_installed(runtime):
                self.runtime_status_label.setStyleSheet("")
                self.runtime_status_label.setText(
                    f"已安装：{runtime.display_name} {runtime.version}"
                )
                self.runtime_progress.setValue(100)
                self.runtime_progress.setFormat("已安装")
                self.runtime_download_button.setText("已安装")
                self.runtime_download_button.setEnabled(False)
            else:
                runtime_error_record = self._download_errors.get("runtime")
                runtime_error = (
                    runtime_error_record[1]
                    if runtime_error_record
                    and runtime_error_record[0] == runtime.key
                    else ""
                )
                self.runtime_status_label.setText(
                    f"下载失败：{runtime_error}。可点击按钮重试。"
                    if runtime_error
                    else (
                        f"未安装：{runtime.display_name} · "
                        f"需要下载 {format_resource_size(runtime.size_bytes)}"
                    )
                )
                self.runtime_status_label.setStyleSheet(
                    f"color: {default_theme.colors.ERROR};"
                    if runtime_error
                    else ""
                )
                self.runtime_progress.setValue(0)
                self.runtime_progress.setFormat("等待下载")
                self.runtime_download_button.setText("下载运行时")
                self.runtime_download_button.setEnabled(True)

        model_worker = self._download_workers.get("model")
        if model_worker is None and self.selected_model_key:
            model = get_model_resource(self.selected_model_key)
            if self._is_model_installed(self.selected_model_key):
                self.model_status_label.setStyleSheet("")
                self.model_status_label.setText(
                    f"已安装：{model.display_name}"
                )
                self.model_progress.setValue(100)
                self.model_progress.setFormat("已安装")
                self.model_download_button.setText("已安装")
                self.model_download_button.setEnabled(False)
            else:
                model_error_record = self._download_errors.get("model")
                model_error = (
                    model_error_record[1]
                    if model_error_record and model_error_record[0] == model.key
                    else ""
                )
                self.model_status_label.setText(
                    f"下载失败：{model_error}。可点击按钮重试。"
                    if model_error
                    else (
                        f"未安装：{model.display_name} · "
                        f"需要下载 {format_resource_size(model.size_bytes)}"
                    )
                )
                self.model_status_label.setStyleSheet(
                    f"color: {default_theme.colors.ERROR};"
                    if model_error
                    else ""
                )
                self.model_progress.setValue(0)
                self.model_progress.setFormat("等待下载")
                self.model_download_button.setText("下载模型")
                self.model_download_button.setEnabled(True)

        missing = self._required_resources()
        if missing and not self._download_workers:
            self.confirm_button.setText("下载并初始化 AI")

    def _download_runtime(self) -> None:
        resource = self._selected_runtime_resource()
        if resource is not None:
            self._start_resource_download(resource)

    def _download_model(self) -> None:
        if self.selected_model_key:
            self._start_resource_download(
                get_model_resource(self.selected_model_key)
            )

    def _start_resource_download(self, resource) -> None:
        slot = resource.kind
        worker = self._download_workers.get(slot)
        if worker is not None and worker.isRunning():
            return

        worker = AIResourceDownloadThread(resource, self)
        self._download_errors.pop(slot, None)
        self._download_workers[slot] = worker
        worker.progress_changed.connect(
            lambda done, total, name=slot: self._on_download_progress(
                name, done, total
            )
        )
        worker.status_changed.connect(
            lambda text, name=slot: self._on_download_status(name, text)
        )
        worker.installed.connect(
            lambda _resource, name=slot: self._on_download_installed(name)
        )
        worker.failed.connect(
            lambda error, name=slot: self._on_download_failed(name, error)
        )
        worker.cancelled.connect(
            lambda name=slot: self._on_download_cancelled(name)
        )
        worker.finished.connect(
            lambda name=slot, current=worker: self._on_download_finished(
                name, current
            )
        )
        self._set_selection_enabled(False)
        self.confirm_button.setEnabled(False)
        if slot == "runtime":
            self.runtime_download_button.setEnabled(False)
            self.runtime_download_button.setText("下载中…")
        else:
            self.model_download_button.setEnabled(False)
            self.model_download_button.setText("下载中…")
        worker.start()

    def _set_selection_enabled(self, enabled: bool) -> None:
        self.provider_combo.setEnabled(enabled)
        for button in self.model_buttons.values():
            button.setEnabled(enabled)

    def _on_download_progress(self, slot: str, done: int, total: int) -> None:
        bar = self.runtime_progress if slot == "runtime" else self.model_progress
        if total > 0:
            percent = min(100, int(done * 100 / total))
            bar.setRange(0, 100)
            bar.setValue(percent)
            bar.setFormat(
                f"{percent}% · {format_resource_size(done)} / "
                f"{format_resource_size(total)}"
            )
        else:
            bar.setRange(0, 0)
            bar.setFormat("正在获取大小…")

    def _on_download_status(self, slot: str, text: str) -> None:
        label = (
            self.runtime_status_label if slot == "runtime" else self.model_status_label
        )
        label.setStyleSheet("")
        label.setText(text)

    def _on_download_installed(self, slot: str) -> None:
        self._download_errors.pop(slot, None)
        bar = self.runtime_progress if slot == "runtime" else self.model_progress
        bar.setRange(0, 100)
        bar.setValue(100)
        bar.setFormat("下载并安装完成")

    def _on_download_failed(self, slot: str, error: str) -> None:
        self._pending_accept = False
        worker = self._download_workers.get(slot)
        resource_key = worker.resource.key if worker is not None else slot
        self._download_errors[slot] = (resource_key, error)
        label = (
            self.runtime_status_label if slot == "runtime" else self.model_status_label
        )
        label.setStyleSheet(f"color: {default_theme.colors.ERROR};")
        label.setText(f"下载失败：{error}。可点击按钮重试。")

    def _on_download_cancelled(self, slot: str) -> None:
        label = (
            self.runtime_status_label if slot == "runtime" else self.model_status_label
        )
        label.setText("下载已暂停，下次会从断点继续。")

    def _on_download_finished(
        self, slot: str, worker: AIResourceDownloadThread
    ) -> None:
        if self._download_workers.get(slot) is worker:
            self._download_workers.pop(slot, None)
        if not self._download_workers:
            self._set_selection_enabled(True)
            self.confirm_button.setEnabled(True)
            self._refresh_selection_details()
            if self._close_after_download_cancel:
                super().reject()
                return
            if self._pending_accept and not self._required_resources():
                self._pending_accept = False
                super().accept()

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
        provider = self.selected_execution_provider
        if provider == "cpu" and profile.recommended_gpu:
            self.warning_label.setText(
                "当前选择仅 CPU。精度优先模型推理和首次建库可能明显较慢。"
            )
            self.warning_label.setStyleSheet(
                f"color: {default_theme.colors.WARNING}; font-weight: 600;"
            )
        elif provider == "cpu":
            self.warning_label.setText(profile.cpu_note)
            self.warning_label.setStyleSheet(
                f"color: {default_theme.colors.WARNING}; font-weight: 600;"
            )
        else:
            self.warning_label.setText(
                "将按需下载 NVIDIA GPU 运行时；CUDA 会话加载失败时安全回退 CPU。"
            )
            self.warning_label.setStyleSheet(
                f"color: {default_theme.colors.WARNING}; font-weight: 600;"
            )
        self._refresh_resource_panels()

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

    @property
    def selected_execution_provider(self) -> str:
        combo = getattr(self, "provider_combo", None)
        value = combo.currentData() if combo is not None else "auto"
        return value if value in ("auto", "cuda", "cpu") else "auto"

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
        missing = self._required_resources()
        if missing:
            self._pending_accept = True
            for resource in missing:
                self._start_resource_download(resource)
            return
        super().accept()

    def reject(self) -> None:
        if self._download_workers:
            self._pending_accept = False
            self._close_after_download_cancel = True
            self.confirm_button.setEnabled(False)
            for worker in tuple(self._download_workers.values()):
                worker.requestInterruption()
            return
        super().reject()

    def closeEvent(self, event) -> None:
        if self._download_workers:
            event.ignore()
            self.reject()
            return
        super().closeEvent(event)
