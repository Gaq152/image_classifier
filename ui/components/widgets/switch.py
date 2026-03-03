"""
滑块开关组件

提供iOS风格的滑块开关控件
"""

from PyQt6.QtWidgets import QAbstractButton
from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve, pyqtProperty
from PyQt6.QtGui import QPainter, QColor, QPen


class Switch(QAbstractButton):
    """iOS风格的滑块开关"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setFixedSize(50, 26)
        self._circle_position = 3

        # 动画
        self.animation = QPropertyAnimation(self, b"circle_position", self)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.animation.setDuration(200)

        # 连接信号
        self.toggled.connect(self._animate)

    @pyqtProperty(float)
    def circle_position(self):
        return self._circle_position

    @circle_position.setter
    def circle_position(self, pos):
        self._circle_position = pos
        self.update()

    def _animate(self, checked):
        """执行动画"""
        if checked:
            self.animation.setStartValue(3)
            self.animation.setEndValue(self.width() - 23)
        else:
            self.animation.setStartValue(self.width() - 23)
            self.animation.setEndValue(3)
        self.animation.start()

    def paintEvent(self, event):
        """绘制开关"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 背景
        if self.isChecked():
            bg_color = QColor("#3B82F6")  # 蓝色
        else:
            bg_color = QColor("#D1D5DB")  # 灰色

        painter.setBrush(bg_color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(0, 0, self.width(), self.height(), 13, 13)

        # 圆形滑块
        painter.setBrush(QColor("#FFFFFF"))
        painter.setPen(QPen(QColor("#E5E7EB"), 1))
        painter.drawEllipse(int(self._circle_position), 3, 20, 20)

    def sizeHint(self):
        """推荐尺寸"""
        return self.size()
