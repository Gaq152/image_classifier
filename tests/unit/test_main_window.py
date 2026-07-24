"""主窗口 UI 信号连接测试。"""

import logging
from unittest.mock import Mock, patch

import pytest
from PyQt6.QtCore import QObject, QRect, QTimer, pyqtSignal

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
        self._main_update_message = ""
        self._pending_update_version = None
        self._pending_update_manifest = None
        self._latest_checked_version = ""
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

    ACTIVE_STATES = {
        "downloading",
        "retrying",
        "verifying",
        "pausing",
        "cancelling",
    }

    progress_changed = pyqtSignal(int, int)
    state_changed = pyqtSignal(str, str)
    download_completed = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self.state = "idle"
        self.message = ""
        self.downloaded = 0
        self.total = 0
        self.shutdown_calls = 0
        self.install_ready_update_calls = 0
        self.discard_ready_update_calls = 0
        self.pause_calls = 0
        self.resume_calls = 0
        self.cancel_calls = 0
        self.start_calls = []
        self._version = ""

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

    def start(self, manifest, version, token="", proxy=None):
        self.start_calls.append((manifest, version, token, proxy))
        self._version = str(version)
        self.state = "downloading"
        self.message = "正在下载更新包..."
        self.state_changed.emit(self.state, self.message)
        return True

    def pause(self):
        self.pause_calls += 1

    def resume(self):
        self.resume_calls += 1

    def cancel(self):
        self.cancel_calls += 1

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


def test_status_bar_opens_popover_with_background_download_progress(qapp):
    """下载进度应集成在版本按钮浮层中，不再打开独立进度窗。"""
    window = ToolbarHarness()
    controller = DownloadControllerStub()
    window.update_download_controller = controller
    try:
        window.create_status_bar()
        window._connect_update_download_controller()

        controller.state = "downloading"
        controller.downloaded = 25
        controller.total = 100
        controller.state_changed.emit("downloading", "正在下载更新包...")
        controller.progress_changed.emit(25, 100)

        assert window.update_download_button.isVisibleTo(window)
        assert "25%" in window.update_download_button.text()
        window.update_download_button.click()
        assert window.update_center_popover.isVisible()
        assert window.update_center_popover.progress_bar.value() == 25
    finally:
        window.update_center_popover.hide()
        window.close()
        window.deleteLater()


def test_paused_download_can_resume_from_popover(qapp):
    """暂停状态应在浮层中展示断点进度并允许继续。"""
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
        window.update_download_button.click()

        assert "继续更新 25%" in window.update_download_button.text()
        assert window.update_center_popover.primary_button.text() == "继续下载"
        window.update_center_popover.primary_button.click()
        assert controller.resume_calls == 1
    finally:
        window.update_center_popover.hide()
        window.close()
        window.deleteLater()


def test_version_button_opens_popover_before_manual_check(qapp):
    """版本按钮只展开浮层，浮层内的检查按钮才启动手动检查。"""
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
        window.update_download_button.click()
        assert window.update_center_popover.isVisible()
        assert checker.start.call_count == 0

        config = Mock(update_proxy="http://127.0.0.1:7890")
        with (
            patch("ui.main_window.load_ready_update", return_value=None),
            patch("ui.main_window.UpdateCheckerThread", return_value=checker) as factory,
            patch("ui.main_window.get_app_config", return_value=config),
            patch("ui.main_window.toast_info") as toast,
        ):
            window.update_center_popover.primary_button.click()

        assert window._main_update_state == "checking"
        assert window._update_check_animation_timer.isActive()
        assert window.update_download_button.isEnabled()
        assert window.update_center_popover.primary_button.text().startswith("正在检查")
        assert not window.update_center_popover.primary_button.isEnabled()
        factory.assert_called_once_with(
            "https://github.com/Gaq152/image_classifier/releases/latest/download/manifest.json",
            "",
            "http://127.0.0.1:7890",
        )
        checker.start.assert_called_once_with()
        toast.assert_called_once_with(window, "正在检查更新...")
    finally:
        window._update_check_animation_timer.stop()
        window.update_center_popover.hide()
        window.close()
        window.deleteLater()


def test_auto_update_result_populates_popover_without_release_notes(qapp):
    """自动检查只写入版本号，更新说明不得进入更新浮层。"""
    window = ToolbarHarness()
    controller = DownloadControllerStub()
    window.update_download_controller = controller
    manifest = {
        "version": "9.9.9",
        "url": "https://example.invalid/ImageClassifier.exe",
        "size_bytes": 123,
        "notes": "这段更新说明不应该显示",
    }
    window._local_update_info = {
        "version": None,
        "path": None,
        "batch_path": None,
    }
    try:
        window.create_status_bar()
        window._connect_update_download_controller()
        with patch("ui.main_window.toast_info") as toast:
            window._process_update_result(
                "9.9.9",
                manifest,
                "https://example.invalid/latest.json",
                "",
                manual=False,
            )

        toast.assert_called_once_with(window, "发现新版本 v9.9.9")
        assert window._main_update_state == "available"
        window.update_download_button.click()
        assert window.update_center_popover.current_version_value.text() == f"v{window.version}"
        assert window.update_center_popover.latest_version_value.text() == "v9.9.9"
        assert "这段更新说明" not in window.update_center_popover.status_label.text()

        window.update_center_popover.primary_button.click()
        assert controller.start_calls == [(manifest, "9.9.9", "", None)]
    finally:
        window.update_center_popover.hide()
        window.close()
        window.deleteLater()


def test_manual_check_without_update_restores_version_button(qapp):
    """手动检查已是最新版时恢复版本按钮并同步最新版本号。"""
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
        assert window.update_download_button.text() == f"v{window.version}"
        assert window.update_center_popover.latest_version_value.text() == f"v{window.version}"
        toast.assert_called_once_with(
            window,
            f"当前已是最新版本 v{window.version}",
        )
    finally:
        window.close()
        window.deleteLater()


def test_automatic_check_failure_keeps_existing_update_state(qapp):
    """自动检查网络失败不能覆盖用户当前看到的更新状态。"""
    window = ToolbarHarness()
    controller = DownloadControllerStub()
    window.update_download_controller = controller
    try:
        window.create_status_bar()
        window._set_main_update_state("available", "9.9.9")
        window._local_update_info = {
            "version": None,
            "path": None,
            "batch_path": None,
        }
        with patch("ui.main_window.toast_warning") as toast:
            window._process_update_result(
                None,
                None,
                None,
                None,
                manual=False,
                error_message="网络不可用",
            )

        assert window._main_update_state == "available"
        assert window.update_center_popover.latest_version_value.text() == "v9.9.9"
        toast.assert_not_called()
    finally:
        window.close()
        window.deleteLater()


def test_manual_check_failure_changes_popover_state(qapp):
    """只有手动检查失败才在更新中心显示失败和重试入口。"""
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
        with patch("ui.main_window.toast_warning"):
            window._process_update_result(
                None,
                None,
                None,
                None,
                manual=True,
                error_message="网络不可用",
            )

        assert window._main_update_state == "failed"
        assert window.update_center_popover.title_label.text() == "更新失败"
        assert window.update_center_popover.primary_button.text() == "重新检查"
    finally:
        window.close()
        window.deleteLater()


def test_ready_update_requires_inline_restart_confirmation(qapp):
    """重启安装确认必须集成在更新浮层内，不能打开大弹窗。"""
    window = ToolbarHarness()
    controller = DownloadControllerStub()
    controller.state = "ready"
    controller.message = "更新 v9.9.9 已下载"
    controller._version = "9.9.9"
    window.update_download_controller = controller
    try:
        window.create_status_bar()
        window._connect_update_download_controller()
        window.update_download_button.click()

        assert window.update_center_popover.primary_button.text() == "重启更新"
        window.update_center_popover.primary_button.click()
        assert controller.install_ready_update_calls == 0
        assert window.update_center_popover.primary_button.text() == "确认重启"
        window.update_center_popover.primary_button.click()
        assert controller.install_ready_update_calls == 1
    finally:
        window.update_center_popover.hide()
        window.close()
        window.deleteLater()


def test_cancel_download_requires_inline_confirmation(qapp):
    """取消下载必须在浮层内二次确认。"""
    window = ToolbarHarness()
    controller = DownloadControllerStub()
    controller.state = "downloading"
    window.update_download_controller = controller
    try:
        window.create_status_bar()
        window._connect_update_download_controller()
        window.update_download_button.click()

        window.update_center_popover.secondary_button.click()
        assert controller.cancel_calls == 0
        assert window.update_center_popover.primary_button.text() == "确认取消"
        window.update_center_popover.primary_button.click()
        assert controller.cancel_calls == 1
    finally:
        window.update_center_popover.hide()
        window.close()
        window.deleteLater()


def test_download_completion_uses_version_entry_and_toast(qapp):
    window = ToolbarHarness()
    controller = DownloadControllerStub()
    window.update_download_controller = controller
    try:
        window.create_status_bar()
        window._connect_update_download_controller()
        with patch("ui.main_window.toast_success") as toast:
            controller.state = "ready"
            controller._version = "9.9.9"
            controller.state_changed.emit("ready", "更新 v9.9.9 已下载")
            controller.download_completed.emit({"version": "9.9.9"})

        assert "重启更新" in window.update_download_button.text()
        toast.assert_called_once_with(
            window,
            "更新 v9.9.9 已下载，可点击右下角版本按钮完成安装",
        )
    finally:
        window.close()
        window.deleteLater()


def test_cancelled_download_returns_to_available_update(qapp):
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


def test_save_window_geometry_records_maximized_state_and_normal_rect():
    """最大化关闭时应保存最大化标记和可恢复的普通窗口尺寸。"""
    config = Mock(remember_window_geometry=True)
    window = Mock()
    window.isMaximized.return_value = True
    window.normalGeometry.return_value = QRect(120, 80, 1280, 720)
    window.geometry.return_value = QRect(0, 0, 1920, 1040)
    window.screen.return_value.name.return_value = "DISPLAY1"

    with patch("ui.main_window.get_app_config", return_value=config):
        ImageClassifier._save_window_geometry(window)

    assert config.window_geometry == {
        "x": 120,
        "y": 80,
        "width": 1280,
        "height": 720,
        "screen_name": "DISPLAY1",
        "maximized": True,
    }


def test_restore_window_geometry_preserves_maximized_state(qapp):
    """保存为最大化的窗口下次启动仍应进入最大化按钮状态。"""
    screen = qapp.primaryScreen()
    available = screen.availableGeometry()
    width = max(200, available.width() - 100)
    height = max(200, available.height() - 100)
    config = Mock(
        remember_window_geometry=True,
        window_geometry={
            "x": available.x() + 50,
            "y": available.y() + 50,
            "width": width,
            "height": height,
            "screen_name": screen.name(),
            "maximized": True,
        },
    )
    window = ToolbarHarness()
    try:
        with patch("ui.main_window.get_app_config", return_value=config):
            restored = window._restore_window_geometry()

        assert restored is True
        assert window._start_maximized is True
        assert (window.width(), window.height()) == (width, height)
    finally:
        window.close()
        window.deleteLater()


def test_legacy_nearly_full_screen_geometry_is_inferred_as_maximized(qapp):
    """旧配置没有状态字段时，接近铺满屏幕的尺寸应兼容为最大化。"""
    screen = qapp.primaryScreen()
    available = screen.availableGeometry()
    config = Mock(
        remember_window_geometry=True,
        window_geometry={
            "x": available.x(),
            "y": available.y(),
            "width": available.width(),
            "height": available.height(),
            "screen_name": screen.name(),
        },
    )
    window = ToolbarHarness()
    try:
        with patch("ui.main_window.get_app_config", return_value=config):
            restored = window._restore_window_geometry()

        assert restored is True
        assert window._start_maximized is True
    finally:
        window.close()
        window.deleteLater()


def test_default_window_geometry_is_centered_and_starts_maximized(qapp):
    """没有历史记录时普通恢复尺寸应居中，首次显示状态应为最大化。"""
    window = ToolbarHarness()
    try:
        window._set_default_window_geometry()
        available = qapp.primaryScreen().availableGeometry()
        expected_x = available.x() + (available.width() - window.width()) // 2
        expected_y = available.y() + (available.height() - window.height()) // 2

        assert window._start_maximized is True
        assert (window.x(), window.y()) == (expected_x, expected_y)
    finally:
        window.close()
        window.deleteLater()
