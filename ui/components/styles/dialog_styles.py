"""
对话框样式管理模块

集中管理所有对话框相关的样式定义，包括基础对话框、标签页对话框、
进度对话框等样式。
"""

from .theme import default_theme


class DialogStyles:
    """对话框样式管理类"""

    @staticmethod
    def get_base_dialog_style() -> str:
        """基础对话框样式"""
        return f"""
            QDialog {{
                background-color: {default_theme.colors.BACKGROUND_SECONDARY};
                color: {default_theme.colors.TEXT_PRIMARY};
                border-radius: {default_theme.sizes.RADIUS_MEDIUM};
            }}
        """

    @staticmethod
    def get_tabbed_dialog_style() -> str:
        """带标签页的对话框样式"""
        return f"""
            QDialog {{
                background-color: {default_theme.colors.BACKGROUND_SECONDARY};
                color: {default_theme.colors.TEXT_PRIMARY};
            }}
            QTabWidget {{
                background-color: {default_theme.colors.BACKGROUND_CARD};
                border: {default_theme.sizes.BORDER_THIN} solid {default_theme.colors.BORDER_LIGHT};
                border-radius: {default_theme.sizes.RADIUS_MEDIUM};
            }}
            QTabWidget::pane {{
                background-color: {default_theme.colors.BACKGROUND_CARD};
                border: {default_theme.sizes.BORDER_THIN} solid {default_theme.colors.BORDER_LIGHT};
                border-radius: {default_theme.sizes.RADIUS_MEDIUM};
                top: -1px;
            }}
            QTabBar::tab {{
                background-color: {default_theme.colors.GRAY_100};
                color: {default_theme.colors.TEXT_PRIMARY};
                border: {default_theme.sizes.BORDER_THIN} solid {default_theme.colors.BORDER_LIGHT};
                padding: {default_theme.sizes.SPACING_SM} {default_theme.sizes.SPACING_LG};
                margin-right: 2px;
                border-top-left-radius: {default_theme.sizes.RADIUS_MEDIUM};
                border-top-right-radius: {default_theme.sizes.RADIUS_MEDIUM};
                font-weight: {default_theme.fonts.WEIGHT_BOLD};
                min-width: 80px;
            }}
            QTabBar::tab:selected {{
                background-color: {default_theme.colors.PRIMARY};
                color: {default_theme.colors.TEXT_ON_PRIMARY};
                border-bottom-color: {default_theme.colors.PRIMARY};
            }}
            QTabBar::tab:hover {{
                background-color: {default_theme.colors.BACKGROUND_HOVER};
            }}
            QTabBar::tab:selected:hover {{
                background-color: {default_theme.colors.PRIMARY_DARK};
            }}
        """

    @staticmethod
    def get_form_dialog_style() -> str:
        """表单对话框样式"""
        return f"""
            QDialog {{
                background-color: {default_theme.colors.BACKGROUND_CARD};
                color: {default_theme.colors.TEXT_PRIMARY};
                border-radius: {default_theme.sizes.RADIUS_MEDIUM};
            }}
            QLabel {{
                color: {default_theme.colors.TEXT_PRIMARY};
                font-size: {default_theme.sizes.FONT_MD};
            }}
            QLabel[type="tip"] {{
                color: {default_theme.colors.TEXT_SECONDARY};
                font-size: {default_theme.sizes.FONT_SM};
                font-style: italic;
            }}
            QLineEdit {{
                background-color: {default_theme.colors.BACKGROUND_CARD};
                color: {default_theme.colors.TEXT_PRIMARY};
                border: {default_theme.sizes.BORDER_THIN} solid {default_theme.colors.BORDER_LIGHT};
                border-radius: {default_theme.sizes.RADIUS_SMALL};
                padding: {default_theme.sizes.SPACING_SM} {default_theme.sizes.SPACING_MD};
                font-size: {default_theme.sizes.FONT_MD};
                min-height: {default_theme.sizes.BUTTON_HEIGHT_SM};
            }}
            QLineEdit:focus {{
                border-color: {default_theme.colors.PRIMARY};
                background-color: {default_theme.colors.BACKGROUND_CARD};
            }}
            QLineEdit:read-only {{
                background-color: {default_theme.colors.GRAY_100};
                color: {default_theme.colors.TEXT_SECONDARY};
            }}
            QTextEdit {{
                background-color: {default_theme.colors.BACKGROUND_CARD};
                color: {default_theme.colors.TEXT_PRIMARY};
                border: {default_theme.sizes.BORDER_THIN} solid {default_theme.colors.BORDER_LIGHT};
                border-radius: {default_theme.sizes.RADIUS_SMALL};
                padding: {default_theme.sizes.SPACING_SM};
                font-size: {default_theme.sizes.FONT_MD};
                selection-background-color: {default_theme.colors.HIGHLIGHT};
            }}
            QTextEdit:focus {{
                border-color: {default_theme.colors.PRIMARY};
            }}
        """

    @staticmethod
    def get_list_dialog_style() -> str:
        """列表对话框样式"""
        return f"""
            QListWidget {{
                background-color: {default_theme.colors.BACKGROUND_CARD};
                color: {default_theme.colors.TEXT_PRIMARY};
                border: {default_theme.sizes.BORDER_THIN} solid {default_theme.colors.BORDER_LIGHT};
                border-radius: {default_theme.sizes.RADIUS_SMALL};
                padding: {default_theme.sizes.SPACING_XS};
                font-size: {default_theme.sizes.FONT_MD};
                selection-background-color: {default_theme.colors.PRIMARY_LIGHT};
                selection-color: {default_theme.colors.TEXT_PRIMARY};
            }}
            QListWidget::item {{
                background-color: transparent;
                border: none;
                border-radius: {default_theme.sizes.RADIUS_SMALL};
                padding: {default_theme.sizes.SPACING_XS} {default_theme.sizes.SPACING_SM};
                margin: 1px;
            }}
            QListWidget::item:hover {{
                background-color: {default_theme.colors.BACKGROUND_HOVER};
            }}
            QListWidget::item:selected {{
                background-color: {default_theme.colors.PRIMARY_LIGHT};
                color: {default_theme.colors.TEXT_PRIMARY};
            }}
        """

    @staticmethod
    def get_progress_dialog_style() -> str:
        """进度对话框样式"""
        return f"""
            QDialog {{
                background-color: {default_theme.colors.BACKGROUND_CARD};
                color: {default_theme.colors.TEXT_PRIMARY};
                border-radius: {default_theme.sizes.RADIUS_MEDIUM};
                border: {default_theme.sizes.BORDER_MEDIUM} solid {default_theme.colors.BORDER_MEDIUM};
            }}
            QProgressBar {{
                background-color: {default_theme.colors.GRAY_200};
                border: {default_theme.sizes.BORDER_THIN} solid {default_theme.colors.BORDER_LIGHT};
                border-radius: {default_theme.sizes.RADIUS_SMALL};
                text-align: center;
                font-size: {default_theme.sizes.FONT_SM};
                font-weight: {default_theme.fonts.WEIGHT_MEDIUM};
                color: {default_theme.colors.TEXT_PRIMARY};
                min-height: {default_theme.sizes.BUTTON_HEIGHT_SM};
            }}
            QProgressBar::chunk {{
                background-color: {default_theme.colors.PRIMARY};
                border-radius: {default_theme.sizes.RADIUS_SMALL};
                margin: 1px;
            }}
            QProgressBar[indeterminate="true"] {{
                background-color: {default_theme.colors.GRAY_200};
            }}
            QProgressBar[indeterminate="true"]::chunk {{
                background-color: {default_theme.colors.PRIMARY};
                width: 30px;
                margin: 1px;
            }}
        """

    @staticmethod
    def get_switch_checkbox_style() -> str:
        """开关样式复选框"""
        return f"""
            QCheckBox {{
                spacing: {default_theme.sizes.SPACING_SM};
                font-size: {default_theme.sizes.FONT_MD};
                color: {default_theme.colors.TEXT_PRIMARY};
            }}
            QCheckBox::indicator {{
                width: 44px;
                height: 24px;
                border-radius: 12px;
                border: {default_theme.sizes.BORDER_THIN} solid {default_theme.colors.BORDER_MEDIUM};
            }}
            QCheckBox::indicator:unchecked {{
                background-color: {default_theme.colors.GRAY_300};
            }}
            QCheckBox::indicator:checked {{
                background-color: {default_theme.colors.SUCCESS};
            }}
            QCheckBox::indicator:hover {{
                border-color: {default_theme.colors.PRIMARY};
            }}
            QCheckBox::indicator:unchecked:hover {{
                background-color: {default_theme.colors.GRAY_400};
            }}
            QCheckBox::indicator:checked:hover {{
                background-color: {default_theme.colors.SUCCESS_DARK};
            }}
        """

    @staticmethod
    def get_text_browser_style() -> str:
        """文本浏览器样式"""
        return f"""
            QTextBrowser {{
                background-color: {default_theme.colors.BACKGROUND_CARD};
                color: {default_theme.colors.TEXT_PRIMARY};
                border: {default_theme.sizes.BORDER_THIN} solid {default_theme.colors.BORDER_LIGHT};
                border-radius: {default_theme.sizes.RADIUS_SMALL};
                padding: {default_theme.sizes.SPACING_MD};
                font-size: {default_theme.sizes.FONT_MD};
                font-family: {default_theme.fonts.FAMILY_DEFAULT};
                line-height: {default_theme.fonts.LINE_HEIGHT_NORMAL};
                selection-background-color: {default_theme.colors.HIGHLIGHT};
            }}
            QTextBrowser a {{
                color: {default_theme.colors.PRIMARY};
                text-decoration: none;
            }}
            QTextBrowser a:hover {{
                color: {default_theme.colors.PRIMARY_DARK};
                text-decoration: underline;
            }}
        """

    @staticmethod
    def get_complete_dialog_style() -> str:
        """完整对话框样式 - 包含所有常用控件"""
        from .button_styles import ButtonStyles
        return f"""
            {DialogStyles.get_base_dialog_style()}
            {DialogStyles.get_form_dialog_style()}
            {DialogStyles.get_list_dialog_style()}
            {DialogStyles.get_text_browser_style()}
            {ButtonStyles.get_primary_button_style()}
            {ButtonStyles.get_secondary_button_style()}
        """

    @staticmethod
    def get_dialog_style_by_type(dialog_type: str) -> str:
        """根据对话框类型获取样式"""
        styles_map = {
            "base": DialogStyles.get_base_dialog_style,
            "tabbed": DialogStyles.get_tabbed_dialog_style,
            "form": DialogStyles.get_form_dialog_style,
            "list": DialogStyles.get_list_dialog_style,
            "progress": DialogStyles.get_progress_dialog_style,
            "complete": DialogStyles.get_complete_dialog_style,
        }

        style_func = styles_map.get(dialog_type, DialogStyles.get_base_dialog_style)
        return style_func()


# 对话框样式快捷方法
def apply_dialog_style(dialog, style_type: str = "complete"):
    """为对话框应用指定样式"""
    style = DialogStyles.get_dialog_style_by_type(style_type)
    dialog.setStyleSheet(style)


def apply_tabbed_help_dialog_style(dialog):
    """应用带标签页帮助对话框的完整样式"""
    from .button_styles import ButtonStyles
    style = f"""
        {DialogStyles.get_tabbed_dialog_style()}
        {ButtonStyles.get_primary_button_style()}
        {ButtonStyles.get_danger_button_style("clearCacheBtn")}
        {DialogStyles.get_switch_checkbox_style()}
    """
    dialog.setStyleSheet(style)