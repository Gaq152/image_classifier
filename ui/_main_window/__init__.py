"""
主窗口内部模块

包含主窗口相关的组件和状态管理。

阶段二目标结构：
- state/: 状态管理（数据类 + 接口）
- builders/: UI 构建器（待创建）
- controllers/: UI 控制器（待创建）
- panels/: 面板组件（待创建）
- app_window.py: 重构后的主窗口壳（Task 2.7）

当前状态：
- ✅ state/ 已创建（Task 2.1）
- ⏳ 主窗口类仍在 ui/main_window.py 文件中（等待 Task 2.7 迁移）
- ⏳ 其他模块待后续任务创建

使用方式：
    # Manager 导入状态接口
    from ui._main_window.state import SessionState, ViewState
    from ui._main_window.state.interfaces import StateView, StateMutator, UIHooks, ImageLoader

    # 或者通过这个模块导入
    from ui._main_window import SessionState, ViewState, StateView, StateMutator, UIHooks, ImageLoader
"""

# 从 state 模块导出所有状态类和接口
from .state import (
    SessionState,
    ViewState,
    StateView,
    StateMutator,
    UIHooks,
    ImageLoader,
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
]
