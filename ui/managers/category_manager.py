"""
类别管理器

负责类别加载、排序、模式切换以及分类确认的业务逻辑。
UI 操作通过 UIHooks 回调，文件操作委托给 FileOperationManager。

设计理念（Task 2.4，2025-12-05）：
- 从 main_window.py 提取类别管理逻辑
- 业务逻辑与 UI 分离，通过接口回调
- 文件操作委托给 FileOperationManager
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Set, TYPE_CHECKING, Union

from PyQt6.QtCore import QObject, pyqtSignal, QTimer

from ui._main_window.state.interfaces import (
    StateViewType,
    StateMutatorType,
    UIHooksType,
    ImageNavigatorType,
)

if TYPE_CHECKING:
    from ui.managers.file_operation_manager import FileOperationManager


class CategoryManager(QObject):
    """
    类别管理器：负责类别加载、排序、模式切换以及分类确认的业务逻辑。

    UI 操作通过 UIHooks 回调，文件操作委托给 FileOperationManager。

    信号：
        categories_changed: 类别列表变化时发射
        selection_changed: 选中类别变化时发射
        mode_changed: 多分类模式切换时发射
        sort_mode_changed: 排序模式变化时发射
    """

    # ========== 信号定义 ==========
    categories_changed = pyqtSignal(list)  # 类别列表变化
    selection_changed = pyqtSignal(int, str)  # 选中索引, 类别名
    mode_changed = pyqtSignal(bool)  # 多分类模式
    sort_mode_changed = pyqtSignal(str, bool)  # 排序模式, 升序

    def __init__(
        self,
        state: StateViewType,
        mutator: StateMutatorType,
        ui: UIHooksType,
        navigator: ImageNavigatorType,
        file_ops: "FileOperationManager",
        logger: logging.Logger,
    ) -> None:
        """
        初始化类别管理器

        Args:
            state: 只读状态接口
            mutator: 状态修改接口
            ui: UI回调接口
            navigator: 图片导航接口
            file_ops: 文件操作管理器
            logger: 日志记录器
        """
        super().__init__()
        self._state = state
        self._mutator = mutator
        self._ui = ui
        self._navigator = navigator
        self._file_ops = file_ops
        self._logger = logger

        self._current_category_index: int = 0
        self._category_buttons: List[object] = []

    # ========== 公共接口 ==========

    def load_categories(self) -> None:
        """加载类别并刷新按钮、计数、排序"""
        self._load_categories_only()
        self._rebuild_category_buttons()

    def add_category(self, name: str) -> bool:
        """
        添加类别：创建目录、写入配置、刷新列表

        Args:
            name: 类别名称

        Returns:
            成功返回 True
        """
        if not self._ensure_base_dir():
            return False
        parent_dir = self._state.current_dir.parent
        target_dir = parent_dir / name
        if target_dir.exists():
            self._logger.warning(f"类别已存在: {name}")
            self._ui.show_toast('warning', f"类别 '{name}' 已存在")
            return False
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            self._mutator.add_category(name)
            self._state.config.assign_default_shortcuts(self._state.categories | {name})

            # 保存配置（容错）
            try:
                self._state.config.save_config()
            except Exception as save_error:
                self._logger.warning(f"添加类别后保存配置失败（操作已完成）: {save_error}")

            self._resort_categories()
            self._rebuild_category_buttons()
            self.categories_changed.emit(list(self._state.ordered_categories))
            self._ui.show_toast('success', f"已添加类别: {name}")
            return True
        except Exception as e:
            self._logger.error(f"添加类别失败: {e}")
            self._ui.show_toast('error', f"添加类别失败: {e}")
            return False

    def delete_category(self, name: str) -> bool:
        """
        删除类别目录并清理状态

        Args:
            name: 类别名称

        Returns:
            成功返回 True
        """
        if not self._ensure_base_dir():
            return False
        parent_dir = self._state.current_dir.parent
        category_path = parent_dir / name
        if not category_path.exists():
            self._logger.warning(f"类别目录不存在: {name}")
            return False

        # 统计目录中的图片数量
        image_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', '.webp'}
        image_count = 0
        if category_path.is_dir():
            for file_path in category_path.iterdir():
                if file_path.is_file() and file_path.suffix.lower() in image_extensions:
                    image_count += 1

        # 确认对话框（根据图片数量显示不同消息）
        if image_count > 0:
            msg = f"类别目录 '{name}' 中有 {image_count} 张图片文件。\n\n确认删除这个类别目录吗？\n这将永久删除目录及其中的所有文件！"
        else:
            msg = f"确定要删除空的类别目录 '{name}' 吗？"

        if not self._ui.show_question("删除类别", msg):
            return False

        try:
            # 收集需要从分类记录中移除的图片路径（用于移动模式）
            affected_paths = []
            for img_path, category in self._state.classified_images.items():
                if isinstance(category, str) and category == name:
                    affected_paths.append(img_path)
                elif isinstance(category, list) and name in category:
                    # 多分类：如果是该类别的唯一分类，则纳入受影响列表
                    if len(category) == 1:
                        affected_paths.append(img_path)

            # 删除目录
            shutil.rmtree(str(category_path))
            self._cleanup_category_state(name)
            self._mutator.remove_category(name)  # 从 categories 集合中移除
            self._state.config.category_shortcuts.pop(name, None)

            # 保存配置（容错：即使保存失败，删除操作也已完成）
            try:
                self._state.config.save_config()
            except Exception as save_error:
                self._logger.warning(f"删除类别后保存配置失败（操作已完成）: {save_error}")
                # 不抛出异常，让删除操作继续完成

            # 移动模式：从图片文件列表中移除不存在的图片
            if not self._state.is_copy_mode and affected_paths:
                files_to_remove = []
                for img_path in affected_paths:
                    img_file = Path(img_path)
                    # 检查原目录中是否还有这个文件
                    if not img_file.exists():
                        files_to_remove.append(img_path)

                if files_to_remove:
                    # 更新图片文件列表
                    current_files = list(self._state.image_files)
                    new_files = [f for f in current_files if str(f) not in files_to_remove]
                    self._mutator.set_image_files(new_files)

                    # 调整当前索引（空列表时设为-1）
                    if not new_files:
                        self._mutator.set_current_index(-1)
                    elif self._state.current_index >= len(new_files):
                        self._mutator.set_current_index(len(new_files) - 1)

                    self._logger.info(f"移动模式下删除类别，从图片列表中移除了 {len(files_to_remove)} 张图片")

            # 保存状态（容错：即使保存失败，操作也已完成）
            try:
                self._ui.save_state()
            except Exception as save_error:
                self._logger.warning(f"删除类别后保存状态失败（操作已完成）: {save_error}")
                # 不抛出异常，让删除操作继续完成

            # 刷新过滤视图（分类记录已清理，需重算可见列表）
            self._ui.apply_image_filter()

            self._resort_categories()
            self._rebuild_category_buttons()
            self.categories_changed.emit(list(self._state.ordered_categories))

            # 调度UI刷新
            self._ui.schedule_ui_update('image_list', 'category_buttons', 'category_counts', 'statistics')

            # 移动模式下如果还有图片，显示更新后的当前图片
            if not self._state.is_copy_mode and self._state.image_files and self._state.current_index >= 0:
                self._navigator.show_current_image()

            self._ui.show_toast('success', f"已删除类别: {name}")
            return True
        except Exception as e:
            self._logger.error(f"删除类别失败: {e}")
            self._ui.show_toast('error', f"删除类别失败: {e}")
            return False

    def rename_category(self, old_name: str, new_name: str) -> bool:
        """
        重命名类别目录及配置映射

        Args:
            old_name: 原类别名
            new_name: 新类别名

        Returns:
            成功返回 True
        """
        if not self._ensure_base_dir():
            return False
        parent_dir = self._state.current_dir.parent
        old_path = parent_dir / old_name
        new_path = parent_dir / new_name
        if not old_path.exists():
            self._logger.warning(f"原类别不存在: {old_name}")
            return False
        if new_path.exists():
            self._logger.warning(f"目标类别已存在: {new_name}")
            self._ui.show_toast('warning', f"类别 '{new_name}' 已存在")
            return False
        try:
            old_path.rename(new_path)
            # 更新 categories 集合
            self._mutator.remove_category(old_name)
            self._mutator.add_category(new_name)
            # 更新快捷键映射
            if old_name in self._state.config.category_shortcuts:
                shortcut = self._state.config.category_shortcuts.pop(old_name)
                self._state.config.category_shortcuts[new_name] = shortcut
            # 更新分类记录
            self._rename_classified_records(old_name, new_name)
            self._state.config.save_config()
            self._resort_categories()
            self._rebuild_category_buttons()
            self.categories_changed.emit(list(self._state.ordered_categories))
            self._ui.show_toast('success', f"已重命名: {old_name} -> {new_name}")
            return True
        except Exception as e:
            self._logger.error(f"重命名类别失败: {e}")
            self._ui.show_toast('error', f"重命名失败: {e}")
            return False

    def ignore_category(self, name: str) -> bool:
        """
        将类别加入忽略列表并清理状态

        Args:
            name: 类别名称

        Returns:
            成功返回 True
        """
        if not self._ensure_base_dir():
            return False
        added = self._state.config.add_ignored_category(name)
        if not added:
            self._logger.info(f"类别已在忽略列表中: {name}")
            return False
        self._state.config.category_shortcuts.pop(name, None)
        self._cleanup_category_state(name)
        self._state.config.save_config()
        self._resort_categories()
        self._rebuild_category_buttons()
        self.categories_changed.emit(list(self._state.ordered_categories))
        self._ui.show_toast('info', f"已忽略类别: {name}")
        return True

    def change_category_sort_mode(self, new_mode: str, ascending: Optional[bool] = None) -> None:
        """
        切换排序模式/方向并重建按钮

        Args:
            new_mode: 排序模式（'name', 'shortcut', 'count'）
            ascending: 是否升序（None表示保持当前）
        """
        if new_mode not in ["name", "shortcut", "count"]:
            self._logger.error(f"非法排序模式: {new_mode}")
            return
        if ascending is not None:
            self._state.config.sort_ascending = ascending
        self._state.config.category_sort_mode = new_mode
        self._state.config.save_config()
        self._resort_categories()
        self._rebuild_category_buttons()
        self.sort_mode_changed.emit(new_mode, self._state.config.sort_ascending)

    def toggle_category_mode(self) -> bool:
        """
        切换单/多分类模式

        Returns:
            新的模式值
        """
        if not self._state.is_copy_mode and not self._state.is_multi_category:
            self._logger.warning("移动模式不支持多分类")
            self._ui.show_toast('warning', "移动模式不支持多分类")
            return self._state.is_multi_category
        new_mode = not self._state.is_multi_category
        self._mutator.set_multi_category(new_mode)
        self._ui.save_state()
        self.mode_changed.emit(new_mode)
        self._ui.refresh_category_buttons_style()
        mode_text = "多分类" if new_mode else "单分类"
        self._ui.show_toast('info', f"已切换到{mode_text}模式")
        return new_mode

    def select_category(self, name: str) -> None:
        """
        选中指定类别并高亮

        Args:
            name: 类别名称
        """
        if name not in self._state.ordered_categories:
            return
        self._current_category_index = list(self._state.ordered_categories).index(name)
        self._mutator.set_current_category_index(self._current_category_index)
        self._mutator.set_selected_category(name)
        self.selection_changed.emit(self._current_category_index, name)
        self._ui.highlight_category_button(self._current_category_index)
        self._ui.ensure_category_visible(self._current_category_index)

    def prev_category(self) -> None:
        """选中上一类别（循环）"""
        if not self._state.ordered_categories:
            return
        self._current_category_index = (self._current_category_index - 1) % len(self._state.ordered_categories)
        name = self._state.ordered_categories[self._current_category_index]
        self.select_category(name)

    def next_category(self) -> None:
        """选中下一类别（循环）"""
        if not self._state.ordered_categories:
            return
        self._current_category_index = (self._current_category_index + 1) % len(self._state.ordered_categories)
        name = self._state.ordered_categories[self._current_category_index]
        self.select_category(name)

    def confirm_category(self) -> None:
        """确认当前选中的类别并执行分类"""
        if not self._state.ordered_categories:
            return
        if not (0 <= self._current_category_index < len(self._state.ordered_categories)):
            return
        category_name = self._state.ordered_categories[self._current_category_index]
        self._classify_current_image(category_name)

    def get_category_counts(self, categories_only: Optional[Set[str]] = None) -> Dict[str, int]:
        """
        统计类别计数

        Args:
            categories_only: 仅统计指定集合（None表示所有）

        Returns:
            类别计数字典
        """
        categories = categories_only or self._state.categories
        counts: Dict[str, int] = {}
        for img_path, category in self._state.classified_images.items():
            if isinstance(category, list):
                for cat in category:
                    if cat in categories:
                        counts[cat] = counts.get(cat, 0) + 1
            else:
                if category in categories:
                    counts[category] = counts.get(category, 0) + 1
        return counts

    # ========== 内部实现 ==========

    def _ensure_base_dir(self) -> bool:
        """检查当前目录是否已设置"""
        if not self._state.current_dir:
            self._logger.warning("当前目录未设置，无法进行类别操作")
            return False
        return True

    def _load_categories_only(self) -> None:
        """扫描目录、同步配置并排序"""
        if not self._ensure_base_dir():
            return
        parent_dir = self._state.current_dir.parent
        categories: Set[str] = set()
        removed: List[str] = []
        try:
            # 清理忽略列表中已不存在的目录
            ignored_removed = []
            for name in list(self._state.config.ignored_categories):
                if not (parent_dir / name).is_dir():
                    ignored_removed.append(name)

            config_needs_save = False  # 标志：是否需要保存配置

            if ignored_removed:
                for name in ignored_removed:
                    self._state.config.remove_ignored_category(name)
                config_needs_save = True  # 标记需要保存，但延迟到末尾统一保存
                self._logger.info(f"已移除不存在的忽略类别: {', '.join(ignored_removed)}")

            for item in parent_dir.iterdir():
                if not item.is_dir():
                    continue
                # 跳过保留目录
                if item.name in self._state.config.reserved_categories:
                    continue
                # 跳过当前图片目录
                if item == self._state.current_dir:
                    continue
                # 跳过忽略的类别
                if self._state.config.is_category_ignored(item.name):
                    continue
                categories.add(item.name)

            # 检查快捷键映射中的类别是否仍存在
            for name in set(self._state.config.category_shortcuts.keys()):
                if (parent_dir / name).is_dir():
                    categories.add(name)
                else:
                    removed.append(name)

            # 【BUG修复】检查 classified_images 中所有被引用的类别是否存在
            # 收集所有被引用的类别
            referenced_categories: Set[str] = set()
            for category in self._state.classified_images.values():
                if isinstance(category, str):
                    referenced_categories.add(category)
                elif isinstance(category, list):
                    referenced_categories.update(category)

            # 检查被引用的类别是否存在（排除已经在removed中的）
            for name in referenced_categories:
                if name not in removed and not (parent_dir / name).is_dir():
                    removed.append(name)
                    self._logger.warning(f"检测到不存在的类别引用: {name}，将清理相关分类记录")

            state_changed = False

            # 清理不存在的类别
            for name in removed:
                self._state.config.category_shortcuts.pop(name, None)
                self._cleanup_category_state(name)
                state_changed = True
                config_needs_save = True  # 快捷键映射变化，需要保存配置

            if state_changed:
                # 分类记录变动后落盘：启动阶段可能被占用，失败则延迟重试
                try:
                    self._ui.save_state()
                except Exception as e:
                    if isinstance(e, PermissionError) or "Permission denied" in str(e):
                        self._logger.warning("状态文件被占用，500ms后重试保存")
                        # 包装成 lambda 捕获异常
                        QTimer.singleShot(500, lambda: self._safe_save_state())
                    else:
                        raise
                # 注意：UI刷新由后续的categories_changed信号触发，避免重复刷新

            # 分配默认快捷键并排序
            self._state.config.assign_default_shortcuts(categories)
            counts = self.get_category_counts(categories_only=categories) if self._state.config.category_sort_mode == "count" else None
            ordered = self._state.config.get_sorted_categories(categories, category_counts=counts)

            self._mutator.set_categories(categories)
            self._mutator.set_ordered_categories(ordered)

            # 统一保存配置（只在末尾保存一次，避免重复）
            if config_needs_save:
                try:
                    self._state.config.save_config()
                except Exception as e:
                    if isinstance(e, PermissionError) or "Permission denied" in str(e):
                        # 防重入：检查是否已有待处理的重试
                        if not getattr(self._state.config, '_save_pending', False):
                            self._logger.warning("配置文件被占用，500ms后重试保存")
                            self._state.config._save_pending = True
                            # 重试时清除 pending 标志
                            def retry_save():
                                self._state.config._save_pending = False
                                self._safe_save_config()
                            QTimer.singleShot(500, retry_save)
                        else:
                            self._logger.debug("已有待处理的保存重试，跳过本次重试")
                    else:
                        raise

            # 初始化选中状态（修复Codex Review中等问题）
            self._current_category_index = 0
            if ordered:
                self._mutator.set_current_category_index(0)
                self._mutator.set_selected_category(ordered[0])

            self.categories_changed.emit(list(ordered))
        except Exception as e:
            self._logger.error(f"加载类别失败: {e}")
            self._mutator.set_categories(set())
            self._mutator.set_ordered_categories([])

    def _resort_categories(self) -> None:
        """重新排序类别列表"""
        counts = self.get_category_counts() if self._state.config.category_sort_mode == "count" else None
        ordered = self._state.config.get_sorted_categories(self._state.categories, category_counts=counts)
        self._mutator.set_ordered_categories(ordered)

    def _rebuild_category_buttons(self) -> None:
        """根据当前 ordered_categories 重建按钮并绑定事件"""
        self._ui.clear_category_buttons()
        layout = self._ui.get_category_button_layout()
        if layout is None:
            return
        self._category_buttons.clear()
        counts = self.get_category_counts()
        shortcuts = self._state.config.category_shortcuts

        for idx, name in enumerate(self._state.ordered_categories):
            shortcut = shortcuts.get(name)
            btn = self._ui.create_category_button(name, shortcut, counts.get(name, 0))
            if btn is not None:
                # 按钮点击触发选中并确认分类
                try:
                    btn.clicked.connect(lambda checked=False, n=name: self._on_button_clicked(n))
                except Exception:
                    pass
                layout.addWidget(btn)
                self._category_buttons.append(btn)
                if idx == self._current_category_index:
                    self._ui.highlight_category_button(idx)

        self._ui.refresh_category_buttons_style()

    def _on_button_clicked(self, name: str) -> None:
        """按钮点击处理"""
        self.select_category(name)
        self.confirm_category()

    def _classify_current_image(self, category_name: str) -> None:
        """
        执行当前图片的分类操作

        流程：
        1. 委托给FileOperationManager执行分类（已处理状态更新、保存、UI刷新）
        2. 更新last_operation_category
        3. 刷新过滤列表（分类后状态变化，需重算可见列表）
        4. 单分类模式下自动跳转到下一张
        5. 多分类模式下更新类别选择状态
        6. 发射selection_changed信号

        Args:
            category_name: 目标类别名
        """
        if not self._state.image_files or self._state.current_index < 0:
            return
        if not (0 <= self._state.current_index < len(self._state.image_files)):
            return

        image_path = self._state.image_files[self._state.current_index]
        file_path = str(image_path)
        original_index = self._state.current_index

        try:
            # 委托给FileOperationManager执行分类
            # FileOperationManager.move_to_category()已处理：
            # - 单/多分类状态更新（classified_images）
            # - 保存状态（save_state）
            # - UI刷新（schedule_ui_update, refresh_category_buttons_style）
            # - 文件物理搬运
            self._file_ops.move_to_category(file_path, category_name)

            # 更新最后操作的类别
            self._mutator.set_last_operation_category(category_name)

            # 刷新过滤列表（分类后状态变化，需重算可见列表）
            self._ui.apply_image_filter()

            # 根据分类模式处理导航和UI
            if not self._state.is_multi_category:
                # 单分类模式：自动跳转到下一张
                self._navigator.select_after_removal(original_index)
            else:
                # 多分类模式：保持当前图片，更新类别选择状态
                self._ui.update_category_selection()

            # 发射选中变化信号
            self.selection_changed.emit(self._current_category_index, category_name)

        except Exception as e:
            self._logger.error(f"分类失败: {e}")
            self._ui.show_toast('error', f"分类失败: {e}")

    def _cleanup_category_state(self, name: str) -> None:
        """
        清理指定类别的分类记录

        Args:
            name: 类别名称
        """
        to_remove = []
        for img_path, category in self._state.classified_images.items():
            if isinstance(category, str) and category == name:
                to_remove.append(img_path)
            elif isinstance(category, list) and name in category:
                new_list = [c for c in category if c != name]
                if new_list:
                    self._mutator.set_classified_image(img_path, new_list)
                else:
                    to_remove.append(img_path)
        for path in to_remove:
            self._mutator.remove_classified_image(path)

    def _rename_classified_records(self, old_name: str, new_name: str) -> None:
        """
        更新分类记录中的类别名

        Args:
            old_name: 原类别名
            new_name: 新类别名
        """
        updates: Dict[str, Union[str, List[str]]] = {}
        for img_path, category in self._state.classified_images.items():
            if isinstance(category, str) and category == old_name:
                updates[img_path] = new_name
            elif isinstance(category, list) and old_name in category:
                new_list = [new_name if c == old_name else c for c in category]
                updates[img_path] = new_list
        for img_path, new_value in updates.items():
            self._mutator.set_classified_image(img_path, new_value)

    def _safe_save_config(self):
        """安全保存配置（捕获异常，避免CRITICAL错误）"""
        try:
            self._state.config.save_config()
            self._logger.debug("重试保存配置成功")
        except Exception as e:
            self._logger.error(f"重试保存配置失败（可能被外部程序占用）: {e}")
            # 捕获异常，不再抛出，避免未捕获异常导致程序崩溃

    def _safe_save_state(self):
        """安全保存状态（捕获异常，避免CRITICAL错误）"""
        try:
            self._ui.save_state()
            self._logger.debug("重试保存状态成功")
        except Exception as e:
            self._logger.error(f"重试保存状态失败（可能被外部程序占用）: {e}")
            # 捕获异常，不再抛出
