"""
教程虚拟组件模块

提供各种虚拟菜单、弹窗组件，仅用于教程演示，不响应实际点击。
"""

from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout, QPushButton, QMenu, QDialog
from PyQt6.QtCore import Qt, QRect
from PyQt6.QtGui import QPainter, QColor
from typing import Optional, List, Tuple


class MockWidget(QWidget):
    """虚拟组件基类

    用于教程演示，禁用所有交互。
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        # 窗口设置
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)

        # 禁用交互，让事件穿透到下层
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)

    def mousePressEvent(self, event):
        """忽略鼠标点击"""
        event.ignore()

    def mouseReleaseEvent(self, event):
        """忽略鼠标释放"""
        event.ignore()

    def mouseMoveEvent(self, event):
        """忽略鼠标移动"""
        event.ignore()


class MockMenu(MockWidget):
    """虚拟菜单组件

    模拟QMenu的外观，用于教程演示。
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self.menu_items: List[Tuple[str, str]] = []  # (icon, text)
        self.has_separator = False
        self._padding = 8
        self._item_height = 32
        self._min_width = 200

    def add_items(self, items: List[Tuple[str, str]], separator_after: Optional[int] = None):
        """添加菜单项

        Args:
            items: [(icon, text), ...] 菜单项列表
            separator_after: 在哪个索引后添加分隔线
        """
        self.menu_items = items
        if separator_after is not None:
            self.has_separator = True
            self.separator_index = separator_after

        # 计算尺寸
        height = len(items) * self._item_height + 2 * self._padding
        if self.has_separator:
            height += 10  # 分隔线高度

        self.setFixedSize(self._min_width, height)

    def paintEvent(self, event):
        """绘制菜单"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 绘制菜单背景（使用固定的浅色主题样式）
        bg_color = QColor(255, 255, 255)
        border_color = QColor(200, 200, 200)

        painter.fillRect(self.rect(), bg_color)
        painter.setPen(border_color)
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))

        # 绘制菜单项
        y = self._padding
        text_color = QColor(50, 50, 50)
        for i, (icon, text) in enumerate(self.menu_items):
            # 绘制菜单项文本
            painter.setPen(text_color)

            item_rect = QRect(self._padding, y, self._min_width - 2 * self._padding, self._item_height)
            full_text = f"{icon} {text}" if icon else text
            painter.drawText(item_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, full_text)

            y += self._item_height

            # 绘制分隔线
            if self.has_separator and i == self.separator_index:
                painter.setPen(border_color)
                painter.drawLine(self._padding, y + 5, self._min_width - self._padding, y + 5)
                y += 10

        painter.end()


class MockDialog(MockWidget):
    """虚拟对话框组件

    模拟QDialog的外观，用于教程演示。
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self.title = ""
        self.content_items: List[Tuple[str, str]] = []  # [(label, widget_type), ...]
        self.buttons: List[str] = []  # [button_text, ...]
        self.content_type = "form"  # "form" or "text_edit"
        self.has_preview = False  # 是否有预览区域

        self._padding = 20
        self._title_height = 0  # 无标题栏
        self._item_height = 80  # 增加高度以容纳预览
        self._button_height = 40
        self._width = 450
        self._text_edit_height = 100

    def set_content(self, title: str, items: List[Tuple[str, str]], buttons: List[str],
                   content_type: str = "form", has_preview: bool = False):
        """设置对话框内容

        Args:
            title: 标题
            items: [(label, widget_type), ...] 表单项列表
            buttons: [button_text, ...] 按钮文本列表
            content_type: "form" 或 "text_edit"
            has_preview: 是否有预览区域
        """
        self.title = title
        self.content_items = items
        self.buttons = buttons
        self.content_type = content_type
        self.has_preview = has_preview

        # 计算高度
        if content_type == "text_edit":
            # 批量添加类别对话框：说明文字 + 文本框 + 预览区域 + 按钮
            height = self._padding * 4 + 30 + self._text_edit_height
            if has_preview:
                height += 100  # 预览区域高度
            height += self._button_height
        else:
            # 普通表单对话框
            height = (self._title_height +
                     len(items) * self._item_height +
                     self._button_height +
                     3 * self._padding)

        self.setFixedSize(self._width, height)

    def paintEvent(self, event):
        """绘制对话框"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 使用固定的浅色主题样式
        bg_color = QColor(255, 255, 255)
        border_color = QColor(200, 200, 200)
        text_color = QColor(50, 50, 50)
        text_secondary = QColor(128, 128, 128)

        # 绘制对话框背景
        painter.fillRect(self.rect(), bg_color)
        painter.setPen(border_color)
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))

        y = self._padding

        if self.content_type == "text_edit":
            # 批量添加类别对话框样式
            # 绘制标题（无标题栏）
            title_rect = QRect(self._padding, y, self._width - 2 * self._padding, 25)
            painter.setPen(text_color)
            font = painter.font()
            font.setPointSize(12)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(title_rect, Qt.AlignmentFlag.AlignLeft, self.title)
            y += 35

            # 绘制说明文字
            font.setPointSize(9)
            font.setBold(False)
            painter.setFont(font)
            painter.setPen(text_secondary)
            tip_text = "请输入类别名称，多个类别用逗号或换行分隔\n已存在的类别会被自动忽略"
            tip_rect = QRect(self._padding, y, self._width - 2 * self._padding, 35)
            painter.drawText(tip_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, tip_text)
            y += 45

            # 绘制文本编辑框
            text_edit_rect = QRect(self._padding, y, self._width - 2 * self._padding, self._text_edit_height)
            painter.fillRect(text_edit_rect, QColor(250, 250, 250))
            painter.setPen(border_color)
            painter.drawRect(text_edit_rect)
            y += self._text_edit_height + self._padding

            # 绘制预览区域（如果有）
            if self.has_preview:
                font.setPointSize(9)
                font.setBold(True)
                painter.setFont(font)
                painter.setPen(text_color)
                painter.drawText(self._padding, y, "预览:")
                y += 20

                preview_rect = QRect(self._padding, y, self._width - 2 * self._padding, 80)
                painter.fillRect(preview_rect, QColor(250, 250, 250))
                painter.setPen(border_color)
                painter.drawRect(preview_rect)
                y += 90

        else:
            # 普通表单对话框样式（保留原有逻辑）
            # 绘制表单项
            for label, widget_type in self.content_items:
                # 绘制标签
                label_rect = QRect(self._padding, y, self._width - 2 * self._padding, 20)
                painter.setPen(text_color)
                painter.drawText(label_rect, Qt.AlignmentFlag.AlignLeft, label)

                # 绘制输入框/下拉框样式
                y += 25
                widget_rect = QRect(self._padding, y, self._width - 2 * self._padding, 30)
                painter.fillRect(widget_rect, QColor(250, 250, 250))
                painter.setPen(border_color)
                painter.drawRect(widget_rect)

                # 如果是下拉框，绘制箭头
                if widget_type == "combobox":
                    painter.drawText(widget_rect.adjusted(0, 0, -10, 0), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "▼")

                y += 35

        # 绘制按钮（在底部）
        button_y = self.height() - self._button_height - self._padding
        button_width = (self._width - (len(self.buttons) + 1) * self._padding) // len(self.buttons)
        x = self._padding

        font = painter.font()
        font.setPointSize(10)
        font.setBold(False)
        painter.setFont(font)

        for button_text in self.buttons:
            button_rect = QRect(x, button_y, button_width, 35)

            # 不同按钮使用不同颜色
            if "确定" in button_text or "添加" in button_text or "继续" in button_text:
                button_color = QColor(66, 133, 244)
                text_color_btn = QColor(255, 255, 255)
            else:
                button_color = QColor(240, 240, 240)
                text_color_btn = text_color

            painter.fillRect(button_rect, button_color)
            painter.setPen(text_color_btn)
            painter.drawText(button_rect, Qt.AlignmentFlag.AlignCenter, button_text)

            x += button_width + self._padding

        painter.end()


class MockMessageBox(MockWidget):
    """虚拟消息框组件"""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self.title = ""
        self.message = ""
        self.buttons: List[str] = []

        self._padding = 20
        self._width = 400
        self._title_height = 40
        self._button_height = 40

    def set_content(self, title: str, message: str, buttons: List[str]):
        """设置消息框内容"""
        self.title = title
        self.message = message
        self.buttons = buttons

        # 计算消息文本需要的高度（简化计算，每50字符一行）
        lines = len(message) // 50 + 1
        message_height = max(60, lines * 25)

        height = self._title_height + message_height + self._button_height + 3 * self._padding
        self.setFixedSize(self._width, height)

    def paintEvent(self, event):
        """绘制消息框"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 使用固定的浅色主题样式
        bg_color = QColor(255, 255, 255)
        border_color = QColor(200, 200, 200)
        text_color = QColor(50, 50, 50)

        # 绘制背景
        painter.fillRect(self.rect(), bg_color)
        painter.setPen(border_color)
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))

        # 绘制标题
        title_rect = QRect(self._padding, self._padding, self._width - 2 * self._padding, 30)
        painter.setPen(text_color)
        font = painter.font()
        font.setBold(True)
        font.setPointSize(12)
        painter.setFont(font)
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignLeft, self.title)

        # 绘制消息
        font.setBold(False)
        font.setPointSize(10)
        painter.setFont(font)
        message_rect = QRect(self._padding, self._title_height + self._padding,
                            self._width - 2 * self._padding,
                            self.height() - self._title_height - self._button_height - 3 * self._padding)
        painter.drawText(message_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.TextWordWrap, self.message)

        # 绘制按钮
        y = self.height() - self._button_height - self._padding
        button_width = (self._width - (len(self.buttons) + 1) * self._padding) // len(self.buttons)
        x = self._padding

        for button_text in self.buttons:
            button_rect = QRect(x, y, button_width, 35)
            button_color = QColor(66, 133, 244) if "确定" in button_text or "重新" in button_text else QColor(240, 240, 240)
            text_color_btn = QColor(255, 255, 255) if "确定" in button_text or "重新" in button_text else text_color

            painter.fillRect(button_rect, button_color)
            painter.setPen(text_color_btn)
            painter.drawText(button_rect, Qt.AlignmentFlag.AlignCenter, button_text)

            x += button_width + self._padding

        painter.end()


class MockTabbedDialog(MockWidget):
    """虚拟带标签页的对话框（用于帮助对话框）"""

    def __init__(self, parent = None):
        super().__init__(parent)

        self.title = ""
        self.tabs = []  # 标签页标题列表
        self.buttons = []  # 底部按钮文本列表

        self._padding = 20
        self._title_height = 40
        self._tab_height = 35
        self._button_height = 40
        self._width = 700
        self._height = 500

    def set_content(self, title, tabs, buttons):
        """设置带标签页对话框内容

        Args:
            title: 窗口标题
            tabs: 标签页标题列表
            buttons: 底部按钮文本列表
        """
        self.title = title
        self.tabs = tabs
        self.buttons = buttons
        self.setFixedSize(self._width, self._height)

    def paintEvent(self, event):
        """绘制带标签页的对话框"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 使用固定的浅色主题样式
        bg_color = QColor(255, 255, 255)
        border_color = QColor(200, 200, 200)
        text_color = QColor(50, 50, 50)
        tab_bg = QColor(240, 240, 240)
        selected_tab_bg = QColor(255, 255, 255)

        # 绘制对话框背景
        painter.fillRect(self.rect(), bg_color)
        painter.setPen(border_color)
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))

        # 绘制标题栏（窗口标题）
        font = painter.font()
        font.setPointSize(11)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(text_color)
        title_rect = QRect(self._padding, 10, self._width - 2 * self._padding, 25)
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignLeft, self.title)

        # 绘制标签页栏
        tab_y = self._title_height
        tab_width = min(120, (self._width - 2 * self._padding) // max(len(self.tabs), 1))

        font.setPointSize(10)
        font.setBold(False)
        painter.setFont(font)

        for i, tab_title in enumerate(self.tabs):
            tab_x = self._padding + i * tab_width
            tab_rect = QRect(tab_x, tab_y, tab_width, self._tab_height)

            # 第一个标签页为选中状态
            if i == 0:
                painter.fillRect(tab_rect, selected_tab_bg)
                painter.setPen(text_color)
            else:
                painter.fillRect(tab_rect, tab_bg)
                painter.setPen(QColor(100, 100, 100))

            painter.drawRect(tab_rect)
            painter.drawText(tab_rect, Qt.AlignmentFlag.AlignCenter, tab_title)

        # 绘制内容区域边框
        content_y = tab_y + self._tab_height
        content_height = self._height - content_y - self._button_height - self._padding * 2
        content_rect = QRect(self._padding, content_y, self._width - 2 * self._padding, content_height)
        painter.setPen(border_color)
        painter.drawRect(content_rect)

        # 绘制内容区域提示文字
        font.setPointSize(10)
        painter.setFont(font)
        painter.setPen(QColor(150, 150, 150))
        painter.drawText(content_rect, Qt.AlignmentFlag.AlignCenter, "(标签页内容)")

        # 绘制底部按钮
        button_y = self._height - self._button_height - self._padding
        button_width = 140
        x = self._padding

        for button_text in self.buttons:
            button_rect = QRect(x, button_y, button_width, 35)

            # 不同按钮使用不同颜色
            if "清理" in button_text:
                button_color = QColor(255, 152, 0)  # 橙色
            elif "教程" in button_text:
                button_color = QColor(66, 133, 244)  # 蓝色
            else:
                button_color = QColor(240, 240, 240)

            text_color_btn = QColor(255, 255, 255) if "清理" in button_text or "教程" in button_text else text_color

            painter.fillRect(button_rect, button_color)
            painter.setPen(text_color_btn)
            painter.drawText(button_rect, Qt.AlignmentFlag.AlignCenter, button_text)

            x += button_width + 10

        painter.end()
