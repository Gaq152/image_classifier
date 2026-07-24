"""大列表快速分类与图片列表视窗同步回归测试。"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from PyQt6.QtWidgets import QListView

from ui.managers.file_operation_manager import FileOperationManager
from ui.managers.image_navigation_manager import ImageNavigationManager
from ui.main_window import ImageClassifier
from ui.models.image_list_model import ImageListModel


class LargeListState:
    """提供分类和导航测试所需的共享状态。"""

    def __init__(self, image_files):
        self.current_dir = image_files[0].parent
        self.image_files = image_files
        self.all_image_files = list(image_files)
        self.current_index = 0
        self.total_images = len(image_files)
        self.classified_images = {}
        self.removed_images = set()
        self.categories = {"category1"}
        self.ordered_categories = ["category1"]
        self.is_copy_mode = True
        self.is_multi_category = False
        self.is_network_path = False
        self.config = Mock()
        self.app_config = Mock()
        self.app_config.local_loop_enabled = False
        self.app_config.network_loop_enabled = False

    def get_real_file_path(self, path):
        return Path(path)


class LargeListMutator:
    """将 Manager 的状态修改立即写回共享状态。"""

    def __init__(self, state):
        self.state = state

    def set_current_index(self, index):
        self.state.current_index = index

    def set_classified_image(self, path, category):
        self.state.classified_images[path] = category

    def remove_classified_image(self, path):
        self.state.classified_images.pop(path, None)

    def remove_from_removed(self, path):
        self.state.removed_images.discard(path)

    def set_current_requested_image(self, path):
        self.state.current_requested_image = path


class LargeListUI:
    """模拟主窗口；若过滤被调用，则真实重置列表模型。"""

    def __init__(self, state, model):
        self.state = state
        self.model = model
        self.filter_apply_count = 0

    def is_image_filter_active(self):
        return False

    def apply_image_filter(self, suppress_show=False):
        self.filter_apply_count += 1
        self.model.update_data(
            [str(path) for path in self.state.image_files],
            self.state.classified_images,
            self.state.removed_images,
            set(),
            list(range(len(self.state.image_files))),
        )

    def save_state(self):
        pass

    def schedule_ui_update(self, *_components):
        pass

    def refresh_category_buttons_style(self):
        pass

    def update_window_title(self, _path):
        pass

    def update_status_bar(self, _message):
        pass

    def show_loading_placeholder(self):
        pass

    def display_image(self, _image_data, _path):
        pass

    def show_toast(self, _level, _message):
        pass


class IncrementalFilterUI(LargeListUI):
    """复用主窗口真实增量筛选逻辑，避免测试替身掩盖模型重置。"""

    def __init__(self, state, model):
        super().__init__(state, model)
        self.image_files = state.image_files
        self.image_list_model = model
        self.classified_images = state.classified_images
        self.removed_images = state.removed_images
        self.categories = state.categories
        self.filter_unclassified = True
        self.filter_classified = False
        self.filter_removed = False
        self._image_search_text = ""
        self._visible_indices = list(range(len(state.image_files)))
        self._original_to_filtered_index = {
            index: index for index in self._visible_indices
        }

    @property
    def current_index(self):
        return self.state.current_index

    def is_image_filter_active(self):
        return ImageClassifier.is_image_filter_active(self)

    def refresh_image_filter_path(self, path):
        return ImageClassifier.refresh_image_filter_path(self, path)


def create_scanner_mock():
    """创建带 Qt 风格信号接口的扫描器替身。"""
    scanner = Mock()
    scanner.initial_batch_ready.connect = Mock()
    scanner.files_found.connect = Mock()
    scanner.scan_progress.connect = Mock()
    scanner.scan_finished.connect = Mock()
    return scanner


@pytest.mark.parametrize(
    "row_count",
    [4000, 10000],
    ids=["4000_rows", "10000_rows"],
)
def test_rapid_classification_does_not_reset_or_lose_large_list_viewport(
    qapp,
    qtbot,
    tmp_path,
    row_count,
):
    """默认全部显示时，连续分类不应重置 4 千或 1 万行列表。"""
    image_dir = tmp_path / "images"
    image_files = [
        image_dir / f"image_{index:05d}.jpg"
        for index in range(row_count)
    ]
    state = LargeListState(image_files)
    mutator = LargeListMutator(state)

    image_list = QListView()
    image_list.resize(360, 140)
    image_list.setUniformItemSizes(True)
    image_list.setLayoutMode(QListView.LayoutMode.SinglePass)
    image_list_model = ImageListModel(
        [str(path) for path in image_files],
        {},
        set(),
        set(),
        image_list,
    )
    image_list.setModel(image_list_model)
    image_list.show()

    ui = LargeListUI(state, image_list_model)
    loader = Mock()
    loader.is_cached.return_value = False
    navigator = ImageNavigationManager(
        state=state,
        mutator=mutator,
        ui=ui,
        loader=loader,
        scanner=create_scanner_mock(),
        image_list=image_list,
        image_list_model=image_list_model,
        get_visible_indices=lambda: None,
        get_original_to_filtered_index=lambda: None,
        is_network_path_callback=lambda _path: False,
    )
    file_ops = FileOperationManager(
        state=state,
        mutator=mutator,
        ui=ui,
        navigator=navigator,
    )

    reset_count = 0

    def record_model_reset():
        nonlocal reset_count
        reset_count += 1

    image_list_model.modelReset.connect(record_model_reset)
    start_index = row_count // 2
    state.current_index = start_index
    navigator.sync_image_list_selection()
    qapp.processEvents()

    try:
        with patch.object(file_ops, '_execute_file_operation_with_check'):
            for _ in range(20):
                current_path = str(state.image_files[state.current_index])
                file_ops.move_to_category(current_path, "category1")

        assert state.current_index == start_index + 20
        assert reset_count == 0
        assert ui.filter_apply_count == 0

        def current_target_is_visible():
            current = image_list.currentIndex()
            if not current.isValid():
                return False
            if current.data(ImageListModel.ROLE_IMAGE_INDEX) != state.current_index:
                return False
            return image_list.viewport().rect().intersects(
                image_list.visualRect(current)
            )

        qtbot.waitUntil(current_target_is_visible, timeout=3000)
    finally:
        image_list.close()
        image_list.deleteLater()
        file_ops.deleteLater()
        navigator.deleteLater()


@pytest.mark.parametrize(
    "row_count",
    [4000, 10000],
    ids=["4000_rows_filtered", "10000_rows_filtered"],
)
def test_rapid_filtered_classification_updates_rows_without_blank_reset(
    qapp,
    qtbot,
    tmp_path,
    row_count,
):
    """只看未分类图片时，连续分类应逐行移除且保持视窗稳定。"""
    image_dir = tmp_path / "images"
    image_files = [
        image_dir / f"image_{index:05d}.jpg"
        for index in range(row_count)
    ]
    state = LargeListState(image_files)
    mutator = LargeListMutator(state)

    image_list = QListView()
    image_list.resize(360, 180)
    image_list.setUniformItemSizes(True)
    image_list.setLayoutMode(QListView.LayoutMode.SinglePass)
    image_list_model = ImageListModel(
        [str(path) for path in image_files],
        {},
        set(),
        set(),
        image_list,
    )
    image_list.setModel(image_list_model)
    image_list.show()

    ui = IncrementalFilterUI(state, image_list_model)
    loader = Mock()
    loader.is_cached.return_value = False
    navigator = ImageNavigationManager(
        state=state,
        mutator=mutator,
        ui=ui,
        loader=loader,
        scanner=create_scanner_mock(),
        image_list=image_list,
        image_list_model=image_list_model,
        get_visible_indices=lambda: ui._visible_indices,
        get_original_to_filtered_index=lambda: ui._original_to_filtered_index,
        is_network_path_callback=lambda _path: False,
    )
    file_ops = FileOperationManager(
        state=state,
        mutator=mutator,
        ui=ui,
        navigator=navigator,
    )

    reset_count = 0
    removed_count = 0

    def record_model_reset():
        nonlocal reset_count
        reset_count += 1

    def record_row_removed(*_args):
        nonlocal removed_count
        removed_count += 1

    image_list_model.modelReset.connect(record_model_reset)
    image_list_model.rowsRemoved.connect(record_row_removed)
    start_index = row_count // 2
    state.current_index = start_index
    navigator.sync_image_list_selection()

    try:
        qtbot.waitUntil(
            lambda: (
                image_list.currentIndex().isValid()
                and image_list.viewport().rect().intersects(
                    image_list.visualRect(image_list.currentIndex())
                )
            ),
            timeout=3000,
        )
        scrollbar_values = []

        with patch.object(file_ops, '_execute_file_operation_with_check'):
            for iteration in range(40):
                current_path = str(state.image_files[state.current_index])
                file_ops.move_to_category(current_path, "category1")
                qapp.processEvents()
                scrollbar_values.append(image_list.verticalScrollBar().value())

                current = image_list.currentIndex()
                assert current.isValid()
                assert (
                    current.data(ImageListModel.ROLE_IMAGE_INDEX)
                    == state.current_index
                )
                current_rect = image_list.visualRect(current)
                assert image_list.viewport().rect().intersects(current_rect), (
                    iteration,
                    state.current_index,
                    current.row(),
                    image_list.verticalScrollBar().value(),
                    current_rect,
                )

        assert state.current_index == start_index + 40
        assert reset_count == 0
        assert removed_count == 40
        assert image_list_model.rowCount() == row_count - 40
        assert ui.filter_apply_count == 0
        assert min(scrollbar_values) > 0
    finally:
        image_list.close()
        image_list.deleteLater()
        file_ops.deleteLater()
        navigator.deleteLater()
