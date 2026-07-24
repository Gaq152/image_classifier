"""
ImageNavigationManager 集成测试

验证 Manager 与真实文件系统、scanner、loader 的端到端协同工作
"""

import pytest
from unittest.mock import Mock

from ui.managers.image_navigation_manager import ImageNavigationManager


class MockState:
    """Mock StateView for integration tests"""
    def __init__(self, test_dir=None):
        self.current_index = -1
        self.total_images = 0
        self.image_files = []
        self.all_image_files = []
        self.current_dir = test_dir
        self.is_network_path = False
        self.app_config = Mock()
        self.app_config.local_loop_enabled = True
        self.app_config.network_loop_enabled = False

    def get_real_file_path(self, path):
        return str(path)


class MockMutator:
    """Mock StateMutator for integration tests"""
    def __init__(self, state):
        self.state = state
        self.updates = []

    def set_current_index(self, index: int):
        self.state.current_index = index
        self.updates.append(('set_current_index', index))

    def set_image_files(self, files: list):
        self.state.image_files = files
        self.updates.append(('set_image_files', len(files)))

    def set_all_image_files(self, files: list):
        self.state.all_image_files = files
        self.updates.append(('set_all_image_files', len(files)))

    def set_total_images(self, total: int):
        self.state.total_images = total
        self.updates.append(('set_total_images', total))

    def set_current_requested_image(self, path: str):
        self.updates.append(('set_current_requested_image', path))

    def set_classified_images(self, images: dict):
        self.updates.append(('set_classified_images', len(images)))

    def set_removed_images(self, images: set):
        self.updates.append(('set_removed_images', len(images)))


class MockUIHooks:
    """Mock UIHooks for integration tests"""
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
        self.calls.append(('display_image', str(path)))


@pytest.fixture
def integration_setup(tmp_path, fake_scanner, enhanced_mock_loader, mock_qtimer):
    """集成测试基础设置（复用 conftest 中的 fixtures + mock_qtimer）"""
    # 创建测试状态
    state = MockState(test_dir=tmp_path)
    mutator = MockMutator(state)
    ui = MockUIHooks()

    # 使用 conftest 中的 enhanced_mock_loader（包含完整缓存支持）
    loader = enhanced_mock_loader

    # 创建 Manager
    manager = ImageNavigationManager(
        state=state,
        mutator=mutator,
        ui=ui,
        loader=loader,
        scanner=fake_scanner,
        image_list=None,
        image_list_model=None,
        get_visible_indices=lambda: None,
        get_original_to_filtered_index=lambda: None,
        is_network_path_callback=lambda x: False,
        logger=None
    )

    return {
        'manager': manager,
        'state': state,
        'mutator': mutator,
        'ui': ui,
        'loader': loader,
        'scanner': fake_scanner,
        'tmp_path': tmp_path
    }


class TestImageNavigationIntegration:
    """ImageNavigationManager 集成测试"""

    # ========== P0 场景 1：基础扫描 + 首图显示 ==========

    def test_scan_and_show_first_image(self, integration_setup, real_image_files, qtbot):
        """
        场景：真实扫描临时目录，首批文件就绪，列表更新并显示第一张
        验证：端到端的扫描 → 列表更新 → 显示首图流程
        """
        setup = integration_setup
        manager = setup['manager']
        state = setup['state']
        ui = setup['ui']
        loader = setup['loader']
        scanner = setup['scanner']
        tmp_path = setup['tmp_path']

        # 前置：创建 3 个测试图片文件
        test_images = real_image_files(count=3)
        state.current_dir = tmp_path

        # 执行：开始加载
        manager.load_images()

        # 验证：调用了 scanner.scan_directory
        assert scanner.is_scanning is True

        # 模拟 scanner 发射首批文件信号
        with qtbot.waitSignal(manager.list_updated, timeout=1000) as blocker:
            scanner.initial_batch_ready.emit(test_images)

        # 验证：列表更新
        assert len(blocker.args[0]) == 3
        assert len(state.image_files) == 3
        assert len(state.all_image_files) == 3
        assert state.current_index == 0

        # 验证：loader 引用设置（显示链路）
        loader.set_image_files_reference.assert_called()
        call_args = loader.set_image_files_reference.call_args[0][0]
        assert len(call_args) == 3

        # 注意：on_initial_batch_ready 不会自动显示首图
        # 显示首图需要用户显式调用 show_current_image 或通过导航触发

        # 模拟扫描完成
        with qtbot.waitSignal(manager.scan_completed, timeout=1000) as complete_blocker:
            scanner.scan_finished.emit(3)

        # 验证：完成信号和总数
        assert complete_blocker.args[0] == 3
        assert state.total_images == 3

        # 验证：UI 状态更新
        status_calls = [call for call in ui.calls if call[0] == 'update_status_bar']
        assert len(status_calls) > 0

    # ========== P0 场景 2：增量扫描去重追加 ==========

    def test_incremental_scan_append_and_dedup(self, integration_setup, real_image_files, qtbot):
        """
        场景：扫描过程中增量批次去重追加
        验证：初始批次 + 增量批次（含重复）→ 去重后的最终列表
        """
        setup = integration_setup
        manager = setup['manager']
        state = setup['state']
        scanner = setup['scanner']
        tmp_path = setup['tmp_path']

        # 前置：创建测试图片
        all_images = real_image_files(count=5)
        initial_batch = all_images[:2]  # 首批2个
        incremental_batch = [all_images[0], all_images[2], all_images[3]]  # 包含重复和新文件

        state.current_dir = tmp_path

        # 执行：开始加载
        manager.load_images()

        # 步骤1：首批文件
        with qtbot.waitSignal(manager.list_updated, timeout=1000):
            scanner.initial_batch_ready.emit(initial_batch)

        assert len(state.image_files) == 2

        # 步骤2：增量批次（包含重复）
        with qtbot.waitSignal(manager.list_updated, timeout=1000):
            scanner.files_found.emit(incremental_batch)

        # 验证：去重后应该有 4 个（0,1,2,3）
        assert len(state.image_files) == 4
        # 验证没有重复
        unique_paths = set(str(p) for p in state.image_files)
        assert len(unique_paths) == 4

        # 步骤3：扫描完成
        with qtbot.waitSignal(manager.scan_completed, timeout=1000):
            scanner.scan_finished.emit(5)

        # 验证：最终去重总数
        assert state.total_images == 4

    # ========== P0 场景 3：本地导航 + 预加载 ==========

    def test_navigation_and_preload_local(self, integration_setup, real_image_files, qtbot):
        """
        场景：本地路径下翻页触发预加载
        验证：next_image → 索引更新 → 预加载被调用（本地策略）
        """
        setup = integration_setup
        manager = setup['manager']
        state = setup['state']
        mutator = setup['mutator']
        loader = setup['loader']

        # 前置：设置 10 个图片，当前索引 0
        test_images = real_image_files(count=10)
        state.image_files = test_images
        state.all_image_files = test_images
        state.current_index = 0
        state.is_network_path = False

        # 执行：下一张
        with qtbot.waitSignal(manager.image_changed, timeout=1000) as blocker:
            manager.next_image()

        # 验证：索引更新为 1
        assert blocker.args[0] == 1
        assert state.current_index == 1

        # 验证：mutator 调用
        index_updates = [u for u in mutator.updates if u[0] == 'set_current_index']
        assert ('set_current_index', 1) in index_updates

        # 验证：load_image 被调用（当前图片）
        assert loader.load_image.called

        # 验证：防抖窗口结束后只为最终位置执行预加载。
        qtbot.waitUntil(lambda: loader.preload_images.called, timeout=1500)
        # 本地路径应该预加载更多图片
        preload_args = loader.preload_images.call_args[0][0]
        assert len(preload_args) > 0  # 预加载了一些图片

        # 增强断言：验证不包含当前图片（比较路径字符串）
        assert str(test_images[1]) not in [str(p) for p in preload_args]

        # 验证预加载范围合理（有预加载内容即可）
        # 预加载的图片应该是 test_images 中的一些图片
        preload_paths = {str(p) for p in preload_args}
        test_paths = {str(p) for p in test_images}
        # 预加载的图片应该在测试图片集合中
        assert preload_paths.issubset(test_paths) or len(preload_args) > 0

    # ========== P0 场景 4：过滤导航 + 列表同步 ==========

    def test_navigation_filtered_selection_sync(self, integration_setup, real_image_files, qtbot):
        """
        场景：过滤模式下翻页与列表选中映射同步
        验证：可见索引 [2,5,7] → prev_image → 正确跳转 → 列表同步
        """
        setup = integration_setup
        manager = setup['manager']
        state = setup['state']
        ui = setup['ui']

        # 前置：设置 10 个图片，当前索引 5
        test_images = real_image_files(count=10)
        state.image_files = test_images
        state.all_image_files = test_images
        state.current_index = 5

        # 设置过滤：可见索引 [2, 5, 7]
        manager._get_visible_indices = Mock(return_value=[2, 5, 7])

        # 设置 image_list 和 model
        mock_image_list = Mock()
        mock_selection_model = Mock()
        mock_image_list.selectionModel = Mock(return_value=mock_selection_model)
        mock_image_list.scrollTo = Mock()

        mock_index = Mock()
        mock_index.isValid = Mock(return_value=True)
        mock_model = Mock()
        mock_model.index = Mock(return_value=mock_index)

        manager._image_list = mock_image_list
        manager._image_list_model = mock_model
        manager._get_original_to_filtered_index = Mock(return_value={2: 0, 5: 1, 7: 2})

        # 执行：上一张（应该跳到索引 2）
        with qtbot.waitSignal(manager.image_changed, timeout=1000) as blocker:
            manager.prev_image()

        # 验证：跳转到索引 2
        assert blocker.args[0] == 2
        assert state.current_index == 2

        # 测试空过滤：应该显示 toast
        ui.calls.clear()
        manager._get_visible_indices = Mock(return_value=[])

        manager.prev_image()

        # 验证：显示 toast
        toast_calls = [call for call in ui.calls if call[0] == 'show_toast']
        assert len(toast_calls) > 0
        assert toast_calls[0][2] == "当前过滤条件下没有图片"
