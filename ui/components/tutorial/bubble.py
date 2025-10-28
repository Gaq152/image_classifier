"""
教程提示气泡组件

提供带箭头的提示气泡，用于显示教程文本和说明。
"""

from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton
from PyQt6.QtCore import Qt, QPoint, QPointF, QRect, QRectF, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPainterPath, QFont
from typing import Optional
from enum import Enum


class ArrowPosition(Enum):
    """箭头位置枚举"""
    TOP = "top"  # 箭头在顶部，气泡在下方
    BOTTOM = "bottom"  # 箭头在底部，气泡在上方
    LEFT = "left"  # 箭头在左侧，气泡在右侧
    RIGHT = "right"  # 箭头在右侧，气泡在左侧


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
        self._bubble_color = QColor(255, 255, 255)  # 白色背景
        self._border_color = QColor(66, 133, 244)  # 蓝色边框
        self._text_color = QColor(60, 64, 67)  # 深灰色文字
        self._border_width = 2
        self._corner_radius = 12
        self._arrow_size = 16  # 箭头大小
        self._arrow_position = ArrowPosition.TOP
        self._padding = 20

        # 窗口设置
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)

        # 创建UI
        self._setup_ui()

        # 初始化隐藏
        self.hide()

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
        self._skip_button.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: rgb(95, 99, 104);
                border: 1px solid rgb(218, 220, 224);
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 10pt;
            }
            QPushButton:hover {
                background-color: rgb(248, 249, 250);
            }
            QPushButton:pressed {
                background-color: rgb(241, 243, 244);
            }
        """)
        self._skip_button.clicked.connect(self.skip_clicked.emit)
        button_layout.addWidget(self._skip_button)

        button_layout.addStretch()

        # 上一步按钮
        self._prev_button = QPushButton("上一步")
        self._prev_button.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: rgb(66, 133, 244);
                border: 1px solid rgb(66, 133, 244);
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 10pt;
            }
            QPushButton:hover {
                background-color: rgba(66, 133, 244, 0.08);
            }
            QPushButton:pressed {
                background-color: rgba(66, 133, 244, 0.16);
            }
            QPushButton:disabled {
                color: rgb(189, 193, 198);
                border-color: rgb(218, 220, 224);
            }
        """)
        self._prev_button.clicked.connect(self.prev_clicked.emit)
        button_layout.addWidget(self._prev_button)

        # 下一步按钮
        self._next_button = QPushButton("下一步")
        self._next_button.setStyleSheet("""
            QPushButton {
                background-color: rgb(66, 133, 244);
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 10pt;
            }
            QPushButton:hover {
                background-color: rgb(51, 103, 214);
            }
            QPushButton:pressed {
                background-color: rgb(26, 115, 232);
            }
        """)
        self._next_button.clicked.connect(self.next_clicked.emit)
        button_layout.addWidget(self._next_button)

        # 完成按钮（初始隐藏，最后一步显示）
        self._finish_button = QPushButton("完成")
        self._finish_button.setStyleSheet("""
            QPushButton {
                background-color: rgb(52, 168, 83);
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 10pt;
            }
            QPushButton:hover {
                background-color: rgb(46, 125, 50);
            }
            QPushButton:pressed {
                background-color: rgb(27, 94, 32);
            }
        """)
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
        else:  # RIGHT
            margins = (base_margin, base_margin, arrow_margin, base_margin)

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
            bubble_rect = QRect(
                rect.left(),
                rect.top() + self._arrow_size,
                rect.width(),
                rect.height() - self._arrow_size
            )
            arrow_tip = QPointF(rect.width() / 2, 0)
            arrow_base_left = QPointF(rect.width() / 2 - self._arrow_size, self._arrow_size)
            arrow_base_right = QPointF(rect.width() / 2 + self._arrow_size, self._arrow_size)

        elif self._arrow_position == ArrowPosition.BOTTOM:
            bubble_rect = QRect(
                rect.left(),
                rect.top(),
                rect.width(),
                rect.height() - self._arrow_size
            )
            arrow_tip = QPointF(rect.width() / 2, rect.height())
            arrow_base_left = QPointF(rect.width() / 2 - self._arrow_size, rect.height() - self._arrow_size)
            arrow_base_right = QPointF(rect.width() / 2 + self._arrow_size, rect.height() - self._arrow_size)

        elif self._arrow_position == ArrowPosition.LEFT:
            bubble_rect = QRect(
                rect.left() + self._arrow_size,
                rect.top(),
                rect.width() - self._arrow_size,
                rect.height()
            )
            arrow_tip = QPointF(0, rect.height() / 2)
            arrow_base_left = QPointF(self._arrow_size, rect.height() / 2 - self._arrow_size)
            arrow_base_right = QPointF(self._arrow_size, rect.height() / 2 + self._arrow_size)

        else:  # RIGHT
            bubble_rect = QRect(
                rect.left(),
                rect.top(),
                rect.width() - self._arrow_size,
                rect.height()
            )
            arrow_tip = QPointF(rect.width(), rect.height() / 2)
            arrow_base_left = QPointF(rect.width() - self._arrow_size, rect.height() / 2 - self._arrow_size)
            arrow_base_right = QPointF(rect.width() - self._arrow_size, rect.height() / 2 + self._arrow_size)

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

    def show_at(self, target_widget: QWidget, offset_x: int = 0, offset_y: int = 0):
        """在指定控件附近显示气泡

        Args:
            target_widget: 目标控件
            offset_x: X轴偏移量
            offset_y: Y轴偏移量
        """
        if not target_widget or not self.parent():
            return

        # 调整气泡大小以适应内容
        self.adjustSize()

        # 计算目标控件的位置（相对于父窗口）
        target_rect = target_widget.rect()
        target_global_pos = target_widget.mapTo(self.parent(), target_rect.center())

        # 根据箭头位置计算气泡位置
        bubble_width = self.width()
        bubble_height = self.height()

        if self._arrow_position == ArrowPosition.TOP:
            # 气泡在目标下方，箭头指向上
            x = target_global_pos.x() - bubble_width // 2 + offset_x
            y = target_global_pos.y() + target_rect.height() // 2 + 10 + offset_y
        elif self._arrow_position == ArrowPosition.BOTTOM:
            # 气泡在目标上方，箭头指向下
            x = target_global_pos.x() - bubble_width // 2 + offset_x
            y = target_global_pos.y() - target_rect.height() // 2 - bubble_height - 10 + offset_y
        elif self._arrow_position == ArrowPosition.LEFT:
            # 气泡在目标右侧，箭头指向左
            x = target_global_pos.x() + target_rect.width() // 2 + 10 + offset_x
            y = target_global_pos.y() - bubble_height // 2 + offset_y
        else:  # RIGHT
            # 气泡在目标左侧，箭头指向右
            x = target_global_pos.x() - target_rect.width() // 2 - bubble_width - 10 + offset_x
            y = target_global_pos.y() - bubble_height // 2 + offset_y

        # 确保气泡不超出父窗口边界
        if self.parent():
            parent_rect = self.parent().rect()
            x = max(10, min(x, parent_rect.width() - bubble_width - 10))
            y = max(10, min(y, parent_rect.height() - bubble_height - 10))

        self.move(x, y)
        self.show()
        self.raise_()
