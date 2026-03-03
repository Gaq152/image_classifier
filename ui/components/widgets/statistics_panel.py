"""
统计面板组件

显示图像分类统计信息的面板组件，包括进度条和各种状态计数。
"""

import logging
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QGridLayout, QLabel, QProgressBar, QSizePolicy
from PyQt6.QtGui import QPainter, QPainterPath, QColor, QPen, QBrush, QLinearGradient
from PyQt6.QtCore import Qt, QRectF
from ..styles.theme import default_theme


class RoundedProgressBar(QProgressBar):
    """自定义绘制的进度条，解决低进度显示问题

    特点：
    - 所有进度（0-100%）都显示圆角
    - 完全填充容器，无间隙
    - 动态圆角半径，低进度时自动缩小
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTextVisible(True)
        self.setContentsMargins(0, 0, 0, 0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(24)
        # 颜色配置（根据进度百分比变化）
        self._chunk_colors = ("stop: 0 #28A745, stop: 1 #20C997")  # 默认绿色
        # 清空默认样式，完全由自绘控制
        self.setStyleSheet("""
            QProgressBar { border: 0; background: transparent; padding: 0; margin: 0; }
            QProgressBar::chunk { background: transparent; margin: 0; padding: 0; }
        """)

    def setChunkColors(self, color_stops: str):
        """设置进度块颜色（渐变格式）"""
        self._chunk_colors = color_stops
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 获取主题颜色
        c = default_theme.colors

        # 绘制区域（留出0.5px避免边界裁剪）
        rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        radius = rect.height() / 2  # 半圆形圆角

        # 1. 创建容器路径（用于背景和裁剪）
        container_path = QPainterPath()
        container_path.addRoundedRect(rect, radius, radius)

        # 2. 绘制背景
        pen = QPen(QColor("#6C757D"))
        pen.setWidthF(1.0)
        painter.setPen(pen)
        painter.setBrush(QBrush(QColor(c.BACKGROUND_SECONDARY)))
        painter.drawPath(container_path)

        # 3. 绘制进度块（使用 ClipPath 确保不超出边界）
        total = self.maximum() - self.minimum()
        progress = 0 if total <= 0 else (self.value() - self.minimum()) / total
        if progress > 0:
            # 设置裁剪区域为容器形状（关键！防止超出边界）
            painter.setClipPath(container_path)

            chunk_width = rect.width() * progress

            # 解析渐变颜色
            gradient = QLinearGradient(rect.left(), 0, rect.right(), 0)
            if "DC3545" in self._chunk_colors:  # 红色（低进度）
                gradient.setColorAt(0, QColor("#DC3545"))
                gradient.setColorAt(1, QColor("#FF6B6B"))
            elif "FFC107" in self._chunk_colors:  # 黄色（中进度）
                gradient.setColorAt(0, QColor("#FFC107"))
                gradient.setColorAt(1, QColor("#FFD700"))
            elif "17A2B8" in self._chunk_colors:  # 蓝色（较高进度）
                gradient.setColorAt(0, QColor("#17A2B8"))
                gradient.setColorAt(1, QColor("#20C997"))
            else:  # 绿色（高进度/完成）
                gradient.setColorAt(0, QColor("#28A745"))
                gradient.setColorAt(1, QColor("#20C997"))

            # 直接绘制矩形，ClipPath 会自动裁剪成圆角
            chunk_rect = QRectF(rect.left(), rect.top(), chunk_width, rect.height())
            painter.setPen(Qt.PenStyle.NoPen)
            painter.fillRect(chunk_rect, gradient)

            # 取消裁剪
            painter.setClipping(False)

        # 4. 重新绘制边框（确保边框在最上层）
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(container_path)

        # 5. 绘制文本
        if self.isTextVisible():
            percentage = int(progress * 100) if total > 0 else 0
            text = f"{percentage}%"
            painter.setPen(QColor(c.TEXT_PRIMARY))
            font = self.font()
            font.setBold(True)
            font.setPointSize(9)
            painter.setFont(font)
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)


class StatisticsPanel(QWidget):
    """分类统计面板"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)
        self.initUI()

        # 立即调用一次统计更新，确保进度条初始样式正确
        self.update_statistics(0, 0, 0)

    def initUI(self):
        """初始化简洁的UI - 2x2网格布局"""
        try:
            layout = QVBoxLayout(self)
            layout.setContentsMargins(8, 6, 8, 6)
            layout.setSpacing(4)

            # 简化的标题
            title_label = QLabel("📊 统计")
            title_label.setStyleSheet("""
                QLabel {
                    font-size: 13px;
                    font-weight: bold;
                    color: #1565C0;
                    border-bottom: 2px solid #2196F3;
                    padding: 4px 6px;
                    margin-bottom: 4px;
                }
            """)
            layout.addWidget(title_label)

            # 创建2x2网格布局的统计信息
            stats_grid = QGridLayout()
            stats_grid.setContentsMargins(0, 0, 0, 0)
            stats_grid.setSpacing(3)

            # 创建统计标签
            self.total_label = QLabel("📁 总计: 0")
            self.classified_label = QLabel("✅ 已分类: 0")
            self.removed_label = QLabel("🗑️ 已移出: 0")
            self.remaining_label = QLabel("⏳ 待处理: 0")

            # 紧凑的标签样式
            label_style = """
                QLabel {
                    padding: 4px 6px;
                    margin: 1px;
                    font-size: 11px;
                    border-radius: 3px;
                    background-color: #F8F9FA;
                }
            """

            for label in [self.total_label, self.classified_label, self.removed_label, self.remaining_label]:
                label.setStyleSheet(label_style)

            # 按2x2网格排列统计信息
            stats_grid.addWidget(self.total_label, 0, 0)        # 第1行第1列
            stats_grid.addWidget(self.classified_label, 0, 1)   # 第1行第2列
            stats_grid.addWidget(self.removed_label, 1, 0)      # 第2行第1列
            stats_grid.addWidget(self.remaining_label, 1, 1)    # 第2行第2列

            layout.addLayout(stats_grid)

            # 单一进度条（使用自定义绘制的圆角进度条）
            self.progress_bar = RoundedProgressBar()
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)
            layout.addWidget(self.progress_bar)

        except Exception as e:
            self.logger.error(f"初始化统计面板UI失败: {e}")

    def update_statistics(self, total, classified, removed, display_count=None):
        """更新统计信息和进度条"""
        try:
            remaining = total - classified - removed
            processed = classified + removed

            # 更新统计标签
            self.total_label.setText(f"📁 总计: {total}")
            self.classified_label.setText(f"✅ 已分类: {classified}")
            self.removed_label.setText(f"🗑️ 已移出: {removed}")
            self.remaining_label.setText(f"⏳ 待处理: {remaining}")

            if display_count is not None:
                self.total_label.setText(f"📁 总计: {total} (显示: {display_count})")

            # 更新进度条
            if total > 0:
                progress_percentage = int((processed / total) * 100)
                self.progress_bar.setValue(progress_percentage)
                self.progress_bar.setFormat(f"{progress_percentage}%")

                # 根据进度调整颜色（自定义进度条使用 setChunkColors）
                if progress_percentage >= 100:
                    chunk_color = "stop: 0 #28A745, stop: 1 #20C997"  # 绿色 - 完成
                elif progress_percentage >= 75:
                    chunk_color = "stop: 0 #17A2B8, stop: 1 #20C997"  # 青色 - 接近完成
                elif progress_percentage >= 50:
                    chunk_color = "stop: 0 #FFC107, stop: 1 #FFD700"  # 黄色 - 进行中
                else:
                    chunk_color = "stop: 0 #DC3545, stop: 1 #FF6B6B"  # 红色 - 刚开始

                self.progress_bar.setChunkColors(chunk_color)
            else:
                self.progress_bar.setValue(0)
                self.progress_bar.setChunkColors("stop: 0 #DC3545, stop: 1 #FF6B6B")

        except Exception as e:
            self.logger.error(f"更新统计信息失败: {e}")

    def apply_theme(self):
        """应用主题到统计面板"""
        try:
            c = default_theme.colors

            # 设置面板背景
            self.setStyleSheet(f"""
                QWidget {{
                    background-color: {c.BACKGROUND_PRIMARY};
                }}
            """)

            # 更新标题标签样式
            if hasattr(self, 'findChildren'):
                for label in self.findChildren(QLabel):
                    if label.text().startswith("📊"):
                        label.setStyleSheet(f"""
                            QLabel {{
                                font-size: 13px;
                                font-weight: bold;
                                color: {c.PRIMARY};
                                border-bottom: 2px solid {c.PRIMARY};
                                padding: 4px 6px;
                                margin-bottom: 4px;
                            }}
                        """)

            # 更新统计标签样式
            label_style = f"""
                QLabel {{
                    padding: 4px 6px;
                    margin: 1px;
                    font-size: 11px;
                    border-radius: 3px;
                    background-color: {c.BACKGROUND_SECONDARY};
                    color: {c.TEXT_PRIMARY};
                }}
            """

            for label in [self.total_label, self.classified_label, self.removed_label, self.remaining_label]:
                label.setStyleSheet(label_style)

            # 更新进度条颜色（自定义进度条使用 setChunkColors）
            if hasattr(self, 'progress_bar'):
                current_value = self.progress_bar.value()
                if current_value >= 100:
                    chunk_color = "stop: 0 #28A745, stop: 1 #20C997"
                elif current_value >= 75:
                    chunk_color = "stop: 0 #17A2B8, stop: 1 #20C997"
                elif current_value >= 50:
                    chunk_color = "stop: 0 #FFC107, stop: 1 #FFD700"
                else:
                    chunk_color = "stop: 0 #DC3545, stop: 1 #FF6B6B"
                self.progress_bar.setChunkColors(chunk_color)
                self.progress_bar.update()  # 触发重绘

        except Exception as e:
            self.logger.error(f"应用主题到统计面板失败: {e}")