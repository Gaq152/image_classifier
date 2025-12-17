"""
文件操作管理器

职责：
- 负责分类、移除、撤销、模式迁移等文件层面的所有操作
- 通过 StateView / StateMutator / UIHooks / ImageNavigator 依赖注入，避免直接访问主窗口
- 使用信号通知 UI 和其他 Manager，保持解耦

设计模式：
- 依赖注入：接收接口而非具体类
- 信号驱动：通过信号通知状态变化
- 职责单一：只负责文件操作，不负责导航和UI更新
"""

from pathlib import Path
import shutil
import hashlib
import logging
from typing import Optional, Union, List

from PyQt6.QtCore import QObject, pyqtSignal

from .._main_window.state.interfaces import StateView, StateMutator, UIHooks, ImageNavigator
from utils.file_operations import retry_file_operation, remove_readonly


class FileOperationManager(QObject):
    """文件操作管理器，集中处理文件搬运、撤销与模式迁移逻辑"""

    # ========== 信号定义 ==========
    file_moved = pyqtSignal(str, str)          # src, dst
    file_removed = pyqtSignal(str)             # path
    file_restored = pyqtSignal(str)            # path
    mode_changed = pyqtSignal(bool)            # is_copy_mode
    migration_progress = pyqtSignal(str, int, int)  # step, current, total
    operation_failed = pyqtSignal(str, str)    # path, reason

    def __init__(
        self,
        state: StateView,
        mutator: StateMutator,
        ui: UIHooks,
        navigator: ImageNavigator,
        logger: Optional[logging.Logger] = None,
    ):
        """
        初始化文件操作管理器

        Args:
            state: 状态只读接口
            mutator: 状态修改接口
            ui: UI回调接口
            navigator: 导航接口
            logger: 日志记录器
        """
        super().__init__()
        self._state = state
        self._mutator = mutator
        self._ui = ui
        self._navigator = navigator
        self._logger = logger or logging.getLogger(__name__)

    # ========== 模式管理 ==========

    def get_mode(self) -> bool:
        """获取当前是否为复制模式"""
        return self._state.is_copy_mode

    def set_mode(self, is_copy_mode: bool) -> None:
        """切换复制/移动模式，保存状态并发出信号"""
        if self._state.is_copy_mode == is_copy_mode:
            return
        self._mutator.set_copy_mode(is_copy_mode)
        self._ui.save_state()
        self.mode_changed.emit(is_copy_mode)
        self._logger.info("操作模式已切换为%s", "复制" if is_copy_mode else "移动")

    # ========== 核心文件操作 ==========

    def move_to_category(self, file_path: str, category_name: str) -> None:
        """
        移动/复制图片到指定分类目录，支持单分类切换与多分类增删

        流程：
        - 多分类：列表中不存在则添加，存在则移除；移除后列表为空则清除记录
        - 单分类：点击同一分类视为撤销；否则重置为新分类
        - 若图片在 remove 目录，先从 remove 迁回目标分类
        - 使用 _execute_file_operation_with_check 处理重名与物理文件搬运

        Args:
            file_path: 图片路径
            category_name: 目标分类名
        """
        try:
            if not self._state.current_dir:
                return

            real_path = str(self._state.get_real_file_path(Path(file_path)))
            old_category = self._state.classified_images.get(file_path)
            was_removed = file_path in self._state.removed_images

            # 多分类分支
            if self._state.is_multi_category:
                categories: List[str] = []
                if isinstance(old_category, list):
                    categories = list(old_category)
                elif isinstance(old_category, str):
                    categories = [old_category]

                if category_name in categories:
                    # 取消该分类
                    categories.remove(category_name)
                    self._maybe_remove_copied_file(real_path, category_name)
                    if categories:
                        self._mutator.set_classified_image(file_path, categories)
                    else:
                        self._mutator.remove_classified_image(file_path)
                else:
                    # 新增分类
                    categories.append(category_name)
                    self._mutator.set_classified_image(file_path, categories)
                    if was_removed:
                        self._move_from_remove_to_category(real_path, category_name)
                        self._mutator.remove_from_removed(file_path)
                    else:
                        self._execute_file_operation_with_check(real_path, category_name, is_remove=False)
            else:
                # 单分类分支：相同分类即撤销
                # 防御：单分类模式下不应出现 list 分类记录（可能来自历史状态/错误切换）
                if isinstance(old_category, list):
                    if len(old_category) == 1:
                        old_category = old_category[0]
                        self._mutator.set_classified_image(file_path, old_category)
                    elif len(old_category) > 1:
                        self._ui.show_toast(
                            'warning',
                            "当前图片已被分配多个标签，无法在单分类模式下继续操作，请切换到多分类模式或先移除多余标签"
                        )
                        return
                    else:
                        old_category = None
                        self._mutator.remove_classified_image(file_path)

                if old_category == category_name:
                    # 传入原始路径 file_path，_undo_classification 内部会处理状态清理
                    self._undo_classification(file_path, category_name)
                    self._ui.refresh_category_buttons_style()
                    return

                # 重置分类：先创建新副本，再删除旧副本（避免删除失败影响新分类）
                self._mutator.set_classified_image(file_path, category_name)
                if was_removed:
                    self._move_from_remove_to_category(real_path, category_name)
                    self._mutator.remove_from_removed(file_path)
                else:
                    self._execute_file_operation_with_check(real_path, category_name, is_remove=False)

                # 创建新副本后，再删除旧类别副本（即使失败也不影响新分类）
                if old_category:
                    self._maybe_remove_copied_file(real_path, old_category)

            self._ui.save_state()
            self._ui.schedule_ui_update('category_buttons', 'category_counts', 'statistics', 'ui_state')
            self._ui.refresh_category_buttons_style()

            # 分类后：单分类自动翻页，多分类保持当前图片（便于同图多标签）
            self._ui.apply_image_filter(suppress_show=True)
            if not self._state.is_multi_category:
                self._navigator.next_image()

            target_dir = self._get_parent_dir() / category_name
            self.file_moved.emit(real_path, str(target_dir / Path(real_path).name))
            self._logger.info("图片已归类到 %s: %s", category_name, Path(real_path).name)
        except Exception as e:
            self._logger.error("移动到分类失败: %s", e)
            self.operation_failed.emit(file_path, str(e))

    def move_to_remove(self, file_path: str) -> None:
        """
        移动图片到 remove 目录，完整保留已修复的导航逻辑

        关键修复（2025-12-05）：
        1) 记录原始索引 original_index
        2) 搬运文件 + 更新 removed/classified 状态
        3) 触发 apply_image_filter() 重新计算可见列表
        4) 调用 navigator.select_after_removal(original_index) 智能选择相邻可见项
        5) 发出 file_removed 信号

        Args:
            file_path: 要删除的图片路径
        """
        try:
            if not self._state.current_dir or self._state.current_index < 0:
                return

            original_index = self._state.current_index  # 关键：记录删除前的索引
            real_path = str(self._state.get_real_file_path(Path(file_path)))

            # 已在移除列表则执行撤销删除
            if file_path in self._state.removed_images:
                self._undo_removal(file_path)  # 修复：传入原始file_path而不是real_path
                return  # _undo_removal内部已发射file_restored信号

            old_category = self._state.classified_images.get(file_path)

            # 状态更新：标记移除并清理分类记录
            self._mutator.add_removed_image(file_path)
            self._mutator.remove_classified_image(file_path)

            # 物理搬运：分类目录 -> remove 或 原目录 -> remove
            if isinstance(old_category, list) and old_category:
                # 多分类：遍历所有分类副本，统一迁移到remove
                for cat in old_category:
                    try:
                        self._move_from_category_to_remove(real_path, cat)
                    except Exception as e:
                        self._logger.error("移除多分类副本失败[%s]: %s", cat, e)
            elif isinstance(old_category, str):
                self._move_from_category_to_remove(real_path, old_category)
            else:
                self._execute_file_operation_with_check(real_path, 'remove', is_remove=True)

            self._ui.save_state()
            self._ui.apply_image_filter(suppress_show=True)  # 重新计算 visible_indices，抑制显示避免重复

            # 关键修复：智能导航到最近可见项，避免跳到第二张
            self._navigator.select_after_removal(original_index)

            # 调度UI更新：统计、计数、按钮样式
            self._ui.schedule_ui_update('statistics', 'category_counts')
            self._ui.refresh_category_buttons_style()
            self.file_removed.emit(file_path)
            self._logger.info("图片已移除: %s", Path(real_path).name)
        except Exception as e:
            self._logger.error("移除图片失败: %s", e)
            self.operation_failed.emit(file_path, str(e))

    def _undo_classification(self, file_path: str, category_name: Optional[str] = None) -> None:
        """
        撤销分类：从分类目录移回原目录，并删除分类记录

        模式行为：
        - 复制模式：删除分类目录中的副本
        - 移动模式：将文件搬回 current_dir，自动处理重名

        Args:
            file_path: 图片路径
            category_name: 可选的分类名（如果为None则从状态中获取）
        """
        try:
            current_dir = self._state.current_dir
            if not current_dir:
                return

            category = category_name or self._state.classified_images.get(file_path)
            if not category:
                return

            source_file = Path(file_path)
            parent_dir = current_dir.parent

            # 兼容处理：category 可能是 str 或 list
            categories: List[str] = []
            if isinstance(category, list):
                categories = [c for c in category if isinstance(c, str) and c]
            elif isinstance(category, str):
                categories = [category]
            if not categories:
                return

            if self._state.is_copy_mode:
                # 复制模式：删除分类目录中的副本（多分类时删除所有标签副本）
                for cat in categories:
                    category_file = parent_dir / cat / source_file.name
                    if category_file.exists():
                        try:
                            remove_readonly(category_file)  # 移除只读属性，避免删除失败
                            retry_file_operation(category_file.unlink, max_retries=5, delay=0.2)
                            self._logger.info("撤销分类(复制模式)：删除副本 %s", category_file)
                        except Exception as e:
                            # 副本删除失败，但仍然清除分类记录（原图还在原目录）
                            self._logger.warning("删除副本失败（文件可能被占用），但已清除分类记录: %s", e)
                            self._ui.show_toast('warning', f"副本删除失败（文件被占用），但已清除分类记录\n建议：关闭占用文件的程序后手动删除")
            else:
                # 移动模式：搬回原目录（兼容异常状态：多分类记录时找第一个存在的文件）
                category_file = None
                for cat in categories:
                    candidate = parent_dir / cat / source_file.name
                    if candidate.exists():
                        category_file = candidate
                        break

                target_file = self._ensure_unique_name(current_dir / source_file.name)
                if category_file and category_file.exists():
                    shutil.move(str(category_file), str(target_file))
                    self._logger.info("撤销分类(移动模式)：%s -> %s", category_file, target_file)

            # 无论副本是否删除成功，都清除分类记录（复制模式下原图还在）
            self._mutator.remove_classified_image(file_path)
            self._ui.save_state_sync()

            # 只发射信号，由主窗口统一处理 UI 更新，避免重复刷新
            self.file_restored.emit(file_path)
        except Exception as e:
            self._logger.error("撤销分类失败: %s", e)
            self.operation_failed.emit(file_path, str(e))

    def _undo_removal(self, file_path: str) -> None:
        """
        撤销删除：从 remove 目录恢复到原目录（未分类状态）

        模式行为：
        - 复制模式：仅删除 remove 中的副本
        - 移动模式：将文件移回 current_dir，自动重命名避免冲突

        Args:
            file_path: 图片路径
        """
        try:
            current_dir = self._state.current_dir
            if not current_dir:
                return

            source_file = Path(file_path)
            remove_file = current_dir.parent / 'remove' / source_file.name

            if not remove_file.exists():
                self._logger.warning("撤销删除时未找到文件: %s", remove_file)
                return

            if self._state.is_copy_mode:
                # 复制模式：删除 remove 副本（修复：移除只读属性）
                try:
                    remove_readonly(remove_file)
                except Exception as e:
                    self._logger.warning(f"移除只读属性失败: {e}")
                remove_file.unlink()
                self._logger.info("撤销删除(复制模式)：删除 remove 副本 %s", remove_file)
            else:
                # 移动模式：搬回原目录
                target_file = self._ensure_unique_name(current_dir / source_file.name)
                shutil.move(str(remove_file), str(target_file))
                self._logger.info("撤销删除(移动模式)：%s -> %s", remove_file, target_file)

            self._mutator.remove_from_removed(file_path)
            self._ui.save_state_sync()

            # 只发射信号，由主窗口统一处理 UI 更新，避免重复刷新
            self.file_restored.emit(file_path)
        except Exception as e:
            self._logger.error("撤销删除失败: %s", e)
            self.operation_failed.emit(file_path, str(e))

    # ========== 模式迁移 ==========

    def _migrate_copy_to_move(self) -> None:
        """
        复制 -> 移动模式迁移

        流程：
        - 将原目录中的文件移动到对应分类目录（若已分类）
        - 移除 remove 目录中多余的副本
        - 迁移过程中显示进度，对失败文件汇总提示
        """
        failures = []
        try:
            # 前置检查（修复Codex Review中等问题）
            current_dir = self._state.current_dir
            if not current_dir or not current_dir.exists():
                self._logger.error("迁移失败：当前目录不存在")
                self.operation_failed.emit("copy_to_move", "当前目录不存在")
                return

            items = list(self._state.classified_images.items())
            total = len(items)
            dialog = self._ui.show_progress_dialog("迁移到移动模式", "正在迁移已分类文件...", maximum=total or 1)
            parent_dir = current_dir.parent

            for idx, (img_path, categories) in enumerate(items):
                try:
                    target_category = categories[0] if isinstance(categories, list) else categories
                    source_file = current_dir / Path(img_path).name
                    target_dir = parent_dir / target_category
                    target_dir.mkdir(parents=True, exist_ok=True)
                    target_file = target_dir / source_file.name

                    # 强制移动语义（修复Codex Review严重问题）
                    if source_file.exists():
                        # 检查目标是否存在，避免覆盖
                        if target_file.exists():
                            target_file = self._ensure_unique_name(target_file)

                        # 修复：移动前移除只读属性，避免权限错误
                        try:
                            remove_readonly(source_file)
                        except Exception as e:
                            self._logger.warning(f"移除只读属性失败: {e}")

                        shutil.move(str(source_file), str(target_file))
                        self._logger.info("迁移移动: %s -> %s", source_file.name, target_file)
                except Exception as inner:
                    failures.append(img_path)
                    self._logger.error("迁移失败: %s", inner)
                    self.operation_failed.emit(img_path, str(inner))
                finally:
                    if hasattr(dialog, 'setValue'):
                        dialog.setValue(idx + 1)
                    self.migration_progress.emit("copy_to_move", idx + 1, total)

            # 清理remove目录中的冗余副本
            remove_dir = parent_dir / 'remove'
            if remove_dir.exists():
                for img_path in self._state.removed_images:
                    remove_file = remove_dir / Path(img_path).name
                    if remove_file.exists():
                        try:
                            # 修复：删除前移除只读属性
                            remove_readonly(remove_file)
                            remove_file.unlink()
                            self._logger.info("清理remove副本: %s", remove_file.name)
                        except Exception as e:
                            self._logger.error("清理remove副本失败: %s", e)

            self.set_mode(False)
            self._ui.refresh_category_buttons_style()
            if failures:
                self._ui.show_toast('warning', f"迁移完成，但有 {len(failures)} 个文件失败")
            else:
                self._ui.show_toast('success', "复制模式迁移完成")
        except Exception as e:
            self._logger.error("复制->移动 迁移失败: %s", e)
            self.operation_failed.emit("copy_to_move", str(e))

    def _migrate_move_to_copy(self) -> None:
        """
        移动 -> 复制模式迁移

        流程：
        - 将分类目录中的文件复制回原目录保留一份
        - 保持分类目录中的文件不变，避免数据丢失
        """
        failures = []
        try:
            # 前置检查（修复Codex Review中等问题）
            current_dir = self._state.current_dir
            if not current_dir or not current_dir.exists():
                self._logger.error("迁移失败：当前目录不存在")
                self.operation_failed.emit("move_to_copy", "当前目录不存在")
                return

            items = list(self._state.classified_images.keys())
            total = len(items)
            dialog = self._ui.show_progress_dialog("迁移到复制模式", "正在复制已分类文件...", maximum=total or 1)

            for idx, img_path in enumerate(items):
                try:
                    self._copy_back_to_source(img_path)
                except Exception as inner:
                    failures.append(img_path)
                    self._logger.error("复制回源失败: %s", inner)
                    self.operation_failed.emit(img_path, str(inner))
                finally:
                    if hasattr(dialog, 'setValue'):
                        dialog.setValue(idx + 1)
                    self.migration_progress.emit("move_to_copy", idx + 1, total)

            self.set_mode(True)
            self._ui.refresh_category_buttons_style()
            if failures:
                self._ui.show_toast('warning', f"迁移完成，但有 {len(failures)} 个文件失败")
            else:
                self._ui.show_toast('success', "移动模式迁移完成")
        except Exception as e:
            self._logger.error("移动->复制 迁移失败: %s", e)
            self.operation_failed.emit("move_to_copy", str(e))

    # ========== 辅助方法 ==========

    def _execute_file_operation_with_check(self, source_path: str, category_name: str, is_remove: bool) -> None:
        """
        执行文件操作前检查重名并处理重复文件

        流程：
        - 若目标存在：调用 _handle_duplicate_file 决策覆盖/重命名/取消
        - 最终委派给 _execute_file_operation_direct

        Args:
            source_path: 源文件路径
            category_name: 目标分类名
            is_remove: 是否为移除操作
        """
        source_file = Path(source_path)
        parent_dir = self._get_parent_dir()
        target_dir = parent_dir / ('remove' if is_remove else category_name)
        target_file = target_dir / source_file.name

        if target_file.exists():
            handled_path = self._handle_duplicate_file(str(source_file), str(target_file))
            if handled_path is None:
                self._logger.info("用户取消了文件操作: %s", source_file.name)
                return
            target_file = Path(handled_path)

        self._execute_file_operation_direct(str(source_file), str(target_file), is_remove)

    def _execute_file_operation_direct(self, source_path: str, target_path: str, is_remove: bool) -> None:
        """
        直接执行复制/移动，不再重复检查

        Args:
            source_path: 源文件路径
            target_path: 目标文件路径
            is_remove: 是否为移除操作
        """
        source_file = Path(source_path)
        target_file = Path(target_path)
        target_file.parent.mkdir(parents=True, exist_ok=True)

        if self._state.is_copy_mode:
            shutil.copy2(source_file, target_file)
            remove_readonly(target_file)  # 移除只读属性，防止后续删除失败
            op = "复制"
        else:
            shutil.move(str(source_file), str(target_file))
            op = "移动"

        self._logger.info("文件%s成功: %s -> %s", op, source_file.name, target_file)
        self.file_moved.emit(str(source_file), str(target_file))

    def _move_from_category_to_remove(self, file_path: str, old_category: str) -> None:
        """
        从分类目录移动到 remove 目录，失败时回退到通用操作

        Args:
            file_path: 文件路径
            old_category: 原分类名
        """
        try:
            src = Path(file_path)
            parent_dir = self._get_parent_dir()
            old_file = parent_dir / old_category / src.name
            remove_dir = parent_dir / 'remove'
            remove_dir.mkdir(parents=True, exist_ok=True)
            target_file = self._ensure_unique_name(remove_dir / src.name)
            shutil.move(str(old_file), str(target_file))
            self._logger.info("分类 -> remove: %s -> %s", old_file, target_file)
        except Exception as e:
            self._logger.error("从分类到 remove 失败: %s", e)
            self._execute_file_operation_with_check(file_path, 'remove', is_remove=True)

    def _move_from_remove_to_category(self, file_path: str, category_name: str) -> None:
        """
        从 remove 目录恢复到指定分类目录

        Args:
            file_path: 文件路径
            category_name: 目标分类名
        """
        try:
            src = Path(file_path)
            parent_dir = self._get_parent_dir()
            remove_file = parent_dir / 'remove' / src.name
            target_dir = parent_dir / category_name
            target_dir.mkdir(parents=True, exist_ok=True)
            target_file = self._ensure_unique_name(target_dir / src.name)
            if remove_file.exists():
                shutil.move(str(remove_file), str(target_file))
            else:
                # 兜底：从原目录复制
                self._execute_file_operation_with_check(file_path, category_name, is_remove=False)
            self._logger.info("remove -> 分类: %s -> %s", remove_file, target_file)
        except Exception as e:
            self._logger.error("从 remove 恢复失败: %s", e)
            raise

    def _copy_back_to_source(self, file_path: str) -> None:
        """
        将分类目录中的文件复制回原目录，避免迁移到复制模式数据丢失

        Args:
            file_path: 文件路径
        """
        src = Path(file_path)
        current_dir = self._state.current_dir
        if not current_dir:
            return
        target_file = self._ensure_unique_name(current_dir / src.name)
        real_src = self._state.get_real_file_path(src)
        target_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(real_src, target_file)
        self._logger.info("迁移到复制模式：已复制回源目录 %s", target_file)

    def _maybe_remove_copied_file(self, source_path: str, category_name: str) -> None:
        """
        复制模式下，移除多分类时删除分类目录中的副本

        仅当大小一致时删除第一个匹配项

        Args:
            source_path: 源文件路径
            category_name: 分类名
        """
        if not self._state.is_copy_mode:
            return

        src = Path(source_path)
        parent_dir = self._get_parent_dir()
        category_dir = parent_dir / category_name
        if not category_dir.exists():
            return

        candidates = [category_dir / src.name]
        counter = 1
        while True:
            candidate = category_dir / f"{src.stem}_{counter}{src.suffix}"
            if candidate.exists():
                candidates.append(candidate)
                counter += 1
            else:
                break

        for candidate in candidates:
            try:
                if candidate.exists() and candidate.stat().st_size == src.stat().st_size:
                    remove_readonly(candidate)  # 移除只读属性，避免删除失败
                    retry_file_operation(candidate.unlink, max_retries=5, delay=0.2)
                    self._logger.info("已删除分类副本: %s", candidate)
                    break
            except Exception as e:
                self._logger.debug("删除分类副本失败: %s", e)

    def _handle_duplicate_file(self, source_path: str, target_path: str) -> Optional[str]:
        """
        处理重复文件

        逻辑：
        - 若内容相同：询问是否覆盖；否则取消
        - 若内容不同：提示重名，自动生成重命名目标

        Args:
            source_path: 源文件路径
            target_path: 目标文件路径

        Returns:
            最终目标路径；返回 None 表示取消
        """
        source_hash = self._get_file_hash(source_path)
        target_hash = self._get_file_hash(target_path)
        target_file = Path(target_path)

        if source_hash and source_hash == target_hash:
            overwrite = self._ui.show_question("文件已存在", f"{target_file.name} 已存在且内容相同，是否覆盖？")
            return target_path if overwrite else None
        else:
            renamed = self._get_renamed_target(target_path)
            self._ui.show_toast('info', f"目标已存在同名文件，已自动重命名为 {Path(renamed).name}")
            return renamed

    def _get_renamed_target(self, target_path: str) -> str:
        """
        生成递增后缀的重命名目标

        Args:
            target_path: 原目标路径

        Returns:
            重命名后的路径
        """
        target_file = Path(target_path)
        base = target_file.stem
        ext = target_file.suffix
        parent = target_file.parent
        counter = 1
        while True:
            new_target = parent / f"{base}_{counter}{ext}"
            if not new_target.exists():
                return str(new_target)
            counter += 1

    def _get_file_hash(self, file_path: str) -> Optional[str]:
        """
        计算文件 MD5，用于重复判断

        Args:
            file_path: 文件路径

        Returns:
            MD5哈希值，失败返回None
        """
        try:
            md5 = hashlib.md5()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    md5.update(chunk)
            return md5.hexdigest()
        except Exception as e:
            self._logger.debug("计算哈希失败: %s", e)
            return None

    def _ensure_unique_name(self, target: Path) -> Path:
        """
        若目标已存在则追加序号，返回可用路径

        Args:
            target: 目标路径

        Returns:
            可用的路径（不存在冲突）
        """
        if not target.exists():
            return target
        counter = 1
        while True:
            candidate = target.with_name(f"{target.stem}_{counter}{target.suffix}")
            if not candidate.exists():
                return candidate
            counter += 1

    def _get_parent_dir(self) -> Path:
        """
        获取图片目录的父目录（分类/移除目录都位于此处）

        Returns:
            父目录路径

        Raises:
            FileNotFoundError: 当前工作目录为空
        """
        if not self._state.current_dir:
            raise FileNotFoundError("当前工作目录为空")
        return self._state.current_dir.parent
