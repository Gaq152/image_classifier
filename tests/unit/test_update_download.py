"""后台更新下载、取消和进度对话框测试。"""

import hashlib
import threading
import time
from unittest.mock import patch
from urllib.error import URLError

from core.update_utils import (
    cleanup_incomplete_updates,
    discard_pending_update,
    download_with_progress,
    load_pending_update,
    load_ready_update,
)
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


def test_download_uses_same_github_accelerator_as_manifest(tmp_path):
    """GitHub 加速前缀必须同时应用到更新包下载。"""
    payload = b"proxied-package"
    destination = tmp_path / "update.exe.part"
    response = BytesResponse(payload)

    with patch("core.update_utils.urlopen", return_value=response) as opener:
        download_with_progress(
            "https://github.com/example/app/releases/download/v9/update.exe",
            destination,
            expected_size=len(payload),
            retries=0,
            proxy="https://ghfast.top",
        )

    request = opener.call_args.args[0]
    assert request.full_url == (
        "https://ghfast.top/"
        "https://github.com/example/app/releases/download/v9/update.exe"
    )
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
