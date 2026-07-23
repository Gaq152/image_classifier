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
    cleanup_incomplete_updates,
    discard_ready_update,
    download_with_progress,
    launch_self_update,
    load_ready_update,
    save_ready_update,
    sha256_file,
)
from utils.paths import get_update_dir


class UpdateDownloadWorker(QThread):
    """在独立线程中下载并校验更新包。"""

    progress_changed = pyqtSignal(int, int)
    phase_changed = pyqtSignal(str)
    download_completed = pyqtSignal(dict)
    download_cancelled = pyqtSignal()
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
        self._cancel_event = threading.Event()
        self._response_lock = threading.Lock()
        self._response = None

    def cancel(self) -> None:
        """请求取消，并关闭网络响应以立即解除阻塞读取。"""
        self._cancel_event.set()
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
        if response is not None and self._cancel_event.is_set():
            try:
                response.close()
            except Exception:
                pass

    def _is_cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def _emit_progress(self, done: int, total: Optional[int]) -> None:
        expected = int(self.manifest.get("size_bytes", 0) or 0)
        self.progress_changed.emit(int(done), int(total or expected or 0))

    def run(self) -> None:
        url = str(self.manifest.get("url", "")).strip()
        expected_hash = str(self.manifest.get("sha256", "")).strip().lower()
        expected_size = int(self.manifest.get("size_bytes", 0) or 0)
        try:
            if not url:
                raise RuntimeError("下载链接无效")
            self.destination.parent.mkdir(parents=True, exist_ok=True)
            self.partial_path.unlink(missing_ok=True)

            self.phase_changed.emit("downloading")
            download_with_progress(
                url,
                self.partial_path,
                self.token or None,
                self._emit_progress,
                cancel_cb=self._is_cancelled,
                response_cb=self._set_response,
            )
            if self._is_cancelled():
                raise DownloadCancelled("更新下载已取消")

            actual_size = self.partial_path.stat().st_size
            if expected_size > 0 and actual_size != expected_size:
                raise RuntimeError(
                    f"更新包大小不完整：期望 {expected_size} 字节，实际 {actual_size} 字节"
                )

            self.phase_changed.emit("verifying")
            actual_hash = sha256_file(
                self.partial_path,
                cancel_cb=self._is_cancelled,
                progress_cb=lambda done, total: self.progress_changed.emit(done, total),
            ).lower()
            if expected_hash and actual_hash != expected_hash:
                raise RuntimeError("更新包 SHA256 校验失败")
            if self._is_cancelled():
                raise DownloadCancelled("更新下载已取消")

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
            self.partial_path.unlink(missing_ok=True)
            self.download_cancelled.emit()
        except Exception as exc:
            self.partial_path.unlink(missing_ok=True)
            if self._is_cancelled():
                self.download_cancelled.emit()
            else:
                self.download_failed.emit(str(exc))
        finally:
            self._set_response(None)


class UpdateDownloadController(QObject):
    """应用级下载控制器，负责跨对话框保留下载状态。"""

    progress_changed = pyqtSignal(int, int)
    state_changed = pyqtSignal(str, str)
    download_completed = pyqtSignal(dict)

    ACTIVE_STATES = {"downloading", "verifying", "cancelling"}

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)
        self.state = "idle"
        self.message = ""
        self.downloaded = 0
        self.total = 0
        self._worker: Optional[UpdateDownloadWorker] = None
        self._progress_dialog = None
        cleanup_incomplete_updates()
        ready = load_ready_update()
        if ready:
            self.state = "ready"
            self.message = f"更新 v{ready['version']} 已下载"

    @property
    def is_active(self) -> bool:
        return self.state in self.ACTIVE_STATES and self._worker is not None

    def start(self, manifest: Dict[str, Any], version: str, token: str = "") -> bool:
        """启动新下载；已有下载或同版本完整包时不重复启动。"""
        if self._worker is not None and self._worker.isRunning():
            return False
        ready = load_ready_update()
        if ready and str(ready.get("version")) == str(version):
            self._set_state("ready", f"更新 v{version} 已下载")
            return False
        if not re.fullmatch(r"[0-9A-Za-z._-]+", str(version)):
            self._set_state("failed", "更新版本号无效")
            return False

        update_dir = get_update_dir()
        destination = update_dir / f"ImageClassifier_v{version}.exe"
        self.downloaded = 0
        self.total = int(manifest.get("size_bytes", 0) or 0)
        self._worker = UpdateDownloadWorker(
            manifest,
            str(version),
            token,
            destination,
            self,
        )
        self._worker.progress_changed.connect(self._on_progress)
        self._worker.phase_changed.connect(self._on_phase_changed)
        self._worker.download_completed.connect(self._on_completed)
        self._worker.download_cancelled.connect(self._on_cancelled)
        self._worker.download_failed.connect(self._on_failed)
        self._worker.finished.connect(self._on_worker_finished)
        self._set_state("downloading", "正在下载更新包...")
        self._worker.start()
        return True

    def cancel(self) -> None:
        """取消当前下载。"""
        if self._worker and self._worker.isRunning():
            self._set_state("cancelling", "正在取消下载...")
            self._worker.cancel()

    def shutdown(self, timeout_ms: int = 10000) -> bool:
        """程序退出前停止下载并等待文件及网络句柄释放。"""
        worker = self._worker
        if worker and worker.isRunning():
            self.cancel()
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
        else:
            self._set_state("downloading", "正在下载更新包...")

    def _on_completed(self, metadata: Dict[str, Any]) -> None:
        self.downloaded = int(metadata.get("actual_size_bytes", self.total) or 0)
        self.total = self.downloaded
        version = metadata.get("version", "")
        self._set_state("ready", f"更新 v{version} 已下载")
        self.download_completed.emit(metadata)

    def _on_cancelled(self) -> None:
        self._set_state("cancelled", "更新下载已取消")

    def _on_failed(self, message: str) -> None:
        self.logger.error("更新下载失败: %s", message)
        self._set_state("failed", message)

    def _on_worker_finished(self) -> None:
        worker = self._worker
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
