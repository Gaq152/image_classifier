"""
Toast通知组件模块

基于成功的悬浮消息实现，提供现代化的非阻塞Toast通知功能。
使用简化架构，确保稳定可靠的显示效果。
"""

# 导入简化版Toast系统（主要接口）
from .simple_toast import (
    Toast, ToastType, ToastPosition,
    toast_info, toast_success, toast_warning, toast_error, toast_floating
)

# 定义公共接口
__all__ = [
    'Toast',
    'ToastType',
    'ToastPosition',
    'toast_info',
    'toast_success',
    'toast_warning',
    'toast_error',
    'toast_floating',
]