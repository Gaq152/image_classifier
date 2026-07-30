"""类别按钮到图片列表聚焦操作的信号链测试。"""

from types import SimpleNamespace

from ui._main_window.panels.category_panel import CategoryPanel


def test_category_button_forwards_single_category_focus_request(qtbot):
    """类别按钮的聚焦请求应携带唯一类别名转发给主窗口。"""
    config = SimpleNamespace(sort_ascending=True, category_shortcuts={})
    panel = CategoryPanel(config)
    qtbot.addWidget(panel)
    panel.update_data(
        ["白色车位内", "黄色车位内"],
        {"白色车位内": 12, "黄色车位内": 8},
        0,
    )
    requests = []
    panel.operation_requested.connect(
        lambda operation, data: requests.append((operation, data))
    )

    panel._category_buttons[1].focus_category()

    assert requests == [
        ("focus_category", {"category_name": "黄色车位内"})
    ]
