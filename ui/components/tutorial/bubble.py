"""
教程提示气泡组件

提供带箭头的提示气泡，用于显示教程文本和说明。
"""

import logging
from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton
from PyQt6.QtCore import Qt, QPoint, QPointF, QRect, QRectF, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPainterPath, QFont
from typing import Optional
from enum import Enum
from ..dialog_utils import style_button
from ..styles.theme import default_theme


class ArrowPosition(Enum):
    """箭头位置枚举"""
    TOP = "top"  # 箭头在顶部，气泡在下方
    BOTTOM = "bottom"  # 箭头在底部，气泡在上方
    LEFT = "left"  # 箭头在左侧，气泡在右侧
    RIGHT = "right"  # 箭头在右侧，气泡在左侧
    LEFT_RIGHT = "left_right"  # 左右双箭头，气泡在中间
    CENTER = "center"  # 无箭头，气泡在父窗口中央


class TutorialBubble(QWidget):
    """教程提示气泡

    显示带箭头的提示框，用于引导用户了解各个功能。
    """

    # 信号
    next_clicked = pyqtSignal()  # 用户点击"下一步"
    prev_clicked = pyqtSignal()  # 用户点击"上一步"
    skip_clicked = pyqtSignal()  # 用户点击"跳过教程"
    finish_clicked = pyqtSignal()  # 用户点击"完成"

    def __init__(self, parent: Optional[QWidget] = None):
        """初始化提示气泡

        Args:
            parent: 父窗口
        """
        super().__init__(parent)

        # 气泡样式配置
        self._bubble_color = QColor(default_theme.colors.BACKGROUND_CARD)
        self._border_color = QColor(default_theme.colors.PRIMARY)
        self._text_color = QColor(default_theme.colors.TEXT_PRIMARY)
        self._border_width = 2
        self._corner_radius = 12
        self._arrow_size = 16  # 箭头大小
        self._arrow_position = ArrowPosition.TOP
        self._arrow_tip_offset = None
        self._padding = 20

        # 双箭头模式的目标位置
        self._left_target_pos = None
        self._right_target_pos = None

        # 窗口设置
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)

        # 创建logger
        self.logger = logging.getLogger(__name__)

        # 创建UI
        self._setup_ui()

        # 初始化隐藏
        self.hide()

    def apply_theme(self):
        """同步气泡、文本及按钮到当前主题。"""
        c = default_theme.colors
        self._bubble_color = QColor(c.BACKGROUND_CARD)
        self._border_color = QColor(c.PRIMARY)
        self._text_color = QColor(c.TEXT_PRIMARY)
        self._content_label.setStyleSheet(
            f"color: {c.TEXT_PRIMARY}; background: transparent;"
        )
        self._style_skip_button()
        style_button(self._prev_button, "secondary")
        style_button(self._next_button, "primary")
        style_button(self._finish_button, "success")
        self.update()

    def _style_skip_button(self):
        """跳过教程保持轻量外观，悬浮时明确提示这是退出操作。"""
        style_button(self._skip_button, "ghost")
        c = default_theme.colors
        self._skip_button.setStyleSheet(
            self._skip_button.styleSheet()
            + f"""
                QPushButton#tutorialSkipButton:hover {{
                    background-color: {c.ERROR};
                    color: {c.TEXT_ON_PRIMARY};
                    border-color: {c.ERROR};
                }}
                QPushButton#tutorialSkipButton:pressed {{
                    background-color: {c.ERROR_DARK};
                    color: {c.TEXT_ON_PRIMARY};
                    border-color: {c.ERROR_DARK};
                }}
            """
        )

    def _setup_ui(self):
        """设置UI布局"""
        # 主布局
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(
            self._padding + self._border_width,
            self._padding + self._border_width + self._arrow_size,
            self._padding + self._border_width,
            self._padding + self._border_width
        )
        main_layout.setSpacing(15)

        # 内容标签
        self._content_label = QLabel()
        self._content_label.setWordWrap(True)
        self._content_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        # 固定一个稳定的正文宽度，避免 QLabel 的 HTML sizeHint 把气泡
        # 撑成超宽单行，随后又被窗口边界硬裁切。
        self._content_label.setMinimumWidth(360)
        self._content_label.setMaximumWidth(380)

        # 设置字体
        font = QFont()
        font.setPointSize(10)
        self._content_label.setFont(font)

        # 设置文字颜色
        self._content_label.setStyleSheet(f"color: rgb({self._text_color.red()}, {self._text_color.green()}, {self._text_color.blue()}); background: transparent;")

        main_layout.addWidget(self._content_label)

        # 按钮布局
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)

        # 跳过按钮
        self._skip_button = QPushButton("跳过教程")
        self._skip_button.setObjectName("tutorialSkipButton")
        self._style_skip_button()
        self._skip_button.clicked.connect(self.skip_clicked.emit)
        button_layout.addWidget(self._skip_button)

        button_layout.addStretch()

        # 上一步按钮
        self._prev_button = QPushButton("上一步")
        style_button(self._prev_button, "secondary")
        self._prev_button.clicked.connect(self.prev_clicked.emit)
        button_layout.addWidget(self._prev_button)

        # 下一步按钮
        self._next_button = QPushButton("下一步")
        style_button(self._next_button, "primary")
        self._next_button.clicked.connect(self.next_clicked.emit)
        button_layout.addWidget(self._next_button)

        # 完成按钮（初始隐藏，最后一步显示）
        self._finish_button = QPushButton("完成")
        style_button(self._finish_button, "success")
        self._finish_button.clicked.connect(self.finish_clicked.emit)
        self._finish_button.hide()
        button_layout.addWidget(self._finish_button)

        main_layout.addLayout(button_layout)

    def set_content(self, text: str):
        """设置气泡内容

        Args:
            text: 显示的文本内容
        """
        self._content_label.setText(text)

    def set_arrow_position(self, position: ArrowPosition):
        """设置箭头位置

        Args:
            position: 箭头位置（TOP/BOTTOM/LEFT/RIGHT）
        """
        self._arrow_position = position
        self._arrow_tip_offset = None
        self._update_margins()
        self.update()

    def _update_margins(self):
        """根据箭头位置更新内边距"""
        base_margin = self._padding + self._border_width
        arrow_margin = base_margin + self._arrow_size

        if self._arrow_position == ArrowPosition.TOP:
            margins = (base_margin, arrow_margin, base_margin, base_margin)
        elif self._arrow_position == ArrowPosition.BOTTOM:
            margins = (base_margin, base_margin, base_margin, arrow_margin)
        elif self._arrow_position == ArrowPosition.LEFT:
            margins = (arrow_margin, base_margin, base_margin, base_margin)
        elif self._arrow_position == ArrowPosition.RIGHT:
            margins = (base_margin, base_margin, arrow_margin, base_margin)
        else:  # LEFT_RIGHT / CENTER 不在气泡本体绘制箭头
            margins = (base_margin, base_margin, base_margin, base_margin)

        self.layout().setContentsMargins(*margins)

    def set_step_info(self, current: int, total: int):
        """设置步骤信息，更新按钮状态

        Args:
            current: 当前步骤（从1开始）
            total: 总步骤数
        """
        # 更新上一步按钮状态
        self._prev_button.setEnabled(current > 1)

        # 如果是最后一步，显示"完成"按钮，隐藏"下一步"按钮
        if current == total:
            self._next_button.hide()
            self._finish_button.show()
        else:
            self._next_button.show()
            self._finish_button.hide()

    def paintEvent(self, event):
        """绘制气泡背景和箭头"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 创建气泡路径（包含箭头）
        path = self._create_bubble_path()

        # 绘制填充
        painter.fillPath(path, self._bubble_color)

        # 绘制边框
        painter.setPen(self._border_color)
        painter.drawPath(path)

        painter.end()

    def _create_bubble_path(self) -> QPainterPath:
        """创建气泡路径（包含箭头）

        Returns:
            包含气泡和箭头的QPainterPath
        """
        rect = self.rect()
        path = QPainterPath()

        # 根据箭头位置调整主体矩形
        if self._arrow_position == ArrowPosition.TOP:
            arrow_center = self._arrow_tip_offset or rect.width() / 2
            bubble_rect = QRect(
                rect.left(),
                rect.top() + self._arrow_size,
                rect.width(),
                rect.height() - self._arrow_size
            )
            arrow_tip = QPointF(arrow_center, 0)
            arrow_base_left = QPointF(arrow_center - self._arrow_size, self._arrow_size)
            arrow_base_right = QPointF(arrow_center + self._arrow_size, self._arrow_size)

        elif self._arrow_position == ArrowPosition.BOTTOM:
            arrow_center = self._arrow_tip_offset or rect.width() / 2
            bubble_rect = QRect(
                rect.left(),
                rect.top(),
                rect.width(),
                rect.height() - self._arrow_size
            )
            arrow_tip = QPointF(arrow_center, rect.height())
            arrow_base_left = QPointF(arrow_center - self._arrow_size, rect.height() - self._arrow_size)
            arrow_base_right = QPointF(arrow_center + self._arrow_size, rect.height() - self._arrow_size)

        elif self._arrow_position == ArrowPosition.LEFT:
            arrow_center = self._arrow_tip_offset or rect.height() / 2
            bubble_rect = QRect(
                rect.left() + self._arrow_size,
                rect.top(),
                rect.width() - self._arrow_size,
                rect.height()
            )
            arrow_tip = QPointF(0, arrow_center)
            arrow_base_left = QPointF(self._arrow_size, arrow_center - self._arrow_size)
            arrow_base_right = QPointF(self._arrow_size, arrow_center + self._arrow_size)

        elif self._arrow_position in (ArrowPosition.LEFT_RIGHT, ArrowPosition.CENTER):
            # 双箭头模式：气泡主体不预留箭头空间，箭头在paintEvent中单独绘制
            bubble_rect = QRect(
                rect.left(),
                rect.top(),
                rect.width(),
                rect.height()
            )
            # 创建圆角矩形
            path.addRoundedRect(QRectF(bubble_rect), self._corner_radius, self._corner_radius)
            return path

        else:  # RIGHT
            arrow_center = self._arrow_tip_offset or rect.height() / 2
            bubble_rect = QRect(
                rect.left(),
                rect.top(),
                rect.width() - self._arrow_size,
                rect.height()
            )
            arrow_tip = QPointF(rect.width(), arrow_center)
            arrow_base_left = QPointF(rect.width() - self._arrow_size, arrow_center - self._arrow_size)
            arrow_base_right = QPointF(rect.width() - self._arrow_size, arrow_center + self._arrow_size)

        # 创建圆角矩形
        path.addRoundedRect(QRectF(bubble_rect), self._corner_radius, self._corner_radius)

        # 添加箭头
        arrow_path = QPainterPath()
        arrow_path.moveTo(arrow_tip)
        arrow_path.lineTo(arrow_base_left)
        arrow_path.lineTo(arrow_base_right)
        arrow_path.closeSubpath()

        # 合并路径
        path = path.united(arrow_path)

        return path

    @staticmethod
    def _opposite_position(position: ArrowPosition) -> ArrowPosition:
        """返回相反方向，供目标附近空间不足时自动翻转。"""
        return {
            ArrowPosition.TOP: ArrowPosition.BOTTOM,
            ArrowPosition.BOTTOM: ArrowPosition.TOP,
            ArrowPosition.LEFT: ArrowPosition.RIGHT,
            ArrowPosition.RIGHT: ArrowPosition.LEFT,
        }.get(position, position)

    def _resolve_position(
        self,
        preferred: ArrowPosition,
        target_bounds: QRect,
        parent_bounds: QRect,
    ) -> ArrowPosition:
        """根据目标四周真实可用空间选择不会严重遮挡目标的一侧。"""
        if preferred in (ArrowPosition.LEFT_RIGHT, ArrowPosition.CENTER):
            return preferred

        gap = 10
        spaces = {
            ArrowPosition.RIGHT: target_bounds.left() - parent_bounds.left() - gap,
            ArrowPosition.LEFT: parent_bounds.right() - target_bounds.right() - gap,
            ArrowPosition.BOTTOM: target_bounds.top() - parent_bounds.top() - gap,
            ArrowPosition.TOP: parent_bounds.bottom() - target_bounds.bottom() - gap,
        }
        required = {
            ArrowPosition.RIGHT: self.width(),
            ArrowPosition.LEFT: self.width(),
            ArrowPosition.BOTTOM: self.height(),
            ArrowPosition.TOP: self.height(),
        }

        if spaces[preferred] >= required[preferred]:
            return preferred
        opposite = self._opposite_position(preferred)
        if spaces[opposite] >= required[opposite]:
            return opposite

        fitting = [
            position
            for position in spaces
            if spaces[position] >= required[position]
        ]
        if fitting:
            return max(fitting, key=lambda position: spaces[position])
        return max(
            spaces,
            key=lambda position: spaces[position] / max(required[position], 1),
        )

    def show_at(self, target_widget: QWidget, offset_x: int = 0, offset_y: int = 0, secondary_target: Optional[QWidget] = None):
        """在指定控件附近显示气泡

        Args:
            target_widget: 目标控件
            offset_x: X轴偏移量
            offset_y: Y轴偏移量
            secondary_target: 第二个目标控件（用于双箭头模式）
        """
        self.logger.debug(f"[Bubble.show_at] ENTER: target={target_widget}, secondary={secondary_target}, offset_x={offset_x}, offset_y={offset_y}")

        if target_widget is None or self.parent() is None:
            self.logger.warning(f"[Bubble.show_at] 提前返回: target_widget={target_widget}, parent={self.parent()}")
            return

        # 调整气泡大小以适应固定宽度下的换行内容。
        self.adjustSize()

        # 计算目标控件的位置（相对于父窗口）
        # 使用mapTo获取控件左上角在父窗口中的位置
        target_pos_in_parent = target_widget.mapTo(self.parent(), target_widget.rect().topLeft())
        target_rect = target_widget.rect()

        target_bounds = QRect(target_pos_in_parent, target_rect.size())
        target_center = QPoint(
            target_pos_in_parent.x() + target_rect.width() // 2,
            target_pos_in_parent.y() + target_rect.height() // 2
        )

        preferred_position = self._arrow_position
        actual_position = self._resolve_position(
            preferred_position,
            target_bounds,
            self.parent().rect(),
        )
        if actual_position != preferred_position:
            self.logger.debug(
                "目标附近空间不足，教程气泡从 %s 自动翻转到 %s",
                preferred_position.value,
                actual_position.value,
            )
            self.set_arrow_position(actual_position)
            self.adjustSize()
            # 原偏移量是按首选方向配置的，翻转后继续使用反而会再次偏离目标。
            offset_x = 0
            offset_y = 0

        # 如果有第二个目标控件，计算其位置
        secondary_global_pos = None
        if secondary_target is not None and actual_position == ArrowPosition.LEFT_RIGHT:
            secondary_pos_in_parent = secondary_target.mapTo(self.parent(), secondary_target.rect().topLeft())
            secondary_rect = secondary_target.rect()
            secondary_global_pos = QPoint(
                secondary_pos_in_parent.x() + secondary_rect.width() // 2,
                secondary_pos_in_parent.y() + secondary_rect.height() // 2
            )
            self.logger.debug(f"[Bubble] secondary_global_pos: {secondary_global_pos}")

        # DEBUG
        self.logger.debug(f"[Bubble] target_pos_in_parent: {target_pos_in_parent}")
        self.logger.debug(f"[Bubble] target_rect: {target_rect}")
        self.logger.debug(f"[Bubble] target_center: {target_center}")

        # 根据箭头位置计算气泡位置
        bubble_width = self.width()
        bubble_height = self.height()

        if actual_position == ArrowPosition.CENTER:
            x = (self.parent().width() - bubble_width) // 2 + offset_x
            y = (self.parent().height() - bubble_height) // 2 + offset_y
        elif actual_position == ArrowPosition.TOP:
            # 气泡在目标下方，箭头指向上
            x = target_center.x() - bubble_width // 2 + offset_x
            y = target_bounds.bottom() + 10 + offset_y
        elif actual_position == ArrowPosition.BOTTOM:
            # 气泡在目标上方，箭头指向下
            x = target_center.x() - bubble_width // 2 + offset_x
            y = target_bounds.top() - bubble_height - 10 + offset_y
        elif actual_position == ArrowPosition.LEFT:
            # 气泡在目标右侧，箭头指向左
            x = target_bounds.right() + 10 + offset_x
            y = target_center.y() - bubble_height // 2 + offset_y
        elif actual_position == ArrowPosition.LEFT_RIGHT:
            # 双箭头模式：气泡在两个控件中间
            if secondary_global_pos is not None:
                # 计算两个控件的中间位置
                mid_x = (target_center.x() + secondary_global_pos.x()) // 2
                mid_y = (target_center.y() + secondary_global_pos.y()) // 2
                x = mid_x - bubble_width // 2 + offset_x
                y = mid_y - bubble_height // 2 + offset_y
                # 保存两个目标位置供绘制箭头使用
                self._left_target_pos = target_center
                self._right_target_pos = secondary_global_pos
            else:
                # 如果没有第二个目标，回退到居中显示
                x = target_center.x() - bubble_width // 2 + offset_x
                y = target_center.y() - bubble_height // 2 + offset_y
        else:  # RIGHT
            # 气泡在目标左侧，箭头指向右
            x = target_bounds.left() - bubble_width - 10 + offset_x
            y = target_center.y() - bubble_height // 2 + offset_y

        # DEBUG：记录计算出来的气泡位置
        self.logger.debug(f"[Bubble] 计算出的气泡位置(修正前): x={x}, y={y}")

        # 气泡是主窗口的子控件，统一在主窗口坐标系内约束即可；不再用
        # primaryScreen 混入另一套坐标，修复多显示器和非原点窗口偏位。
        if self.parent():
            parent_rect = self.parent().rect()
            max_x = max(10, parent_rect.width() - bubble_width - 10)
            max_y = max(10, parent_rect.height() - bubble_height - 10)

            x = max(10, min(x, max_x))
            y = max(10, min(y, max_y))

        # 边界夹取后让箭头尖端继续对准目标中心，而不是固定在气泡正中。
        arrow_margin = self._corner_radius + self._arrow_size + 2
        if actual_position in (ArrowPosition.TOP, ArrowPosition.BOTTOM):
            self._arrow_tip_offset = max(
                arrow_margin,
                min(target_center.x() - x, bubble_width - arrow_margin),
            )
        elif actual_position in (ArrowPosition.LEFT, ArrowPosition.RIGHT):
            self._arrow_tip_offset = max(
                arrow_margin,
                min(target_center.y() - y, bubble_height - arrow_margin),
            )
        else:
            self._arrow_tip_offset = None

        self.logger.debug(f"[Bubble] 最终气泡位置(修正后): x={x}, y={y}")

        self.move(x, y)
        self.show()
        self.raise_()

        # 触发重绘，确保箭头显示（特别是双箭头模式）
        self.update()
