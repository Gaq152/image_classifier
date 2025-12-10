"""
管理器模块

包含各种功能管理器，用于分离main_window中的复杂逻辑。

状态接口（阶段二，决策 Q1 调整）：
- 状态接口在 ui._main_window.state.interfaces
- Manager 通过 Protocol 接口访问主窗口状态
- ❌ SessionState/ViewState 数据类已废弃

使用方式：
    from ui._main_window.state.interfaces import StateView, UIHooks
    from ui.managers import FileStateManager, ImageNavigationManager, FileOperationManager
"""

from .file_state_manager import FileStateManager
from .image_navigation_manager import ImageNavigationManager
from .file_operation_manager import FileOperationManager
from .category_manager import CategoryManager

__all__ = [
    'FileStateManager',
    'ImageNavigationManager',
    'FileOperationManager',
    'CategoryManager',
]
