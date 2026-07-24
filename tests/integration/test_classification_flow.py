"""
分类流程集成测试
"""

from pathlib import Path
from unittest.mock import Mock

from ui.managers.file_operation_manager import FileOperationManager


class MutableState:
    """分类流程所需的最小可变状态。"""

    def __init__(self, current_dir: Path, image_path: Path):
        self.current_dir = current_dir
        self.current_index = 0
        self.image_files = [image_path]
        self.is_copy_mode = True
        self.is_multi_category = False
        self.classified_images = {}
        self.removed_images = set()

    def get_real_file_path(self, path: Path) -> Path:
        """测试中不存在虚拟路径，直接返回原路径。"""
        return path


class StateMutator:
    """将 Manager 的状态修改写回测试状态。"""

    def __init__(self, state: MutableState):
        self.state = state

    def set_classified_image(self, path: str, category: str) -> None:
        self.state.classified_images[path] = category

    def remove_classified_image(self, path: str) -> None:
        self.state.classified_images.pop(path, None)


class TestUIHooks:
    """记录分类流程触发的 UI 回调。"""

    __test__ = False

    def __init__(self):
        self.saved = False
        self.updated_components = ()

    def save_state(self) -> None:
        self.saved = True

    def schedule_ui_update(self, *components: str) -> None:
        self.updated_components = components

    def refresh_category_buttons_style(self) -> None:
        pass

    def apply_image_filter(self, suppress_show: bool = False) -> None:
        pass


class TestClassificationFlow:
    """测试完整的分类流程"""

    def test_basic_classification(self, tmp_path):
        """测试基本分类流程：扫描 → 浏览 → 分类"""
        image_dir = tmp_path / "images"
        category_dir = tmp_path / "cat1"
        image_dir.mkdir()
        category_dir.mkdir()
        image_path = image_dir / "sample.jpg"
        image_path.write_bytes(b"test-image")

        state = MutableState(image_dir, image_path)
        mutator = StateMutator(state)
        ui = TestUIHooks()
        navigator = Mock()
        manager = FileOperationManager(
            state=state,
            mutator=mutator,
            ui=ui,
            navigator=navigator,
            logger=None,
        )
        moved_events = []
        manager.file_moved.connect(
            lambda source, target: moved_events.append((source, target))
        )

        manager.move_to_category(str(image_path), "cat1")

        copied_path = category_dir / image_path.name
        assert image_path.exists()
        assert copied_path.read_bytes() == b"test-image"
        assert state.classified_images[str(image_path)] == "cat1"
        assert ui.saved is True
        assert "category_counts" in ui.updated_components
        navigator.next_image.assert_called_once_with()
        assert moved_events == [(str(image_path), str(copied_path))]
