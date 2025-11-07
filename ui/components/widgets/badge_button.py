"""
带红点标记的按钮组件
用于在按钮上显示未读提示或通知标记
"""

from PyQt6.QtWidgets import QPushButton, QWidget, QLabel
from PyQt6.QtCore import Qt, QRect
from PyQt6.QtGui import QPainter, QColor, QPen


class BadgeButton(QPushButton):
    """带红点标记的按钮组件"""

    def __init__(self, text='', parent=None):
        super().__init__(text, parent)
        self._show_badge = False
        self._badge_color = QColor(255, 59, 48)  # iOS红色
        self._badge_size = 12  # 再次增大红点到12像素

    def set_badge_visible(self, visible: bool):
        """设置红点是否可见"""
        if self._show_badge != visible:
            self._show_badge = visible
            self.update()  # 触发重绘

    def is_badge_visible(self) -> bool:
        """返回红点是否可见"""
        return self._show_badge

    def set_badge_color(self, color: QColor):
        """设置红点颜色"""
        self._badge_color = color
        if self._show_badge:
            self.update()

    def set_badge_size(self, size: int):
        """设置红点大小"""
        self._badge_size = size
        if self._show_badge:
            self.update()

    def paintEvent(self, event):
        """重写绘制事件，在按钮上绘制红点"""
        # 先调用父类绘制按钮本身
        super().paintEvent(event)

        # 如果需要显示红点，则在右上角绘制
        if self._show_badge:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            # 计算红点位置（完全在按钮内部的右上角）
            # 留出边距确保红点完全可见
            margin = 3
            badge_x = self.width() - self._badge_size - margin
            badge_y = margin

            # 绘制红点外圈（白色边框，增强可见性）
            painter.setPen(QPen(QColor(255, 255, 255), 2))
            painter.setBrush(self._badge_color)
            painter.drawEllipse(badge_x, badge_y, self._badge_size, self._badge_size)

            painter.end()


class BadgeWidget(QWidget):
    """包装任意widget并在其上显示红点的容器组件 - 直接绘制红点"""

    def __init__(self, widget: QWidget, parent=None):
        super().__init__(parent)
        self._widget = widget
        self._badge_size = 14  # 红点大小14像素
        self._badge_visible = False
        self._badge_color = QColor(255, 59, 48)  # iOS红色 #FF3B30

        # 使用布局管理器，让widget自己决定大小
        from PyQt6.QtWidgets import QVBoxLayout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(widget)

        # 设置尺寸策略跟随widget
        self.setSizePolicy(widget.sizePolicy())

    def paintEvent(self, event):
        """重写绘制事件，直接绘制红点"""
        super().paintEvent(event)

        if self._badge_visible:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            # 计算红点位置（右上角）
            x = self.width() - self._badge_size - 2
            y = 2

            # 绘制白色边框
            painter.setPen(QPen(QColor(255, 255, 255), 2))
            painter.setBrush(self._badge_color)
            painter.drawEllipse(x, y, self._badge_size, self._badge_size)

            painter.end()

    def resizeEvent(self, event):
        """窗口大小变化时触发重绘"""
        super().resizeEvent(event)
        self.update()

    def set_badge_visible(self, visible: bool):
        """设置红点是否可见"""
        if self._badge_visible != visible:
            self._badge_visible = visible
            self.update()  # 触发重绘

    def is_badge_visible(self) -> bool:
        """返回红点是否可见"""
        return self._badge_visible

    def set_badge_color(self, color: QColor):
        """设置红点颜色"""
        self._badge_color = color
        if self._badge_visible:
            self.update()  # 触发重绘

    def set_badge_size(self, size: int):
        """设置红点大小"""
        self._badge_size = size
        if self._badge_visible:
            self.update()  # 触发重绘
