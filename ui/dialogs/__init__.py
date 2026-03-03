"""
对话框模块

包含应用程序使用的各种对话框组件。
重构后的模块化结构，保持向后兼容。
"""

# 工具类
from .utils.update_checker import UpdateCheckerThread

# 独立组件
from .widgets.animated_toggle import AnimatedToggle

# 已拆分的对话框
from .progress_dialog import ProgressDialog
from .category_shortcut_dialog import CategoryShortcutDialog
from .add_categories_dialog import AddCategoriesDialog
from .ignored_categories_dialog import ManageIgnoredCategoriesDialog
from .help_dialog import TabbedHelpDialog

# SettingsDialog 已拆分到 settings 子包
from .settings import SettingsDialog

__all__ = [
    'UpdateCheckerThread',
    'AnimatedToggle',
    'CategoryShortcutDialog',
    'AddCategoriesDialog',
    'TabbedHelpDialog',
    'ProgressDialog',
    'ManageIgnoredCategoriesDialog',
    'SettingsDialog',
]
