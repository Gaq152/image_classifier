"""
教程遮罩层组件

提供半透明遮罩效果，并支持挖空特定区域以突出显示指定的UI元素。
"""

from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QRect, QRectF, QPoint, QPointF, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPainterPath, QPen, QRegion
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
        self._bubble_region: Optional[QRect] = None  # bubble区域，避免拦截bubble的点击

        # 箭头配置
        self._arrow_color = QColor(66, 133, 244)  # 蓝色箭头
        self._arrow_width = 3  # 箭头线条宽度
        self._arrow_size = 16  # 箭头头部大小
        self._arrow_start_pos: Optional[QPoint] = None  # 箭头起始位置（bubble位置）
        self._arrow_left_target: Optional[QPoint] = None  # 左侧箭头目标位置
        self._arrow_right_target: Optional[QPoint] = None  # 右侧箭头目标位置

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

    def add_highlight_region(self, rect: QRect, padding: Optional[int] = None):
        """添加一个额外的高亮区域（不清除现有区域）

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

        self._highlight_regions.append(expanded_rect)
        self.update()  # 触发重绘

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

    def set_dual_arrows(self, bubble_center: QPoint, left_target: QPoint, right_target: QPoint):
        """设置双箭头的位置

        Args:
            bubble_center: 气泡中心位置（全局坐标）
            left_target: 左侧目标位置（全局坐标）
            right_target: 右侧目标位置（全局坐标）
        """
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"[Overlay] 设置双箭头: bubble={bubble_center}, left={left_target}, right={right_target}")

        self._arrow_start_pos = bubble_center
        self._arrow_left_target = left_target
        self._arrow_right_target = right_target
        self.update()

    def clear_arrows(self):
        """清除箭头"""
        self._arrow_start_pos = None
        self._arrow_left_target = None
        self._arrow_right_target = None
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

        # 绘制双箭头（如果设置了）
        if (self._arrow_start_pos is not None and
            self._arrow_left_target is not None and
            self._arrow_right_target is not None):

            import logging
            logger = logging.getLogger(__name__)
            logger.debug(f"[Overlay.paintEvent] 开始绘制双箭头")

            # 设置箭头画笔
            pen = QPen(self._arrow_color)
            pen.setWidth(self._arrow_width)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)

            # 绘制左箭头 - 从气泡中心到左侧目标
            left_start = QPointF(self._arrow_start_pos)
            left_end = QPointF(self._arrow_left_target)

            painter.drawLine(left_start, left_end)

            # 左箭头头部（指向左侧目标）
            # 计算箭头方向向量
            import math
            dx = left_end.x() - left_start.x()
            dy = left_end.y() - left_start.y()
            length = math.sqrt(dx*dx + dy*dy)
            if length > 0:
                # 单位方向向量
                ux = dx / length
                uy = dy / length
                # 箭头两侧的点
                arrow_angle = math.pi / 6  # 30度
                left_wing_x = left_end.x() - self._arrow_size * (ux * math.cos(arrow_angle) + uy * math.sin(arrow_angle))
                left_wing_y = left_end.y() - self._arrow_size * (uy * math.cos(arrow_angle) - ux * math.sin(arrow_angle))
                right_wing_x = left_end.x() - self._arrow_size * (ux * math.cos(arrow_angle) - uy * math.sin(arrow_angle))
                right_wing_y = left_end.y() - self._arrow_size * (uy * math.cos(arrow_angle) + ux * math.sin(arrow_angle))

                painter.drawLine(left_end, QPointF(left_wing_x, left_wing_y))
                painter.drawLine(left_end, QPointF(right_wing_x, right_wing_y))

            # 绘制右箭头 - 从气泡中心到右侧目标
            right_start = QPointF(self._arrow_start_pos)
            right_end = QPointF(self._arrow_right_target)

            painter.drawLine(right_start, right_end)

            # 右箭头头部（指向右侧目标）
            dx = right_end.x() - right_start.x()
            dy = right_end.y() - right_start.y()
            length = math.sqrt(dx*dx + dy*dy)
            if length > 0:
                # 单位方向向量
                ux = dx / length
                uy = dy / length
                # 箭头两侧的点
                arrow_angle = math.pi / 6  # 30度
                left_wing_x = right_end.x() - self._arrow_size * (ux * math.cos(arrow_angle) + uy * math.sin(arrow_angle))
                left_wing_y = right_end.y() - self._arrow_size * (uy * math.cos(arrow_angle) - ux * math.sin(arrow_angle))
                right_wing_x = right_end.x() - self._arrow_size * (ux * math.cos(arrow_angle) - uy * math.sin(arrow_angle))
                right_wing_y = right_end.y() - self._arrow_size * (uy * math.cos(arrow_angle) + ux * math.sin(arrow_angle))

                painter.drawLine(right_end, QPointF(left_wing_x, left_wing_y))
                painter.drawLine(right_end, QPointF(right_wing_x, right_wing_y))

            logger.debug(f"[Overlay.paintEvent] 双箭头绘制完成")

        painter.end()

    def set_bubble_region(self, bubble_rect: QRect):
        """设置bubble区域，避免拦截bubble的点击

        Args:
            bubble_rect: bubble的矩形区域
        """
        self._bubble_region = bubble_rect

    def mousePressEvent(self, event):
        """处理鼠标点击事件

        如果点击的是遮罩区域（非高亮区域且非bubble区域），发出信号。
        """
        click_pos = event.pos()

        # 检查是否点击在bubble区域内（忽略bubble的点击）
        if self._bubble_region and self._bubble_region.contains(click_pos):
            event.ignore()  # 让事件传递到bubble
            return

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
        self.clear_arrows()

    def highlight_widget(self, widget: QWidget, padding: Optional[int] = None):
        """高亮显示指定的控件

        Args:
            widget: 需要高亮的控件
            padding: 高亮区域的内边距，默认使用类属性值
        """
        if widget is None or self.parent() is None:
            return

        # 将控件坐标转换为父窗口坐标
        widget_rect = widget.rect()
        global_pos = widget.mapTo(self.parent(), widget_rect.topLeft())
        highlight_rect = QRect(global_pos, widget_rect.size())

        # DEBUG
        import logging
        logger = logging.getLogger(__name__)
        logger.debug(f"[Overlay] widget_rect={widget_rect}, global_pos={global_pos}, highlight_rect={highlight_rect}")

        # 设置高亮区域
        self.set_highlight_region(highlight_rect, padding)

    def highlight_widgets(self, widgets: List[QWidget], padding: Optional[int] = None):
        """高亮显示多个控件

        Args:
            widgets: 需要高亮的控件列表
            padding: 高亮区域的内边距，默认使用类属性值
        """
        if not widgets or self.parent() is None:
            return

        highlight_rects = []
        for widget in widgets:
            if widget is not None:
                # 将控件坐标转换为父窗口坐标
                widget_rect = widget.rect()
                global_pos = widget.mapTo(self.parent(), widget_rect.topLeft())
                highlight_rect = QRect(global_pos, widget_rect.size())
                highlight_rects.append(highlight_rect)

        # 设置高亮区域
        if highlight_rects:
            self.set_highlight_regions(highlight_rects, padding)
