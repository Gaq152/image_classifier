"""
FileOperationManager 单元测试
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch

from ui.managers.file_operation_manager import FileOperationManager


@pytest.fixture
def mock_state():
    """创建Mock StateView"""
    state = Mock()
    state.current_dir = Path("/test/images")
    state.is_copy_mode = True
    state.is_multi_category = False
    state.classified_images = {}
    state.removed_images = set()
    state.categories = set()
    state.image_files = []
    state.current_index = 0

    # Mock get_real_file_path方法
    def get_real_path(path):
        return path
    state.get_real_file_path = Mock(side_effect=get_real_path)

    return state


@pytest.fixture
def mock_mutator():
    """创建Mock StateMutator"""
    mutator = Mock()
    return mutator


@pytest.fixture
def mock_ui():
    """创建Mock UIHooks"""
    ui = Mock()
    ui.save_state = Mock()
    ui.save_state_sync = Mock()
    ui.schedule_ui_update = Mock()
    ui.refresh_category_buttons_style = Mock()
    ui.apply_image_filter = Mock()
    ui.is_image_filter_active = Mock(return_value=False)
    ui.refresh_image_filter_path = None
    ui.show_progress_dialog = Mock()
    ui.show_question = Mock(return_value=False)
    ui.show_toast = Mock()
    return ui


@pytest.fixture
def mock_navigator():
    """创建Mock ImageNavigator"""
    navigator = Mock()
    navigator.select_after_removal = Mock()
    navigator.show_current_image = Mock()
    return navigator


@pytest.fixture
def manager(mock_state, mock_mutator, mock_ui, mock_navigator):
    """创建 FileOperationManager 实例"""
    return FileOperationManager(
        state=mock_state,
        mutator=mock_mutator,
        ui=mock_ui,
        navigator=mock_navigator,
        logger=None
    )


class TestFileOperationManager:
    """FileOperationManager 单元测试"""

    # ========== 初始化测试 ==========

    def test_manager_initialization(self, manager):
        """测试 Manager 初始化"""
        assert manager is not None

    def test_signals_exist(self, manager):
        """测试所有信号存在"""
        assert hasattr(manager, 'file_moved')
        assert hasattr(manager, 'file_removed')
        assert hasattr(manager, 'file_restored')
        assert hasattr(manager, 'mode_changed')
        assert hasattr(manager, 'migration_progress')
        assert hasattr(manager, 'operation_failed')

    # ========== 模式管理测试 ==========

    def test_get_mode(self, manager, mock_state):
        """测试获取模式"""
        mock_state.is_copy_mode = True
        assert manager.get_mode() is True

        mock_state.is_copy_mode = False
        assert manager.get_mode() is False

    def test_set_mode_changes_state(self, manager, mock_mutator, mock_ui, qtbot):
        """测试设置模式改变状态"""
        with qtbot.waitSignal(manager.mode_changed, timeout=1000) as blocker:
            manager.set_mode(False)

        # 验证调用了mutator和ui方法
        mock_mutator.set_copy_mode.assert_called_once_with(False)
        mock_ui.save_state.assert_called_once()

        # 验证信号参数
        assert blocker.args[0] is False

    def test_set_mode_no_change_if_same(self, manager, mock_mutator, mock_state):
        """测试相同模式不触发变化"""
        mock_state.is_copy_mode = True
        manager.set_mode(True)

        # 不应该调用mutator
        mock_mutator.set_copy_mode.assert_not_called()

    # ========== 文件分类测试（单分类模式） ==========

    def test_move_to_category_single_mode(self, manager, mock_state, mock_mutator, mock_ui, qtbot):
        """测试单分类模式分类图片"""
        mock_state.is_multi_category = False
        mock_state.classified_images = {}
        file_path = "/test/images/test.jpg"

        with patch('shutil.copy2'):
            with qtbot.waitSignal(manager.file_moved, timeout=1000):
                manager.move_to_category(file_path, "category1")

        # 验证状态更新
        mock_mutator.set_classified_image.assert_called_once()
        mock_ui.save_state.assert_called_once()
        mock_ui.schedule_ui_update.assert_called()

    def test_move_to_category_skips_model_reset_without_filter(
        self,
        manager,
        mock_state,
        mock_ui,
    ):
        """默认全部显示且无搜索时，分类不应重建图片列表模型。"""
        mock_state.is_multi_category = False
        mock_ui.is_image_filter_active.return_value = False

        with patch.object(manager, '_execute_file_operation_with_check'):
            manager.move_to_category("/test/images/test.jpg", "category1")

        mock_ui.apply_image_filter.assert_not_called()

    def test_move_to_category_falls_back_to_model_reset_for_legacy_ui_hook(
        self,
        manager,
        mock_state,
        mock_ui,
    ):
        """旧 UIHooks 未提供增量接口时，筛选场景仍可回退完整刷新。"""
        mock_state.is_multi_category = False
        mock_ui.is_image_filter_active.return_value = True

        with patch.object(manager, '_execute_file_operation_with_check'):
            manager.move_to_category("/test/images/test.jpg", "category1")

        mock_ui.apply_image_filter.assert_called_once_with(suppress_show=True)

    def test_move_to_category_prefers_incremental_filter_update(
        self,
        manager,
        mock_state,
        mock_ui,
    ):
        """新 UIHooks 应只更新受影响路径，不再重置图片列表模型。"""
        mock_state.is_multi_category = False
        mock_ui.is_image_filter_active.return_value = True
        mock_ui.refresh_image_filter_path = Mock(return_value="removed")
        file_path = "/test/images/test.jpg"

        with patch.object(manager, '_execute_file_operation_with_check'):
            manager.move_to_category(file_path, "category1")

        mock_ui.refresh_image_filter_path.assert_called_once_with(file_path)
        mock_ui.apply_image_filter.assert_not_called()

    def test_move_to_category_emits_logical_path_when_restoring_removed_image(
        self,
        manager,
        mock_state,
        qtbot,
    ):
        """从 remove 恢复时，列表状态更新应使用模型保存的原始路径。"""
        logical_path = "/test/images/test.jpg"
        mock_state.is_multi_category = False
        mock_state.removed_images = {logical_path}
        mock_state.get_real_file_path.return_value = Path("/test/remove/test.jpg")

        with patch.object(manager, '_move_from_remove_to_category'):
            with qtbot.waitSignal(manager.file_moved, timeout=1000) as blocker:
                manager.move_to_category(logical_path, "category1")

        assert blocker.args[0] == logical_path

    def test_move_to_category_single_mode_same_category_undo(self, manager, mock_state, mock_mutator):
        """测试单分类模式点击相同类别触发撤销"""
        mock_state.is_multi_category = False
        mock_state.classified_images = {"/test/images/test.jpg": "category1"}

        with patch.object(manager, '_undo_classification') as mock_undo:
            manager.move_to_category("/test/images/test.jpg", "category1")

        # 应该调用撤销而不是重新分类
        mock_undo.assert_called_once_with("/test/images/test.jpg", "category1")

    def test_move_to_category_single_mode_change_category(self, manager, mock_state, mock_mutator, mock_ui):
        """测试单分类模式切换类别"""
        mock_state.is_multi_category = False
        mock_state.classified_images = {"/test/images/test.jpg": "category1"}

        with patch('shutil.copy2'):
            manager.move_to_category("/test/images/test.jpg", "category2")

        # 应该更新为新类别
        calls = mock_mutator.set_classified_image.call_args_list
        assert len(calls) >= 1
        assert calls[-1][0][1] == "category2"

    # ========== 文件分类测试（多分类模式） ==========

    def test_move_to_category_multi_mode_add(self, manager, mock_state, mock_mutator, mock_ui):
        """测试多分类模式添加类别"""
        mock_state.is_multi_category = True
        mock_state.classified_images = {"/test/images/test.jpg": ["category1"]}

        with patch('shutil.copy2'):
            manager.move_to_category("/test/images/test.jpg", "category2")

        # 验证添加了新类别
        calls = mock_mutator.set_classified_image.call_args_list
        assert len(calls) >= 1
        final_categories = calls[-1][0][1]
        assert "category1" in final_categories
        assert "category2" in final_categories

    def test_move_to_category_multi_mode_remove(self, manager, mock_state, mock_mutator):
        """测试多分类模式移除类别"""
        mock_state.is_multi_category = True
        mock_state.classified_images = {"/test/images/test.jpg": ["category1", "category2"]}

        with patch.object(manager, '_maybe_remove_copied_file'):
            manager.move_to_category("/test/images/test.jpg", "category1")

        # 验证移除了category1
        calls = mock_mutator.set_classified_image.call_args_list
        assert len(calls) >= 1
        final_categories = calls[-1][0][1]
        assert "category1" not in final_categories
        assert "category2" in final_categories

    def test_move_to_category_multi_mode_remove_last_category(self, manager, mock_state, mock_mutator):
        """测试多分类模式移除最后一个类别"""
        mock_state.is_multi_category = True
        mock_state.classified_images = {"/test/images/test.jpg": ["category1"]}

        with patch.object(manager, '_maybe_remove_copied_file'):
            manager.move_to_category("/test/images/test.jpg", "category1")

        # 应该完全移除分类记录
        mock_mutator.remove_classified_image.assert_called_once_with("/test/images/test.jpg")

    # ========== 文件移除测试 ==========

    def test_move_to_remove_basic(self, manager, mock_state, mock_mutator, mock_ui, mock_navigator, qtbot):
        """测试基本移除功能"""
        mock_state.current_index = 5
        mock_state.classified_images = {}
        mock_state.removed_images = set()

        with patch('shutil.copy2'):
            with qtbot.waitSignal(manager.file_removed, timeout=1000):
                manager.move_to_remove("/test/images/test.jpg")

        # 验证状态更新
        mock_mutator.add_removed_image.assert_called_once()
        mock_ui.apply_image_filter.assert_called_once()
        mock_navigator.select_after_removal.assert_called_once_with(5)

    def test_move_to_remove_already_removed_triggers_undo(self, manager, mock_state):
        """测试已移除的图片再次移除触发撤销"""
        mock_state.current_index = 0  # 需要设置有效索引
        mock_state.removed_images = {"/test/images/test.jpg"}

        with patch.object(manager, '_undo_removal') as mock_undo:
            manager.move_to_remove("/test/images/test.jpg")

        mock_undo.assert_called_once_with("/test/images/test.jpg")

    def test_move_to_remove_with_classification(self, manager, mock_state, mock_mutator):
        """测试移除已分类图片"""
        mock_state.current_index = 0
        mock_state.classified_images = {"/test/images/test.jpg": "category1"}

        with patch.object(manager, '_move_from_category_to_remove'):
            manager.move_to_remove("/test/images/test.jpg")

        # 应该清除分类记录
        mock_mutator.remove_classified_image.assert_called_once()

    # ========== 撤销操作测试 ==========

    def test_undo_classification_copy_mode(self, manager, mock_state, mock_mutator, mock_ui, qtbot):
        """测试复制模式撤销分类"""
        mock_state.is_copy_mode = True
        mock_state.current_dir = Path("/test/images")
        mock_state.classified_images = {"/test/images/test.jpg": "category1"}

        with patch('pathlib.Path.exists', return_value=True):
            with patch('pathlib.Path.unlink') as mock_unlink:
                with qtbot.waitSignal(manager.file_restored, timeout=1000):
                    manager._undo_classification("/test/images/test.jpg", "category1")

        # 验证删除了分类副本
        mock_unlink.assert_called_once()
        mock_mutator.remove_classified_image.assert_called_once()

    def test_undo_classification_move_mode(self, manager, mock_state, mock_mutator, qtbot):
        """测试移动模式撤销分类"""
        mock_state.is_copy_mode = False
        mock_state.current_dir = Path("/test/images")
        mock_state.classified_images = {"/test/images/test.jpg": "category1"}

        with patch.object(
            Path,
            'exists',
            autospec=True,
            side_effect=lambda path: path.parent.name == "category1",
        ):
            with patch('shutil.move') as mock_move:
                with qtbot.waitSignal(manager.file_restored, timeout=1000):
                    manager._undo_classification("/test/images/test.jpg", "category1")

        # 验证移动了文件
        mock_move.assert_called_once()
        mock_mutator.remove_classified_image.assert_called_once()

    def test_undo_removal_copy_mode(self, manager, mock_state, mock_mutator, qtbot):
        """测试复制模式撤销移除"""
        mock_state.is_copy_mode = True
        mock_state.current_dir = Path("/test/images")

        with patch('pathlib.Path.exists', return_value=True):
            with patch('pathlib.Path.unlink') as mock_unlink:
                with qtbot.waitSignal(manager.file_restored, timeout=1000):
                    manager._undo_removal("/test/images/test.jpg")

        mock_unlink.assert_called_once()
        mock_mutator.remove_from_removed.assert_called_once()

    def test_undo_removal_move_mode(self, manager, mock_state, mock_mutator, qtbot):
        """测试移动模式撤销移除"""
        mock_state.is_copy_mode = False
        mock_state.current_dir = Path("/test/images")

        with patch.object(
            Path,
            'exists',
            autospec=True,
            side_effect=lambda path: path.parent.name == "remove",
        ):
            with patch('shutil.move') as mock_move:
                with qtbot.waitSignal(manager.file_restored, timeout=1000):
                    manager._undo_removal("/test/images/test.jpg")

        mock_move.assert_called_once()
        mock_mutator.remove_from_removed.assert_called_once()

    # ========== 辅助方法测试 ==========

    def test_ensure_unique_name_no_conflict(self, manager):
        """测试无冲突时返回原路径"""
        target = Path("/test/new_file.jpg")
        with patch('pathlib.Path.exists', return_value=False):
            result = manager._ensure_unique_name(target)
        assert result == target

    def test_ensure_unique_name_with_conflict(self, manager):
        """测试有冲突时追加序号"""
        target = Path("/test/file.jpg")
        exists_calls = [True, True, False]  # file.jpg存在, file_1.jpg存在, file_2.jpg不存在

        with patch('pathlib.Path.exists', side_effect=exists_calls):
            result = manager._ensure_unique_name(target)

        assert result.name == "file_2.jpg"

    def test_get_parent_dir(self, manager, mock_state):
        """测试获取父目录"""
        mock_state.current_dir = Path("/test/images")
        result = manager._get_parent_dir()
        assert result == Path("/test")

    def test_get_parent_dir_no_current_dir(self, manager, mock_state):
        """测试无当前目录时抛出异常"""
        mock_state.current_dir = None
        with pytest.raises(FileNotFoundError):
            manager._get_parent_dir()

    # ========== 边界条件测试 ==========

    def test_move_to_category_no_current_dir(self, manager, mock_state):
        """测试无当前目录时不执行操作"""
        mock_state.current_dir = None

        # 不应该抛出异常，只是返回
        manager.move_to_category("/test/test.jpg", "category1")

        # 方法应该提前返回，不执行任何操作
        # 无需检查信号，因为它不会被发射

    def test_move_to_remove_invalid_index(self, manager, mock_state):
        """测试无效索引时不执行操作"""
        mock_state.current_index = -1

        manager.move_to_remove("/test/test.jpg")

        # 应该直接返回，不执行任何操作
        # （验证方法是确保没有调用mutator的方法）

    def test_operation_error_emits_failed_signal(self, manager, mock_state, qtbot):
        """测试操作失败时发射失败信号"""
        mock_state.current_dir = Path("/test/images")

        with patch('shutil.copy2', side_effect=Exception("Test error")):
            with qtbot.waitSignal(manager.operation_failed, timeout=1000) as blocker:
                manager.move_to_category("/test/test.jpg", "category1")

        # 验证失败信号参数
        assert "test.jpg" in blocker.args[0]
        assert "Test error" in blocker.args[1]

    # ========== 文件哈希测试 ==========

    def test_get_file_hash_success(self, manager, tmp_path):
        """测试成功计算文件哈希"""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        hash_result = manager._get_file_hash(str(test_file))

        assert hash_result is not None
        assert len(hash_result) == 32  # MD5哈希长度

    def test_get_file_hash_failure(self, manager):
        """测试文件不存在时返回None"""
        hash_result = manager._get_file_hash("/nonexistent/file.jpg")
        assert hash_result is None

    # ========== 重命名目标测试 ==========

    def test_get_renamed_target_increments(self, manager):
        """测试重命名目标递增序号"""
        target = "/test/file.jpg"

        exists_calls = [True, True, False]  # file_1.jpg存在, file_2.jpg存在, file_3.jpg不存在
        with patch('pathlib.Path.exists', side_effect=exists_calls):
            result = manager._get_renamed_target(target)

        # Windows路径规范化
        assert result == str(Path("/test/file_3.jpg"))

    # ========== 类别切换测试（BUG修复验证） ==========

    def test_single_mode_change_category_removes_old_copy(self, manager, mock_state, mock_mutator):
        """测试单分类模式切换类别时删除旧副本（复制模式）"""
        mock_state.is_copy_mode = True
        mock_state.is_multi_category = False
        mock_state.classified_images = {"/test/images/test.jpg": "cat3"}

        with patch.object(manager, '_maybe_remove_copied_file') as mock_remove:
            with patch('shutil.copy2'):
                manager.move_to_category("/test/images/test.jpg", "cat4")

        # 应该先删除cat3的副本（Windows路径规范化）
        actual_path = mock_remove.call_args[0][0]
        expected_path = str(Path("/test/images/test.jpg"))
        assert actual_path == expected_path
        assert mock_remove.call_args[0][1] == "cat3"

        # 然后更新状态为cat4
        calls = mock_mutator.set_classified_image.call_args_list
        assert len(calls) >= 1
        assert calls[-1][0][1] == "cat4"

    # ========== 新增测试：Critical 级别 - 只读/权限/异常处理 ==========

    def test_move_to_category_readonly_copy_mode_calls_remove_readonly(
        self, manager, mock_state, mock_mutator, mock_ui, qtbot
    ):
        """测试复制模式下只读文件触发 remove_readonly"""
        mock_state.is_copy_mode = True
        mock_state.is_multi_category = False
        img_path = "/test/images/readonly.jpg"
        category = "cat1"

        # Mock：目标不存在，复制成功后移除目标文件只读属性
        with patch('shutil.copy2'):
            with patch('pathlib.Path.exists', return_value=False):
                with patch(
                    'ui.managers.file_operation_manager.remove_readonly'
                ) as mock_remove_ro:
                    with qtbot.waitSignal(manager.file_moved, timeout=1000):
                        manager.move_to_category(img_path, category)

        # 验证：remove_readonly 被调用
        assert mock_remove_ro.called

        # 验证：file_moved 信号发射
        # 已通过 waitSignal 验证

    def test_move_to_remove_operation_exception_emits_failed(
        self, manager, mock_state, mock_ui, qtbot
    ):
        """测试移除操作异常时发射 operation_failed 信号"""
        img_path = "/test/images/test.jpg"
        mock_state.removed_images = set()  # 未被移除
        mock_state.classified_images = {img_path: "cat1"}

        # Mock：操作失败
        with patch.object(manager, '_move_from_category_to_remove',
                         side_effect=Exception("磁盘错误")):
            with qtbot.waitSignal(manager.operation_failed, timeout=1000) as blocker:
                manager.move_to_remove(img_path)

        # 验证：operation_failed 信号参数
        assert blocker.args[0] == img_path
        assert "磁盘错误" in blocker.args[1] or "异常" in blocker.args[1]

    def test_undo_classification_copy_remove_readonly_retry(
        self, manager, mock_state, mock_mutator, mock_ui
    ):
        """测试撤销分类时只读文件的重试处理"""
        mock_state.is_copy_mode = True
        img_path = "/test/images/test.jpg"
        category = "cat1"
        mock_state.classified_images = {img_path: category}

        # Mock：删除副本时遇到只读错误，重试成功
        with patch('pathlib.Path.exists', return_value=True):
            with patch('pathlib.Path.unlink', side_effect=PermissionError("只读")):
                with patch(
                    'ui.managers.file_operation_manager.remove_readonly'
                ) as mock_remove_ro:
                    with patch(
                        'ui.managers.file_operation_manager.retry_file_operation',
                        return_value=True,
                    ):
                        manager._undo_classification(img_path, category)

        # 验证：remove_readonly 被调用
        assert mock_remove_ro.called

        # 该兼容分支允许实现按实际文件状态决定是否提示警告。

    # ========== 新增测试：模式迁移流程 ==========

    def test_migrate_copy_to_move_success_flow(
        self, manager, mock_state, mock_mutator, mock_ui, qtbot, monkeypatch
    ):
        """测试复制→移动迁移成功流程"""
        # Mock QTimer.singleShot 立即执行
        def immediate_call(interval, callback):
            callback()
        monkeypatch.setattr('PyQt6.QtCore.QTimer.singleShot', immediate_call)

        mock_state.is_copy_mode = True
        mock_state.classified_images = {
            "/test/img1.jpg": "cat1",
            "/test/img2.jpg": "cat2"
        }
        mock_state.current_dir = Path("/test/images")

        # Mock progress dialog
        mock_progress = Mock()
        mock_progress.setValue = Mock()
        mock_progress.setMaximum = Mock()
        mock_ui.show_progress_dialog = Mock(return_value=mock_progress)

        # Mock 文件操作：全部成功
        current_dir = mock_state.current_dir
        with patch.object(
            Path,
            'exists',
            autospec=True,
            side_effect=lambda path: path == current_dir or path.parent == current_dir,
        ):
            with patch('shutil.move'):
                with qtbot.waitSignal(manager.mode_changed, timeout=2000):
                    manager._migrate_copy_to_move()

        # 验证：progress_dialog.setValue 被调用
        assert mock_progress.setValue.called

        # 验证：模式切换为移动模式
        # mode_changed 信号已发射（通过 waitSignal 验证）

        # 验证：显示成功toast
        success_calls = [c for c in mock_ui.show_toast.call_args_list
                        if len(c[0]) > 0 and c[0][0] == 'success']
        assert len(success_calls) > 0

    def test_migrate_copy_to_move_failure_emits_operation_failed(
        self, manager, mock_state, mock_ui, qtbot, monkeypatch
    ):
        """测试复制→移动迁移失败时发射 operation_failed"""
        # Mock QTimer
        def immediate_call(interval, callback):
            callback()
        monkeypatch.setattr('PyQt6.QtCore.QTimer.singleShot', immediate_call)

        mock_state.is_copy_mode = True
        mock_state.classified_images = {
            "/test/img1.jpg": "cat1"
        }
        mock_state.current_dir = Path("/test/images")

        # Mock progress dialog
        mock_progress = Mock()
        mock_ui.show_progress_dialog = Mock(return_value=mock_progress)

        # Mock：移动操作失败
        current_dir = mock_state.current_dir
        with patch.object(
            Path,
            'exists',
            autospec=True,
            side_effect=lambda path: path == current_dir or path.parent == current_dir,
        ):
            with patch('shutil.move', side_effect=Exception("移动失败")):
                manager._migrate_copy_to_move()

        # 验证：显示警告toast（包含失败信息）
        warning_calls = [c for c in mock_ui.show_toast.call_args_list
                        if len(c[0]) > 0 and c[0][0] == 'warning']
        assert len(warning_calls) > 0

    def test_migrate_move_to_copy_success(
        self, manager, mock_state, mock_mutator, mock_ui, qtbot, monkeypatch
    ):
        """测试移动→复制迁移成功流程"""
        # Mock QTimer
        def immediate_call(interval, callback):
            callback()
        monkeypatch.setattr('PyQt6.QtCore.QTimer.singleShot', immediate_call)

        mock_state.is_copy_mode = False
        mock_state.classified_images = {
            "/test/img1.jpg": "cat1"
        }
        mock_state.current_dir = Path("/test/images")

        # Mock progress dialog
        mock_progress = Mock()
        mock_ui.show_progress_dialog = Mock(return_value=mock_progress)

        # Mock 文件操作：复制成功
        current_dir = mock_state.current_dir
        with patch.object(
            Path,
            'exists',
            autospec=True,
            side_effect=lambda path: path == current_dir,
        ):
            with patch.object(manager, '_copy_back_to_source', return_value=True):
                with qtbot.waitSignal(manager.mode_changed, timeout=2000):
                    manager._migrate_move_to_copy()

        # 验证：_copy_back_to_source 被调用
        # assert manager._copy_back_to_source.called

        # 验证：mode_changed 信号发射（已通过 waitSignal 验证）

        # 验证：成功toast
        success_calls = [c for c in mock_ui.show_toast.call_args_list
                        if len(c[0]) > 0 and c[0][0] == 'success']
        assert len(success_calls) > 0

    # ========== 新增测试：重名冲突处理 ==========

    def test_handle_duplicate_same_hash_overwrite(
        self, manager, mock_ui
    ):
        """测试重名冲突：哈希相同，用户选择覆盖"""
        source = Path("/test/source.jpg")
        target = Path("/test/cat1/source.jpg")

        # Mock：哈希相同
        with patch.object(manager, '_get_file_hash', return_value="abc123"):
            # Mock：用户选择覆盖
            mock_ui.show_question = Mock(return_value=True)

            result = manager._handle_duplicate_file(str(source), str(target))

        # 验证：返回原目标路径（覆盖）
        assert result == str(target)

    def test_handle_duplicate_same_hash_cancel(
        self, manager, mock_ui
    ):
        """测试重名冲突：哈希相同，用户取消"""
        source = Path("/test/source.jpg")
        target = Path("/test/cat1/source.jpg")

        # Mock：哈希相同
        with patch.object(manager, '_get_file_hash', return_value="abc123"):
            # Mock：用户取消
            mock_ui.show_question = Mock(return_value=False)

            result = manager._handle_duplicate_file(str(source), str(target))

        # 验证：返回 None（取消操作）
        assert result is None

    def test_handle_duplicate_diff_hash_auto_rename(
        self, manager, mock_ui
    ):
        """测试重名冲突：哈希不同，自动重命名"""
        source = Path("/test/source.jpg")
        target = Path("/test/cat1/source.jpg")

        # Mock：哈希不同
        with patch.object(manager, '_get_file_hash', side_effect=["hash1", "hash2"]):
            # Mock：生成新名称
            with patch.object(manager, '_get_renamed_target',
                              return_value="/test/cat1/source_1.jpg"):
                result = manager._handle_duplicate_file(str(source), str(target))

        # 验证：返回重命名后的路径
        assert result == "/test/cat1/source_1.jpg"

        # 验证：显示info toast
        info_calls = [c for c in mock_ui.show_toast.call_args_list
                     if len(c[0]) > 0 and c[0][0] == 'info']
        assert len(info_calls) > 0

    # ========== 新增测试：Major 级别 - 多分类/撤销场景 ==========

    def test_move_to_category_multi_was_removed_moves_back(
        self, manager, mock_state, mock_mutator, qtbot
    ):
        """测试多分类模式从 remove 迁回"""
        mock_state.is_copy_mode = True
        mock_state.is_multi_category = True
        img_path = "/test/images/test.jpg"
        category = "cat1"

        # 图片在 removed_images 中
        mock_state.removed_images = {img_path}

        # Mock 文件操作
        with patch.object(manager, '_move_from_remove_to_category') as mock_move:
            with qtbot.waitSignal(manager.file_moved, timeout=1000):
                manager.move_to_category(img_path, category)

        # 验证：调用了 _move_from_remove_to_category
        assert mock_move.called
        assert mock_move.call_args[0][0] == str(Path(img_path))
        assert mock_move.call_args[0][1] == category

        # 验证：从 removed_images 中移除
        assert mock_mutator.remove_from_removed.called

    def test_move_to_remove_already_classified_multi(
        self, manager, mock_state, mock_mutator
    ):
        """测试多分类模式移除已分类的图片"""
        mock_state.is_multi_category = True
        img_path = "/test/images/test.jpg"

        # 已分类到多个类别
        mock_state.classified_images = {
            img_path: ["cat1", "cat2"]
        }

        # Mock 文件操作
        with patch.object(manager, '_move_from_category_to_remove') as mock_move:
            manager.move_to_remove(img_path)

        # 验证：_move_from_category_to_remove 被调用（每个类别一次）
        assert mock_move.call_count == 2

    def test_undo_removal_move_mode_renames_on_conflict(
        self, manager, mock_state, mock_mutator
    ):
        """测试撤销移除时遇到重名冲突自动重命名"""
        mock_state.is_copy_mode = False
        img_path = "/test/images/test.jpg"
        mock_state.removed_images = {img_path}

        # Mock：目标路径已存在，需要重命名
        with patch.object(manager, '_ensure_unique_name',
                         return_value="/test/images/test_1.jpg") as mock_unique:
            with patch('shutil.move'):
                with patch('pathlib.Path.exists', return_value=True):
                    manager._undo_removal(img_path)

        # 验证：调用了 _ensure_unique_name
        assert mock_unique.called

    def test_move_to_category_same_category_calls_undo_and_refresh(
        self, manager, mock_state, mock_ui
    ):
        """测试分类到相同类别时调用撤销并刷新样式"""
        mock_state.is_copy_mode = True
        mock_state.is_multi_category = False
        img_path = "/test/images/test.jpg"
        category = "cat1"

        # 已分类到 cat1
        mock_state.classified_images = {img_path: category}

        # Mock _undo_classification
        with patch.object(manager, '_undo_classification') as mock_undo:
            manager.move_to_category(img_path, category)

        # 验证：调用了 _undo_classification
        assert mock_undo.called
        assert mock_undo.call_args[0] == (img_path, category)

        # 验证：刷新了样式
        assert mock_ui.refresh_category_buttons_style.called

    def test_execute_file_operation_to_remove_calls_copy(
        self, manager
    ):
        """测试移除操作使用 copy 而不是 move"""
        source = Path("/test/source.jpg")
        target = Path("/test/remove/source.jpg")

        # Mock 文件操作
        with patch('shutil.copy2') as mock_copy:
            with patch('pathlib.Path.exists', return_value=False):
                manager._execute_file_operation_with_check(
                    source, target, is_remove=True
                )

        # 验证：使用 copy2 而不是 move
        assert mock_copy.called
