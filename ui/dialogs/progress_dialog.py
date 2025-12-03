"""
进度对话框

增强的进度对话框组件，支持取消和详细信息显示。
"""

import logging
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QProgressBar
from PyQt6.QtCore import pyqtSignal
from ..components.styles.theme import default_theme
from ..components.styles import DialogStyles


class ProgressDialog(QDialog):
    """增强的进度对话框，支持取消和详细信息"""
    cancelled = pyqtSignal()

    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(400)
        self.cancelled_flag = False
        self._force_closed = False  # 添加强制关闭标志
        self.logger = logging.getLogger(__name__)

        # 应用主题样式
        c = default_theme.colors

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # 主要进度信息
        self.main_label = QLabel("正在处理...")
        self.main_label.setStyleSheet(f"QLabel {{ color: {c.TEXT_PRIMARY}; font-weight: bold; }}")
        layout.addWidget(self.main_label)

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        layout.addWidget(self.progress_bar)

        # 详细信息
        self.detail_label = QLabel("")
        self.detail_label.setStyleSheet(f"QLabel {{ color: {c.TEXT_SECONDARY}; font-size: 11px; }}")
        layout.addWidget(self.detail_label)

        # 取消按钮
        button_layout = QHBoxLayout()
        self.cancel_button = QPushButton("取消")
        self.cancel_button.clicked.connect(self.cancel_operation)
        button_layout.addStretch()
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)

        # 设置样式
        self.setStyleSheet(f"""
            {DialogStyles.get_base_dialog_style()}
            QLabel {{
                padding: 4px;
            }}
            QProgressBar {{
                text-align: center;
                min-height: 20px;
                border: 1px solid {c.BORDER_MEDIUM};
                border-radius: 10px;
                background-color: {c.BACKGROUND_SECONDARY};
                color: {c.TEXT_PRIMARY};
                font-size: 11px;
                font-weight: bold;
            }}
            QProgressBar::chunk {{
                background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0 {c.SUCCESS}, stop: 1 {c.SUCCESS_DARK});
                border-radius: 8px;
                margin: 1px;
            }}
            QPushButton {{
                padding: 6px 20px;
                background-color: {c.ERROR};
                color: white;
                border: none;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: {c.ERROR_DARK};
            }}
        """)

    def update_progress(self, value, maximum=100):
        """更新进度"""
        try:
            self.progress_bar.setMaximum(maximum)
            self.progress_bar.setValue(value)
        except Exception as e:
            self.logger.error(f"更新进度失败: {e}")

    def update_main_text(self, text):
        """更新主要文本"""
        try:
            self.main_label.setText(text)
        except Exception as e:
            self.logger.error(f"更新主要文本失败: {e}")

    def update_detail_text(self, text):
        """更新详细信息"""
        try:
            self.detail_label.setText(text)
        except Exception as e:
            self.logger.error(f"更新详细信息失败: {e}")

    def cancel_operation(self):
        """取消操作"""
        try:
            self.cancelled_flag = True
            self.cancelled.emit()
            self.cancel_button.setEnabled(False)
            self.cancel_button.setText("正在取消...")
        except Exception as e:
            self.logger.error(f"取消操作失败: {e}")

    def force_close(self):
        """强制关闭对话框"""
        self._force_closed = True
        self.close()

    def is_cancelled(self):
        """检查是否已取消"""
        return self.cancelled_flag

    def closeEvent(self, event):
        """重写关闭事件"""
        if self._force_closed:
            event.accept()
        else:
            # 正常情况下需要等待操作完成
            event.accept()
