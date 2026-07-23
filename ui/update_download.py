"""更新包后台下载、取消、校验和完成状态管理。"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Dict, Optional

from PyQt6.QtCore import QObject, QThread, Qt, pyqtSignal
from PyQt6.QtWidgets import QApplication, QWidget

from core.update_utils import (
    DownloadCancelled,
    DownloadRetryExhausted,
    cleanup_incomplete_updates,
    discard_pending_update,
    discard_ready_update,
    download_with_progress,
    launch_self_update,
    load_pending_update,
    load_ready_update,
    save_pending_update,
    save_ready_update,
    sha256_file,
)
from utils.app_config import get_app_config
from utils.paths import get_update_dir


class UpdateDownloadWorker(QThread):
    """在独立线程中下载并校验更新包。"""

    progress_changed = pyqtSignal(int, int)
    phase_changed = pyqtSignal(str)
    download_completed = pyqtSignal(dict)
    download_cancelled = pyqtSignal()
    download_paused = pyqtSignal(str)
    download_failed = pyqtSignal(str)

    def __init__(
        self,
        manifest: Dict[str, Any],
        version: str,
        token: str,
        destination: Path,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self.manifest = dict(manifest)
        self.version = version
        self.token = token
        self.destination = destination
        self.partial_path = destination.with_suffix(destination.suffix + ".part")
        self._stop_event = threading.Event()
        self._stop_lock = threading.Lock()
        self._stop_mode: Optional[str] = None
        self._response_lock = threading.Lock()
        self._response = None
        self._retrying = False

    def cancel(self) -> None:
        """请求取消，并关闭网络响应以立即解除阻塞读取。"""
        self._request_stop("cancel")

    def pause(self) -> None:
        """请求暂停；停止网络读取但保留可续传临时文件。"""
        self._request_stop("pause")

    def _request_stop(self, mode: str) -> None:
        with self._stop_lock:
            # 显式取消优先于此前的暂停请求。
            if self._stop_mode != "cancel":
                self._stop_mode = mode
            self._stop_event.set()
        with self._response_lock:
            response = self._response
        if response is not None:
            try:
                response.close()
            except Exception:
                pass

    def _set_response(self, response) -> None:
        with self._response_lock:
            self._response = response
        if response is not None and self._stop_event.is_set():
            try:
                response.close()
            except Exception:
                pass

    def _is_stopped(self) -> bool:
        return self._stop_event.is_set()

    def _was_paused(self) -> bool:
        with self._stop_lock:
            return self._stop_mode == "pause"

    def _emit_progress(self, done: int, total: Optional[int]) -> None:
        if self._retrying:
            self._retrying = False
            self.phase_changed.emit("downloading")
        expected = int(self.manifest.get("size_bytes", 0) or 0)
        self.progress_changed.emit(int(done), int(total or expected or 0))

    def _emit_retry(self, attempt: int, retries: int, error: str) -> None:
        self._retrying = True
        self.phase_changed.emit(f"retrying:{attempt}:{retries}:{error}")

    def run(self) -> None:
        url = str(self.manifest.get("url", "")).strip()
        expected_hash = str(self.manifest.get("sha256", "")).strip().lower()
        expected_size = int(self.manifest.get("size_bytes", 0) or 0)
        try:
            if not url:
                raise RuntimeError("下载链接无效")
            self.destination.parent.mkdir(parents=True, exist_ok=True)

            self.phase_changed.emit("downloading")
            download_with_progress(
                url,
                self.partial_path,
                self.token or None,
                self._emit_progress,
                cancel_cb=self._is_stopped,
                response_cb=self._set_response,
                expected_size=expected_size,
                retries=3,
                retry_cb=self._emit_retry,
            )
            if self._is_stopped():
                raise DownloadCancelled("更新下载已停止")

            actual_size = self.partial_path.stat().st_size
            if expected_size > 0 and actual_size != expected_size:
                raise RuntimeError(
                    f"更新包大小不完整：期望 {expected_size} 字节，实际 {actual_size} 字节"
                )

            self.phase_changed.emit("verifying")
            actual_hash = sha256_file(
                self.partial_path,
                cancel_cb=self._is_stopped,
                progress_cb=lambda done, total: self.progress_changed.emit(done, total),
            ).lower()
            if expected_hash and actual_hash != expected_hash:
                raise RuntimeError("更新包 SHA256 校验失败")
            if self._is_stopped():
                raise DownloadCancelled("更新下载已停止")

            os.replace(self.partial_path, self.destination)
            metadata = save_ready_update(
                self.destination,
                self.version,
                actual_hash,
                expected_size or actual_size,
            )
            metadata["path"] = str(self.destination.resolve())
            self.download_completed.emit(metadata)
        except DownloadCancelled:
            if self._was_paused():
                self.download_paused.emit("更新下载已暂停")
            else:
                self.partial_path.unlink(missing_ok=True)
                discard_pending_update(self.destination.parent)
                self.download_cancelled.emit()
        except DownloadRetryExhausted as exc:
            self.download_paused.emit(
                f"网络连接不稳定，已保留下载进度：{exc}"
            )
        except Exception as exc:
            self.partial_path.unlink(missing_ok=True)
            if self._is_stopped():
                if self._was_paused():
                    self.download_paused.emit("更新下载已暂停")
                else:
                    discard_pending_update(self.destination.parent)
                    self.download_cancelled.emit()
            else:
                discard_pending_update(self.destination.parent)
                self.download_failed.emit(str(exc))
        finally:
            self._set_response(None)


class UpdateDownloadController(QObject):
    """应用级下载控制器，负责跨对话框保留下载状态。"""

    progress_changed = pyqtSignal(int, int)
    state_changed = pyqtSignal(str, str)
    download_completed = pyqtSignal(dict)

    ACTIVE_STATES = {
        "downloading",
        "retrying",
        "verifying",
        "pausing",
        "cancelling",
    }

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)
        self.state = "idle"
        self.message = ""
        self.downloaded = 0
        self.total = 0
        self._worker: Optional[UpdateDownloadWorker] = None
        self._progress_dialog = None
        self._manifest: Dict[str, Any] = {}
        self._version = ""
        self._token = ""
        self._destination: Optional[Path] = None
        cleanup_incomplete_updates()
        ready = load_ready_update()
        if ready:
            self.state = "ready"
            self.message = f"更新 v{ready['version']} 已下载"
            self.downloaded = int(ready.get("actual_size_bytes", 0) or 0)
            self.total = self.downloaded
        else:
            pending = load_pending_update()
            if pending:
                self._restore_pending(pending)
                self.state = "paused"
                self.message = "检测到未完成更新，可继续下载"

    @property
    def is_active(self) -> bool:
        return self.state in self.ACTIVE_STATES and self._worker is not None

    @property
    def has_download_task(self) -> bool:
        return self.is_active or self.state == "paused"

    def start(self, manifest: Dict[str, Any], version: str, token: str = "") -> bool:
        """启动新下载；同一任务存在临时文件时自动从断点继续。"""
        if self._worker is not None and self._worker.isRunning():
            return False
        ready = load_ready_update()
        if ready and str(ready.get("version")) == str(version):
            self._set_state("ready", f"更新 v{version} 已下载")
            return False
        if not re.fullmatch(r"[0-9A-Za-z._-]+", str(version)):
            self._set_state("failed", "更新版本号无效")
            return False

        pending = load_pending_update()
        same_pending = bool(
            pending
            and str(pending.get("version")) == str(version)
            and str(pending.get("manifest", {}).get("sha256", "")).lower()
            == str(manifest.get("sha256", "")).lower()
        )
        if pending and not same_pending:
            discard_pending_update()

        update_dir = get_update_dir()
        self._destination = (
            pending["path"]
            if same_pending
            else update_dir / f"ImageClassifier_v{version}.exe"
        )
        self._manifest = dict(manifest)
        self._version = str(version)
        self._token = token or ""
        partial_path = self._destination.with_suffix(
            self._destination.suffix + ".part"
        )
        self.downloaded = partial_path.stat().st_size if partial_path.is_file() else 0
        self.total = int(manifest.get("size_bytes", 0) or 0)
        save_pending_update(
            self._destination,
            self._version,
            self._manifest,
        )
        return self._start_worker()

    def _start_worker(self) -> bool:
        """根据控制器中保存的任务信息创建下载线程。"""
        if not self._destination or not self._manifest or not self._version:
            self._set_state("failed", "没有可继续的更新任务")
            return False
        if self._worker is not None and self._worker.isRunning():
            return False
        self._worker = UpdateDownloadWorker(
            self._manifest,
            self._version,
            self._token,
            self._destination,
            self,
        )
        self._worker.progress_changed.connect(self._on_progress)
        self._worker.phase_changed.connect(self._on_phase_changed)
        self._worker.download_completed.connect(self._on_completed)
        self._worker.download_cancelled.connect(self._on_cancelled)
        self._worker.download_paused.connect(self._on_paused)
        self._worker.download_failed.connect(self._on_failed)
        self._worker.finished.connect(self._on_worker_finished)
        message = "正在继续下载更新包..." if self.downloaded else "正在下载更新包..."
        self._set_state("downloading", message)
        self._worker.start()
        return True

    def _restore_pending(self, pending: Dict[str, Any]) -> None:
        """从持久化任务恢复控制器字段和进度。"""
        self._manifest = dict(pending.get("manifest", {}))
        self._version = str(pending.get("version", ""))
        self._destination = pending.get("path")
        self.downloaded = int(pending.get("downloaded_bytes", 0) or 0)
        self.total = int(self._manifest.get("size_bytes", 0) or 0)

    def resume(self) -> bool:
        """继续暂停或上次退出时保留的下载任务。"""
        if self._worker is not None and self._worker.isRunning():
            return False
        pending = load_pending_update()
        if not pending:
            self._set_state("failed", "未找到可继续的下载内容，请重新下载")
            return False
        self._restore_pending(pending)
        if not self._token:
            try:
                self._token = get_app_config().update_token or ""
            except Exception:
                self._token = ""
        return self._start_worker()

    def pause(self) -> None:
        """暂停当前下载并保留断点。"""
        if self._worker and self._worker.isRunning():
            self._set_state("pausing", "正在暂停下载...")
            self._worker.pause()

    def cancel(self) -> None:
        """取消当前下载，并删除断点和任务标记。"""
        if self._worker and self._worker.isRunning():
            self._set_state("cancelling", "正在取消下载...")
            self._worker.cancel()
        elif self.state == "paused":
            discard_pending_update()
            self.downloaded = 0
            self.total = 0
            self._set_state("cancelled", "更新下载已取消")

    def shutdown(self, timeout_ms: int = 10000) -> bool:
        """程序退出前暂停下载并等待句柄释放，保留续传断点。"""
        worker = self._worker
        if worker and worker.isRunning():
            if self.state == "cancelling":
                worker.cancel()
            elif self.state not in {"ready", "failed", "cancelled", "paused"}:
                self._set_state("pausing", "正在保存下载进度...")
                worker.pause()
            if not worker.wait(timeout_ms):
                return False
        cleanup_incomplete_updates()
        return True

    def show_progress_dialog(self, parent: Optional[QWidget] = None) -> None:
        """显示或重新打开下载进度入口。"""
        from .update_dialog import DownloadProgressDialog

        if self._progress_dialog is None:
            self._progress_dialog = DownloadProgressDialog(self, parent)
            self._progress_dialog.destroyed.connect(self._clear_progress_dialog)
        elif parent is not None and self._progress_dialog.parentWidget() is not parent:
            # 从设置页启动时挂到设置页上方；从状态栏重开时再挂回主窗口。
            self._progress_dialog.setParent(parent, Qt.WindowType.Dialog)
            self._progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self._progress_dialog.sync_from_controller()
        self._progress_dialog.show()
        self._progress_dialog.raise_()
        self._progress_dialog.activateWindow()

    def install_ready_update(self) -> bool:
        """启动持久化更新脚本并退出应用。"""
        ready = load_ready_update()
        if not ready:
            self._set_state("failed", "完整更新包不存在，请重新下载")
            return False
        package_path = ready["path"]
        target_exe = (
            Path(sys.executable)
            if getattr(sys, "frozen", False)
            else Path.cwd() / "ImageClassifier.exe"
        )
        batch_path = launch_self_update(target_exe, package_path)
        subprocess.Popen(
            ["cmd", "/c", "start", "", str(batch_path), str(package_path)],
            shell=False,
        )
        QApplication.quit()
        return True

    def discard_ready_update(self) -> None:
        discard_ready_update()
        self._set_state("idle", "")

    def _clear_progress_dialog(self, *_args) -> None:
        self._progress_dialog = None

    def _set_state(self, state: str, message: str) -> None:
        self.state = state
        self.message = message
        self.state_changed.emit(state, message)

    def _on_progress(self, done: int, total: int) -> None:
        self.downloaded = done
        if total > 0:
            self.total = total
        self.progress_changed.emit(self.downloaded, self.total)

    def _on_phase_changed(self, phase: str) -> None:
        if phase == "verifying":
            self._set_state("verifying", "正在校验更新包...")
        elif phase.startswith("retrying:"):
            parts = phase.split(":", 3)
            attempt = parts[1] if len(parts) > 1 else "?"
            retries = parts[2] if len(parts) > 2 else "?"
            self._set_state(
                "retrying",
                f"网络波动，正在自动重试（{attempt}/{retries}）...",
            )
        else:
            self._set_state("downloading", "正在下载更新包...")

    def _on_completed(self, metadata: Dict[str, Any]) -> None:
        self.downloaded = int(metadata.get("actual_size_bytes", self.total) or 0)
        self.total = self.downloaded
        version = metadata.get("version", "")
        self._set_state("ready", f"更新 v{version} 已下载")
        self.download_completed.emit(metadata)

    def _on_cancelled(self) -> None:
        discard_pending_update()
        self.downloaded = 0
        self.total = 0
        self._set_state("cancelled", "更新下载已取消")

    def _on_paused(self, message: str) -> None:
        pending = load_pending_update()
        if pending:
            self._restore_pending(pending)
        self._set_state("paused", message or "更新下载已暂停")

    def _on_failed(self, message: str) -> None:
        self.logger.error("更新下载失败: %s", message)
        discard_pending_update()
        self.downloaded = 0
        self.total = 0
        self._set_state("failed", message)

    def _on_worker_finished(self) -> None:
        worker = self.sender() or self._worker
        if worker is self._worker:
            self._worker = None
        if worker is not None:
            worker.deleteLater()


def get_update_download_controller() -> UpdateDownloadController:
    """获取绑定到 QApplication 生命周期的下载控制器单例。"""
    app = QApplication.instance()
    if app is None:
        raise RuntimeError("QApplication 尚未初始化")
    controller = getattr(app, "_update_download_controller", None)
    if controller is None:
        controller = UpdateDownloadController(app)
        app._update_download_controller = controller
    return controller
