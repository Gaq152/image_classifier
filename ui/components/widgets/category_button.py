"""
分类按钮组件

自定义的类别按钮组件，支持快捷键显示、计数、右键菜单、多分类状态等功能。
"""

import logging
from PyQt6.QtWidgets import (QPushButton, QLabel, QHBoxLayout, QDialog, QVBoxLayout,
                            QLineEdit, QMenu, QMessageBox)
from PyQt6.QtCore import Qt

from ....utils.file_operations import normalize_folder_name, retry_file_operation
from ....utils.exceptions import FileOperationError
from ...dialogs import CategoryShortcutDialog
from ..toast import toast_warning, toast_error, toast_floating
from ..styles import apply_category_button_style, WidgetStyles, ButtonStyles
from ..styles.theme import default_theme


class CategoryButton(QPushButton):
    """自定义类别按钮"""

    def __init__(self, category_name, config, is_remove=False, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(30)
        self.setMaximumWidth(250)
        self.is_remove = is_remove
        self.category_name = category_name  # 直接使用类别名称
        self.chinese_name = category_name  # 保持向后兼容
        self.config = config
        self.count = 0
        self.is_multi_classified = False  # 添加多分类状态标记
        self.logger = logging.getLogger(__name__)

        # 创建内部布局
        self.inner_layout = QHBoxLayout(self)
        self.inner_layout.setContentsMargins(8, 0, 8, 0)
        self.inner_layout.setSpacing(4)

        # 创建标签
        self.text_label = QLabel()
        self.count_label = QLabel()
        self.count_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.count_label.setMinimumWidth(30)
        font = self.count_label.font()
        font.setBold(True)
        self.count_label.setFont(font)

        self.inner_layout.addWidget(self.text_label, 1)
        self.inner_layout.addWidget(self.count_label, 0)

        # 更新文本
        self.update_text()

        # 使用统一的样式系统
        apply_category_button_style(self)

        # 更新标签颜色以匹配主题
        self.update_label_colors()

    def update_text(self):
        """更新按钮文本"""
        try:
            shortcut = self.config.category_shortcuts.get(self.category_name, '')
            if shortcut:
                text = f"[{shortcut}] {self.category_name}"
            else:
                text = self.category_name
            self.text_label.setText(text)
        except Exception as e:
            self.logger.error(f"更新按钮文本失败: {e}")
            self.text_label.setText(self.category_name)

    def set_count(self, count):
        """设置计数"""
        self.count = count
        self.count_label.setText(str(count))

    def set_classified(self, classified):
        """设置分类状态"""
        self.setProperty("classified", classified)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update_label_colors()  # 更新标签颜色

    def set_removed(self, removed):
        """设置移除状态"""
        self.setProperty("removed", removed)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update_label_colors()  # 更新标签颜色

    def set_multi_classified(self, multi_classified):
        """设置多分类状态"""
        self.is_multi_classified = multi_classified
        self.setProperty("multi_classified", multi_classified)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update_label_colors()  # 更新标签颜色
        if multi_classified:
            self.logger.debug(f"设置多分类标记: {self.category_name}")

    def update_label_colors(self):
        """更新标签颜色以匹配当前主题"""
        try:
            # 获取当前按钮状态
            is_classified = self.property("classified")
            is_removed = self.property("removed")
            is_multi = self.property("multi_classified")
            is_checked = self.isChecked()

            # 根据状态选择颜色
            if is_classified or is_multi or is_removed or is_checked:
                # 有彩色背景的状态：使用白色（深色主题）或深色（浅色主题）
                if default_theme.is_dark:
                    color = "#FFFFFF"
                else:
                    color = default_theme.colors.GRAY_800
            else:
                # 普通状态：使用主题的 TEXT_PRIMARY
                color = default_theme.colors.TEXT_PRIMARY

            # 应用颜色到标签
            label_style = f"color: {color}; background: transparent; border: none;"
            self.text_label.setStyleSheet(label_style)
            self.count_label.setStyleSheet(label_style)

        except Exception as e:
            self.logger.error(f"更新标签颜色失败: {e}")

    def show_context_menu(self, pos):
        """显示右键菜单"""
        try:
            menu = QMenu(self)

            # 应用主题样式
            menu.setStyleSheet(WidgetStyles.get_context_menu_style())

            # 修改类别名称
            rename_action = menu.addAction("🏷️ 修改类别名称")
            rename_action.triggered.connect(self.rename_category)

            # 修改快捷键
            shortcut_action = menu.addAction("⌨️ 修改快捷键")
            shortcut_action.triggered.connect(self.change_shortcut)

            menu.addSeparator()

            # 忽略类别（如果不是移除按钮）
            if not self.is_remove:
                ignore_action = menu.addAction("⊘ 忽略该类别")
                ignore_action.triggered.connect(self.ignore_category)

            # 管理忽略类别
            manage_ignored_action = menu.addAction("⚙️ 管理忽略类别")
            manage_ignored_action.triggered.connect(self.manage_ignored_categories)

            menu.addSeparator()

            # 删除类别（如果不是移除按钮）
            if not self.is_remove:
                delete_action = menu.addAction("🗑️ 删除类别")
                delete_action.triggered.connect(self.delete_category)

            # 显示菜单
            menu.exec(self.mapToGlobal(pos))

        except Exception as e:
            # 获取主窗口用于显示Toast
            main_window = self.parent()
            while main_window and not hasattr(main_window, 'show_error_toast'):
                main_window = main_window.parent()
            if main_window:
                main_window.show_error_toast(f"显示菜单失败: {e}")
            else:
                toast_error(self, f"显示菜单失败: {e}")

    def rename_category(self):
        """重命名类别"""
        try:

            # 创建自定义对话框
            dialog = QDialog(self)
            dialog.setWindowTitle("修改类别名称")
            dialog.setModal(True)
            dialog.setFixedSize(350, 150)

            # 使用统一的样式系统
            dialog.setStyleSheet(WidgetStyles.get_custom_rename_dialog_style())

            layout = QVBoxLayout(dialog)
            layout.setSpacing(15)
            layout.setContentsMargins(20, 20, 20, 20)

            # 标签
            label = QLabel(f"请输入新的类别名称:")
            layout.addWidget(label)

            # 输入框
            line_edit = QLineEdit(self.category_name)
            line_edit.selectAll()
            layout.addWidget(line_edit)

            # 按钮
            button_layout = QHBoxLayout()
            button_layout.addStretch()

            ok_button = QPushButton("确定")
            ok_button.clicked.connect(dialog.accept)
            ok_button.setDefault(True)
            button_layout.addWidget(ok_button)

            cancel_button = QPushButton("取消")
            cancel_button.setObjectName("cancelButton")
            cancel_button.clicked.connect(dialog.reject)
            button_layout.addWidget(cancel_button)

            layout.addLayout(button_layout)

            # 设置焦点
            line_edit.setFocus()

            # 显示对话框
            if dialog.exec() == QDialog.DialogCode.Accepted:
                new_name = line_edit.text().strip()
                if new_name and new_name != self.category_name:
                    main_window = self.window()
                    if main_window and hasattr(main_window, 'rename_category'):
                        main_window.rename_category(self.category_name, new_name)

        except Exception as e:
            # 获取主窗口用于显示Toast
            main_window = self.parent()
            while main_window and not hasattr(main_window, 'show_error_toast'):
                main_window = main_window.parent()
            if main_window:
                main_window.show_error_toast(f"重命名失败: {e}")
            else:
                toast_error(self, f"重命名失败: {e}")

    def change_shortcut(self):
        """修改快捷键"""
        try:

            main_window = self.window()
            if main_window and hasattr(main_window, 'config'):
                dialog = CategoryShortcutDialog(main_window.config, self.category_name, self)
                if dialog.exec():
                    # 保存配置
                    main_window.config.save_config()
                    self.logger.info(f"快捷键已修改并保存: {self.category_name}")
                    # 重新设置快捷键
                    main_window.setup_shortcuts()

                    # 重新计算排序列表（特别是"按快捷键排序"模式）
                    categories = getattr(main_window, 'categories', None)
                    if categories is not None:
                        category_counts = None
                        if main_window.config.category_sort_mode == "count":
                            category_counts = main_window._get_category_counts()
                        main_window.ordered_categories = main_window.config.get_sorted_categories(
                            categories, category_counts=category_counts
                        )

                    # 更新类别按钮列表（重新排序）
                    main_window.update_category_buttons()
                    self.logger.info(f"类别按钮列表已更新")
                    # 更新当前按钮文本
                    self.update_text()

        except Exception as e:
            # 获取主窗口用于显示Toast
            main_window = self.parent()
            while main_window and not hasattr(main_window, 'show_error_toast'):
                main_window = main_window.parent()
            if main_window:
                main_window.show_error_toast(f"修改快捷键失败: {e}")
            else:
                toast_error(self, f"修改快捷键失败: {e}")

    def manage_ignored_categories(self):
        """管理忽略的类别列表"""
        try:
            main_window = self.window()
            if main_window and hasattr(main_window, 'show_manage_ignored_dialog'):
                main_window.show_manage_ignored_dialog()
        except Exception as e:
            # 获取主窗口用于显示Toast
            main_window = self.parent()
            while main_window and not hasattr(main_window, 'show_error_toast'):
                main_window = main_window.parent()
            if main_window:
                main_window.show_error_toast(f"打开管理对话框失败: {e}")
            else:
                toast_error(self, f"打开管理对话框失败: {e}")

    def change_sort_mode(self, new_mode):
        """切换排序模式"""
        try:
            main_window = self.window()
            if main_window and hasattr(main_window, 'change_category_sort_mode'):
                main_window.change_category_sort_mode(new_mode)
        except Exception as e:
            # 获取主窗口用于显示Toast
            main_window = self.parent()
            while main_window and not hasattr(main_window, 'show_error_toast'):
                main_window = main_window.parent()
            if main_window:
                main_window.show_error_toast(f"切换排序模式失败: {e}")
            else:
                toast_error(self, f"切换排序模式失败: {e}")

    def ignore_category(self):
        """忽略类别"""
        try:
            from ..styles.theme import default_theme
            c = default_theme.colors

            # 创建自定义消息框
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("⊘ 确认忽略")
            msg_box.setText(f"确定要忽略类别 '{self.category_name}' 吗？")
            msg_box.setInformativeText("注意：忽略后该目录将不再显示在类别列表中，但目录和文件不会被删除！")
            msg_box.setIcon(QMessageBox.Icon.Question)

            # 创建中文按钮
            yes_button = QPushButton("是")
            no_button = QPushButton("否")

            msg_box.addButton(yes_button, QMessageBox.ButtonRole.YesRole)
            msg_box.addButton(no_button, QMessageBox.ButtonRole.NoRole)

            # 设置默认按钮为"否"
            msg_box.setDefaultButton(no_button)

            # 使用主题样式
            message_box_style = f"""
                QMessageBox {{
                    background-color: {c.BACKGROUND_CARD};
                    color: {c.TEXT_PRIMARY};
                }}
                QMessageBox QLabel {{
                    color: {c.TEXT_PRIMARY};
                    font-size: 14px;
                }}
                {ButtonStyles.get_primary_button_style()}
            """
            msg_box.setStyleSheet(message_box_style)

            # 显示对话框并处理结果
            msg_box.exec()
            clicked_button = msg_box.clickedButton()

            if clicked_button == yes_button:
                main_window = self.window()
                if main_window and hasattr(main_window, 'ignore_category'):
                    main_window.ignore_category(self.category_name)

        except Exception as e:
            # 获取主窗口用于显示Toast
            main_window = self.parent()
            while main_window and not hasattr(main_window, 'show_error_toast'):
                main_window = main_window.parent()
            if main_window:
                main_window.show_error_toast(f"忽略类别失败: {e}")
            else:
                toast_error(self, f"忽略类别失败: {e}")

    def delete_category(self):
        """删除类别"""
        try:
            from ..styles.theme import default_theme
            c = default_theme.colors

            # 创建自定义消息框
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("🗑️ 确认删除")
            msg_box.setText(f"确定要删除类别 '{self.category_name}' 吗？")
            msg_box.setInformativeText("注意：这将删除对应的文件夹及其中的所有文件！")
            msg_box.setIcon(QMessageBox.Icon.Question)

            # 创建中文按钮
            yes_button = QPushButton("是")
            no_button = QPushButton("否")

            msg_box.addButton(yes_button, QMessageBox.ButtonRole.YesRole)
            msg_box.addButton(no_button, QMessageBox.ButtonRole.NoRole)

            # 设置默认按钮为"否"
            msg_box.setDefaultButton(no_button)

            # 使用主题样式
            message_box_style = f"""
                QMessageBox {{
                    background-color: {c.BACKGROUND_CARD};
                    color: {c.TEXT_PRIMARY};
                }}
                QMessageBox QLabel {{
                    color: {c.TEXT_PRIMARY};
                    font-size: 14px;
                }}
                {ButtonStyles.get_primary_button_style()}
            """
            msg_box.setStyleSheet(message_box_style)

            # 显示对话框并处理结果
            msg_box.exec()
            clicked_button = msg_box.clickedButton()

            if clicked_button == yes_button:
                main_window = self.window()
                if main_window and hasattr(main_window, 'delete_category'):
                    main_window.delete_category(self.category_name)

        except Exception as e:
            # 获取主窗口用于显示Toast
            main_window = self.parent()
            while main_window and not hasattr(main_window, 'show_error_toast'):
                main_window = main_window.parent()
            if main_window:
                main_window.show_error_toast(f"删除类别失败: {e}")
            else:
                toast_error(self, f"删除类别失败: {e}")

    def mousePressEvent(self, event):
        """处理鼠标按下事件"""
        if event.button() == Qt.MouseButton.RightButton:
            self.show_context_menu(event.pos())
        else:
            super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        """处理双击事件 - 支持多分类模式下的选中/取消选择"""
        if not self.is_remove:
            # 获取主窗口并调用分类方法
            main_window = self.window()
            if main_window:
                # 在多分类模式下，双击可以选中或取消选择
                if main_window.is_multi_category:
                    # 多分类模式：双击切换选择状态
                    main_window.move_to_category(self.category_name)
                else:
                    # 单分类模式：保持原有逻辑，检查是否已分类
                    if hasattr(main_window, 'image_files') and hasattr(main_window, 'current_index') and main_window.image_files:
                        if 0 <= main_window.current_index < len(main_window.image_files):
                            current_path = str(main_window.image_files[main_window.current_index])
                            current_category = main_window.classified_images.get(current_path)

                            # 检查是否已分类到该类别
                            already_classified = False
                            if isinstance(current_category, list):
                                already_classified = self.category_name in current_category
                            else:
                                already_classified = current_category == self.category_name

                            # 多分类模式下，已分类的图片再次点击会触发撤销，所以需要继续执行
                            # 单分类模式下，也需要支持撤销，所以也要继续执行
                            # 删除原有的"避免重复处理"逻辑，让 move_to_category 方法处理撤销逻辑

                    # 如果未分类或分类到其他类别，则进行分类操作
                    main_window.move_to_category(self.category_name)
        event.accept()