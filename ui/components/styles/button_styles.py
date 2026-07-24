"""
按钮样式管理模块

集中管理所有按钮相关的样式定义，提供统一的按钮外观和交互效果。
包括工具栏按钮、普通按钮、特殊功能按钮等样式。
"""

from .theme import default_theme


class ButtonStyles:
    """按钮样式管理类"""

    @staticmethod
    def get_base_button_style() -> str:
        """基础按钮样式"""
        return f"""
            QPushButton {{
                background-color: {default_theme.colors.BACKGROUND_CARD};
                color: {default_theme.colors.TEXT_PRIMARY};
                border: {default_theme.sizes.BORDER_THIN} solid {default_theme.colors.BORDER_MEDIUM};
                padding: 7px {default_theme.sizes.SPACING_LG};
                border-radius: {default_theme.sizes.RADIUS_MEDIUM};
                font-size: {default_theme.sizes.FONT_MD};
                font-weight: {default_theme.fonts.WEIGHT_MEDIUM};
                text-align: center;
                min-height: 20px;
            }}
            QPushButton:hover {{
                background-color: {default_theme.colors.BACKGROUND_HOVER};
                border-color: {default_theme.colors.BORDER_DARK};
            }}
            QPushButton:pressed {{
                background-color: {default_theme.colors.BACKGROUND_PRESSED};
            }}
            QPushButton:disabled {{
                background-color: {default_theme.colors.GRAY_100};
                color: {default_theme.colors.TEXT_DISABLED};
                border-color: {default_theme.colors.BORDER_LIGHT};
            }}
        """

    @staticmethod
    def get_primary_button_style(object_name: str = None) -> str:
        """主要按钮样式（蓝色）"""
        selector = f"QPushButton#{object_name}" if object_name else "QPushButton"
        return f"""
            {selector} {{
                background-color: {default_theme.colors.PRIMARY};
                color: {default_theme.colors.TEXT_ON_PRIMARY};
                border: none;
                border-radius: {default_theme.sizes.RADIUS_MEDIUM};
                padding: 7px {default_theme.sizes.SPACING_LG};
                font-size: {default_theme.sizes.FONT_MD};
                font-weight: {default_theme.fonts.WEIGHT_MEDIUM};
                min-height: 20px;
            }}
            {selector}:hover {{
                background-color: {default_theme.colors.PRIMARY_DARK};
            }}
            {selector}:pressed {{
                background-color: {default_theme.colors.PRIMARY_DARK};
            }}
            {selector}:disabled {{
                background-color: {default_theme.colors.GRAY_300};
                color: {default_theme.colors.TEXT_DISABLED};
            }}
        """

    @staticmethod
    def get_secondary_button_style(object_name: str = None) -> str:
        """次要按钮样式（灰色）"""
        selector = f"QPushButton#{object_name}" if object_name else "QPushButton"
        return f"""
            {selector} {{
                background-color: {default_theme.colors.GRAY_100};
                color: {default_theme.colors.TEXT_PRIMARY};
                border: {default_theme.sizes.BORDER_THIN} solid {default_theme.colors.BORDER_LIGHT};
                border-radius: {default_theme.sizes.RADIUS_MEDIUM};
                padding: 7px {default_theme.sizes.SPACING_LG};
                font-size: {default_theme.sizes.FONT_MD};
                font-weight: {default_theme.fonts.WEIGHT_MEDIUM};
                min-height: 20px;
            }}
            {selector}:hover {{
                background-color: {default_theme.colors.BACKGROUND_HOVER};
                border-color: {default_theme.colors.BORDER_MEDIUM};
            }}
            {selector}:pressed {{
                background-color: {default_theme.colors.BACKGROUND_PRESSED};
            }}
            {selector}:disabled {{
                background-color: {default_theme.colors.GRAY_100};
                color: {default_theme.colors.TEXT_DISABLED};
                border-color: {default_theme.colors.BORDER_LIGHT};
            }}
        """

    @staticmethod
    def get_success_button_style(object_name: str = None) -> str:
        """成功按钮样式（绿色）"""
        selector = f"QPushButton#{object_name}" if object_name else "QPushButton"
        return f"""
            {selector} {{
                background-color: {default_theme.colors.SUCCESS};
                color: {default_theme.colors.TEXT_ON_PRIMARY};
                border: none;
                border-radius: {default_theme.sizes.RADIUS_MEDIUM};
                padding: 7px {default_theme.sizes.SPACING_LG};
                font-size: {default_theme.sizes.FONT_MD};
                font-weight: {default_theme.fonts.WEIGHT_MEDIUM};
                min-height: 20px;
            }}
            {selector}:hover {{
                background-color: {default_theme.colors.SUCCESS_DARK};
            }}
            {selector}:pressed {{
                background-color: {default_theme.colors.SUCCESS_LIGHT};
            }}
        """

    @staticmethod
    def get_danger_button_style(object_name: str = None) -> str:
        """危险按钮样式（红色）"""
        selector = f"QPushButton#{object_name}" if object_name else "QPushButton"
        return f"""
            {selector} {{
                background-color: {default_theme.colors.ERROR};
                color: {default_theme.colors.TEXT_ON_PRIMARY};
                border: none;
                border-radius: {default_theme.sizes.RADIUS_MEDIUM};
                padding: 7px {default_theme.sizes.SPACING_LG};
                font-size: {default_theme.sizes.FONT_MD};
                font-weight: {default_theme.fonts.WEIGHT_MEDIUM};
                min-height: 20px;
            }}
            {selector}:hover {{
                background-color: {default_theme.colors.ERROR_DARK};
            }}
            {selector}:pressed {{
                background-color: {default_theme.colors.ERROR_LIGHT};
            }}
        """

    @staticmethod
    def get_dialog_button_style() -> str:
        """对话框按钮体系：默认次要按钮，按 uiRole 切换语义颜色。"""
        c = default_theme.colors
        s = default_theme.sizes
        return f"""
            QPushButton {{
                background-color: {c.BACKGROUND_CARD};
                color: {c.TEXT_PRIMARY};
                border: 1px solid {c.BORDER_MEDIUM};
                border-radius: {s.RADIUS_MEDIUM};
                padding: 0 16px;
                font-size: {s.FONT_MD};
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: {c.BACKGROUND_HOVER};
                border-color: {c.BORDER_DARK};
            }}
            QPushButton:pressed {{ background-color: {c.BACKGROUND_PRESSED}; }}
            QPushButton:checked {{
                background-color: {c.PRIMARY_LIGHT};
                color: {c.TEXT_PRIMARY};
                border-color: {c.PRIMARY};
            }}
            QPushButton:disabled {{
                background-color: {c.GRAY_100};
                color: {c.TEXT_DISABLED};
                border-color: {c.BORDER_LIGHT};
            }}
            QPushButton[uiRole="primary"] {{
                background-color: {c.PRIMARY};
                color: {c.TEXT_ON_PRIMARY};
                border-color: {c.PRIMARY};
            }}
            QPushButton[uiRole="primary"]:hover {{
                background-color: {c.PRIMARY_DARK};
                border-color: {c.PRIMARY_DARK};
            }}
            QPushButton[uiRole="primary"]:pressed {{
                background-color: {c.PRIMARY_DARK};
                border-color: {c.PRIMARY_DARK};
            }}
            QPushButton[uiRole="danger"] {{
                background-color: {c.ERROR};
                color: {c.TEXT_ON_PRIMARY};
                border-color: {c.ERROR};
            }}
            QPushButton[uiRole="danger"]:hover {{
                background-color: {c.ERROR_DARK};
                border-color: {c.ERROR_DARK};
            }}
            QPushButton[uiRole="danger"]:pressed {{
                background-color: {c.ERROR_DARK};
                border-color: {c.ERROR_DARK};
            }}
            QPushButton[uiRole="success"] {{
                background-color: {c.SUCCESS};
                color: {c.TEXT_ON_PRIMARY};
                border-color: {c.SUCCESS};
            }}
            QPushButton[uiRole="success"]:hover {{
                background-color: {c.SUCCESS_DARK};
                border-color: {c.SUCCESS_DARK};
            }}
            QPushButton[uiRole="success"]:pressed {{
                background-color: {c.SUCCESS_DARK};
                border-color: {c.SUCCESS_DARK};
            }}
            QPushButton[uiRole="ghost"] {{
                background-color: transparent;
                border-color: transparent;
                color: {c.TEXT_SECONDARY};
            }}
            QPushButton[uiRole="ghost"]:hover {{
                background-color: {c.BACKGROUND_HOVER};
                color: {c.TEXT_PRIMARY};
            }}
            QPushButton[uiKind="icon"] {{
                padding: 0;
            }}
        """

    @staticmethod
    def get_square_button_style(object_name: str, size: str = "medium") -> str:
        """正方形图标按钮样式（工具栏用）- 支持主题切换"""
        return f"""
            QPushButton#{object_name} {{
                background-color: {default_theme.colors.BACKGROUND_CARD};
                color: {default_theme.colors.TEXT_SECONDARY};
                border: none;
                border-radius: 6px;
                font-size: 16px;
                font-weight: normal;
                text-align: center;
            }}
            QPushButton#{object_name}:hover {{
                background-color: {default_theme.colors.BACKGROUND_HOVER};
            }}
            QPushButton#{object_name}:pressed {{
                background-color: {default_theme.colors.BACKGROUND_PRESSED};
            }}
            QPushButton#{object_name}:disabled {{
                background-color: {default_theme.colors.GRAY_200};
                color: {default_theme.colors.TEXT_DISABLED};
            }}
        """

    @staticmethod
    def get_category_button_style() -> str:
        """类别按钮样式"""
        return f"""
            QPushButton {{
                background-color: {default_theme.colors.BACKGROUND_CARD};
                color: {default_theme.colors.TEXT_PRIMARY};
                border: {default_theme.sizes.BORDER_THIN} solid {default_theme.colors.BORDER_LIGHT};
                border-radius: {default_theme.sizes.RADIUS_SMALL};
                padding: {default_theme.sizes.SPACING_SM} {default_theme.sizes.SPACING_MD};
                font-size: {default_theme.sizes.FONT_MD};
                font-weight: {default_theme.fonts.WEIGHT_MEDIUM};
                text-align: left;
                min-height: 30px;
                max-width: 250px;
            }}
            QPushButton:hover {{
                background-color: {default_theme.colors.BACKGROUND_HOVER};
                border-color: {default_theme.colors.BORDER_MEDIUM};
            }}
            QPushButton:pressed {{
                background-color: {default_theme.colors.BACKGROUND_PRESSED};
            }}
            QPushButton:checked {{
                background-color: {default_theme.colors.PRIMARY_LIGHT};
                border-color: {default_theme.colors.PRIMARY};
                color: {default_theme.colors.PRIMARY_DARK};
            }}
            QPushButton[classified="true"] {{
                background-color: {default_theme.colors.SUCCESS_LIGHT};
                border-color: {default_theme.colors.SUCCESS};
            }}
            QPushButton[multi_classified="true"] {{
                background-color: {default_theme.colors.WARNING_LIGHT};
                border-color: {default_theme.colors.WARNING};
            }}
        """

    @staticmethod
    def get_icon_button_style(size: str = "medium") -> str:
        """纯图标按钮样式（无边框）"""
        size_map = {
            "small": (default_theme.sizes.BUTTON_HEIGHT_SM, default_theme.sizes.FONT_SM),
            "medium": (default_theme.sizes.BUTTON_HEIGHT_MD, default_theme.sizes.FONT_LG),
            "large": (default_theme.sizes.BUTTON_HEIGHT_LG, default_theme.sizes.FONT_XL)
        }

        button_size, font_size = size_map.get(size, size_map["medium"])

        return f"""
            QPushButton {{
                background-color: transparent;
                color: {default_theme.colors.TEXT_SECONDARY};
                border: none;
                border-radius: {default_theme.sizes.RADIUS_SMALL};
                font-size: {font_size};
                width: {button_size};
                height: {button_size};
                min-width: {button_size};
                min-height: {button_size};
                max-width: {button_size};
                max-height: {button_size};
            }}
            QPushButton:hover {{
                background-color: {default_theme.colors.BACKGROUND_HOVER};
                color: {default_theme.colors.TEXT_PRIMARY};
            }}
            QPushButton:pressed {{
                background-color: {default_theme.colors.BACKGROUND_PRESSED};
            }}
        """

    @staticmethod
    def get_text_button_style() -> str:
        """文本按钮样式（无背景）"""
        return f"""
            QPushButton {{
                background-color: transparent;
                color: {default_theme.colors.PRIMARY};
                border: none;
                padding: {default_theme.sizes.SPACING_SM} {default_theme.sizes.SPACING_MD};
                font-size: {default_theme.sizes.FONT_MD};
                font-weight: {default_theme.fonts.WEIGHT_MEDIUM};
                text-decoration: none;
            }}
            QPushButton:hover {{
                color: {default_theme.colors.PRIMARY_DARK};
                text-decoration: underline;
            }}
            QPushButton:pressed {{
                color: {default_theme.colors.PRIMARY_DARK};
            }}
            QPushButton:disabled {{
                color: {default_theme.colors.TEXT_DISABLED};
            }}
        """


# 向后兼容的工具栏按钮样式类
class ToolbarButtonStyles:
    """工具栏按钮样式类（向后兼容）"""

    # 现代正方形圆角按钮样式模板
    MODERN_SQUARE_STYLE = ButtonStyles.get_square_button_style("{object_name}")

    @staticmethod
    def get_square_button_style(object_name: str) -> str:
        """获取正方形圆角按钮样式（向后兼容）"""
        return ButtonStyles.get_square_button_style(object_name)
