"""
图像列表项组件

自定义的列表项组件，显示图片状态和名称，支持多种状态图标。
"""

from pathlib import Path
from PyQt6.QtWidgets import QListWidgetItem
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap, QPainter, QPen, QBrush, QColor, QIcon


class ImageListItem(QListWidgetItem):
    """自定义列表项，显示图片状态和名称"""

    def __init__(self, image_path, is_classified, is_removed, parent=None):
        super().__init__(parent)
        self.image_path = image_path
        self.file_path = image_path  # 兼容性别名
        self.is_classified = is_classified
        self.is_removed = is_removed
        self.is_multi_classified = False  # 多分类状态标记
        self.setText(Path(image_path).name)
        # 延迟icon设置，避免QPixmap在QApplication前创建
        # self.setIcon(self.create_status_icon())

    def set_status_icon(self):
        """设置状态图标"""
        self.setIcon(self.create_status_icon())

    def create_status_icon(self):
        """创建美化的状态图标"""
        # 创建36x36的图标
        pixmap = QPixmap(36, 36)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 根据状态设置颜色和图标
        if self.is_classified:
            if self.is_multi_classified:
                # 多分类 - 蓝色图标
                color = QColor("#2196F3")
                shadow_color = QColor("#1565C0")
            else:
                # 已分类 - 绿色勾选图标
                color = QColor("#4CAF50")
                shadow_color = QColor("#2E7D32")
        elif self.is_removed:
            # 已移除 - 红色删除图标
            color = QColor("#F44336")
            shadow_color = QColor("#C62828")
        else:
            # 待处理 - 橙色警告图标
            color = QColor("#FF9800")
            shadow_color = QColor("#F57C00")

        # 绘制阴影效果
        painter.setPen(QPen(shadow_color, 2))
        painter.setBrush(QBrush(shadow_color, Qt.BrushStyle.SolidPattern))
        painter.drawEllipse(3, 3, 28, 28)

        # 绘制主圆形
        painter.setPen(QPen(color, 2))
        painter.setBrush(QBrush(color, Qt.BrushStyle.SolidPattern))
        painter.drawEllipse(2, 2, 28, 28)

        # 绘制状态符号
        painter.setPen(QPen(Qt.GlobalColor.white, 3))
        if self.is_classified:
            if self.is_multi_classified:
                # 绘制多分类标记 - 双层矩形
                painter.drawRect(8, 8, 14, 14)
                painter.drawRect(14, 14, 14, 14)
            else:
                # 绘制√ - 更优雅的勾选
                painter.drawLine(8, 16, 14, 22)
                painter.drawLine(14, 22, 26, 10)
        elif self.is_removed:
            # 绘制× - 删除符号
            painter.drawLine(10, 10, 24, 24)
            painter.drawLine(24, 10, 10, 24)
        else:
            # 绘制! - 待处理警告
            painter.setPen(QPen(Qt.GlobalColor.white, 2))
            painter.drawLine(16, 8, 16, 18)  # 竖线
            painter.drawEllipse(14, 22, 4, 4)  # 点

        painter.end()
        return QIcon(pixmap)

    def update_status(self, is_classified, is_removed, is_multi_classified=False):
        """更新状态"""
        self.is_classified = is_classified
        self.is_removed = is_removed
        self.is_multi_classified = is_multi_classified
        self.set_status_icon()