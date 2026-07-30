"""教程内容和气泡定位回归测试。"""

from PyQt6.QtWidgets import QWidget

from ui.components.tutorial.bubble import ArrowPosition, TutorialBubble
from ui.components.tutorial.manager import TutorialManager


def _show_parent_and_target(qtbot, target_geometry):
    parent = QWidget()
    parent.resize(900, 600)
    target = QWidget(parent)
    target.setGeometry(*target_geometry)
    qtbot.addWidget(parent)
    parent.show()
    target.show()
    return parent, target


def test_category_focus_is_explained_inside_management_menu_step():
    """聚焦是类别右键菜单的子功能，不应拆成孤立步骤。"""
    steps = TutorialManager._define_tutorial_steps(None)
    focus_steps = [step for step in steps if step.title == "聚焦查看一个类别"]
    menu_step = next(step for step in steps if step.title == "类别管理菜单")

    assert focus_steps == []
    assert "只看此类别" in menu_step.content
    assert "<b>×</b>" in menu_step.content
    assert ("🎯", "只看此类别") in menu_step.mock_widget_content["items"]


def test_tutorial_avoids_overlapping_and_stale_mock_panels():
    """简单菜单写进气泡，过时的弹窗模型不再覆盖真实界面。"""
    steps = TutorialManager._define_tutorial_steps(None)
    by_title = {step.title: step for step in steps}

    for title in ("筛选图片", "类别排序", "添加分类类别", "设置面板", "获取帮助"):
        assert by_title[title].mock_widget_type is None

    assert "高级功能" not in by_title["获取帮助"].content
    assert len(steps) == 18


def test_primary_toolbar_steps_do_not_draw_cross_window_dual_arrows():
    """顶部主入口只定位自身，避免箭头横穿整个窗口。"""
    steps = TutorialManager._define_tutorial_steps(None)
    by_title = {step.title: step for step in steps}

    for title in ("打开图片目录", "添加分类类别"):
        step = by_title[title]
        assert step.arrow_position == ArrowPosition.TOP
        assert step.secondary_target_widget_name is None


def test_skip_tutorial_hover_uses_danger_color(qtbot):
    parent = QWidget()
    qtbot.addWidget(parent)
    bubble = TutorialBubble(parent)

    style = bubble._skip_button.styleSheet()
    assert "QPushButton#tutorialSkipButton:hover" in style
    assert "background-color" in style
    assert "uiRole" in style  # 仍保留统一 ghost 基础样式


def test_tutorial_bubble_flips_away_from_left_window_edge(qtbot):
    """左侧目标放不下气泡时，应自动显示到目标右侧。"""
    parent, target = _show_parent_and_target(qtbot, (10, 220, 100, 50))
    bubble = TutorialBubble(parent)
    bubble.set_content("<h3>图片列表</h3><p>定位测试</p>")
    bubble.set_arrow_position(ArrowPosition.RIGHT)

    bubble.show_at(target)

    assert bubble._arrow_position == ArrowPosition.LEFT
    assert bubble.x() > target.geometry().right()
    arrow_target_y = bubble.y() + bubble._arrow_tip_offset
    assert abs(arrow_target_y - target.geometry().center().y()) <= 1


def test_tutorial_bubble_flips_away_from_right_window_edge(qtbot):
    """右侧目标放不下气泡时，应自动显示到目标左侧。"""
    parent, target = _show_parent_and_target(qtbot, (790, 220, 100, 50))
    bubble = TutorialBubble(parent)
    bubble.set_content("<h3>类别列表</h3><p>定位测试</p>")
    bubble.set_arrow_position(ArrowPosition.LEFT)

    bubble.show_at(target)

    assert bubble._arrow_position == ArrowPosition.RIGHT
    assert bubble.geometry().right() < target.geometry().left()
    arrow_target_y = bubble.y() + bubble._arrow_tip_offset
    assert abs(arrow_target_y - target.geometry().center().y()) <= 1


def test_tutorial_center_step_has_no_directional_arrow(qtbot):
    """欢迎与完成步骤应稳定居中，不再用指向窗口边缘的假箭头。"""
    parent, target = _show_parent_and_target(qtbot, (0, 0, 900, 600))
    bubble = TutorialBubble(parent)
    bubble.set_content("<h3>欢迎</h3><p>居中显示</p>")
    bubble.set_arrow_position(ArrowPosition.CENTER)

    bubble.show_at(target)

    assert abs(bubble.geometry().center().x() - parent.rect().center().x()) <= 1
    assert abs(bubble.geometry().center().y() - parent.rect().center().y()) <= 1
    assert bubble._arrow_tip_offset is None
