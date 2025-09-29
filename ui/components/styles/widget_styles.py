"""
通用组件样式管理模块

集中管理所有通用UI组件的样式定义，包括类别按钮、图像标签、
列表项、进度条等组件样式。
"""

from .theme import default_theme


class WidgetStyles:
    """通用组件样式管理类"""

    @staticmethod
    def get_category_button_style() -> str:
        """类别按钮样式 - 保持原始外观"""
        return """
            QPushButton {
                font-size: 13px;
                padding: 6px 8px;
                border: 1px solid #ddd;
                border-radius: 4px;
                background-color: #ffffff;
                text-align: left;
                margin: 1px 0;
                font-weight: 500;
                min-height: 20px;
            }
            QPushButton:hover {
                border-color: #aaa;
                background-color: #f0f0f0;
            }
            /* 键盘导航或鼠标选中状态 - 蓝色边框 */
            QPushButton:checked {
                border: 2px solid #2196F3;
                background-color: #E3F2FD;
                color: #1565C0;
                font-weight: bold;
            }
            /* 已分类状态 - 绿色背景（多分类模式下已选中的类别）*/
            QPushButton[classified="true"] {
                border: 1px solid #4CAF50;
                background-color: #E8F5E8;
                color: #2E7D32;
                font-weight: bold;
            }
            /* 已分类且当前选中状态 - 蓝色边框，绿色背景 */
            QPushButton[classified="true"]:checked {
                border: 2px solid #2196F3;
                background-color: #C8E6C9;
                color: #1B5E20;
                font-weight: bold;
            }
            /* 多分类状态 - 绿色背景（用于多分类模式下已分类的类别）*/
            QPushButton[multi_classified="true"] {
                border: 1px solid #4CAF50;
                background-color: #E8F5E8;
                color: #2E7D32;
                font-weight: bold;
            }
            /* 多分类且当前选中状态 - 蓝色边框，绿色背景 */
            QPushButton[multi_classified="true"]:checked {
                border: 2px solid #2196F3;
                background-color: #C8E6C9;
                color: #1B5E20;
                font-weight: bold;
            }
            /* 已移除状态 - 红色背景 */
            QPushButton[removed="true"] {
                border: 1px solid #F44336;
                background-color: #FFEBEE;
                color: #C62828;
                font-weight: bold;
            }
            /* 已移除且选中状态 */
            QPushButton[removed="true"]:checked {
                border: 2px solid #2196F3;
                background-color: #FFCDD2;
                color: #B71C1C;
                font-weight: bold;
            }
            QLabel {
                background: transparent;
                border: none;
                font-size: 13px;
                font-weight: inherit;
                color: inherit;
            }
        """

    @staticmethod
    def get_image_label_style() -> str:
        """图像标签样式"""
        return f"""
            QLabel {{
                border: {default_theme.sizes.BORDER_THIN} solid {default_theme.colors.BORDER_LIGHT};
                background-color: {default_theme.colors.BACKGROUND_SECONDARY};
                border-radius: {default_theme.sizes.RADIUS_SMALL};
            }}
        """

    @staticmethod
    def get_info_button_style() -> str:
        """信息按钮样式"""
        return f"""
            QPushButton {{
                background-color: {default_theme.get_rgba_color(default_theme.colors.BLACK, 0.7)};
                color: {default_theme.colors.TEXT_ON_DARK};
                border: none;
                border-radius: 15px;
                font-size: {default_theme.sizes.FONT_LG};
                font-weight: {default_theme.fonts.WEIGHT_BOLD};
            }}
            QPushButton:hover {{
                background-color: {default_theme.get_rgba_color(default_theme.colors.BLACK, 0.8)};
            }}
            QPushButton:pressed {{
                background-color: {default_theme.get_rgba_color(default_theme.colors.BLACK, 0.9)};
            }}
        """

    @staticmethod
    def get_info_panel_style() -> str:
        """信息面板样式"""
        return f"""
            QFrame {{
                background-color: {default_theme.get_rgba_color(default_theme.colors.BLACK, 0.8)};
                border-radius: {default_theme.sizes.RADIUS_MEDIUM};
                border: {default_theme.sizes.BORDER_THIN} solid {default_theme.get_rgba_color(default_theme.colors.WHITE, 0.2)};
            }}
            QLabel {{
                color: {default_theme.colors.TEXT_ON_DARK};
                background: transparent;
                font-size: {default_theme.sizes.FONT_SM};
                padding: 2px {default_theme.sizes.SPACING_SM};
            }}
            QLabel[objectName="info_title"] {{
                font-size: {default_theme.sizes.FONT_LG};
                font-weight: {default_theme.fonts.WEIGHT_BOLD};
                color: {default_theme.colors.SUCCESS};
                border-bottom: {default_theme.sizes.BORDER_THIN} solid {default_theme.get_rgba_color(default_theme.colors.WHITE, 0.3)};
                margin-bottom: 5px;
            }}
            QPushButton {{
                background-color: {default_theme.get_rgba_color(default_theme.colors.SUCCESS, 0.8)};
                color: {default_theme.colors.TEXT_ON_DARK};
                border: none;
                border-radius: {default_theme.sizes.RADIUS_SMALL};
                padding: {default_theme.sizes.SPACING_XS} {default_theme.sizes.SPACING_SM};
                font-size: {default_theme.sizes.FONT_XS};
                margin: 2px;
            }}
            QPushButton:hover {{
                background-color: {default_theme.get_rgba_color(default_theme.colors.SUCCESS, 0.9)};
            }}
        """

    @staticmethod
    def get_enhanced_progress_bar_style() -> str:
        """增强进度条样式"""
        return f"""
            QProgressBar {{
                background-color: {default_theme.colors.GRAY_200};
                border: {default_theme.sizes.BORDER_THIN} solid {default_theme.colors.BORDER_LIGHT};
                border-radius: {default_theme.sizes.RADIUS_SMALL};
                text-align: center;
                font-size: {default_theme.sizes.FONT_SM};
                font-weight: {default_theme.fonts.WEIGHT_MEDIUM};
                color: {default_theme.colors.TEXT_PRIMARY};
                min-height: 20px;
                max-height: 20px;
            }}
            QProgressBar::chunk {{
                background: {default_theme.create_gradient(default_theme.colors.PRIMARY, default_theme.colors.PRIMARY_DARK)};
                border-radius: {default_theme.sizes.RADIUS_SMALL};
                margin: 1px;
            }}
            QProgressBar[status="success"]::chunk {{
                background: {default_theme.create_gradient(default_theme.colors.SUCCESS, default_theme.colors.SUCCESS_DARK)};
            }}
            QProgressBar[status="warning"]::chunk {{
                background: {default_theme.create_gradient(default_theme.colors.WARNING, default_theme.colors.WARNING_DARK)};
            }}
            QProgressBar[status="error"]::chunk {{
                background: {default_theme.create_gradient(default_theme.colors.ERROR, default_theme.colors.ERROR_DARK)};
            }}
        """

    @staticmethod
    def get_scroll_area_style() -> str:
        """滚动区域样式"""
        return f"""
            QScrollArea {{
                background-color: {default_theme.colors.BACKGROUND_CARD};
                border: {default_theme.sizes.BORDER_THIN} solid {default_theme.colors.BORDER_LIGHT};
                border-radius: {default_theme.sizes.RADIUS_SMALL};
            }}
            QScrollBar:vertical {{
                background-color: {default_theme.colors.GRAY_100};
                width: 12px;
                border-radius: 6px;
                margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background-color: {default_theme.colors.GRAY_400};
                border-radius: 6px;
                min-height: 20px;
                margin: 2px;
            }}
            QScrollBar::handle:vertical:hover {{
                background-color: {default_theme.colors.GRAY_500};
            }}
            QScrollBar::handle:vertical:pressed {{
                background-color: {default_theme.colors.GRAY_600};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                border: none;
                background: none;
                height: 0px;
            }}
            QScrollBar:horizontal {{
                background-color: {default_theme.colors.GRAY_100};
                height: 12px;
                border-radius: 6px;
                margin: 0px;
            }}
            QScrollBar::handle:horizontal {{
                background-color: {default_theme.colors.GRAY_400};
                border-radius: 6px;
                min-width: 20px;
                margin: 2px;
            }}
            QScrollBar::handle:horizontal:hover {{
                background-color: {default_theme.colors.GRAY_500};
            }}
            QScrollBar::handle:horizontal:pressed {{
                background-color: {default_theme.colors.GRAY_600};
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                border: none;
                background: none;
                width: 0px;
            }}
        """

    @staticmethod
    def get_list_widget_style() -> str:
        """列表组件样式"""
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
                outline: none;
            }}
            QListWidget::item {{
                background-color: transparent;
                border: none;
                border-radius: {default_theme.sizes.RADIUS_SMALL};
                padding: {default_theme.sizes.SPACING_XS} {default_theme.sizes.SPACING_SM};
                margin: 1px;
                min-height: 24px;
            }}
            QListWidget::item:hover {{
                background-color: {default_theme.colors.BACKGROUND_HOVER};
            }}
            QListWidget::item:selected {{
                background-color: {default_theme.colors.PRIMARY_LIGHT};
                color: {default_theme.colors.TEXT_PRIMARY};
            }}
            QListWidget::item:selected:active {{
                background-color: {default_theme.colors.PRIMARY};
                color: {default_theme.colors.TEXT_ON_PRIMARY};
            }}
        """

    @staticmethod
    def get_status_label_style() -> str:
        """状态标签样式"""
        return f"""
            QLabel {{
                background-color: {default_theme.colors.GRAY_100};
                color: {default_theme.colors.TEXT_SECONDARY};
                border: {default_theme.sizes.BORDER_THIN} solid {default_theme.colors.BORDER_LIGHT};
                border-radius: {default_theme.sizes.RADIUS_SMALL};
                padding: {default_theme.sizes.SPACING_XS} {default_theme.sizes.SPACING_SM};
                font-size: {default_theme.sizes.FONT_SM};
                font-weight: {default_theme.fonts.WEIGHT_MEDIUM};
            }}
            QLabel[status="success"] {{
                background-color: {default_theme.colors.SUCCESS_LIGHT};
                color: {default_theme.colors.SUCCESS_DARK};
                border-color: {default_theme.colors.SUCCESS};
            }}
            QLabel[status="warning"] {{
                background-color: {default_theme.colors.WARNING_LIGHT};
                color: {default_theme.colors.WARNING_DARK};
                border-color: {default_theme.colors.WARNING};
            }}
            QLabel[status="error"] {{
                background-color: {default_theme.colors.ERROR_LIGHT};
                color: {default_theme.colors.ERROR_DARK};
                border-color: {default_theme.colors.ERROR};
            }}
            QLabel[status="info"] {{
                background-color: {default_theme.colors.PRIMARY_LIGHT};
                color: {default_theme.colors.PRIMARY_DARK};
                border-color: {default_theme.colors.PRIMARY};
            }}
        """

    @staticmethod
    def get_separator_style() -> str:
        """分隔线样式"""
        return f"""
            QFrame[frameShape="4"] {{  /* HLine */
                color: {default_theme.colors.BORDER_LIGHT};
                background-color: {default_theme.colors.BORDER_LIGHT};
                height: 1px;
                border: none;
                margin: {default_theme.sizes.SPACING_SM} 0;
            }}
            QFrame[frameShape="5"] {{  /* VLine */
                color: {default_theme.colors.BORDER_LIGHT};
                background-color: {default_theme.colors.BORDER_LIGHT};
                width: 1px;
                border: none;
                margin: 0 {default_theme.sizes.SPACING_SM};
            }}
        """

    @staticmethod
    def get_custom_rename_dialog_style() -> str:
        """自定义重命名对话框样式"""
        from .dialog_styles import DialogStyles
        from .button_styles import ButtonStyles
        return f"""
            {DialogStyles.get_base_dialog_style()}
            {DialogStyles.get_form_dialog_style()}
            {ButtonStyles.get_primary_button_style()}
            {ButtonStyles.get_secondary_button_style("cancelButton")}
        """

    @staticmethod
    def get_context_menu_style() -> str:
        """右键菜单样式"""
        return f"""
            QMenu {{
                background-color: {default_theme.colors.BACKGROUND_CARD};
                color: {default_theme.colors.TEXT_PRIMARY};
                border: {default_theme.sizes.BORDER_THIN} solid {default_theme.colors.BORDER_MEDIUM};
                border-radius: {default_theme.sizes.RADIUS_MEDIUM};
                padding: {default_theme.sizes.SPACING_XS};
            }}
            QMenu::item {{
                background-color: transparent;
                padding: {default_theme.sizes.SPACING_SM} {default_theme.sizes.SPACING_LG};
                border-radius: {default_theme.sizes.RADIUS_SMALL};
                margin: 1px;
            }}
            QMenu::item:selected {{
                background-color: {default_theme.colors.PRIMARY_LIGHT};
                color: {default_theme.colors.PRIMARY_DARK};
            }}
            QMenu::item:disabled {{
                color: {default_theme.colors.TEXT_DISABLED};
            }}
            QMenu::separator {{
                height: 1px;
                background-color: {default_theme.colors.BORDER_LIGHT};
                margin: {default_theme.sizes.SPACING_XS} {default_theme.sizes.SPACING_SM};
            }}
        """


# 组件样式快捷方法
def apply_category_button_style(button):
    """为类别按钮应用样式"""
    button.setStyleSheet(WidgetStyles.get_category_button_style())


def apply_enhanced_image_label_style(label):
    """为增强图像标签应用样式"""
    label.setStyleSheet(WidgetStyles.get_image_label_style())


def apply_info_panel_style(panel):
    """为信息面板应用样式"""
    panel.setStyleSheet(WidgetStyles.get_info_panel_style())


def apply_progress_bar_style(progress_bar, status="normal"):
    """为进度条应用样式"""
    if status != "normal":
        progress_bar.setProperty("status", status)
    progress_bar.setStyleSheet(WidgetStyles.get_enhanced_progress_bar_style())


def apply_status_label_style(label, status="normal"):
    """为状态标签应用样式"""
    if status != "normal":
        label.setProperty("status", status)
    label.setStyleSheet(WidgetStyles.get_status_label_style())


def apply_list_widget_style(list_widget):
    """为列表组件应用样式"""
    combined_style = f"""
        {WidgetStyles.get_list_widget_style()}
        {WidgetStyles.get_scroll_area_style()}
    """
    list_widget.setStyleSheet(combined_style)


def apply_scroll_area_style(scroll_area):
    """为滚动区域应用样式"""
    scroll_area.setStyleSheet(WidgetStyles.get_scroll_area_style())