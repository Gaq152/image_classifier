"""
通用UI组件模块

提供可复用的UI组件，包括自定义按钮、标签、列表项等。
这些组件使用统一的样式系统，便于维护和扩展。

使用示例:
    from ui.components.widgets import EnhancedButton, StatusLabel

    # 创建带样式的按钮
    button = EnhancedButton("点击我", button_type="primary")

    # 创建状态标签
    status_label = StatusLabel("成功", status="success")

Note:
    此模块为预留结构，用于未来抽取可复用组件。
    当前组件定义仍在 ui/widgets.py 中，后续重构时会逐步迁移到此处。
"""

# 预留导入位置
# from .enhanced_button import EnhancedButton
# from .status_label import StatusLabel
from .category_button import CategoryButton
# Phase 1.1: ImageListItem已废弃，Model/View架构不再需要
# from .image_list_item import ImageListItem
from .enhanced_image_label import EnhancedImageLabel
from .statistics_panel import StatisticsPanel
from .switch import Switch

# 定义公共接口
__all__ = [
    # 预留组件导出
    # 'EnhancedButton',
    # 'StatusLabel',
    'CategoryButton',
    # 'ImageListItem',  # Phase 1.1: 已废弃
    'EnhancedImageLabel',
    'StatisticsPanel',
    'Switch',
]

# 版本信息
__version__ = '1.0.0'
__author__ = 'Image Classifier Team'
__description__ = 'Reusable UI components with unified styling'