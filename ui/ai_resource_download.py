"""Background downloads for optional AI runtime and model resources."""

from PyQt6.QtCore import QThread, pyqtSignal

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
