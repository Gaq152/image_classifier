"""
状态管理模块

包含状态数据类和接口定义。

设计理念（Codex Review，2025-12-04）：
- 数据类（SessionState, ViewState）：存储状态数据
- 接口（StateView, StateMutator, UIHooks, ImageLoader）：Manager 依赖注入，消除 Parent Reaching
- 主窗口持有数据类，实现接口，注入给 Manager

使用方式：
    from ui.main_window.state import SessionState, ViewState
    from ui.main_window.state.interfaces import StateView, UIHooks

    class ImageClassifier(QMainWindow, StateView, UIHooks):
        def __init__(self):
            self.session_state = SessionState()
            self.view_state = ViewState()
"""

# 数据类
from .session_state import SessionState
from .view_state import ViewState

# 接口
from .interfaces import (
    StateView,
    StateMutator,
    UIHooks,
    ImageLoader,
    StateViewType,
    StateMutatorType,
    UIHooksType,
    ImageLoaderType,
)

__all__ = [
    # 数据类
    'SessionState',
    'ViewState',
    # 接口
    'StateView',
    'StateMutator',
    'UIHooks',
    'ImageLoader',
    # 类型别名
    'StateViewType',
    'StateMutatorType',
    'UIHooksType',
    'ImageLoaderType',
]
