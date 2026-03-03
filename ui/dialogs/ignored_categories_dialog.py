"""管理忽略类别对话框模块"""

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QWidget,
    QCheckBox,
)

from ..components.styles import DialogStyles
from ..components.styles.theme import default_theme
from ..components.toast import toast_success, toast_warning, toast_info, toast_error


class ManageIgnoredCategoriesDialog(QDialog):
    """管理被忽略的类别对话框"""

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.parent_window = parent
        self.restore_count = 0

        self.setWindowTitle("⊘ 管理忽略的类别")
        self.setModal(True)
        self.setMinimumSize(500, 400)

        # 使用统一样式
        self.setStyleSheet(DialogStyles.get_form_dialog_style())

        self.init_ui()
        self.load_ignored_list()

    def init_ui(self):
        """初始化UI"""
        c = default_theme.colors

        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        # 标题说明
        title_label = QLabel("当前已忽略的类别目录：")
        title_label.setStyleSheet(f"""
            QLabel {{
                font-size: 14px;
                font-weight: bold;
                color: {c.TEXT_PRIMARY};
            }}
        """)
        layout.addWidget(title_label)

        # 列表容器
        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet(f"""
            QListWidget {{
                border: 1px solid {c.BORDER_MEDIUM};
                border-radius: 4px;
                background-color: {c.BACKGROUND_SECONDARY};
                color: {c.TEXT_PRIMARY};
                font-size: 13px;
            }}
            QListWidget::item {{
                border-bottom: 1px solid {c.BORDER_LIGHT};
            }}
            QListWidget::item:hover {{
                background-color: {c.BACKGROUND_HOVER};
            }}
        """)
        layout.addWidget(self.list_widget)

        # 底部说明
        info_label = QLabel("💡 提示：被忽略的目录不会被删除，只是不显示在类别列表中")
        info_label.setStyleSheet(f"""
            QLabel {{
                font-size: 12px;
                color: {c.TEXT_SECONDARY};
                padding: 5px;
                background-color: {c.BACKGROUND_HOVER};
                border-radius: 4px;
            }}
        """)
        layout.addWidget(info_label)

        # 按钮区域
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        # 批量恢复按钮
        batch_restore_btn = QPushButton("批量恢复选中")
        batch_restore_btn.clicked.connect(self.batch_restore)
        batch_restore_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {c.WARNING};
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 13px;
                min-width: 100px;
            }}
            QPushButton:hover {{
                background-color: {c.WARNING_DARK};
            }}
            QPushButton:pressed {{
                background-color: {c.WARNING_DARK};
            }}
        """)
        button_layout.addWidget(batch_restore_btn)

        # 关闭按钮
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.close_dialog)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {c.GRAY_500};
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 13px;
                min-width: 80px;
            }}
            QPushButton:hover {{
                background-color: {c.GRAY_600};
            }}
            QPushButton:pressed {{
                background-color: {c.GRAY_700};
            }}
        """)
        button_layout.addWidget(close_btn)

        layout.addLayout(button_layout)

    def load_ignored_list(self):
        """加载并显示忽略列表"""
        self.list_widget.clear()

        if not self.config.ignored_categories:
            # 空状态提示
            empty_item = QListWidgetItem("暂无被忽略的类别")
            empty_item.setFlags(Qt.ItemFlag.NoItemFlags)
            empty_item.setForeground(Qt.GlobalColor.gray)
            empty_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.list_widget.addItem(empty_item)
            return

        # 添加忽略的类别
        for category_name in sorted(self.config.ignored_categories):
            self.create_list_item(category_name)

    def create_list_item(self, category_name):
        """创建列表项（类别名 + 恢复按钮）"""
        c = default_theme.colors

        # 创建容器widget
        item_widget = QWidget()
        item_widget.setFixedHeight(45)  # 设置固定高度，确保按钮完整显示
        item_layout = QHBoxLayout(item_widget)
        item_layout.setContentsMargins(10, 6, 10, 6)
        item_layout.setSpacing(10)

        # 复选框
        checkbox = QCheckBox(f"📁 {category_name}")
        checkbox.setStyleSheet(f"""
            QCheckBox {{
                font-size: 13px;
                color: {c.TEXT_PRIMARY};
            }}
        """)
        item_layout.addWidget(checkbox)

        item_layout.addStretch()

        # 恢复按钮
        restore_btn = QPushButton("恢复")
        restore_btn.setFixedSize(60, 32)
        restore_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {c.SUCCESS};
                color: white;
                border: none;
                border-radius: 3px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: {c.SUCCESS_DARK};
            }}
            QPushButton:pressed {{
                background-color: {c.SUCCESS_DARK};
            }}
        """)
        restore_btn.clicked.connect(lambda: self.restore_category(category_name))
        item_layout.addWidget(restore_btn)

        # 添加到列表
        list_item = QListWidgetItem(self.list_widget)
        list_item.setSizeHint(QSize(0, 45))  # 设置列表项高度与widget一致
        list_item.setData(Qt.ItemDataRole.UserRole, category_name)  # 存储类别名
        self.list_widget.addItem(list_item)
        self.list_widget.setItemWidget(list_item, item_widget)

    def restore_category(self, category_name):
        """恢复单个类别"""
        try:
            if self.config.remove_ignored_category(category_name):
                self.config.save_config()
                self.restore_count += 1
                toast_success(self, f"已恢复类别: {category_name}")

                # 刷新对话框列表
                self.load_ignored_list()

                # 立即刷新主窗口的类别列表
                if self.parent_window and hasattr(self.parent_window, 'load_categories'):
                    self.parent_window.load_categories()
            else:
                toast_warning(self, f"类别 '{category_name}' 未被忽略")
        except Exception as e:
            toast_error(self, f"恢复失败: {str(e)}")

    def batch_restore(self):
        """批量恢复选中的类别"""
        restored = []

        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            widget = self.list_widget.itemWidget(item)

            if widget:
                # 查找复选框
                checkbox = widget.findChild(QCheckBox)
                if checkbox and checkbox.isChecked():
                    category_name = item.data(Qt.ItemDataRole.UserRole)
                    if category_name and self.config.remove_ignored_category(category_name):
                        restored.append(category_name)

        if restored:
            self.config.save_config()
            self.restore_count += len(restored)
            toast_success(self, f"已恢复 {len(restored)} 个类别")
            self.load_ignored_list()

            # 立即刷新主窗口的类别列表
            if self.parent_window and hasattr(self.parent_window, 'load_categories'):
                self.parent_window.load_categories()
        else:
            toast_info(self, "请先选择要恢复的类别")

    def close_dialog(self):
        """关闭对话框"""
        # 如果有恢复操作，通知主窗口刷新
        if self.restore_count > 0 and self.parent_window:
            if hasattr(self.parent_window, 'load_categories'):
                self.parent_window.load_categories()

        self.accept()
