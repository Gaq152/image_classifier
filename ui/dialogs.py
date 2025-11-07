"""
对话框模块

包含应用程序使用的各种对话框组件。
"""

import logging
import os
import sys
import subprocess
import shutil
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, unquote
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                            QPushButton, QTextEdit, QListWidget, QListWidgetItem,
                            QMessageBox, QTabWidget, QProgressBar, QApplication,
                            QWidget, QTextBrowser, QCheckBox, QGroupBox, QScrollArea, QComboBox,
                            QDoubleSpinBox)
from PyQt6.QtCore import Qt, pyqtSignal, QUrl, QPropertyAnimation, QEasingCurve, QRectF, pyqtProperty, QTimer
from PyQt6.QtGui import QKeySequence, QIcon, QDesktopServices, QPainter, QColor, QPen
from ..utils.file_operations import normalize_folder_name, retry_file_operation
from .._version_ import compare_version, __version__
from ..utils.exceptions import FileOperationError
from .._version_ import get_about_info, get_latest_version_info, VERSION_HISTORY, get_manifest_url, CONTACT_INFO
from ..core.update_utils import fetch_manifest, download_with_progress, sha256_file, launch_self_update
from ..utils.app_config import get_app_config
from .components.toast import toast_info, toast_success, toast_warning, toast_error
from .components.styles.theme import default_theme
from .components.styles import ButtonStyles
from .update_dialog import UpdateInfoDialog
from .components.widgets.switch import Switch


class AnimatedToggle(QWidget):
    """带有流畅滑动动画的Toggle开关组件"""
    clicked = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._checked = False
        self._circle_position = 2  # 滑块位置

        # 尺寸设置
        self.setFixedSize(44, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        # 动画设置
        self.animation = QPropertyAnimation(self, b"circle_position", self)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.animation.setDuration(200)  # 200ms的动画时长

    @pyqtProperty(float)
    def circle_position(self):
        return self._circle_position

    @circle_position.setter
    def circle_position(self, pos):
        self._circle_position = pos
        self.update()

    def paintEvent(self, event):
        """绘制Toggle开关"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 绘制背景轨道
        if self._checked:
            track_color = QColor("#66bb6a")  # 绿色（选中）
        else:
            track_color = QColor("#cfd8dc")  # 灰色（未选中）

        painter.setBrush(track_color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(0, 0, self.width(), self.height(), 12, 12)

        # 绘制滑块
        painter.setBrush(QColor("#FFFFFF"))
        circle_radius = 10
        painter.drawEllipse(
            int(self._circle_position),
            int((self.height() - circle_radius * 2) / 2),
            circle_radius * 2,
            circle_radius * 2
        )

    def mousePressEvent(self, event):
        """点击切换状态"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.setChecked(not self._checked)
            self.clicked.emit(self._checked)

    def setChecked(self, checked):
        """设置选中状态"""
        if self._checked == checked:
            return

        self._checked = checked

        # 启动动画
        if checked:
            # 移动到右侧
            self.animation.setStartValue(self._circle_position)
            self.animation.setEndValue(self.width() - 22)  # 44 - 20(圆直径) - 2(边距)
        else:
            # 移动到左侧
            self.animation.setStartValue(self._circle_position)
            self.animation.setEndValue(2)

        self.animation.start()

    def isChecked(self):
        """获取选中状态"""
        return self._checked


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
        from .components.styles import DialogStyles
        from .components.styles.theme import default_theme
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
        from .components.styles import ButtonStyles
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
            from .components.styles import DialogStyles, ButtonStyles
            from .components.styles.theme import default_theme
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
            for line in text.split('\n'):  # 修复：使用正确的换行符
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
            
            for line in text.split('\n'):  # 修复：使用正确的换行符
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


class TabbedHelpDialog(QDialog):
    """带标签页的帮助对话框"""
    
    def __init__(self, version, parent=None, config=None):
        super().__init__(parent)
        self.version = version
        self.config = getattr(parent, 'config', None) if config is None else config
        self.logger = logging.getLogger(__name__)
        self.initUI()
    
    def _get_resource_path(self, relative_path):
        """获取资源文件路径，兼容开发环境和打包环境"""
        try:

            # PyInstaller 打包后的临时目录
            if hasattr(sys, '_MEIPASS'):
                base_path = Path(sys._MEIPASS)
                resource_path = base_path / relative_path
                if resource_path.exists():
                    return resource_path
                
            # 开发环境 - 从当前文件位置查找
            base_path = Path(__file__).parent.parent
            resource_path = base_path / relative_path
            if resource_path.exists():
                return resource_path
                
            # 尝试从程序运行目录查找
            base_path = Path.cwd()
            resource_path = base_path / relative_path
            if resource_path.exists():
                return resource_path
                
            return None
        except Exception:
            return None
        
    def _get_html_colors(self):
        """获取用于 HTML 内容的主题颜色映射"""
        c = default_theme.colors
        return {
            'bg_primary': c.BACKGROUND_PRIMARY,
            'bg_secondary': c.BACKGROUND_SECONDARY,
            'bg_hover': c.BACKGROUND_HOVER,
            'text_primary': c.TEXT_PRIMARY,
            'text_secondary': c.TEXT_SECONDARY,
            'border': c.BORDER_MEDIUM,
            'primary': c.PRIMARY,
            'primary_light': c.PRIMARY_LIGHT,
        }

    def _get_dialog_style(self):
        """根据当前主题获取对话框样式"""
        c = default_theme.colors

        return f"""
                QDialog {{
                    background-color: {c.BACKGROUND_PRIMARY};
                    color: {c.TEXT_PRIMARY};
                }}
                QTabWidget {{
                    background-color: {c.BACKGROUND_PRIMARY};
                    border: 1px solid {c.BORDER_MEDIUM};
                    border-radius: 4px;
                }}
                QTabWidget::pane {{
                    background-color: {c.BACKGROUND_PRIMARY};
                    border: 1px solid {c.BORDER_MEDIUM};
                    border-radius: 4px;
                    top: -1px;
                }}
                QTabBar::tab {{
                    background-color: {c.BACKGROUND_SECONDARY};
                    color: {c.TEXT_SECONDARY};
                    border: 1px solid {c.BORDER_MEDIUM};
                    padding: 8px 16px;
                    margin-right: 2px;
                    border-top-left-radius: 4px;
                    border-top-right-radius: 4px;
                    font-weight: normal;
                    min-width: 80px;
                }}
                QTabBar::tab:selected {{
                    background-color: {c.BACKGROUND_PRIMARY};
                    color: {c.TEXT_PRIMARY};
                    border-bottom-color: {c.BACKGROUND_PRIMARY};
                    font-weight: 500;
                }}
                QTabBar::tab:hover {{
                    background-color: {c.BACKGROUND_HOVER};
                }}
                QTabBar::tab:selected:hover {{
                    background-color: {c.BACKGROUND_PRIMARY};
                }}
                QPushButton {{
                    background-color: {c.PRIMARY};
                    color: white;
                    border: none;
                    border-radius: 4px;
                    padding: 8px 16px;
                    font-size: 13px;
                    font-weight: normal;
                    min-width: 80px;
                }}
                QPushButton:hover {{
                    background-color: {c.PRIMARY_DARK};
                }}
                QPushButton:pressed {{
                    background-color: {c.PRIMARY_DARK};
                }}
                QPushButton#clearCacheBtn {{
                    background-color: {c.WARNING};
                }}
                QPushButton#clearCacheBtn:hover {{
                    background-color: {c.WARNING_DARK};
                }}
                QPushButton#clearCacheBtn:pressed {{
                    background-color: {c.WARNING_DARK};
                }}
                QTextBrowser {{
                    background-color: {c.BACKGROUND_PRIMARY};
                    color: {c.TEXT_PRIMARY};
                    border: none;
                    selection-background-color: {c.PRIMARY};
                    selection-color: white;
                }}
                QLabel {{
                    color: {c.TEXT_PRIMARY};
                }}
            """

    def _apply_theme(self):
        """应用主题到对话框"""
        try:
            c = default_theme.colors

            # 更新对话框样式
            self.setStyleSheet(self._get_dialog_style())

            # 更新所有 QTextBrowser 的样式并重新生成HTML内容
            if hasattr(self, 'findChildren'):
                # 找到所有QTextBrowser并重新生成其HTML内容
                tab_widget = self.findChild(QTabWidget)
                if tab_widget:
                    for i in range(tab_widget.count()):
                        tab = tab_widget.widget(i)
                        if tab:
                            text_browser = tab.findChild(QTextBrowser)
                            if text_browser:
                                # 更新样式
                                text_browser.setStyleSheet(f"""
                                    QTextBrowser {{
                                        background-color: {c.BACKGROUND_PRIMARY};
                                        color: {c.TEXT_PRIMARY};
                                        font-size: 13px;
                                        line-height: 1.6;
                                        selection-background-color: {c.PRIMARY};
                                        selection-color: white;
                                        border: none;
                                    }}
                                """)

                                # 根据标签页名称重新生成HTML内容
                                tab_title = tab_widget.tabText(i)
                                if tab_title == '快速入门':
                                    text_browser.setHtml(self._generate_quick_start_html())
                                elif tab_title == '使用指南':
                                    text_browser.setHtml(self._generate_help_html())
                                elif tab_title == '高级功能':
                                    text_browser.setHtml(self._generate_advanced_html())
                                elif tab_title == '常见问题':
                                    text_browser.setHtml(self._generate_faq_html())
                                elif tab_title == '关于':
                                    text_browser.setHtml(self._generate_about_html())

            # 强制重绘
            self.update()
        except Exception as e:
            self.logger.error(f"应用主题失败: {e}")

    def initUI(self):
        """初始化UI"""
        try:
            self.setWindowTitle('帮助和关于')
            self.setMinimumSize(700, 500)
            self.setModal(True)

            # 设置对话框整体样式
            self.setStyleSheet(self._get_dialog_style())

            # 旧的样式代码已移到_get_dialog_style方法中
            old_style = """
                QDialog {
                    background-color: #FFFFFF;
                    color: #212121;
                }
                QTabWidget {
                    background-color: #FFFFFF;
                    border: 1px solid #E0E0E0;
                    border-radius: 4px;
                }
                QTabWidget::pane {
                    background-color: #FFFFFF;
                    border: 1px solid #E0E0E0;
                    border-radius: 4px;
                    top: -1px;
                }
                QTabBar::tab {
                    background-color: #F5F5F5;
                    color: #616161;
                    border: 1px solid #E0E0E0;
                    padding: 8px 16px;
                    margin-right: 2px;
                    border-top-left-radius: 4px;
                    border-top-right-radius: 4px;
                    font-weight: normal;
                    min-width: 80px;
                }
                QTabBar::tab:selected {
                    background-color: #FFFFFF;
                    color: #212121;
                    border-bottom-color: #FFFFFF;
                    font-weight: 500;
                }
                QTabBar::tab:hover {
                    background-color: #EEEEEE;
                }
                QTabBar::tab:selected:hover {
                    background-color: #FFFFFF;
                }
                QPushButton {
                    background-color: #3498DB;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    padding: 8px 16px;
                    font-size: 13px;
                    font-weight: normal;
                    min-width: 80px;
                }
                QPushButton:hover {
                    background-color: #2980B9;
                }
                QPushButton:pressed {
                    background-color: #21618C;
                }
                QPushButton#clearCacheBtn {
                    background-color: #FF9800;
                }
                QPushButton#clearCacheBtn:hover {
                    background-color: #F57C00;
                }
                QPushButton#clearCacheBtn:pressed {
                    background-color: #E65100;
                }
            """
            
            layout = QVBoxLayout(self)

            # 创建标签页控件
            tab_widget = QTabWidget()

            # 添加快速入门标签页
            quick_start_tab = self.create_quick_start_tab()
            tab_widget.addTab(quick_start_tab, '快速入门')

            # 添加详细帮助标签页
            help_tab = self.create_help_tab()
            tab_widget.addTab(help_tab, '使用指南')

            # 添加高级功能标签页
            advanced_tab = self.create_advanced_tab()
            tab_widget.addTab(advanced_tab, '高级功能')

            # 添加常见问题标签页
            faq_tab = self.create_faq_tab()
            tab_widget.addTab(faq_tab, '常见问题')

            # 添加关于标签页
            about_tab = self.create_about_tab()
            tab_widget.addTab(about_tab, '关于')
            
            layout.addWidget(tab_widget)

            # 提示：更多设置请打开设置页面
            hint_layout = QHBoxLayout()
            hint_layout.addStretch()
            hint_label = QLabel("💡 提示：更多设置请点击工具栏的 ⚙️ 设置按钮")
            hint_label.setStyleSheet("font-size: 12px; padding: 10px;")
            hint_layout.addWidget(hint_label)
            hint_layout.addStretch()
            layout.addLayout(hint_layout)

            # 应用当前主题
            self._apply_theme()

        except Exception as e:
            self.logger.error(f"初始化帮助对话框UI失败: {e}")

    def _handle_link_click(self, url):
        """处理链接点击事件"""
        try:
            url_str = url.toString()

            # 处理复制邮箱地址的链接
            if url_str.startswith('copy://'):
                email = url_str.replace('copy://', '')
                # 复制到剪贴板
                clipboard = QApplication.clipboard()
                clipboard.setText(email)
                toast_success(self, f'邮箱地址已复制: {email}')
                self.logger.info(f"复制邮箱地址到剪贴板: {email}")
            else:
                # 其他链接使用默认浏览器打开
                QDesktopServices.openUrl(url)
        except Exception as e:
            self.logger.error(f"处理链接点击失败: {e}")
            toast_error(self, f'操作失败: {e}')

    def _show_styled_message(self, msg_type, title, text):
        """显示样式化的消息框"""     
        msgBox = QMessageBox(self)
        if msg_type == '信息':
            msgBox.setIcon(QMessageBox.Icon.Information)
        elif msg_type == '警告':
            msgBox.setIcon(QMessageBox.Icon.Warning)
        elif msg_type == '错误':
            msgBox.setIcon(QMessageBox.Icon.Critical)
            
        msgBox.setWindowTitle(title)
        msgBox.setText(text)
        
        # 设置程序图标
        try:
            icon_path = self._get_resource_path('assets/icon.ico')
            if icon_path and icon_path.exists():
                msgBox.setWindowIcon(QIcon(str(icon_path)))
        except Exception:
            pass
        
        # 设置美化样式
        msgBox.setStyleSheet("""
            QMessageBox {
                background-color: #F8F9FA;
                color: #2C3E50;
                border: 1px solid #BDC3C7;
                border-radius: 8px;
                font-size: 14px;
            }
            QMessageBox QLabel {
                color: #2C3E50;
                font-size: 14px;
                padding: 10px;
            }
            QMessageBox QPushButton {
                background-color: #3498DB;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 13px;
                font-weight: bold;
                min-width: 80px;
            }
            QMessageBox QPushButton:hover {
                background-color: #2980B9;
            }
            QMessageBox QPushButton:pressed {
                background-color: #21618C;
            }
        """)
        
        # 中文化按钮
        msgBox.setStandardButtons(QMessageBox.StandardButton.Ok)
        msgBox.button(QMessageBox.StandardButton.Ok).setText("确定")
        
        msgBox.exec()

    def _ask_yes_no(self, title: str, text: str):
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setText(text)
        # 统一图标/样式
        box.setIcon(QMessageBox.Icon.Question)
        try:
            icon_path = self._get_resource_path('assets/icon.ico')
            if icon_path and icon_path.exists():
                box.setWindowIcon(QIcon(str(icon_path)))
        except Exception:
            pass
        # 样式
        box.setStyleSheet("""
            QMessageBox {
                background-color: #F8F9FA;
                color: #2C3E50;
                border: 1px solid #BDC3C7;
                border-radius: 8px;
                font-size: 14px;
            }
            QMessageBox QLabel {
                color: #2C3E50;
                font-size: 14px;
                padding: 10px;
            }
            QMessageBox QPushButton {
                background-color: #3498DB;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 13px;
                font-weight: bold;
                min-width: 80px;
            }
            QMessageBox QPushButton:hover { background-color: #2980B9; }
            QMessageBox QPushButton:pressed { background-color: #21618C; }
        """)
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        # 中文化按钮
        yes_btn = box.button(QMessageBox.StandardButton.Yes)
        no_btn = box.button(QMessageBox.StandardButton.No)
        if yes_btn:
            yes_btn.setText("确定")
        if no_btn:
            no_btn.setText("取消")
        return box.exec()
        
    def _generate_quick_start_html(self):
        """生成快速入门标签页的HTML内容"""
        colors = self._get_html_colors()

        return f'''
        <h2 style="border-bottom: 2px solid {colors['primary']}; padding-bottom: 8px; color: {colors['text_primary']};">快速入门指南</h2>

        <div style="background-color: {colors['bg_hover']}; padding: 15px; border-left: 4px solid {colors['primary']}; margin: 15px 0;">
        <h3 style="color: {colors['primary']}; margin-top: 0;">三步快速开始</h3>
        <ol style="line-height: 1.8; color: {colors['text_primary']};">
        <li><b>选择文件夹</b>：点击"打开目录"选择包含图片的文件夹</li>
        <li><b>创建类别</b>：点击"新增类别"添加分类标签</li>
        <li><b>开始分类</b>：双击类别按钮或使用快捷键分类图片</li>
        </ol>
        </div>

        <h3 style="color: {colors['text_primary']}; margin-top: 20px;">支持的图片格式</h3>
        <p style="background-color: {colors['bg_secondary']}; padding: 10px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">
        JPG, JPEG, PNG, BMP, GIF, TIFF
        </p>

        <h3 style="color: {colors['text_primary']}; margin-top: 20px;">核心操作</h3>
        <table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse; width: 100%; margin: 10px 0; border: 1px solid {colors['border']};">
        <tr style="background-color: {colors['bg_secondary']};">
        <th style="width: 25%; padding: 8px; border: 1px solid {colors['border']}; text-align: left; color: {colors['text_primary']};">操作</th>
        <th style="width: 35%; padding: 8px; border: 1px solid {colors['border']}; text-align: left; color: {colors['text_primary']};">方法</th>
        <th style="width: 40%; padding: 8px; border: 1px solid {colors['border']}; text-align: left; color: {colors['text_primary']};">说明</th>
        </tr>
        <tr>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">浏览图片</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">← → 键 或 鼠标点击</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">在图片列表中前后导航</td>
        </tr>
        <tr style="background-color: {colors['bg_hover']};">
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">选择类别</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">↑ ↓ 键</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">在类别列表中上下切换选择</td>
        </tr>
        <tr>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">分类图片</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">双击类别按钮 或 Enter键</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">将当前图片分类到选中类别</td>
        </tr>
        <tr style="background-color: {colors['bg_hover']};">
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">缩放图片</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">鼠标滚轮 或 Ctrl +/-</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">放大缩小查看图片细节</td>
        </tr>
        <tr>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">移动图片</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">鼠标左键拖拽</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">移动图片查看不同区域</td>
        </tr>
        <tr style="background-color: {colors['bg_hover']};">
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">移出图片</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">Delete 键</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">将图片移到移出目录</td>
        </tr>
        </table>

        <h3 style="color: {colors['text_primary']}; margin-top: 20px;">高效使用技巧</h3>
        <ul style="line-height: 1.8; color: {colors['text_primary']};">
        <li><b>使用快捷键</b>：按数字键 1-9 快速分类到对应类别</li>
        <li><b>文件模式切换</b>：点击工具栏的"复制模式"/"移动模式"按钮切换</li>
        <li><b>多分类模式</b>：点击"→ 单分类模式"按钮开启多分类，一图多标签</li>
        <li><b>回车确认</b>：选中类别后按 Enter 键快速分类</li>
        <li><b>自动同步</b>：程序会自动检测外部文件变化</li>
        <li><b>状态保存</b>：工作状态会自动保存，重启后恢复</li>
        </ul>

        <div style="background-color: {colors['bg_hover']}; padding: 15px; border-left: 4px solid {colors['primary']}; margin: 20px 0;">
        <h4 style="color: {colors['primary']}; margin-top: 0;">专业提示</h4>
        <p style="line-height: 1.6; color: {colors['text_primary']};">
        • 使用右键点击类别按钮可以自定义快捷键<br>
        • 按 F5 键可以刷新文件列表同步外部变化<br>
        • 按 Ctrl+F 键可以让图片适应窗口大小<br>
        • 支持批量添加类别，用逗号分隔多个类别名<br>
        • <b>多分类模式</b>：再次点击已分类的类别可取消分类<br>
        • <b>高亮按钮</b>：表示当前图片属于该类别（多分类模式下）
        </p>
        </div>
        '''

    def create_quick_start_tab(self):
        """创建快速入门标签页"""

        widget = QWidget()
        layout = QVBoxLayout(widget)

        text_browser = QTextBrowser()

        # 应用主题样式
        c = default_theme.colors
        text_browser.setStyleSheet(f"""
            QTextBrowser {{
                background-color: {c.BACKGROUND_PRIMARY};
                color: {c.TEXT_PRIMARY};
                font-size: 13px;
                line-height: 1.6;
                selection-background-color: {c.PRIMARY};
                selection-color: white;
                border: none;
            }}
        """)

        text_browser.setHtml(self._generate_quick_start_html())
        layout.addWidget(text_browser)

        return widget
        
    def _generate_help_html(self):
        """生成使用指南标签页的HTML内容"""
        colors = self._get_html_colors()

        return f'''
        <h2 style="border-bottom: 2px solid {colors['primary']}; padding-bottom: 8px; color: {colors['text_primary']};">详细使用指南</h2>

        <h3 style="color: {colors['text_primary']}; margin-top: 20px;">文件管理</h3>

        <h4 style="color: {colors['text_primary']};">目录操作</h4>
        <ul style="line-height: 1.8; color: {colors['text_primary']};">
        <li><b>打开目录</b>：选择包含待分类图片的根目录</li>
        <li><b>子目录处理</b>：程序会递归扫描所有子目录中的图片</li>
        <li><b>目录结构</b>：分类后的图片会按类别名创建对应文件夹</li>
        <li><b>移出目录</b>：删除的图片会移动到 "remove" 文件夹</li>
        </ul>

        <h4 style="color: {colors['text_primary']};">类别管理</h4>
        <ul style="line-height: 1.8; color: {colors['text_primary']};">
        <li><b>新增类别</b>：单个添加或批量添加（逗号分隔）</li>
        <li><b>编辑类别</b>：右键类别按钮选择"编辑"</li>
        <li><b>删除类别</b>：右键类别按钮选择"删除"</li>
        <li><b>快捷键设置</b>：右键类别按钮选择"设置快捷键"</li>
        <li><b>类别限制</b>：类别名最长50个字符，支持中英文</li>
        </ul>

        <h3 style="color: {colors['text_primary']}; margin-top: 20px;">图片浏览与操作</h3>

        <h4 style="color: {colors['text_primary']};">视图控制</h4>
        <table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse; width: 100%; margin: 10px 0; border: 1px solid {colors['border']};">
        <tr style="background-color: {colors['bg_secondary']};">
        <th style="width: 20%; padding: 8px; border: 1px solid {colors['border']}; text-align: left; color: {colors['text_primary']};">功能</th>
        <th style="width: 30%; padding: 8px; border: 1px solid {colors['border']}; text-align: left; color: {colors['text_primary']};">操作方法</th>
        <th style="width: 20%; padding: 8px; border: 1px solid {colors['border']}; text-align: left; color: {colors['text_primary']};">快捷键</th>
        <th style="width: 30%; padding: 8px; border: 1px solid {colors['border']}; text-align: left; color: {colors['text_primary']};">说明</th>
        </tr>
        <tr>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">适应窗口</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">菜单/快捷键</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">Ctrl+F</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">自动调整图片大小适应显示区域</td>
        </tr>
        <tr style="background-color: {colors['bg_hover']};">
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">放大图片</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">滚轮向上/菜单</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">Ctrl + =</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">放大图片，最大3倍</td>
        </tr>
        <tr>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">缩小图片</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">滚轮向下/菜单</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">Ctrl + -</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">缩小图片显示</td>
        </tr>
        <tr style="background-color: {colors['bg_hover']};">
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">原始大小</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">菜单/快捷键</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">Ctrl + 0</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">显示图片100%原始大小</td>
        </tr>
        <tr>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">拖拽移动</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">鼠标左键拖拽</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">-</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">移动图片查看不同区域</td>
        </tr>
        </table>

        <h4 style="color: {colors['text_primary']};">分类操作</h4>
        <ul style="line-height: 1.8; color: {colors['text_primary']};">
        <li><b>复制模式</b>：保留原文件，复制到目标类别文件夹（默认）</li>
        <li><b>移动模式</b>：直接移动文件到目标类别文件夹</li>
        <li><b>分类方法</b>：双击类别按钮、使用快捷键或按回车键</li>
        <li><b>多分类模式</b>：同一张图片可分配到多个类别</li>
        </ul>

        <h4 style="color: {colors['text_primary']};">分类模式详解</h4>
        <div style="background-color: {colors['bg_hover']}; padding: 15px; border-left: 4px solid {colors['primary']}; margin: 15px 0;">
        <h5 style="color: {colors['primary']}; margin-top: 0;">单分类模式（默认）</h5>
        <ul style="margin: 5px 0; padding-left: 20px; line-height: 1.6; color: {colors['text_primary']};">
        <li>一张图片只能属于一个类别</li>
        <li>重新分类会自动从旧类别移动到新类别</li>
        <li>类别按钮显示绿色背景表示已分类</li>
        <li>适合传统的文件整理需求</li>
        </ul>
        </div>

        <div style="background-color: {colors['bg_hover']}; padding: 15px; border-left: 4px solid {colors['primary']}; margin: 15px 0;">
        <h5 style="color: {colors['primary']}; margin-top: 0;">多分类模式（新功能）</h5>
        <ul style="margin: 5px 0; padding-left: 20px; line-height: 1.6; color: {colors['text_primary']};">
        <li><b>灵活分类</b>：一张图片可以同时属于多个类别</li>
        <li><b>切换方式</b>：点击工具栏"→ 单分类模式"按钮切换</li>
        <li><b>分类操作</b>：点击类别按钮添加分类，再次点击取消分类</li>
        <li><b>视觉反馈</b>：多分类的类别按钮显示蓝色背景</li>
        <li><b>应用场景</b>：标签化管理，如"风景+日落"、"人物+室内"等</li>
        </ul>

        <table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse; width: 100%; margin: 10px 0; border: 1px solid {colors['border']};">
        <tr style="background-color: {colors['bg_secondary']};">
        <th style="padding: 8px; border: 1px solid {colors['border']}; text-align: left; color: {colors['text_primary']};">操作</th>
        <th style="padding: 8px; border: 1px solid {colors['border']}; text-align: left; color: {colors['text_primary']};">多分类模式行为</th>
        <th style="padding: 8px; border: 1px solid {colors['border']}; text-align: left; color: {colors['text_primary']};">单分类模式行为</th>
        </tr>
        <tr>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">首次分类</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">添加到类别列表</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">直接分类到该类别</td>
        </tr>
        <tr style="background-color: {colors['bg_hover']};">
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">已分类的类别</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">从列表中移除（取消分类）</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">不执行操作</td>
        </tr>
        <tr>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">其他类别</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">同时添加到类别列表</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">从旧类别移动到新类别</td>
        </tr>
        </table>
        </div>

        <div style="background-color: {colors['bg_hover']}; padding: 15px; border-left: 4px solid {colors['primary']}; margin: 20px 0;">
        <h5 style="color: {colors['primary']}; margin-top: 0;">多分类模式使用技巧</h5>
        <ul style="margin: 5px 0; padding-left: 20px; line-height: 1.6; color: {colors['text_primary']};">
        <li><b>标签化思维</b>：把类别当作标签，一张图片可以有多个标签</li>
        <li><b>快速取消</b>：再次点击已分类的类别按钮可快速取消该分类</li>
        <li><b>状态查看</b>：蓝色背景的类别按钮表示当前图片属于该类别</li>
        <li><b>物理文件</b>：图片会被复制到每个分类的文件夹中</li>
        <li><b>模式切换</b>：可随时在单分类和多分类模式间切换</li>
        </ul>
        </div>

        <h3 style="color: {colors['text_primary']}; margin-top: 20px;">状态与统计</h3>

        <h4 style="color: {colors['text_primary']};">状态标识</h4>
        <ul style="line-height: 1.8; color: {colors['text_primary']};">
        <li><b>已分类</b>：图片已成功分类到某个类别</li>
        <li><b>已移出</b>：图片已移动到移出目录</li>
        <li><b>未处理</b>：尚未分类的图片</li>
        <li><b>进度显示</b>：底部状态栏显示处理进度</li>
        </ul>

        <h4 style="color: {colors['text_primary']};">实时统计</h4>
        <ul style="line-height: 1.8; color: {colors['text_primary']};">
        <li><b>总数统计</b>：显示图片总数和处理进度</li>
        <li><b>类别统计</b>：每个类别的图片数量</li>
        <li><b>效率统计</b>：分类速度和剩余时间估计</li>
        </ul>

        <h3 style="color: {colors['text_primary']}; margin-top: 20px;">同步与刷新</h3>
        <ul style="line-height: 1.8; color: {colors['text_primary']};">
        <li><b>自动同步</b>：程序会定期检测外部文件变化</li>
        <li><b>手动刷新</b>：按 F5 键立即同步文件状态</li>
        <li><b>智能检测</b>：检测新增、删除、移动的文件</li>
        <li><b>状态保存</b>：工作状态自动保存，重启后恢复</li>
        </ul>

        <h3 style="color: {colors['text_primary']}; margin-top: 20px;">高级设置</h3>
        <ul style="line-height: 1.8; color: {colors['text_primary']};">
        <li><b>性能优化</b>：针对大量图片的性能优化</li>
        <li><b>网络优化</b>：SMB/NAS网络存储专项优化</li>
        <li><b>缓存管理</b>：智能图片缓存提高浏览速度</li>
        </ul>
        '''

    def create_help_tab(self):
        """创建帮助标签页"""

        widget = QWidget()
        layout = QVBoxLayout(widget)

        text_browser = QTextBrowser()

        # 应用主题样式
        c = default_theme.colors
        text_browser.setStyleSheet(f"""
            QTextBrowser {{
                background-color: {c.BACKGROUND_PRIMARY};
                color: {c.TEXT_PRIMARY};
                font-size: 13px;
                line-height: 1.6;
                selection-background-color: {c.PRIMARY};
                selection-color: white;
                border: none;
            }}
        """)

        text_browser.setHtml(self._generate_help_html())
        layout.addWidget(text_browser)

        return widget
        
    def _generate_advanced_html(self):
        """生成高级功能标签页的HTML内容"""
        colors = self._get_html_colors()

        return f'''
        <h2 style="border-bottom: 2px solid {colors['primary']}; padding-bottom: 8px; color: {colors['text_primary']};">高级功能详解</h2>

        <h3 style="color: {colors['text_primary']}; margin-top: 20px;">分类操作</h3>

        <h4 style="color: {colors['text_primary']};">当前分类功能</h4>
        <ul style="line-height: 1.8; color: {colors['text_primary']};">
        <li><b>单张分类</b>：双击类别按钮分类当前图片</li>
        <li><b>快捷键分类</b>：使用数字键1-9或自定义快捷键</li>
        <li><b>多分类模式</b>：一张图片可同时分配到多个类别</li>
        <li><b>快速导航</b>：使用方向键浏览图片和选择类别</li>
        </ul>

        <h4 style="color: {colors['text_primary']};">类别管理</h4>
        <ul style="line-height: 1.8; color: {colors['text_primary']};">
        <li><b>批量添加</b>：输入多个类别名，用逗号分隔</li>
        <li><b>快捷键绑定</b>：右键类别按钮自定义快捷键</li>
        <li><b>类别排序</b>：拖拽调整类别显示顺序</li>
        <li><b>状态统计</b>：实时显示每个类别的图片数量</li>
        </ul>

        <h3 style="color: {colors['text_primary']}; margin-top: 20px;">自定义功能</h3>

        <h4 style="color: {colors['text_primary']};">快捷键自定义</h4>
        <ul style="line-height: 1.8; color: {colors['text_primary']};">
        <li><b>数字键</b>：1-9 对应前9个类别</li>
        <li><b>字母键</b>：a-z 可自定义对应不同类别</li>
        <li><b>功能键</b>：F1-F12 可绑定特殊操作</li>
        <li><b>组合键</b>：支持 Ctrl、Alt、Shift 组合</li>
        </ul>

        <h4 style="color: {colors['text_primary']};">界面特性</h4>
        <ul style="line-height: 1.8; color: {colors['text_primary']};">
        <li><b>响应式布局</b>：界面自动适应窗口大小</li>
        <li><b>分割面板</b>：可拖拽调整各区域大小</li>
        <li><b>状态保存</b>：界面布局自动保存和恢复</li>
        </ul>

        <h3 style="color: {colors['text_primary']}; margin-top: 20px;">网络存储优化</h3>

        <h4 style="color: {colors['text_primary']};">SMB/NAS 支持</h4>
        <ul style="line-height: 1.8; color: {colors['text_primary']};">
        <li><b>网络路径</b>：支持 \\\\server\\share 格式</li>
        <li><b>连接池</b>：维护网络连接池提高效率</li>
        <li><b>操作重试</b>：网络操作失败时自动重试</li>
        <li><b>缓存优化</b>：智能缓存网络图片</li>
        </ul>

        <h4 style="color: {colors['text_primary']};">性能优化</h4>
        <ul style="line-height: 1.8; color: {colors['text_primary']};">
        <li><b>预加载</b>：提前加载下一张图片</li>
        <li><b>内存管理</b>：智能释放不需要的图片内存</li>
        <li><b>多线程</b>：后台线程处理文件操作</li>
        <li><b>进度缓存</b>：缓存处理进度避免重复扫描</li>
        </ul>

        <h3 style="color: {colors['text_primary']}; margin-top: 20px;">同步与备份</h3>

        <h4 style="color: {colors['text_primary']};">文件同步</h4>
        <ul style="line-height: 1.8; color: {colors['text_primary']};">
        <li><b>实时监控</b>：监控目录变化自动更新</li>
        <li><b>增量同步</b>：只处理变化的文件</li>
        <li><b>冲突解决</b>：智能处理文件名冲突</li>
        <li><b>分类撤销</b>：多分类模式支持快速取消分类</li>
        </ul>

        <h4 style="color: {colors['text_primary']};">状态备份</h4>
        <ul style="line-height: 1.8; color: {colors['text_primary']};">
        <li><b>自动保存</b>：定期保存工作状态</li>
        <li><b>手动备份</b>：导出当前分类状态</li>
        <li><b>状态恢复</b>：从备份文件恢复工作状态</li>
        </ul>

        <h3 style="color: {colors['text_primary']}; margin-top: 20px;">图片分析</h3>

        <h4 style="color: {colors['text_primary']};">图片信息</h4>
        <ul style="line-height: 1.8; color: {colors['text_primary']};">
        <li><b>EXIF 数据</b>：显示拍摄时间、相机信息等</li>
        <li><b>文件属性</b>：大小、分辨率、格式信息</li>
        </ul>
        '''

    def create_advanced_tab(self):
        """创建高级功能标签页"""

        widget = QWidget()
        layout = QVBoxLayout(widget)

        text_browser = QTextBrowser()

        # 应用主题样式
        c = default_theme.colors
        text_browser.setStyleSheet(f"""
            QTextBrowser {{
                background-color: {c.BACKGROUND_PRIMARY};
                color: {c.TEXT_PRIMARY};
                font-size: 13px;
                line-height: 1.6;
                selection-background-color: {c.PRIMARY};
                selection-color: white;
                border: none;
            }}
        """)

        text_browser.setHtml(self._generate_advanced_html())
        layout.addWidget(text_browser)

        return widget
        
    def _generate_faq_html(self):
        """生成常见问题标签页的HTML内容"""
        colors = self._get_html_colors()

        return f'''
        <h2 style="border-bottom: 2px solid {colors['primary']}; padding-bottom: 8px; color: {colors['text_primary']};">常见问题解答</h2>

        <h3 style="color: {colors['text_primary']}; margin-top: 20px;">文件和目录</h3>

        <div style="background-color: {colors['bg_hover']}; padding: 15px; border-left: 4px solid {colors['primary']}; margin: 15px 0;">
        <h4 style="color: {colors['primary']};">Q: 程序支持哪些图片格式？</h4>
        <p style="line-height: 1.6; color: {colors['text_primary']};"><b>A:</b> 支持 JPG、JPEG、PNG、BMP、GIF、TIFF 等常见格式，区分大小写。</p>

        <h4 style="color: {colors['primary']}; margin-top: 15px;">Q: 可以处理子目录中的图片吗？</h4>
        <p style="line-height: 1.6; color: {colors['text_primary']};"><b>A:</b> 是的，程序会递归扫描选定目录下的所有子目录，自动发现图片文件。</p>

        <h4 style="color: {colors['primary']}; margin-top: 15px;">Q: 分类后的图片存储在哪里？</h4>
        <p style="line-height: 1.6; color: {colors['text_primary']};"><b>A:</b> 在原目录下创建以类别名命名的文件夹，图片会复制或移动到相应文件夹中。</p>

        <h4 style="color: {colors['primary']}; margin-top: 15px;">Q: 删除的图片会永久消失吗？</h4>
        <p style="line-height: 1.6; color: {colors['text_primary']};"><b>A:</b> 不会，删除的图片会移动到 "remove" 目录中，可以手动恢复。</p>
        </div>

        <h3 style="color: {colors['text_primary']}; margin-top: 20px;">图片显示和操作</h3>

        <div style="background-color: {colors['bg_hover']}; padding: 15px; border-left: 4px solid {colors['primary']}; margin: 15px 0;">
        <h4 style="color: {colors['primary']};">Q: 图片显示很慢或模糊？</h4>
        <p style="line-height: 1.6; color: {colors['text_primary']};"><b>A:</b> 对于大图片和网络路径，程序会自动检测并启用性能优化模式，提供最佳的显示效果。</p>

        <h4 style="color: {colors['primary']}; margin-top: 15px;">Q: 如何查看图片的详细信息？</h4>
        <p style="line-height: 1.6; color: {colors['text_primary']};"><b>A:</b> 点击图片右上角的 ℹ️ 按钮即可显示半透明的信息面板，查看图片的基本信息、尺寸属性和分类状态。点击"更多信息"可展开查看详细的文件信息。</p>

        <h4 style="color: {colors['primary']}; margin-top: 15px;">Q: 缩放后图片位置错乱？</h4>
        <p style="line-height: 1.6; color: {colors['text_primary']};"><b>A:</b> 按 Ctrl+F 键重置为适应窗口模式，或按 Ctrl+0 显示原始大小。</p>
        </div>

        <h3 style="color: {colors['text_primary']}; margin-top: 20px;">分类和管理</h3>

        <div style="background-color: {colors['bg_hover']}; padding: 15px; border-left: 4px solid {colors['primary']}; margin: 15px 0;">
        <h4 style="color: {colors['primary']};">Q: 复制模式和移动模式有什么区别？</h4>
        <p style="line-height: 1.6; color: {colors['text_primary']};"><b>A:</b> 复制模式保留原文件并创建副本；移动模式直接移动文件到目标位置。</p>

        <h4 style="color: {colors['primary']}; margin-top: 15px;">Q: 如何撤销错误的分类操作？</h4>
        <p style="line-height: 1.6; color: {colors['text_primary']};"><b>A:</b> <b>单分类模式</b>：只能更改分类，不能变为未分类状态，需手动移除文件后按F5刷新。<b>多分类模式</b>：再次点击已分类的类别按钮可直接取消该分类。</p>

        <h4 style="color: {colors['primary']}; margin-top: 15px;">Q: 类别名称有长度限制吗？</h4>
        <p style="line-height: 1.6; color: {colors['text_primary']};"><b>A:</b> 类别名称最长50个字符，支持中英文和常见符号，但不能包含文件系统禁用字符。</p>
        </div>

        <h3 style="color: {colors['text_primary']}; margin-top: 20px;">网络存储</h3>

        <div style="background-color: {colors['bg_hover']}; padding: 15px; border-left: 4px solid {colors['primary']}; margin: 15px 0;">
        <h4 style="color: {colors['primary']};">Q: 支持网络驱动器（NAS）吗？</h4>
        <p style="line-height: 1.6; color: {colors['text_primary']};"><b>A:</b> 支持，默认启用"网络路径优化"设置以提高性能。</p>

        <h4 style="color: {colors['primary']}; margin-top: 15px;">Q: 网络断开后程序崩溃？</h4>
        <p style="line-height: 1.6; color: {colors['text_primary']};"><b>A:</b> 程序有文件操作重试机制，网络操作失败时会自动重试3次。建议保持网络稳定以获得最佳性能。</p>

        <h4 style="color: {colors['primary']}; margin-top: 15px;">Q: SMB 共享访问很慢？</h4>
        <p style="line-height: 1.6; color: {colors['text_primary']};"><b>A:</b> 默认启用"SMB缓存优化"，程序会缓存常用图片以提高访问速度。</p>
        </div>

        <h3 style="color: {colors['text_primary']}; margin-top: 20px;">性能和优化</h3>

        <div style="background-color: {colors['bg_hover']}; padding: 15px; border-left: 4px solid {colors['primary']}; margin: 15px 0;">
        <h4 style="color: {colors['primary']};">Q: 处理大量图片时程序卡顿？</h4>
        <p style="line-height: 1.6; color: {colors['text_primary']};"><b>A:</b> 程序会根据图片数量和系统性能自动调整优化策略，包括减少动画效果和智能预加载。</p>

        <h4 style="color: {colors['primary']}; margin-top: 15px;">Q: 内存占用过高？</h4>
        <p style="line-height: 1.6; color: {colors['text_primary']};"><b>A:</b> 程序会自动管理内存，也可以手动清理缓存（帮助对话框中的清理按钮）。</p>

        <h4 style="color: {colors['primary']}; margin-top: 15px;">Q: 如何清理程序产生的缓存？</h4>
        <p style="line-height: 1.6; color: {colors['text_primary']};"><b>A:</b> 在帮助对话框中点击"清理SMB缓存"按钮，或手动删除用户目录下的 .image_classifier_cache 文件夹。</p>
        </div>

        <h3 style="color: {colors['text_primary']}; margin-top: 20px;">故障排除</h3>

        <div style="background-color: {colors['bg_hover']}; padding: 15px; border-left: 4px solid {colors['primary']}; margin: 15px 0;">
        <h4 style="color: {colors['primary']};">常见问题诊断步骤</h4>
        <ol style="line-height: 1.8; color: {colors['text_primary']};">
        <li><b>检查日志</b>：查看 logs/image_classifier.log 了解错误详情</li>
        <li><b>重启程序</b>：简单重启通常能解决临时问题</li>
        <li><b>清理缓存</b>：清理程序缓存解决数据冲突</li>
        <li><b>检查权限</b>：确保对目标目录有读写权限</li>
        <li><b>更新程序</b>：下载最新版本获得 bug 修复</li>
        </ol>

        <h4 style="color: {colors['primary']}; margin-top: 15px;">获取帮助</h4>
        <p style="line-height: 1.6; color: {colors['text_primary']};">如果问题仍未解决，请将错误日志和操作步骤反馈给我们：</p>
        <p style="background-color: {colors['bg_secondary']}; padding: 12px; border-left: 4px solid {colors['primary']}; margin: 10px 0;">
        <b style="color: {colors['text_primary']};">问题反馈邮箱：</b><br>
        <a href="copy://{CONTACT_INFO['support_email']}" style="color: {colors['primary']}; text-decoration: none; font-size: 15px; font-weight: bold; cursor: pointer;">
        {CONTACT_INFO['support_email']}
        </a>
        <span style="color: {colors['text_secondary']}; font-size: 13px; margin-left: 10px;">（点击复制邮箱地址）</span>
        </p>
        </div>
        '''

    def create_faq_tab(self):
        """创建常见问题标签页"""

        widget = QWidget()
        layout = QVBoxLayout(widget)

        text_browser = QTextBrowser()

        # 应用主题样式
        c = default_theme.colors
        text_browser.setStyleSheet(f"""
            QTextBrowser {{
                background-color: {c.BACKGROUND_PRIMARY};
                color: {c.TEXT_PRIMARY};
                font-size: 13px;
                line-height: 1.6;
                selection-background-color: {c.PRIMARY};
                selection-color: white;
                border: none;
            }}
            a {{
                color: {c.PRIMARY};
                text-decoration: underline;
            }}
            a:hover {{
                color: {c.PRIMARY_LIGHT};
                background-color: {c.BACKGROUND_HOVER};
            }}
        """)

        # 连接链接点击事件
        text_browser.setOpenLinks(False)  # 禁用默认的链接打开行为
        text_browser.anchorClicked.connect(self._handle_link_click)

        text_browser.setHtml(self._generate_faq_html())
        layout.addWidget(text_browser)

        return widget
    
    def _generate_version_history_html(self):
        """生成版本历史HTML内容"""
        html_parts = []
        colors = self._get_html_colors()

        # 根据主题选择版本样式配色
        if default_theme.is_dark:
            # 暗色主题配色
            version_styles = [
                {"bg": "#1e3a1e", "border": "#4caf50", "text": "#81c784", "emoji": "🎉", "label": "(当前版本)"},
                {"bg": "#1a2a3a", "border": "#2196f3", "text": "#64b5f6", "emoji": "✨", "label": ""},
                {"bg": "#2a2a2a", "border": "#6c757d", "text": "#b0b0b0", "emoji": "🚀", "label": ""},
                {"bg": "#3a2a1a", "border": "#ff9800", "text": "#ffb74d", "emoji": "🔧", "label": ""},
                {"bg": "#3a1a2a", "border": "#e91e63", "text": "#f48fb1", "emoji": "📦", "label": ""},
            ]
        else:
            # 亮色主题配色
            version_styles = [
                {"bg": "#e8f5e8", "border": "#4caf50", "text": "#2e7d32", "emoji": "🎉", "label": "(当前版本)"},
                {"bg": "#f0f7ff", "border": "#2196f3", "text": "#1565c0", "emoji": "✨", "label": ""},
                {"bg": "#f8f9fa", "border": "#6c757d", "text": "#495057", "emoji": "🚀", "label": ""},
                {"bg": "#fff3e0", "border": "#ff9800", "text": "#ef6c00", "emoji": "🔧", "label": ""},
                {"bg": "#fce4ec", "border": "#e91e63", "text": "#c2185b", "emoji": "📦", "label": ""},
            ]

        for i, version_info in enumerate(VERSION_HISTORY):
            style = version_styles[min(i, len(version_styles) - 1)]

            # 当前版本标记
            version_label = style["label"] if i == 0 else ""

            html_part = f'''
            <div style="background-color: {style["bg"]}; padding: 15px; border-radius: 8px; margin: 10px 0; border-left: 4px solid {style["border"]};">
            <h4 style="color: {style["text"]}; margin: 0 0 10px 0;">{style["emoji"]} v{version_info["version"]} {version_label} - {version_info["date"]}</h4>
            '''

            if version_info.get("title"):
                html_part += f'<p style="margin: 0 0 10px 0; font-weight: bold; color: {style["text"]};">{version_info["title"]}</p>'

            # 添加亮点
            if version_info.get("highlights"):
                html_part += f'<ul style="margin: 5px 0; padding-left: 20px; color: {colors["text_primary"]};">'
                for highlight in version_info["highlights"]:
                    html_part += f'<li>{highlight}</li>'
                html_part += '</ul>'
            # 如果没有亮点，使用详细信息的前几项
            elif version_info.get("details"):
                html_part += f'<ul style="margin: 5px 0; padding-left: 20px; color: {colors["text_primary"]};">'
                for detail in version_info["details"][:4]:  # 只显示前4项
                    html_part += f'<li>{detail}</li>'
                html_part += '</ul>'

            html_part += '</div>'
            html_parts.append(html_part)

        return '\n'.join(html_parts)
        
    def _generate_about_html(self):
        """生成关于标签页的HTML内容"""
        about_info = get_about_info()
        colors = self._get_html_colors()

        return f'''
        <h2 style="border-bottom: 2px solid {colors['primary']}; padding-bottom: 8px; color: {colors['text_primary']};">图片分类工具 v{about_info["version"]}</h2>

        <div style="text-align: center; background-color: {colors['bg_hover']}; padding: 20px; border-left: 4px solid {colors['primary']}; margin: 20px 0;">
        <h3 style="margin: 0; color: {colors['primary']};">专业图片分类管理工具</h3>
        <p style="margin: 10px 0 0 0; color: {colors['text_primary']};">提高图片整理效率，让分类工作更简单</p>
        </div>

        <h3 style="color: {colors['text_primary']}; margin-top: 20px;">核心特性</h3>

        <div style="background-color: {colors['bg_hover']}; padding: 15px; border-left: 4px solid {colors['primary']}; margin: 15px 0;">
        <h4 style="color: {colors['primary']}; margin-top: 0;">图片处理</h4>
        <ul style="margin: 5px 0; padding-left: 20px; line-height: 1.6; color: {colors['text_primary']};">
        <li>支持多种常见图片格式</li>
        <li>智能图片预览和缩放</li>
        <li>拖拽移动查看细节</li>
        <li>EXIF信息显示</li>
        </ul>

        <h4 style="color: {colors['primary']}; margin-top: 15px;">文件管理</h4>
        <ul style="margin: 5px 0; padding-left: 20px; line-height: 1.6; color: {colors['text_primary']};">
        <li>复制/移动双模式操作</li>
        <li>批量分类处理</li>
        <li>智能类别管理</li>
        <li>自动状态同步</li>
        </ul>

        <h4 style="color: {colors['primary']}; margin-top: 15px;">操作体验</h4>
        <ul style="margin: 5px 0; padding-left: 20px; line-height: 1.6; color: {colors['text_primary']};">
        <li>丰富的快捷键支持</li>
        <li>自定义快捷键设置</li>
        <li>直观的状态提示</li>
        <li>实时进度跟踪</li>
        </ul>

        <h4 style="color: {colors['primary']}; margin-top: 15px;">性能优化</h4>
        <ul style="margin: 5px 0; padding-left: 20px; line-height: 1.6; color: {colors['text_primary']};">
        <li>网络存储优化</li>
        <li>智能缓存机制</li>
        <li>多线程处理</li>
        <li>内存自动管理</li>
        </ul>
        </div>

        <h3 style="color: {colors['text_primary']}; margin-top: 20px;">技术架构</h3>

        <table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse; width: 100%; margin: 10px 0; border: 1px solid {colors['border']};">
        <tr style="background-color: {colors['bg_secondary']};">
        <th style="width: 30%; padding: 8px; border: 1px solid {colors['border']}; text-align: left; color: {colors['text_primary']};">技术栈</th>
        <th style="width: 35%; padding: 8px; border: 1px solid {colors['border']}; text-align: left; color: {colors['text_primary']};">版本/库</th>
        <th style="width: 35%; padding: 8px; border: 1px solid {colors['border']}; text-align: left; color: {colors['text_primary']};">说明</th>
        </tr>
        <tr>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};"><b>开发语言</b></td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">Python 3.8+</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">主要开发语言</td>
        </tr>
        <tr style="background-color: {colors['bg_hover']};">
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};"><b>界面框架</b></td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">PyQt6</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">现代化GUI框架</td>
        </tr>
        <tr>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};"><b>图像处理</b></td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">OpenCV + Pillow</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">图片加载和处理</td>
        </tr>
        <tr style="background-color: {colors['bg_hover']};">
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};"><b>数据存储</b></td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">JSON</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">配置和状态存储</td>
        </tr>
        <tr>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};"><b>日志系统</b></td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">Python logging</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">错误跟踪和调试</td>
        </tr>
        <tr style="background-color: {colors['bg_hover']};">
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};"><b>多线程</b></td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">QThread</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">后台任务处理</td>
        </tr>
        </table>

        <h3 style="color: {colors['text_primary']}; margin-top: 20px;">版本发展历程</h3>
        <div style="margin: 20px 0;">
        {self._generate_version_history_html()}
        </div>

        <div style="background-color: {colors['bg_hover']}; padding: 20px; border-left: 4px solid {colors['primary']}; text-align: center; margin: 30px 0;">
        <h3 style="margin: 0 0 15px 0; color: {colors['primary']};">版权信息</h3>
        <p style="margin: 5px 0; color: {colors['text_primary']};"><b>© 2025 GDDI</b></p>
        <p style="margin: 5px 0; color: {colors['text_primary']};">专注于提升图片管理效率的专业软件</p>
        <p style="margin: 15px 0 5px 0; color: {colors['text_secondary']}; font-size: 14px; line-height: 1.6;">
        本软件遵循 MIT 开源协议<br>
        感谢所有贡献者和用户的支持
        </p>
        <div style="margin-top: 15px; padding-top: 15px; border-top: 1px solid {colors['border']};">
        <span style="color: {colors['text_secondary']}; font-size: 13px;">
        让图片整理变得简单高效
        </span>
        </div>
        </div>
        '''

    def create_about_tab(self):
        """创建关于标签页"""

        widget = QWidget()
        layout = QVBoxLayout(widget)

        text_browser = QTextBrowser()

        # 应用主题样式
        c = default_theme.colors
        text_browser.setStyleSheet(f"""
            QTextBrowser {{
                background-color: {c.BACKGROUND_PRIMARY};
                color: {c.TEXT_PRIMARY};
                font-size: 13px;
                line-height: 1.6;
                selection-background-color: {c.PRIMARY};
                selection-color: white;
                border: none;
            }}
        """)

        text_browser.setHtml(self._generate_about_html())
        layout.addWidget(text_browser)

        return widget


class ProgressDialog(QDialog):
    """增强的进度对话框，支持取消和详细信息"""
    cancelled = pyqtSignal()
    
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(400)
        self.cancelled_flag = False
        self._force_closed = False  # 添加强制关闭标志
        self.logger = logging.getLogger(__name__)

        # 应用主题样式
        from .components.styles import DialogStyles
        from .components.styles.theme import default_theme
        c = default_theme.colors

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # 主要进度信息
        self.main_label = QLabel("正在处理...")
        self.main_label.setStyleSheet(f"QLabel {{ color: {c.TEXT_PRIMARY}; font-weight: bold; }}")
        layout.addWidget(self.main_label)

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        layout.addWidget(self.progress_bar)

        # 详细信息
        self.detail_label = QLabel("")
        self.detail_label.setStyleSheet(f"QLabel {{ color: {c.TEXT_SECONDARY}; font-size: 11px; }}")
        layout.addWidget(self.detail_label)

        # 取消按钮
        button_layout = QHBoxLayout()
        self.cancel_button = QPushButton("取消")
        self.cancel_button.clicked.connect(self.cancel_operation)
        button_layout.addStretch()
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)

        # 设置样式
        self.setStyleSheet(f"""
            {DialogStyles.get_base_dialog_style()}
            QLabel {{
                padding: 4px;
            }}
            QProgressBar {{
                text-align: center;
                min-height: 20px;
                border: 1px solid {c.BORDER_MEDIUM};
                border-radius: 10px;
                background-color: {c.BACKGROUND_SECONDARY};
                color: {c.TEXT_PRIMARY};
                font-size: 11px;
                font-weight: bold;
            }}
            QProgressBar::chunk {{
                background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0 {c.SUCCESS}, stop: 1 {c.SUCCESS_DARK});
                border-radius: 8px;
                margin: 1px;
            }}
            QPushButton {{
                padding: 6px 20px;
                background-color: {c.ERROR};
                color: white;
                border: none;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: {c.ERROR_DARK};
            }}
        """)
        
    def update_progress(self, value, maximum=100):
        """更新进度"""
        try:
            self.progress_bar.setMaximum(maximum)
            self.progress_bar.setValue(value)
        except Exception as e:
            self.logger.error(f"更新进度失败: {e}")
        
    def update_main_text(self, text):
        """更新主要文本"""
        try:
            self.main_label.setText(text)
        except Exception as e:
            self.logger.error(f"更新主要文本失败: {e}")
        
    def update_detail_text(self, text):
        """更新详细信息"""
        try:
            self.detail_label.setText(text)
        except Exception as e:
            self.logger.error(f"更新详细信息失败: {e}")
        
    def cancel_operation(self):
        """取消操作"""
        try:
            self.cancelled_flag = True
            self.cancelled.emit()
            self.cancel_button.setEnabled(False)
            self.cancel_button.setText("正在取消...")
        except Exception as e:
            self.logger.error(f"取消操作失败: {e}")
        
    def force_close(self):
        """强制关闭对话框"""
        self._force_closed = True
        self.close()
        
    def is_cancelled(self):
        """检查是否已取消"""
        return self.cancelled_flag
        
    def closeEvent(self, event):
        """重写关闭事件"""
        if self._force_closed:
            event.accept()
        else:
            # 正常情况下需要等待操作完成
            event.accept()


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
        from .components.styles import DialogStyles
        self.setStyleSheet(DialogStyles.get_form_dialog_style())

        self.init_ui()
        self.load_ignored_list()

    def init_ui(self):
        """初始化UI"""
        from .components.styles.theme import default_theme
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
        from .components.styles.theme import default_theme
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
        from PyQt6.QtCore import QSize
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

                # 刷新列表
                self.load_ignored_list()
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
        else:
            toast_info(self, "请先选择要恢复的类别")

    def close_dialog(self):
        """关闭对话框"""
        # 如果有恢复操作，通知主窗口刷新
        if self.restore_count > 0 and self.parent_window:
            if hasattr(self.parent_window, 'load_categories'):
                self.parent_window.load_categories()

        self.accept()


class SettingsDialog(QDialog):
    """设置对话框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)
        self.app_config = get_app_config()
        self._centered = False

        # 临时存储配置（用于取消操作）
        self.temp_config = {}

        # 防抖定时器（用于延迟保存配置，避免频繁写入磁盘）
        self.zoom_save_timer = QTimer()
        self.zoom_save_timer.setSingleShot(True)
        self.zoom_save_timer.timeout.connect(self._save_zoom_config)

        self.initUI()

    def initUI(self):
        """初始化UI"""
        self.setWindowTitle("设置")
        self.setMinimumWidth(700)
        self.setMinimumHeight(650)

        # 主布局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # 创建Tab控件
        self.tab_widget = QTabWidget()

        # 基本设置Tab
        basic_tab = self.create_basic_tab()
        self.tab_widget.addTab(basic_tab, "⚙️ 基本设置")

        # 高级设置Tab
        advanced_tab = self.create_advanced_tab()
        self.tab_widget.addTab(advanced_tab, "🔧 高级设置")

        layout.addWidget(self.tab_widget)

        # 底部按钮
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        reset_btn = QPushButton("恢复默认")
        reset_btn.clicked.connect(self.reset_to_defaults)
        button_layout.addWidget(reset_btn)

        layout.addLayout(button_layout)

        # 应用主题样式
        self._apply_theme()

    def create_appearance_section(self) -> QGroupBox:
        """创建外观设置区域"""
        from .components.widgets import Switch

        group = QGroupBox("🎨 外观设置")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)

        # 主题设置
        theme_group = QWidget()
        theme_layout = QVBoxLayout(theme_group)
        theme_layout.setSpacing(8)

        theme_title = QLabel("🌓 主题模式")
        theme_title.setStyleSheet("font-size: 14px; font-weight: bold;")
        theme_layout.addWidget(theme_title)

        # 主题选择下拉列表和自动切换开关（横向布局）
        theme_select_layout = QHBoxLayout()
        theme_select_layout.setSpacing(10)

        self.theme_combo = QComboBox()
        self.theme_combo.addItem("☀️  浅色主题", "light")
        self.theme_combo.addItem("🌙  深色主题", "dark")
        self.theme_combo.addItem("💻  跟随系统", "system")
        self.theme_combo.setMinimumHeight(40)
        # 禁用滚轮切换
        self.theme_combo.wheelEvent = lambda event: None
        self.theme_combo.currentIndexChanged.connect(self.on_theme_combo_changed)
        theme_select_layout.addWidget(self.theme_combo)

        theme_select_layout.addStretch()

        # 自动切换标签和Switch
        auto_label = QLabel("⏰ 自动切换")
        auto_label.setStyleSheet("font-size: 13px;")
        auto_label.setToolTip("8:00-18:00亮色，其他时间暗色")
        theme_select_layout.addWidget(auto_label)

        self.auto_theme_switch = Switch()
        self.auto_theme_switch.toggled.connect(self.on_auto_theme_toggled)
        theme_select_layout.addWidget(self.auto_theme_switch)

        theme_layout.addLayout(theme_select_layout)
        layout.addWidget(theme_group)

        # 根据当前主题模式设置下拉列表状态（阻止信号避免触发theme_mode重置）
        current_theme_mode = self.app_config.theme_mode

        # 阻止信号触发
        self.theme_combo.blockSignals(True)

        if current_theme_mode == "auto":
            # 启用自动切换
            self.auto_theme_switch.blockSignals(True)
            self.auto_theme_switch.setChecked(True)
            self.auto_theme_switch.blockSignals(False)
            # 禁用主题下拉列表
            self.theme_combo.setEnabled(False)
            # 设置为当前实际主题
            if self.app_config.theme == "dark":
                self.theme_combo.setCurrentIndex(1)
            else:
                self.theme_combo.setCurrentIndex(0)
        elif current_theme_mode == "system":
            # 设置为跟随系统
            self.theme_combo.setCurrentIndex(2)
        elif self.app_config.theme == "dark":
            # 设置为暗色
            self.theme_combo.setCurrentIndex(1)
        else:
            # 设置为亮色
            self.theme_combo.setCurrentIndex(0)

        # 恢复信号
        self.theme_combo.blockSignals(False)

        layout.addStretch()
        return group

    def create_tutorial_section(self) -> QGroupBox:
        """创建教程设置区域"""
        group = QGroupBox("🎓 教程设置")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(20)

        # 教程状态
        status_group = QWidget()
        status_layout = QVBoxLayout(status_group)
        status_layout.setSpacing(10)

        # 标题
        status_title = QLabel("📚 教程状态")
        status_title.setStyleSheet("font-size: 14px; font-weight: bold;")
        status_layout.addWidget(status_title)

        # 确定当前状态
        if self.app_config.tutorial_completed:
            status_text = "✅ 教程已完成"
            status_color = "#10B981"
        elif self.app_config.tutorial_skipped:
            status_text = "⏭️ 教程已跳过"
            status_color = "#F59E0B"
        else:
            status_text = "⏸️ 教程未开始"
            status_color = "#6B7280"

        # 状态显示和按钮（横向布局）
        control_widget = QWidget()
        control_layout = QHBoxLayout(control_widget)
        control_layout.setContentsMargins(0, 0, 0, 0)
        control_layout.setSpacing(15)

        # 状态标签（左侧）
        self.tutorial_status_label = QLabel(status_text)
        self.tutorial_status_label.setObjectName("tutorialStatusLabel")
        self.tutorial_status_color = status_color

        if default_theme.is_dark:
            bg_color = "rgba(255, 255, 255, 0.08)"
        else:
            bg_color = "rgba(0, 0, 0, 0.05)"

        self.tutorial_status_label.setStyleSheet(f"""
            QLabel#tutorialStatusLabel {{
                color: {status_color} !important;
                font-size: 13px;
                font-weight: normal;
                padding: 8px 12px;
                background-color: {bg_color};
                border-radius: 4px;
            }}
        """)
        control_layout.addWidget(self.tutorial_status_label)

        control_layout.addStretch()

        # 重新开始教程按钮（右侧）
        start_tutorial_btn = QPushButton("重新开始教程")
        start_tutorial_btn.clicked.connect(self.start_tutorial)
        start_tutorial_btn.setMinimumHeight(36)
        start_tutorial_btn.setMinimumWidth(120)
        control_layout.addWidget(start_tutorial_btn)

        status_layout.addWidget(control_widget)

        layout.addWidget(status_group)

        layout.addStretch()
        return group

    def create_basic_tab(self) -> QWidget:
        """创建基本设置Tab"""
        tab = QWidget()

        # 创建可滚动区域
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)

        # 滚动内容容器
        scroll_content = QWidget()
        scroll_content.setObjectName("scrollContent")
        content_layout = QVBoxLayout(scroll_content)
        content_layout.setSpacing(20)
        content_layout.setContentsMargins(0, 0, 10, 0)

        # 添加各个设置组
        content_layout.addWidget(self.create_appearance_section())
        content_layout.addWidget(self.create_preview_section())
        content_layout.addWidget(self.create_tutorial_section())
        content_layout.addWidget(self.create_basic_update_section())
        content_layout.addStretch()

        scroll_area.setWidget(scroll_content)

        # Tab布局
        tab_layout = QVBoxLayout(tab)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.addWidget(scroll_area)

        return tab

    def create_advanced_tab(self) -> QWidget:
        """创建高级设置Tab"""
        tab = QWidget()

        # 创建可滚动区域
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)

        # 滚动内容容器
        scroll_content = QWidget()
        scroll_content.setObjectName("scrollContent")
        content_layout = QVBoxLayout(scroll_content)
        content_layout.setSpacing(20)
        content_layout.setContentsMargins(0, 0, 10, 0)

        # 添加各个设置组
        content_layout.addWidget(self.create_log_toast_section())
        content_layout.addWidget(self.create_advanced_update_section())
        content_layout.addWidget(self.create_directory_section())
        content_layout.addWidget(self.create_smb_section())
        content_layout.addStretch()

        scroll_area.setWidget(scroll_content)

        # Tab布局
        tab_layout = QVBoxLayout(tab)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.addWidget(scroll_area)

        return tab

    def create_log_toast_section(self) -> QGroupBox:
        """创建日志和Toast级别设置区域"""
        group = QGroupBox("📝 日志与提示")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(20)

        # 日志级别设置
        log_group = QWidget()
        log_layout = QVBoxLayout(log_group)
        log_layout.setSpacing(10)

        # 标题和下拉框（横向布局）
        log_header = QWidget()
        log_header_layout = QHBoxLayout(log_header)
        log_header_layout.setContentsMargins(0, 0, 0, 0)
        log_header_layout.setSpacing(10)

        log_title = QLabel("📋 日志保存级别")
        log_title.setStyleSheet("font-size: 14px; font-weight: bold;")
        log_header_layout.addWidget(log_title)

        log_header_layout.addStretch()

        self.log_level_combo = QComboBox()
        self.log_level_combo.addItem("🐛 DEBUG - 调试信息", "DEBUG")
        self.log_level_combo.addItem("ℹ️  INFO - 一般信息", "INFO")
        self.log_level_combo.addItem("⚠️  WARNING - 警告信息", "WARNING")
        self.log_level_combo.addItem("❌ ERROR - 错误信息", "ERROR")
        self.log_level_combo.addItem("🔥 CRITICAL - 严重错误", "CRITICAL")
        self.log_level_combo.setMinimumHeight(36)
        self.log_level_combo.setMinimumWidth(220)
        # 禁用滚轮切换
        self.log_level_combo.wheelEvent = lambda event: None
        # 设置当前级别
        current_log_level = self.app_config.log_level
        for i in range(self.log_level_combo.count()):
            if self.log_level_combo.itemData(i) == current_log_level:
                self.log_level_combo.setCurrentIndex(i)
                break
        self.log_level_combo.currentIndexChanged.connect(self.on_log_level_changed)
        log_header_layout.addWidget(self.log_level_combo)

        log_layout.addWidget(log_header)
        layout.addWidget(log_group)

        # Toast级别设置
        toast_group = QWidget()
        toast_layout = QVBoxLayout(toast_group)
        toast_layout.setSpacing(10)

        # 标题和下拉框（横向布局）
        toast_header = QWidget()
        toast_header_layout = QHBoxLayout(toast_header)
        toast_header_layout.setContentsMargins(0, 0, 0, 0)
        toast_header_layout.setSpacing(10)

        toast_title = QLabel("💬 Toast提示级别")
        toast_title.setStyleSheet("font-size: 14px; font-weight: bold;")
        toast_header_layout.addWidget(toast_title)

        toast_header_layout.addStretch()

        self.toast_level_combo = QComboBox()
        self.toast_level_combo.addItem("🐛 DEBUG - 所有提示", "DEBUG")
        self.toast_level_combo.addItem("ℹ️  INFO - 一般及以上", "INFO")
        self.toast_level_combo.addItem("⚠️  WARNING - 警告及错误", "WARNING")
        self.toast_level_combo.addItem("❌ ERROR - 仅错误提示", "ERROR")
        self.toast_level_combo.setMinimumHeight(36)
        self.toast_level_combo.setMinimumWidth(220)
        # 禁用滚轮切换
        self.toast_level_combo.wheelEvent = lambda event: None
        # 设置当前级别
        current_toast_level = self.app_config.toast_level
        for i in range(self.toast_level_combo.count()):
            if self.toast_level_combo.itemData(i) == current_toast_level:
                self.toast_level_combo.setCurrentIndex(i)
                break
        self.toast_level_combo.currentIndexChanged.connect(self.on_toast_level_changed)
        toast_header_layout.addWidget(self.toast_level_combo)

        toast_layout.addWidget(toast_header)
        layout.addWidget(toast_group)

        return group

    def create_basic_update_section(self) -> QGroupBox:
        """创建基本更新设置区域（仅包含开关和手动检查）"""
        from .components.widgets import Switch

        group = QGroupBox("🔄 更新设置")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(20)

        # 更新检查设置组
        update_group = QWidget()
        update_layout = QVBoxLayout(update_group)
        update_layout.setSpacing(10)

        # 标题
        update_title = QLabel("🔄 更新设置")
        update_title.setStyleSheet("font-size: 14px; font-weight: bold;")
        update_layout.addWidget(update_title)

        # 描述
        update_desc = QLabel("立即检查是否有新版本可用，启用自动检查更新（推荐开启）")
        update_desc.setWordWrap(True)
        update_layout.addWidget(update_desc)

        # 检查更新按钮和自动更新开关（横向布局）
        control_widget = QWidget()
        control_layout = QHBoxLayout(control_widget)
        control_layout.setContentsMargins(0, 0, 0, 0)
        control_layout.setSpacing(15)

        # 检查更新按钮
        check_update_btn = QPushButton("检查更新")
        check_update_btn.clicked.connect(self.check_for_updates)
        check_update_btn.setMinimumHeight(36)
        check_update_btn.setMinimumWidth(120)
        control_layout.addWidget(check_update_btn)

        control_layout.addStretch()

        # 自动检查开关（辅助功能）
        auto_check_label = QLabel("启用自动检查")
        auto_check_label.setStyleSheet("font-size: 13px;")
        control_layout.addWidget(auto_check_label)

        self.auto_update_switch = Switch()
        self.auto_update_switch.setChecked(self.app_config.auto_update_enabled)
        control_layout.addWidget(self.auto_update_switch)

        update_layout.addWidget(control_widget)

        layout.addWidget(update_group)
        layout.addStretch()
        return group

    def create_advanced_update_section(self) -> QGroupBox:
        """创建高级更新设置区域（包含更新地址和令牌）"""
        group = QGroupBox("🔄 更新设置")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(20)

        # 更新服务器设置
        endpoint_group = QWidget()
        endpoint_layout = QVBoxLayout(endpoint_group)
        endpoint_layout.setSpacing(10)

        # 标题和按钮（横向布局）
        endpoint_header = QWidget()
        endpoint_header_layout = QHBoxLayout(endpoint_header)
        endpoint_header_layout.setContentsMargins(0, 0, 0, 0)
        endpoint_header_layout.setSpacing(10)

        endpoint_title = QLabel("🌐 更新服务器")
        endpoint_title.setStyleSheet("font-size: 14px; font-weight: bold;")
        endpoint_header_layout.addWidget(endpoint_title)

        endpoint_header_layout.addStretch()

        # 编辑按钮
        self.endpoint_edit_btn = QPushButton("✏️ 编辑")
        self.endpoint_edit_btn.setFixedHeight(28)
        self.endpoint_edit_btn.setObjectName("iconButton")
        self.endpoint_edit_btn.setToolTip("编辑更新服务器地址（通常无需修改）")
        self.endpoint_edit_btn.setStyleSheet("""
            QPushButton {
                background-color: #6B7280;
                color: white;
                font-size: 12px;
                border: none;
                border-radius: 4px;
                padding: 0 10px;
            }
            QPushButton:hover {
                background-color: #4B5563;
            }
            QPushButton:pressed {
                background-color: #374151;
            }
        """)
        self.endpoint_edit_btn.clicked.connect(self.edit_endpoint)
        endpoint_header_layout.addWidget(self.endpoint_edit_btn)

        # 保存按钮（初始隐藏）
        self.endpoint_save_btn = QPushButton("✓ 保存")
        self.endpoint_save_btn.setFixedHeight(28)
        self.endpoint_save_btn.setObjectName("iconButton")
        self.endpoint_save_btn.setToolTip("保存更新地址")
        self.endpoint_save_btn.setStyleSheet("""
            QPushButton {
                background-color: #10B981;
                color: white;
                font-size: 12px;
                font-weight: bold;
                border: none;
                border-radius: 4px;
                padding: 0 10px;
            }
            QPushButton:hover {
                background-color: #059669;
            }
            QPushButton:pressed {
                background-color: #047857;
            }
        """)
        self.endpoint_save_btn.clicked.connect(self.save_endpoint)
        self.endpoint_save_btn.hide()
        endpoint_header_layout.addWidget(self.endpoint_save_btn)

        # 取消按钮（初始隐藏）
        self.endpoint_cancel_btn = QPushButton("✕ 取消")
        self.endpoint_cancel_btn.setFixedHeight(28)
        self.endpoint_cancel_btn.setObjectName("iconButton")
        self.endpoint_cancel_btn.setToolTip("取消编辑")
        self.endpoint_cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #EF4444;
                color: white;
                font-size: 12px;
                font-weight: bold;
                border: none;
                border-radius: 4px;
                padding: 0 10px;
            }
            QPushButton:hover {
                background-color: #DC2626;
            }
            QPushButton:pressed {
                background-color: #B91C1C;
            }
        """)
        self.endpoint_cancel_btn.clicked.connect(self.cancel_endpoint_edit)
        self.endpoint_cancel_btn.hide()
        endpoint_header_layout.addWidget(self.endpoint_cancel_btn)

        endpoint_layout.addWidget(endpoint_header)

        # 输入框
        self.endpoint_input = QLineEdit()
        self.endpoint_input.setText(self.app_config.update_endpoint)
        self.endpoint_input.setCursorPosition(0)  # 显示开头而不是结尾
        self.endpoint_input.setPlaceholderText("https://...")
        self.endpoint_input.setMinimumHeight(32)
        self.endpoint_input.setReadOnly(True)  # 默认只读
        endpoint_layout.addWidget(self.endpoint_input)

        layout.addWidget(endpoint_group)

        # 访问令牌设置
        token_group = QWidget()
        token_layout = QVBoxLayout(token_group)
        token_layout.setSpacing(10)

        # 标题和按钮（横向布局）
        token_header = QWidget()
        token_header_layout = QHBoxLayout(token_header)
        token_header_layout.setContentsMargins(0, 0, 0, 0)
        token_header_layout.setSpacing(8)

        token_title = QLabel("🔑 访问令牌")
        token_title.setStyleSheet("font-size: 14px; font-weight: bold;")
        token_header_layout.addWidget(token_title)

        token_header_layout.addStretch()

        # 显示/隐藏按钮
        self.show_token_btn = QPushButton("👁️ 显示")
        self.show_token_btn.setFixedHeight(28)
        self.show_token_btn.setCheckable(True)
        self.show_token_btn.setObjectName("iconButton")
        self.show_token_btn.setToolTip("显示/隐藏令牌内容")
        self.show_token_btn.setStyleSheet("""
            QPushButton {
                background-color: #6B7280;
                color: white;
                font-size: 12px;
                border: none;
                border-radius: 4px;
                padding: 0 10px;
            }
            QPushButton:hover {
                background-color: #4B5563;
            }
            QPushButton:pressed {
                background-color: #374151;
            }
            QPushButton:checked {
                background-color: #3B82F6;
            }
        """)
        self.show_token_btn.clicked.connect(self.toggle_token_visibility)
        token_header_layout.addWidget(self.show_token_btn)

        # 编辑按钮
        self.token_edit_btn = QPushButton("✏️ 编辑")
        self.token_edit_btn.setFixedHeight(28)
        self.token_edit_btn.setObjectName("iconButton")
        self.token_edit_btn.setToolTip("编辑访问私有更新服务器的令牌（可选）")
        self.token_edit_btn.setStyleSheet("""
            QPushButton {
                background-color: #6B7280;
                color: white;
                font-size: 12px;
                border: none;
                border-radius: 4px;
                padding: 0 10px;
            }
            QPushButton:hover {
                background-color: #4B5563;
            }
            QPushButton:pressed {
                background-color: #374151;
            }
        """)
        self.token_edit_btn.clicked.connect(self.edit_token)
        token_header_layout.addWidget(self.token_edit_btn)

        # 保存按钮（初始隐藏）
        self.token_save_btn = QPushButton("✓ 保存")
        self.token_save_btn.setFixedHeight(28)
        self.token_save_btn.setObjectName("iconButton")
        self.token_save_btn.setToolTip("保存令牌")
        self.token_save_btn.setStyleSheet("""
            QPushButton {
                background-color: #10B981;
                color: white;
                font-size: 12px;
                font-weight: bold;
                border: none;
                border-radius: 4px;
                padding: 0 10px;
            }
            QPushButton:hover {
                background-color: #059669;
            }
            QPushButton:pressed {
                background-color: #047857;
            }
        """)
        self.token_save_btn.clicked.connect(self.save_token)
        self.token_save_btn.hide()
        token_header_layout.addWidget(self.token_save_btn)

        # 取消按钮（初始隐藏）
        self.token_cancel_btn = QPushButton("✕ 取消")
        self.token_cancel_btn.setFixedHeight(28)
        self.token_cancel_btn.setObjectName("iconButton")
        self.token_cancel_btn.setToolTip("取消编辑")
        self.token_cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #EF4444;
                color: white;
                font-size: 12px;
                font-weight: bold;
                border: none;
                border-radius: 4px;
                padding: 0 10px;
            }
            QPushButton:hover {
                background-color: #DC2626;
            }
            QPushButton:pressed {
                background-color: #B91C1C;
            }
        """)
        self.token_cancel_btn.clicked.connect(self.cancel_token_edit)
        self.token_cancel_btn.hide()
        token_header_layout.addWidget(self.token_cancel_btn)

        token_layout.addWidget(token_header)

        # 输入框
        self.token_input = QLineEdit()
        self.token_input.setText(self.app_config.update_token)
        self.token_input.setCursorPosition(0)  # 显示开头而不是结尾
        self.token_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.token_input.setPlaceholderText("留空表示不使用令牌")
        self.token_input.setMinimumHeight(32)
        self.token_input.setReadOnly(True)  # 默认只读
        token_layout.addWidget(self.token_input)

        layout.addWidget(token_group)
        layout.addStretch()
        return group

    def create_directory_section(self) -> QGroupBox:
        """创建工作目录设置区域"""
        group = QGroupBox("📁 工作目录")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(20)

        # 工作目录历史
        dir_group = QWidget()
        dir_layout = QVBoxLayout(dir_group)
        dir_layout.setSpacing(10)

        # 标题和按钮（横向布局）
        dir_header = QWidget()
        dir_header_layout = QHBoxLayout(dir_header)
        dir_header_layout.setContentsMargins(0, 0, 0, 0)
        dir_header_layout.setSpacing(10)

        dir_title = QLabel("📁 最后打开的目录")
        dir_title.setStyleSheet("font-size: 14px; font-weight: bold;")
        dir_header_layout.addWidget(dir_title)

        dir_header_layout.addStretch()

        clear_dir_btn = QPushButton("清除历史记录")
        clear_dir_btn.clicked.connect(self.clear_directory_history)
        clear_dir_btn.setMinimumHeight(28)
        clear_dir_btn.setToolTip("清除最后打开的工作目录路径")
        dir_header_layout.addWidget(clear_dir_btn)

        dir_layout.addWidget(dir_header)

        # 路径显示
        last_dir = self.app_config.last_opened_directory
        self.last_dir_label = QLabel(last_dir if last_dir else "（无）")
        self.last_dir_label.setObjectName("lastDirLabel")
        self.last_dir_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        c = default_theme.colors
        self.last_dir_label.setStyleSheet(f"""
            color: {c.TEXT_PRIMARY};
            padding: 10px;
            background-color: {c.BACKGROUND_SECONDARY};
            border-radius: 4px;
            font-size: 12px;
            font-family: monospace;
        """)
        self.last_dir_label.setWordWrap(True)
        dir_layout.addWidget(self.last_dir_label)

        layout.addWidget(dir_group)
        layout.addStretch()
        return group

    def create_smb_section(self) -> QGroupBox:
        """创建SMB缓存设置区域"""
        from utils.paths import get_cache_dir

        group = QGroupBox("🌐 网络缓存")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(20)

        # SMB缓存管理
        smb_group = QWidget()
        smb_layout = QVBoxLayout(smb_group)
        smb_layout.setSpacing(10)

        # 标题和按钮（横向布局）
        smb_header = QWidget()
        smb_header_layout = QHBoxLayout(smb_header)
        smb_header_layout.setContentsMargins(0, 0, 0, 0)
        smb_header_layout.setSpacing(10)

        smb_title = QLabel("🌐 SMB/NAS 缓存")
        smb_title.setStyleSheet("font-size: 14px; font-weight: bold;")
        smb_header_layout.addWidget(smb_title)

        smb_header_layout.addStretch()

        clear_smb_btn = QPushButton("清除SMB缓存")
        clear_smb_btn.clicked.connect(self.clear_smb_cache)
        clear_smb_btn.setMinimumHeight(28)
        clear_smb_btn.setToolTip("清除SMB/NAS网络路径的图片缓存（如果遇到缓存问题可尝试清除）")
        smb_header_layout.addWidget(clear_smb_btn)

        smb_layout.addWidget(smb_header)

        # 缓存路径显示
        cache_dir = get_cache_dir()
        self.cache_path_label = QLabel(str(cache_dir))
        self.cache_path_label.setObjectName("cacheDirLabel")
        self.cache_path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        c = default_theme.colors
        self.cache_path_label.setStyleSheet(f"""
            color: {c.TEXT_PRIMARY};
            padding: 10px;
            background-color: {c.BACKGROUND_SECONDARY};
            border-radius: 4px;
            font-size: 12px;
            font-family: monospace;
        """)
        self.cache_path_label.setWordWrap(True)
        smb_layout.addWidget(self.cache_path_label)

        layout.addWidget(smb_group)

        # 配置文件信息
        info_group = QWidget()
        info_layout = QVBoxLayout(info_group)
        info_layout.setSpacing(10)

        info_title = QLabel("ℹ️ 配置信息")
        info_title.setStyleSheet("font-size: 14px; font-weight: bold;")
        info_layout.addWidget(info_title)

        version_label = QLabel(f"配置文件版本：{self.app_config._config.get('version', '未知')}")
        info_layout.addWidget(version_label)

        self.config_path_label = QLabel(f"配置文件路径：{self.app_config._config_file}")
        self.config_path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.config_path_label.setWordWrap(True)
        info_layout.addWidget(self.config_path_label)

        layout.addWidget(info_group)

        layout.addStretch()
        return group

    def create_update_section(self) -> QGroupBox:
        """创建更新设置区域"""
        from .components.widgets import Switch

        group = QGroupBox("🔄 更新设置")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(20)

        # 更新检查设置组
        update_group = QWidget()
        update_layout = QVBoxLayout(update_group)
        update_layout.setSpacing(10)

        # 标题
        update_title = QLabel("🔄 更新设置")
        update_title.setStyleSheet("font-size: 14px; font-weight: bold;")
        update_layout.addWidget(update_title)

        # 描述
        update_desc = QLabel("立即检查是否有新版本可用，启用自动检查更新（推荐开启）")
        update_desc.setWordWrap(True)
        update_layout.addWidget(update_desc)

        # 检查更新按钮和自动更新开关（横向布局）
        control_widget = QWidget()
        control_layout = QHBoxLayout(control_widget)
        control_layout.setContentsMargins(0, 0, 0, 0)
        control_layout.setSpacing(15)

        # 检查更新按钮（主要功能）
        check_update_btn = QPushButton("检查更新")
        check_update_btn.clicked.connect(self.check_for_updates)
        check_update_btn.setMinimumHeight(36)
        check_update_btn.setMinimumWidth(120)
        control_layout.addWidget(check_update_btn)

        control_layout.addStretch()

        # 自动检查开关（辅助功能）
        auto_check_label = QLabel("启用自动检查")
        auto_check_label.setStyleSheet("font-size: 13px;")
        control_layout.addWidget(auto_check_label)

        self.auto_update_switch = Switch()
        self.auto_update_switch.setChecked(self.app_config.auto_update_enabled)
        control_layout.addWidget(self.auto_update_switch)

        update_layout.addWidget(control_widget)

        layout.addWidget(update_group)

        # 更新服务器设置
        endpoint_group = QWidget()
        endpoint_layout = QVBoxLayout(endpoint_group)
        endpoint_layout.setSpacing(10)

        # 标题和按钮（横向布局）
        endpoint_header = QWidget()
        endpoint_header_layout = QHBoxLayout(endpoint_header)
        endpoint_header_layout.setContentsMargins(0, 0, 0, 0)
        endpoint_header_layout.setSpacing(10)

        endpoint_title = QLabel("🌐 更新服务器")
        endpoint_title.setStyleSheet("font-size: 14px; font-weight: bold;")
        endpoint_header_layout.addWidget(endpoint_title)

        endpoint_header_layout.addStretch()

        # 编辑按钮
        self.endpoint_edit_btn = QPushButton("✏️ 编辑")
        self.endpoint_edit_btn.setFixedHeight(28)
        self.endpoint_edit_btn.setObjectName("iconButton")
        self.endpoint_edit_btn.setToolTip("编辑更新服务器地址（通常无需修改）")
        self.endpoint_edit_btn.setStyleSheet("""
            QPushButton {
                background-color: #6B7280;
                color: white;
                font-size: 12px;
                border: none;
                border-radius: 4px;
                padding: 0 10px;
            }
            QPushButton:hover {
                background-color: #4B5563;
            }
            QPushButton:pressed {
                background-color: #374151;
            }
        """)
        self.endpoint_edit_btn.clicked.connect(self.edit_endpoint)
        endpoint_header_layout.addWidget(self.endpoint_edit_btn)

        # 保存按钮（初始隐藏）
        self.endpoint_save_btn = QPushButton("✓ 保存")
        self.endpoint_save_btn.setFixedHeight(28)
        self.endpoint_save_btn.setObjectName("iconButton")
        self.endpoint_save_btn.setToolTip("保存更新地址")
        self.endpoint_save_btn.setStyleSheet("""
            QPushButton {
                background-color: #10B981;
                color: white;
                font-size: 12px;
                font-weight: bold;
                border: none;
                border-radius: 4px;
                padding: 0 10px;
            }
            QPushButton:hover {
                background-color: #059669;
            }
            QPushButton:pressed {
                background-color: #047857;
            }
        """)
        self.endpoint_save_btn.clicked.connect(self.save_endpoint)
        self.endpoint_save_btn.hide()
        endpoint_header_layout.addWidget(self.endpoint_save_btn)

        # 取消按钮（初始隐藏）
        self.endpoint_cancel_btn = QPushButton("✕ 取消")
        self.endpoint_cancel_btn.setFixedHeight(28)
        self.endpoint_cancel_btn.setObjectName("iconButton")
        self.endpoint_cancel_btn.setToolTip("取消编辑")
        self.endpoint_cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #EF4444;
                color: white;
                font-size: 12px;
                font-weight: bold;
                border: none;
                border-radius: 4px;
                padding: 0 10px;
            }
            QPushButton:hover {
                background-color: #DC2626;
            }
            QPushButton:pressed {
                background-color: #B91C1C;
            }
        """)
        self.endpoint_cancel_btn.clicked.connect(self.cancel_endpoint_edit)
        self.endpoint_cancel_btn.hide()
        endpoint_header_layout.addWidget(self.endpoint_cancel_btn)

        endpoint_layout.addWidget(endpoint_header)

        # 输入框
        self.endpoint_input = QLineEdit()
        self.endpoint_input.setText(self.app_config.update_endpoint)
        self.endpoint_input.setCursorPosition(0)  # 显示开头而不是结尾
        self.endpoint_input.setPlaceholderText("https://...")
        self.endpoint_input.setMinimumHeight(32)
        self.endpoint_input.setReadOnly(True)  # 默认只读
        endpoint_layout.addWidget(self.endpoint_input)

        layout.addWidget(endpoint_group)

        # 访问令牌设置
        token_group = QWidget()
        token_layout = QVBoxLayout(token_group)
        token_layout.setSpacing(10)

        # 标题和按钮（横向布局）
        token_header = QWidget()
        token_header_layout = QHBoxLayout(token_header)
        token_header_layout.setContentsMargins(0, 0, 0, 0)
        token_header_layout.setSpacing(8)

        token_title = QLabel("🔑 访问令牌")
        token_title.setStyleSheet("font-size: 14px; font-weight: bold;")
        token_header_layout.addWidget(token_title)

        token_header_layout.addStretch()

        # 显示/隐藏按钮
        self.show_token_btn = QPushButton("👁️ 显示")
        self.show_token_btn.setFixedHeight(28)
        self.show_token_btn.setCheckable(True)
        self.show_token_btn.setObjectName("iconButton")
        self.show_token_btn.setToolTip("显示/隐藏令牌内容")
        self.show_token_btn.setStyleSheet("""
            QPushButton {
                background-color: #6B7280;
                color: white;
                font-size: 12px;
                border: none;
                border-radius: 4px;
                padding: 0 10px;
            }
            QPushButton:hover {
                background-color: #4B5563;
            }
            QPushButton:pressed {
                background-color: #374151;
            }
            QPushButton:checked {
                background-color: #3B82F6;
            }
        """)
        self.show_token_btn.clicked.connect(self.toggle_token_visibility)
        token_header_layout.addWidget(self.show_token_btn)

        # 编辑按钮
        self.token_edit_btn = QPushButton("✏️ 编辑")
        self.token_edit_btn.setFixedHeight(28)
        self.token_edit_btn.setObjectName("iconButton")
        self.token_edit_btn.setToolTip("编辑访问私有更新服务器的令牌（可选）")
        self.token_edit_btn.setStyleSheet("""
            QPushButton {
                background-color: #6B7280;
                color: white;
                font-size: 12px;
                border: none;
                border-radius: 4px;
                padding: 0 10px;
            }
            QPushButton:hover {
                background-color: #4B5563;
            }
            QPushButton:pressed {
                background-color: #374151;
            }
        """)
        self.token_edit_btn.clicked.connect(self.edit_token)
        token_header_layout.addWidget(self.token_edit_btn)

        # 保存按钮（初始隐藏）
        self.token_save_btn = QPushButton("✓ 保存")
        self.token_save_btn.setFixedHeight(28)
        self.token_save_btn.setObjectName("iconButton")
        self.token_save_btn.setToolTip("保存令牌")
        self.token_save_btn.setStyleSheet("""
            QPushButton {
                background-color: #10B981;
                color: white;
                font-size: 12px;
                font-weight: bold;
                border: none;
                border-radius: 4px;
                padding: 0 10px;
            }
            QPushButton:hover {
                background-color: #059669;
            }
            QPushButton:pressed {
                background-color: #047857;
            }
        """)
        self.token_save_btn.clicked.connect(self.save_token)
        self.token_save_btn.hide()
        token_header_layout.addWidget(self.token_save_btn)

        # 取消按钮（初始隐藏）
        self.token_cancel_btn = QPushButton("✕ 取消")
        self.token_cancel_btn.setFixedHeight(28)
        self.token_cancel_btn.setObjectName("iconButton")
        self.token_cancel_btn.setToolTip("取消编辑")
        self.token_cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #EF4444;
                color: white;
                font-size: 12px;
                font-weight: bold;
                border: none;
                border-radius: 4px;
                padding: 0 10px;
            }
            QPushButton:hover {
                background-color: #DC2626;
            }
            QPushButton:pressed {
                background-color: #B91C1C;
            }
        """)
        self.token_cancel_btn.clicked.connect(self.cancel_token_edit)
        self.token_cancel_btn.hide()
        token_header_layout.addWidget(self.token_cancel_btn)

        token_layout.addWidget(token_header)

        # 输入框
        self.token_input = QLineEdit()
        self.token_input.setText(self.app_config.update_token)
        self.token_input.setCursorPosition(0)  # 显示开头而不是结尾
        self.token_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.token_input.setPlaceholderText("留空表示不使用令牌")
        self.token_input.setMinimumHeight(32)
        self.token_input.setReadOnly(True)  # 默认只读
        token_layout.addWidget(self.token_input)

        layout.addWidget(token_group)

        layout.addStretch()
        return group

    def create_preview_section(self) -> QGroupBox:
        """创建图像预览设置区域"""
        group = QGroupBox("🖼️ 图像预览设置")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)

        # 标题行：左边是缩放范围标题，右边是全局应用开关
        header_layout = QHBoxLayout()

        zoom_title = QLabel("🔍 缩放范围")
        zoom_title.setStyleSheet("font-size: 14px; font-weight: bold;")
        header_layout.addWidget(zoom_title)

        header_layout.addStretch()

        # 全局应用缩放开关（横向布局）
        apply_label = QLabel("全局应用缩放倍数")
        header_layout.addWidget(apply_label)

        self.remember_zoom_checkbox = Switch()
        self.remember_zoom_checkbox.setChecked(self.app_config.global_zoom_enabled)
        self.remember_zoom_checkbox.setToolTip("启用后，当前的缩放倍数会应用到所有图片。关闭后，每次翻页都会恢复默认适应窗口模式")
        self.remember_zoom_checkbox.toggled.connect(self.on_remember_zoom_changed)
        header_layout.addWidget(self.remember_zoom_checkbox)

        layout.addLayout(header_layout)

        # 最大和最小缩放倍数横向并排
        zoom_controls_layout = QHBoxLayout()
        zoom_controls_layout.setSpacing(15)

        # 最大缩放倍数
        zoom_max_label = QLabel("最大缩放倍数：")
        zoom_controls_layout.addWidget(zoom_max_label)

        self.zoom_max_spinbox = QDoubleSpinBox()
        self.zoom_max_spinbox.setDecimals(1)
        self.zoom_max_spinbox.setRange(1.0, 20.0)
        self.zoom_max_spinbox.setSingleStep(0.5)
        self.zoom_max_spinbox.setValue(self.app_config.image_zoom_max)
        self.zoom_max_spinbox.setSuffix(" 倍")
        self.zoom_max_spinbox.setMinimumHeight(40)
        self.zoom_max_spinbox.setToolTip("设置图片缩放的最大倍数（范围：1.0-20.0）")
        # 禁用滚轮调整
        self.zoom_max_spinbox.wheelEvent = lambda event: None
        self.zoom_max_spinbox.valueChanged.connect(self.on_zoom_max_changed)
        zoom_controls_layout.addWidget(self.zoom_max_spinbox)

        # 最小缩放倍数
        zoom_min_label = QLabel("最小缩放倍数：")
        zoom_controls_layout.addWidget(zoom_min_label)

        self.zoom_min_spinbox = QDoubleSpinBox()
        self.zoom_min_spinbox.setDecimals(2)
        self.zoom_min_spinbox.setRange(0.01, 1.0)
        self.zoom_min_spinbox.setSingleStep(0.01)
        self.zoom_min_spinbox.setValue(self.app_config.image_zoom_min)
        self.zoom_min_spinbox.setSuffix(" 倍")
        self.zoom_min_spinbox.setMinimumHeight(40)
        self.zoom_min_spinbox.setToolTip("设置图片缩放的最小倍数（范围：0.01-1.0）")
        # 禁用滚轮调整
        self.zoom_min_spinbox.wheelEvent = lambda event: None
        self.zoom_min_spinbox.valueChanged.connect(self.on_zoom_min_changed)
        zoom_controls_layout.addWidget(self.zoom_min_spinbox)

        zoom_controls_layout.addStretch()
        layout.addLayout(zoom_controls_layout)

        layout.addStretch()
        return group


    def on_theme_combo_changed(self, index: int):
        """主题下拉列表变化处理"""
        if not hasattr(self, 'auto_theme_switch'):
            return

        # 如果自动切换已启用，下拉列表应该是禁用的，不应触发此事件
        # 但为了安全起见，还是检查一下
        if self.auto_theme_switch.isChecked():
            return

        # 获取选中的主题模式
        mode = self.theme_combo.currentData()
        if mode:
            self.select_theme(mode)

    def on_theme_button_clicked(self, mode: str):
        """主题按钮点击处理（已废弃，保留以兼容旧代码）"""
        if not hasattr(self, 'auto_theme_switch'):
            return

        # 如果自动切换已启用，显示提示
        if self.auto_theme_switch.isChecked():
            toast_warning(self, "请先关闭自动切换")
            return

        # 否则正常切换主题
        self.select_theme(mode)

    def on_auto_theme_toggled(self, checked: bool):
        """自动切换复选框状态变化"""
        if checked:
            # 启用自动模式
            actual_theme = self.app_config.get_auto_theme_by_time()
            # 先设置主题，再设置模式（这样模式设置时可以正确读取新主题）
            self.app_config.theme = actual_theme
            self.app_config.theme_mode = "auto"
            default_theme.set_theme(actual_theme)

            # 禁用主题下拉列表
            self.theme_combo.setEnabled(False)

            # 更新下拉列表显示当前主题（阻止信号触发）
            self.theme_combo.blockSignals(True)
            if actual_theme == "dark":
                self.theme_combo.setCurrentIndex(1)  # 深色主题
            else:
                self.theme_combo.setCurrentIndex(0)  # 浅色主题
            self.theme_combo.blockSignals(False)

            # 应用主题
            self._apply_theme()
            if self.parent():
                if hasattr(self.parent(), 'apply_theme'):
                    self.parent().apply_theme()
                if hasattr(self.parent(), 'theme_button'):
                    theme_icon = '☾' if actual_theme == "light" else '☼'
                    self.parent().theme_button.setText(theme_icon)
                    # 禁用主窗口的主题按钮
                    self.parent().theme_button.setEnabled(False)
                    self.parent().theme_button.setToolTip("已启用自动切换，点击查看提示")
                # 启动主窗口的自动主题定时器
                if hasattr(self.parent(), 'start_auto_theme_timer'):
                    self.parent().start_auto_theme_timer()

            toast_success(self, f"已启用自动切换（当前: {'亮色' if actual_theme == 'light' else '暗色'}主题）")
        else:
            # 禁用自动模式，恢复手动模式
            self.app_config.theme_mode = "manual"

            # 启用主题下拉列表
            self.theme_combo.setEnabled(True)

            # 根据当前主题设置下拉列表（阻止信号触发）
            current_theme = self.app_config.theme
            self.theme_combo.blockSignals(True)
            if current_theme == "dark":
                self.theme_combo.setCurrentIndex(1)  # 深色主题
            else:
                self.theme_combo.setCurrentIndex(0)  # 浅色主题
            self.theme_combo.blockSignals(False)

            # 停止主窗口的自动主题定时器，并重新启用主题按钮
            if self.parent():
                if hasattr(self.parent(), 'stop_auto_theme_timer'):
                    self.parent().stop_auto_theme_timer()
                if hasattr(self.parent(), 'theme_button'):
                    # 重新启用主窗口的主题按钮
                    self.parent().theme_button.setEnabled(True)
                    # 恢复正确的tooltip
                    current_theme = self.app_config.theme
                    theme_tooltip = '切换到暗色主题' if current_theme == "light" else '切换到亮色主题'
                    self.parent().theme_button.setToolTip(theme_tooltip)

            toast_info(self, "已关闭自动切换")

    def on_log_level_changed(self, index: int):
        """日志级别下拉框改变事件"""
        level = self.log_level_combo.itemData(index)
        self.app_config.log_level = level
        toast_success(self, f"日志级别已设置为 {level}（重启生效）")

    def on_toast_level_changed(self, index: int):
        """Toast级别下拉框改变事件"""
        level = self.toast_level_combo.itemData(index)
        self.logger.debug(f"Toast级别下拉框改变: index={index}, level={level}")

        # 更新配置
        self.app_config.toast_level = level

        # 验证配置是否更新（使用已经导入的get_app_config，避免导入方式不一致）
        verify_config = get_app_config()
        self.logger.debug(f"配置验证: self.app_config.toast_level={self.app_config.toast_level}, "
                         f"get_app_config().toast_level={verify_config.toast_level}, "
                         f"是否同一实例={self.app_config is verify_config}")

        toast_success(self, f"Toast提示级别已设置为 {level}")

    def select_theme(self, mode: str):
        """选择主题模式并立即应用

        Args:
            mode: "light"(亮色), "dark"(暗色), "system"(跟随系统)
        """
        # 更新下拉列表状态（阻止信号触发）
        self.theme_combo.blockSignals(True)
        if mode == "system":
            self.theme_combo.setCurrentIndex(2)  # 跟随系统
            # 获取系统主题
            actual_theme = self.app_config.get_system_theme()
            # 先设置主题，再设置模式（这样模式设置时可以正确读取新主题）
            self.app_config.theme = actual_theme
            self.app_config.theme_mode = "system"
            default_theme.set_theme(actual_theme)
            toast_message = f"已切换到系统模式（当前: {'亮色' if actual_theme == 'light' else '暗色'}主题）"
        else:
            # 手动选择亮色或暗色
            if mode == "light":
                self.theme_combo.setCurrentIndex(0)  # 浅色主题
            else:
                self.theme_combo.setCurrentIndex(1)  # 深色主题

            # 先设置主题，再设置模式（这样模式设置时可以正确读取新主题）
            self.app_config.theme = mode
            self.app_config.theme_mode = "manual"
            default_theme.set_theme(mode)
            toast_message = f"已切换到{'亮色' if mode == 'light' else '暗色'}主题"
        self.theme_combo.blockSignals(False)

        # 先应用设置面板的主题样式
        self._apply_theme()

        # 再同步更新主窗口
        if self.parent():
            # 更新主窗口样式
            if hasattr(self.parent(), 'apply_theme'):
                self.parent().apply_theme()

            # 更新主题按钮图标和启用状态
            if hasattr(self.parent(), 'theme_button'):
                current_theme = self.app_config.theme
                theme_icon = '☾' if current_theme == "light" else '☼'
                self.parent().theme_button.setText(theme_icon)

                if mode == "system":
                    # 跟随系统模式：禁用主窗口按钮
                    self.parent().theme_button.setEnabled(False)
                    self.parent().theme_button.setToolTip("已启用跟随系统，点击查看提示")
                else:
                    # 手动模式：启用主窗口按钮
                    self.parent().theme_button.setEnabled(True)
                    theme_tooltip = '切换到暗色主题' if current_theme == "light" else '切换到亮色主题'
                    self.parent().theme_button.setToolTip(theme_tooltip)

        # 提示用户已应用
        toast_success(self, toast_message)

    def toggle_token_visibility(self):
        """切换令牌显示/隐藏"""
        if self.token_input.echoMode() == QLineEdit.EchoMode.Password:
            self.token_input.setEchoMode(QLineEdit.EchoMode.Normal)
            self.show_token_btn.setText("👁️ 隐藏")
        else:
            self.token_input.setEchoMode(QLineEdit.EchoMode.Password)
            self.show_token_btn.setText("👁️ 显示")

    def edit_endpoint(self):
        """进入更新地址编辑模式"""
        # 保存当前值，以便取消时恢复
        self._endpoint_backup = self.endpoint_input.text()

        # 解锁输入框
        self.endpoint_input.setReadOnly(False)
        self.endpoint_input.setFocus()

        # 切换按钮显示
        self.endpoint_edit_btn.hide()
        self.endpoint_save_btn.show()
        self.endpoint_cancel_btn.show()

    def save_endpoint(self):
        """保存更新地址"""
        endpoint = self.endpoint_input.text().strip()
        if not endpoint:
            toast_warning(self, "更新地址不能为空")
            return

        # 保存到配置
        self.app_config.update_endpoint = endpoint
        toast_success(self, "更新地址已保存")

        # 锁定输入框
        self.endpoint_input.setReadOnly(True)

        # 切换按钮显示
        self.endpoint_save_btn.hide()
        self.endpoint_cancel_btn.hide()
        self.endpoint_edit_btn.show()

    def cancel_endpoint_edit(self):
        """取消更新地址编辑"""
        # 恢复原值
        self.endpoint_input.setText(self._endpoint_backup)
        self.endpoint_input.setCursorPosition(0)  # 显示开头而不是结尾

        # 锁定输入框
        self.endpoint_input.setReadOnly(True)

        # 切换按钮显示
        self.endpoint_save_btn.hide()
        self.endpoint_cancel_btn.hide()
        self.endpoint_edit_btn.show()

    def edit_token(self):
        """进入访问令牌编辑模式"""
        # 保存当前值，以便取消时恢复
        self._token_backup = self.token_input.text()

        # 解锁输入框
        self.token_input.setReadOnly(False)
        self.token_input.setFocus()

        # 切换按钮显示
        self.token_edit_btn.hide()
        self.token_save_btn.show()
        self.token_cancel_btn.show()

    def save_token(self):
        """保存访问令牌"""
        token = self.token_input.text().strip()

        # 保存到配置
        self.app_config.update_token = token
        toast_success(self, "访问令牌已保存")

        # 锁定输入框
        self.token_input.setReadOnly(True)

        # 切换按钮显示
        self.token_save_btn.hide()
        self.token_cancel_btn.hide()
        self.token_edit_btn.show()

    def cancel_token_edit(self):
        """取消访问令牌编辑"""
        # 恢复原值
        self.token_input.setText(self._token_backup)
        self.token_input.setCursorPosition(0)  # 显示开头而不是结尾

        # 锁定输入框
        self.token_input.setReadOnly(True)

        # 切换按钮显示
        self.token_save_btn.hide()
        self.token_cancel_btn.hide()
        self.token_edit_btn.show()

    def reset_tutorial(self):
        """重置教程状态"""
        msgBox = QMessageBox(self)
        msgBox.setWindowTitle("确认重置")
        msgBox.setText("确定要重置教程状态吗？\n下次启动程序时将重新显示新手引导。")
        msgBox.setIcon(QMessageBox.Icon.Question)
        yes_btn = msgBox.addButton("是", QMessageBox.ButtonRole.YesRole)
        no_btn = msgBox.addButton("否", QMessageBox.ButtonRole.NoRole)
        msgBox.setDefaultButton(no_btn)
        msgBox.exec()

        if msgBox.clickedButton() == yes_btn:
            self.app_config.reset_tutorial()
            toast_success(self, "教程状态已重置")

            # 更新状态显示
            self.tutorial_status_label.setText("⏸️ 教程未开始")
            c = default_theme.colors
            self.tutorial_status_label.setStyleSheet(f"""
                QLabel {{
                    color: {c.TEXT_SECONDARY};
                    font-size: 13px;
                    padding: 10px;
                    background-color: {c.BACKGROUND_SECONDARY};
                    border-radius: 4px;
                }}
            """)

    def start_tutorial(self):
        """关闭设置面板并立即开始教程"""
        # 重置教程状态
        self.app_config.reset_tutorial()

        # 关闭设置对话框
        self.accept()

        # 触发主窗口的教程
        if hasattr(self.parent(), 'start_tutorial'):
            self.parent().start_tutorial()

    def clear_directory_history(self):
        """清除目录历史"""
        msgBox = QMessageBox(self)
        msgBox.setWindowTitle("确认清除")
        msgBox.setText("确定要清除工作目录历史记录吗？")
        msgBox.setIcon(QMessageBox.Icon.Question)
        yes_btn = msgBox.addButton("是", QMessageBox.ButtonRole.YesRole)
        no_btn = msgBox.addButton("否", QMessageBox.ButtonRole.NoRole)
        msgBox.setDefaultButton(no_btn)
        msgBox.exec()

        if msgBox.clickedButton() == yes_btn:
            self.app_config.last_opened_directory = ""
            self.last_dir_label.setText("（无）")
            toast_success(self, "历史记录已清除")

    def check_for_updates(self):
        """检查更新"""
        try:
            import re
            import subprocess
            from ..utils.paths import get_update_dir
            from .._version_ import compare_version, __version__

            # 1. 首先检查本地是否有待安装的更新包
            local_pending_version = None
            local_download_path = None
            local_batch_path = None

            try:
                update_dir = get_update_dir()
                self.logger.debug(f"检查本地更新目录: {update_dir}")

                if update_dir.exists():
                    # 查找 update 目录下的 exe 文件
                    exe_files = list(update_dir.glob('*.exe'))
                    if exe_files:
                        # 按修改时间排序，取最新的
                        exe_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
                        local_download_path = exe_files[0]

                        # 从文件名提取版本号
                        match = re.search(r'v(\d+\.\d+\.\d+)', local_download_path.name)
                        if match:
                            local_pending_version = match.group(1)

                        # 检查是否有对应的 batch 文件
                        batch_files = list(update_dir.glob('update.bat'))
                        if batch_files:
                            local_batch_path = batch_files[0]

                        self.logger.info(f"检测到本地待安装更新: version={local_pending_version}, exe={local_download_path.name}")

                        # 检查本地更新包版本是否与当前版本相同
                        if local_pending_version == __version__:
                            self.logger.info(f"本地更新包v{local_pending_version}与当前版本相同，清理更新包")
                            try:
                                if local_download_path.exists():
                                    local_download_path.unlink()
                                    self.logger.info(f"已删除同版本更新包: {local_download_path}")
                                if local_batch_path and local_batch_path.exists():
                                    local_batch_path.unlink()
                                    self.logger.info(f"已删除批处理脚本: {local_batch_path}")
                            except Exception as e:
                                self.logger.warning(f"清理同版本更新包失败: {e}")
                            # 跳过提示，继续检查线上更新
                        else:
                            # 本地更新包版本不同于当前版本，询问用户是否安装
                            # 询问用户是否安装本地更新包（使用主题适配样式）
                            msg_box = QMessageBox(self)
                            msg_box.setWindowTitle("发现已下载更新")
                            msg_box.setText(f"检测到待安装的更新 v{local_pending_version}，是否现在重启并完成更新？")
                            msg_box.setIcon(QMessageBox.Icon.Question)

                            # 应用主题适配样式
                            c = default_theme.colors
                            msg_box.setStyleSheet(f"""
                                QMessageBox {{
                                    background-color: {c.BACKGROUND_PRIMARY};
                                    color: {c.TEXT_PRIMARY};
                                    border: 1px solid {c.BORDER_MEDIUM};
                                    border-radius: 8px;
                                    font-size: 14px;
                                    min-width: 400px;
                                }}
                                QMessageBox QLabel {{
                                    color: {c.TEXT_PRIMARY};
                                    font-size: 14px;
                                    padding: 10px;
                                }}
                                QPushButton {{
                                    background-color: {c.PRIMARY};
                                    color: white;
                                    border: none;
                                    border-radius: 6px;
                                    padding: 10px 24px;
                                    font-size: 14px;
                                    font-weight: bold;
                                    min-width: 100px;
                                    min-height: 36px;
                                }}
                                QPushButton:hover {{ background-color: {c.PRIMARY_DARK}; }}
                                QPushButton:pressed {{ background-color: {c.PRIMARY_DARK}; }}
                            """)

                            yes_btn = msg_box.addButton("是", QMessageBox.ButtonRole.YesRole)
                            no_btn = msg_box.addButton("否", QMessageBox.ButtonRole.NoRole)
                            msg_box.setDefaultButton(yes_btn)

                            msg_box.exec()

                            if msg_box.clickedButton() == yes_btn:
                                # 用户选择立即重启
                                self.logger.info(f"启动批处理脚本: {local_batch_path}")
                                subprocess.Popen(["cmd", "/c", "start", "", str(local_batch_path), str(local_download_path)], shell=False)
                                self.logger.info("用户选择立即重启安装更新")
                                QApplication.quit()
                                return  # 退出程序
                            else:
                                # 用户选择稍后安装
                                self.logger.info("用户选择稍后安装本地更新包")
                                # 不继续检查线上更新，直接返回
                                return
            except Exception as e:
                self.logger.debug(f"检查本地更新目录失败: {e}")

            # 2. 没有本地更新包，检查线上更新
            toast_info(self, "正在检查更新...")

            # 获取manifest
            manifest_url = get_manifest_url(latest=True)
            endpoint = self.app_config.update_endpoint
            token = self.app_config.update_token

            manifest = fetch_manifest(manifest_url, token)
            if not manifest:
                toast_warning(self, "无法获取更新信息")
                return

            new_ver = manifest.get('version')
            if not new_ver:
                toast_warning(self, "更新信息格式错误")
                return

            # 比较版本
            cmp_result = compare_version(new_ver, __version__)

            if cmp_result > 0:
                # 有新版本 - 显示红点并显示详细信息对话框
                size_bytes = int(manifest.get('size_bytes', 0) or 0)
                notes = str(manifest.get('notes', '')).strip()

                # 创建详细信息对话框
                update_dialog = UpdateInfoDialog(
                    new_version=new_ver,
                    current_version=__version__,
                    size_bytes=size_bytes,
                    notes=notes,
                    manifest=manifest,
                    token=token,
                    parent=self
                )
                update_dialog.exec()
            elif cmp_result == 0:
                toast_success(self, f"当前已是最新版本 v{__version__}")
            else:
                toast_info(self, f"当前版本 v{__version__} 高于线上版本 v{new_ver}")

        except Exception as e:
            self.logger.error(f"检查更新失败: {e}")
            toast_error(self, f"检查更新失败: {str(e)}")

    def clear_smb_cache(self):
        """清除SMB缓存"""
        msgBox = QMessageBox(self)
        msgBox.setWindowTitle("确认清除")
        msgBox.setText("确定要清除SMB/NAS网络路径的图片缓存吗？")
        msgBox.setIcon(QMessageBox.Icon.Question)
        yes_btn = msgBox.addButton("是", QMessageBox.ButtonRole.YesRole)
        no_btn = msgBox.addButton("否", QMessageBox.ButtonRole.NoRole)
        msgBox.setDefaultButton(no_btn)
        msgBox.exec()

        if msgBox.clickedButton() == yes_btn:
            try:
                # 调用主窗口的图片加载器清除缓存
                if self.parent() and hasattr(self.parent(), 'image_loader'):
                    self.parent().image_loader.clear_cache()
                    toast_success(self, "SMB缓存已清除")
                    self.logger.warning("用户手动清除了SMB缓存")
                else:
                    toast_warning(self, "无法访问图片加载器")
            except Exception as e:
                self.logger.error(f"清除SMB缓存失败: {e}")
                toast_error(self, f"清除缓存失败: {str(e)}")

    def _save_zoom_config(self):
        """保存缩放配置到磁盘（防抖定时器触发）"""
        try:
            self.app_config._save_config()
            self.logger.debug("已保存缩放配置")
        except Exception as e:
            self.logger.error(f"保存缩放配置失败: {e}")

    def on_zoom_max_changed(self, value: float):
        """最大缩放倍数变化处理（使用防抖机制延迟保存）"""
        # 只更新内存中的值，不立即保存（绕过setter）
        self.app_config._config["image_zoom_max"] = value
        # 通知主窗口更新缩放限制（立即生效）
        if self.parent() and hasattr(self.parent(), 'image_label'):
            self.parent().image_label.max_scale = value
        # 重启防抖定时器（500ms后保存）
        self.zoom_save_timer.stop()
        self.zoom_save_timer.start(500)

    def on_zoom_min_changed(self, value: float):
        """最小缩放倍数变化处理（使用防抖机制延迟保存）"""
        # 只更新内存中的值，不立即保存（绕过setter）
        self.app_config._config["image_zoom_min"] = value
        # 通知主窗口更新缩放限制（立即生效）
        if self.parent() and hasattr(self.parent(), 'image_label'):
            self.parent().image_label.min_scale = value
        # 重启防抖定时器（500ms后保存）
        self.zoom_save_timer.stop()
        self.zoom_save_timer.start(500)

    def on_remember_zoom_changed(self, checked: bool):
        """全局应用缩放倍数选项变化处理"""
        self.app_config.global_zoom_enabled = checked
        toast_info(self, f"全局缩放功能已{'启用' if checked else '禁用'}")

    def reset_to_defaults(self):
        """恢复默认设置"""
        c = default_theme.colors

        # 创建消息框（与删除类别确认框样式一致）
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("⚠️ 确认恢复默认")
        msg_box.setText("确定要恢复所有设置到默认值吗？")
        msg_box.setInformativeText("此操作不可撤销。")
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
            # 恢复默认值
            self.theme_combo.setCurrentIndex(0)  # 默认浅色主题
            self.auto_theme_switch.setChecked(False)  # 默认关闭自动切换
            self.theme_combo.setEnabled(True)  # 确保下拉列表可用
            self.auto_update_switch.setChecked(True)
            self.endpoint_input.setText("https://gitlab.desauto.cn/api/v4/projects/820/packages/generic/image_classifier/latest/manifest.json")
            self.endpoint_input.setCursorPosition(0)  # 显示开头而不是结尾
            self.token_input.setText("")
            self.token_input.setCursorPosition(0)  # 显示开头而不是结尾

            # 恢复日志级别和Toast级别到默认值（INFO）
            for i in range(self.log_level_combo.count()):
                if self.log_level_combo.itemData(i) == "INFO":
                    self.log_level_combo.setCurrentIndex(i)
                    break
            for i in range(self.toast_level_combo.count()):
                if self.toast_level_combo.itemData(i) == "INFO":
                    self.toast_level_combo.setCurrentIndex(i)
                    break

            # 保存配置（实时保存）
            self.app_config.auto_update_enabled = True
            self.app_config.log_level = "INFO"
            self.app_config.toast_level = "INFO"

            toast_success(self, "已恢复默认设置")

    def _apply_theme(self):
        """应用主题样式"""
        c = default_theme.colors

        self.setStyleSheet(f"""
            QDialog {{
                background-color: {c.BACKGROUND_PRIMARY};
                color: {c.TEXT_PRIMARY};
            }}
            QLabel {{
                color: {c.TEXT_PRIMARY};
            }}
            QTabWidget::pane {{
                border: 1px solid {c.BORDER_MEDIUM};
                border-radius: 4px;
                background-color: {c.BACKGROUND_CARD};
            }}
            QTabBar::tab {{
                background-color: {c.BACKGROUND_SECONDARY};
                color: {c.TEXT_SECONDARY};
                padding: 8px 16px;
                border: 1px solid {c.BORDER_LIGHT};
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                margin-right: 2px;
            }}
            QTabBar::tab:selected {{
                background-color: {c.BACKGROUND_CARD};
                color: {c.TEXT_PRIMARY};
                border-bottom: 2px solid {c.PRIMARY};
            }}
            QTabBar::tab:hover {{
                background-color: {c.BACKGROUND_HOVER};
            }}
            QPushButton {{
                background-color: {c.PRIMARY};
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 13px;
                min-height: 32px;
            }}
            QPushButton:hover {{
                background-color: {c.PRIMARY_DARK};
            }}
            QPushButton:pressed {{
                background-color: {c.PRIMARY_DARK};
            }}
            QPushButton:checked {{
                background-color: {c.PRIMARY};
                border: 2px solid {c.PRIMARY_DARK};
            }}
            QLineEdit {{
                background-color: {c.BACKGROUND_SECONDARY};
                color: {c.TEXT_PRIMARY};
                border: 1px solid {c.BORDER_MEDIUM};
                border-radius: 4px;
                padding: 6px 10px;
            }}
            QLineEdit:focus {{
                border: 1px solid {c.PRIMARY};
            }}
            QCheckBox {{
                color: {c.TEXT_PRIMARY};
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border: 2px solid {c.BORDER_MEDIUM};
                border-radius: 3px;
                background-color: {c.BACKGROUND_SECONDARY};
            }}
            QCheckBox::indicator:checked {{
                background-color: {c.PRIMARY};
                border-color: {c.PRIMARY};
            }}
            QGroupBox {{
                color: {c.TEXT_PRIMARY};
                border: 1px solid {c.BORDER_MEDIUM};
                border-radius: 6px;
                margin-top: 12px;
                font-weight: bold;
                padding-top: 8px;
                background-color: {c.BACKGROUND_CARD};
            }}
            QGroupBox::title {{
                color: {c.TEXT_PRIMARY};
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 8px;
                background-color: {c.BACKGROUND_CARD};
            }}
            QScrollArea {{
                background-color: {c.BACKGROUND_CARD};
                border: none;
            }}
            QWidget#scrollContent {{
                background-color: {c.BACKGROUND_CARD};
            }}
            QTabWidget > QWidget {{
                background-color: {c.BACKGROUND_CARD};
            }}
            QScrollBar:vertical {{
                background-color: {c.BACKGROUND_SECONDARY};
                width: 12px;
                border-radius: 6px;
                margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background-color: {c.BORDER_MEDIUM};
                border-radius: 6px;
                min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{
                background-color: {c.TEXT_SECONDARY};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
            }}
            QScrollBar:horizontal {{
                background-color: {c.BACKGROUND_SECONDARY};
                height: 12px;
                border-radius: 6px;
                margin: 0px;
            }}
            QScrollBar::handle:horizontal {{
                background-color: {c.BORDER_MEDIUM};
                border-radius: 6px;
                min-width: 20px;
            }}
            QScrollBar::handle:horizontal:hover {{
                background-color: {c.TEXT_SECONDARY};
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                width: 0px;
            }}
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
                background: none;
            }}
            QComboBox {{
                background-color: {c.BACKGROUND_SECONDARY};
                color: {c.TEXT_PRIMARY};
                border: 2px solid {c.BORDER_MEDIUM};
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 13px;
                font-weight: 500;
            }}
            QComboBox:hover {{
                border-color: {c.PRIMARY};
            }}
            QComboBox:disabled {{
                background-color: {c.GRAY_100};
                color: {c.TEXT_DISABLED};
                border-color: {c.BORDER_LIGHT};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 0px;
            }}
            QComboBox::down-arrow {{
                image: none;
                width: 0;
                height: 0;
            }}
            QComboBox QAbstractItemView {{
                background-color: {c.BACKGROUND_CARD};
                border: 2px solid {c.BORDER_MEDIUM};
                border-radius: 6px;
                selection-background-color: {c.PRIMARY};
                selection-color: white;
                padding: 4px;
                color: {c.TEXT_PRIMARY};
                min-width: 180px;
            }}
            QComboBox QAbstractItemView::item {{
                padding: 8px 12px;
                min-height: 32px;
                color: {c.TEXT_PRIMARY};
            }}
            QComboBox QAbstractItemView::item:hover {{
                background-color: {c.BACKGROUND_HOVER};
                color: {c.TEXT_PRIMARY};
            }}
            QComboBox QAbstractItemView::item:selected {{
                background-color: {c.PRIMARY};
                color: white;
            }}
            QWidget#separator_line {{
                background-color: {c.BORDER_MEDIUM};
            }}
            QLabel {{
                color: {c.TEXT_PRIMARY};
            }}
        """)

        # 单独更新教程状态标签的样式（使用内联样式确保优先级）
        if hasattr(self, 'tutorial_status_label') and hasattr(self, 'tutorial_status_color'):
            if default_theme.is_dark:
                bg_color = "rgba(255, 255, 255, 0.08)"
            else:
                bg_color = "rgba(0, 0, 0, 0.05)"

            self.tutorial_status_label.setStyleSheet(f"""
                QLabel#tutorialStatusLabel {{
                    color: {self.tutorial_status_color} !important;
                    font-size: 13px;
                    font-weight: normal !important;
                    padding: 10px;
                    background-color: {bg_color};
                    border-radius: 4px;
                }}
            """)

        # 强制刷新所有子组件的样式（防止缓存导致颜色不更新）
        # 参考主窗口的实现，确保主题切换时所有组件都能正确渲染新颜色
        self._refresh_all_widgets()

    def _refresh_all_widgets(self):
        """强制刷新所有子组件的样式渲染

        Qt的样式系统存在缓存机制，当通过父容器的setStyleSheet更改样式时，
        某些已渲染的子组件可能不会自动更新。这个方法通过unpolish/polish
        强制Qt重新计算和应用所有组件的样式。

        同时，对于所有QLabel和QCheckBox，明确设置它们的颜色以确保正确渲染。
        """
        from PyQt6.QtWidgets import QLabel, QCheckBox
        import re
        c = default_theme.colors

        # 获取所有QLabel和QCheckBox
        all_labels = self.findChildren(QLabel)
        all_checkboxes = self.findChildren(QCheckBox)

        # 手动更新特殊标签
        if hasattr(self, 'last_dir_label') and self.last_dir_label:
            self.last_dir_label.setStyleSheet(f"""
                color: {c.TEXT_PRIMARY};
                padding: 10px;
                background-color: {c.BACKGROUND_SECONDARY};
                border-radius: 4px;
                font-size: 12px;
                font-family: monospace;
            """)

        # 手动更新所有缓存路径标签（基础Tab和高级Tab）
        cache_labels = [label for label in all_labels if label.objectName() == "cacheDirLabel"]
        for cache_label in cache_labels:
            cache_label.setStyleSheet(f"""
                color: {c.TEXT_PRIMARY};
                padding: 10px;
                background-color: {c.BACKGROUND_SECONDARY};
                border-radius: 4px;
                font-size: 12px;
                font-family: monospace;
            """)

        # 处理所有QLabel
        for label in all_labels:
            # 跳过特殊的状态标签（它有自己的颜色处理）
            if label.objectName() in ("tutorialStatusLabel", "lastDirLabel", "cacheDirLabel"):
                continue

            current_style = label.styleSheet()

            if current_style:
                # 有inline样式的情况
                if 'color:' in current_style:
                    # 替换现有颜色
                    new_style = re.sub(r'color:\s*[^;]+', f'color: {c.TEXT_PRIMARY}', current_style)
                    label.setStyleSheet(new_style)
                else:
                    # 添加颜色
                    new_style = current_style.rstrip(';') + f'; color: {c.TEXT_PRIMARY};'
                    label.setStyleSheet(new_style)
            else:
                # 没有inline样式，明确设置颜色以避免缓存问题
                label.setStyleSheet(f'color: {c.TEXT_PRIMARY};')

        # 处理所有QCheckBox
        for checkbox in all_checkboxes:
            current_style = checkbox.styleSheet()

            if current_style:
                if 'color:' in current_style:
                    new_style = re.sub(r'color:\s*[^;]+', f'color: {c.TEXT_PRIMARY}', current_style)
                    checkbox.setStyleSheet(new_style)
                else:
                    new_style = current_style.rstrip(';') + f'; color: {c.TEXT_PRIMARY};'
                    checkbox.setStyleSheet(new_style)
            else:
                checkbox.setStyleSheet(f'color: {c.TEXT_PRIMARY};')

        # 获取所有子组件（递归）
        all_widgets = self.findChildren(QWidget)

        # 对每个组件强制重新应用样式
        for widget in all_widgets:
            # unpolish 移除当前样式，polish 重新应用样式
            # 这会强制Qt重新计算组件的外观
            widget.style().unpolish(widget)
            widget.style().polish(widget)
            # 触发重绘
            widget.update()

        # 同时刷新对话框本身
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def showEvent(self, event):
        """对话框显示时居中并同步配置"""
        super().showEvent(event)

        # 居中对话框
        if not self._centered and self.parent():
            parent_geometry = self.parent().geometry()
            x = parent_geometry.x() + (parent_geometry.width() - self.width()) // 2
            y = parent_geometry.y() + (parent_geometry.height() - self.height()) // 2
            self.move(x, y)
            self._centered = True

        # 重新加载配置以同步主窗口的主题变化
        self.app_config.reload_config()

        # 更新主题下拉框的值
        current_theme_mode = self.app_config.theme_mode

        # 阻止信号触发
        self.theme_combo.blockSignals(True)

        if current_theme_mode == "auto":
            # 自动切换模式
            self.auto_theme_switch.setChecked(True)
            self.theme_combo.setEnabled(False)
            # 设置为当前实际主题
            if self.app_config.theme == "dark":
                self.theme_combo.setCurrentIndex(1)
            else:
                self.theme_combo.setCurrentIndex(0)
        elif current_theme_mode == "system":
            # 跟随系统模式
            self.theme_combo.setCurrentIndex(2)
            self.auto_theme_switch.setChecked(False)
        elif self.app_config.theme == "dark":
            # 暗色主题
            self.theme_combo.setCurrentIndex(1)
            self.theme_combo.setEnabled(True)
            self.auto_theme_switch.setChecked(False)
        else:
            # 亮色主题
            self.theme_combo.setCurrentIndex(0)
            self.theme_combo.setEnabled(True)
            self.auto_theme_switch.setChecked(False)

        # 恢复信号
        self.theme_combo.blockSignals(False)

    def closeEvent(self, event):
        """对话框关闭时，立即保存未完成的配置"""
        # 如果防抖定时器正在运行，立即触发保存
        if self.zoom_save_timer.isActive():
            self.zoom_save_timer.stop()
            self._save_zoom_config()
            self.logger.debug("对话框关闭，立即保存缩放配置")
        super().closeEvent(event)


