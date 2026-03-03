"""
状态管理模块

包含状态接口定义（Protocol），供 Manager 依赖注入使用。

设计理念（决策 Q1 - 废弃数据类）：
- ❌ 数据类（SessionState, ViewState）：已废弃
- ✅ 接口（StateView, StateMutator, UIHooks, ImageLoader, ImageNavigator）：保留供 Manager 使用
- 主窗口使用裸属性管理状态，实现 Protocol 接口，注入给 Manager

使用方式：
    from ui._main_window.state.interfaces import StateView, UIHooks

    class ImageClassifier(QMainWindow, StateView, UIHooks):
        def __init__(self):
            # 直接使用裸属性，不使用数据类
            self.current_index = 0
            self.classified_images = {}
"""

# 接口
from .interfaces import (
    StateView,
    StateMutator,
    UIHooks,
    ImageLoader,
    ImageNavigator,
    StateViewType,
    StateMutatorType,
    UIHooksType,
    ImageLoaderType,
    ImageNavigatorType,
)

__all__ = [
    # 接口
    'StateView',
    'StateMutator',
    'UIHooks',
    'ImageLoader',
    'ImageNavigator',
    # 类型别名
    'StateViewType',
    'StateMutatorType',
    'UIHooksType',
    'ImageLoaderType',
    'ImageNavigatorType',
]
