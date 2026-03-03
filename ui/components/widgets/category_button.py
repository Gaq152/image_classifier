"""
分类按钮组件

自定义的类别按钮组件，支持快捷键显示、计数、右键菜单、多分类状态等功能。

Phase 2.5 重构：使用信号机制替代 Parent Reaching 反模式
- 所有业务操作通过信号通知父组件，而不是直接调用 main_window 方法
"""

import logging
from PyQt6.QtWidgets import (QPushButton, QLabel, QHBoxLayout, QDialog, QVBoxLayout,
                            QLineEdit, QMenu, QMessageBox)
from PyQt6.QtCore import Qt, pyqtSignal

from ..toast import toast_error
from ..styles import apply_category_button_style, WidgetStyles, ButtonStyles
from ..styles.theme import default_theme


class CategoryButton(QPushButton):
    """自定义类别按钮

    信号（Phase 2.5 重构）：
        rename_requested: 请求重命名类别 (old_name, new_name)
        shortcut_change_requested: 请求修改快捷键 (category_name)
        ignore_requested: 请求忽略类别 (category_name)
        delete_requested: 请求删除类别 (category_name)
        manage_ignored_requested: 请求打开管理忽略类别对话框
        classify_requested: 请求分类到该类别 (category_name) - 双击触发
    """

    # 信号定义
    rename_requested = pyqtSignal(str, str)  # old_name, new_name
    shortcut_change_requested = pyqtSignal(str)  # category_name
    ignore_requested = pyqtSignal(str)  # category_name
    delete_requested = pyqtSignal(str)  # category_name
    manage_ignored_requested = pyqtSignal()
    classify_requested = pyqtSignal(str)  # category_name

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

    def update_style(self):
        """更新按钮样式（主题切换时调用）"""
        apply_category_button_style(self)
        self.update_label_colors()
        # 强制刷新样式
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

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
            self.logger.error(f"显示右键菜单失败: {e}")
            toast_error(self, f"显示菜单失败: {e}")

    def rename_category(self):
        """重命名类别 - 显示对话框并发射信号"""
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
                    # Phase 2.5: 使用信号通知父组件
                    self.rename_requested.emit(self.category_name, new_name)

        except Exception as e:
            self.logger.error(f"重命名对话框失败: {e}")
            toast_error(self, f"重命名失败: {e}")

    def change_shortcut(self):
        """修改快捷键 - 发射信号让父组件处理"""
        try:
            # Phase 2.5: 直接发射信号，让父组件处理对话框和后续逻辑
            self.shortcut_change_requested.emit(self.category_name)
        except Exception as e:
            self.logger.error(f"请求修改快捷键失败: {e}")
            toast_error(self, f"修改快捷键失败: {e}")

    def manage_ignored_categories(self):
        """管理忽略的类别列表 - 发射信号让父组件处理"""
        try:
            # Phase 2.5: 发射信号让父组件打开对话框
            self.manage_ignored_requested.emit()
        except Exception as e:
            self.logger.error(f"请求管理忽略类别失败: {e}")
            toast_error(self, f"打开管理对话框失败: {e}")

    def change_sort_mode(self, new_mode):
        """切换排序模式 - 该功能已迁移到 CategoryPanel，此方法保留以兼容旧代码"""
        # Phase 2.5: 排序模式切换已由 CategoryPanel 直接处理
        # 此方法仅保留空实现以防止旧代码调用报错
        self.logger.warning(f"change_sort_mode 已弃用，排序模式切换请使用 CategoryPanel")

    def ignore_category(self):
        """忽略类别 - 显示确认对话框并发射信号"""
        try:
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
                # Phase 2.5: 使用信号通知父组件
                self.ignore_requested.emit(self.category_name)

        except Exception as e:
            self.logger.error(f"忽略类别对话框失败: {e}")
            toast_error(self, f"忽略类别失败: {e}")

    def delete_category(self):
        """删除类别 - 显示确认对话框并发射信号"""
        try:
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
                # Phase 2.5: 使用信号通知父组件
                self.delete_requested.emit(self.category_name)

        except Exception as e:
            self.logger.error(f"删除类别对话框失败: {e}")
            toast_error(self, f"删除类别失败: {e}")

    def mousePressEvent(self, event):
        """处理鼠标按下事件"""
        if event.button() == Qt.MouseButton.RightButton:
            self.show_context_menu(event.pos())
        else:
            super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        """处理双击事件 - 发射分类信号"""
        if not self.is_remove:
            # Phase 2.5: 双击时发射分类请求信号，让父组件处理分类逻辑
            self.classify_requested.emit(self.category_name)
        event.accept()