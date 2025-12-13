"""类别面板 - 负责类别按钮的显示和交互"""
import functools
import logging
from typing import List, Dict, Optional
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea,
    QLabel, QPushButton, QButtonGroup, QMenu
)
from PyQt6.QtCore import pyqtSignal, Qt, QPoint
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QAction

from ...components.widgets.category_button import CategoryButton
from ...components.styles import WidgetStyles
from ...components.styles.theme import default_theme
from ...dialogs import AddCategoriesDialog


class CategoryPanel(QWidget):
    """类别面板 - 管理类别按钮的显示和交互

    信号：
        category_selected: 用户选中类别（单击）
        category_confirmed: 用户确认分类（通过按钮点击分类）
        operation_requested: 业务请求（添加/删除/重命名类别等）
        sort_mode_changed: 排序模式改变
        sort_direction_toggled: 排序方向切换
    """

    # 信号定义
    category_selected = pyqtSignal(str)  # 类别名称
    category_confirmed = pyqtSignal(str)  # 类别名称（用于执行分类）
    operation_requested = pyqtSignal(str, dict)  # 操作类型, 数据字典
    sort_mode_changed = pyqtSignal(str)  # 排序模式: 'name', 'shortcut', 'count'
    sort_direction_toggled = pyqtSignal()  # 排序方向切换

    def __init__(self, config, parent=None):
        """初始化类别面板

        Args:
            config: 配置对象
            parent: 父窗口
        """
        super().__init__(parent)
        self.config = config
        self.logger = logging.getLogger(__name__)

        # 状态
        self._ordered_categories = []
        self._category_counts = {}
        self._current_category_index = 0
        self._is_multi_category = False
        self._category_buttons = []
        self._categories_dict = {}  # 用于AddCategoriesDialog

        # UI组件
        self.category_scroll = None
        self.category_widget = None
        self.button_layout = None
        self.sort_button = None
        self.sort_direction_button = None

        self._init_ui()
        self.apply_theme()  # 初始化时应用主题

    def _init_ui(self):
        """初始化UI"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 创建标题栏和工具栏
        self._create_header(main_layout)

        # 创建类别按钮滚动区域
        self.category_scroll = QScrollArea()
        self.category_scroll.setObjectName("category_list")
        self.category_scroll.setWidgetResizable(True)
        self.category_scroll.setMinimumHeight(150)
        self.category_scroll.setStyleSheet("""
            QScrollArea {
                border: 1px solid #FFB74D;
                border-radius: 4px;
                background-color: #FFFFFF;
            }
            QScrollBar:vertical {
                border: 1px solid #FFB74D;
                background: #FFF8E1;
                width: 10px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background: #FF9800;
                border-radius: 3px;
                min-height: 15px;
            }
            QScrollBar::handle:vertical:hover {
                background: #F57C00;
            }
            QScrollBar::handle:vertical:pressed {
                background: #E65100;
            }
            QScrollBar:horizontal {
                border: 1px solid #FFB74D;
                background: #FFF8E1;
                height: 10px;
                border-radius: 3px;
            }
            QScrollBar::handle:horizontal {
                background: #FF9800;
                border-radius: 3px;
                min-width: 15px;
            }
            QScrollBar::handle:horizontal:hover {
                background: #F57C00;
            }
            QScrollBar::handle:horizontal:pressed {
                background: #E65100;
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical,
            QScrollBar::add-line:horizontal,
            QScrollBar::sub-line:horizontal {
                border: none;
                background: none;
            }
        """)

        self.category_widget = QWidget()
        self.button_layout = QVBoxLayout(self.category_widget)
        self.button_layout.setSpacing(3)
        self.button_layout.setContentsMargins(4, 4, 4, 4)

        self.category_scroll.setWidget(self.category_widget)
        main_layout.addWidget(self.category_scroll, 1)

    def _create_header(self, layout):
        """创建标题栏和工具栏"""
        # 标题容器
        category_title_container = QWidget()
        category_title_container.setObjectName("category_title_container")
        category_title_container.setStyleSheet("""
            QWidget#category_title_container {
                border-bottom: 2px solid #FF9800;
                margin-bottom: 4px;
                max-height: 28px;
                min-height: 28px;
            }
        """)
        category_title_layout = QHBoxLayout(category_title_container)
        category_title_layout.setContentsMargins(6, 0, 6, 4)
        category_title_layout.setSpacing(8)
        category_title_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # 标题
        category_label = QLabel("🏷️ 分类类别")
        category_label.setStyleSheet("""
            QLabel {
                font-size: 13px;
                font-weight: bold;
                color: #E65100;
                border: none;
                background-color: transparent;
                padding: 0px;
                margin: 0px;
            }
        """)
        category_title_layout.addWidget(category_label)
        category_title_layout.addStretch()

        # 排序方向按钮
        self.sort_direction_button = self._create_toolbar_button(
            '↑' if self.config.sort_ascending else '↓',
            'sort_direction_button',
            '',
            self._on_sort_direction_clicked,
            size=(18, 18)
        )
        self.sort_direction_button.setStyleSheet("""
            QPushButton#sort_direction_button {
                background-color: transparent;
                color: #E65100;
                border: none;
                border-radius: 3px;
                font-size: 12px;
                font-weight: bold;
                text-align: center;
                margin: 0px;
                padding: 0px;
            }
            QPushButton#sort_direction_button:hover {
                background-color: rgba(245, 245, 245, 180);
            }
            QPushButton#sort_direction_button:pressed {
                background-color: rgba(224, 224, 224, 180);
            }
        """)
        category_title_layout.addWidget(self.sort_direction_button)
        self._update_direction_button_tooltip()

        # 排序按钮
        self.sort_button = self._create_toolbar_button(
            '▼', 'sort_button',
            '类别排序方式',
            self._show_sort_menu,
            size=(18, 18)
        )
        self.sort_button.setStyleSheet("""
            QPushButton#sort_button {
                background-color: transparent;
                color: #E65100;
                border: none;
                border-radius: 3px;
                font-size: 11px;
                font-weight: normal;
                text-align: center;
                margin: 0px;
                padding: 0px;
            }
            QPushButton#sort_button:hover {
                background-color: rgba(245, 245, 245, 180);
            }
            QPushButton#sort_button:pressed {
                background-color: rgba(224, 224, 224, 180);
            }
        """)
        category_title_layout.addWidget(self.sort_button)

        # 添加类别按钮
        add_button = self._create_toolbar_button(
            '+', 'add_category_button',
            '批量添加分类类别',
            self._on_add_clicked,
            size=(18, 18)
        )
        add_button.setStyleSheet("""
            QPushButton#add_category_button {
                background-color: transparent;
                color: #E65100;
                border: none;
                border-radius: 3px;
                font-size: 14px;
                font-weight: bold;
                text-align: center;
                margin: 0px;
                padding: 0px;
            }
            QPushButton#add_category_button:hover {
                background-color: rgba(245, 245, 245, 180);
            }
            QPushButton#add_category_button:pressed {
                background-color: rgba(224, 224, 224, 180);
            }
        """)
        category_title_layout.addWidget(add_button)

        layout.addWidget(category_title_container, 0)

    def _create_toolbar_button(self, text: str, object_name: str, tooltip: str,
                              click_handler=None, size=(40, 40)) -> QPushButton:
        """创建工具栏按钮"""
        btn = QPushButton(text)
        btn.setObjectName(object_name)
        btn.setFixedSize(*size)
        btn.setToolTip(tooltip)
        if click_handler:
            btn.clicked.connect(click_handler)
        return btn

    # ========== Public API ==========

    def update_data(self, categories: List[str], counts: Dict[str, int],
                   current_index: int, categories_dict: Dict = None,
                   current_category: Optional[str] = None):
        """更新面板数据并重建按钮

        Args:
            categories: 排序后的类别名称列表
            counts: 各类别的分类数量
            current_index: 当前选中的类别索引
            categories_dict: 类别字典（用于AddCategoriesDialog）
            current_category: 当前图片的分类状态（单分类模式为str，多分类模式为list）
        """
        self._ordered_categories = categories
        self._category_counts = counts
        self._current_category_index = current_index
        if categories_dict is not None:
            self._categories_dict = categories_dict

        self._rebuild_buttons(current_category)
        self.update_selection(current_index)

    def update_selection(self, index: int):
        """仅更新选中状态"""
        self._current_category_index = index
        if 0 <= index < len(self._category_buttons):
            # 清除所有按钮的选中状态
            for btn in self._category_buttons:
                btn.setChecked(False)
            # 设置当前按钮为选中状态
            self._category_buttons[index].setChecked(True)
            # 确保按钮可见
            self.category_scroll.ensureWidgetVisible(self._category_buttons[index])

    def set_multi_category_mode(self, is_multi: bool):
        """设置多分类模式"""
        self._is_multi_category = is_multi

    def prev_category(self):
        """选择上一个类别"""
        if not self._category_buttons:
            return

        # 取消当前选中
        if 0 <= self._current_category_index < len(self._category_buttons):
            self._category_buttons[self._current_category_index].setChecked(False)

        # 循环选择上一个
        if self._current_category_index <= 0:
            self._current_category_index = len(self._category_buttons) - 1
        else:
            self._current_category_index -= 1

        # 设置新的选中状态
        self._category_buttons[self._current_category_index].setChecked(True)
        self.category_scroll.ensureWidgetVisible(self._category_buttons[self._current_category_index])

        # 发射信号
        category_name = self._ordered_categories[self._current_category_index]
        self.category_selected.emit(category_name)
        self.logger.info(f"选择类别: {category_name}")

    def next_category(self):
        """选择下一个类别"""
        if not self._category_buttons:
            return

        # 取消当前选中
        if 0 <= self._current_category_index < len(self._category_buttons):
            self._category_buttons[self._current_category_index].setChecked(False)

        # 循环选择下一个
        if self._current_category_index >= len(self._category_buttons) - 1:
            self._current_category_index = 0
        else:
            self._current_category_index += 1

        # 设置新的选中状态
        self._category_buttons[self._current_category_index].setChecked(True)
        self.category_scroll.ensureWidgetVisible(self._category_buttons[self._current_category_index])

        # 发射信号
        category_name = self._ordered_categories[self._current_category_index]
        self.category_selected.emit(category_name)
        self.logger.info(f"选择类别: {category_name}")

    def confirm_category(self):
        """确认当前选中的类别（用于快捷键Enter分类）"""
        if 0 <= self._current_category_index < len(self._ordered_categories):
            category_name = self._ordered_categories[self._current_category_index]
            self.category_confirmed.emit(category_name)

    def refresh_buttons_style(self):
        """刷新所有按钮样式"""
        for btn in self._category_buttons:
            if hasattr(btn, 'update_style'):
                btn.update_style()

    def update_sort_direction_button(self, ascending: bool):
        """更新排序方向按钮"""
        self.sort_direction_button.setText('↑' if ascending else '↓')
        self._update_direction_button_tooltip()

    # ========== Internal Logic ==========

    def _rebuild_buttons(self, current_category=None):
        """重建按钮网格"""
        # 清除现有按钮
        for i in reversed(range(self.button_layout.count())):
            widget = self.button_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)
        self._category_buttons.clear()

        if not self._ordered_categories:
            return

        # 创建按钮容器
        container = QWidget()
        container.setLayout(QVBoxLayout())
        container.layout().setSpacing(2)
        container.layout().setContentsMargins(0, 0, 0, 0)

        # 创建按钮组
        button_group = QButtonGroup(self)
        button_group.setExclusive(True)

        # 按排序后的顺序添加按钮
        for category_name in self._ordered_categories:
            try:
                btn = CategoryButton(category_name, self.config)
                btn.setCheckable(True)

                # 连接点击信号
                btn.clicked.connect(functools.partial(self._on_button_clicked, category_name))

                # 设置分类状态
                if current_category is not None:
                    if isinstance(current_category, list):
                        # 多分类模式
                        is_classified = category_name in current_category
                        is_multi = len(current_category) > 1 and is_classified
                        btn.set_classified(is_classified)
                        btn.set_multi_classified(is_multi)
                    else:
                        # 单分类模式
                        btn.set_classified(category_name == current_category)
                        btn.set_multi_classified(False)
                else:
                    btn.set_classified(False)
                    btn.set_multi_classified(False)

                # 确保按钮的UI样式更新
                btn.style().unpolish(btn)
                btn.style().polish(btn)

                # 设置类别计数
                btn.set_count(self._category_counts.get(category_name, 0))

                container.layout().addWidget(btn)
                self._category_buttons.append(btn)
                button_group.addButton(btn)

                # 如果是当前选中的类别，设置为选中状态
                if (self._current_category_index < len(self._ordered_categories) and
                    category_name == self._ordered_categories[self._current_category_index]):
                    btn.setChecked(True)

            except Exception as e:
                self.logger.error(f"创建类别按钮失败: {category_name}, 错误: {str(e)}")
                continue

        # 添加弹性空间
        container.layout().addStretch()

        # 将容器添加到滚动区域
        self.button_layout.addWidget(container)

        # 确保初始状态正确
        if (self._category_buttons and self._current_category_index >= 0 and
            self._current_category_index < len(self._category_buttons)):
            self._category_buttons[self._current_category_index].setChecked(True)
        elif self._category_buttons and not any(btn.isChecked() for btn in self._category_buttons):
            # 如果没有任何按钮被选中，默认选中第一个
            self._current_category_index = 0
            self._category_buttons[0].setChecked(True)

    def _on_button_clicked(self, category_name: str):
        """处理按钮点击"""
        # 更新选中的索引
        if category_name in self._ordered_categories:
            self._current_category_index = self._ordered_categories.index(category_name)

            # 清除所有按钮的选中状态
            for btn in self._category_buttons:
                btn.setChecked(False)

            # 设置当前按钮为选中状态
            if 0 <= self._current_category_index < len(self._category_buttons):
                self._category_buttons[self._current_category_index].setChecked(True)
                self.category_scroll.ensureWidgetVisible(self._category_buttons[self._current_category_index])

            # 发射信号
            self.category_selected.emit(category_name)
            self.logger.info(f"鼠标选择类别: {category_name}")

    def _on_add_clicked(self):
        """处理添加按钮点击"""
        # 发射操作请求信号，让主窗口处理
        # 主窗口需要提供current_dir信息
        self.operation_requested.emit('add_category', {})

    def _show_sort_menu(self):
        """显示排序方式菜单"""
        menu = QMenu(self)
        menu.setStyleSheet(WidgetStyles.get_context_menu_style())

        # 获取当前排序模式
        current_mode = getattr(self.config, 'category_sort_mode', 'name')

        # 三个单选菜单项
        action_name = QAction(self._create_checkbox_icon(current_mode == 'name'), "按名称排序", self)
        action_name.triggered.connect(lambda: self.sort_mode_changed.emit('name'))
        menu.addAction(action_name)

        action_shortcut = QAction(self._create_checkbox_icon(current_mode == 'shortcut'), "按快捷键排序", self)
        action_shortcut.triggered.connect(lambda: self.sort_mode_changed.emit('shortcut'))
        menu.addAction(action_shortcut)

        action_count = QAction(self._create_checkbox_icon(current_mode == 'count'), "按分类数量排序", self)
        action_count.triggered.connect(lambda: self.sort_mode_changed.emit('count'))
        menu.addAction(action_count)

        # 智能定位菜单
        menu.adjustSize()
        button_global_rect = self.sort_button.mapToGlobal(self.sort_button.rect().bottomRight())
        menu_size = menu.sizeHint()

        # 获取窗口边界
        window = self.window()
        window_rect = window.rect()
        window_global_pos = window.mapToGlobal(window_rect.topLeft())
        window_right = window_global_pos.x() + window_rect.width()
        window_bottom = window_global_pos.y() + window_rect.height()

        # 初始位置：按钮右下角，菜单右对齐
        x = button_global_rect.x() - menu_size.width()
        y = button_global_rect.y()

        # 确保菜单不超出窗口左边界
        if x < window_global_pos.x():
            x = window_global_pos.x() + 5

        # 如果菜单超出窗口底部，显示在按钮上方
        if y + menu_size.height() > window_bottom - 10:
            y = self.sort_button.mapToGlobal(self.sort_button.rect().topRight()).y() - menu_size.height()

        menu.exec(QPoint(x, y))

    def _on_sort_direction_clicked(self):
        """处理排序方向按钮点击"""
        self.sort_direction_toggled.emit()

    def _update_direction_button_tooltip(self):
        """更新排序方向按钮的tooltip"""
        if self.config.sort_ascending:
            self.sort_direction_button.setToolTip("当前升序，点击切换为降序")
        else:
            self.sort_direction_button.setToolTip("当前降序，点击切换为升序")

    def _create_checkbox_icon(self, is_checked: bool) -> QIcon:
        """创建复选框图标"""
        pixmap = QPixmap(16, 16)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        if is_checked:
            painter.setPen(Qt.GlobalColor.black)
            painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "✓")
        painter.end()

        return QIcon(pixmap)

    def apply_theme(self):
        """应用主题到面板"""
        c = default_theme.colors

        # 更新标题容器（橙色边框）
        category_title_container = self.findChild(QWidget, "category_title_container")
        if category_title_container:
            category_title_container.setStyleSheet(f"""
                QWidget#category_title_container {{
                    border-bottom: 2px solid {c.WARNING};
                    margin-bottom: 4px;
                    max-height: 28px;
                    min-height: 28px;
                }}
            """)

        # 更新滚动区域样式（橙色主题）
        if self.category_scroll:
            self.category_scroll.setStyleSheet(f"""
                QScrollArea {{
                    border: 1px solid {c.WARNING};
                    border-radius: 4px;
                    background-color: {c.BACKGROUND_SECONDARY};
                }}
                QScrollBar:vertical {{
                    border: 1px solid {c.WARNING};
                    background: {c.BACKGROUND_SECONDARY};
                    width: 10px;
                    border-radius: 3px;
                }}
                QScrollBar::handle:vertical {{
                    background: {c.WARNING};
                    border-radius: 3px;
                    min-height: 15px;
                }}
                QScrollBar::handle:vertical:hover {{
                    background: {c.WARNING_DARK};
                }}
                QScrollBar::handle:vertical:pressed {{
                    background: {c.WARNING_DARK};
                }}
                QScrollBar:horizontal {{
                    border: 1px solid {c.WARNING};
                    background: {c.BACKGROUND_SECONDARY};
                    height: 10px;
                    border-radius: 3px;
                }}
                QScrollBar::handle:horizontal {{
                    background: {c.WARNING};
                    border-radius: 3px;
                    min-width: 15px;
                }}
                QScrollBar::handle:horizontal:hover {{
                    background: {c.WARNING_DARK};
                }}
                QScrollBar::handle:horizontal:pressed {{
                    background: {c.WARNING_DARK};
                }}
                QScrollBar::add-line:vertical,
                QScrollBar::sub-line:vertical,
                QScrollBar::add-line:horizontal,
                QScrollBar::sub-line:horizontal {{
                    border: none;
                    background: none;
                }}
            """)

        # 更新类别按钮容器背景
        if self.category_widget:
            self.category_widget.setStyleSheet(f"""
                QWidget {{
                    background-color: {c.BACKGROUND_SECONDARY};
                }}
            """)

        # 刷新所有按钮样式
        self.refresh_buttons_style()
