"""
Toast组件样式定义

定义不同类型Toast的颜色、图标和CSS样式。
"""

from .toast_config import ToastType


class ToastStyles:
    """Toast样式管理类"""

    # Toast类型样式配置
    STYLES = {
        ToastType.INFO: {
            'background': '#3498DB',  # 完全不透明的蓝色
            'text_color': '#ffffff',
            'border_color': '#2980B9',  # 深蓝色边框
            'icon': 'ℹ️',
            'icon_unicode': 'ℹ',  # 备用Unicode字符
            'shadow_color': 'rgba(52, 152, 219, 100)'
        },
        ToastType.SUCCESS: {
            'background': '#27AE60',  # 完全不透明的绿色
            'text_color': '#ffffff',
            'border_color': '#229954',  # 深绿色边框
            'icon': '✅',
            'icon_unicode': '✓',  # 备用Unicode字符
            'shadow_color': 'rgba(39, 174, 96, 100)'
        },
        ToastType.WARNING: {
            'background': '#F39C12',  # 完全不透明的橙色
            'text_color': '#ffffff',
            'border_color': '#E67E22',  # 深橙色边框
            'icon': '⚠️',
            'icon_unicode': '⚠',  # 备用Unicode字符
            'shadow_color': 'rgba(243, 156, 18, 100)'
        },
        ToastType.ERROR: {
            'background': '#E74C3C',  # 完全不透明的红色
            'text_color': '#ffffff',
            'border_color': '#C0392B',  # 深红色边框
            'icon': '❌',
            'icon_unicode': '✗',  # 备用Unicode字符
            'shadow_color': 'rgba(231, 76, 60, 100)'
        }
    }

    @staticmethod
    def get_style(toast_type: ToastType) -> dict:
        """获取指定类型的样式配置"""
        return ToastStyles.STYLES.get(toast_type, ToastStyles.STYLES[ToastType.INFO])

    @staticmethod
    def get_stylesheet(toast_type: ToastType, config) -> str:
        """生成Toast的CSS样式表"""
        style = ToastStyles.get_style(toast_type)

        return f"""
            QWidget {{
                background-color: {style['background']};
                border: 3px solid {style['border_color']};
                border-radius: 8px;
                margin: 4px;
                padding: 4px;
            }}

            QHBoxLayout {{
                margin: 0px;
                spacing: {config.icon_spacing}px;
            }}

            QLabel#toast_icon {{
                color: {style['text_color']};
                font-size: {config.icon_size}px;
                font-weight: bold;
                border: none;
                background: transparent;
                padding: {config.padding_vertical}px {config.padding_horizontal//2}px;
                margin: 0px;
                min-width: {config.icon_size + 4}px;
                text-align: center;
            }}

            QLabel#toast_text {{
                color: {style['text_color']};
                font-size: {config.font_size}px;
                font-weight: {config.font_weight};
                border: none;
                background: transparent;
                padding: {config.padding_vertical}px {config.padding_horizontal}px;
                margin: 0px;
            }}

            QPushButton#toast_close {{
                color: {style['text_color']};
                background: transparent;
                border: none;
                border-radius: 4px;
                padding: 4px;
                margin: 2px;
                font-size: 12px;
                font-weight: bold;
            }}

            QPushButton#toast_close:hover {{
                background-color: rgba(255, 255, 255, 30);
            }}

            QPushButton#toast_close:pressed {{
                background-color: rgba(255, 255, 255, 50);
            }}
        """

    @staticmethod
    def get_icon(toast_type: ToastType, use_unicode: bool = False) -> str:
        """获取Toast类型对应的图标"""
        style = ToastStyles.get_style(toast_type)
        return style['icon_unicode'] if use_unicode else style['icon']