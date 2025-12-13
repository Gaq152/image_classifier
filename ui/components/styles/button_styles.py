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
                border: none;
                padding: {default_theme.sizes.SPACING_SM} {default_theme.sizes.SPACING_LG};
                border-radius: {default_theme.sizes.RADIUS_MEDIUM};
                font-size: {default_theme.sizes.FONT_MD};
                font-weight: {default_theme.fonts.WEIGHT_MEDIUM};
                text-align: center;
                min-height: {default_theme.sizes.BUTTON_HEIGHT_MD};
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
                padding: {default_theme.sizes.SPACING_SM} {default_theme.sizes.SPACING_LG};
                font-size: {default_theme.sizes.FONT_MD};
                font-weight: {default_theme.fonts.WEIGHT_MEDIUM};
                min-height: {default_theme.sizes.BUTTON_HEIGHT_MD};
            }}
            {selector}:hover {{
                background-color: {default_theme.colors.PRIMARY_DARK};
            }}
            {selector}:pressed {{
                background-color: {default_theme.colors.PRIMARY_LIGHT};
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
                padding: {default_theme.sizes.SPACING_SM} {default_theme.sizes.SPACING_LG};
                font-size: {default_theme.sizes.FONT_MD};
                font-weight: {default_theme.fonts.WEIGHT_MEDIUM};
                min-height: {default_theme.sizes.BUTTON_HEIGHT_MD};
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
                padding: {default_theme.sizes.SPACING_SM} {default_theme.sizes.SPACING_LG};
                font-size: {default_theme.sizes.FONT_MD};
                font-weight: {default_theme.fonts.WEIGHT_MEDIUM};
                min-height: {default_theme.sizes.BUTTON_HEIGHT_MD};
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
                padding: {default_theme.sizes.SPACING_SM} {default_theme.sizes.SPACING_LG};
                font-size: {default_theme.sizes.FONT_MD};
                font-weight: {default_theme.fonts.WEIGHT_MEDIUM};
                min-height: {default_theme.sizes.BUTTON_HEIGHT_MD};
            }}
            {selector}:hover {{
                background-color: {default_theme.colors.ERROR_DARK};
            }}
            {selector}:pressed {{
                background-color: {default_theme.colors.ERROR_LIGHT};
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
                border-radius: 8px;
                font-size: 18px;
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
                color: {default_theme.colors.PRIMARY_LIGHT};
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