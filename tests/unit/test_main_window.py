"""主窗口 UI 信号连接测试。"""

import logging

import pytest
from PyQt6.QtCore import QObject, pyqtSignal

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


class DownloadControllerStub(QObject):
    """状态栏下载入口测试替身。"""

    progress_changed = pyqtSignal(int, int)
    state_changed = pyqtSignal(str, str)

    def __init__(self):
        super().__init__()
        self.state = "idle"
        self.message = ""
        self.downloaded = 0
        self.total = 0
        self.show_progress_dialog_calls = 0
        self.shutdown_calls = 0

    def show_progress_dialog(self, _parent):
        self.show_progress_dialog_calls += 1

    def shutdown(self, timeout_ms=10000):
        self.shutdown_calls += 1
        return True


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


@pytest.mark.parametrize(
    ("status_filters", "search_text", "expected"),
    [
        ((True, True, True), "", False),
        ((False, True, True), "", True),
        ((True, False, True), "", True),
        ((True, True, True), "sample", True),
    ],
)
def test_image_filter_active_detection(
    qapp,
    status_filters,
    search_text,
    expected,
):
    """只有筛选条件或搜索会改变列表内容时才视为过滤已启用。"""
    window = ToolbarHarness()
    try:
        (
            window.filter_unclassified,
            window.filter_classified,
            window.filter_removed,
        ) = status_filters
        window._image_search_text = search_text

        assert window.is_image_filter_active() is expected
    finally:
        window.close()
        window.deleteLater()


def test_status_bar_exposes_background_update_progress(qapp):
    """后台下载隐藏进度窗后，状态栏仍应提供可重新打开的进度入口。"""
    window = ToolbarHarness()
    controller = DownloadControllerStub()
    window.update_download_controller = controller
    try:
        window.create_status_bar()
        window._connect_update_download_controller()

        controller.state = "downloading"
        controller.state_changed.emit("downloading", "正在下载更新包...")
        controller.progress_changed.emit(25, 100)

        assert window.update_download_button.isVisibleTo(window)
        assert window.update_download_button.text() == "更新 25%"

        window.update_download_button.click()
        assert controller.show_progress_dialog_calls == 1
    finally:
        window.close()
        window.deleteLater()
