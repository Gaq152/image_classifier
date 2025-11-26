"""
增强的图像显示组件模块

包含EnhancedImageLabel类，提供图像缩放、拖拽、信息面板等高级功能。
"""

import logging
import math
import os
from datetime import datetime
from pathlib import Path
from PyQt6.QtWidgets import (QLabel, QVBoxLayout, QHBoxLayout, QFrame, QPushButton,
                            QTextEdit, QApplication)
from PyQt6.QtCore import Qt, QTimer, QPoint, QFileInfo
from PyQt6.QtGui import QPixmap, QPainter, QFont

from ..toast import toast_floating
from ..styles import apply_enhanced_image_label_style
from ..styles.widget_styles import WidgetStyles
from ....utils.app_config import get_app_config


class EnhancedImageLabel(QLabel):
    """增强的图像显示组件，支持缩放和拖拽"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(300, 200)
        apply_enhanced_image_label_style(self)

        # 从配置中读取缩放限制
        app_config = get_app_config()

        self.original_pixmap = None
        self.scale_factor = 1.0
        self.min_scale = app_config.image_zoom_min  # 从配置读取最小缩放
        self.max_scale = app_config.image_zoom_max  # 从配置读取最大缩放
        self.scale_step = 0.2  # 增大缩放步长，减少细微调整
        self._fit_to_window_mode = True  # 默认适应窗口模式

        # 拖拽相关
        self.dragging = False
        self.last_pan_point = None
        self.image_offset = QPoint(0, 0)  # 使用QPoint更精确
        self.drag_threshold = 3  # 拖拽阈值，避免误触

        # 启用鼠标追踪，用于拖拽
        self.setMouseTracking(True)

        # 创建信息按钮
        self.create_info_button()

        # 创建状态标记
        self.create_status_badge()

        # 防抖定时器（用于延迟保存缩放配置）
        self.zoom_save_timer = QTimer()
        self.zoom_save_timer.setSingleShot(True)
        self.zoom_save_timer.timeout.connect(self._do_save_zoom)

        self.logger = logging.getLogger(__name__)

    def _save_current_zoom(self):
        """延迟保存当前缩放倍数（使用防抖机制）"""
        # 重启防抖定时器（500ms后保存）
        self.zoom_save_timer.stop()
        self.zoom_save_timer.start(500)

    def _do_save_zoom(self):
        """实际保存缩放倍数到配置（防抖定时器触发）"""
        try:
            app_config = get_app_config()
            # 直接更新内存中的值，绕过 setter 避免立即写入磁盘
            app_config._config["last_zoom_factor"] = self.scale_factor
            # 保存到磁盘
            app_config._save_config()
            self.logger.debug(f"已保存缩放倍数: {self.scale_factor:.2f}x")
        except Exception as e:
            self.logger.error(f"保存缩放倍数失败: {e}")

    def create_info_button(self):
        """创建信息按钮"""
        try:

            # 创建圆形信息按钮
            self.info_button = QPushButton("ℹ️", self)
            self.info_button.setFixedSize(30, 30)

            # 使用主题样式
            self.info_button.setStyleSheet(WidgetStyles.get_info_button_style())

            # 设置提示文本
            self.info_button.setToolTip("点击查看图片详细信息")

            # 连接点击事件
            self.info_button.clicked.connect(self.show_image_info_panel)

            # 初始位置（右上角）
            self.position_info_button()

        except Exception as e:
            self.logger.error(f"创建信息按钮失败: {e}")

    def position_info_button(self):
        """定位信息按钮到右上角"""
        try:
            if hasattr(self, 'info_button') and self.info_button:
                x = self.width() - self.info_button.width() - 10
                y = 10
                self.info_button.move(x, y)
        except Exception as e:
            self.logger.debug(f"定位信息按钮失败: {e}")

    def create_status_badge(self):
        """创建状态标记"""
        try:

            # 创建状态标签
            self.status_badge = QLabel("", self)
            self.status_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.status_badge.setStyleSheet("""
                QLabel {
                    background-color: rgba(76, 175, 80, 230);
                    color: white;
                    padding: 4px 10px;
                    border-radius: 4px;
                    font-size: 12px;
                    font-weight: bold;
                }
            """)

            # 初始隐藏
            self.status_badge.hide()

            # 定位到左上角
            self.position_status_badge()

        except Exception as e:
            self.logger.error(f"创建状态标记失败: {e}")

    def position_status_badge(self):
        """定位状态标记到左上角"""
        try:
            if hasattr(self, 'status_badge') and self.status_badge:
                x = 10
                y = 10
                self.status_badge.move(x, y)
        except Exception as e:
            self.logger.debug(f"定位状态标记失败: {e}")

    def update_status_badge(self):
        """更新状态标记显示"""
        try:
            if not hasattr(self, 'status_badge'):
                return

            # 获取主窗口
            main_window = self.parent()
            while main_window and not hasattr(main_window, 'image_files'):
                main_window = main_window.parent()

            if not main_window or not hasattr(main_window, 'image_files') or not main_window.image_files:
                self.status_badge.hide()
                return

            if main_window.current_index < 0 or main_window.current_index >= len(main_window.image_files):
                self.status_badge.hide()
                return

            current_image_path = str(main_window.image_files[main_window.current_index])

            # 获取分类状态
            classification = main_window.classified_images.get(current_image_path)
            is_removed = current_image_path in main_window.removed_images

            if is_removed:
                # 已移除
                self.status_badge.setText("🗑 已移除")
                self.status_badge.setStyleSheet("""
                    QLabel {
                        background-color: rgba(239, 68, 68, 230);
                        color: white;
                        padding: 4px 10px;
                        border-radius: 4px;
                        font-size: 12px;
                        font-weight: bold;
                    }
                """)
                self.status_badge.adjustSize()
                self.status_badge.show()
            elif classification:
                if isinstance(classification, list) and len(classification) > 0:
                    # 多分类：显示类别列表（换行展示）
                    categories_text = "📁 " + "\n".join(classification)
                    self.status_badge.setText(categories_text)
                    self.status_badge.setStyleSheet("""
                        QLabel {
                            background-color: rgba(59, 130, 246, 230);
                            color: white;
                            padding: 6px 10px;
                            border-radius: 4px;
                            font-size: 11px;
                            font-weight: bold;
                            line-height: 1.4;
                        }
                    """)
                    self.status_badge.adjustSize()
                    self.status_badge.show()
                elif isinstance(classification, str):
                    # 单分类：显示类别名称
                    self.status_badge.setText(f"📁 {classification}")
                    self.status_badge.setStyleSheet("""
                        QLabel {
                            background-color: rgba(59, 130, 246, 230);
                            color: white;
                            padding: 6px 10px;
                            border-radius: 4px;
                            font-size: 11px;
                            font-weight: bold;
                        }
                    """)
                    self.status_badge.adjustSize()
                    self.status_badge.show()
                else:
                    # 空分类或异常
                    self.status_badge.hide()
            else:
                # 未处理
                self.status_badge.hide()

        except Exception as e:
            self.logger.error(f"更新状态标记失败: {e}")

    def set_image(self, pixmap):
        """设置图像"""
        try:
            if pixmap and not pixmap.isNull():
                self.original_pixmap = pixmap
                self.image_offset = QPoint(0, 0)

                # 检查是否应用全局缩放倍数
                app_config = get_app_config()

                if app_config.global_zoom_enabled and app_config.last_zoom_factor != 1.0:
                    # 应用保存的缩放倍数
                    self.scale_factor = app_config.last_zoom_factor
                    self._fit_to_window_mode = False
                    self.update_display()
                    self.logger.debug(f"应用全局缩放倍数: {self.scale_factor:.2f}x")
                else:
                    # 使用默认的适应窗口模式
                    self.scale_factor = 1.0
                    self._fit_to_window_mode = True
                    self.fit_to_window()

                # 更新信息面板内容（如果存在且可见）
                if hasattr(self, 'info_panel') and self.info_panel and self.info_panel.isVisible():
                    QTimer.singleShot(100, self.update_info_panel)

                # 更新状态标记
                QTimer.singleShot(50, self.update_status_badge)
            else:
                self.clear()
                self.original_pixmap = None

                # 隐藏信息面板（如果没有图片）
                if hasattr(self, 'info_panel') and self.info_panel:
                    self.info_panel.hide()

                # 隐藏状态标记
                if hasattr(self, 'status_badge'):
                    self.status_badge.hide()

        except Exception as e:
            self.logger.error(f"设置图像失败: {e}")

    def fit_to_window(self):
        """适应窗口大小"""
        if not self.original_pixmap:
            return

        try:
            label_size = self.size()
            pixmap_size = self.original_pixmap.size()

            # 计算缩放比例
            scale_x = label_size.width() / pixmap_size.width()
            scale_y = label_size.height() / pixmap_size.height()
            self.scale_factor = min(scale_x, scale_y, self.max_scale)  # 允许放大，但不超过最大缩放倍数

            # 重置偏移
            self.image_offset = QPoint(0, 0)
            self._fit_to_window_mode = True

            self.update_display()
            # 更新信息面板中的缩放信息
            if hasattr(self, 'info_panel') and self.info_panel and self.info_panel.isVisible():
                QTimer.singleShot(50, self.update_info_panel)
        except Exception as e:
            self.logger.error(f"适应窗口失败: {e}")

    def zoom_in(self):
        """放大"""
        if self.scale_factor >= self.max_scale:
            self.logger.info("已达到最大缩放倍数，停止放大防止卡顿")
            toast_floating(self, f"📈 已达到最大缩放倍数 ({self.max_scale:.1f}x)，可在设置中修改", 3000)
            return

        self._fit_to_window_mode = False  # 手动缩放时退出适应窗口模式
        self.scale_factor = min(self.scale_factor + self.scale_step, self.max_scale)
        self.update_display()
        self._save_current_zoom()  # 保存缩放倍数
        # 更新信息面板中的缩放信息
        if hasattr(self, 'info_panel') and self.info_panel and self.info_panel.isVisible():
            QTimer.singleShot(50, self.update_info_panel)

    def zoom_out(self):
        """缩小"""
        if self.scale_factor <= self.min_scale:
            toast_floating(self, f"📉 已达到最小缩放倍数 ({self.min_scale:.2f}x)", 3000)
            return

        self._fit_to_window_mode = False  # 手动缩放时退出适应窗口模式
        self.scale_factor = max(self.scale_factor - self.scale_step, self.min_scale)
        self.update_display()
        self._save_current_zoom()  # 保存缩放倍数
        # 更新信息面板中的缩放信息
        if hasattr(self, 'info_panel') and self.info_panel and self.info_panel.isVisible():
            QTimer.singleShot(50, self.update_info_panel)

    def reset_zoom(self):
        """重置缩放"""
        self.scale_factor = 1.0
        self.image_offset = QPoint(0, 0)
        self._fit_to_window_mode = True  # 重置时回到适应窗口模式
        self._save_current_zoom()  # 保存缩放倍数（重置为1.0）
        self.fit_to_window()

    def scale_image(self, factor):
        """缩放图像"""
        try:
            self._fit_to_window_mode = False  # 手动缩放时退出适应窗口模式
            new_scale = self.scale_factor * factor

            # 限制缩放范围，防止过度放大导致卡顿
            if new_scale > self.max_scale:
                self.logger.info(f"缩放倍数 {new_scale:.1f} 超过限制 {self.max_scale}，已限制")
                toast_floating(self, f"📈 已达到最大缩放倍数 ({self.max_scale:.1f}x)，可在设置中修改", 3000)
                new_scale = self.max_scale

            self.scale_factor = max(self.min_scale, min(new_scale, self.max_scale))
            self.update_display()
            self._save_current_zoom()  # 保存缩放倍数
            # 更新信息面板中的缩放信息
            if hasattr(self, 'info_panel') and self.info_panel and self.info_panel.isVisible():
                QTimer.singleShot(50, self.update_info_panel)
        except Exception as e:
            self.logger.error(f"缩放图像失败: {e}")

    def update_display(self):
        """更新显示 - 支持拖拽偏移"""
        if not self.original_pixmap:
            return

        try:
            # 缩放图像
            scaled_size = self.original_pixmap.size() * self.scale_factor
            scaled_pixmap = self.original_pixmap.scaled(
                scaled_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )

            # 如果有拖拽偏移，创建带偏移的显示
            if self.image_offset.x() != 0 or self.image_offset.y() != 0:
                # 创建更大的画布来容纳偏移
                canvas_size = self.size()
                canvas = QPixmap(canvas_size)
                canvas.fill(Qt.GlobalColor.transparent)

                painter = QPainter(canvas)
                try:
                    # 计算居中位置加上偏移
                    x = (canvas_size.width() - scaled_pixmap.width()) // 2 + self.image_offset.x()
                    y = (canvas_size.height() - scaled_pixmap.height()) // 2 + self.image_offset.y()

                    painter.drawPixmap(x, y, scaled_pixmap)
                finally:
                    painter.end()

                self.setPixmap(canvas)
            else:
                self.setPixmap(scaled_pixmap)

        except Exception as e:
            self.logger.error(f"更新显示失败: {e}")

    def wheelEvent(self, event):
        """处理鼠标滚轮事件 - 优化缩放响应"""
        try:
            # 检查是否按住Ctrl键进行精细缩放
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                # 精细缩放模式
                scale_step = 0.05
            else:
                scale_step = self.scale_step

            if event.angleDelta().y() > 0:
                # 向上滚动 - 放大
                if self.scale_factor < self.max_scale:
                    self._fit_to_window_mode = False
                    self.scale_factor = min(self.scale_factor + scale_step, self.max_scale)
                    self.update_display()
                    self._save_current_zoom()  # 保存缩放倍数
                    # 更新信息面板中的缩放信息
                    if hasattr(self, 'info_panel') and self.info_panel and self.info_panel.isVisible():
                        QTimer.singleShot(50, self.update_info_panel)
                else:
                    # 已达到最大缩放，显示提示
                    toast_floating(self, f"📈 已达到最大缩放倍数 ({self.max_scale:.1f}x)，可在设置中修改", 3000)
            else:
                # 向下滚动 - 缩小
                if self.scale_factor > self.min_scale:
                    self._fit_to_window_mode = False
                    self.scale_factor = max(self.scale_factor - scale_step, self.min_scale)
                    self.update_display()
                    self._save_current_zoom()  # 保存缩放倍数
                    # 更新信息面板中的缩放信息
                    if hasattr(self, 'info_panel') and self.info_panel and self.info_panel.isVisible():
                        QTimer.singleShot(50, self.update_info_panel)
                else:
                    # 已达到最小缩放，显示提示
                    toast_floating(self, f"📉 已达到最小缩放倍数 ({self.min_scale:.2f}x)", 3000)

        except Exception as e:
            self.logger.error(f"滚轮事件处理失败: {e}")

    def mousePressEvent(self, event):
        """处理鼠标按下事件 - 开始拖拽或关闭信息面板"""
        try:
            if event.button() == Qt.MouseButton.LeftButton:
                # 检查是否点击了信息面板区域或信息按钮
                if hasattr(self, 'info_panel') and self.info_panel and self.info_panel.isVisible():
                    panel_rect = self.info_panel.geometry()
                    click_pos = event.position().toPoint()

                    # 检查是否点击了信息按钮
                    if hasattr(self, 'info_button') and self.info_button:
                        button_rect = self.info_button.geometry()
                        if button_rect.contains(click_pos):
                            # 点击了信息按钮，不处理拖拽，让按钮事件处理
                            return

                    # 如果点击在面板外部（且不是信息按钮），隐藏面板
                    if not panel_rect.contains(click_pos):
                        self.info_panel.hide()
                        return

                # 允许在任何缩放级别下拖拽图片
                self.dragging = True
                self.last_pan_point = event.position().toPoint()
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
        except Exception as e:
            self.logger.error(f"鼠标按下事件处理失败: {e}")

    def mouseMoveEvent(self, event):
        """处理鼠标移动事件 - 拖拽图片"""
        try:
            if self.dragging and self.last_pan_point:
                current_point = event.position().toPoint()
                delta = current_point - self.last_pan_point

                # 只有在移动距离超过阈值时才开始拖拽
                if (abs(delta.x()) > self.drag_threshold or
                    abs(delta.y()) > self.drag_threshold):

                    self.image_offset += delta
                    self.last_pan_point = current_point
                    self.update_display()
            else:
                # 在任何缩放级别下都显示可拖拽光标
                self.setCursor(Qt.CursorShape.OpenHandCursor)

        except Exception as e:
            self.logger.error(f"鼠标移动事件处理失败: {e}")

    def mouseReleaseEvent(self, event):
        """处理鼠标释放事件 - 结束拖拽"""
        try:
            if event.button() == Qt.MouseButton.LeftButton:
                self.dragging = False
                self.last_pan_point = None

                # 恢复可拖拽光标
                self.setCursor(Qt.CursorShape.OpenHandCursor)
        except Exception as e:
            self.logger.error(f"鼠标释放事件处理失败: {e}")

    def resizeEvent(self, event):
        """处理窗口大小改变事件"""
        super().resizeEvent(event)
        # 只在适应窗口模式下自动调整
        if self.original_pixmap and self._fit_to_window_mode:
            # 延迟调整，避免频繁刷新
            QTimer.singleShot(50, self.fit_to_window)

        # 重新定位信息按钮、面板和状态标记
        QTimer.singleShot(10, self.position_info_button)
        QTimer.singleShot(10, self.position_info_panel)
        QTimer.singleShot(10, self.position_status_badge)

    def show_image_info_panel(self):
        """显示图片信息面板"""
        try:
            if hasattr(self, 'info_panel') and self.info_panel:
                # 如果面板已存在，切换显示状态
                if self.info_panel.isVisible():
                    self.info_panel.hide()
                else:
                    self.update_info_panel()
                    self.info_panel.show()
            else:
                # 创建新的信息面板
                self.create_info_panel()

        except Exception as e:
            self.logger.error(f"显示图片信息面板失败: {e}")

    def create_info_panel(self):
        """创建图片信息面板"""
        try:

            # 创建半透明面板
            self.info_panel = QFrame(self)
            self.info_panel.setFixedWidth(450)
            self.info_panel.setStyleSheet("""
                QFrame {
                    background-color: rgba(0, 0, 0, 180);
                    border-radius: 8px;
                    border: 1px solid rgba(255, 255, 255, 50);
                }
                QLabel {
                    color: white;
                    background: transparent;
                    font-size: 12px;
                    padding: 2px 8px;
                }
                QLabel[objectName="info_title"] {
                    font-size: 14px;
                    font-weight: bold;
                    color: #4CAF50;
                    border-bottom: 1px solid rgba(255, 255, 255, 30);
                    margin-bottom: 5px;
                }
                QPushButton {
                    background-color: rgba(76, 175, 80, 180);
                    color: white;
                    border: none;
                    border-radius: 4px;
                    padding: 4px 8px;
                    font-size: 11px;
                    margin: 2px;
                }
                QPushButton:hover {
                    background-color: rgba(76, 175, 80, 220);
                }
            """)

            layout = QVBoxLayout(self.info_panel)
            layout.setContentsMargins(10, 10, 10, 10)
            layout.setSpacing(2)

            # 标题
            title_label = QLabel("📷 图片信息")
            title_label.setObjectName("info_title")
            layout.addWidget(title_label)

            # 基本信息标签
            self.info_labels = {}
            info_items = [
                ('filename', '文件名', ''),
                ('size', '文件大小', ''),
                ('dimensions', '图片尺寸', ''),
                ('scale', '当前缩放', ''),
                ('status', '分类状态', ''),
                ('categories', '所属类别', '')
            ]

            for key, title, value in info_items:
                label = QLabel(f"{title}: {value}")
                self.info_labels[key] = label
                layout.addWidget(label)

            # 更多信息按钮
            self.more_info_btn = QPushButton("▼ 更多信息")
            self.more_info_btn.clicked.connect(self.toggle_more_info)
            layout.addWidget(self.more_info_btn)

            # 详细信息区域（默认隐藏）
            self.detailed_info_widget = QFrame()
            self.detailed_info_layout = QVBoxLayout(self.detailed_info_widget)
            self.detailed_info_layout.setContentsMargins(0, 5, 0, 0)

            # 详细信息标签
            self.detailed_labels = {}

            # 特殊处理路径信息（带复制按钮）
            self.create_path_info_widget()

            # 其他详细信息
            other_detailed_items = [
                ('created', '创建时间', ''),
                ('modified', '修改时间', ''),
                ('display_mode', '显示模式', '')
            ]

            for key, title, value in other_detailed_items:
                label = QLabel(f"{title}: {value}")
                label.setWordWrap(True)
                self.detailed_labels[key] = label
                self.detailed_info_layout.addWidget(label)

            self.detailed_info_widget.hide()
            layout.addWidget(self.detailed_info_widget)

            # 设置面板位置（右上角）
            self.position_info_panel()

            # 更新信息并显示
            self.update_info_panel()
            self.info_panel.show()

        except Exception as e:
            self.logger.error(f"创建图片信息面板失败: {e}")

    def position_info_panel(self):
        """定位信息面板到右上角"""
        try:
            if hasattr(self, 'info_panel') and self.info_panel:
                panel_width = self.info_panel.width()
                x = self.width() - panel_width - 10
                y = 10
                self.info_panel.move(x, y)
        except Exception as e:
            self.logger.debug(f"定位信息面板失败: {e}")

    def toggle_more_info(self):
        """切换更多信息显示"""
        try:
            if self.detailed_info_widget.isVisible():
                self.detailed_info_widget.hide()
                self.more_info_btn.setText("▼ 更多信息")
                self.info_panel.setFixedHeight(self.info_panel.sizeHint().height())
            else:
                self.detailed_info_widget.show()
                self.more_info_btn.setText("▲ 收起")
                self.info_panel.setFixedHeight(self.info_panel.sizeHint().height())
        except Exception as e:
            self.logger.error(f"切换更多信息失败: {e}")

    def update_info_panel(self):
        """更新信息面板内容"""
        try:
            if not hasattr(self, 'info_panel') or not self.info_panel:
                return

            # 获取当前图片信息
            main_window = self.parent()
            while main_window and not hasattr(main_window, 'image_files'):
                main_window = main_window.parent()

            if not main_window or not hasattr(main_window, 'image_files') or not main_window.image_files:
                return

            if main_window.current_index < 0 or main_window.current_index >= len(main_window.image_files):
                return

            current_image_path = main_window.image_files[main_window.current_index]


            # 收集图片信息
            file_info = QFileInfo(str(current_image_path))
            file_stats = os.stat(str(current_image_path))

            # 更新基本信息
            self.info_labels['filename'].setText(f"文件名: {file_info.fileName()}")
            self.info_labels['size'].setText(f"文件大小: {self.format_file_size(file_stats.st_size)}")

            # 图片尺寸
            if self.original_pixmap:
                width = self.original_pixmap.width()
                height = self.original_pixmap.height()
                self.info_labels['dimensions'].setText(f"图片尺寸: {width} × {height}")
            else:
                self.info_labels['dimensions'].setText("图片尺寸: 未知")

            # 当前缩放
            self.info_labels['scale'].setText(f"当前缩放: {self.scale_factor:.2f}x")

            # 分类状态
            image_path_str = str(current_image_path)
            classification = main_window.classified_images.get(image_path_str)
            is_removed = image_path_str in main_window.removed_images

            if is_removed:
                self.info_labels['status'].setText("分类状态: 已移出")
                self.info_labels['categories'].setText("所属类别: 无")
            elif classification:
                if isinstance(classification, list) and len(classification) > 0:
                    # 多分类情况：显示已分类，类别显示所有类别名称
                    self.info_labels['status'].setText("分类状态: 已分类")
                    categories = ', '.join(classification)
                    self.info_labels['categories'].setText(f"所属类别: {categories}")
                elif isinstance(classification, str):
                    # 单分类情况：显示已分类，类别显示具体类别名称
                    self.info_labels['status'].setText("分类状态: 已分类")
                    self.info_labels['categories'].setText(f"所属类别: {classification}")
                else:
                    # 空列表或其他异常情况
                    self.info_labels['status'].setText("分类状态: 未处理")
                    self.info_labels['categories'].setText("所属类别: 无")
            else:
                self.info_labels['status'].setText("分类状态: 未处理")
                self.info_labels['categories'].setText("所属类别: 无")

            # 更新详细信息
            # 更新路径信息（使用QTextEdit）
            if hasattr(self, 'path_text_edit'):
                self.path_text_edit.setPlainText(file_info.absoluteFilePath())

            # 更新其他详细信息
            self.detailed_labels['created'].setText(f"创建时间: {datetime.fromtimestamp(file_stats.st_ctime).strftime('%Y-%m-%d %H:%M:%S')}")
            self.detailed_labels['modified'].setText(f"修改时间: {datetime.fromtimestamp(file_stats.st_mtime).strftime('%Y-%m-%d %H:%M:%S')}")
            self.detailed_labels['display_mode'].setText(f"显示模式: {'适应窗口' if self._fit_to_window_mode else '自由缩放'}")

        except Exception as e:
            self.logger.error(f"更新信息面板失败: {e}")

    def format_file_size(self, size_bytes):
        """格式化文件大小"""
        try:
            if size_bytes == 0:
                return "0 B"
            size_names = ["B", "KB", "MB", "GB"]
            i = int(math.floor(math.log(size_bytes, 1024)))
            p = math.pow(1024, i)
            s = round(size_bytes / p, 2)
            return f"{s} {size_names[i]}"
        except:
            return f"{size_bytes} B"


    def create_path_info_widget(self):
        """创建路径信息组件（带复制按钮）"""
        try:

            # 创建路径信息容器
            path_container = QFrame()
            path_layout = QVBoxLayout(path_container)
            path_layout.setContentsMargins(0, 0, 0, 5)
            path_layout.setSpacing(3)

            # 路径标题
            path_title = QLabel("完整路径:")
            path_title.setStyleSheet("font-weight: bold; color: #4CAF50;")
            path_layout.addWidget(path_title)

            # 路径显示和复制按钮的容器
            path_content_layout = QHBoxLayout()
            path_content_layout.setContentsMargins(0, 0, 0, 0)
            path_content_layout.setSpacing(5)

            # 使用QTextEdit显示路径，支持完整显示和选择
            self.path_text_edit = QTextEdit()
            self.path_text_edit.setMaximumHeight(60)  # 限制高度但允许滚动
            self.path_text_edit.setMinimumHeight(40)
            self.path_text_edit.setReadOnly(True)
            self.path_text_edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            self.path_text_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            self.path_text_edit.setStyleSheet("""
                QTextEdit {
                    background-color: rgba(255, 255, 255, 20);
                    border: 1px solid rgba(255, 255, 255, 50);
                    border-radius: 4px;
                    padding: 4px;
                    font-size: 11px;
                    color: white;
                }
                QTextEdit:focus {
                    border-color: rgba(76, 175, 80, 150);
                }
            """)
            path_content_layout.addWidget(self.path_text_edit, 1)  # 占据大部分空间

            # 复制按钮
            copy_button = QPushButton("📋")
            copy_button.setFixedSize(30, 30)
            copy_button.setToolTip("复制完整路径到剪贴板")
            copy_button.setStyleSheet("""
                QPushButton {
                    background-color: rgba(76, 175, 80, 180);
                    color: white;
                    border: none;
                    border-radius: 4px;
                    font-size: 12px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: rgba(76, 175, 80, 220);
                }
                QPushButton:pressed {
                    background-color: rgba(76, 175, 80, 255);
                }
            """)
            copy_button.clicked.connect(self.copy_path_to_clipboard)
            path_content_layout.addWidget(copy_button)

            path_layout.addLayout(path_content_layout)

            # 将路径容器添加到详细信息布局
            self.detailed_info_layout.addWidget(path_container)

            # 保存引用以便后续更新
            self.path_container = path_container

        except Exception as e:
            self.logger.error(f"创建路径信息组件失败: {e}")

    def copy_path_to_clipboard(self):
        """复制路径到剪贴板"""
        try:
            if hasattr(self, 'path_text_edit'):
                path_text = self.path_text_edit.toPlainText()
                if path_text:
                    clipboard = QApplication.clipboard()
                    clipboard.setText(path_text)
                    # 显示复制成功提示
                    toast_floating(self, "📋 路径已复制到剪贴板", 2000)
                else:
                    toast_floating(self, "❌ 没有路径可复制", 2000)

        except Exception as e:
            self.logger.error(f"复制路径到剪贴板失败: {e}")
            toast_floating(self, "❌ 复制失败", 2000)