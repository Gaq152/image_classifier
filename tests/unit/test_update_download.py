"""后台更新下载、取消和进度对话框测试。"""

import hashlib
import threading
import time
from unittest.mock import Mock, patch
from urllib.error import URLError

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtWidgets import QDialog

from core.update_utils import (
    cleanup_incomplete_updates,
    discard_pending_update,
    download_with_progress,
    load_pending_update,
    load_ready_update,
    save_pending_update,
)
from ui.update_dialog import DownloadProgressDialog, UpdateInfoDialog
from ui.update_download import UpdateDownloadController, UpdateDownloadWorker


class BytesResponse:
    """可被下载线程关闭的内存响应。"""

    def __init__(
        self,
        data: bytes,
        delay: float = 0.0,
        status: int = 200,
        content_range: str | None = None,
    ):
        self.data = data
        self.offset = 0
        self.delay = delay
        self.status = status
        self.headers = {"Content-Length": str(len(data))}
        if content_range:
            self.headers["Content-Range"] = content_range
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


class InterruptingResponse(BytesResponse):
    """读取一个分块后模拟网络中断。"""

    def __init__(self, data: bytes):
        super().__init__(data)
        self.read_count = 0

    def read(self, size: int) -> bytes:
        self.read_count += 1
        if self.read_count > 1:
            raise URLError("connection reset")
        return super().read(size)


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
        self.pause = Mock()
        self.resume = Mock(return_value=True)
        self.install_ready_update = Mock(return_value=True)

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


def build_manifest(payload: bytes):
    return {
        "url": "https://example.invalid/ImageClassifier.exe",
        "size_bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def test_download_resumes_after_midstream_network_interruption(tmp_path):
    """网络中断自动重试时，应从已写入字节处发送 Range 继续下载。"""
    payload = b"resume-payload" * 60000
    destination = tmp_path / "update.exe.part"
    first_response = InterruptingResponse(payload)
    seen_ranges = []

    def open_response(request, **_kwargs):
        range_header = request.get_header("Range")
        seen_ranges.append(range_header)
        if len(seen_ranges) == 1:
            return first_response
        start = int(range_header.removeprefix("bytes=").removesuffix("-"))
        remaining = payload[start:]
        return BytesResponse(
            remaining,
            status=206,
            content_range=f"bytes {start}-{len(payload) - 1}/{len(payload)}",
        )

    with patch("core.update_utils.urlopen", side_effect=open_response):
        download_with_progress(
            "https://example.invalid/update.exe",
            destination,
            expected_size=len(payload),
            retry_delay=0,
        )

    assert destination.read_bytes() == payload
    assert seen_ranges[0] is None
    assert seen_ranges[1] == f"bytes={256 * 1024}-"


def test_resume_falls_back_to_full_download_when_server_ignores_range(tmp_path):
    """服务端返回 200 而非 206 时必须覆盖临时文件，不能拼接出损坏包。"""
    payload = b"full-package" * 1000
    destination = tmp_path / "update.exe.part"
    destination.write_bytes(payload[:1234])
    response = BytesResponse(payload, status=200)
    requests = []

    def open_response(request, **_kwargs):
        requests.append(request)
        return response

    with patch("core.update_utils.urlopen", side_effect=open_response):
        download_with_progress(
            "https://example.invalid/update.exe",
            destination,
            expected_size=len(payload),
            retry_delay=0,
        )

    assert requests[0].get_header("Range") == "bytes=1234-"
    assert destination.read_bytes() == payload


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


def test_worker_pause_keeps_partial_and_next_worker_resumes(qtbot, tmp_path):
    """暂停必须保留 .part，继续时从断点下载并仍通过最终校验。"""
    payload = b"x" * (4 * 1024 * 1024)
    destination = tmp_path / "ImageClassifier_v9.9.9.exe"
    first_response = BytesResponse(payload, delay=0.005)
    first_worker = UpdateDownloadWorker(
        build_manifest(payload),
        "9.9.9",
        "",
        destination,
    )
    paused_once = False

    def pause_after_progress(done, _total):
        nonlocal paused_once
        if done > 0 and not paused_once:
            paused_once = True
            first_worker.pause()

    first_worker.progress_changed.connect(pause_after_progress)
    with patch("core.update_utils.urlopen", return_value=first_response):
        with qtbot.waitSignal(first_worker.download_paused, timeout=3000):
            first_worker.start()

    assert first_worker.wait(3000)
    partial_size = first_worker.partial_path.stat().st_size
    assert 0 < partial_size < len(payload)

    range_requests = []

    def resume_response(request, **_kwargs):
        range_requests.append(request.get_header("Range"))
        remaining = payload[partial_size:]
        return BytesResponse(
            remaining,
            status=206,
            content_range=(
                f"bytes {partial_size}-{len(payload) - 1}/{len(payload)}"
            ),
        )

    resumed_worker = UpdateDownloadWorker(
        build_manifest(payload),
        "9.9.9",
        "",
        destination,
    )
    with patch("core.update_utils.urlopen", side_effect=resume_response):
        with qtbot.waitSignal(resumed_worker.download_completed, timeout=3000):
            resumed_worker.start()

    assert resumed_worker.wait(3000)
    assert range_requests == [f"bytes={partial_size}-"]
    assert destination.read_bytes() == payload


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


def test_controller_shutdown_pauses_and_releases_file(
    qtbot,
    tmp_path,
    monkeypatch,
):
    """退出时应停止线程、释放句柄并保留可在下次启动继续的断点。"""
    payload = b"x" * (8 * 1024 * 1024)
    response = BytesResponse(payload, delay=0.01)
    monkeypatch.setattr("ui.update_download.get_update_dir", lambda: tmp_path)
    monkeypatch.setattr(
        "ui.update_download.cleanup_incomplete_updates",
        lambda: cleanup_incomplete_updates(tmp_path),
    )
    monkeypatch.setattr(
        "ui.update_download.load_ready_update",
        lambda: load_ready_update(tmp_path),
    )
    monkeypatch.setattr(
        "ui.update_download.load_pending_update",
        lambda: load_pending_update(tmp_path),
    )
    monkeypatch.setattr(
        "ui.update_download.discard_pending_update",
        lambda: discard_pending_update(tmp_path),
    )
    controller = UpdateDownloadController()

    with patch("core.update_utils.urlopen", return_value=response):
        controller.start(build_manifest(payload), "9.9.9")
        qtbot.waitUntil(lambda: controller.downloaded > 0, timeout=3000)
        assert controller.shutdown(timeout_ms=3000)

    assert response.closed_event.is_set()
    partial = tmp_path / "ImageClassifier_v9.9.9.exe.part"
    assert partial.exists()
    assert 0 < partial.stat().st_size < len(payload)
    assert not (tmp_path / "ImageClassifier_v9.9.9.exe").exists()
    assert load_pending_update(tmp_path) is not None

    restored = UpdateDownloadController()
    assert restored.state == "paused"
    assert restored.downloaded == partial.stat().st_size


def test_progress_dialog_background_and_close_have_distinct_behavior(qtbot):
    """显式后台下载继续任务，窗口关闭选择取消后才真正取消。"""
    controller = FakeDownloadController()
    dialog = DownloadProgressDialog(controller)
    qtbot.addWidget(dialog)
    dialog.show()

    dialog.background_btn.click()
    assert not dialog.isVisible()
    controller.cancel.assert_not_called()

    dialog.show()
    with patch.object(
        dialog,
        "_confirm_close_download",
        return_value="cancel",
    ) as confirm:
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


def test_progress_dialog_pauses_and_resumes_without_cancelling(qtbot):
    """暂停按钮应保留任务，暂停状态下同一按钮用于继续下载。"""
    controller = FakeDownloadController()
    dialog = DownloadProgressDialog(controller)
    qtbot.addWidget(dialog)
    dialog.show()

    dialog.pause_btn.click()
    controller.pause.assert_called_once_with()
    controller.cancel.assert_not_called()

    controller.state = "paused"
    controller.message = "更新下载已暂停"
    controller.state_changed.emit(controller.state, controller.message)
    assert dialog.pause_btn.text() == "继续下载"

    dialog.pause_btn.click()
    controller.resume.assert_called_once_with()
    controller.cancel.assert_not_called()
    controller.state = "cancelled"
    dialog.close()


def test_progress_dialog_uses_themed_ready_actions(qtbot):
    """下载完成与后续重开应复用同一主题窗口和重启操作。"""
    controller = FakeDownloadController()
    dialog = DownloadProgressDialog(controller)
    qtbot.addWidget(dialog)
    dialog.show()

    controller.state = "ready"
    controller.message = "更新 v9.9.9 已下载"
    controller.state_changed.emit(controller.state, controller.message)

    assert dialog.isVisible()
    assert dialog.background_btn.text() == "稍后安装"
    assert dialog.action_btn.text() == "立即重启"

    dialog.background_btn.click()
    assert not dialog.isVisible()
    controller.install_ready_update.assert_not_called()

    dialog.show()
    dialog.action_btn.click()
    controller.install_ready_update.assert_called_once_with()
    controller.state = "cancelled"
    dialog.close()


def test_cancel_from_paused_state_still_requires_confirmation(qtbot):
    """暂停后明确取消仍需二次确认，并删除任务由控制器负责。"""
    controller = FakeDownloadController()
    controller.state = "paused"
    controller.message = "更新下载已暂停"
    dialog = DownloadProgressDialog(controller)
    qtbot.addWidget(dialog)
    dialog.show()

    with patch.object(dialog, "_confirm_cancel_download", return_value=True):
        dialog.action_btn.click()

    controller.cancel.assert_called_once_with()
    controller.state = "cancelled"
    dialog.close()


def test_window_close_moves_download_to_background_when_selected(qtbot):
    """关闭窗口时选择后台下载，应隐藏窗口且不取消任务。"""
    controller = FakeDownloadController()
    dialog = DownloadProgressDialog(controller)
    qtbot.addWidget(dialog)
    dialog.show()

    with patch.object(
        dialog,
        "_confirm_close_download",
        return_value="background",
    ):
        dialog.close()

    assert not dialog.isVisible()
    controller.cancel.assert_not_called()
    controller.state = "cancelled"
    dialog.close()


def test_update_info_keeps_progress_above_settings_dialog(qtbot):
    """从设置页启动下载时，进度窗口必须以设置页为父窗口。"""
    settings_dialog = QDialog()
    qtbot.addWidget(settings_dialog)
    controller = Mock()
    controller.start.return_value = True
    manifest = {
        "url": "https://example.invalid/ImageClassifier.exe",
        "sha256": "abc",
        "size_bytes": 100,
    }
    update_dialog = UpdateInfoDialog(
        "9.9.9",
        "9.9.8",
        100,
        "测试更新",
        manifest,
        parent=settings_dialog,
    )
    qtbot.addWidget(update_dialog)

    with patch(
        "ui.update_dialog.get_update_download_controller",
        return_value=controller,
    ):
        update_dialog.start_download()

    controller.show_progress_dialog.assert_called_once_with(settings_dialog)


def test_progress_dialog_is_window_modal_to_its_parent(qtbot):
    """窗口级模态确保进度窗不会落到设置窗口后面。"""
    settings_dialog = QDialog()
    qtbot.addWidget(settings_dialog)
    controller = FakeDownloadController()
    dialog = DownloadProgressDialog(controller, settings_dialog)
    qtbot.addWidget(dialog)

    assert dialog.parentWidget() is settings_dialog
    assert dialog.windowModality() == Qt.WindowModality.WindowModal
