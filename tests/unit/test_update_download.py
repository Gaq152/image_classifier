"""后台更新下载、取消和进度对话框测试。"""

import hashlib
import threading
import time
from unittest.mock import Mock, patch

from PyQt6.QtCore import QObject, pyqtSignal

from core.update_utils import load_ready_update
from ui.update_dialog import DownloadProgressDialog
from ui.update_download import UpdateDownloadController, UpdateDownloadWorker


class BytesResponse:
    """可被下载线程关闭的内存响应。"""

    def __init__(self, data: bytes, delay: float = 0.0):
        self.data = data
        self.offset = 0
        self.delay = delay
        self.headers = {"Content-Length": str(len(data))}
        self.closed_event = threading.Event()

    def read(self, size: int) -> bytes:
        if self.delay:
            time.sleep(self.delay)
        if self.closed_event.is_set() or self.offset >= len(self.data):
            return b""
        end = min(len(self.data), self.offset + size)
        chunk = self.data[self.offset:end]
        self.offset = end
        return chunk

    def close(self):
        self.closed_event.set()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


class FakeDownloadController(QObject):
    """进度窗口交互测试替身。"""

    progress_changed = pyqtSignal(int, int)
    state_changed = pyqtSignal(str, str)

    def __init__(self):
        super().__init__()
        self.state = "downloading"
        self.message = "正在下载更新包..."
        self.downloaded = 10
        self.total = 100
        self.cancel = Mock()
        self.install_ready_update = Mock(return_value=True)

    @property
    def is_active(self):
        return self.state in {"downloading", "verifying", "cancelling"}


def build_manifest(payload: bytes):
    return {
        "url": "https://example.invalid/ImageClassifier.exe",
        "size_bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def test_worker_only_publishes_exe_after_size_and_hash_verification(
    qtbot,
    tmp_path,
):
    """成功下载必须经过 .part、大小和哈希校验后才产生最终 exe。"""
    payload = b"verified-package" * 1000
    response = BytesResponse(payload)
    destination = tmp_path / "ImageClassifier_v9.9.9.exe"
    worker = UpdateDownloadWorker(
        build_manifest(payload),
        "9.9.9",
        "",
        destination,
    )

    with patch("core.update_utils.urlopen", return_value=response):
        with qtbot.waitSignal(worker.download_completed, timeout=3000):
            worker.start()

    assert worker.wait(3000)
    assert destination.read_bytes() == payload
    assert not worker.partial_path.exists()
    ready = load_ready_update(tmp_path, verify_hash=True)
    assert ready is not None
    assert ready["version"] == "9.9.9"


def test_worker_cancel_closes_response_and_deletes_partial(qtbot, tmp_path):
    """取消下载必须关闭网络响应并释放、删除临时文件。"""
    payload = b"x" * (8 * 1024 * 1024)
    response = BytesResponse(payload, delay=0.01)
    destination = tmp_path / "ImageClassifier_v9.9.9.exe"
    worker = UpdateDownloadWorker(
        build_manifest(payload),
        "9.9.9",
        "",
        destination,
    )
    worker.progress_changed.connect(lambda *_args: worker.cancel())

    with patch("core.update_utils.urlopen", return_value=response):
        with qtbot.waitSignal(worker.download_cancelled, timeout=3000):
            worker.start()

    assert worker.wait(3000)
    assert response.closed_event.is_set()
    assert not destination.exists()
    assert not worker.partial_path.exists()
    assert load_ready_update(tmp_path) is None


def test_controller_shutdown_waits_for_cancel_and_releases_file(
    qtbot,
    tmp_path,
    monkeypatch,
):
    """退出程序时控制器必须等下载线程停止，不能留下被占用文件。"""
    payload = b"x" * (8 * 1024 * 1024)
    response = BytesResponse(payload, delay=0.01)
    monkeypatch.setattr("ui.update_download.get_update_dir", lambda: tmp_path)
    monkeypatch.setattr("ui.update_download.cleanup_incomplete_updates", lambda: None)
    monkeypatch.setattr("ui.update_download.load_ready_update", lambda: None)
    controller = UpdateDownloadController()

    with patch("core.update_utils.urlopen", return_value=response):
        controller.start(build_manifest(payload), "9.9.9")
        qtbot.waitUntil(lambda: controller.downloaded > 0, timeout=3000)
        assert controller.shutdown(timeout_ms=3000)

    assert response.closed_event.is_set()
    assert not (tmp_path / "ImageClassifier_v9.9.9.exe.part").exists()
    assert not (tmp_path / "ImageClassifier_v9.9.9.exe").exists()


def test_progress_dialog_background_and_close_have_distinct_behavior(qtbot):
    """显式后台下载继续任务，窗口关闭确认后才真正取消。"""
    controller = FakeDownloadController()
    dialog = DownloadProgressDialog(controller)
    qtbot.addWidget(dialog)
    dialog.show()

    dialog.background_btn.click()
    assert not dialog.isVisible()
    controller.cancel.assert_not_called()

    dialog.show()
    with patch.object(dialog, "_confirm_cancel_download", return_value=True) as confirm:
        dialog.close()
    confirm.assert_called_once_with()
    controller.cancel.assert_called_once_with()


def test_cancel_button_requires_confirmation(qtbot):
    """点击取消下载时，拒绝确认应继续下载，确认后才调用取消。"""
    controller = FakeDownloadController()
    dialog = DownloadProgressDialog(controller)
    qtbot.addWidget(dialog)
    dialog.show()

    with patch.object(dialog, "_confirm_cancel_download", return_value=False):
        dialog.action_btn.click()
    controller.cancel.assert_not_called()

    with patch.object(dialog, "_confirm_cancel_download", return_value=True) as confirm:
        dialog.action_btn.click()
    confirm.assert_called_once_with()
    controller.cancel.assert_called_once_with()
    controller.state = "cancelled"
    dialog.close()


def test_window_close_keeps_downloading_when_confirmation_is_rejected(qtbot):
    """关闭窗口时选择继续下载，应忽略关闭事件并保留进度窗口。"""
    controller = FakeDownloadController()
    dialog = DownloadProgressDialog(controller)
    qtbot.addWidget(dialog)
    dialog.show()

    with patch.object(dialog, "_confirm_cancel_download", return_value=False):
        dialog.close()

    assert dialog.isVisible()
    controller.cancel.assert_not_called()
    controller.state = "cancelled"
    dialog.close()
