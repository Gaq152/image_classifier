"""
测试配置文件（pytest）

提供测试 fixtures 和通用配置。
"""

import pytest
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer
from unittest.mock import Mock, MagicMock
import numpy as np

@pytest.fixture(scope="session")
def qapp():
    """提供全局 QApplication 实例"""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app
    # 不关闭，让 pytest 管理生命周期

@pytest.fixture
def tmp_image_dir(tmp_path):
    """创建临时图片目录"""
    image_dir = tmp_path / "test_images"
    image_dir.mkdir()
    return image_dir

@pytest.fixture
def test_categories(tmp_path):
    """创建测试类别目录"""
    categories = ['cat1', 'cat2', 'cat3']
    for cat in categories:
        (tmp_path / cat).mkdir()
    return categories

@pytest.fixture
def mock_qtimer(monkeypatch):
    """Mock QTimer.singleShot 为立即执行，避免异步等待"""
    def immediate_call(interval, callback):
        callback()
    monkeypatch.setattr(QTimer, "singleShot", immediate_call)
    return immediate_call

@pytest.fixture
def make_test_images(tmp_path):
    """创建测试图片文件的工厂函数"""
    def _make(count=10, prefix="test", extension=".jpg", subdir=None):
        """创建指定数量的测试图片文件

        Args:
            count: 图片数量
            prefix: 文件名前缀
            extension: 文件扩展名
            subdir: 子目录名称（可选）

        Returns:
            List[Path]: 图片路径列表
        """
        base_dir = tmp_path / subdir if subdir else tmp_path
        base_dir.mkdir(exist_ok=True, parents=True)

        images = []
        for i in range(count):
            img_path = base_dir / f"{prefix}_{i}{extension}"
            # 创建空文件
            img_path.touch()
            images.append(img_path)
        return images
    return _make

@pytest.fixture
def mock_readonly_file(tmp_path):
    """创建只读文件的工厂函数"""
    def _make(filename="readonly.jpg"):
        """创建只读文件

        Args:
            filename: 文件名

        Returns:
            Path: 只读文件路径
        """
        file_path = tmp_path / filename
        file_path.touch()
        # 设置为只读（Windows: 去掉写权限）
        import stat
        file_path.chmod(stat.S_IREAD)
        return file_path
    return _make

@pytest.fixture
def enhanced_mock_loader():
    """增强版 ImageLoader Mock，支持缓存操作"""
    loader = Mock()
    loader.load_image = Mock()
    loader.preload_images = Mock()
    loader.set_image_files_reference = Mock()
    loader.set_current_image_index = Mock()
    loader.clear_cache = Mock()

    # 缓存相关
    loader.is_cached = Mock(return_value=False)
    loader._get_from_cache = Mock(return_value=None)

    # 模拟缓存数据（numpy数组）
    def get_cached_image():
        return np.zeros((100, 100, 3), dtype=np.uint8)
    loader.get_cached_image = get_cached_image

    return loader

@pytest.fixture
def enhanced_mock_scanner():
    """增强版 Scanner Mock，支持所有信号和方法"""
    scanner = Mock()

    # 方法
    scanner.scan_directory = Mock()
    scanner.cancel_scan = Mock()

    # 信号（需要支持 connect 和 emit）
    for signal_name in ['initial_batch_ready', 'files_found', 'scan_progress',
                        'scan_finished', 'scan_error']:
        signal = MagicMock()
        signal.connect = Mock()
        signal.emit = Mock()
        setattr(scanner, signal_name, signal)

    return scanner

@pytest.fixture
def mock_image_list():
    """Mock ImageList Widget"""
    image_list = Mock()
    image_list.count = Mock(return_value=0)
    image_list.currentRow = Mock(return_value=-1)
    image_list.setCurrentRow = Mock()
    image_list.scrollToItem = Mock()
    return image_list

@pytest.fixture
def mock_image_list_model():
    """Mock ImageList Model"""
    model = Mock()
    model.rowCount = Mock(return_value=0)

    # selectionModel
    selection_model = Mock()
    selection_model.setCurrentIndex = Mock()
    selection_model.clearSelection = Mock()
    model.selectionModel = Mock(return_value=selection_model)

    return model

@pytest.fixture
def real_image_files(tmp_path):
    """创建真实的测试图片文件"""
    def _make(count=5, prefix="test_image"):
        """创建指定数量的测试图片文件

        Args:
            count: 图片数量
            prefix: 文件名前缀

        Returns:
            List[Path]: 图片文件路径列表
        """
        images = []
        for i in range(count):
            img_path = tmp_path / f"{prefix}_{i:03d}.jpg"
            # 创建小的空文件模拟图片
            img_path.write_bytes(b'fake_image_data')
            images.append(img_path)
        return images
    return _make

@pytest.fixture
def fake_scanner():
    """创建简化的 FakeScanner，支持基本信号"""
    from PyQt6.QtCore import QObject, pyqtSignal
    from pathlib import Path

    class FakeScanner(QObject):
        """简化的扫描器，用于集成测试"""
        initial_batch_ready = pyqtSignal(list)
        files_found = pyqtSignal(list)
        scan_progress = pyqtSignal(str)
        scan_finished = pyqtSignal(int)
        scan_error = pyqtSignal(str)

        def __init__(self):
            super().__init__()
            self.is_scanning = False

        def scan_directory(self, directory: Path):
            """模拟扫描目录"""
            self.is_scanning = True
            # 实际的集成测试会手动触发信号

        def cancel_scan(self):
            """取消扫描"""
            self.is_scanning = False

    return FakeScanner()
