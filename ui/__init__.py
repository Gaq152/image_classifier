"""
UI模块

包含应用程序的用户界面组件。
"""

from .main_window import ImageClassifier
from .components.widgets import CategoryButton, EnhancedImageLabel, StatisticsPanel
# Phase 1.1: ImageListItem已废弃，Model/View架构不再需要
from .dialogs import (CategoryShortcutDialog, AddCategoriesDialog,
                     TabbedHelpDialog, ProgressDialog)

__all__ = [
    'ImageClassifier',
    'CategoryButton',
    'EnhancedImageLabel',
    'StatisticsPanel',
    'CategoryShortcutDialog',
    'AddCategoriesDialog',
    'TabbedHelpDialog',
    'ProgressDialog'
]
