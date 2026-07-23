"""
更新对话框模块

包含更新信息展示和下载功能
"""

import logging
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                            QPushButton, QProgressBar, QTextEdit, QMessageBox)
from PyQt6.QtCore import Qt
from .components.toast import toast_error
from .components.styles.theme import default_theme
from utils.app_config import get_app_config
from .update_download import get_update_download_controller


class UpdateInfoDialog(QDialog):
    """更新信息对话框 - 显示更新详情并支持下载"""

    def __init__(self, new_version: str, current_version: str,
                 size_bytes: int, notes: str, manifest: dict, token: str = "",
                 parent=None):
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)
        self.new_version = new_version
        self.current_version = current_version
        self.size_bytes = size_bytes
        self.notes = notes
        self.manifest = manifest
        self.token = token
        self.initUI()

    def initUI(self):
        """初始化UI"""
        self.setWindowTitle("发现新版本")
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(30, 30, 30, 30)

        # 图标和标题区域
        header_layout = QHBoxLayout()
        header_layout.setSpacing(15)

        # 图标（使用问号图标）
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(48, 48)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setText("?")
        header_layout.addWidget(self.icon_label)

        # 版本信息
        version_layout = QVBoxLayout()
        version_layout.setSpacing(5)

        self.version_title = QLabel(f"检测到新版本: v{self.new_version}")
        version_layout.addWidget(self.version_title)

        self.current_label = QLabel(f"当前版本: v{self.current_version}")
        version_layout.addWidget(self.current_label)

        header_layout.addLayout(version_layout)
        header_layout.addStretch()

        layout.addLayout(header_layout)

        # 文件大小
        size_mb = f"{self.size_bytes/1024/1024:.1f} MB" if self.size_bytes else "未知"
        self.size_label = QLabel(f"大小: {size_mb}")
        layout.addWidget(self.size_label)

        # 更新说明
        self.notes_title = QLabel("更新说明:")
        layout.addWidget(self.notes_title)

        # 更新说明文本框
        self.notes_text = QTextEdit()
        self.notes_text.setReadOnly(True)
        self.notes_text.setMaximumHeight(150)

        # 处理notes格式（从分号分隔转换为换行）
        formatted_notes = self.notes.replace('; ', '\n') if self.notes else "暂无更新说明"
        self.notes_text.setPlainText(formatted_notes)

        layout.addWidget(self.notes_text)

        # 提示文字
        self.prompt_label = QLabel("是否立即下载并更新？")
        layout.addWidget(self.prompt_label)

        layout.addStretch()

        # 按钮区域
        button_layout = QHBoxLayout()
        button_layout.setSpacing(15)
        button_layout.addStretch()

        # 确定按钮
        self.confirm_btn = QPushButton("确定")
        self.confirm_btn.setMinimumWidth(100)
        self.confirm_btn.setMinimumHeight(36)
        self.confirm_btn.clicked.connect(self.start_download)
        button_layout.addWidget(self.confirm_btn)

        # 取消按钮
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.setMinimumWidth(100)
        self.cancel_btn.setMinimumHeight(36)
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)

        layout.addLayout(button_layout)

        # 应用主题
        self._apply_theme()

    def _apply_theme(self):
        """应用主题样式"""
        # 确保使用当前配置的主题
        config = get_app_config()
        default_theme.set_theme(config.theme)
        c = default_theme.colors

        # 整体对话框样式
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {c.BACKGROUND_PRIMARY};
            }}
        """)

        # 图标样式
        self.icon_label.setStyleSheet(f"""
            QLabel {{
                background-color: {c.PRIMARY};
                border-radius: 24px;
                font-size: 32px;
                color: white;
            }}
        """)

        # 版本标题
        self.version_title.setStyleSheet(f"""
            font-size: 16px;
            font-weight: bold;
            color: {c.TEXT_PRIMARY};
        """)

        # 当前版本
        self.current_label.setStyleSheet(f"""
            font-size: 13px;
            color: {c.TEXT_SECONDARY};
        """)

        # 文件大小
        self.size_label.setStyleSheet(f"""
            font-size: 14px;
            color: {c.TEXT_PRIMARY};
            margin-left: 10px;
        """)

        # 更新说明标题
        self.notes_title.setStyleSheet(f"""
            font-size: 14px;
            font-weight: bold;
            color: {c.TEXT_PRIMARY};
            margin-top: 10px;
        """)

        # 更新说明文本框
        self.notes_text.setStyleSheet(f"""
            QTextEdit {{
                background-color: {c.BACKGROUND_SECONDARY};
                border: 1px solid {c.BORDER_MEDIUM};
                border-radius: 6px;
                padding: 10px;
                font-size: 13px;
                color: {c.TEXT_PRIMARY};
                line-height: 1.6;
            }}
        """)

        # 提示文字
        self.prompt_label.setStyleSheet(f"""
            font-size: 14px;
            color: {c.TEXT_PRIMARY};
            margin-top: 10px;
        """)

        # 确定按钮
        self.confirm_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {c.PRIMARY};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 20px;
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {c.PRIMARY_DARK};
            }}
            QPushButton:pressed {{
                background-color: {c.PRIMARY_DARK};
            }}
        """)

        # 取消按钮
        self.cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {c.GRAY_500};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 20px;
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {c.GRAY_600};
            }}
            QPushButton:pressed {{
                background-color: {c.GRAY_700};
            }}
        """)

    def start_download(self):
        """开始下载更新"""
        try:
            url = str(self.manifest.get('url', '')).strip()
            if not url:
                toast_error(self, "下载链接无效")
                return
            controller = get_update_download_controller()
            controller.start(self.manifest, self.new_version, self.token)
            host = self.parentWidget()
            controller.show_progress_dialog(host)
            self.accept()
        except Exception as e:
            self.logger.error(f"下载更新失败: {e}")
            toast_error(self, f"下载失败: {str(e)}")


class DownloadProgressDialog(QDialog):
    """可切换后台、可真正取消并可重新打开的下载进度对话框。"""

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.setWindowTitle("下载更新")
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        # 提示标签
        self.label = QLabel("正在下载更新包...")
        layout.addWidget(self.label)

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        layout.addWidget(self.progress_bar)

        button_layout = QHBoxLayout()
        button_layout.addStretch()
        self.background_btn = QPushButton("后台下载")
        self.background_btn.clicked.connect(self.hide)
        button_layout.addWidget(self.background_btn)
        self.action_btn = QPushButton("取消下载")
        self.action_btn.clicked.connect(self._handle_action)
        button_layout.addWidget(self.action_btn)
        layout.addLayout(button_layout)

        self.controller.progress_changed.connect(self.update_progress)
        self.controller.state_changed.connect(self._on_state_changed)

        # 应用主题
        self._apply_theme()
        self.sync_from_controller()

    def _apply_theme(self):
        """应用主题样式"""
        # 确保使用当前配置的主题
        config = get_app_config()
        default_theme.set_theme(config.theme)
        c = default_theme.colors

        # 整体对话框样式
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {c.BACKGROUND_PRIMARY};
            }}
        """)

        # 提示标签样式
        self.label.setStyleSheet(f"""
            font-size: 14px;
            color: {c.TEXT_PRIMARY};
        """)

        # 进度条样式
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                border: 1px solid {c.BORDER_MEDIUM};
                border-radius: 4px;
                text-align: center;
                height: 24px;
                background-color: {c.BACKGROUND_SECONDARY};
                color: {c.TEXT_PRIMARY};
            }}
            QProgressBar::chunk {{
                background-color: {c.PRIMARY};
                border-radius: 3px;
            }}
        """)

        self.background_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {c.GRAY_500};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 18px;
                min-width: 90px;
            }}
            QPushButton:hover {{ background-color: {c.GRAY_600}; }}
        """)
        self.action_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {c.PRIMARY};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 18px;
                min-width: 90px;
            }}
            QPushButton:hover {{ background-color: {c.PRIMARY_DARK}; }}
            QPushButton:disabled {{ background-color: {c.GRAY_500}; }}
        """)

    def update_progress(self, done: int, total: int):
        """更新进度"""
        if total > 0:
            self.progress_bar.setRange(0, 100)
            percentage = int((done / total) * 100)
            self.progress_bar.setValue(percentage)
            done_mb = done / 1024 / 1024
            total_mb = total / 1024 / 1024
            if self.controller.state == "verifying":
                self.label.setText(
                    f"正在校验: {done_mb:.1f} MB / {total_mb:.1f} MB"
                )
            else:
                self.label.setText(
                    f"正在下载: {done_mb:.1f} MB / {total_mb:.1f} MB"
                )
        else:
            self.progress_bar.setRange(0, 0)

    def set_verifying_mode(self):
        """设置为校验模式，显示不确定进度"""
        self.progress_bar.setRange(0, 0)  # 不确定进度模式
        self.label.setText("正在校验文件完整性...")
        self.setWindowTitle("校验文件")

    def sync_from_controller(self):
        """根据应用级控制器恢复当前显示状态。"""
        self._on_state_changed(self.controller.state, self.controller.message)
        if self.controller.is_active and (
            self.controller.downloaded or self.controller.total
        ):
            self.update_progress(
                self.controller.downloaded,
                self.controller.total,
            )

    def _on_state_changed(self, state: str, message: str):
        self.setWindowTitle("下载更新")
        if state == "downloading":
            self.label.setText(message or "正在下载更新包...")
            self.background_btn.setText("后台下载")
            self.background_btn.show()
            self.action_btn.setText("取消下载")
            self.action_btn.setEnabled(True)
        elif state == "verifying":
            self.label.setText(message or "正在校验更新包...")
            self.background_btn.setText("后台运行")
            self.background_btn.show()
            self.action_btn.setText("取消下载")
            self.action_btn.setEnabled(True)
        elif state == "cancelling":
            self.label.setText(message or "正在取消下载...")
            self.background_btn.hide()
            self.action_btn.setText("正在取消...")
            self.action_btn.setEnabled(False)
        elif state == "ready":
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(100)
            self.label.setText(message or "更新包已下载并校验完成")
            self.background_btn.setText("稍后安装")
            self.background_btn.show()
            self.action_btn.setText("立即重启")
            self.action_btn.setEnabled(True)
        elif state == "failed":
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)
            self.label.setText(f"下载失败：{message}")
            self.background_btn.hide()
            self.action_btn.setText("关闭")
            self.action_btn.setEnabled(True)
        elif state == "cancelled":
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)
            self.label.setText(message or "更新下载已取消")
            self.background_btn.hide()
            self.action_btn.setText("关闭")
            self.action_btn.setEnabled(True)
        else:
            self.label.setText(message or "暂无更新下载任务")
            self.background_btn.hide()
            self.action_btn.setText("关闭")
            self.action_btn.setEnabled(True)

    def _handle_action(self):
        if self.controller.is_active:
            if self._confirm_cancel_download():
                self.controller.cancel()
        elif self.controller.state == "ready":
            self.controller.install_ready_update()
        else:
            self.close()

    def _confirm_cancel_download(self) -> bool:
        """二次确认是否取消并删除未完成的更新下载。"""
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("确认取消下载")
        msg_box.setIcon(QMessageBox.Icon.Warning)
        msg_box.setText("确定要取消更新下载吗？")
        msg_box.setInformativeText("未完成的下载内容将被删除。")

        cancel_btn = msg_box.addButton(
            "取消下载",
            QMessageBox.ButtonRole.DestructiveRole,
        )
        continue_btn = msg_box.addButton(
            "继续下载",
            QMessageBox.ButtonRole.RejectRole,
        )
        msg_box.setDefaultButton(continue_btn)

        config = get_app_config()
        default_theme.set_theme(config.theme)
        c = default_theme.colors
        msg_box.setStyleSheet(f"""
            QMessageBox {{
                background-color: {c.BACKGROUND_PRIMARY};
                color: {c.TEXT_PRIMARY};
            }}
            QMessageBox QLabel {{ color: {c.TEXT_PRIMARY}; }}
            QPushButton {{
                border: none;
                border-radius: 6px;
                padding: 8px 18px;
                min-width: 90px;
                background-color: {c.PRIMARY};
                color: white;
            }}
            QPushButton:hover {{ background-color: {c.PRIMARY_DARK}; }}
        """)

        msg_box.exec()
        return msg_box.clickedButton() == cancel_btn

    def closeEvent(self, event):
        """点击窗口关闭按钮视为取消；后台下载必须显式选择。"""
        if self.controller.is_active:
            if not self._confirm_cancel_download():
                event.ignore()
                return
            self.controller.cancel()
        event.accept()
