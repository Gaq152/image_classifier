"""
Toast组件配置类和枚举定义

定义Toast的类型、位置、配置等核心参数。
"""

from enum import Enum
from typing import Optional


class ToastType(Enum):
    """Toast消息类型枚举"""
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


class ToastPosition(Enum):
    """Toast显示位置枚举"""
    TOP_CENTER = "top_center"
    TOP_LEFT = "top_left"
    TOP_RIGHT = "top_right"
    BOTTOM_CENTER = "bottom_center"
    BOTTOM_LEFT = "bottom_left"
    BOTTOM_RIGHT = "bottom_right"
    CENTER = "center"


class ToastConfig:
    """Toast配置类"""

    def __init__(self):
        # 显示配置
        self.duration = 3000  # 显示时长(ms)
        self.position = ToastPosition.TOP_CENTER
        self.auto_close = True
        self.closable = False  # 是否显示关闭按钮

        # 尺寸配置
        self.max_width = 400
        self.min_width = 200
        self.max_height = 120

        # 布局配置
        self.margin = 20  # 距离边缘的边距
        self.spacing = 10  # Toast之间的间距
        self.max_count = 5  # 最大同时显示数量

        # 动画配置
        self.animation_duration = 300  # 动画时长(ms)
        self.fade_in_duration = 250
        self.fade_out_duration = 200

        # 字体配置
        self.font_size = 18  # 进一步增加字体大小
        self.font_weight = 700  # 进一步增加字体粗细
        self.icon_size = 20  # 增加图标大小

        # 边距配置
        self.padding_horizontal = 16
        self.padding_vertical = 12
        self.icon_spacing = 8

    def copy(self) -> 'ToastConfig':
        """创建配置副本"""
        new_config = ToastConfig()
        for key, value in self.__dict__.items():
            setattr(new_config, key, value)
        return new_config

    def update(self, **kwargs) -> 'ToastConfig':
        """更新配置参数"""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
        return self


# 默认配置实例
DEFAULT_CONFIG = ToastConfig()