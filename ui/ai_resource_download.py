"""Background downloads for optional AI runtime and model resources."""

from __future__ import annotations

import time
from typing import Dict, Optional

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from core.ai.resource_manager import (
    AIResourceSpec,
    download_and_install_resource,
)
from core.update_utils import DownloadCancelled
from utils.app_config import get_app_config


class AIResourceDownloadThread(QThread):
    """Download, verify, and install one AI resource off the UI thread."""

    progress_changed = pyqtSignal(int, int)
    status_changed = pyqtSignal(str)
    installed = pyqtSignal(object)
    failed = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self, resource: AIResourceSpec, parent=None) -> None:
        super().__init__(parent)
        self.resource = resource

    def run(self) -> None:
        try:
            proxy = (
                get_app_config().update_proxy
                if "github.com" in self.resource.url
                else ""
            )
            download_and_install_resource(
                self.resource,
                progress_cb=lambda done, total: self.progress_changed.emit(
                    int(done), int(total or self.resource.size_bytes)
                ),
                cancel_cb=self.isInterruptionRequested,
                status_cb=self.status_changed.emit,
                proxy=proxy,
            )
        except DownloadCancelled:
            self.cancelled.emit()
        except Exception as error:
            self.failed.emit(str(error))
        else:
            self.installed.emit(self.resource)


class AIResourceDownloadManager(QObject):
    """Own AI downloads independently from any configuration dialog.

    The main window owns one manager for the whole application lifetime.  A
    configuration dialog merely observes its snapshots, so closing the dialog
    never destroys or silently cancels an in-progress download.
    """

    resource_state_changed = pyqtSignal(str, object)
    resource_installed = pyqtSignal(object)
    resource_failed = pyqtSignal(object, str)
    resource_cancelled = pyqtSignal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._workers: Dict[str, AIResourceDownloadThread] = {}
        self._states: Dict[str, dict] = {}

    def snapshot(self, resource_or_key) -> Optional[dict]:
        """Return a copy of the latest state for one resource."""
        key = getattr(resource_or_key, "key", resource_or_key)
        state = self._states.get(str(key))
        return dict(state) if state is not None else None

    def is_active(self, resource_or_key) -> bool:
        key = str(getattr(resource_or_key, "key", resource_or_key))
        worker = self._workers.get(key)
        return bool(worker is not None and worker.isRunning())

    @property
    def has_active_downloads(self) -> bool:
        return any(worker.isRunning() for worker in self._workers.values())

    def start(self, resource: AIResourceSpec) -> bool:
        """Start a resource download, or keep observing an existing one."""
        if self.is_active(resource):
            return False

        worker = AIResourceDownloadThread(resource, self)
        state = {
            "key": resource.key,
            "resource": resource,
            "state": "downloading",
            "done": 0,
            "total": int(resource.size_bytes),
            "status": f"正在下载 {resource.display_name}…",
            "error": "",
        }
        self._states[resource.key] = state
        self._workers[resource.key] = worker
        worker.progress_changed.connect(
            lambda done, total, key=resource.key: self._on_progress(
                key, done, total
            )
        )
        worker.status_changed.connect(
            lambda status, key=resource.key: self._on_status(key, status)
        )
        worker.installed.connect(self._on_installed)
        worker.failed.connect(
            lambda error, current=resource: self._on_failed(current, error)
        )
        worker.cancelled.connect(
            lambda current=resource: self._on_cancelled(current)
        )
        worker.finished.connect(
            lambda key=resource.key, current=worker: self._on_finished(
                key, current
            )
        )
        self._emit_state(resource.key)
        worker.start()
        return True

    def cancel(self, resource_or_key) -> None:
        """Explicitly pause one download; closing a dialog does not call this."""
        key = str(getattr(resource_or_key, "key", resource_or_key))
        worker = self._workers.get(key)
        if worker is not None and worker.isRunning():
            worker.requestInterruption()

    def shutdown(self, timeout_ms: int = 10000) -> bool:
        """Stop downloads when the whole application exits."""
        workers = tuple(self._workers.values())
        for worker in workers:
            if worker.isRunning():
                worker.requestInterruption()
        deadline = time.monotonic() + max(0, timeout_ms) / 1000
        for worker in workers:
            if not worker.isRunning():
                continue
            remaining_ms = max(0, int((deadline - time.monotonic()) * 1000))
            if not worker.wait(remaining_ms):
                return False
        return True

    def _emit_state(self, key: str) -> None:
        snapshot = self.snapshot(key)
        if snapshot is not None:
            self.resource_state_changed.emit(key, snapshot)

    def _on_progress(self, key: str, done: int, total: int) -> None:
        state = self._states.get(key)
        if state is None:
            return
        state.update(
            done=int(done),
            total=int(total or state.get("total") or 0),
        )
        self._emit_state(key)

    def _on_status(self, key: str, status: str) -> None:
        state = self._states.get(key)
        if state is None:
            return
        state["status"] = status
        state["state"] = "installing" if "安装" in status else "downloading"
        self._emit_state(key)

    def _on_installed(self, resource: AIResourceSpec) -> None:
        state = self._states.get(resource.key)
        if state is not None:
            state.update(
                state="installed",
                done=int(resource.size_bytes),
                total=int(resource.size_bytes),
                status=f"{resource.display_name}下载并安装完成",
                error="",
            )
            self._emit_state(resource.key)
        self.resource_installed.emit(resource)

    def _on_failed(self, resource: AIResourceSpec, error: str) -> None:
        state = self._states.get(resource.key)
        if state is not None:
            state.update(
                state="failed",
                status=f"{resource.display_name}下载失败",
                error=str(error),
            )
            self._emit_state(resource.key)
        self.resource_failed.emit(resource, str(error))

    def _on_cancelled(self, resource: AIResourceSpec) -> None:
        state = self._states.get(resource.key)
        if state is not None:
            state.update(
                state="cancelled",
                status="下载已暂停，下次会从断点继续。",
            )
            self._emit_state(resource.key)
        self.resource_cancelled.emit(resource)

    def _on_finished(
        self, key: str, worker: AIResourceDownloadThread
    ) -> None:
        if self._workers.get(key) is worker:
            self._workers.pop(key, None)
        worker.deleteLater()
        self._emit_state(key)
