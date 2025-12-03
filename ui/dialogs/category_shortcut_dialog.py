"""类别快捷键设置对话框模块"""

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton

from ..components.styles import ButtonStyles, DialogStyles
from ..components.styles.theme import default_theme
from ..components.toast import toast_success, toast_warning


class CategoryShortcutDialog(QDialog):
    """类别快捷键设置对话框"""

    def __init__(self, config, category, parent=None):
        super().__init__(parent)
        self.config = config
        self.category = category
        self.logger = logging.getLogger(__name__)

        self.setWindowTitle(f'设置类别"{category}"的快捷键')
        self.setModal(True)

        # 应用主题样式
        c = default_theme.colors
        self.setStyleSheet(DialogStyles.get_form_dialog_style())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # 创建快捷键编辑区域
        row = QHBoxLayout()
        label = QLabel('快捷键:')
        label.setStyleSheet(f"QLabel {{ color: {c.TEXT_PRIMARY}; }}")
        self.edit = QLineEdit(self.config.category_shortcuts.get(category, ''))
        self.edit.setReadOnly(True)
        self.edit.setPlaceholderText('点击此处按下新的快捷键')
        row.addWidget(label)
        row.addWidget(self.edit)
        layout.addLayout(row)

        # 添加说明标签
        tip_label = QLabel('支持单个按键或组合键(Ctrl+, Alt+, Shift+)\n按ESC清除快捷键')
        tip_label.setStyleSheet(f"QLabel {{ color: {c.TEXT_SECONDARY}; }}")
        layout.addWidget(tip_label)

        # 添加确定和取消按钮
        buttons = QHBoxLayout()
        ok_btn = QPushButton('确定')
        cancel_btn = QPushButton('取消')
        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)

        # 应用按钮样式
        ok_btn.setStyleSheet(ButtonStyles.get_primary_button_style())
        cancel_btn.setStyleSheet(ButtonStyles.get_secondary_button_style(""))

        buttons.addWidget(ok_btn)
        buttons.addWidget(cancel_btn)
        layout.addLayout(buttons)

    def keyPressEvent(self, event):
        """处理按键事件"""
        try:
            if event.key() == Qt.Key.Key_Escape:
                self.edit.clear()
                if self.category in self.config.category_shortcuts:
                    del self.config.category_shortcuts[self.category]
                return

            # 获取修饰键
            modifiers = event.modifiers()
            key = event.key()

            # 忽略单独的修饰键
            if key in (Qt.Key.Key_Control, Qt.Key.Key_Alt, Qt.Key.Key_Shift):
                return

            # 构建快捷键文本
            key_text = QKeySequence(key).toString()
            if not key_text:
                return

            shortcut = ''
            if modifiers & Qt.KeyboardModifier.ControlModifier:
                shortcut += 'Ctrl+'
            if modifiers & Qt.KeyboardModifier.AltModifier:
                shortcut += 'Alt+'
            if modifiers & Qt.KeyboardModifier.ShiftModifier:
                shortcut += 'Shift+'
            shortcut += key_text

            # 检查快捷键是否可用
            if not self.config.is_shortcut_available(shortcut):
                # 详细检查冲突原因
                normalized_shortcut = self.config._normalize_shortcut(shortcut)

                # 获取主窗口用于显示Toast
                main_window = self.parent()
                while main_window and not hasattr(main_window, 'current_index'):
                    main_window = main_window.parent()
                toast_parent = main_window if main_window else self

                # 检查是否为保留快捷键
                if normalized_shortcut in self.config.reserved_shortcuts:
                    toast_warning(toast_parent, f'快捷键 "{shortcut}" 是系统保留快捷键，不能使用')
                else:
                    # 找出使用该快捷键的类别（大小写不敏感）
                    conflict_category = None
                    conflict_key = None
                    for cat, key in self.config.category_shortcuts.items():
                        if cat != self.category and self.config._normalize_shortcut(key) == normalized_shortcut:
                            conflict_category = cat
                            conflict_key = key
                            break

                    if conflict_category:
                        case_note = ""
                        if conflict_key != shortcut:
                            case_note = f"\n\n注意：该快捷键已以 \"{conflict_key}\" 的形式被使用。\n字母快捷键不区分大小写。"

                        toast_warning(toast_parent, f'快捷键 "{shortcut}" 已被类别 "{conflict_category}" 使用，请选择其他快捷键')
                    else:
                        toast_warning(toast_parent, f'快捷键 "{shortcut}" 已被占用，请选择其他快捷键')
                return

            # 统一存储格式：单字母快捷键存储为小写
            stored_shortcut = shortcut
            if len(shortcut) == 1 and shortcut.isalpha():
                stored_shortcut = shortcut.lower()
            elif '+' in shortcut:
                # 组合键，只将最后的字母部分转为小写
                parts = shortcut.split('+')
                if len(parts[-1]) == 1 and parts[-1].isalpha():
                    parts[-1] = parts[-1].lower()
                    stored_shortcut = '+'.join(parts)

            self.edit.setText(shortcut)  # 显示用户输入的原始格式
            self.config.category_shortcuts[self.category] = stored_shortcut  # 存储标准化格式

        except Exception as e:
            self.logger.error(f"处理快捷键事件失败: {e}")

    def accept(self):
        """确认按钮点击时的处理"""
        shortcut = self.edit.text().strip()
        if shortcut:
            # 获取主窗口用于显示Toast
            main_window = self.parent()
            while main_window and not hasattr(main_window, 'current_index'):
                main_window = main_window.parent()
            toast_parent = main_window if main_window else self
            toast_success(toast_parent, f'类别 "{self.category}" 快捷键已设置为 "{shortcut}"')

        # 调用父类的accept方法
        super().accept()
