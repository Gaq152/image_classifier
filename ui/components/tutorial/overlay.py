"""
教程遮罩层组件

提供半透明遮罩效果，并支持挖空特定区域以突出显示指定的UI元素。
"""

from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QRect, QRectF, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPainterPath, QRegion
from typing import Optional, List


class TutorialOverlay(QWidget):
    """教程遮罩层

    创建一个半透明的黑色遮罩，覆盖整个主窗口，
    并在指定区域挖空以突出显示需要引导的UI元素。
    """

    # 信号：用户点击了遮罩层（非高亮区域）
    overlay_clicked = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        """初始化遮罩层

        Args:
            parent: 父窗口，通常是主窗口
        """
        super().__init__(parent)

        # 遮罩配置
        self._mask_color = QColor(0, 0, 0, 180)  # 半透明黑色，透明度180/255
        self._highlight_regions: List[QRect] = []  # 需要高亮（挖空）的区域列表
        self._highlight_padding = 8  # 高亮区域的内边距
        self._highlight_radius = 8  # 高亮区域的圆角半径

        # 窗口设置
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)

        # 初始化隐藏
        self.hide()

    def set_highlight_region(self, rect: QRect, padding: Optional[int] = None):
        """设置单个高亮区域

        Args:
            rect: 需要高亮的矩形区域（窗口坐标系）
            padding: 高亮区域的内边距，默认使用类属性值
        """
        if padding is not None:
            actual_padding = padding
        else:
            actual_padding = self._highlight_padding

        # 扩展矩形以添加内边距
        expanded_rect = rect.adjusted(
            -actual_padding,
            -actual_padding,
            actual_padding,
            actual_padding
        )

        self._highlight_regions = [expanded_rect]
        self.update()  # 触发重绘

    def set_highlight_regions(self, rects: List[QRect], padding: Optional[int] = None):
        """设置多个高亮区域

        Args:
            rects: 需要高亮的矩形区域列表（窗口坐标系）
            padding: 高亮区域的内边距，默认使用类属性值
        """
        if padding is not None:
            actual_padding = padding
        else:
            actual_padding = self._highlight_padding

        # 扩展所有矩形
        self._highlight_regions = [
            rect.adjusted(
                -actual_padding,
                -actual_padding,
                actual_padding,
                actual_padding
            )
            for rect in rects
        ]

        self.update()  # 触发重绘

    def clear_highlight_regions(self):
        """清除所有高亮区域"""
        self._highlight_regions = []
        self.update()

    def set_mask_opacity(self, opacity: int):
        """设置遮罩透明度

        Args:
            opacity: 透明度值，范围0-255，0为完全透明，255为完全不透明
        """
        self._mask_color.setAlpha(opacity)
        self.update()

    def set_highlight_radius(self, radius: int):
        """设置高亮区域圆角半径

        Args:
            radius: 圆角半径（像素）
        """
        self._highlight_radius = radius
        self.update()

    def paintEvent(self, event):
        """绘制遮罩层

        使用QPainter绘制半透明遮罩，并在高亮区域挖空。
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 创建完整的遮罩路径（覆盖整个窗口）
        full_path = QPainterPath()
        full_path.addRect(QRectF(self.rect()))  # Convert QRect to QRectF

        # 从遮罩中减去高亮区域（挖空）
        if self._highlight_regions:
            for highlight_rect in self._highlight_regions:
                # 创建圆角矩形路径
                cutout_path = QPainterPath()
                cutout_path.addRoundedRect(
                    QRectF(highlight_rect),  # Convert QRect to QRectF
                    self._highlight_radius,
                    self._highlight_radius
                )

                # 从完整路径中减去高亮区域
                full_path = full_path.subtracted(cutout_path)

        # 填充遮罩
        painter.fillPath(full_path, self._mask_color)

        painter.end()

    def mousePressEvent(self, event):
        """处理鼠标点击事件

        如果点击的是遮罩区域（非高亮区域），发出信号。
        """
        click_pos = event.pos()

        # 检查点击位置是否在高亮区域内
        in_highlight = False
        for highlight_rect in self._highlight_regions:
            if highlight_rect.contains(click_pos):
                in_highlight = True
                break

        # 如果点击的是遮罩区域，发出信号
        if not in_highlight:
            self.overlay_clicked.emit()

        # 允许事件继续传播到高亮区域的控件
        if in_highlight:
            event.ignore()
        else:
            event.accept()

    def show_overlay(self):
        """显示遮罩层"""
        # 确保遮罩层覆盖整个父窗口
        if self.parent():
            self.setGeometry(self.parent().rect())

        self.show()
        self.raise_()  # 确保在最顶层

    def hide_overlay(self):
        """隐藏遮罩层"""
        self.hide()
        self.clear_highlight_regions()

    def highlight_widget(self, widget: QWidget, padding: Optional[int] = None):
        """高亮显示指定的控件

        Args:
            widget: 需要高亮的控件
            padding: 高亮区域的内边距，默认使用类属性值
        """
        if not widget or not self.parent():
            return

        # 将控件坐标转换为父窗口坐标
        widget_rect = widget.rect()
        global_pos = widget.mapTo(self.parent(), widget_rect.topLeft())
        highlight_rect = QRect(global_pos, widget_rect.size())

        # 设置高亮区域
        self.set_highlight_region(highlight_rect, padding)

    def highlight_widgets(self, widgets: List[QWidget], padding: Optional[int] = None):
        """高亮显示多个控件

        Args:
            widgets: 需要高亮的控件列表
            padding: 高亮区域的内边距，默认使用类属性值
        """
        if not widgets or not self.parent():
            return

        highlight_rects = []
        for widget in widgets:
            if widget:
                # 将控件坐标转换为父窗口坐标
                widget_rect = widget.rect()
                global_pos = widget.mapTo(self.parent(), widget_rect.topLeft())
                highlight_rect = QRect(global_pos, widget_rect.size())
                highlight_rects.append(highlight_rect)

        # 设置高亮区域
        if highlight_rects:
            self.set_highlight_regions(highlight_rects, padding)
