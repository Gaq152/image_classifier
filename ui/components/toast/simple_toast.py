"""
简化版Toast实现 - 参考成功的悬浮消息实现
基于项目中成功的show_floating_message实现模式
"""

import logging
from PyQt6.QtWidgets import QLabel
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QFont
from enum import Enum
from ....utils.app_config import get_app_config


class ToastType(Enum):
    """Toast类型"""
    DEBUG = "debug"
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    FLOATING = "floating"  # 保持原悬浮消息样式


# Toast级别权重（用于过滤）
TOAST_LEVEL_WEIGHT = {
    "DEBUG": 0,
    "INFO": 1,
    "WARNING": 2,
    "ERROR": 3
}


class ToastPosition(Enum):
    """Toast位置"""
    TOP_RIGHT = "top_right"
    TOP_CENTER = "top_center"
    TOP_LEFT = "top_left"
    CENTER = "center"
    BOTTOM_LEFT = "bottom_left"
    BOTTOM_CENTER = "bottom_center"
    BOTTOM_RIGHT = "bottom_right"


class Toast:
    """简化Toast系统 - 基于成功的悬浮消息实现"""

    # Toast样式配置
    STYLES = {
        ToastType.DEBUG: {
            'background': 'rgba(108, 117, 125, 230)',
            'border': 'rgba(73, 80, 87, 255)',
            'icon': '🐛'
        },
        ToastType.INFO: {
            'background': 'rgba(52, 152, 219, 230)',
            'border': 'rgba(41, 128, 185, 255)',
            'icon': 'ℹ️'
        },
        ToastType.SUCCESS: {
            'background': 'rgba(39, 174, 96, 230)',
            'border': 'rgba(34, 153, 84, 255)',
            'icon': '✅'
        },
        ToastType.WARNING: {
            'background': 'rgba(243, 156, 18, 230)',
            'border': 'rgba(211, 134, 15, 255)',
            'icon': '⚠️'
        },
        ToastType.ERROR: {
            'background': 'rgba(231, 76, 60, 230)',
            'border': 'rgba(192, 57, 43, 255)',
            'icon': '❌'
        },
        ToastType.FLOATING: {
            'background': 'rgba(0, 0, 0, 200)',
            'border': 'rgba(255, 255, 255, 100)',
            'icon': ''  # 不使用默认图标，保持消息中的原始emoji
        }
    }

    @staticmethod
    def _should_show_toast(toast_type: ToastType) -> bool:
        """判断是否应该显示Toast（根据配置的级别）"""
        # FLOATING类型总是显示
        if toast_type == ToastType.FLOATING:
            return True

        try:
            app_config = get_app_config()
            configured_level = app_config.toast_level.upper()

            # 将ToastType映射到级别名称
            type_to_level = {
                ToastType.DEBUG: "DEBUG",
                ToastType.INFO: "INFO",
                ToastType.SUCCESS: "INFO",  # SUCCESS视为INFO级别
                ToastType.WARNING: "WARNING",
                ToastType.ERROR: "ERROR"
            }

            toast_level = type_to_level.get(toast_type, "INFO")
            configured_weight = TOAST_LEVEL_WEIGHT.get(configured_level, 1)
            toast_weight = TOAST_LEVEL_WEIGHT.get(toast_level, 1)

            # Toast过滤日志（使用DEBUG级别）
            import logging
            logger = logging.getLogger(__name__)
            should_show = toast_weight >= configured_weight
            logger.debug(f"Toast过滤检查: [{toast_type.value}] 消息级别={toast_level}(权重{toast_weight}), "
                        f"配置级别={configured_level}(权重{configured_weight}), "
                        f"结果={'显示' if should_show else '过滤'}")

            return toast_weight >= configured_weight
        except Exception as e:
            # 配置读取失败时，默认显示所有INFO及以上
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Toast过滤失败: {e}，默认显示")
            return True

    @staticmethod
    def show(parent, message: str, toast_type: ToastType = ToastType.INFO,
             duration: int = 3000, position: ToastPosition = ToastPosition.TOP_CENTER,
             show_icon: bool = True):
        """显示Toast消息 - 基于成功的悬浮消息实现"""
        try:
            # 检查是否应该显示
            if not Toast._should_show_toast(toast_type):
                return

            # 获取样式
            style = Toast.STYLES.get(toast_type, Toast.STYLES[ToastType.INFO])

            # 如果已有Toast，先隐藏
            if hasattr(parent, '_toast') and parent._toast:
                parent._toast.hide()
                parent._toast.deleteLater()

            # 创建完整消息内容
            if show_icon:
                full_message = f"{style['icon']} {message}"
            else:
                full_message = message

            # 创建Toast标签（直接作为parent的子组件）
            parent._toast = QLabel(full_message, parent)

            # 为FLOATING类型使用特殊样式，匹配原悬浮消息
            if toast_type == ToastType.FLOATING:
                parent._toast.setStyleSheet(f"""
                    QLabel {{
                        background-color: {style['background']};
                        color: white;
                        border-radius: 8px;
                        padding: 12px 20px;
                        font-size: 14px;
                        font-weight: bold;
                        border: 1px solid {style['border']};
                    }}
                """)
                # 设置字体（匹配原悬浮消息）
                font = QFont()
                font.setPointSize(12)
                font.setBold(True)
                parent._toast.setFont(font)
            else:
                # 使用标准Toast样式
                parent._toast.setStyleSheet(f"""
                    QLabel {{
                        background-color: {style['background']};
                        color: white;
                        border-radius: 6px;
                        padding: 8px 16px;
                        font-size: 13px;
                        font-weight: bold;
                        border: 2px solid {style['border']};
                    }}
                """)
                # 设置字体
                font = QFont()
                font.setPointSize(11)
                font.setBold(True)
                parent._toast.setFont(font)

            # 调整大小并根据位置定位
            parent._toast.adjustSize()
            x, y = Toast._calculate_position(parent, parent._toast, position)
            parent._toast.move(x, y)

            # 显示Toast
            parent._toast.show()
            parent._toast.raise_()  # 确保在最顶层

            # 设置定时器自动隐藏
            if hasattr(parent, '_toast_timer'):
                parent._toast_timer.stop()

            parent._toast_timer = QTimer()
            parent._toast_timer.setSingleShot(True)
            parent._toast_timer.timeout.connect(lambda: Toast._hide_toast(parent))
            parent._toast_timer.start(duration)

            return parent._toast

        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"显示Toast失败: {e}")
            return None

    @staticmethod
    def _calculate_position(parent, toast_widget, position: ToastPosition):
        """计算Toast位置"""
        parent_width = parent.width()
        parent_height = parent.height()
        toast_width = toast_widget.width()
        toast_height = toast_widget.height()
        margin = 20

        if position == ToastPosition.TOP_RIGHT:
            x = parent_width - toast_width - margin
            y = margin
        elif position == ToastPosition.TOP_CENTER:
            x = (parent_width - toast_width) // 2
            y = margin
        elif position == ToastPosition.TOP_LEFT:
            x = margin
            y = margin
        elif position == ToastPosition.CENTER:
            x = (parent_width - toast_width) // 2
            y = (parent_height - toast_height) // 2
        elif position == ToastPosition.BOTTOM_LEFT:
            x = margin
            y = parent_height - toast_height - margin
        elif position == ToastPosition.BOTTOM_CENTER:
            x = (parent_width - toast_width) // 2
            y = parent_height - toast_height - margin
        elif position == ToastPosition.BOTTOM_RIGHT:
            x = parent_width - toast_width - margin
            y = parent_height - toast_height - margin
        else:
            # 默认右上角
            x = parent_width - toast_width - margin
            y = margin

        return x, y

    @staticmethod
    def _hide_toast(parent):
        """隐藏Toast"""
        try:
            if hasattr(parent, '_toast') and parent._toast:
                parent._toast.hide()
                parent._toast.deleteLater()
                parent._toast = None
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.debug(f"隐藏Toast失败: {e}")


# 便捷函数 - 兼容原始API
def toast_info(parent, message: str, duration: int = 3000, position: ToastPosition = ToastPosition.TOP_CENTER):
    """显示信息Toast"""
    return Toast.show(parent, message, ToastType.INFO, duration, position)


def toast_success(parent, message: str, duration: int = 3000, position: ToastPosition = ToastPosition.TOP_CENTER):
    """显示成功Toast"""
    return Toast.show(parent, message, ToastType.SUCCESS, duration, position)


def toast_warning(parent, message: str, duration: int = 3000, position: ToastPosition = ToastPosition.TOP_CENTER):
    """显示警告Toast"""
    return Toast.show(parent, message, ToastType.WARNING, duration, position)


def toast_error(parent, message: str, duration: int = 3000, position: ToastPosition = ToastPosition.TOP_CENTER):
    """显示错误Toast"""
    return Toast.show(parent, message, ToastType.ERROR, duration, position)


# 简化版便捷函数
def simple_toast_info(parent, message: str, duration: int = 3000):
    """显示信息Toast（简化版）"""
    return Toast.show(parent, message, ToastType.INFO, duration)


def simple_toast_success(parent, message: str, duration: int = 3000):
    """显示成功Toast（简化版）"""
    return Toast.show(parent, message, ToastType.SUCCESS, duration)


def simple_toast_warning(parent, message: str, duration: int = 3000):
    """显示警告Toast（简化版）"""
    return Toast.show(parent, message, ToastType.WARNING, duration)


def simple_toast_error(parent, message: str, duration: int = 3000):
    """显示错误Toast（简化版）"""
    return Toast.show(parent, message, ToastType.ERROR, duration)


def toast_floating(parent, message: str, duration: int = 3000, position: ToastPosition = ToastPosition.TOP_CENTER):
    """显示悬浮样式Toast（保持原悬浮消息样式）"""
    return Toast.show(parent, message, ToastType.FLOATING, duration, position, show_icon=False)