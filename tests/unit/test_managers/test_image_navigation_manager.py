"""
ImageNavigationManager 单元测试
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
from PyQt6.QtCore import QObject
from PyQt6.QtWidgets import QListView

from ui.managers.image_navigation_manager import ImageNavigationManager
from ui.models.image_list_model import ImageListModel


class MockState:
    """Mock StateView"""
    def __init__(self):
        self.current_index = 0
        self.total_images = 0
        self.image_files = []
        self.all_image_files = []
        self.current_dir = None
        self.is_network_path = False
        # 添加config和app_config属性
        self.config = Mock()
        self.config.enable_loop_on_local_path = True
        self.config.enable_loop_on_network_path = False
        self.app_config = Mock()
        # 使用正确的属性名（_should_enable_loop使用的名称）
        self.app_config.local_loop_enabled = True
        self.app_config.network_loop_enabled = False

    def get_real_file_path(self, path):
        """Mock get_real_file_path方法"""
        return path


class MockMutator:
    """Mock StateMutator"""
    def __init__(self):
        self.updates = []

    def set_current_index(self, index: int):
        self.updates.append(('set_current_index', index))

    def set_image_files(self, files: list):
        self.updates.append(('set_image_files', files))

    def set_all_image_files(self, files: list):
        self.updates.append(('set_all_image_files', files))

    def set_total_images(self, total: int):
        self.updates.append(('set_total_images', total))

    def set_current_requested_image(self, path: str):
        self.updates.append(('set_current_requested_image', path))

    def set_classified_images(self, images: dict):
        self.updates.append(('set_classified_images', images))

    def set_removed_images(self, images: set):
        self.updates.append(('set_removed_images', images))


class StateUpdatingMutator(MockMutator):
    """模拟主窗口真实行为：修改索引时立即写回共享状态。"""

    def __init__(self, state: MockState):
        super().__init__()
        self.state = state

    def set_current_index(self, index: int):
        self.state.current_index = index
        super().set_current_index(index)


class MockUIHooks:
    """Mock UIHooks"""
    def __init__(self):
        self.calls = []

    def update_status_bar(self, message: str):
        self.calls.append(('update_status_bar', message))

    def schedule_ui_update(self, *components):
        self.calls.append(('schedule_ui_update', components))

    def show_toast(self, level: str, message: str):
        self.calls.append(('show_toast', level, message))

    def show_loading_placeholder(self, path=None):
        self.calls.append(('show_loading_placeholder', path))

    def update_window_title(self, path):
        self.calls.append(('update_window_title', path))

    def display_image(self, image_data, path):
        self.calls.append(('display_image', path))


@pytest.fixture
def mock_state():
    return MockState()


@pytest.fixture
def mock_mutator():
    return MockMutator()


@pytest.fixture
def mock_ui():
    return MockUIHooks()


@pytest.fixture
def mock_loader():
    loader = Mock()
    loader.load_image = Mock()
    loader.preload_images = Mock()
    loader.set_image_files_reference = Mock()
    return loader


@pytest.fixture
def mock_scanner():
    scanner = Mock()
    scanner.initial_batch_ready = Mock()
    scanner.files_found = Mock()
    scanner.scan_progress = Mock()
    scanner.scan_finished = Mock()
    # 添加 connect 方法
    scanner.initial_batch_ready.connect = Mock()
    scanner.files_found.connect = Mock()
    scanner.scan_progress.connect = Mock()
    scanner.scan_finished.connect = Mock()
    return scanner


@pytest.fixture
def manager(mock_state, mock_mutator, mock_ui, mock_loader, mock_scanner):
    """创建 ImageNavigationManager 实例"""
    return ImageNavigationManager(
        state=mock_state,
        mutator=mock_mutator,
        ui=mock_ui,
        loader=mock_loader,
        scanner=mock_scanner,
        image_list=None,
        image_list_model=None,
        get_visible_indices=lambda: None,
        get_original_to_filtered_index=lambda: None,
        is_network_path_callback=lambda x: False,  # 默认本地路径
        logger=None
    )


class TestImageNavigationManager:
    """ImageNavigationManager 单元测试"""

    # ========== 原有测试 ==========

    def test_keyboard_navigation_immediately_syncs_real_list_current_index(
        self,
        manager,
        mock_state,
        qapp,
    ):
        """快捷键翻页返回前，真实列表当前项应与业务索引保持一致。"""
        image_files = [Path(f"test_{index}.jpg") for index in range(100)]
        mock_state.image_files = image_files
        mock_state.current_index = 20
        manager._mutator = StateUpdatingMutator(mock_state)

        image_list = QListView()
        image_list.resize(320, 240)
        image_list_model = ImageListModel(
            [str(path) for path in image_files],
            {},
            set(),
            set(),
            image_list,
        )
        image_list.setModel(image_list_model)
        manager.set_ui_components(image_list, image_list_model)

        old_index = image_list_model.index(mock_state.current_index, 0)
        image_list.setCurrentIndex(old_index)
        image_list.show()
        qapp.processEvents()

        try:
            # 模拟快速前进后退：业务索引连续变化，但不等待 50ms 的同步定时器。
            for _ in range(10):
                manager.next_image()
            for _ in range(5):
                manager.prev_image()

            assert mock_state.current_index == 25
            assert (
                image_list.currentIndex().data(ImageListModel.ROLE_IMAGE_INDEX)
                == mock_state.current_index
            )
        finally:
            image_list.close()
            image_list.deleteLater()

    def test_immediate_sync_after_model_reset_restores_keyboard_target(
        self,
        manager,
        mock_state,
        qapp,
    ):
        """模型重置后立即同步，应恢复快捷键目标行并滚动到可见区域。"""
        image_files = [Path(f"test_{index}.jpg") for index in range(100)]
        mock_state.image_files = image_files
        mock_state.current_index = 20
        manager._mutator = StateUpdatingMutator(mock_state)

        image_list = QListView()
        image_list.resize(320, 120)
        image_list_model = ImageListModel(
            [str(path) for path in image_files],
            {},
            set(),
            set(),
            image_list,
        )
        image_list.setModel(image_list_model)
        manager.set_ui_components(image_list, image_list_model)

        old_index = image_list_model.index(mock_state.current_index, 0)
        image_list.setCurrentIndex(old_index)
        image_list.show()
        qapp.processEvents()

        try:
            for _ in range(10):
                manager.next_image()
            for _ in range(5):
                manager.prev_image()

            # 模拟分类时 apply_image_filter() 对列表模型的整体重置。
            image_list_model.update_data(
                [str(path) for path in image_files],
                {},
                set(),
                set(),
                list(range(len(image_files))),
            )

            # 修复路径：显示当前图片时立即以业务索引同步列表。
            manager.show_current_image()

            assert (
                image_list.currentIndex().data(ImageListModel.ROLE_IMAGE_INDEX)
                == mock_state.current_index
            )

            qapp.processEvents()
            target_rect = image_list.visualRect(image_list.currentIndex())
            assert image_list.viewport().rect().intersects(target_rect)
        finally:
            image_list.close()
            image_list.deleteLater()

    def test_rapid_navigation_coalesces_delayed_selection_sync(
        self,
        manager,
        mock_state,
        qtbot,
    ):
        """连续快捷键翻页应只保留最后一次 50ms 延迟校准。"""
        mock_state.image_files = [Path(f"test_{index}.jpg") for index in range(100)]
        mock_state.current_index = 20
        manager._mutator = StateUpdatingMutator(mock_state)
        timeout_observer = Mock()
        manager._selection_sync_timer.timeout.connect(timeout_observer)

        for _ in range(10):
            manager.next_image()

        assert manager._selection_sync_timer.isActive()
        assert timeout_observer.call_count == 0

        qtbot.wait(80)

        assert manager._selection_sync_timer.isActive() is False
        assert timeout_observer.call_count == 1

    @pytest.mark.parametrize(
        "row_count",
        [4000, 10000],
        ids=["4000_rows", "10000_rows"],
    )
    def test_batched_large_model_reset_schedules_final_viewport_sync(
        self,
        manager,
        mock_state,
        qapp,
        qtbot,
        row_count,
    ):
        """大列表模型重置后，应在 Batched 布局稳定时恢复目标视窗。"""
        image_files = [Path(f"test_{index:05d}.jpg") for index in range(row_count)]
        mock_state.image_files = image_files
        mock_state.current_index = row_count // 2
        manager._mutator = StateUpdatingMutator(mock_state)

        image_list = QListView()
        image_list.resize(360, 140)
        image_list.setUniformItemSizes(True)
        image_list.setLayoutMode(QListView.LayoutMode.Batched)
        image_list.setBatchSize(256)
        image_list_model = ImageListModel(
            [str(path) for path in image_files],
            {},
            set(),
            set(),
            image_list,
        )
        image_list.setModel(image_list_model)
        manager.set_ui_components(image_list, image_list_model)
        image_list.show()
        qapp.processEvents()

        try:
            image_list.setCurrentIndex(image_list_model.index(0, 0))
            image_list_model.update_data(
                [str(path) for path in image_files],
                {},
                set(),
                set(),
                list(range(row_count)),
            )

            assert manager._selection_sync_timer.isActive()

            def current_target_is_visible():
                current = image_list.currentIndex()
                if not current.isValid():
                    return False
                if (
                    current.data(ImageListModel.ROLE_IMAGE_INDEX)
                    != mock_state.current_index
                ):
                    return False
                return image_list.viewport().rect().intersects(
                    image_list.visualRect(current)
                )

            qtbot.waitUntil(current_target_is_visible, timeout=3000)
        finally:
            image_list.close()
            image_list.deleteLater()

    def test_scanner_signals_connected(self, manager, mock_scanner):
        """测试 scanner 信号是否正确连接"""
        # 验证4个信号都被连接
        assert mock_scanner.initial_batch_ready.connect.called
        assert mock_scanner.files_found.connect.called
        assert mock_scanner.scan_progress.connect.called
        assert mock_scanner.scan_finished.connect.called

    def test_on_initial_batch_ready_signal_emission(self, manager, qtbot, mock_state):
        """测试初始批次信号发射"""
        test_files = [Path(f"test_{i}.jpg") for i in range(5)]

        with qtbot.waitSignal(manager.list_updated, timeout=1000) as blocker:
            manager._loading_in_progress = True
            # 设置mock_state的image_files，因为信号发射的是state.image_files
            mock_state.image_files = test_files
            manager.on_initial_batch_ready(test_files)

        # 验证信号参数
        assert len(blocker.args[0]) == 5

    def test_on_scan_finished_updates_state(self, manager, mock_mutator, mock_state):
        """测试扫描完成时更新状态"""
        # 预设文件列表
        test_files = [Path(f"test_{i}.jpg") for i in range(10)]
        mock_state.image_files = test_files

        manager._background_loading = True
        manager.on_scan_finished(10)

        # 验证调用了 set_total_images，参数应该是去重后的数量
        assert ('set_total_images', 10) in mock_mutator.updates

    def test_on_scan_progress_emits_signal(self, manager, qtbot):
        """测试扫描进度信号转发"""
        with qtbot.waitSignal(manager.scan_progress, timeout=1000) as blocker:
            manager._on_scan_progress("扫描中...")

        assert blocker.args[0] == "扫描中..."

    # ========== 翻页功能测试 ==========

    def test_prev_image_normal(self, manager, mock_state, mock_mutator, qtbot):
        """测试正常上一张"""
        mock_state.current_index = 5
        mock_state.image_files = [Path(f"test_{i}.jpg") for i in range(10)]

        with patch.object(manager, 'show_current_image'):
            with qtbot.waitSignal(manager.image_changed, timeout=1000) as blocker:
                manager.prev_image()

        assert blocker.args[0] == 4
        assert ('set_current_index', 4) in mock_mutator.updates

    def test_next_image_normal(self, manager, mock_state, mock_mutator, qtbot):
        """测试正常下一张"""
        mock_state.current_index = 5
        mock_state.image_files = [Path(f"test_{i}.jpg") for i in range(10)]

        with patch.object(manager, 'show_current_image'):
            with qtbot.waitSignal(manager.image_changed, timeout=1000) as blocker:
                manager.next_image()

        assert blocker.args[0] == 6
        assert ('set_current_index', 6) in mock_mutator.updates

    def test_prev_image_at_first_with_loop(self, manager, mock_state, mock_mutator, qtbot):
        """测试第一张时上一张（循环到最后）"""
        mock_state.current_index = 0
        mock_state.image_files = [Path(f"test_{i}.jpg") for i in range(10)]
        mock_state.config.enable_loop_on_local_path = True

        with patch.object(manager, 'show_current_image'):
            with qtbot.waitSignal(manager.image_changed, timeout=1000) as blocker:
                manager.prev_image()

        # 应该循环到最后一张（索引9）
        assert blocker.args[0] == 9
        assert ('set_current_index', 9) in mock_mutator.updates

    def test_next_image_at_last_with_loop(self, manager, mock_state, mock_mutator, qtbot):
        """测试最后一张时下一张（循环到第一张）"""
        mock_state.current_index = 9
        mock_state.image_files = [Path(f"test_{i}.jpg") for i in range(10)]
        mock_state.config.enable_loop_on_local_path = True

        with patch.object(manager, 'show_current_image'):
            with qtbot.waitSignal(manager.image_changed, timeout=1000) as blocker:
                manager.next_image()

        # 应该循环到第一张（索引0）
        assert blocker.args[0] == 0
        assert ('set_current_index', 0) in mock_mutator.updates

    def test_prev_image_at_first_no_loop(self, manager, mock_state, mock_ui):
        """测试第一张时上一张（不循环，显示提示）"""
        mock_state.current_index = 0
        mock_state.image_files = [Path(f"test_{i}.jpg") for i in range(10)]
        mock_state.app_config.local_loop_enabled = False  # 使用正确的属性名

        manager.prev_image()

        # 应该显示toast提示
        assert ('show_toast', 'info', "已经是第一张图片了！") in mock_ui.calls

    def test_next_image_at_last_no_loop(self, manager, mock_state, mock_ui):
        """测试最后一张时下一张（不循环，显示提示）"""
        mock_state.current_index = 9
        mock_state.image_files = [Path(f"test_{i}.jpg") for i in range(10)]
        mock_state.app_config.local_loop_enabled = False  # 使用正确的属性名

        manager.next_image()

        # 应该显示toast提示
        assert ('show_toast', 'info', "已经是最后一张图片了！") in mock_ui.calls

    # ========== 跳转功能测试 ==========

    def test_jump_to_image_valid_index(self, manager, mock_state, mock_mutator, qtbot):
        """测试跳转到有效索引"""
        mock_state.current_index = 0
        mock_state.image_files = [Path(f"test_{i}.jpg") for i in range(10)]

        with patch.object(manager, 'show_current_image'):
            with qtbot.waitSignal(manager.image_changed, timeout=1000) as blocker:
                manager.jump_to_image(5)

        assert blocker.args[0] == 5
        assert ('set_current_index', 5) in mock_mutator.updates

    def test_jump_to_image_invalid_index(self, manager, mock_state, mock_mutator):
        """测试跳转到无效索引"""
        mock_state.image_files = [Path(f"test_{i}.jpg") for i in range(10)]
        initial_updates_count = len(mock_mutator.updates)

        # 不应该抛出异常
        manager.jump_to_image(-1)
        manager.jump_to_image(100)

        # 不应该有新的set_current_index调用
        assert len(mock_mutator.updates) == initial_updates_count

    # ========== 过滤模式导航测试 ==========

    def test_prev_image_with_filter(self, manager, mock_state, mock_mutator, qtbot):
        """测试过滤模式下的上一张"""
        mock_state.current_index = 5
        mock_state.image_files = [Path(f"test_{i}.jpg") for i in range(10)]
        # Mock过滤后的可见索引：[2, 5, 7]
        manager._get_visible_indices = Mock(return_value=[2, 5, 7])

        with patch.object(manager, 'show_current_image'):
            with qtbot.waitSignal(manager.image_changed, timeout=1000) as blocker:
                manager.prev_image()

        # 应该跳到索引2（上一个可见项）
        assert blocker.args[0] == 2
        assert ('set_current_index', 2) in mock_mutator.updates

    def test_next_image_with_filter(self, manager, mock_state, mock_mutator, qtbot):
        """测试过滤模式下的下一张"""
        mock_state.current_index = 5
        mock_state.image_files = [Path(f"test_{i}.jpg") for i in range(10)]
        # Mock过滤后的可见索引：[2, 5, 7]
        manager._get_visible_indices = Mock(return_value=[2, 5, 7])

        with patch.object(manager, 'show_current_image'):
            with qtbot.waitSignal(manager.image_changed, timeout=1000) as blocker:
                manager.next_image()

        # 应该跳到索引7（下一个可见项）
        assert blocker.args[0] == 7
        assert ('set_current_index', 7) in mock_mutator.updates

    def test_navigation_with_empty_filter(self, manager, mock_state, mock_ui):
        """测试过滤结果为空时的导航"""
        mock_state.current_index = 5
        mock_state.image_files = [Path(f"test_{i}.jpg") for i in range(10)]
        manager._get_visible_indices = Mock(return_value=[])  # 过滤结果为空

        manager.prev_image()

        # 应该显示提示
        assert ('show_toast', 'info', "当前过滤条件下没有图片") in mock_ui.calls

    def test_prev_image_filter_loop_to_last(self, manager, mock_state, mock_mutator, qtbot):
        """测试过滤模式下第一张循环到最后"""
        mock_state.current_index = 2  # 当前在第一个可见项
        mock_state.image_files = [Path(f"test_{i}.jpg") for i in range(10)]
        mock_state.config.enable_loop_on_local_path = True
        manager._get_visible_indices = Mock(return_value=[2, 5, 7])

        with patch.object(manager, 'show_current_image'):
            with qtbot.waitSignal(manager.image_changed, timeout=1000) as blocker:
                manager.prev_image()

        # 应该循环到最后一个可见项（索引7）
        assert blocker.args[0] == 7
        assert ('set_current_index', 7) in mock_mutator.updates

    # ========== 删除后导航测试 ==========

    def test_select_after_removal_with_filter(self, manager, mock_state, mock_mutator):
        """测试过滤模式下删除后的智能选择"""
        original_index = 5
        mock_state.current_index = 5
        mock_state.image_files = [Path(f"test_{i}.jpg") for i in range(9)]  # 删除后9张
        # Mock删除后的可见索引：[2, 6, 7]（原索引5的图片已删除）
        manager._get_visible_indices = Mock(return_value=[2, 6, 7])

        with patch.object(manager, 'show_current_image'):
            manager.select_after_removal(original_index)

        # 应该选择索引6（删除位置后的第一个可见项）
        assert ('set_current_index', 6) in mock_mutator.updates

    def test_select_after_removal_no_filter(self, manager, mock_state, mock_mutator):
        """测试无过滤模式下删除后的选择"""
        original_index = 5
        mock_state.current_index = 5
        mock_state.image_files = [Path(f"test_{i}.jpg") for i in range(9)]  # 删除后还有9张

        with patch.object(manager, 'show_current_image'):
            manager.select_after_removal(original_index)

        # image_files 保留原始索引，应该显式选择下一张（索引6）
        assert ('set_current_index', 6) in mock_mutator.updates

    def test_select_after_removal_last_image(self, manager, mock_state, mock_mutator):
        """测试删除最后一张后的选择"""
        original_index = 9
        mock_state.current_index = 9
        mock_state.image_files = [Path(f"test_{i}.jpg") for i in range(9)]  # 删除后9张（0-8）

        with patch.object(manager, 'show_current_image'):
            manager.select_after_removal(original_index)

        # 应该选择索引8（新的最后一张）
        assert ('set_current_index', 8) in mock_mutator.updates

    # ========== 边界条件测试 ==========

    def test_prev_image_empty_list(self, manager, mock_state):
        """测试空列表时上一张"""
        mock_state.image_files = []
        mock_state.current_index = -1

        # 不应该抛出异常
        manager.prev_image()

    def test_next_image_empty_list(self, manager, mock_state):
        """测试空列表时下一张"""
        mock_state.image_files = []
        mock_state.current_index = -1

        # 不应该抛出异常
        manager.next_image()

    def test_network_path_loop_disabled(self, manager, mock_state, mock_ui):
        """测试网络路径默认禁用循环"""
        mock_state.current_index = 0
        mock_state.image_files = [Path(f"test_{i}.jpg") for i in range(10)]
        mock_state.is_network_path = True  # 设置为网络路径
        mock_state.app_config.network_loop_enabled = False  # 使用正确的属性名

        manager.prev_image()

        # 应该显示提示，不循环
        assert ('show_toast', 'info', "已经是第一张图片了！") in mock_ui.calls

    # ========== 新增测试：第一组 - 状态管理与扫描流程 ==========

    def test_load_images_resets_state_and_calls_scan(self, mock_state, mock_mutator,
                                                      mock_ui, mock_loader, mock_scanner):
        """测试 load_images 重置状态并调用扫描"""
        # 前置：设置当前目录
        mock_state.current_dir = Path("/test/images")

        # 创建 manager
        manager = ImageNavigationManager(
            state=mock_state,
            mutator=mock_mutator,
            ui=mock_ui,
            loader=mock_loader,
            scanner=mock_scanner,
            image_list=None,
            image_list_model=None,
            get_visible_indices=lambda: None,
            get_original_to_filtered_index=lambda: None,
            is_network_path_callback=lambda x: False,
            logger=None
        )

        # 执行
        manager.load_images()

        # 验证：清理缓存
        mock_loader.clear_cache.assert_called_once()

        # 验证：状态重置（检查 mutator 调用）
        mutator_calls = [call[0] for call in mock_mutator.updates]
        assert 'set_current_index' in mutator_calls
        # 找到 set_current_index 的参数
        for call in mock_mutator.updates:
            if call[0] == 'set_current_index':
                assert call[1] == -1  # 索引重置为 -1

        # 验证：调用 scanner.scan_directory
        mock_scanner.scan_directory.assert_called_once_with(mock_state.current_dir)

    def test_load_images_no_current_dir_returns(self, mock_state, mock_mutator,
                                                 mock_ui, mock_loader, mock_scanner):
        """测试无目录时 load_images 直接返回"""
        # 前置：无当前目录
        mock_state.current_dir = None

        manager = ImageNavigationManager(
            state=mock_state,
            mutator=mock_mutator,
            ui=mock_ui,
            loader=mock_loader,
            scanner=mock_scanner,
            image_list=None,
            image_list_model=None,
            get_visible_indices=lambda: None,
            get_original_to_filtered_index=lambda: None,
            is_network_path_callback=lambda x: False,
            logger=None
        )

        # 执行
        manager.load_images()

        # 验证：scanner 和 loader 未被调用
        mock_scanner.scan_directory.assert_not_called()
        mock_loader.clear_cache.assert_not_called()

    def test_on_initial_batch_ready_sets_loader_reference_and_emits(
        self, manager, mock_state, mock_mutator, mock_loader, qtbot
    ):
        """测试首批文件处理：设置 loader 引用并发射信号"""
        test_files = [Path(f"test_{i}.jpg") for i in range(5)]

        # 前置：设置 loading 标志 + 设置 state.image_files（信号发射时会用到）
        manager._loading_in_progress = True
        mock_state.image_files = test_files  # 关键：信号发射的是 state.image_files

        # 执行并等待信号
        with qtbot.waitSignal(manager.list_updated, timeout=1000) as blocker:
            manager.on_initial_batch_ready(test_files)

        # 验证：mutator 调用
        assert ('set_image_files', test_files) in mock_mutator.updates
        assert ('set_all_image_files', test_files) in mock_mutator.updates
        assert ('set_current_index', 0) in mock_mutator.updates

        # 验证：loader 引用设置
        mock_loader.set_image_files_reference.assert_called_once_with(test_files)

        # 验证：loading 标志重置
        assert manager._loading_in_progress is False

        # 验证：信号参数（信号发射的是 state.image_files，所以应该是5）
        assert len(blocker.args[0]) == 5

    def test_on_initial_batch_ready_ignored_when_not_loading(
        self, manager, mock_mutator, mock_loader
    ):
        """测试非 loading 状态时忽略首批文件"""
        test_files = [Path(f"test_{i}.jpg") for i in range(5)]

        # 前置：loading 标志为 False
        manager._loading_in_progress = False

        initial_updates_count = len(mock_mutator.updates)

        # 执行
        manager.on_initial_batch_ready(test_files)

        # 验证：mutator 和 loader 未被调用
        assert len(mock_mutator.updates) == initial_updates_count
        mock_loader.set_image_files_reference.assert_not_called()

    def test_on_files_found_appends_unique_and_sets_reference(
        self, manager, mock_state, mock_mutator, mock_loader, qtbot
    ):
        """测试增量文件处理：去重追加并设置引用"""
        # 前置：已有文件 a
        existing_file = Path("test_a.jpg")
        mock_state.image_files = [existing_file]
        mock_state.all_image_files = [existing_file]
        manager._background_loading = True

        # 执行：新增 a 和 b（a 是重复的）
        new_files = [existing_file, Path("test_b.jpg")]
        with qtbot.waitSignal(manager.list_updated, timeout=1000):
            manager.on_files_found(new_files)

        # 验证：只追加了 b（去重生效）
        set_image_files_calls = [call for call in mock_mutator.updates
                                 if call[0] == 'set_image_files']
        # 最后一次调用应该包含 [a, b]
        assert len(set_image_files_calls) > 0
        last_files = set_image_files_calls[-1][1]
        assert len(last_files) == 2
        assert Path("test_b.jpg") in last_files

        # 验证：调用了 set_image_files_reference
        assert mock_loader.set_image_files_reference.call_count >= 1

    def test_on_files_found_skipped_when_not_background(
        self, manager, mock_mutator, mock_loader
    ):
        """测试非后台加载时忽略增量文件"""
        # 前置：background_loading 为 False
        manager._background_loading = False

        initial_updates_count = len(mock_mutator.updates)
        new_files = [Path("test_a.jpg"), Path("test_b.jpg")]

        # 执行
        manager.on_files_found(new_files)

        # 验证：mutator 和 loader 未被调用
        assert len(mock_mutator.updates) == initial_updates_count
        mock_loader.set_image_files_reference.assert_not_called()

    def test_on_scan_finished_dedup_and_total(
        self, manager, mock_state, mock_mutator, mock_loader, qtbot
    ):
        """测试扫描完成：去重并设置 total"""
        # 前置：image_files 包含重复
        duplicate_files = [Path("a.jpg"), Path("a.jpg"), Path("b.jpg")]
        mock_state.image_files = duplicate_files.copy()
        mock_state.all_image_files = duplicate_files.copy()
        manager._background_loading = True

        # 执行
        with qtbot.waitSignal(manager.scan_completed, timeout=1000) as blocker:
            manager.on_scan_finished(3)

        # 验证：去重调用（set_image_files 和 set_all_image_files）
        set_calls = [call for call in mock_mutator.updates
                     if call[0] in ['set_image_files', 'set_all_image_files']]
        assert len(set_calls) >= 2

        # 验证：set_total_images 被调用（去重后数量）
        total_calls = [call for call in mock_mutator.updates
                       if call[0] == 'set_total_images']
        assert len(total_calls) > 0
        # 最后一次应该是去重后的数量（2）
        assert total_calls[-1][1] == 2

        # 验证：loader 引用设置
        mock_loader.set_image_files_reference.assert_called()

        # 验证：scan_completed 信号参数
        assert blocker.args[0] == 2  # 去重后的数量

    # ========== 新增测试：第二组 - 缓存与显示逻辑 ==========

    def test_show_current_image_cached_hit_path(
        self, manager, mock_state, mock_mutator, mock_ui
    ):
        """测试缓存命中时的显示流程"""
        # 前置：设置当前状态
        test_path = Path("test_0.jpg")
        mock_state.current_index = 0
        mock_state.image_files = [test_path]
        mock_state.get_real_file_path = Mock(return_value=str(test_path))

        # Mock loader 缓存命中
        manager._loader.is_cached = Mock(return_value=True)
        cached_data = Mock()  # 模拟缓存的图片数据
        manager._loader._get_from_cache = Mock(return_value=cached_data)

        # 执行
        manager.show_current_image()

        # 验证：设置 current_requested_image（这是show_current_image实际做的）
        requested_calls = [call for call in mock_mutator.updates
                          if call[0] == 'set_current_requested_image']
        assert len(requested_calls) > 0

        # 验证：显示图片（缓存命中）- display_calls[0][1] 实际是 Path 对象
        display_calls = [call for call in mock_ui.calls
                        if call[0] == 'display_image']
        assert len(display_calls) == 1
        # 比较路径的字符串形式
        assert str(display_calls[0][1]) == str(test_path)

        # 验证：仍然调用 load_image（priority加载）
        manager._loader.load_image.assert_called_once()
        assert manager._loader.load_image.call_args[1]['priority'] is True

    def test_show_current_image_cache_miss_placeholder_and_load(
        self, manager, mock_state, mock_mutator, mock_ui
    ):
        """测试缓存未命中时显示占位符并加载"""
        # 前置：设置当前状态
        test_path = Path("test_0.jpg")
        mock_state.current_index = 0
        mock_state.image_files = [test_path]
        mock_state.get_real_file_path = Mock(return_value=str(test_path))

        # Mock loader 缓存未命中
        manager._loader.is_cached = Mock(return_value=False)

        # 执行
        manager.show_current_image()

        # 验证：显示占位符
        placeholder_calls = [call for call in mock_ui.calls
                            if call[0] == 'show_loading_placeholder']
        assert len(placeholder_calls) == 1

        # 验证：调用 loader.load_image
        manager._loader.load_image.assert_called_once()
        assert manager._loader.load_image.call_args[1]['priority'] is True

        # 验证：设置 current_requested_image
        requested_calls = [call for call in mock_mutator.updates
                          if call[0] == 'set_current_requested_image']
        assert len(requested_calls) > 0

    def test_show_current_image_invalid_index_shows_placeholder(
        self, manager, mock_state, mock_ui
    ):
        """测试无效索引时显示占位符"""
        # 前置：无效索引
        mock_state.current_index = -1
        mock_state.image_files = []

        # 执行
        manager.show_current_image()

        # 验证：显示占位符
        placeholder_calls = [call for call in mock_ui.calls
                            if call[0] == 'show_loading_placeholder']
        assert len(placeholder_calls) == 1

        # 验证：loader.load_image 未被调用
        manager._loader.load_image.assert_not_called()

    # ========== 新增测试：第三组 - 过滤导航与索引映射 ==========

    def test_prev_next_filtered_not_in_visible_pick_nearest(
        self, manager, mock_state, mock_mutator, qtbot
    ):
        """测试当前索引不在可见列表时选择最近的项"""
        # 前置：current_index=5, 可见索引=[1, 3, 7]
        mock_state.current_index = 5
        mock_state.image_files = [Path(f"test_{i}.jpg") for i in range(10)]
        manager._get_visible_indices = Mock(return_value=[1, 3, 7])

        with patch.object(manager, 'show_current_image'):
            # 测试 prev（应该选择 3）
            with qtbot.waitSignal(manager.image_changed, timeout=1000) as blocker:
                manager.prev_image()
            assert blocker.args[0] == 3
            assert ('set_current_index', 3) in mock_mutator.updates

            # 重置状态
            mock_state.current_index = 5
            mock_mutator.updates.clear()

            # 测试 next（应该选择 7）
            with qtbot.waitSignal(manager.image_changed, timeout=1000) as blocker:
                manager.next_image()
            assert blocker.args[0] == 7
            assert ('set_current_index', 7) in mock_mutator.updates

    def test_prev_next_filtered_empty_toast(self, manager, mock_state, mock_ui):
        """测试过滤结果为空时显示提示"""
        # 前置：可见索引为空
        mock_state.current_index = 5
        mock_state.image_files = [Path(f"test_{i}.jpg") for i in range(10)]
        manager._get_visible_indices = Mock(return_value=[])

        # 测试 prev
        manager.prev_image()
        assert ('show_toast', 'info', "当前过滤条件下没有图片") in mock_ui.calls

        # 清理并测试 next
        mock_ui.calls.clear()
        manager.next_image()
        assert ('show_toast', 'info', "当前过滤条件下没有图片") in mock_ui.calls

    def test_sync_image_list_selection_filtered_mapping(self, manager, mock_state):
        """测试索引映射与列表选择同步"""
        # 前置：设置 image_list（必须）+ model 和 selectionModel
        mock_image_list = Mock()
        mock_selection_model = Mock()
        mock_image_list.selectionModel = Mock(return_value=mock_selection_model)
        mock_image_list.scrollTo = Mock()

        # 创建 Mock index
        mock_index = Mock()
        mock_index.isValid = Mock(return_value=True)

        mock_model = Mock()
        mock_model.index = Mock(return_value=mock_index)

        manager._image_list = mock_image_list  # 关键：必须设置 image_list
        manager._image_list_model = mock_model

        # 场景1：映射存在 - original_index=5 映射到 filtered_index=1
        mock_state.current_index = 5
        manager._get_original_to_filtered_index = Mock(return_value={5: 1})

        manager.sync_image_list_selection()

        # 验证：使用 filtered index (1) 进行选择
        assert mock_selection_model.setCurrentIndex.called

        # 场景2：映射不存在 - 应该清空选择
        mock_selection_model.reset_mock()
        manager._get_original_to_filtered_index = Mock(return_value={})

        manager.sync_image_list_selection()

        # 验证：清空选择
        assert mock_selection_model.clearSelection.called

    def test_select_after_removal_filtered_choose_next_then_prev(
        self, manager, mock_state, mock_mutator, qtbot
    ):
        """测试删除后智能选择：优先下一个，不存在则上一个"""
        # 前置：visible_indices=[2, 6], original_index=4
        mock_state.image_files = [Path(f"test_{i}.jpg") for i in range(8)]
        manager._get_visible_indices = Mock(return_value=[2, 6])

        with patch.object(manager, 'show_current_image'):
            # 场景1：删除索引4，应该选择6（下一个可见项）
            with qtbot.waitSignal(manager.image_changed, timeout=1000) as blocker:
                manager.select_after_removal(4)
            assert blocker.args[0] == 6
            assert ('set_current_index', 6) in mock_mutator.updates

            # 场景2：visible_indices=[2], 删除索引5，应该选择2（上一个可见项）
            mock_mutator.updates.clear()
            manager._get_visible_indices = Mock(return_value=[2])

            with qtbot.waitSignal(manager.image_changed, timeout=1000) as blocker:
                manager.select_after_removal(5)
            assert blocker.args[0] == 2
            assert ('set_current_index', 2) in mock_mutator.updates

            # 场景3：visible_indices=[], 应该设置为-1并显示提示
            mock_mutator.updates.clear()
            mock_state.image_files = []
            manager._get_visible_indices = Mock(return_value=[])

            manager.select_after_removal(0)
            assert ('set_current_index', -1) in mock_mutator.updates

    # ========== 新增测试：第四组 - 预加载与配置 ==========

    def test_should_enable_loop_network_vs_local(self, manager, mock_state):
        """测试网络路径和本地路径的循环配置区分"""
        # 场景1：本地路径 - 使用 local_loop_enabled
        mock_state.is_network_path = False
        mock_state.app_config.local_loop_enabled = True
        mock_state.app_config.network_loop_enabled = False

        result = manager._should_enable_loop()
        assert result is True

        # 场景2：网络路径 - 使用 network_loop_enabled
        mock_state.is_network_path = True
        mock_state.app_config.local_loop_enabled = True
        mock_state.app_config.network_loop_enabled = False

        result = manager._should_enable_loop()
        assert result is False

        # 场景3：网络路径开启循环
        mock_state.app_config.network_loop_enabled = True

        result = manager._should_enable_loop()
        assert result is True

    def test_jump_to_image_invalid_index_no_exception(self, manager, mock_state, mock_mutator):
        """测试跳转到无效索引不抛出异常且记录日志"""
        # 前置
        mock_state.image_files = [Path(f"test_{i}.jpg") for i in range(10)]
        initial_updates_count = len(mock_mutator.updates)

        # 执行：负数索引
        manager.jump_to_image(-1)

        # 验证：没有状态更新
        assert len(mock_mutator.updates) == initial_updates_count

        # 执行：超出范围索引
        manager.jump_to_image(100)

        # 验证：没有状态更新
        assert len(mock_mutator.updates) == initial_updates_count

    def test_preload_adjacent_images_direction_forward_local_range(
        self, manager, mock_state, mock_loader
    ):
        """测试前向预加载（本地路径）的范围计算"""
        # 前置：50张图片，本地路径，前向历史，当前索引10
        mock_state.image_files = [Path(f"test_{i}.jpg") for i in range(50)]
        mock_state.current_index = 10
        mock_state.is_network_path = False

        # 设置前向历史（3次前进）- _user_behavior 是字典
        manager._user_behavior['direction_history'] = [1, 1, 1]

        # 执行
        manager.preload_adjacent_images()

        # 验证：调用 preload_images
        assert mock_loader.preload_images.called

        # 验证：预加载范围（本地：前10后40）
        call_args = mock_loader.preload_images.call_args[0][0]
        assert len(call_args) > 0  # 有预加载项
        # 验证包含前面和后面的图片（不包含当前）
        assert Path("test_10.jpg") not in call_args  # 不包含当前
        # 前向历史应该预加载更多后面的图片
        assert any(int(p.stem.split('_')[1]) > 10 for p in call_args)

    def test_preload_adjacent_images_backward_network_range(
        self, manager, mock_state, mock_loader
    ):
        """测试后向预加载（网络路径）的范围计算"""
        # 前置：30张图片，网络路径，后向历史，当前索引20
        mock_state.image_files = [Path(f"test_{i}.jpg") for i in range(30)]
        mock_state.current_index = 20
        mock_state.is_network_path = True

        # 设置后向历史（3次后退）- _user_behavior 是字典
        manager._user_behavior['direction_history'] = [-1, -1, -1]

        # 执行
        manager.preload_adjacent_images()

        # 验证：调用 preload_images
        assert mock_loader.preload_images.called

        # 验证：预加载范围（网络：前10后3）
        call_args = mock_loader.preload_images.call_args[0][0]
        assert len(call_args) > 0
        # 验证不包含当前
        assert Path("test_20.jpg") not in call_args
        # 后向历史应该预加载更多前面的图片
        assert any(int(p.stem.split('_')[1]) < 20 for p in call_args)
        # 网络路径预加载数量应该较少（约10-13张）
        assert len(call_args) < 20  # 网络路径预加载较少

    # ========== 新增测试：第五组 - 并发安全 ==========

    def test_show_current_image_reentrancy_guard(self, manager, mock_state):
        """测试 show_current_image 的防重入保护"""
        # 前置：设置当前状态
        test_path = Path("test_0.jpg")
        mock_state.current_index = 0
        mock_state.image_files = [test_path]

        # 设置重入标志
        manager._showing_image = True

        # Mock _show_current_image_internal
        manager._show_current_image_internal = Mock()

        # 执行
        manager.show_current_image()

        # 验证：内部方法未被调用（被防重入保护阻止）
        manager._show_current_image_internal.assert_not_called()

        # 重置标志并再次执行
        manager._showing_image = False
        manager.show_current_image()

        # 验证：这次应该调用了
        manager._show_current_image_internal.assert_called_once()

    def test_on_scan_progress_forward_signal(self, manager, mock_ui, qtbot):
        """测试扫描进度信号转发"""
        test_message = "正在扫描图片... (123/500)"

        # 执行并等待信号
        with qtbot.waitSignal(manager.scan_progress, timeout=1000) as blocker:
            manager._on_scan_progress(test_message)

        # 验证：信号参数正确
        assert blocker.args[0] == test_message

        # 验证：调用 UI 更新状态栏
        assert ('update_status_bar', test_message) in mock_ui.calls
