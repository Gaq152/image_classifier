"""统一 UI 设计系统的尺寸、角色和弹窗入口测试。"""

import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QLineEdit,
    QVBoxLayout,
    QMessageBox,
    QPushButton,
    QLabel,
    QTabWidget,
    QTextBrowser,
    QToolButton,
    QSizePolicy,
    QWidget,
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


def test_themed_message_box_does_not_expand_icon_column(qtbot):
    """消息框图标不能继承正文最小宽度而制造大块左侧空白。"""
    box = ThemedMessageBox()
    qtbot.addWidget(box)
    box.setIcon(QMessageBox.Icon.Question)
    box.setText("确定要清除SMB/NAS网络路径的图片缓存吗？")
    box.setInformativeText("这将删除本地缓存目录中的所有文件。")
    box.addButton("是", QMessageBox.ButtonRole.YesRole)
    box.addButton("否", QMessageBox.ButtonRole.NoRole)

    box.show()
    qtbot.waitUntil(lambda: box.isVisible(), timeout=1000)

    icon_label = box.findChild(QLabel, "qt_msgboxex_icon_label")
    text_label = box.findChild(QLabel, "qt_msgbox_label")
    assert icon_label is not None
    assert text_label is not None
    assert icon_label.minimumWidth() < 100
    assert icon_label.width() < text_label.width()
    assert icon_label.pixmap() is not None
    assert icon_label.width() >= icon_label.pixmap().deviceIndependentSize().width()
    assert text_label.x() - icon_label.geometry().right() < 40
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


def test_settings_only_exposes_update_proxy(qtbot):
    from ui.dialogs.settings.settings_dialog import SettingsDialog

    dialog = SettingsDialog()
    qtbot.addWidget(dialog)

    assert hasattr(dialog, "update_proxy_input")
    assert not hasattr(dialog, "check_update_btn")
    assert not hasattr(dialog, "auto_update_switch")
    assert not hasattr(dialog, "endpoint_input")
    assert not hasattr(dialog, "token_input")
    button_texts = {button.text() for button in dialog.findChildren(QPushButton)}
    assert "检查更新" not in button_texts


def test_settings_uses_compact_info_buttons_for_feature_help(qtbot):
    from ui.dialogs.settings.settings_dialog import SettingsDialog

    dialog = SettingsDialog()
    qtbot.addWidget(dialog)

    info_buttons = dialog.findChildren(QToolButton, "infoButton")
    assert len(info_buttons) >= 15
    assert all(button.toolTip() for button in info_buttons)
    assert all(len(button.toolTip()) <= 50 for button in info_buttons)
    assert all((button.width(), button.height()) == (18, 18) for button in info_buttons)

    with patch(
        "ui.dialogs.settings.settings_dialog.QToolTip.showText"
    ) as show_tooltip:
        info_buttons[0].click()

    show_tooltip.assert_called_once()


def test_settings_hides_inline_descriptions_and_proxy_placeholder(qtbot):
    from ui.dialogs.settings.settings_dialog import SettingsDialog

    dialog = SettingsDialog()
    qtbot.addWidget(dialog)

    visible_text = "\n".join(label.text() for label in dialog.findChildren(QLabel))
    assert dialog.update_proxy_input.placeholderText() == ""
    assert "留空时直接连接 GitHub" not in visible_text
    assert "预热功能会在打开网络目录时" not in visible_text
    assert "建议开启循环翻页" not in visible_text
    assert "约增加预热时间" not in visible_text
    assert "关闭程序时保存窗口位置和大小" not in visible_text


def test_settings_normalizes_and_saves_clash_proxy(qtbot):
    from ui.dialogs.settings.settings_dialog import SettingsDialog

    dialog = SettingsDialog()
    qtbot.addWidget(dialog)
    fake_config = SimpleNamespace(update_proxy="")
    dialog.app_config = fake_config
    dialog.update_proxy_input.setText("127.0.0.1:7890")

    with patch("ui.dialogs.settings.settings_dialog.toast_success") as toast:
        dialog.save_update_proxy()

    assert fake_config.update_proxy == "http://127.0.0.1:7890"
    assert dialog.update_proxy_input.text() == "http://127.0.0.1:7890"
    toast.assert_called_once_with(dialog, "更新代理已保存")


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


def test_help_dialog_has_compact_about_page_without_version_history(qtbot):
    from ui.dialogs.help_dialog import TabbedHelpDialog

    dialog = TabbedHelpDialog("7.2.1")
    qtbot.addWidget(dialog)

    tab_widget = dialog.findChild(QTabWidget)
    about_tab = tab_widget.widget(3)
    about_text = about_tab.findChild(QTextBrowser).toPlainText()
    hero = about_tab.findChild(QWidget, "aboutHero")
    logo = about_tab.findChild(QLabel, "aboutLogo")
    app_name = about_tab.findChild(QLabel, "aboutAppName")

    assert dialog.layout().count() == 1
    assert hero.height() == 164
    assert hero.sizePolicy().verticalPolicy() == QSizePolicy.Policy.Fixed
    assert app_name.text() == "图片分类工具"
    assert app_name.alignment() == Qt.AlignmentFlag.AlignCenter
    assert logo.pixmap() is not None
    assert logo.pixmap().width() == 52
    assert "主要功能" in about_text
    assert "版本发展历程" not in about_text
    assert "更新日志" not in about_text


def test_help_templates_use_current_feature_names():
    html_root = Path(__file__).resolve().parents[2] / "assets" / "html"
    rendered_help = "\n".join(
        (html_root / name).read_text(encoding="utf-8")
        for name in ("quick_start.html", "user_guide.html", "faq.html", "about.html")
    )

    assert "新增类别" not in rendered_help
    assert "点击右下角版本号可打开更新中心" in rendered_help
    assert "版本发展历程" not in rendered_help
