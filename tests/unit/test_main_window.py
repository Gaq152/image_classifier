"""主窗口 UI 信号连接测试。"""

import logging
from unittest.mock import Mock, patch

import pytest
from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from PyQt6.QtWidgets import QMainWindow

from ui.main_window import ImageClassifier, __version__


class ToolbarHarness(ImageClassifier):
    """仅初始化工具栏测试所需状态。"""

    def __init__(self):
        QMainWindow.__init__(self)
        self.version = __version__
        self.logger = logging.getLogger("toolbar-test")
        self.categories = set()
        self.dialog_open_count = 0
        self.config = None
        self.update_checker_thread = None
        self._main_update_state = "idle"
        self._pending_update_version = None
        self._pending_update_manifest = None
        self._pending_update_token = ""
        self._update_check_manual = False
        self._update_check_animation_step = 0
        self._update_check_animation_timer = QTimer(self)
        self._update_check_animation_timer.setInterval(300)
        self._update_check_animation_timer.timeout.connect(
            self._advance_update_check_animation
        )

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
    download_completed = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self.state = "idle"
        self.message = ""
        self.downloaded = 0
        self.total = 0
        self.show_progress_dialog_calls = 0
        self.shutdown_calls = 0
        self.install_ready_update_calls = 0
        self.discard_ready_update_calls = 0

    @property
    def is_active(self):
        return self.state in {
            "downloading",
            "retrying",
            "verifying",
            "pausing",
            "cancelling",
        }

    @property
    def has_download_task(self):
        return self.is_active or self.state == "paused"

    def show_progress_dialog(self, _parent):
        self.show_progress_dialog_calls += 1

    def install_ready_update(self):
        self.install_ready_update_calls += 1
        return True

    def discard_ready_update(self):
        self.discard_ready_update_calls += 1
        self.state = "idle"
        self.message = ""
        self.state_changed.emit("idle", "")

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


def test_status_bar_exposes_paused_download_and_progress(qapp):
    """暂停下载后右下角应显示断点进度，并可重新打开进度窗口。"""
    window = ToolbarHarness()
    controller = DownloadControllerStub()
    controller.state = "paused"
    controller.message = "更新下载已暂停"
    controller.downloaded = 25
    controller.total = 100
    window.update_download_controller = controller
    try:
        window.create_status_bar()
        window._connect_update_download_controller()

        assert window._main_update_state == "paused"
        assert window.update_download_button.text() == "继续更新 25%"
        window.update_download_button.click()
        assert controller.show_progress_dialog_calls == 1
    finally:
        window.close()
        window.deleteLater()


def test_idle_update_button_starts_manual_check_and_animation(qapp):
    """空闲入口点击后应启动后台检查并进入点状加载状态。"""
    window = ToolbarHarness()
    controller = DownloadControllerStub()
    window.update_download_controller = controller
    checker = Mock()
    checker.isRunning.return_value = False
    checker.check_success.connect = Mock()
    checker.check_failed.connect = Mock()
    try:
        window.create_status_bar()
        window._connect_update_download_controller()

        with (
            patch("ui.main_window.load_ready_update", return_value=None),
            patch("ui.main_window.UpdateCheckerThread", return_value=checker),
            patch("ui.main_window.toast_info") as toast,
        ):
            window.update_download_button.click()

        assert window._main_update_state == "checking"
        assert window._update_check_animation_timer.isActive()
        assert window.update_download_button.text().startswith("检查更新")
        checker.start.assert_called_once_with()
        toast.assert_called_once_with(window, "正在检查更新...")
    finally:
        window._update_check_animation_timer.stop()
        window.close()
        window.deleteLater()


def test_auto_update_result_waits_for_status_button_click(qapp):
    """自动检查发现新版本时只提醒，点击入口后才显示更新内容。"""
    window = ToolbarHarness()
    controller = DownloadControllerStub()
    window.update_download_controller = controller
    manifest = {
        "version": "9.9.9",
        "url": "https://example.invalid/ImageClassifier.exe",
        "size_bytes": 123,
        "notes": "测试更新",
    }
    window._local_update_info = {
        "version": None,
        "path": None,
        "batch_path": None,
    }
    try:
        window.create_status_bar()
        window._connect_update_download_controller()

        with (
            patch("ui.main_window.UpdateInfoDialog") as dialog_class,
            patch("ui.main_window.toast_info") as toast,
        ):
            window._process_update_result(
                "9.9.9",
                manifest,
                "https://example.invalid/latest.json",
                "token",
                manual=False,
            )
            dialog_class.assert_not_called()
            toast.assert_called_once_with(window, "发现新版本 v9.9.9")

            assert window._main_update_state == "available"
            assert "9.9.9" in window.update_download_button.text()
            window.update_download_button.click()

        dialog_class.assert_called_once()
        dialog_class.return_value.exec.assert_called_once_with()
    finally:
        window.close()
        window.deleteLater()


def test_manual_check_without_update_restores_idle_and_keeps_toast(qapp):
    """手动检查没有新版本时恢复普通入口并保留原有 Toast。"""
    window = ToolbarHarness()
    controller = DownloadControllerStub()
    window.update_download_controller = controller
    window._local_update_info = {
        "version": None,
        "path": None,
        "batch_path": None,
    }
    try:
        window.create_status_bar()
        window._connect_update_download_controller()
        with patch("ui.main_window.toast_success") as toast:
            window._process_update_result(
                window.version,
                {"version": window.version},
                None,
                "",
                manual=True,
            )

        assert window._main_update_state == "idle"
        assert window.update_download_button.text() == "检查更新"
        toast.assert_called_once_with(
            window,
            f"当前已是最新版本 v{window.version}",
        )
    finally:
        window.close()
        window.deleteLater()


def test_ready_update_reopens_themed_progress_dialog(qapp):
    """完整包入口应复用程序主题进度窗，不能打开原生消息框。"""
    window = ToolbarHarness()
    controller = DownloadControllerStub()
    controller.state = "ready"
    controller.message = "更新 v9.9.9 已下载"
    window.update_download_controller = controller
    try:
        window.create_status_bar()
        window._connect_update_download_controller()

        assert window._main_update_state == "ready"
        assert window.update_download_button.text() == "重启更新"
        window.update_download_button.click()
        assert controller.show_progress_dialog_calls == 1
    finally:
        window.close()
        window.deleteLater()


def test_download_completion_uses_status_entry_and_toast(qapp):
    """完成下载后提示右下角入口，入口继续复用主题进度窗。"""
    window = ToolbarHarness()
    controller = DownloadControllerStub()
    window.update_download_controller = controller
    try:
        window.create_status_bar()
        window._connect_update_download_controller()
        with patch("ui.main_window.toast_success") as toast:
            controller.state = "ready"
            controller.state_changed.emit("ready", "更新 v9.9.9 已下载")
            controller.download_completed.emit({"version": "9.9.9"})

        assert window.update_download_button.text() == "重启更新"
        toast.assert_called_once_with(
            window,
            "更新 v9.9.9 已下载，可点击右下角“重启更新”完成安装",
        )
    finally:
        window.close()
        window.deleteLater()


def test_cancelled_download_returns_to_available_update(qapp):
    """下载取消后应保留线上版本信息，以便用户重新发起下载。"""
    window = ToolbarHarness()
    controller = DownloadControllerStub()
    window.update_download_controller = controller
    window._pending_update_version = "9.9.9"
    window._pending_update_manifest = {"version": "9.9.9"}
    try:
        window.create_status_bar()
        window._connect_update_download_controller()
        window._on_update_download_state("cancelled", "更新下载已取消")

        assert window._main_update_state == "available"
        assert "9.9.9" in window.update_download_button.text()
    finally:
        window.close()
        window.deleteLater()
