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
        """主工具栏样式"""
        return f"""
            QToolBar {{
                background-color: {default_theme.colors.BACKGROUND_PRIMARY};
                border: {default_theme.sizes.BORDER_THIN} solid {default_theme.colors.BORDER_LIGHT};
                border-radius: {default_theme.sizes.RADIUS_MEDIUM};
                spacing: {default_theme.sizes.SPACING_SM};
                padding: {default_theme.sizes.SPACING_SM};
                margin: 2px;
            }}
            /* QAction 按钮样式 - 现代化蓝色主题 */
            QToolBar QToolButton {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                           stop:0 #42A5F5, stop:1 #2196F3);
                color: {default_theme.colors.TEXT_ON_PRIMARY};
                border: none;
                border-radius: {default_theme.sizes.RADIUS_LARGE};
                padding: {default_theme.sizes.SPACING_SM} {default_theme.sizes.SPACING_LG};
                margin: {default_theme.sizes.SPACING_XS} 2px;
                font-size: {default_theme.sizes.FONT_MD};
                font-weight: {default_theme.fonts.WEIGHT_MEDIUM};
                min-width: 90px;
                min-height: 30px;
                max-height: 30px;
            }}
            QToolBar QToolButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                           stop:0 #1E88E5, stop:1 #1976D2);
            }}
            QToolBar QToolButton:pressed {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                           stop:0 #1565C0, stop:1 #0D47A1);
            }}
            /* 普通QPushButton样式 - 不影响模式按钮，与QToolButton保持一致 */
            QToolBar QPushButton:not([objectName="mode_button"]):not([objectName="refresh_button"]):not([objectName="help_button"]):not([objectName="category_mode_button"]) {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                           stop:0 #42A5F5, stop:1 #2196F3);
                color: {default_theme.colors.TEXT_ON_PRIMARY};
                border: none;
                border-radius: {default_theme.sizes.RADIUS_LARGE};
                padding: {default_theme.sizes.SPACING_SM} {default_theme.sizes.SPACING_LG};
                margin: {default_theme.sizes.SPACING_XS} 2px;
                font-size: {default_theme.sizes.FONT_MD};
                font-weight: {default_theme.fonts.WEIGHT_MEDIUM};
                min-width: 90px;
                min-height: 30px;
                max-height: 30px;
            }}
            QToolBar QPushButton:not([objectName="mode_button"]):not([objectName="refresh_button"]):not([objectName="help_button"]):not([objectName="category_mode_button"]):hover {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                           stop:0 #1E88E5, stop:1 #1976D2);
            }}
            QToolBar QPushButton:not([objectName="mode_button"]):not([objectName="refresh_button"]):not([objectName="help_button"]):not([objectName="category_mode_button"]):pressed {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                           stop:0 #1565C0, stop:1 #0D47A1);
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