"""统一的主题弹窗、按钮角色和布局尺寸工具。"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QLayout,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QWidget,
)

from .styles import ButtonStyles, DialogStyles, default_theme


BUTTON_VARIANTS = {"primary", "secondary", "danger", "success", "ghost"}
BUTTON_SIZES = {
    "compact": default_theme.sizes.BUTTON_HEIGHT_COMPACT_PX,
    "standard": default_theme.sizes.BUTTON_HEIGHT_STANDARD_PX,
    "large": default_theme.sizes.BUTTON_HEIGHT_LARGE_PX,
}


def repolish(widget: QWidget) -> None:
    """动态属性变化后立即刷新 Qt 样式。"""
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


def style_button(
    button: QPushButton,
    variant: str = "secondary",
    size: str = "standard",
    *,
    min_width: Optional[int] = None,
) -> QPushButton:
    """应用统一按钮角色、尺寸、光标和交互样式。"""
    if variant not in BUTTON_VARIANTS:
        raise ValueError(f"未知按钮样式: {variant}")
    if size not in BUTTON_SIZES:
        raise ValueError(f"未知按钮尺寸: {size}")
    button.setProperty("uiRole", variant)
    button.setProperty("uiSize", size)
    button.setProperty("uiKind", "action")
    button.setFixedHeight(BUTTON_SIZES[size])
    button.setMinimumWidth(
        min_width
        if min_width is not None
        else default_theme.sizes.BUTTON_MIN_WIDTH_PX
    )
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setStyleSheet(ButtonStyles.get_dialog_button_style())
    repolish(button)
    return button


def style_icon_button(
    button: QPushButton,
    variant: str = "ghost",
    size: str = "compact",
) -> QPushButton:
    """应用统一的方形图标按钮样式，供标题栏和工具栏使用。"""
    style_button(
        button,
        variant,
        size,
        min_width=BUTTON_SIZES[size],
    )
    dimension = BUTTON_SIZES[size]
    button.setProperty("uiKind", "icon")
    button.setFixedSize(dimension, dimension)
    repolish(button)
    return button


def create_button(
    text: str,
    variant: str = "secondary",
    size: str = "standard",
    parent: Optional[QWidget] = None,
    *,
    min_width: Optional[int] = None,
) -> QPushButton:
    """创建符合统一规范的普通按钮。"""
    return style_button(
        QPushButton(text, parent),
        variant,
        size,
        min_width=min_width,
    )


def configure_dialog(
    dialog: QDialog,
    layout: Optional[QLayout] = None,
    *,
    style_type: str = "complete",
    compact: bool = False,
) -> None:
    """应用统一弹窗外观，以及 24/16 或 20/12 的边距节奏。"""
    dialog.setStyleSheet(DialogStyles.get_dialog_style_by_type(style_type))
    if layout is not None:
        margin = 20 if compact else default_theme.sizes.DIALOG_MARGIN_PX
        spacing = 12 if compact else default_theme.sizes.DIALOG_SPACING_PX
        layout.setContentsMargins(margin, margin, margin, margin)
        layout.setSpacing(spacing)


class ThemedMessageBox(QMessageBox):
    """统一颜色、按钮角色、尺寸和中文标准按钮的消息框。"""

    _BUTTON_TEXT = {
        QMessageBox.StandardButton.Ok: "确定",
        QMessageBox.StandardButton.Cancel: "取消",
        QMessageBox.StandardButton.Yes: "是",
        QMessageBox.StandardButton.No: "否",
        QMessageBox.StandardButton.Apply: "应用",
        QMessageBox.StandardButton.Close: "关闭",
        QMessageBox.StandardButton.Retry: "重试",
        QMessageBox.StandardButton.Discard: "放弃",
        QMessageBox.StandardButton.Save: "保存",
    }

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setStyleSheet(DialogStyles.get_message_box_style())

    def _style_buttons(self) -> None:
        for button in self.buttons():
            role = self.buttonRole(button)
            if role == QMessageBox.ButtonRole.DestructiveRole:
                variant = "danger"
            elif role in {
                QMessageBox.ButtonRole.AcceptRole,
                QMessageBox.ButtonRole.YesRole,
                QMessageBox.ButtonRole.ApplyRole,
            }:
                variant = "primary"
            else:
                variant = "secondary"
            if isinstance(button, QPushButton):
                style_button(button, variant)

        for standard, text in self._BUTTON_TEXT.items():
            button = self.button(standard)
            if button is not None:
                button.setText(text)

    def showEvent(self, event) -> None:
        self.setStyleSheet(DialogStyles.get_message_box_style())
        self._style_buttons()
        super().showEvent(event)


class ThemedProgressDialog(QProgressDialog):
    """遵循统一尺寸和主题样式的 Qt 标准进度框。"""

    def __init__(
        self,
        label_text: str,
        cancel_text: str,
        minimum: int,
        maximum: int,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(label_text, cancel_text, minimum, maximum, parent)
        self.setMinimumWidth(440)
        self.setStyleSheet(
            f"""
            {DialogStyles.get_complete_dialog_style()}
            {DialogStyles.get_progress_dialog_style()}
            """
        )
        cancel_button = self.findChild(QPushButton)
        if cancel_button is not None:
            style_button(cancel_button, "secondary")


def create_message_box(
    parent: Optional[QWidget],
    icon: QMessageBox.Icon,
    title: str,
    text: str,
    *,
    informative_text: str = "",
) -> ThemedMessageBox:
    """创建统一消息框；调用方继续负责添加业务按钮和执行。"""
    box = ThemedMessageBox(parent)
    box.setIcon(icon)
    box.setWindowTitle(title)
    box.setText(text)
    if informative_text:
        box.setInformativeText(informative_text)
    return box
