"""
主窗口样式管理模块

集中管理主窗口相关的样式定义，包括主窗口背景、
分割器样式等UI容器组件的样式。
"""

from .theme import default_theme


class MainWindowStyles:
    """主窗口样式管理类"""

    @staticmethod
    def get_main_window_style() -> str:
        """主窗口基础样式"""
        return f"""
            QMainWindow {{
                background-color: {default_theme.colors.BACKGROUND_PRIMARY};
            }}
            QSplitter::handle {{
                background-color: #BDC3C7;
                border: {default_theme.sizes.BORDER_THIN} solid #95A5A6;
                width: 4px;
                border-radius: {default_theme.sizes.RADIUS_SMALL};
            }}
            QSplitter::handle:hover {{
                background-color: {default_theme.colors.PRIMARY};
            }}
        """

    @staticmethod
    def get_central_widget_style() -> str:
        """中央控件样式"""
        return f"""
            QWidget {{
                background-color: {default_theme.colors.BACKGROUND_PRIMARY};
                color: {default_theme.colors.TEXT_PRIMARY};
            }}
        """

    @staticmethod
    def get_window_frame_style() -> str:
        """窗口框架样式"""
        return f"""
            QMainWindow {{
                background-color: {default_theme.colors.BACKGROUND_PRIMARY};
                color: {default_theme.colors.TEXT_PRIMARY};
                border: {default_theme.sizes.BORDER_THIN} solid {default_theme.colors.BORDER_LIGHT};
            }}
        """


# 快捷方法
def apply_main_window_style(window):
    """为主窗口应用样式"""
    window.setStyleSheet(MainWindowStyles.get_main_window_style())


def apply_central_widget_style(widget):
    """为中央控件应用样式"""
    widget.setStyleSheet(MainWindowStyles.get_central_widget_style())