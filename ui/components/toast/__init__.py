"""
Toast通知组件模块

基于成功的悬浮消息实现，提供现代化的非阻塞Toast通知功能。
使用简化架构，确保稳定可靠的显示效果。

使用示例:
    from ui.components.toast import toast_info, toast_success, toast_warning, toast_error

    # 显示不同类型的Toast
    toast_info(self, "✨ 操作成功完成")
    toast_success(self, "🎉 文件保存成功")
    toast_warning(self, "⚠️ 磁盘空间不足")
    toast_error(self, "❌ 网络连接失败")

    # 自定义位置
    toast_info(self, "📂 正在处理文件...",
              duration=5000,
              position=ToastPosition.BOTTOM_CENTER)
"""

# 导入简化版Toast系统（主要接口）
from .simple_toast import (
    Toast, ToastType, ToastPosition,
    toast_info, toast_success, toast_warning, toast_error, toast_floating,
    simple_toast_info, simple_toast_success, simple_toast_warning, simple_toast_error
)

# 为了向后兼容，保留旧的导入路径
from .toast_config import ToastConfig
from .toast_styles import ToastStyles

# 定义公共接口
__all__ = [
    # 新的简化版系统
    'Toast',
    'ToastType',
    'ToastPosition',
    'toast_info',
    'toast_success',
    'toast_warning',
    'toast_error',
    'toast_floating',
    'simple_toast_info',
    'simple_toast_success',
    'simple_toast_warning',
    'simple_toast_error',
    # 向后兼容
    'ToastConfig',
    'ToastStyles',
]

# 版本信息
__version__ = '2.0.0'  # 升级到2.0，基于简化版实现
__author__ = 'Image Classifier Team'
__description__ = 'Simple and reliable PyQt6 Toast notification system'