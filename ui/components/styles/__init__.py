"""
样式管理系统

提供统一的样式管理接口，包括主题、按钮、对话框、组件等样式定义。
通过此模块可以方便地使用所有预定义的样式和快捷方法。

使用示例:
    from ui.components.styles import (
        default_theme, ButtonStyles, DialogStyles, WidgetStyles,
        apply_category_button_style, apply_dialog_style
    )

    # 使用主题颜色
    color = default_theme.colors.PRIMARY

    # 获取按钮样式
    button_style = ButtonStyles.get_primary_button_style("myButton")

    # 应用样式到组件
    apply_category_button_style(my_button)
    apply_dialog_style(my_dialog, "form")
"""

# 导入核心主题
from .theme import default_theme, Theme, Colors, Sizes, Fonts, Shadows, Animations

# 导入样式管理类
from .button_styles import ButtonStyles, ToolbarButtonStyles
from .dialog_styles import DialogStyles
from .widget_styles import WidgetStyles
from .toolbar_styles import ToolbarStyles
from .main_window_styles import MainWindowStyles

# 导入快捷方法
# from .button_styles import (
#     # 暂时没有快捷方法，预留位置
# )

from .dialog_styles import (
    apply_dialog_style,
    apply_tabbed_help_dialog_style
)

from .widget_styles import (
    apply_category_button_style,
    apply_enhanced_image_label_style,
    apply_info_panel_style,
    apply_progress_bar_style,
    apply_status_label_style,
    apply_list_widget_style,
    apply_scroll_area_style
)

# 定义公共接口
__all__ = [
    # 主题相关
    'default_theme',
    'Theme',
    'Colors',
    'Sizes',
    'Fonts',
    'Shadows',
    'Animations',

    # 样式管理类
    'ButtonStyles',
    'ToolbarButtonStyles',
    'DialogStyles',
    'WidgetStyles',
    'ToolbarStyles',
    'MainWindowStyles',

    # 快捷方法 - 对话框
    'apply_dialog_style',
    'apply_tabbed_help_dialog_style',

    # 快捷方法 - 组件
    'apply_category_button_style',
    'apply_enhanced_image_label_style',
    'apply_info_panel_style',
    'apply_progress_bar_style',
    'apply_status_label_style',
    'apply_list_widget_style',
    'apply_scroll_area_style',
]

# 版本信息
__version__ = '1.0.0'
__author__ = 'Image Classifier Team'
__description__ = 'Unified style management system for PyQt6 application'


def get_complete_app_style() -> str:
    """获取应用程序完整样式表"""
    return f"""
        /* 主应用窗口样式 */
        QMainWindow {{
            background-color: {default_theme.colors.BACKGROUND_PRIMARY};
            color: {default_theme.colors.TEXT_PRIMARY};
        }}

        /* 基础组件样式 */
        {ButtonStyles.get_base_button_style()}
        {DialogStyles.get_base_dialog_style()}
        {WidgetStyles.get_scroll_area_style()}
        {WidgetStyles.get_separator_style()}

        /* 工具提示样式 */
        QToolTip {{
            background-color: {default_theme.colors.BLACK};
            color: {default_theme.colors.TEXT_ON_DARK};
            border: {default_theme.sizes.BORDER_THIN} solid {default_theme.colors.BORDER_DARK};
            border-radius: {default_theme.sizes.RADIUS_SMALL};
            padding: {default_theme.sizes.SPACING_XS} {default_theme.sizes.SPACING_SM};
            font-size: {default_theme.sizes.FONT_SM};
        }}

        /* 状态栏样式 */
        QStatusBar {{
            background-color: {default_theme.colors.BACKGROUND_SECONDARY};
            color: {default_theme.colors.TEXT_SECONDARY};
            border-top: {default_theme.sizes.BORDER_THIN} solid {default_theme.colors.BORDER_LIGHT};
            font-size: {default_theme.sizes.FONT_SM};
        }}

        /* 菜单栏样式 */
        QMenuBar {{
            background-color: {default_theme.colors.BACKGROUND_PRIMARY};
            color: {default_theme.colors.TEXT_PRIMARY};
            border-bottom: {default_theme.sizes.BORDER_THIN} solid {default_theme.colors.BORDER_LIGHT};
            font-size: {default_theme.sizes.FONT_MD};
        }}
        QMenuBar::item {{
            background-color: transparent;
            padding: {default_theme.sizes.SPACING_SM} {default_theme.sizes.SPACING_MD};
        }}
        QMenuBar::item:selected {{
            background-color: {default_theme.colors.BACKGROUND_HOVER};
        }}

        /* 工具栏样式 */
        QToolBar {{
            background-color: {default_theme.colors.BACKGROUND_SECONDARY};
            border: none;
            spacing: {default_theme.sizes.SPACING_XS};
            padding: {default_theme.sizes.SPACING_XS};
        }}
        QToolBar::separator {{
            background-color: {default_theme.colors.BORDER_LIGHT};
            width: 1px;
            margin: 0 {default_theme.sizes.SPACING_XS};
        }}
    """


def apply_app_style(app_or_widget):
    """为应用程序或窗口应用完整样式"""
    app_or_widget.setStyleSheet(get_complete_app_style())