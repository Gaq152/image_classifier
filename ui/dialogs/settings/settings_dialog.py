"""设置对话框模块"""

import logging
import re
from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QMessageBox, QTabWidget,
    QWidget, QCheckBox, QGroupBox, QScrollArea, QComboBox,
    QDoubleSpinBox, QSpinBox
)
from PyQt6.QtCore import Qt, QTimer, QEvent

from utils.app_config import get_app_config
from utils.paths import get_cache_dir
from core.update_utils import normalize_update_proxy
from ...components.toast import toast_info, toast_success, toast_warning, toast_error
from ...components.styles.theme import default_theme
from ...components.styles import ButtonStyles
from ...components.dialog_utils import ThemedMessageBox, configure_dialog, style_button
from ...components.widgets.switch import Switch

class SettingsDialog(QDialog):
    """设置对话框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)
        self.app_config = get_app_config()
        self._centered = False

        # 临时存储配置（用于取消操作）
        self.temp_config = {}

        # 防抖定时器（用于延迟保存配置，避免频繁写入磁盘）
        self.zoom_save_timer = QTimer()
        self.zoom_save_timer.setSingleShot(True)
        self.zoom_save_timer.timeout.connect(self._save_zoom_config)

        self.initUI()

    def initUI(self):
        """初始化UI"""
        self.setWindowTitle("设置")
        self.setMinimumWidth(700)
        self.setMinimumHeight(650)

        # 主布局
        layout = QVBoxLayout(self)
        configure_dialog(self, layout)

        # 创建Tab控件
        self.tab_widget = QTabWidget()

        # 基本设置Tab
        basic_tab = self.create_basic_tab()
        self.tab_widget.addTab(basic_tab, "⚙️ 基本设置")

        # 高级设置Tab
        advanced_tab = self.create_advanced_tab()
        self.tab_widget.addTab(advanced_tab, "🔧 高级设置")

        layout.addWidget(self.tab_widget)

        # 底部按钮
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        reset_btn = QPushButton("恢复默认")
        reset_btn.clicked.connect(self.reset_to_defaults)
        button_layout.addWidget(reset_btn)

        layout.addLayout(button_layout)

        # 应用主题样式
        self._apply_theme()

    def create_appearance_section(self) -> QGroupBox:
        """创建外观设置区域"""

        group = QGroupBox("🎨 外观设置")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)

        # 主题设置
        theme_group = QWidget()
        theme_layout = QVBoxLayout(theme_group)
        theme_layout.setSpacing(8)

        theme_title = QLabel("🌓 主题模式")
        theme_title.setStyleSheet("font-size: 14px; font-weight: bold;")
        theme_layout.addWidget(theme_title)

        # 主题选择下拉列表和自动切换开关（横向布局）
        theme_select_layout = QHBoxLayout()
        theme_select_layout.setSpacing(10)

        self.theme_combo = QComboBox()
        self.theme_combo.addItem("☀️  浅色主题", "light")
        self.theme_combo.addItem("🌙  深色主题", "dark")
        self.theme_combo.addItem("💻  跟随系统", "system")
        self.theme_combo.setMinimumHeight(40)
        # 禁用滚轮切换
        self.theme_combo.wheelEvent = lambda event: None
        self.theme_combo.currentIndexChanged.connect(self.on_theme_combo_changed)
        theme_select_layout.addWidget(self.theme_combo)

        theme_select_layout.addStretch()

        # 自动切换标签和Switch
        auto_label = QLabel("⏰ 自动切换")
        auto_label.setStyleSheet("font-size: 13px;")
        auto_label.setToolTip("8:00-18:00亮色，其他时间暗色")
        theme_select_layout.addWidget(auto_label)

        self.auto_theme_switch = Switch()
        self.auto_theme_switch.toggled.connect(self.on_auto_theme_toggled)
        theme_select_layout.addWidget(self.auto_theme_switch)

        theme_layout.addLayout(theme_select_layout)
        layout.addWidget(theme_group)

        # 根据当前主题模式设置下拉列表状态（阻止信号避免触发theme_mode重置）
        current_theme_mode = self.app_config.theme_mode

        # 阻止信号触发
        self.theme_combo.blockSignals(True)

        if current_theme_mode == "auto":
            # 启用自动切换
            self.auto_theme_switch.blockSignals(True)
            self.auto_theme_switch.setChecked(True)
            self.auto_theme_switch.blockSignals(False)
            # 禁用主题下拉列表
            self.theme_combo.setEnabled(False)
            # 设置为当前实际主题
            if self.app_config.theme == "dark":
                self.theme_combo.setCurrentIndex(1)
            else:
                self.theme_combo.setCurrentIndex(0)
        elif current_theme_mode == "system":
            # 设置为跟随系统
            self.theme_combo.setCurrentIndex(2)
        elif self.app_config.theme == "dark":
            # 设置为暗色
            self.theme_combo.setCurrentIndex(1)
        else:
            # 设置为亮色
            self.theme_combo.setCurrentIndex(0)

        # 恢复信号
        self.theme_combo.blockSignals(False)

        layout.addStretch()
        return group

    def create_tutorial_section(self) -> QGroupBox:
        """创建教程设置区域"""
        c = default_theme.colors
        group = QGroupBox("🎓 教程设置")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(20)

        # 教程状态
        status_group = QWidget()
        status_layout = QVBoxLayout(status_group)
        status_layout.setSpacing(10)

        # 标题
        status_title = QLabel("📚 教程状态")
        status_title.setStyleSheet("font-size: 14px; font-weight: bold;")
        status_layout.addWidget(status_title)

        # 确定当前状态
        if self.app_config.tutorial_completed:
            status_text = "✅ 教程已完成"
            status_color = c.SUCCESS
        elif self.app_config.tutorial_skipped:
            status_text = "⏭️ 教程已跳过"
            status_color = c.WARNING
        else:
            status_text = "⏸️ 教程未开始"
            status_color = c.TEXT_SECONDARY

        # 状态显示和按钮（横向布局）
        control_widget = QWidget()
        control_layout = QHBoxLayout(control_widget)
        control_layout.setContentsMargins(0, 0, 0, 0)
        control_layout.setSpacing(15)

        # 状态标签（左侧）
        self.tutorial_status_label = QLabel(status_text)
        self.tutorial_status_label.setObjectName("tutorialStatusLabel")
        self.tutorial_status_color = status_color

        if default_theme.is_dark:
            bg_color = "rgba(255, 255, 255, 0.08)"
        else:
            bg_color = "rgba(0, 0, 0, 0.05)"

        self.tutorial_status_label.setStyleSheet(f"""
            QLabel#tutorialStatusLabel {{
                color: {status_color} !important;
                font-size: 13px;
                font-weight: normal;
                padding: 8px 12px;
                background-color: {bg_color};
                border-radius: 4px;
            }}
        """)
        control_layout.addWidget(self.tutorial_status_label)

        control_layout.addStretch()

        # 重新开始教程按钮（右侧）
        start_tutorial_btn = QPushButton("重新开始教程")
        start_tutorial_btn.clicked.connect(self.start_tutorial)
        start_tutorial_btn.setMinimumHeight(36)
        start_tutorial_btn.setMinimumWidth(120)
        control_layout.addWidget(start_tutorial_btn)

        status_layout.addWidget(control_widget)

        layout.addWidget(status_group)

        layout.addStretch()
        return group

    def create_basic_tab(self) -> QWidget:
        """创建基本设置Tab"""
        tab = QWidget()

        # 创建可滚动区域
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)

        # 滚动内容容器
        scroll_content = QWidget()
        scroll_content.setObjectName("scrollContent")
        content_layout = QVBoxLayout(scroll_content)
        content_layout.setSpacing(20)
        content_layout.setContentsMargins(0, 0, 10, 0)

        # 添加各个设置组
        content_layout.addWidget(self.create_appearance_section())
        content_layout.addWidget(self.create_window_section())
        content_layout.addWidget(self.create_preview_section())
        content_layout.addWidget(self.create_tutorial_section())
        content_layout.addStretch()

        scroll_area.setWidget(scroll_content)

        # Tab布局
        tab_layout = QVBoxLayout(tab)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.addWidget(scroll_area)

        return tab

    def create_advanced_tab(self) -> QWidget:
        """创建高级设置Tab"""
        tab = QWidget()

        # 创建可滚动区域
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)

        # 滚动内容容器
        scroll_content = QWidget()
        scroll_content.setObjectName("scrollContent")
        content_layout = QVBoxLayout(scroll_content)
        content_layout.setSpacing(20)
        content_layout.setContentsMargins(0, 0, 10, 0)

        # 添加各个设置组
        content_layout.addWidget(self.create_log_toast_section())
        content_layout.addWidget(self.create_advanced_update_section())
        content_layout.addWidget(self.create_directory_section())
        content_layout.addWidget(self.create_smb_section())
        content_layout.addStretch()

        scroll_area.setWidget(scroll_content)

        # Tab布局
        tab_layout = QVBoxLayout(tab)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.addWidget(scroll_area)

        return tab

    def create_log_toast_section(self) -> QGroupBox:
        """创建日志和Toast级别设置区域"""
        group = QGroupBox("📝 日志与提示")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(20)

        # 日志级别设置
        log_group = QWidget()
        log_layout = QVBoxLayout(log_group)
        log_layout.setSpacing(10)

        # 标题和下拉框（横向布局）
        log_header = QWidget()
        log_header_layout = QHBoxLayout(log_header)
        log_header_layout.setContentsMargins(0, 0, 0, 0)
        log_header_layout.setSpacing(10)

        log_title = QLabel("📋 日志保存级别")
        log_title.setStyleSheet("font-size: 14px; font-weight: bold;")
        log_header_layout.addWidget(log_title)

        log_header_layout.addStretch()

        self.log_level_combo = QComboBox()
        self.log_level_combo.addItem("🐛 DEBUG - 调试信息", "DEBUG")
        self.log_level_combo.addItem("ℹ️  INFO - 一般信息", "INFO")
        self.log_level_combo.addItem("⚠️  WARNING - 警告信息", "WARNING")
        self.log_level_combo.addItem("❌ ERROR - 错误信息", "ERROR")
        self.log_level_combo.addItem("🔥 CRITICAL - 严重错误", "CRITICAL")
        self.log_level_combo.setMinimumHeight(36)
        self.log_level_combo.setMinimumWidth(220)
        # 禁用滚轮切换
        self.log_level_combo.wheelEvent = lambda event: None
        # 设置当前级别
        current_log_level = self.app_config.log_level
        for i in range(self.log_level_combo.count()):
            if self.log_level_combo.itemData(i) == current_log_level:
                self.log_level_combo.setCurrentIndex(i)
                break
        self.log_level_combo.currentIndexChanged.connect(self.on_log_level_changed)
        log_header_layout.addWidget(self.log_level_combo)

        log_layout.addWidget(log_header)
        layout.addWidget(log_group)

        # Toast级别设置
        toast_group = QWidget()
        toast_layout = QVBoxLayout(toast_group)
        toast_layout.setSpacing(10)

        # 标题和下拉框（横向布局）
        toast_header = QWidget()
        toast_header_layout = QHBoxLayout(toast_header)
        toast_header_layout.setContentsMargins(0, 0, 0, 0)
        toast_header_layout.setSpacing(10)

        toast_title = QLabel("💬 Toast提示级别")
        toast_title.setStyleSheet("font-size: 14px; font-weight: bold;")
        toast_header_layout.addWidget(toast_title)

        toast_header_layout.addStretch()

        self.toast_level_combo = QComboBox()
        self.toast_level_combo.addItem("🐛 DEBUG - 所有提示", "DEBUG")
        self.toast_level_combo.addItem("ℹ️  INFO - 一般及以上", "INFO")
        self.toast_level_combo.addItem("⚠️  WARNING - 警告及错误", "WARNING")
        self.toast_level_combo.addItem("❌ ERROR - 仅错误提示", "ERROR")
        self.toast_level_combo.setMinimumHeight(36)
        self.toast_level_combo.setMinimumWidth(220)
        # 禁用滚轮切换
        self.toast_level_combo.wheelEvent = lambda event: None
        # 设置当前级别
        current_toast_level = self.app_config.toast_level
        for i in range(self.toast_level_combo.count()):
            if self.toast_level_combo.itemData(i) == current_toast_level:
                self.toast_level_combo.setCurrentIndex(i)
                break
        self.toast_level_combo.currentIndexChanged.connect(self.on_toast_level_changed)
        toast_header_layout.addWidget(self.toast_level_combo)

        toast_layout.addWidget(toast_header)
        layout.addWidget(toast_group)

        return group

    def create_advanced_update_section(self) -> QGroupBox:
        """创建更新代理设置区域。"""
        group = QGroupBox("🚀 更新代理")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        description = QLabel(
            "留空时直接连接 GitHub。支持本地 Clash HTTP 代理，"
            "也支持 ghfast.top 这类 GitHub 加速地址。"
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        input_row = QHBoxLayout()
        input_row.setSpacing(10)
        self.update_proxy_input = QLineEdit()
        self.update_proxy_input.setText(self.app_config.update_proxy)
        self.update_proxy_input.setPlaceholderText(
            "http://127.0.0.1:7890 或 https://ghfast.top"
        )
        self.update_proxy_input.setMinimumHeight(36)
        self.update_proxy_input.returnPressed.connect(self.save_update_proxy)
        input_row.addWidget(self.update_proxy_input, 1)

        save_button = QPushButton("保存")
        save_button.setMinimumHeight(36)
        save_button.clicked.connect(self.save_update_proxy)
        input_row.addWidget(save_button)
        layout.addLayout(input_row)

        hint = QLabel("该配置会同时用于检查更新和更新包下载。")
        hint.setObjectName("secondaryText")
        layout.addWidget(hint)
        return group

    def create_directory_section(self) -> QGroupBox:
        """创建工作目录设置区域"""
        group = QGroupBox("📁 工作目录")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(20)

        # 工作目录历史
        dir_group = QWidget()
        dir_layout = QVBoxLayout(dir_group)
        dir_layout.setSpacing(10)

        # 标题和按钮（横向布局）
        dir_header = QWidget()
        dir_header_layout = QHBoxLayout(dir_header)
        dir_header_layout.setContentsMargins(0, 0, 0, 0)
        dir_header_layout.setSpacing(10)

        dir_title = QLabel("📁 最后打开的目录")
        dir_title.setStyleSheet("font-size: 14px; font-weight: bold;")
        dir_header_layout.addWidget(dir_title)

        dir_header_layout.addStretch()

        clear_dir_btn = QPushButton("清除历史记录")
        clear_dir_btn.clicked.connect(self.clear_directory_history)
        clear_dir_btn.setMinimumHeight(28)
        clear_dir_btn.setToolTip("清除最后打开的工作目录路径")
        dir_header_layout.addWidget(clear_dir_btn)

        dir_layout.addWidget(dir_header)

        # 路径显示
        last_dir = self.app_config.last_opened_directory
        is_network = self.app_config.last_opened_drive_is_network

        # 构建带网络路径标记的显示文本
        if last_dir:
            path_type_icon = "🌐" if is_network else "💾"
            path_type_text = "网络路径" if is_network else "本地路径"
            drive = Path(last_dir).drive if last_dir else ""
            display_text = f"{path_type_icon} {last_dir}\n({drive} - {path_type_text})"
        else:
            display_text = "（无）"

        self.last_dir_label = QLabel(display_text)
        self.last_dir_label.setObjectName("lastDirLabel")
        self.last_dir_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        c = default_theme.colors
        self.last_dir_label.setStyleSheet(f"""
            color: {c.TEXT_PRIMARY};
            padding: 10px;
            background-color: {c.BACKGROUND_SECONDARY};
            border-radius: 4px;
            font-size: 12px;
            font-family: monospace;
        """)
        self.last_dir_label.setWordWrap(True)
        dir_layout.addWidget(self.last_dir_label)

        layout.addWidget(dir_group)
        layout.addStretch()
        return group

    def create_smb_section(self) -> QGroupBox:
        """创建SMB缓存设置区域"""

        group = QGroupBox("🌐 网络缓存")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(20)

        # SMB缓存管理
        smb_group = QWidget()
        smb_layout = QVBoxLayout(smb_group)
        smb_layout.setSpacing(10)

        # 标题和按钮（横向布局）
        smb_header = QWidget()
        smb_header_layout = QHBoxLayout(smb_header)
        smb_header_layout.setContentsMargins(0, 0, 0, 0)
        smb_header_layout.setSpacing(10)

        smb_title = QLabel("🌐 SMB/NAS 缓存")
        smb_title.setStyleSheet("font-size: 14px; font-weight: bold;")
        smb_header_layout.addWidget(smb_title)

        smb_header_layout.addStretch()

        clear_smb_btn = QPushButton("清除SMB缓存")
        clear_smb_btn.clicked.connect(self.clear_smb_cache)
        clear_smb_btn.setMinimumHeight(28)
        clear_smb_btn.setToolTip("清除SMB/NAS网络路径的图片缓存（如果遇到缓存问题可尝试清除）")
        smb_header_layout.addWidget(clear_smb_btn)

        smb_layout.addWidget(smb_header)

        # 缓存路径显示
        cache_dir = get_cache_dir()
        self.cache_path_label = QLabel(str(cache_dir))
        self.cache_path_label.setObjectName("cacheDirLabel")
        self.cache_path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        c = default_theme.colors
        self.cache_path_label.setStyleSheet(f"""
            color: {c.TEXT_PRIMARY};
            padding: 10px;
            background-color: {c.BACKGROUND_SECONDARY};
            border-radius: 4px;
            font-size: 12px;
            font-family: monospace;
        """)
        self.cache_path_label.setWordWrap(True)
        smb_layout.addWidget(self.cache_path_label)

        # 缓存大小显示
        self.cache_size_label = QLabel()
        self.cache_size_label.setObjectName("cacheSizeLabel")
        self.cache_size_label.setStyleSheet(f"""
            color: {c.TEXT_SECONDARY};
            padding: 8px 10px;
            background-color: {c.BACKGROUND_SECONDARY};
            border-radius: 4px;
            font-size: 12px;
        """)
        smb_layout.addWidget(self.cache_size_label)

        # 初始化缓存大小显示
        self._update_cache_size_display()

        layout.addWidget(smb_group)

        # 缓存预热设置（优化8）
        warmup_group = QWidget()
        warmup_layout = QVBoxLayout(warmup_group)
        warmup_layout.setSpacing(10)

        # 标题和开关（横向布局）
        warmup_header = QWidget()
        warmup_header_layout = QHBoxLayout(warmup_header)
        warmup_header_layout.setContentsMargins(0, 0, 0, 0)
        warmup_header_layout.setSpacing(10)

        warmup_title = QLabel("🔥 缓存预热")
        warmup_title.setStyleSheet("font-size: 14px; font-weight: bold;")
        warmup_header_layout.addWidget(warmup_title)

        warmup_header_layout.addStretch()

        # 预热开关
        warmup_switch_label = QLabel("启用预热")
        warmup_switch_label.setStyleSheet("font-size: 13px;")
        warmup_header_layout.addWidget(warmup_switch_label)

        self.warmup_enabled_switch = Switch()
        self.warmup_enabled_switch.setChecked(self.app_config.cache_warmup_enabled)
        self.warmup_enabled_switch.toggled.connect(self.on_warmup_enabled_changed)
        warmup_header_layout.addWidget(self.warmup_enabled_switch)

        warmup_layout.addWidget(warmup_header)

        # 预热图片数量设置（横向布局）
        warmup_count_widget = QWidget()
        warmup_count_layout = QHBoxLayout(warmup_count_widget)
        warmup_count_layout.setContentsMargins(0, 0, 0, 0)
        warmup_count_layout.setSpacing(10)

        warmup_count_label = QLabel("预热图片数量：")
        warmup_count_label.setStyleSheet("font-size: 13px;")
        warmup_count_layout.addWidget(warmup_count_label)

        # 自定义SpinBox布局：输入框 + 上下按钮 + 单位
        spinbox_container = QWidget()
        spinbox_container_layout = QHBoxLayout(spinbox_container)
        spinbox_container_layout.setContentsMargins(0, 0, 0, 0)
        spinbox_container_layout.setSpacing(0)

        # SpinBox（使用统一样式）
        self.warmup_count_spinbox = QSpinBox()
        self.warmup_count_spinbox.setRange(10, 500)
        self.warmup_count_spinbox.setSingleStep(10)
        self.warmup_count_spinbox.setValue(self.app_config.cache_warmup_count)
        self.warmup_count_spinbox.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self.warmup_count_spinbox.setFixedSize(60, 24)
        self.warmup_count_spinbox.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # 使用统一样式方法
        self._apply_spinbox_style(self.warmup_count_spinbox)
        # 禁用滚轮
        self.warmup_count_spinbox.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.warmup_count_spinbox.installEventFilter(self)
        spinbox_container_layout.addWidget(self.warmup_count_spinbox)

        # 使用统一的按钮创建方法
        warmup_buttons = self._create_spinbox_buttons(self.warmup_count_spinbox, button_height=16)
        spinbox_container_layout.addWidget(warmup_buttons)

        # 单位标签（放在外面）
        unit_label = QLabel("张")
        unit_label.setStyleSheet(f"font-size: 13px; color: {c.TEXT_PRIMARY}; margin-left: 5px;")
        spinbox_container_layout.addWidget(unit_label)

        warmup_count_layout.addWidget(spinbox_container)

        # 防抖定时器：延迟500ms后保存
        self._warmup_count_debounce_timer = QTimer(self)
        self._warmup_count_debounce_timer.setSingleShot(True)
        self._warmup_count_debounce_timer.timeout.connect(self._save_warmup_count)
        self._pending_warmup_count = self.app_config.cache_warmup_count
        self.warmup_count_spinbox.valueChanged.connect(self._on_warmup_count_changed_debounced)

        warmup_count_layout.addStretch()

        warmup_layout.addWidget(warmup_count_widget)

        # 预热说明
        warmup_desc = QLabel("💡 预热功能会在打开网络目录时，主动预加载前N张图片到缓存，加快首次浏览速度。")
        warmup_desc.setWordWrap(True)
        warmup_desc.setStyleSheet(f"color: {c.TEXT_SECONDARY}; font-size: 12px; padding: 5px 0;")
        warmup_layout.addWidget(warmup_desc)

        layout.addWidget(warmup_group)

        # 循环翻页设置
        loop_group = QWidget()
        loop_layout = QVBoxLayout(loop_group)
        loop_layout.setSpacing(10)

        # 标题
        loop_title = QLabel("🔄 循环翻页")
        loop_title.setStyleSheet("font-size: 14px; font-weight: bold;")
        loop_layout.addWidget(loop_title)

        # 本地路径循环开关
        local_loop_widget = QWidget()
        local_loop_layout = QHBoxLayout(local_loop_widget)
        local_loop_layout.setContentsMargins(0, 0, 0, 0)
        local_loop_layout.setSpacing(10)

        local_loop_label = QLabel("本地路径循环：")
        local_loop_label.setStyleSheet("font-size: 13px;")
        local_loop_layout.addWidget(local_loop_label)

        self.local_loop_switch = Switch()
        self.local_loop_switch.setChecked(self.app_config.local_loop_enabled)
        self.local_loop_switch.toggled.connect(self.on_local_loop_changed)
        local_loop_layout.addWidget(self.local_loop_switch)

        local_loop_layout.addStretch()
        loop_layout.addWidget(local_loop_widget)

        # 本地循环说明
        local_loop_desc = QLabel("💡 本地文件读取速度快，建议开启循环翻页")
        local_loop_desc.setWordWrap(True)
        local_loop_desc.setStyleSheet(f"color: {c.TEXT_SECONDARY}; font-size: 12px; padding: 5px 0;")
        loop_layout.addWidget(local_loop_desc)

        # 网络路径循环开关
        network_loop_widget = QWidget()
        network_loop_layout = QHBoxLayout(network_loop_widget)
        network_loop_layout.setContentsMargins(0, 0, 0, 0)
        network_loop_layout.setSpacing(10)

        network_loop_label = QLabel("网络路径循环：")
        network_loop_label.setStyleSheet("font-size: 13px;")
        network_loop_layout.addWidget(network_loop_label)

        self.network_loop_switch = Switch()
        self.network_loop_switch.setChecked(self.app_config.network_loop_enabled)
        self.network_loop_switch.toggled.connect(self.on_network_loop_changed)
        network_loop_layout.addWidget(self.network_loop_switch)

        network_loop_layout.addStretch()
        loop_layout.addWidget(network_loop_widget)

        # 网络循环说明
        network_loop_desc = QLabel("⚠️ 开启后将额外预热末尾图片（约增加预热时间50%），建议按需开启")
        network_loop_desc.setWordWrap(True)
        network_loop_desc.setStyleSheet(f"color: {c.TEXT_SECONDARY}; font-size: 12px; padding: 5px 0;")
        loop_layout.addWidget(network_loop_desc)

        layout.addWidget(loop_group)

        # 配置文件信息
        info_group = QWidget()
        info_layout = QVBoxLayout(info_group)
        info_layout.setSpacing(10)

        info_title = QLabel("ℹ️ 配置信息")
        info_title.setStyleSheet("font-size: 14px; font-weight: bold;")
        info_layout.addWidget(info_title)

        version_label = QLabel(f"配置文件版本：{self.app_config._config.get('version', '未知')}")
        info_layout.addWidget(version_label)

        self.config_path_label = QLabel(f"配置文件路径：{self.app_config._config_file}")
        self.config_path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.config_path_label.setWordWrap(True)
        info_layout.addWidget(self.config_path_label)

        layout.addWidget(info_group)

        layout.addStretch()
        return group

    def create_window_section(self) -> QGroupBox:
        """创建窗口行为设置区域"""
        c = default_theme.colors

        group = QGroupBox("🖥️ 窗口")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)

        # 记住窗口位置开关
        geo_widget = QWidget()
        geo_layout = QHBoxLayout(geo_widget)
        geo_layout.setContentsMargins(0, 0, 0, 0)
        geo_layout.setSpacing(10)

        geo_label = QLabel("📐 记住窗口位置和大小")
        geo_label.setStyleSheet("font-size: 13px; font-weight: bold;")
        geo_layout.addWidget(geo_label)

        geo_layout.addStretch()

        switch_label = QLabel("启用")
        switch_label.setStyleSheet("font-size: 13px;")
        geo_layout.addWidget(switch_label)

        self.remember_geometry_switch = Switch()
        self.remember_geometry_switch.setChecked(self.app_config.remember_window_geometry)
        self.remember_geometry_switch.toggled.connect(self._on_remember_geometry_changed)
        geo_layout.addWidget(self.remember_geometry_switch)

        layout.addWidget(geo_widget)

        # 说明
        desc = QLabel("💡 关闭程序时保存窗口位置和大小，下次启动原位还原。多显示器场景下，若原位置对应的显示器不存在会自动回退到主屏幕居中。")
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {c.TEXT_SECONDARY}; font-size: 12px; padding: 0 0 5px 0;")
        layout.addWidget(desc)

        return group

    def _on_remember_geometry_changed(self, checked: bool):
        """窗口记忆开关改变"""
        self.app_config.remember_window_geometry = checked
        if not checked:
            # 关闭时清除已保存的几何信息
            self.app_config.window_geometry = None
        toast_success(self, f"记住窗口位置已{'启用' if checked else '禁用'}")

    def create_preview_section(self) -> QGroupBox:
        """创建图像预览设置区域"""
        c = default_theme.colors  # 主题颜色变量

        group = QGroupBox("🖼️ 图像预览设置")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)

        # 标题行：左边是缩放范围标题，右边是全局应用开关
        header_layout = QHBoxLayout()

        zoom_title = QLabel("🔍 缩放范围")
        zoom_title.setStyleSheet("font-size: 14px; font-weight: bold;")
        header_layout.addWidget(zoom_title)

        header_layout.addStretch()

        # 全局应用缩放开关（横向布局）
        apply_label = QLabel("全局应用缩放倍数")
        header_layout.addWidget(apply_label)

        self.remember_zoom_checkbox = Switch()
        self.remember_zoom_checkbox.setChecked(self.app_config.global_zoom_enabled)
        self.remember_zoom_checkbox.setToolTip("启用后，当前的缩放倍数会应用到所有图片。关闭后，每次翻页都会恢复默认适应窗口模式")
        self.remember_zoom_checkbox.toggled.connect(self.on_remember_zoom_changed)
        header_layout.addWidget(self.remember_zoom_checkbox)

        layout.addLayout(header_layout)

        # 最大和最小缩放倍数横向并排
        zoom_controls_layout = QHBoxLayout()
        zoom_controls_layout.setSpacing(15)

        # 最大缩放倍数
        zoom_max_label = QLabel("最大缩放倍数：")
        zoom_controls_layout.addWidget(zoom_max_label)

        # 创建包含spinbox和外部按钮的容器（无间距，组合式组件）
        zoom_max_container = QHBoxLayout()
        zoom_max_container.setSpacing(0)
        zoom_max_container.setContentsMargins(0, 0, 0, 0)

        self.zoom_max_spinbox = QDoubleSpinBox()
        self.zoom_max_spinbox.setDecimals(1)
        self.zoom_max_spinbox.setRange(1.0, 20.0)
        self.zoom_max_spinbox.setSingleStep(0.5)
        self.zoom_max_spinbox.setValue(self.app_config.image_zoom_max)
        self.zoom_max_spinbox.setMinimumHeight(32)
        self.zoom_max_spinbox.setMinimumWidth(80)  # 增加宽度以完整显示数字
        self.zoom_max_spinbox.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)  # 隐藏内置按钮
        self.zoom_max_spinbox.setToolTip("设置图片缩放的最大倍数（范围：1.0-20.0）")
        # 禁用滚轮调整
        self.zoom_max_spinbox.wheelEvent = lambda event: None
        self.zoom_max_spinbox.valueChanged.connect(self.on_zoom_max_changed)
        # 美化样式
        self._apply_spinbox_style(self.zoom_max_spinbox)
        zoom_max_container.addWidget(self.zoom_max_spinbox)

        # 外部上下按钮（垂直排列）
        zoom_max_buttons = self._create_spinbox_buttons(self.zoom_max_spinbox, button_height=16)
        zoom_max_container.addWidget(zoom_max_buttons)

        zoom_controls_layout.addLayout(zoom_max_container)

        # "倍" 标签
        zoom_max_unit = QLabel("倍")
        zoom_max_unit.setStyleSheet(f"color: {c.TEXT_SECONDARY}; font-size: 13px; margin-left: 5px;")
        zoom_controls_layout.addWidget(zoom_max_unit)

        # 最小缩放倍数
        zoom_min_label = QLabel("最小缩放倍数：")
        zoom_controls_layout.addWidget(zoom_min_label)

        # 创建包含spinbox和外部按钮的容器（无间距，组合式组件）
        zoom_min_container = QHBoxLayout()
        zoom_min_container.setSpacing(0)
        zoom_min_container.setContentsMargins(0, 0, 0, 0)

        self.zoom_min_spinbox = QDoubleSpinBox()
        self.zoom_min_spinbox.setDecimals(2)
        self.zoom_min_spinbox.setRange(0.01, 1.0)
        self.zoom_min_spinbox.setSingleStep(0.01)
        self.zoom_min_spinbox.setValue(self.app_config.image_zoom_min)
        self.zoom_min_spinbox.setMinimumHeight(32)
        self.zoom_min_spinbox.setMinimumWidth(80)  # 增加宽度以完整显示数字
        self.zoom_min_spinbox.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)  # 隐藏内置按钮
        self.zoom_min_spinbox.setToolTip("设置图片缩放的最小倍数（范围：0.01-1.0）")
        # 禁用滚轮调整
        self.zoom_min_spinbox.wheelEvent = lambda event: None
        self.zoom_min_spinbox.valueChanged.connect(self.on_zoom_min_changed)
        # 美化样式
        self._apply_spinbox_style(self.zoom_min_spinbox)
        zoom_min_container.addWidget(self.zoom_min_spinbox)

        # 外部上下按钮（垂直排列）
        zoom_min_buttons = self._create_spinbox_buttons(self.zoom_min_spinbox, button_height=16)
        zoom_min_container.addWidget(zoom_min_buttons)

        zoom_controls_layout.addLayout(zoom_min_container)

        # "倍" 标签
        zoom_min_unit = QLabel("倍")
        zoom_min_unit.setStyleSheet(f"color: {c.TEXT_SECONDARY}; font-size: 13px; margin-left: 5px;")
        zoom_controls_layout.addWidget(zoom_min_unit)

        zoom_controls_layout.addStretch()
        layout.addLayout(zoom_controls_layout)

        layout.addStretch()
        return group

    def on_theme_combo_changed(self, index: int):
        """主题下拉列表变化处理"""
        if not hasattr(self, 'auto_theme_switch'):
            return

        # 如果自动切换已启用，下拉列表应该是禁用的，不应触发此事件
        # 但为了安全起见，还是检查一下
        if self.auto_theme_switch.isChecked():
            return

        # 获取选中的主题模式
        mode = self.theme_combo.currentData()
        if mode:
            self.select_theme(mode)

    def on_theme_button_clicked(self, mode: str):
        """主题按钮点击处理（已废弃，保留以兼容旧代码）"""
        if not hasattr(self, 'auto_theme_switch'):
            return

        # 如果自动切换已启用，显示提示
        if self.auto_theme_switch.isChecked():
            toast_warning(self, "请先关闭自动切换")
            return

        # 否则正常切换主题
        self.select_theme(mode)

    def on_auto_theme_toggled(self, checked: bool):
        """自动切换复选框状态变化"""
        if checked:
            # 启用自动模式
            actual_theme = self.app_config.get_auto_theme_by_time()
            # 先设置主题，再设置模式（这样模式设置时可以正确读取新主题）
            self.app_config.theme = actual_theme
            self.app_config.theme_mode = "auto"
            default_theme.set_theme(actual_theme)

            # 禁用主题下拉列表
            self.theme_combo.setEnabled(False)

            # 更新下拉列表显示当前主题（阻止信号触发）
            self.theme_combo.blockSignals(True)
            if actual_theme == "dark":
                self.theme_combo.setCurrentIndex(1)  # 深色主题
            else:
                self.theme_combo.setCurrentIndex(0)  # 浅色主题
            self.theme_combo.blockSignals(False)

            # 应用主题
            self._apply_theme()
            if self.parent():
                if hasattr(self.parent(), 'apply_theme'):
                    self.parent().apply_theme()
                if hasattr(self.parent(), 'theme_button'):
                    theme_icon = '☾' if actual_theme == "light" else '☼'
                    self.parent().theme_button.setText(theme_icon)
                    # 禁用主窗口的主题按钮
                    self.parent().theme_button.setEnabled(False)
                    self.parent().theme_button.setToolTip("已启用自动切换，点击查看提示")
                # 启动主窗口的自动主题定时器
                if hasattr(self.parent(), 'start_auto_theme_timer'):
                    self.parent().start_auto_theme_timer()

            toast_success(self, f"已启用自动切换（当前: {'亮色' if actual_theme == 'light' else '暗色'}主题）")
        else:
            # 禁用自动模式，恢复手动模式
            self.app_config.theme_mode = "manual"

            # 启用主题下拉列表
            self.theme_combo.setEnabled(True)

            # 根据当前主题设置下拉列表（阻止信号触发）
            current_theme = self.app_config.theme
            self.theme_combo.blockSignals(True)
            if current_theme == "dark":
                self.theme_combo.setCurrentIndex(1)  # 深色主题
            else:
                self.theme_combo.setCurrentIndex(0)  # 浅色主题
            self.theme_combo.blockSignals(False)

            # 停止主窗口的自动主题定时器，并重新启用主题按钮
            if self.parent():
                if hasattr(self.parent(), 'stop_auto_theme_timer'):
                    self.parent().stop_auto_theme_timer()
                if hasattr(self.parent(), 'update_theme_button_state'):
                    # 使用主窗口的update_theme_button_state方法来正确设置状态
                    self.parent().update_theme_button_state()

            toast_info(self, "已关闭自动切换")

    def on_log_level_changed(self, index: int):
        """日志级别下拉框改变事件"""
        level = self.log_level_combo.itemData(index)
        self.app_config.log_level = level
        toast_success(self, f"日志级别已设置为 {level}（重启生效）")

    def on_toast_level_changed(self, index: int):
        """Toast级别下拉框改变事件"""
        level = self.toast_level_combo.itemData(index)
        self.logger.debug(f"Toast级别下拉框改变: index={index}, level={level}")

        # 更新配置
        self.app_config.toast_level = level

        # 验证配置是否更新（使用已经导入的get_app_config，避免导入方式不一致）
        verify_config = get_app_config()
        self.logger.debug(f"配置验证: self.app_config.toast_level={self.app_config.toast_level}, "
                         f"get_app_config().toast_level={verify_config.toast_level}, "
                         f"是否同一实例={self.app_config is verify_config}")

        toast_success(self, f"Toast提示级别已设置为 {level}")

    def on_warmup_enabled_changed(self, checked: bool):
        """缓存预热开关改变事件（优化8）"""
        self.app_config.cache_warmup_enabled = checked
        status = "启用" if checked else "禁用"
        toast_success(self, f"缓存预热功能已{status}（仅网络路径有效）")

    def _on_warmup_count_changed_debounced(self, value: int):
        """预热图片数量改变事件（带防抖）"""
        # 记录待保存的值，重启防抖定时器
        self._pending_warmup_count = value
        self._warmup_count_debounce_timer.start(500)  # 500ms防抖

    def _save_warmup_count(self):
        """防抖定时器触发后实际保存"""
        value = self._pending_warmup_count
        self.app_config.cache_warmup_count = value
        toast_success(self, f"预热图片数量已设置为 {value} 张")

    def on_warmup_count_changed(self, value: int):
        """预热图片数量改变事件（优化8）- 保留兼容性"""
        self.app_config.cache_warmup_count = value
        toast_success(self, f"预热图片数量已设置为 {value} 张")

    def eventFilter(self, obj, event):
        """事件过滤器：禁用SpinBox的滚轮事件"""
        if obj == self.warmup_count_spinbox and event.type() == QEvent.Type.Wheel:
            # 拦截滚轮事件，不传递给SpinBox
            return True
        return super().eventFilter(obj, event)

    def on_local_loop_changed(self, checked: bool):
        """本地路径循环翻页开关改变事件"""
        self.app_config.local_loop_enabled = checked
        status = "启用" if checked else "禁用"
        toast_success(self, f"本地路径循环翻页已{status}（翻页到边界时生效）")

    def on_network_loop_changed(self, checked: bool):
        """网络路径循环翻页开关改变事件"""
        self.app_config.network_loop_enabled = checked
        status = "启用" if checked else "禁用"

        if checked:
            toast_success(self, f"网络路径循环翻页已{status}\n翻页到边界时生效，末尾预热需重新打开目录")
        else:
            toast_success(self, f"网络路径循环翻页已{status}（翻页到边界时生效）")

    def select_theme(self, mode: str):
        """选择主题模式并立即应用

        Args:
            mode: "light"(亮色), "dark"(暗色), "system"(跟随系统)
        """
        # 更新下拉列表状态（阻止信号触发）
        self.theme_combo.blockSignals(True)
        if mode == "system":
            self.theme_combo.setCurrentIndex(2)  # 跟随系统
            # 获取系统主题
            actual_theme = self.app_config.get_system_theme()
            # 先设置主题，再设置模式（这样模式设置时可以正确读取新主题）
            self.app_config.theme = actual_theme
            self.app_config.theme_mode = "system"
            default_theme.set_theme(actual_theme)
            toast_message = f"已切换到系统模式（当前: {'亮色' if actual_theme == 'light' else '暗色'}主题）"
        else:
            # 手动选择亮色或暗色
            if mode == "light":
                self.theme_combo.setCurrentIndex(0)  # 浅色主题
            else:
                self.theme_combo.setCurrentIndex(1)  # 深色主题

            # 先设置主题，再设置模式（这样模式设置时可以正确读取新主题）
            self.app_config.theme = mode
            self.app_config.theme_mode = "manual"
            default_theme.set_theme(mode)
            toast_message = f"已切换到{'亮色' if mode == 'light' else '暗色'}主题"
        self.theme_combo.blockSignals(False)

        # 先应用设置面板的主题样式
        self._apply_theme()

        # 再同步更新主窗口
        if self.parent():
            # 更新主窗口样式
            if hasattr(self.parent(), 'apply_theme'):
                self.parent().apply_theme()

            # 更新主题按钮图标和启用状态
            if hasattr(self.parent(), 'theme_button'):
                current_theme = self.app_config.theme
                theme_icon = '☾' if current_theme == "light" else '☼'
                self.parent().theme_button.setText(theme_icon)

                if mode == "system":
                    # 跟随系统模式：禁用主窗口按钮
                    self.parent().theme_button.setEnabled(False)
                    self.parent().theme_button.setToolTip("已启用跟随系统，点击查看提示")
                else:
                    # 手动模式：启用主窗口按钮（但需要检查性能）
                    if hasattr(self.parent(), 'update_theme_button_state'):
                        self.parent().update_theme_button_state()
                    else:
                        self.parent().theme_button.setEnabled(True)
                        theme_tooltip = '切换到暗色主题' if current_theme == "light" else '切换到亮色主题'
                        self.parent().theme_button.setToolTip(theme_tooltip)

        # 提示用户已应用
        toast_success(self, toast_message)

    def save_update_proxy(self):
        """校验并保存检查更新和下载共用的代理配置。"""
        raw_value = self.update_proxy_input.text().strip()
        try:
            proxy = normalize_update_proxy(raw_value)
        except ValueError as exc:
            toast_warning(self, str(exc))
            self.update_proxy_input.setFocus()
            return
        self.update_proxy_input.setText(proxy)
        self.app_config.update_proxy = proxy
        toast_success(
            self,
            "更新代理已保存" if proxy else "已恢复为直接连接 GitHub",
        )

    def reset_tutorial(self):
        """重置教程状态"""
        msgBox = ThemedMessageBox(self)
        msgBox.setWindowTitle("确认重置")
        msgBox.setText("确定要重置教程状态吗？\n下次启动程序时将重新显示新手引导。")
        msgBox.setIcon(QMessageBox.Icon.Question)
        yes_btn = msgBox.addButton("是", QMessageBox.ButtonRole.YesRole)
        no_btn = msgBox.addButton("否", QMessageBox.ButtonRole.NoRole)
        msgBox.setDefaultButton(no_btn)
        msgBox.exec()

        if msgBox.clickedButton() == yes_btn:
            self.app_config.reset_tutorial()
            toast_success(self, "教程状态已重置")

            # 更新状态显示
            self.tutorial_status_label.setText("⏸️ 教程未开始")
            c = default_theme.colors
            self.tutorial_status_label.setStyleSheet(f"""
                QLabel {{
                    color: {c.TEXT_SECONDARY};
                    font-size: 13px;
                    padding: 10px;
                    background-color: {c.BACKGROUND_SECONDARY};
                    border-radius: 4px;
                }}
            """)

    def start_tutorial(self):
        """关闭设置面板并立即开始教程"""
        # 重置教程状态
        self.app_config.reset_tutorial()

        # 关闭设置对话框
        self.accept()

        # 触发主窗口的教程
        if hasattr(self.parent(), 'start_tutorial'):
            self.parent().start_tutorial()

    def clear_directory_history(self):
        """清除目录历史"""
        msgBox = ThemedMessageBox(self)
        msgBox.setWindowTitle("确认清除")
        msgBox.setText("确定要清除工作目录历史记录吗？")
        msgBox.setIcon(QMessageBox.Icon.Question)
        yes_btn = msgBox.addButton("是", QMessageBox.ButtonRole.YesRole)
        no_btn = msgBox.addButton("否", QMessageBox.ButtonRole.NoRole)
        msgBox.setDefaultButton(no_btn)
        msgBox.exec()

        if msgBox.clickedButton() == yes_btn:
            self.app_config.last_opened_directory = ""
            self.last_dir_label.setText("（无）")
            toast_success(self, "历史记录已清除")

    def clear_smb_cache(self):
        """清除SMB缓存"""
        msgBox = ThemedMessageBox(self)
        msgBox.setWindowTitle("确认清除")
        msgBox.setText("确定要清除SMB/NAS网络路径的图片缓存吗？\n这将删除本地缓存目录中的所有文件。")
        msgBox.setIcon(QMessageBox.Icon.Question)
        yes_btn = msgBox.addButton("是", QMessageBox.ButtonRole.YesRole)
        no_btn = msgBox.addButton("否", QMessageBox.ButtonRole.NoRole)
        msgBox.setDefaultButton(no_btn)
        msgBox.exec()

        if msgBox.clickedButton() == yes_btn:
            try:
                # 清除内存缓存
                if self.parent() and hasattr(self.parent(), 'image_loader'):
                    self.parent().image_loader.clear_cache()

                # 清除磁盘缓存
                cache_dir = get_cache_dir()
                if cache_dir.exists():
                    import shutil
                    for item in cache_dir.iterdir():
                        try:
                            if item.is_file():
                                item.unlink()
                            elif item.is_dir():
                                shutil.rmtree(item)
                        except Exception as e:
                            self.logger.warning(f"删除缓存文件失败 {item}: {e}")

                # 更新缓存大小显示
                self._update_cache_size_display()

                toast_success(self, "SMB缓存已清除")
                self.logger.warning("用户手动清除了SMB缓存")
            except Exception as e:
                self.logger.error(f"清除SMB缓存失败: {e}")
                toast_error(self, f"清除缓存失败: {str(e)}")

    def _update_cache_size_display(self):
        """更新缓存大小显示"""
        try:
            cache_dir = get_cache_dir()
            if not cache_dir.exists():
                self.cache_size_label.setText("缓存大小：0 B（0 个文件）")
                return

            total_size = 0
            file_count = 0

            for item in cache_dir.rglob('*'):
                if item.is_file():
                    try:
                        total_size += item.stat().st_size
                        file_count += 1
                    except Exception:
                        continue

            # 格式化大小显示
            if total_size < 1024:
                size_str = f"{total_size} B"
            elif total_size < 1024 * 1024:
                size_str = f"{total_size / 1024:.2f} KB"
            elif total_size < 1024 * 1024 * 1024:
                size_str = f"{total_size / (1024 * 1024):.2f} MB"
            else:
                size_str = f"{total_size / (1024 * 1024 * 1024):.2f} GB"

            self.cache_size_label.setText(f"📦 缓存大小：{size_str}（{file_count} 个文件）")

        except Exception as e:
            self.logger.error(f"更新缓存大小显示失败: {e}")
            self.cache_size_label.setText("缓存大小：计算失败")

    def _save_zoom_config(self):
        """保存缩放配置到磁盘（防抖定时器触发）"""
        try:
            self.app_config._save_config()
            self.logger.debug("已保存缩放配置")
            # 显示当前缩放范围
            zoom_max = self.app_config.image_zoom_max
            zoom_min = self.app_config.image_zoom_min
            toast_success(self, f"缩放范围已设置：{zoom_min:.2f}x ~ {zoom_max:.1f}x")
        except Exception as e:
            self.logger.error(f"保存缩放配置失败: {e}")

    def on_zoom_max_changed(self, value: float):
        """最大缩放倍数变化处理（使用防抖机制延迟保存）"""
        # 只更新内存中的值，不立即保存（绕过setter）
        self.app_config._config["image_zoom_max"] = value
        # 通知主窗口更新缩放限制（立即生效）
        if self.parent() and hasattr(self.parent(), 'image_label'):
            self.parent().image_label.max_scale = value
        # 重启防抖定时器（500ms后保存）
        self.zoom_save_timer.stop()
        self.zoom_save_timer.start(500)

    def on_zoom_min_changed(self, value: float):
        """最小缩放倍数变化处理（使用防抖机制延迟保存）"""
        # 只更新内存中的值，不立即保存（绕过setter）
        self.app_config._config["image_zoom_min"] = value
        # 通知主窗口更新缩放限制（立即生效）
        if self.parent() and hasattr(self.parent(), 'image_label'):
            self.parent().image_label.min_scale = value
        # 重启防抖定时器（500ms后保存）
        self.zoom_save_timer.stop()
        self.zoom_save_timer.start(500)

    def on_remember_zoom_changed(self, checked: bool):
        """全局应用缩放倍数选项变化处理"""
        self.app_config.global_zoom_enabled = checked
        toast_info(self, f"全局缩放功能已{'启用' if checked else '禁用'}")

    def reset_to_defaults(self):
        """恢复默认设置"""
        # 创建消息框（与删除类别确认框样式一致）
        msg_box = ThemedMessageBox(self)
        msg_box.setWindowTitle("⚠️ 确认恢复默认")
        msg_box.setText("确定要恢复所有设置到默认值吗？")
        msg_box.setInformativeText("此操作不可撤销。")
        msg_box.setIcon(QMessageBox.Icon.Question)

        # 创建中文按钮
        yes_button = QPushButton("是")
        no_button = QPushButton("否")

        msg_box.addButton(yes_button, QMessageBox.ButtonRole.YesRole)
        msg_box.addButton(no_button, QMessageBox.ButtonRole.NoRole)

        # 设置默认按钮为"否"
        msg_box.setDefaultButton(no_button)

        # 显示对话框并处理结果
        msg_box.exec()
        clicked_button = msg_box.clickedButton()

        if clicked_button == yes_button:
            # 恢复默认值
            self.theme_combo.setCurrentIndex(0)  # 默认浅色主题
            self.auto_theme_switch.setChecked(False)  # 默认关闭自动切换
            self.theme_combo.setEnabled(True)  # 确保下拉列表可用

            self.update_proxy_input.setText("")

            # 恢复日志级别和Toast级别到默认值（INFO）
            for i in range(self.log_level_combo.count()):
                if self.log_level_combo.itemData(i) == "INFO":
                    self.log_level_combo.setCurrentIndex(i)
                    break
            for i in range(self.toast_level_combo.count()):
                if self.toast_level_combo.itemData(i) == "INFO":
                    self.toast_level_combo.setCurrentIndex(i)
                    break

            # 保存配置（实时保存）
            self.app_config.update_proxy = ""
            self.app_config.log_level = "INFO"
            self.app_config.toast_level = "INFO"

            toast_success(self, "已恢复默认设置")

    def _apply_theme(self):
        """应用主题样式"""
        c = default_theme.colors

        self.setStyleSheet(f"""
            QDialog {{
                background-color: {c.BACKGROUND_PRIMARY};
                color: {c.TEXT_PRIMARY};
            }}
            QLabel {{
                color: {c.TEXT_PRIMARY};
            }}
            QTabWidget::pane {{
                border: 1px solid {c.BORDER_MEDIUM};
                border-radius: 4px;
                background-color: {c.BACKGROUND_CARD};
            }}
            QTabBar::tab {{
                background-color: {c.BACKGROUND_SECONDARY};
                color: {c.TEXT_SECONDARY};
                padding: 8px 16px;
                border: 1px solid {c.BORDER_LIGHT};
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                margin-right: 2px;
            }}
            QTabBar::tab:selected {{
                background-color: {c.BACKGROUND_CARD};
                color: {c.TEXT_PRIMARY};
                border-bottom: 2px solid {c.PRIMARY};
            }}
            QTabBar::tab:hover {{
                background-color: {c.BACKGROUND_HOVER};
            }}
            {ButtonStyles.get_dialog_button_style()}
            QLineEdit {{
                background-color: {c.BACKGROUND_SECONDARY};
                color: {c.TEXT_PRIMARY};
                border: 1px solid {c.BORDER_MEDIUM};
                border-radius: 4px;
                padding: 6px 10px;
            }}
            QLineEdit:focus {{
                border: 1px solid {c.PRIMARY};
            }}
            QCheckBox {{
                color: {c.TEXT_PRIMARY};
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border: 2px solid {c.BORDER_MEDIUM};
                border-radius: 3px;
                background-color: {c.BACKGROUND_SECONDARY};
            }}
            QCheckBox::indicator:checked {{
                background-color: {c.PRIMARY};
                border-color: {c.PRIMARY};
            }}
            QGroupBox {{
                color: {c.TEXT_PRIMARY};
                border: 1px solid {c.BORDER_MEDIUM};
                border-radius: 6px;
                margin-top: 12px;
                font-weight: bold;
                padding-top: 8px;
                background-color: {c.BACKGROUND_CARD};
            }}
            QGroupBox::title {{
                color: {c.TEXT_PRIMARY};
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 8px;
                background-color: {c.BACKGROUND_CARD};
            }}
            QScrollArea {{
                background-color: {c.BACKGROUND_CARD};
                border: none;
            }}
            QWidget#scrollContent {{
                background-color: {c.BACKGROUND_CARD};
            }}
            QTabWidget > QWidget {{
                background-color: {c.BACKGROUND_CARD};
            }}
            QScrollBar:vertical {{
                background-color: {c.BACKGROUND_SECONDARY};
                width: 12px;
                border-radius: 6px;
                margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background-color: {c.BORDER_MEDIUM};
                border-radius: 6px;
                min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{
                background-color: {c.TEXT_SECONDARY};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
            }}
            QScrollBar:horizontal {{
                background-color: {c.BACKGROUND_SECONDARY};
                height: 12px;
                border-radius: 6px;
                margin: 0px;
            }}
            QScrollBar::handle:horizontal {{
                background-color: {c.BORDER_MEDIUM};
                border-radius: 6px;
                min-width: 20px;
            }}
            QScrollBar::handle:horizontal:hover {{
                background-color: {c.TEXT_SECONDARY};
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                width: 0px;
            }}
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
                background: none;
            }}
            QComboBox {{
                background-color: {c.BACKGROUND_SECONDARY};
                color: {c.TEXT_PRIMARY};
                border: 2px solid {c.BORDER_MEDIUM};
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 13px;
                font-weight: 500;
            }}
            QComboBox:hover {{
                border-color: {c.PRIMARY};
            }}
            QComboBox:disabled {{
                background-color: {c.GRAY_100};
                color: {c.TEXT_DISABLED};
                border-color: {c.BORDER_LIGHT};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 0px;
            }}
            QComboBox::down-arrow {{
                image: none;
                width: 0;
                height: 0;
            }}
            QComboBox QAbstractItemView {{
                background-color: {c.BACKGROUND_CARD};
                border: 2px solid {c.BORDER_MEDIUM};
                border-radius: 6px;
                selection-background-color: {c.PRIMARY};
                selection-color: white;
                padding: 4px;
                color: {c.TEXT_PRIMARY};
                min-width: 180px;
            }}
            QComboBox QAbstractItemView::item {{
                padding: 8px 12px;
                min-height: 32px;
                color: {c.TEXT_PRIMARY};
            }}
            QComboBox QAbstractItemView::item:hover {{
                background-color: {c.BACKGROUND_HOVER};
                color: {c.TEXT_PRIMARY};
            }}
            QComboBox QAbstractItemView::item:selected {{
                background-color: {c.PRIMARY};
                color: white;
            }}
            QWidget#separator_line {{
                background-color: {c.BORDER_MEDIUM};
            }}
            QLabel {{
                color: {c.TEXT_PRIMARY};
            }}
        """)

        self._style_action_buttons()

        # SpinBox 使用自己的组合控件样式，避免父级 QLineEdit 内边距裁切数字。
        for spinbox in self.findChildren(QSpinBox):
            self._apply_spinbox_style(spinbox)
        for spinbox in self.findChildren(QDoubleSpinBox):
            self._apply_spinbox_style(spinbox)
        for button in self.findChildren(QPushButton):
            direction = button.property("uiSpinDirection")
            if direction:
                self._style_spinbox_button(
                    button,
                    direction,
                    int(button.property("uiSpinHeight") or 16),
                )

        # 单独更新教程状态标签的样式（使用内联样式确保优先级）
        if hasattr(self, 'tutorial_status_label') and hasattr(self, 'tutorial_status_color'):
            if default_theme.is_dark:
                bg_color = "rgba(255, 255, 255, 0.08)"
            else:
                bg_color = "rgba(0, 0, 0, 0.05)"

            self.tutorial_status_label.setStyleSheet(f"""
                QLabel#tutorialStatusLabel {{
                    color: {self.tutorial_status_color} !important;
                    font-size: 13px;
                    font-weight: normal !important;
                    padding: 10px;
                    background-color: {bg_color};
                    border-radius: 4px;
                }}
            """)

        # 强制刷新所有子组件的样式（防止缓存导致颜色不更新）
        # 参考主窗口的实现，确保主题切换时所有组件都能正确渲染新颜色
        self._refresh_all_widgets()

    def _style_action_buttons(self):
        """按按钮语义统一设置页中的颜色、宽度和 36px 高度。"""
        for button in self.findChildren(QPushButton):
            if button.property("uiControlPart"):
                continue
            text = button.text().replace("✓", "").replace("✕", "").strip()
            size = "compact" if button.objectName() == "iconButton" else "standard"
            min_width = 72 if size == "compact" else None
            if any(keyword in text for keyword in ("恢复默认", "清除历史", "清除SMB")):
                style_button(button, "danger", size, min_width=min_width)
            elif any(keyword in text for keyword in ("检查更新", "保存")):
                style_button(button, "primary", size, min_width=min_width)
            else:
                style_button(button, "secondary", size, min_width=min_width)

    def _refresh_all_widgets(self):
        """强制刷新所有子组件的样式渲染

        Qt的样式系统存在缓存机制，当通过父容器的setStyleSheet更改样式时，
        某些已渲染的子组件可能不会自动更新。这个方法通过unpolish/polish
        强制Qt重新计算和应用所有组件的样式。

        同时，对于所有QLabel和QCheckBox，明确设置它们的颜色以确保正确渲染。
        """
        c = default_theme.colors

        # 获取所有QLabel和QCheckBox
        all_labels = self.findChildren(QLabel)
        all_checkboxes = self.findChildren(QCheckBox)

        # 手动更新特殊标签
        if hasattr(self, 'last_dir_label') and self.last_dir_label:
            self.last_dir_label.setStyleSheet(f"""
                color: {c.TEXT_PRIMARY};
                padding: 10px;
                background-color: {c.BACKGROUND_SECONDARY};
                border-radius: 4px;
                font-size: 12px;
                font-family: monospace;
            """)

        # 手动更新所有缓存路径标签（基础Tab和高级Tab）
        cache_labels = [label for label in all_labels if label.objectName() == "cacheDirLabel"]
        for cache_label in cache_labels:
            cache_label.setStyleSheet(f"""
                color: {c.TEXT_PRIMARY};
                padding: 10px;
                background-color: {c.BACKGROUND_SECONDARY};
                border-radius: 4px;
                font-size: 12px;
                font-family: monospace;
            """)

        # 手动更新缓存大小标签
        cache_size_labels = [label for label in all_labels if label.objectName() == "cacheSizeLabel"]
        for cache_size_label in cache_size_labels:
            cache_size_label.setStyleSheet(f"""
                color: {c.TEXT_SECONDARY};
                padding: 8px 10px;
                background-color: {c.BACKGROUND_SECONDARY};
                border-radius: 4px;
                font-size: 12px;
            """)

        # 处理所有QLabel
        for label in all_labels:
            # 跳过特殊的状态标签（它有自己的颜色处理）
            if label.objectName() in ("tutorialStatusLabel", "lastDirLabel", "cacheDirLabel", "cacheSizeLabel"):
                continue

            current_style = label.styleSheet()

            if current_style:
                # 有inline样式的情况
                if 'color:' in current_style:
                    # 替换现有颜色
                    new_style = re.sub(r'color:\s*[^;]+', f'color: {c.TEXT_PRIMARY}', current_style)
                    label.setStyleSheet(new_style)
                else:
                    # 添加颜色
                    new_style = current_style.rstrip(';') + f'; color: {c.TEXT_PRIMARY};'
                    label.setStyleSheet(new_style)
            else:
                # 没有inline样式，明确设置颜色以避免缓存问题
                label.setStyleSheet(f'color: {c.TEXT_PRIMARY};')

        # 处理所有QCheckBox
        for checkbox in all_checkboxes:
            current_style = checkbox.styleSheet()

            if current_style:
                if 'color:' in current_style:
                    new_style = re.sub(r'color:\s*[^;]+', f'color: {c.TEXT_PRIMARY}', current_style)
                    checkbox.setStyleSheet(new_style)
                else:
                    new_style = current_style.rstrip(';') + f'; color: {c.TEXT_PRIMARY};'
                    checkbox.setStyleSheet(new_style)
            else:
                checkbox.setStyleSheet(f'color: {c.TEXT_PRIMARY};')

        # 获取所有子组件（递归）
        all_widgets = self.findChildren(QWidget)

        # 对每个组件强制重新应用样式
        for widget in all_widgets:
            # unpolish 移除当前样式，polish 重新应用样式
            # 这会强制Qt重新计算组件的外观
            widget.style().unpolish(widget)
            widget.style().polish(widget)
            # 触发重绘
            widget.update()

        # 同时刷新对话框本身
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def _apply_spinbox_style(self, spinbox):
        """为spinbox应用美化样式（组合式组件风格：左侧圆角，右侧直角连接按钮）

        支持 QSpinBox 和 QDoubleSpinBox
        """
        c = default_theme.colors

        # 使用通用选择器，同时匹配 QSpinBox 和 QDoubleSpinBox
        spinbox.setStyleSheet(f"""
            QSpinBox, QDoubleSpinBox {{
                background-color: {c.BACKGROUND_SECONDARY};
                color: {c.TEXT_PRIMARY};
                border: 1px solid {c.BORDER_MEDIUM};
                border-radius: 4px;
                border-top-right-radius: 0px;
                border-bottom-right-radius: 0px;
                padding: 0px 8px;
                font-size: 13px;
                selection-background-color: {c.PRIMARY};
            }}
            QSpinBox QLineEdit, QDoubleSpinBox QLineEdit {{
                background-color: transparent;
                color: {c.TEXT_PRIMARY};
                border: none;
                padding: 0px;
                margin: 0px;
                selection-background-color: {c.PRIMARY};
            }}
            QSpinBox:hover, QDoubleSpinBox:hover {{
                border-color: {c.PRIMARY};
            }}
            QSpinBox:focus, QDoubleSpinBox:focus {{
                border-color: {c.PRIMARY};
                background-color: {c.BACKGROUND_PRIMARY};
            }}
            QSpinBox::up-button, QSpinBox::down-button,
            QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
                width: 0px;
                border: none;
                background: transparent;
            }}
        """)
        # 必须在 setStyleSheet 之后设置，Qt 的样式重新 polish 会重算最小高度。
        spinbox.setFixedHeight(32)

    def _style_spinbox_button(self, button, direction: str, button_height: int):
        """应用组合 SpinBox 上下按钮样式，并支持运行时切换主题。"""
        c = default_theme.colors
        is_up = direction == "up"
        top_right_radius = "4px" if is_up else "0px"
        bottom_right_radius = "0px" if is_up else "4px"
        horizontal_border = (
            f"border-bottom: 1px solid {c.BORDER_MEDIUM};"
            if is_up
            else "border-top: none;"
        )
        button.setStyleSheet(f"""
            QPushButton {{
                background-color: {c.BACKGROUND_SECONDARY};
                color: {c.TEXT_SECONDARY};
                border: 1px solid {c.BORDER_MEDIUM};
                border-left: none;
                {horizontal_border}
                border-top-right-radius: {top_right_radius};
                border-bottom-right-radius: {bottom_right_radius};
                margin: 0px;
                padding: 0px;
                font-size: 8px;
                min-height: 0px;
                max-height: {button_height}px;
            }}
            QPushButton:hover {{
                background-color: {c.BACKGROUND_HOVER};
                color: {c.TEXT_PRIMARY};
            }}
            QPushButton:pressed {{
                background-color: {c.PRIMARY};
                color: {c.TEXT_ON_PRIMARY};
            }}
        """)
        button.setFixedHeight(button_height)

    def _create_spinbox_buttons(self, spinbox, button_height=12):
        """创建外部垂直排列的上下按钮（组合式组件风格）

        Args:
            spinbox: 要绑定的QSpinBox或QDoubleSpinBox
            button_height: 每个按钮的高度，默认12px

        Returns:
            QWidget: 包含上下按钮的容器组件
        """
        # 按钮容器
        btn_container = QWidget()
        btn_container.setFixedWidth(20)
        btn_container.setFixedHeight(button_height * 2)
        buttons_layout = QVBoxLayout(btn_container)
        buttons_layout.setSpacing(0)
        buttons_layout.setContentsMargins(0, 0, 0, 0)

        # 上箭头按钮（右上圆角，无左边框，底部分割线）
        up_button = QPushButton("▲")
        up_button.setProperty("uiControlPart", True)
        up_button.setProperty("uiSpinDirection", "up")
        up_button.setProperty("uiSpinHeight", button_height)
        up_button.setFixedHeight(button_height)
        up_button.setCursor(Qt.CursorShape.PointingHandCursor)
        up_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # 防止抢走输入框焦点
        up_button.setAutoRepeat(True)  # 长按连发
        up_button.setAutoRepeatDelay(400)  # 首次延迟400ms
        up_button.setAutoRepeatInterval(80)  # 之后每80ms触发一次
        self._style_spinbox_button(up_button, "up", button_height)
        up_button.clicked.connect(lambda: spinbox.stepUp())
        buttons_layout.addWidget(up_button)

        # 下箭头按钮（右下圆角，无左边框，无上边框）
        down_button = QPushButton("▼")
        down_button.setProperty("uiControlPart", True)
        down_button.setProperty("uiSpinDirection", "down")
        down_button.setProperty("uiSpinHeight", button_height)
        down_button.setFixedHeight(button_height)
        down_button.setCursor(Qt.CursorShape.PointingHandCursor)
        down_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # 防止抢走输入框焦点
        down_button.setAutoRepeat(True)  # 长按连发
        down_button.setAutoRepeatDelay(400)  # 首次延迟400ms
        down_button.setAutoRepeatInterval(80)  # 之后每80ms触发一次
        self._style_spinbox_button(down_button, "down", button_height)
        down_button.clicked.connect(lambda: spinbox.stepDown())
        buttons_layout.addWidget(down_button)

        return btn_container

    def showEvent(self, event):
        """对话框显示时居中并同步配置"""
        super().showEvent(event)

        # 居中对话框
        if not self._centered and self.parent():
            parent_geometry = self.parent().geometry()
            x = parent_geometry.x() + (parent_geometry.width() - self.width()) // 2
            y = parent_geometry.y() + (parent_geometry.height() - self.height()) // 2
            self.move(x, y)
            self._centered = True

        # 重新加载配置以同步主窗口的主题变化
        self.app_config.reload_config()
        self.update_proxy_input.setText(self.app_config.update_proxy)

        # 更新主题下拉框的值
        current_theme_mode = self.app_config.theme_mode

        # 阻止信号触发
        self.theme_combo.blockSignals(True)

        if current_theme_mode == "auto":
            # 自动切换模式
            self.auto_theme_switch.setChecked(True)
            self.theme_combo.setEnabled(False)
            # 设置为当前实际主题
            if self.app_config.theme == "dark":
                self.theme_combo.setCurrentIndex(1)
            else:
                self.theme_combo.setCurrentIndex(0)
        elif current_theme_mode == "system":
            # 跟随系统模式
            self.theme_combo.setCurrentIndex(2)
            self.auto_theme_switch.setChecked(False)
        elif self.app_config.theme == "dark":
            # 暗色主题
            self.theme_combo.setCurrentIndex(1)
            # Phase 1.1: Model/View架构已解决性能问题，移除限制
            self.theme_combo.setEnabled(True)
            self.auto_theme_switch.setChecked(False)
        else:
            # 亮色主题
            self.theme_combo.setCurrentIndex(0)
            # Phase 1.1: Model/View架构已解决性能问题，移除限制
            self.theme_combo.setEnabled(True)
            self.auto_theme_switch.setChecked(False)

        # 恢复信号
        self.theme_combo.blockSignals(False)

    def closeEvent(self, event):
        """对话框关闭时，立即保存未完成的配置"""
        # 如果防抖定时器正在运行，立即触发保存
        if self.zoom_save_timer.isActive():
            self.zoom_save_timer.stop()
            self._save_zoom_config()
            self.logger.debug("对话框关闭，立即保存缩放配置")
        super().closeEvent(event)
