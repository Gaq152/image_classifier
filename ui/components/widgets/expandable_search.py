"""
可展开的搜索组件
默认显示图标，点击展开输入框，支持回车搜索
基于Gemini和Codex的review建议优化
"""
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLineEdit, QToolButton
from PyQt6.QtCore import Qt, pyqtSignal, QPropertyAnimation, QEasingCurve, QEvent

from ..styles.theme import default_theme


class ExpandableSearch(QWidget):
    """
    可展开的搜索组件
    默认显示搜索图标，点击后平滑展开输入框（向左展开）
    搜索按钮固定位置，输入框在左侧展开
    """
    search_confirmed = pyqtSignal(str)  # 回车确认搜索
    search_cleared = pyqtSignal()       # 清除/关闭搜索

    # 展开宽度
    EXPANDED_WIDTH = 150

    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_expanded = False
        self._had_text = False  # 跟踪是否有文本，用于避免冗余信号
        self._is_active_search = False  # 跟踪是否处于搜索筛选状态
        self._init_ui()
        # 安装事件过滤器
        self.search_input.installEventFilter(self)

    def _init_ui(self):
        """初始化UI"""
        # 紧凑布局，无间距
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 1. 搜索输入框 (初始宽度为0，隐藏)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索...")
        self.search_input.setFixedWidth(0)
        self.search_input.setMinimumWidth(0)
        self.search_input.setFixedHeight(20)
        self.search_input.hide()

        # Gemini建议：使用内置清除按钮，自动处理显示/隐藏逻辑
        self.search_input.setClearButtonEnabled(True)
        self._apply_input_style()

        # 回车信号连接
        self.search_input.returnPressed.connect(self._on_return_pressed)

        # 2. 搜索按钮/图标（固定位置）
        self.search_btn = QToolButton()
        self.search_btn.setText("🔍")
        self.search_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.search_btn.setToolTip("搜索图片文件名\n输入关键字后按 Enter 确认")
        self.search_btn.setFixedSize(20, 20)
        self._apply_button_style()
        self.search_btn.clicked.connect(self._toggle_search)

        # 添加到布局：输入框 -> 搜索按钮
        layout.addWidget(self.search_input)
        layout.addWidget(self.search_btn)

        # 3. 动画设置
        self.animation = QPropertyAnimation(self.search_input, b"maximumWidth")
        self.animation.setDuration(200)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.animation.finished.connect(self._on_animation_finished)

    def _apply_input_style(self):
        """应用输入框样式"""
        c = default_theme.colors
        self.search_input.setStyleSheet(f"""
            QLineEdit {{
                border: none;
                border-bottom: 2px solid {c.PRIMARY};
                background-color: transparent;
                padding: 2px 4px;
                margin-right: 2px;
                color: {c.TEXT_PRIMARY};
                font-size: 12px;
                selection-background-color: {c.PRIMARY};
            }}
            QLineEdit:focus {{
                background-color: {c.BACKGROUND_SECONDARY};
                border-bottom: 2px solid {c.PRIMARY_LIGHT};
            }}
        """)

    def _apply_button_style(self):
        """应用搜索按钮样式"""
        c = default_theme.colors
        self.search_btn.setStyleSheet(f"""
            QToolButton {{
                border: none;
                border-radius: 10px;
                color: {c.PRIMARY};
                font-size: 12px;
                background: transparent;
            }}
            QToolButton:hover {{
                background-color: rgba(52, 152, 219, 0.15);
            }}
            QToolButton:pressed {{
                background-color: rgba(52, 152, 219, 0.25);
            }}
        """)

    def _toggle_search(self):
        """切换展开/收起状态"""
        if self.is_expanded:
            # 如果有内容，点击图标执行搜索；没内容则收起
            text = self.search_input.text().strip()
            if text:
                self._on_return_pressed()
            else:
                self.collapse()
        else:
            self.expand()

    def expand(self):
        """展开搜索框"""
        if self.is_expanded:
            return

        # Codex建议：先停止任何正在运行的动画
        self.animation.stop()

        self.is_expanded = True
        self.search_input.show()
        self.search_input.setMaximumWidth(self.EXPANDED_WIDTH)

        # Codex建议：使用当前宽度作为起始值，避免闪烁
        current_width = self.search_input.width()
        self.animation.setStartValue(current_width)
        self.animation.setEndValue(self.EXPANDED_WIDTH)
        self.animation.start()

    def _on_animation_finished(self):
        """动画结束后的处理"""
        if self.is_expanded:
            # 展开完成，聚焦输入框
            self.search_input.setFocus()
            self.search_input.selectAll()
        else:
            # Codex建议：收起完成后再清空和隐藏，避免视觉闪烁
            had_text = bool(self.search_input.text().strip())
            self.search_input.clear()
            self.search_input.setFixedWidth(0)
            self.search_input.hide()

            # 修复：检查是否处于搜索筛选状态，而不仅仅是输入框是否有文本
            # 场景：用户搜索后点X清空输入，再收起，此时输入为空但仍需清除筛选
            if had_text or self._had_text or self._is_active_search:
                self.search_cleared.emit()
            self._had_text = False
            self._is_active_search = False  # 重置搜索状态

    def collapse(self):
        """收起搜索框"""
        if not self.is_expanded:
            return

        # Codex建议：先停止任何正在运行的动画
        self.animation.stop()

        self.is_expanded = False
        # 记录是否有文本，用于动画结束后判断是否发射信号
        self._had_text = bool(self.search_input.text().strip())

        # Codex建议：使用当前宽度作为起始值
        current_width = self.search_input.width()
        self.animation.setStartValue(current_width)
        self.animation.setEndValue(0)
        self.animation.start()
        # 注意：文本清空移到_on_animation_finished，避免动画期间内容消失

    def _on_return_pressed(self):
        """处理回车搜索"""
        text = self.search_input.text().strip()
        if text:
            self._is_active_search = True  # 标记进入搜索筛选状态
            self.search_confirmed.emit(text)
        else:
            self.collapse()

    def clear_and_collapse(self):
        """清除搜索并收起（供外部调用）"""
        self.collapse()

    def set_search_text(self, text: str):
        """设置搜索文本（供外部调用）"""
        if text:
            if not self.is_expanded:
                self.expand()
            self.search_input.setText(text)
        else:
            self.collapse()

    def apply_theme(self):
        """应用主题（主题切换时调用）"""
        self._apply_input_style()
        self._apply_button_style()

    def eventFilter(self, obj, event):
        """事件过滤器：处理键盘事件"""
        if obj == self.search_input and event.type() == QEvent.Type.KeyPress:
            # Codex建议：过滤自动重复按键，防止长按触发多次
            if event.isAutoRepeat():
                return False

            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._on_return_pressed()
                return True
            elif event.key() == Qt.Key.Key_Escape:
                self.collapse()
                return True
        return super().eventFilter(obj, event)
