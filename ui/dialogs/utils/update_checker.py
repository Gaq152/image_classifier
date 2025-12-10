"""
更新检查线程

统一的后台更新检查实现，供主窗口和设置对话框共用。
从 ui/dialogs.py 和 ui/main_window.py 合并而来。
"""

import logging
from PyQt6.QtCore import QThread, pyqtSignal
from core.update_utils import fetch_manifest


class UpdateCheckerThread(QThread):
    """后台检查更新的线程，避免阻塞UI

    信号:
        check_success: 检查成功时发射，携带 (manifest字典, endpoint, token)
        check_failed: 检查失败时发射，携带 (错误信息)

    用法:
        checker = UpdateCheckerThread(endpoint, token)
        checker.check_success.connect(on_success)
        checker.check_failed.connect(on_failed)
        checker.start()
    """

    # 信号：检查成功 (manifest字典, endpoint, token)
    check_success = pyqtSignal(dict, str, str)
    # 信号：检查失败 (错误信息)
    check_failed = pyqtSignal(str)

    def __init__(self, endpoint: str, token: str = None):
        """初始化更新检查线程

        Args:
            endpoint: 更新服务器地址
            token: 可选的认证令牌
        """
        super().__init__()
        self.endpoint = endpoint
        self.token = token
        self.logger = logging.getLogger(__name__)

    def run(self):
        """在后台线程中执行更新检查"""
        try:
            self.logger.debug(f"[后台更新检查] 开始检查: {self.endpoint}")
            manifest = fetch_manifest(self.endpoint, self.token or None)
            self.logger.debug(f"[后台更新检查] 检查成功: v{manifest.get('version', 'unknown')}")
            # 发送成功信号
            self.check_success.emit(manifest, self.endpoint, self.token or '')
        except Exception as e:
            self.logger.debug(f"[后台更新检查] 检查失败: {e}")
            # 发送失败信号
            self.check_failed.emit(str(e))
