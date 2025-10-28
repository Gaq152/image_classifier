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
    """包装任意widget并在其上显示红点的容器组件 - 使用叠加Label方式"""

    def __init__(self, widget: QWidget, parent=None):
        super().__init__(parent)
        self._widget = widget
        self._badge_size = 14  # 红点大小14像素

        # 使用布局管理器，让widget自己决定大小
        from PyQt6.QtWidgets import QVBoxLayout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(widget)

        # 设置尺寸策略跟随widget
        self.setSizePolicy(widget.sizePolicy())

        # 创建红点Label，叠加在widget上层
        self._badge_label = QLabel(self)
        self._badge_label.setFixedSize(self._badge_size, self._badge_size)
        self._badge_label.setStyleSheet("""
            QLabel {
                background-color: #FF3B30;
                border: 2px solid white;
                border-radius: 7px;
            }
        """)
        self._badge_label.hide()  # 默认隐藏
        self._badge_label.raise_()  # 确保在最上层

    def resizeEvent(self, event):
        """窗口大小变化时更新红点位置"""
        super().resizeEvent(event)
        self._update_badge_position()

    def _update_badge_position(self):
        """更新红点位置到右上角"""
        if hasattr(self, '_badge_label'):
            # 位置：右上角，稍微偏移
            x = self.width() - self._badge_size - 2
            y = 2
            self._badge_label.move(x, y)

    def set_badge_visible(self, visible: bool):
        """设置红点是否可见"""
        if hasattr(self, '_badge_label'):
            if visible:
                self._badge_label.show()
                self._update_badge_position()
            else:
                self._badge_label.hide()

    def is_badge_visible(self) -> bool:
        """返回红点是否可见"""
        if hasattr(self, '_badge_label'):
            return self._badge_label.isVisible()
        return False

    def set_badge_color(self, color: QColor):
        """设置红点颜色"""
        if hasattr(self, '_badge_label'):
            self._badge_label.setStyleSheet(f"""
                QLabel {{
                    background-color: {color.name()};
                    border: 2px solid white;
                    border-radius: {self._badge_size // 2}px;
                }}
            """)

    def set_badge_size(self, size: int):
        """设置红点大小"""
        self._badge_size = size
        if hasattr(self, '_badge_label'):
            self._badge_label.setFixedSize(size, size)
            self._badge_label.setStyleSheet(f"""
                QLabel {{
                    background-color: #FF3B30;
                    border: 2px solid white;
                    border-radius: {size // 2}px;
                }}
            """)
            self._update_badge_position()
