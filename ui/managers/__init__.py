"""
管理器模块

包含各种功能管理器，用于分离main_window中的复杂逻辑。

状态接口（阶段二）：
- 状态接口已移至 ui._main_window.state.interfaces
- Manager 应从 ui._main_window.state.interfaces 导入接口
- 数据类在 ui._main_window.state (SessionState, ViewState)

使用方式：
    from ui._main_window.state import SessionState, ViewState
    from ui._main_window.state.interfaces import StateView, UIHooks
    from ui.managers import FileStateManager
"""

from .file_state_manager import FileStateManager
from .image_navigation_manager import ImageNavigationManager

__all__ = [
    'FileStateManager',
    'ImageNavigationManager',
]
