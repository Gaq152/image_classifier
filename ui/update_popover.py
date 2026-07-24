"""锚定在状态栏版本按钮上的轻量更新中心。"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .components.styles.theme import default_theme


class UpdateCenterPopover(QFrame):
    """在版本按钮上方展开的非模态更新中心。"""

    check_requested = pyqtSignal()
    download_requested = pyqtSignal()
    pause_requested = pyqtSignal()
    resume_requested = pyqtSignal()
    cancel_requested = pyqtSignal()
    restart_requested = pyqtSignal()

    DOWNLOAD_STATES = {
        "downloading",
        "retrying",
        "verifying",
        "pausing",
        "paused",
        "cancelling",
        "ready",
    }

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setObjectName("updateCenterPopover")
        self.setFixedWidth(350)
        self._state = "idle"
        self._can_download = False
        self._confirm_action: Optional[str] = None
        self._build_ui()
        self.apply_theme()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(14)

        header = QHBoxLayout()
        header.setSpacing(10)
        self.status_dot = QFrame()
        self.status_dot.setObjectName("updateStatusDot")
        self.status_dot.setFixedSize(12, 12)
        header.addWidget(self.status_dot, 0, Qt.AlignmentFlag.AlignTop)

        header_text = QVBoxLayout()
        header_text.setSpacing(3)
        self.title_label = QLabel("软件更新")
        self.title_label.setObjectName("updatePopoverTitle")
        self.status_label = QLabel("点击下方按钮检查新版本")
        self.status_label.setObjectName("updatePopoverStatus")
        self.status_label.setWordWrap(True)
        header_text.addWidget(self.title_label)
        header_text.addWidget(self.status_label)
        header.addLayout(header_text, 1)
        layout.addLayout(header)

        version_panel = QFrame()
        version_panel.setObjectName("updateVersionPanel")
        version_layout = QVBoxLayout(version_panel)
        version_layout.setContentsMargins(12, 10, 12, 10)
        version_layout.setSpacing(9)
        self.current_version_value = self._add_version_row(
            version_layout,
            "当前版本",
        )
        self.latest_version_value = self._add_version_row(
            version_layout,
            "最新版本",
        )
        layout.addWidget(version_panel)

        self.progress_container = QWidget()
        progress_layout = QVBoxLayout(self.progress_container)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        progress_layout.setSpacing(6)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFixedHeight(8)
        self.progress_detail = QLabel("")
        self.progress_detail.setObjectName("updateProgressDetail")
        progress_layout.addWidget(self.progress_bar)
        progress_layout.addWidget(self.progress_detail)
        layout.addWidget(self.progress_container)
        self.progress_container.hide()

        actions = QHBoxLayout()
        actions.setSpacing(10)
        actions.addStretch()
        self.secondary_button = QPushButton("取消")
        self.secondary_button.setObjectName("updateSecondaryButton")
        self.secondary_button.setMinimumHeight(34)
        self.secondary_button.clicked.connect(self._on_secondary_clicked)
        self.primary_button = QPushButton("检查更新")
        self.primary_button.setObjectName("updatePrimaryButton")
        self.primary_button.setMinimumHeight(34)
        self.primary_button.clicked.connect(self._on_primary_clicked)
        actions.addWidget(self.secondary_button)
        actions.addWidget(self.primary_button)
        layout.addLayout(actions)

    @staticmethod
    def _add_version_row(layout: QVBoxLayout, label: str) -> QLabel:
        row = QHBoxLayout()
        key = QLabel(label)
        key.setObjectName("updateVersionKey")
        value = QLabel("—")
        value.setObjectName("updateVersionValue")
        value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(key)
        row.addStretch()
        row.addWidget(value)
        layout.addLayout(row)
        return value

    def set_state(
        self,
        state: str,
        current_version: str,
        latest_version: str = "",
        message: str = "",
        done: int = 0,
        total: int = 0,
        can_download: bool = False,
    ) -> None:
        """同步检查、下载与安装状态，不展示版本更新说明。"""
        state_changed = state != self._state
        self._state = state
        self._can_download = can_download
        self.current_version_value.setText(f"v{current_version}")
        self.latest_version_value.setText(
            f"v{latest_version}" if latest_version else "—"
        )
        self._sync_progress(state, done, total)

        if self._confirm_action and not state_changed:
            return
        self._confirm_action = None
        title, fallback = self._state_copy(state, latest_version)
        self.title_label.setText(title)
        self.status_label.setText(message or fallback)
        self._configure_actions(state)
        self._apply_state_color(state)

    @staticmethod
    def _state_copy(state: str, latest_version: str) -> tuple[str, str]:
        if state == "checking":
            return "正在检查更新", "正在连接更新服务器..."
        if state == "available":
            return "发现新版本", f"新版本 v{latest_version} 可以下载。"
        if state == "downloading":
            return "正在下载更新", "下载可在后台继续进行。"
        if state == "retrying":
            return "正在重试下载", "网络连接不稳定，正在自动重试。"
        if state == "verifying":
            return "正在校验更新", "正在验证更新包完整性。"
        if state == "pausing":
            return "正在暂停下载", "正在保存当前下载进度。"
        if state == "paused":
            return "更新已暂停", "已保留下载进度，可随时继续。"
        if state == "cancelling":
            return "正在取消下载", "正在释放下载文件。"
        if state == "ready":
            return "更新已下载", "更新包已校验完成，可以重启安装。"
        if state == "failed":
            return "更新失败", "无法完成更新操作，请重试。"
        if latest_version:
            return "当前已是最新版本", "当前安装版本已经是最新。"
        return "软件更新", "点击下方按钮检查新版本。"

    def _sync_progress(self, state: str, done: int, total: int) -> None:
        visible = state in self.DOWNLOAD_STATES
        self.progress_container.setVisible(visible)
        if not visible:
            return
        if total > 0:
            percentage = min(100, int(done * 100 / total))
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(percentage)
            self.progress_detail.setText(
                f"{self._format_bytes(done)} / {self._format_bytes(total)}"
            )
        else:
            self.progress_bar.setRange(0, 0)
            self.progress_detail.setText("正在获取下载大小...")

    @staticmethod
    def _format_bytes(value: int) -> str:
        size = float(max(0, value))
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024 or unit == "GB":
                return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
            size /= 1024
        return f"{int(value)} B"

    def _configure_actions(self, state: str) -> None:
        self.secondary_button.setEnabled(True)
        self.primary_button.setEnabled(True)
        if state == "checking":
            self.secondary_button.hide()
            self.primary_button.setText("正在检查·")
            self.primary_button.setEnabled(False)
        elif state == "available":
            self.secondary_button.hide()
            self.primary_button.setText("下载更新")
        elif state in {"downloading", "retrying"}:
            self.secondary_button.setText("取消下载")
            self.secondary_button.show()
            self.primary_button.setText("暂停下载")
        elif state in {"verifying", "pausing", "cancelling"}:
            self.secondary_button.setText("取消下载")
            self.secondary_button.show()
            self.secondary_button.setEnabled(False)
            self.primary_button.setText("处理中...")
            self.primary_button.setEnabled(False)
        elif state == "paused":
            self.secondary_button.setText("取消下载")
            self.secondary_button.show()
            self.primary_button.setText("继续下载")
        elif state == "ready":
            self.secondary_button.setText("稍后")
            self.secondary_button.show()
            self.primary_button.setText("重启更新")
        elif state == "failed":
            self.secondary_button.hide()
            self.primary_button.setText(
                "重新下载" if self._can_download else "重新检查"
            )
        else:
            self.secondary_button.hide()
            self.primary_button.setText("检查更新")

    def set_checking_step(self, step: int) -> None:
        if self._state != "checking" or self._confirm_action:
            return
        dots = "·" * ((step % 3) + 1)
        self.primary_button.setText(f"正在检查{dots}")

    def _on_primary_clicked(self) -> None:
        if self._confirm_action == "cancel":
            self._confirm_action = None
            self.cancel_requested.emit()
            return
        if self._confirm_action == "restart":
            self._confirm_action = None
            self.restart_requested.emit()
            return
        if self._state == "available" or (
            self._state == "failed" and self._can_download
        ):
            self.download_requested.emit()
        elif self._state in {"downloading", "retrying"}:
            self.pause_requested.emit()
        elif self._state == "paused":
            self.resume_requested.emit()
        elif self._state == "ready":
            self._show_confirmation("restart")
        elif self._state not in {"checking", "verifying", "pausing", "cancelling"}:
            self.check_requested.emit()

    def _on_secondary_clicked(self) -> None:
        if self._confirm_action:
            self._confirm_action = None
            title, fallback = self._state_copy(
                self._state,
                self.latest_version_value.text().lstrip("v"),
            )
            self.title_label.setText(title)
            self.status_label.setText(fallback)
            self._configure_actions(self._state)
            return
        if self._state in {"downloading", "retrying", "paused"}:
            self._show_confirmation("cancel")
        elif self._state == "ready":
            self.hide()

    def _show_confirmation(self, action: str) -> None:
        self._confirm_action = action
        if action == "cancel":
            self.title_label.setText("取消更新下载？")
            self.status_label.setText("已下载的内容将被删除，下次需要重新下载。")
            self.primary_button.setText("确认取消")
        else:
            self.title_label.setText("重启并安装更新？")
            self.status_label.setText("程序将关闭并完成更新安装。")
            self.primary_button.setText("确认重启")
        self.primary_button.setEnabled(True)
        self.secondary_button.setText("返回")
        self.secondary_button.setEnabled(True)
        self.secondary_button.show()

    def show_anchored(self, anchor: QWidget) -> None:
        """优先贴着版本按钮上方向上展开，并限制在当前屏幕内。"""
        self.apply_theme()
        self.adjustSize()
        anchor_top_left = anchor.mapToGlobal(anchor.rect().topLeft())
        anchor_bottom_right = anchor.mapToGlobal(anchor.rect().bottomRight())
        screen = anchor.screen() or QApplication.screenAt(anchor_top_left)
        available = screen.availableGeometry() if screen else QApplication.primaryScreen().availableGeometry()
        x = anchor_bottom_right.x() - self.width()
        y = anchor_top_left.y() - self.height() - 8
        if y < available.top():
            y = anchor_bottom_right.y() + 8
        x = max(available.left() + 8, min(x, available.right() - self.width() - 8))
        y = max(available.top() + 8, min(y, available.bottom() - self.height() - 8))
        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()

    def apply_theme(self) -> None:
        c = default_theme.colors
        self.setStyleSheet(f"""
            QFrame#updateCenterPopover {{
                background: {c.BACKGROUND_CARD};
                border: 1px solid {c.BORDER_MEDIUM};
                border-radius: 12px;
            }}
            QLabel {{
                color: {c.TEXT_PRIMARY};
                border: none;
                background: transparent;
            }}
            QLabel#updatePopoverTitle {{
                font-size: 15px;
                font-weight: 700;
            }}
            QLabel#updatePopoverStatus,
            QLabel#updateVersionKey,
            QLabel#updateProgressDetail {{
                color: {c.TEXT_SECONDARY};
                font-size: 12px;
            }}
            QLabel#updateVersionValue {{
                font-size: 13px;
                font-weight: 650;
            }}
            QFrame#updateVersionPanel {{
                background: {c.BACKGROUND_SECONDARY};
                border: 1px solid {c.BORDER_LIGHT};
                border-radius: 8px;
            }}
            QProgressBar {{
                border: none;
                border-radius: 4px;
                background: {c.BACKGROUND_PRESSED};
                color: transparent;
            }}
            QProgressBar::chunk {{
                border-radius: 4px;
                background: {c.PRIMARY};
            }}
            QPushButton {{
                min-width: 84px;
                padding: 0 13px;
                border-radius: 7px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton#updatePrimaryButton {{
                color: {c.TEXT_ON_PRIMARY};
                background: {c.PRIMARY};
                border: 1px solid {c.PRIMARY};
            }}
            QPushButton#updatePrimaryButton:hover {{
                background: {c.PRIMARY_DARK};
            }}
            QPushButton#updatePrimaryButton:disabled {{
                color: {c.TEXT_DISABLED};
                background: {c.BACKGROUND_PRESSED};
                border-color: {c.BORDER_LIGHT};
            }}
            QPushButton#updateSecondaryButton {{
                color: {c.TEXT_PRIMARY};
                background: {c.BACKGROUND_CARD};
                border: 1px solid {c.BORDER_MEDIUM};
            }}
            QPushButton#updateSecondaryButton:hover {{
                background: {c.BACKGROUND_HOVER};
            }}
        """)
        self._apply_state_color(self._state)

    def _apply_state_color(self, state: str) -> None:
        c = default_theme.colors
        if state == "ready":
            color = c.SUCCESS
        elif state in {"available", "paused", "pausing"}:
            color = c.WARNING
        elif state == "failed":
            color = c.ERROR
        elif state in {"checking", "downloading", "retrying", "verifying"}:
            color = c.PRIMARY
        else:
            color = c.TEXT_DISABLED
        self.status_dot.setStyleSheet(
            f"background: {color}; border: none; border-radius: 6px;"
        )
