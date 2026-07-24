"""
工具栏样式管理模块

集中管理工具栏相关的样式定义，包括工具栏基础样式、
QAction按钮样式、特殊按钮样式等。
"""

from .theme import default_theme


class ToolbarStyles:
    """工具栏样式管理类"""

    @staticmethod
    def get_main_toolbar_style() -> str:
        """主工具栏样式：操作按钮与方形工具按钮共享 32px 高度。"""
        c = default_theme.colors
        s = default_theme.sizes
        return f"""
            QToolBar {{
                background-color: {c.BACKGROUND_PRIMARY};
                border: {s.BORDER_THIN} solid {c.BORDER_LIGHT};
                border-radius: {s.RADIUS_MEDIUM};
                spacing: 6px;
                padding: 5px 6px;
                margin: 2px 4px;
            }}
            QToolBar QToolButton {{
                background-color: {c.PRIMARY};
                color: {c.TEXT_ON_PRIMARY};
                border: 1px solid {c.PRIMARY};
                border-radius: {s.RADIUS_MEDIUM};
                padding: 0 14px;
                margin: 0;
                font-size: {s.FONT_MD};
                font-weight: {default_theme.fonts.WEIGHT_MEDIUM};
                min-width: 88px;
                min-height: 30px;
                max-height: 30px;
            }}
            QToolBar QToolButton:hover {{
                background-color: {c.PRIMARY_DARK};
                border-color: {c.PRIMARY_DARK};
            }}
            QToolBar QToolButton:pressed {{
                background-color: {c.PRIMARY_DARK};
            }}
            QToolBar QToolButton:disabled {{
                background-color: {c.GRAY_300};
                color: {c.TEXT_DISABLED};
                border-color: {c.GRAY_300};
            }}
            QToolBar::separator {{
                background-color: {c.BORDER_LIGHT};
                width: 1px;
                margin: 6px 4px;
            }}
        """

    @staticmethod
    def get_toolbar_separator_style() -> str:
        """工具栏分隔符样式"""
        return f"""
            QToolBar::separator {{
                background-color: {default_theme.colors.BORDER_LIGHT};
                width: 1px;
                margin: 0 {default_theme.sizes.SPACING_XS};
            }}
        """


# 快捷方法
def apply_main_toolbar_style(toolbar):
    """为主工具栏应用样式"""
    toolbar.setStyleSheet(ToolbarStyles.get_main_toolbar_style())
