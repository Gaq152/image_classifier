"""
主窗口内部模块

包含主窗口相关的组件和状态管理。

阶段二目标结构（决策 Q1 调整）：
- state/: 状态接口（Protocol）- 已废弃数据类
- builders/: UI 构建器（待创建）
- panels/: 面板组件（待创建）
- app_window.py: 重构后的主窗口壳（待创建）

当前状态：
- ✅ state/interfaces.py 已创建（Protocol 接口）
- ❌ SessionState, ViewState 数据类已废弃（决策 Q1）
- ⏳ 主窗口类仍在 ui/main_window.py 文件中（等待拆分）
- ⏳ builders/panels 待后续任务创建

使用方式：
    # Manager 导入状态接口
    from ui._main_window.state.interfaces import StateView, StateMutator, UIHooks

    # 主窗口实现接口，使用裸属性管理状态
    class ImageClassifier(QMainWindow, StateView, UIHooks):
        def __init__(self):
            self.current_index = 0
            self.classified_images = {}
"""

# 从 state 模块导出接口
from .state import (
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
