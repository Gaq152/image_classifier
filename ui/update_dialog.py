"""
更新对话框模块

包含更新信息展示和下载功能
"""

import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                            QPushButton, QProgressBar, QApplication, QTextEdit, QMessageBox)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QPixmap
from core.update_utils import download_with_progress, sha256_file, launch_self_update
from utils.paths import get_update_dir
from .components.toast import toast_error
from .components.styles.theme import default_theme
from utils.app_config import get_app_config


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
            sha256 = str(self.manifest.get('sha256', '')).strip()

            if not url:
                toast_error(self, "下载链接无效")
                return

            # 使用update目录
            update_dir = get_update_dir()
            update_dir.mkdir(parents=True, exist_ok=True)
            dest = update_dir / f"ImageClassifier_v{self.new_version}.exe"

            # 创建下载进度对话框
            progress_dialog = DownloadProgressDialog(self)
            progress_dialog.show()
            QApplication.processEvents()

            def on_progress(done: int, total: Optional[int]):
                if total and total > 0:
                    progress_dialog.update_progress(done, total)
                QApplication.processEvents()

            try:
                # 下载文件
                download_with_progress(url, dest, self.token or None, on_progress)
            finally:
                progress_dialog.close()

            # 校验SHA256（在下载对话框中显示进度）
            if sha256:
                self.logger.info(f"开始校验SHA256: {sha256}")

                # 重新创建校验进度对话框
                verify_dialog = DownloadProgressDialog(self)
                verify_dialog.set_verifying_mode()
                verify_dialog.show()
                QApplication.processEvents()

                try:
                    actual = sha256_file(dest)
                    verify_dialog.close()

                    if actual.lower() != sha256.lower():
                        toast_error(self, f"文件校验失败")
                        self.logger.error(f"SHA256校验失败: 期望{sha256}, 实际{actual}")
                        try:
                            dest.unlink(missing_ok=True)
                        except Exception:
                            pass
                        return
                    else:
                        self.logger.info("SHA256校验成功")
                except Exception as e:
                    verify_dialog.close()
                    self.logger.error(f"校验过程中出错: {e}")
                    toast_error(self, f"校验失败: {str(e)}")
                    return

            # 询问用户是否立即重启
            exe_path = Path(sys.executable)
            batch_path = launch_self_update(exe_path, dest)

            # 创建自定义中文按钮的消息框
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle('更新完成')
            msg_box.setText('文件下载和校验完成，是否现在重启应用以完成更新？')
            msg_box.setIcon(QMessageBox.Icon.Question)

            # 应用主题适配样式
            config = get_app_config()
            default_theme.set_theme(config.theme)
            c = default_theme.colors
            msg_box.setStyleSheet(f"""
                QMessageBox {{
                    background-color: {c.BACKGROUND_PRIMARY};
                    color: {c.TEXT_PRIMARY};
                    border: 1px solid {c.BORDER_MEDIUM};
                    border-radius: 8px;
                    font-size: 14px;
                    min-width: 400px;
                }}
                QMessageBox QLabel {{
                    color: {c.TEXT_PRIMARY};
                    font-size: 14px;
                    padding: 10px;
                }}
                QPushButton {{
                    background-color: {c.PRIMARY};
                    color: white;
                    border: none;
                    border-radius: 6px;
                    padding: 10px 24px;
                    font-size: 14px;
                    font-weight: bold;
                    min-width: 100px;
                    min-height: 36px;
                }}
                QPushButton:hover {{ background-color: {c.PRIMARY_DARK}; }}
                QPushButton:pressed {{ background-color: {c.PRIMARY_DARK}; }}
            """)

            # 创建中文按钮
            yes_button = msg_box.addButton('是', QMessageBox.ButtonRole.YesRole)
            no_button = msg_box.addButton('否', QMessageBox.ButtonRole.NoRole)
            msg_box.setDefaultButton(yes_button)

            msg_box.exec()
            clicked_button = msg_box.clickedButton()

            if clicked_button == yes_button:
                # 用户选择立即重启
                self.logger.info(f"启动批处理脚本: {batch_path}")
                subprocess.Popen(["cmd", "/c", "start", "", str(batch_path), str(dest)], shell=False)
                self.logger.info("用户选择立即重启安装更新")
                # 关闭对话框
                self.accept()
                QApplication.quit()
            else:
                # 用户选择稍后重启
                self.logger.info("用户选择稍后安装更新包")

                info_box = QMessageBox(self)
                info_box.setWindowTitle('稍后安装')
                info_box.setText('更新包已下载完成，您可以在稍后方便的时候手动安装。\n'
                                 '更新文件已保存到更新目录，下次启动时会提示您安装。')
                info_box.setIcon(QMessageBox.Icon.Information)

                # 应用主题适配样式
                config = get_app_config()
                default_theme.set_theme(config.theme)
                c = default_theme.colors
                info_box.setStyleSheet(f"""
                    QMessageBox {{
                        background-color: {c.BACKGROUND_PRIMARY};
                        color: {c.TEXT_PRIMARY};
                        border: 1px solid {c.BORDER_MEDIUM};
                        border-radius: 8px;
                        font-size: 14px;
                        min-width: 400px;
                    }}
                    QMessageBox QLabel {{
                        color: {c.TEXT_PRIMARY};
                        font-size: 14px;
                        padding: 10px;
                    }}
                    QPushButton {{
                        background-color: {c.PRIMARY};
                        color: white;
                        border: none;
                        border-radius: 6px;
                        padding: 10px 24px;
                        font-size: 14px;
                        font-weight: bold;
                        min-width: 100px;
                        min-height: 36px;
                    }}
                    QPushButton:hover {{ background-color: {c.PRIMARY_DARK}; }}
                    QPushButton:pressed {{ background-color: {c.PRIMARY_DARK}; }}
                """)

                info_box.addButton('确定', QMessageBox.ButtonRole.AcceptRole)
                info_box.exec()

                # 关闭对话框
                self.accept()

        except Exception as e:
            self.logger.error(f"下载更新失败: {e}")
            toast_error(self, f"下载失败: {str(e)}")
            # 关闭对话框（即使出错也关闭）
            self.reject()


class DownloadProgressDialog(QDialog):
    """下载进度对话框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("下载更新")
        self.setModal(True)
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

    def update_progress(self, done: int, total: int):
        """更新进度"""
        if total > 0:
            percentage = int((done / total) * 100)
            self.progress_bar.setValue(percentage)
            done_mb = done / 1024 / 1024
            total_mb = total / 1024 / 1024
            self.label.setText(f"正在下载: {done_mb:.1f} MB / {total_mb:.1f} MB")

    def set_verifying_mode(self):
        """设置为校验模式，显示不确定进度"""
        self.progress_bar.setRange(0, 0)  # 不确定进度模式
        self.label.setText("正在校验文件完整性...")
        self.setWindowTitle("校验文件")
