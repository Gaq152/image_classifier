"""批量添加类别对话框模块"""

import logging
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QListWidget,
    QListWidgetItem,
    QWidget,
)

from ...utils.file_operations import normalize_folder_name, retry_file_operation
from ..components.styles import ButtonStyles, DialogStyles
from ..components.styles.theme import default_theme
from ..components.toast import toast_warning, toast_error


class AddCategoriesDialog(QDialog):
    """批量添加类别对话框"""

    def __init__(self, existing_categories, parent=None):
        super().__init__(parent)
        self.existing_categories = existing_categories
        self.added_categories = set()
        self.logger = logging.getLogger(__name__)
        self._centered = False  # 标记是否已居中
        self.initUI()

    def initUI(self):
        """初始化UI"""
        try:
            # 应用主题样式
            c = default_theme.colors
            self.setStyleSheet(DialogStyles.get_form_dialog_style())

            self.setWindowTitle('批量添加类别')
            self.setMinimumWidth(400)
            layout = QVBoxLayout(self)
            layout.setContentsMargins(20, 20, 20, 20)
            layout.setSpacing(15)

            # 添加说明标签
            tip_label = QLabel('请输入类别名称，多个类别用逗号或换行分隔\n已存在的类别会被自动忽略')
            tip_label.setStyleSheet(f'QLabel {{ color: {c.TEXT_SECONDARY}; }}')
            layout.addWidget(tip_label)

            # 添加文本编辑框
            self.edit = QTextEdit()
            self.edit.setPlaceholderText('例如: 类别1, 类别2\n类别3\n类别4')
            self.edit.setMinimumHeight(100)
            self.edit.setStyleSheet(f"""
                QTextEdit {{
                    background-color: {c.BACKGROUND_SECONDARY};
                    color: {c.TEXT_PRIMARY};
                    border: 1px solid {c.BORDER_MEDIUM};
                    border-radius: 4px;
                    padding: 8px;
                    font-size: 13px;
                }}
            """)
            layout.addWidget(self.edit)

            # 添加预览区域
            preview_group = QWidget()
            preview_layout = QVBoxLayout(preview_group)
            preview_label = QLabel('预览:')
            preview_label.setStyleSheet(f'QLabel {{ color: {c.TEXT_PRIMARY}; font-weight: bold; }}')
            preview_layout.addWidget(preview_label)
            self.preview_list = QListWidget()
            self.preview_list.setMaximumHeight(150)
            self.preview_list.setStyleSheet(f"""
                QListWidget {{
                    background-color: {c.BACKGROUND_SECONDARY};
                    color: {c.TEXT_PRIMARY};
                    border: 1px solid {c.BORDER_MEDIUM};
                    border-radius: 4px;
                    padding: 4px;
                }}
                QListWidget::item {{
                    padding: 4px 8px;
                    border-radius: 3px;
                }}
                QListWidget::item:hover {{
                    background-color: {c.BACKGROUND_HOVER};
                }}
                QListWidget::item:selected {{
                    background-color: {c.PRIMARY};
                    color: white;
                }}
                QListWidget::item:selected:hover {{
                    background-color: {c.PRIMARY_DARK};
                }}
            """)
            preview_layout.addWidget(self.preview_list)
            layout.addWidget(preview_group)

            # 添加按钮
            btn_layout = QHBoxLayout()
            btn_layout.addStretch()  # 左侧弹性空间，让按钮靠右

            # 统一按钮样式：固定padding和height
            button_style_base = """
                padding: 6px 16px;
                font-size: 13px;
                font-weight: 500;
                border-radius: 4px;
                min-height: 24px;
            """

            add_btn = QPushButton('添加')
            add_btn.setMinimumWidth(100)
            add_btn.clicked.connect(self.add_categories)
            add_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {c.PRIMARY};
                    color: white;
                    border: none;
                    {button_style_base}
                }}
                QPushButton:hover {{
                    background-color: {c.PRIMARY_DARK};
                }}
                QPushButton:pressed {{
                    background-color: {c.PRIMARY_DARK};
                }}
            """)

            continue_btn = QPushButton('添加并继续')
            continue_btn.setMinimumWidth(120)
            continue_btn.clicked.connect(self.add_and_continue)
            continue_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {c.SUCCESS};
                    color: white;
                    border: none;
                    {button_style_base}
                }}
                QPushButton:hover {{
                    background-color: {c.SUCCESS_DARK};
                }}
                QPushButton:pressed {{
                    background-color: {c.SUCCESS_DARK};
                }}
            """)

            cancel_btn = QPushButton('取消')
            cancel_btn.setMinimumWidth(100)
            cancel_btn.clicked.connect(self.reject)
            cancel_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {c.GRAY_100};
                    color: {c.TEXT_PRIMARY};
                    border: 1px solid {c.BORDER_LIGHT};
                    {button_style_base}
                }}
                QPushButton:hover {{
                    background-color: {c.BACKGROUND_HOVER};
                    border-color: {c.BORDER_MEDIUM};
                }}
                QPushButton:pressed {{
                    background-color: {c.BACKGROUND_PRESSED};
                }}
            """)

            btn_layout.addWidget(add_btn)
            btn_layout.addWidget(continue_btn)
            btn_layout.addWidget(cancel_btn)
            layout.addLayout(btn_layout)

            # 连接文本变化信号
            self.edit.textChanged.connect(self.update_preview)

        except Exception as e:
            self.logger.error(f"初始化添加类别对话框UI失败: {e}")

    def update_preview(self):
        """更新预览列表"""
        try:
            self.preview_list.clear()
            text = self.edit.toPlainText()
            if not text.strip():
                return

            # 分割文本并处理
            categories = set()
            for line in text.split('\n'):
                # 同时支持中英文逗号
                parts = []
                for part in line.replace('，', ',').split(','):
                    parts.append(part)
                for cat in parts:
                    cat = normalize_folder_name(cat.strip())  # 添加规范化处理
                    if cat and cat not in self.existing_categories and cat not in categories:
                        categories.add(cat)
                        item = QListWidgetItem(cat)
                        self.preview_list.addItem(item)
        except Exception as e:
            self.logger.error(f"更新预览失败: {e}")

    def add_categories(self):
        """添加类别并关闭对话框"""
        if self._add_categories():
            self.accept()

    def _add_categories(self):
        """实际添加类别的逻辑"""
        try:
            text = self.edit.toPlainText()
            if not text.strip():
                return False

            # 分割文本并处理
            added = False
            errors = []  # 记录错误信息

            for line in text.split('\n'):
                # 同时支持中英文逗号
                parts = []
                for part in line.replace('，', ',').split(','):
                    parts.append(part)
                for cat in parts:
                    chinese_name = normalize_folder_name(cat.strip())  # 规范化类别名称
                    if not chinese_name:  # 跳过空类别名
                        continue

                    # 检查类别名称长度
                    if len(chinese_name) > 50:
                        errors.append(f'类别名称 "{chinese_name}" 超过50个字符')
                        continue

                    if chinese_name in self.existing_categories:
                        toast_warning(self, f'类别 "{chinese_name}" 已存在，将跳过')
                        continue

                    try:
                        # 创建目录(直接使用类别名)
                        parent = self.parent()
                        if parent and hasattr(parent, 'current_dir'):
                            category_dir = Path(parent.current_dir).parent / chinese_name
                            def create_dir():
                                category_dir.mkdir(exist_ok=True)
                            retry_file_operation(create_dir)
                            self.added_categories.add(chinese_name)
                            self.existing_categories.add(chinese_name)
                            added = True
                            self.logger.info(f"成功创建类别目录: {category_dir}")
                        else:
                            errors.append(f'无法获取父目录信息')
                    except Exception as e:
                        errors.append(f'创建类别 "{chinese_name}" 失败: {str(e)}')
                        continue

            # 如果有错误但也有成功添加的类别
            if errors and added:
                error_msg = '\n'.join(errors)
                toast_warning(self, f'部分类别添加失败: {error_msg}')
            # 如果只有错误没有成功添加的类别
            elif errors and not added:
                error_msg = '\n'.join(errors)
                toast_error(self, f'添加类别失败: {error_msg}')
                return False

            if added:
                # 强制刷新父窗口的类别列表
                parent = self.parent()
                if parent and hasattr(parent, 'load_categories'):
                    QApplication.processEvents()  # 处理挂起的事件
                    parent.load_categories()
                if parent and hasattr(parent, 'update_category_buttons'):
                    parent.update_category_buttons()

            return added

        except Exception as e:
            self.logger.error(f"添加类别失败: {e}")
            toast_error(self, f'添加类别失败: {str(e)}')
            return False

    def add_and_continue(self):
        """添加类别并清空输入框"""
        try:
            if self._add_categories():
                # 强制刷新父窗口类别按钮
                parent = self.parent()
                if parent and hasattr(parent, 'load_categories'):
                    QApplication.processEvents()  # 处理挂起的事件
                    parent.load_categories()
                if parent and hasattr(parent, 'update_category_buttons'):
                    parent.update_category_buttons()

                # 清空输入框并更新预览
                self.edit.clear()
                self.preview_list.clear()
                self.edit.setFocus()

                # 重置已添加类别集合
                self.added_categories = set()

                # 强制更新UI
                self.update()
                QApplication.processEvents()
        except Exception as e:
            self.logger.error(f"添加并继续失败: {e}")

    def showEvent(self, event):
        """对话框显示时居中"""
        super().showEvent(event)
        if not self._centered:
            self._center_on_parent()
            self._centered = True

    def _center_on_parent(self):
        """将对话框居中显示在父窗口上"""
        try:
            parent = self.parent()
            if parent:
                # 获取父窗口的几何信息
                parent_geometry = parent.geometry()
                # 计算对话框应该显示的位置（父窗口中心）
                x = parent_geometry.x() + (parent_geometry.width() - self.width()) // 2
                y = parent_geometry.y() + (parent_geometry.height() - self.height()) // 2
                # 移动对话框到计算出的位置
                self.move(x, y)
                self.logger.debug(f"对话框已居中: x={x}, y={y}")
        except Exception as e:
            self.logger.error(f"居中对话框失败: {e}")
