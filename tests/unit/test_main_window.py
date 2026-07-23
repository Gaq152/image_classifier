"""主窗口 UI 信号连接测试。"""

import logging

from PyQt6.QtWidgets import QMainWindow

from ui.main_window import ImageClassifier


class ToolbarHarness(ImageClassifier):
    """仅初始化工具栏测试所需状态。"""

    def __init__(self):
        QMainWindow.__init__(self)
        self.logger = logging.getLogger("toolbar-test")
        self.categories = set()
        self.dialog_open_count = 0

    def show_add_category_dialog(self):
        """记录添加类别对话框的打开次数。"""
        self.dialog_open_count += 1

    def create_mode_button(self, toolbar):
        """跳过与当前测试无关的操作模式按钮。"""

    def create_category_mode_button(self, toolbar):
        """跳过与当前测试无关的分类模式按钮。"""


def test_toolbar_add_category_action_opens_dialog(qapp):
    """工具栏添加类别按钮应打开对话框且不污染类别集合。"""
    window = ToolbarHarness()
    try:
        window.create_toolbar()
        action = next(
            item for item in window.toolbar.actions()
            if item.text() == "➕ 添加类别"
        )

        action.trigger()

        assert window.dialog_open_count == 1
        assert window.categories == set()
    finally:
        window.close()
        window.deleteLater()
