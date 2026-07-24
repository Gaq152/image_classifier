"""统一 UI 设计系统的尺寸、角色和弹窗入口测试。"""

import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from PyQt6.QtWidgets import (
    QDialog,
    QLineEdit,
    QVBoxLayout,
    QMessageBox,
    QPushButton,
)

from ui.components.dialog_utils import (
    ThemedMessageBox,
    configure_dialog,
    style_button,
    style_icon_button,
)
from ui.components.styles import ToolbarStyles, default_theme


@pytest.mark.parametrize(
    ("size", "expected_height"),
    [
        ("compact", 32),
        ("standard", 36),
        ("large", 40),
    ],
)
def test_button_sizes_are_deterministic(qapp, size, expected_height):
    """所有普通页面按钮只能使用统一的三档高度。"""
    button = QPushButton("测试")
    style_button(button, "primary", size)

    assert button.height() == expected_height
    assert button.minimumWidth() == default_theme.sizes.BUTTON_MIN_WIDTH_PX
    assert button.property("uiRole") == "primary"
    assert button.property("uiSize") == size


@pytest.mark.parametrize(
    "variant",
    ["primary", "secondary", "danger", "success", "ghost"],
)
def test_button_semantic_variants_share_one_style_system(qapp, variant):
    button = QPushButton("测试")
    style_button(button, variant)

    assert button.property("uiRole") == variant
    assert "QPushButton[uiRole=" in button.styleSheet()
    assert button.height() == 36


def test_icon_button_uses_compact_square_variant(qapp):
    button = QPushButton("+")

    style_icon_button(button)

    assert (button.width(), button.height()) == (32, 32)
    assert button.minimumWidth() == 32
    assert button.property("uiKind") == "icon"
    assert button.property("uiRole") == "ghost"


def test_main_toolbar_uses_theme_tokens_without_legacy_gradient():
    style = ToolbarStyles.get_main_toolbar_style()

    assert default_theme.colors.PRIMARY in style
    assert default_theme.colors.BORDER_LIGHT in style
    # Qt 的 QSS 高度不包含 1px 上下边框，30px 内容盒最终为 32px。
    assert "min-height: 30px" in style
    assert "qlineargradient" not in style


def test_dialog_layout_uses_shared_spacing(qapp):
    dialog = QDialog()
    layout = QVBoxLayout(dialog)

    configure_dialog(dialog, layout)

    margins = layout.contentsMargins()
    assert (margins.left(), margins.top(), margins.right(), margins.bottom()) == (
        24,
        24,
        24,
        24,
    )
    assert layout.spacing() == 16
    assert default_theme.colors.BACKGROUND_PRIMARY in dialog.styleSheet()


def test_themed_message_box_assigns_button_roles(qtbot):
    box = ThemedMessageBox()
    qtbot.addWidget(box)
    confirm = box.addButton("继续", QMessageBox.ButtonRole.AcceptRole)
    cancel = box.addButton("删除", QMessageBox.ButtonRole.DestructiveRole)

    box.show()
    qtbot.waitUntil(lambda: box.isVisible(), timeout=1000)

    assert confirm.property("uiRole") == "primary"
    assert cancel.property("uiRole") == "danger"
    assert confirm.height() == 36
    assert cancel.height() == 36
    box.close()


def test_panel_header_buttons_share_compact_size(qtbot):
    from ui._main_window.panels.category_panel import CategoryPanel
    from ui._main_window.panels.image_view_panel import ImageViewPanel

    category_panel = CategoryPanel(SimpleNamespace(sort_ascending=True))
    image_panel = ImageViewPanel()
    qtbot.addWidget(category_panel)
    qtbot.addWidget(image_panel)

    buttons = [
        category_panel.sort_direction_button,
        category_panel.sort_button,
        category_panel.add_button,
        image_panel.delete_button,
    ]
    assert all((button.width(), button.height()) == (32, 32) for button in buttons)
    assert all(button.property("uiKind") == "icon" for button in buttons)
    assert image_panel.delete_button.property("uiRole") == "danger"


def test_settings_only_styles_business_buttons(qtbot):
    from ui.dialogs.settings.settings_dialog import SettingsDialog

    dialog = SettingsDialog()
    qtbot.addWidget(dialog)

    for button in dialog.findChildren(QPushButton):
        if button.property("uiControlPart"):
            assert button.property("uiRole") is None
            assert button.height() < 32
            continue
        expected_height = 32 if button.objectName() == "iconButton" else 36
        assert button.height() == expected_height
        assert button.property("uiRole") in {
            "primary",
            "secondary",
            "danger",
            "success",
            "ghost",
        }


def test_settings_zoom_spinboxes_do_not_clip_numbers(qtbot):
    from ui.dialogs.settings.settings_dialog import SettingsDialog

    dialog = SettingsDialog()
    dialog.resize(900, 760)
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitUntil(lambda: dialog.isVisible(), timeout=1000)

    for spinbox in (dialog.zoom_max_spinbox, dialog.zoom_min_spinbox):
        line_edit = spinbox.findChild(QLineEdit)
        assert (spinbox.height(), spinbox.minimumHeight(), spinbox.maximumHeight()) == (
            32,
            32,
            32,
        )
        assert line_edit.height() >= line_edit.fontMetrics().height()
        assert "QDoubleSpinBox QLineEdit" in spinbox.styleSheet()


def test_ui_code_does_not_bypass_themed_message_box():
    """业务 UI 不得重新引入系统原生消息框入口。"""
    ui_root = Path(__file__).resolve().parents[2] / "ui"
    violations = []
    direct_constructor = re.compile(r"(?<!Themed)QMessageBox\s*\(")
    static_call = re.compile(
        r"QMessageBox\.(information|warning|critical|question)\s*\("
    )
    for path in ui_root.rglob("*.py"):
        if path.name == "dialog_utils.py":
            continue
        source = path.read_text(encoding="utf-8")
        if direct_constructor.search(source) or static_call.search(source):
            violations.append(str(path.relative_to(ui_root)))

    assert violations == []


def test_help_contact_metadata_uses_current_brand():
    from _version_ import CONTACT_INFO

    assert CONTACT_INFO == {
        "support_email": "admin@anlife.top",
        "company": "anlife",
        "copyright_year": "2024",
    }
