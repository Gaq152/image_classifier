"""带动画的 Toggle 组件"""

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, Qt, pyqtProperty, pyqtSignal
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QWidget


class AnimatedToggle(QWidget):
    """带有流畅滑动动画的Toggle开关组件"""
    clicked = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._checked = False
        self._circle_position = 2  # 滑块位置

        # 尺寸设置
        self.setFixedSize(44, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        # 动画设置
        self.animation = QPropertyAnimation(self, b"circle_position", self)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.animation.setDuration(200)  # 200ms的动画时长

    @pyqtProperty(float)
    def circle_position(self):
        return self._circle_position

    @circle_position.setter
    def circle_position(self, pos):
        self._circle_position = pos
        self.update()

    def paintEvent(self, event):
        """绘制Toggle开关"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 绘制背景轨道
        if self._checked:
            track_color = QColor("#66bb6a")  # 绿色（选中）
        else:
            track_color = QColor("#cfd8dc")  # 灰色（未选中）

        painter.setBrush(track_color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(0, 0, self.width(), self.height(), 12, 12)

        # 绘制滑块
        painter.setBrush(QColor("#FFFFFF"))
        circle_radius = 10
        painter.drawEllipse(
            int(self._circle_position),
            int((self.height() - circle_radius * 2) / 2),
            circle_radius * 2,
            circle_radius * 2
        )

    def mousePressEvent(self, event):
        """点击切换状态"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.setChecked(not self._checked)
            self.clicked.emit(self._checked)

    def setChecked(self, checked):
        """设置选中状态"""
        if self._checked == checked:
            return

        self._checked = checked

        # 启动动画
        if checked:
            # 移动到右侧
            self.animation.setStartValue(self._circle_position)
            self.animation.setEndValue(self.width() - 22)  # 44 - 20(圆直径) - 2(边距)
        else:
            # 移动到左侧
            self.animation.setStartValue(self._circle_position)
            self.animation.setEndValue(2)

        self.animation.start()

    def isChecked(self):
        """获取选中状态"""
        return self._checked
