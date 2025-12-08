"""
图片导航管理器

负责图片浏览、翻页、跳转、预加载等导航相关功能。
通过依赖注入接收状态接口和 UI 回调，避免直接访问主窗口（消除 Parent Reaching 反模式）。

设计理念（Task 2.2，2025-12-04）：
- 从 main_window.py 提取导航相关方法（load_images, prev_image, next_image 等）
- 使用 StateView/StateMutator/UIHooks/ImageLoader 接口访问状态和触发 UI 更新
- Manager 内部维护临时状态（防重入标志、翻页方向历史）
- 通过回调处理跨 Manager 调用（如 category_selection_callback）

Codex Review 修复（2025-12-04）：
- 修复状态加载逻辑（通过注入的 load_state_callback）
- 保留 sync_image_list_selection 的索引映射和滚动逻辑
- 修复循环翻页配置（区分本地/网络路径）
- 发射 image_changed 信号
- 补充 _show_current_image_internal 的完整逻辑
"""

from pathlib import Path
from typing import List, Optional, Callable, Set, Dict, Union, TYPE_CHECKING
from PyQt6.QtCore import QObject, pyqtSignal, QTimer
import logging

from .._main_window.state.interfaces import StateView, StateMutator, UIHooks, ImageLoader

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QListView, QAbstractItemView
    from PyQt6.QtCore import QAbstractItemModel, QItemSelectionModel


class ImageNavigationManager(QObject):
    """
    图片导航管理器

    职责：
    - 加载目录下的图片文件（通过 FileScanner）
    - 显示当前图片、翻页（上一张/下一张）、跳转到指定索引
    - 智能预加载相邻图片
    - 同步图片列表的选中状态
    - 支持过滤列表导航和循环翻页
    """

    # 信号：图片索引变化
    image_changed = pyqtSignal(int)

    def __init__(
        self,
        state: StateView,
        mutator: StateMutator,
        ui: UIHooks,
        loader: ImageLoader,
        scanner,  # FileScanner 类型（避免循环导入）
        image_list: "QListView",  # 图片列表控件
        image_list_model: "QAbstractItemModel",  # 列表模型
        get_visible_indices: Callable[[], Optional[List[int]]],  # 获取过滤后的可见索引（None表示未过滤）
        get_original_to_filtered_index: Callable[[], Optional[Dict[int, int]]],  # 获取原始索引到过滤索引的映射
        update_category_selection_callback: Optional[Callable[[str], None]] = None,  # 更新类别选中状态（传入字符串路径）
        load_state_callback: Optional[Callable[[], None]] = None,  # 加载状态文件的回调
        log_image_info_callback: Optional[Callable[[str], None]] = None,  # 记录图片信息的回调
        log_performance_info_callback: Optional[Callable[[str, ...], None]] = None,  # 记录性能信息的回调
        is_network_path_callback: Optional[Callable[[str], bool]] = None,  # 判断是否为网络路径
        show_loading_placeholder_callback: Optional[Callable[[str], None]] = None,  # 显示加载占位符（传入路径）
        logger: Optional[logging.Logger] = None
    ):
        """
        初始化图片导航管理器

        Args:
            state: 状态只读接口
            mutator: 状态修改接口
            ui: UI 回调接口
            loader: 图片加载器接口
            scanner: 文件扫描器
            image_list: 图片列表控件
            image_list_model: 列表模型
            get_visible_indices: 获取过滤后的可见索引（None表示未过滤）
            get_original_to_filtered_index: 获取原始索引到过滤索引的映射
            update_category_selection_callback: 更新类别选中状态
            load_state_callback: 加载状态文件的回调
            log_image_info_callback: 记录图片信息的回调
            log_performance_info_callback: 记录性能信息的回调
            is_network_path_callback: 判断是否为网络路径
            show_loading_placeholder_callback: 显示加载占位符
            logger: 日志记录器
        """
        super().__init__()

        # 依赖注入
        self._state = state
        self._mutator = mutator
        self._ui = ui
        self._loader = loader
        self._scanner = scanner
        self._image_list = image_list
        self._image_list_model = image_list_model
        self._get_visible_indices = get_visible_indices
        self._get_original_to_filtered_index = get_original_to_filtered_index
        self._update_category_selection = update_category_selection_callback
        self._load_state = load_state_callback
        self._log_image_info = log_image_info_callback
        self._log_performance_info = log_performance_info_callback
        self._is_network_path = is_network_path_callback
        self._show_loading_placeholder = show_loading_placeholder_callback
        self._logger = logger or logging.getLogger(__name__)

        # 内部状态
        self._showing_image = False  # 防重入标志
        self._user_behavior: Dict = {}  # 用户行为记录（翻页方向历史等）

        # 临时状态（用于加载过程）
        self._loading_in_progress = False
        self._initial_batch_loaded = False
        self._background_loading = False
        self._current_requested_image: Optional[str] = None  # 当前请求加载的图片路径（用于异步加载验证）

        # 连接文件扫描器信号
        self._scanner.initial_batch_ready.connect(self.on_initial_batch_ready)
        self._scanner.scan_progress.connect(self._on_scan_progress)

    # ========== 图片加载 ==========

    def load_images(self):
        """开始智能加载目录下的图片"""
        current_dir = self._state.current_dir
        if not current_dir:
            return

        self._logger.info(f"开始加载图片目录: {current_dir}")

        # 清理图片缓存
        self._loader.clear_cache()

        # 清空分类状态缓存（关键修复：重新加载目录时清除内存中的旧状态）
        self._mutator.set_classified_images({})
        self._mutator.set_removed_images(set())

        # 重置状态
        self._mutator.set_all_image_files([])
        self._mutator.set_image_files([])
        self._mutator.set_current_index(-1)

        self._loading_in_progress = True
        self._initial_batch_loaded = False
        self._background_loading = False

        # 显示加载提示
        self._ui.update_status_bar("🔍 正在后台扫描图片文件...")

        # 启动智能文件扫描
        self._scanner.scan_directory(current_dir)

    def on_initial_batch_ready(self, initial_files: List[Path]):
        """处理初始批次文件"""
        if not self._loading_in_progress:
            return

        self._logger.info(f"接收到初始批次: {len(initial_files)} 个文件")

        # 设置初始显示文件
        self._mutator.set_image_files(initial_files.copy())
        self._mutator.set_all_image_files(initial_files.copy())
        self._mutator.set_current_index(0 if initial_files else -1)

        self._initial_batch_loaded = True

        # 设置图片加载器的文件列表引用
        self._loader.set_image_files_reference(initial_files)

        # 立即完全启用UI
        self._loading_in_progress = False

        # 异步加载状态文件，避免阻塞UI
        if self._load_state:
            QTimer.singleShot(50, self._delayed_load_state)

        # 立即更新UI组件（不包括current_image，避免重复刷新）
        self._ui.schedule_ui_update('image_list', 'statistics', 'ui_state')

        # 立即显示成功信息
        current_dir = self._state.current_dir
        path_str = str(current_dir) if current_dir else ""
        is_network_path = self._state.is_network_path
        location_type = "网络路径" if is_network_path else "本地路径"

        self._ui.update_status_bar(f"✅ {location_type}已就绪 {len(initial_files)} 张图片，后台继续扫描...")

        # 后台标记：程序已可用，全量扫描在后台继续
        self._background_loading = True

        self._logger.info("🚀 程序UI已完全启用，用户可立即使用")

    def _delayed_load_state(self):
        """延迟加载状态文件，避免阻塞UI"""
        try:
            if self._load_state:
                self._load_state()
                self._logger.debug("状态文件异步加载完成")
        except Exception as e:
            self._logger.error(f"延迟加载状态文件失败: {e}")

    def _on_scan_progress(self, message: str):
        """处理扫描进度（更新状态栏）"""
        self._ui.update_status_bar(message)

    # ========== 图片显示 ==========

    def show_current_image(self):
        """显示当前图片 - 防止多图刷新"""
        # 防重入检查，避免多次触发
        if self._showing_image:
            return

        self._showing_image = True
        try:
            # 直接调用内部方法，避免额外的事件处理
            self._show_current_image_internal()

            # 仅异步更新UI状态，避免阻塞
            QTimer.singleShot(10, lambda: self._ui.schedule_ui_update('ui_state'))
        finally:
            self._showing_image = False

    def _show_current_image_internal(self):
        """内部显示当前图片方法 - 保持与原 main_window 逻辑一致"""
        image_files = self._state.image_files
        current_index = self._state.current_index

        if 0 <= current_index < len(image_files):
            img_path = str(image_files[current_index])

            # 计算文件的实际路径（根据操作模式和分类状态）
            real_path = str(self._state.get_real_file_path(Path(img_path)))

            # 记录图片文件信息（使用真实路径）
            if self._log_image_info:
                self._log_image_info(real_path)

            # 立即更新窗口标题（传入路径参数）
            self._ui.update_window_title(Path(img_path))

            # 设置当前图片索引用于智能缓存
            self._loader.set_current_image_index(current_index)

            # 检查缓存命中情况（使用真实路径）
            is_cached = self._loader.is_cached(Path(real_path))

            # 记录性能信息
            if self._log_performance_info:
                self._log_performance_info(
                    "显示图片_开始",
                    f"文件={Path(img_path).name}",
                    f"索引={current_index + 1}/{len(image_files)}",
                    f"缓存命中={is_cached}"
                )

            # 检查当前图片的分类状态并更新类别选择
            if self._update_category_selection:
                self._update_category_selection(img_path)

            # 记录当前请求的图片路径（用于回调时判断）
            self._current_requested_image = str(Path(real_path).resolve())

            # 如果缓存命中，直接显示；否则显示占位符
            if is_cached:
                # 直接从缓存加载，避免闪烁
                cached_data = self._loader.get_from_cache(Path(real_path))
                if cached_data is not None:
                    # 通过 UIHooks 显示（支持 numpy 数组或 QPixmap）
                    self._ui.display_image(cached_data, Path(real_path))
                    self._ui.update_status_bar(f"📷 {Path(img_path).name}")
                else:
                    # 缓存失效，显示占位符并异步加载
                    if self._show_loading_placeholder:
                        self._show_loading_placeholder(img_path)
                    else:
                        self._ui.show_loading_placeholder()
            else:
                # 显示占位符，异步加载图片
                if self._show_loading_placeholder:
                    self._show_loading_placeholder(img_path)
                else:
                    self._ui.show_loading_placeholder()

            # 异步加载完整图片（使用真实路径）
            self._loader.load_image(Path(real_path), priority=True)

            # 延迟预加载相邻图片，避免影响当前图片显示
            is_network_current = self._is_network_path(img_path) if self._is_network_path else False
            delay_time = 300 if is_network_current else 100

            QTimer.singleShot(delay_time, self.preload_adjacent_images)

            # 延迟更新图片列表高亮选中状态，避免阻塞当前图片显示
            QTimer.singleShot(50, self.sync_image_list_selection)

            # 调度UI状态更新
            self._ui.schedule_ui_update('ui_state')
        else:
            # 无效索引，显示占位符
            self._ui.show_loading_placeholder()

    # ========== 图片翻页 ==========

    def prev_image(self):
        """上一张图片（支持循环翻页、过滤列表导航）"""
        image_files = self._state.image_files
        current_index = self._state.current_index

        # Codex最终Review修复：区分"未过滤"和"过滤结果为空"
        visible_indices = self._get_visible_indices()

        if visible_indices is not None:
            # 过滤已激活
            if not visible_indices:
                # 过滤结果为空，不允许导航
                self._ui.show_toast('info', "当前过滤条件下没有图片")
                return

            # 有可见图片：在可见列表中导航
            try:
                current_pos = visible_indices.index(current_index)
                if current_pos > 0:
                    # 移动到上一张可见图片
                    self._mutator.set_current_index(visible_indices[current_pos - 1])
                    self._record_direction(-1)
                    self.image_changed.emit(visible_indices[current_pos - 1])
                    self.show_current_image()
                else:
                    # 已经是第一张可见图片
                    loop_enabled = self._should_enable_loop()
                    if loop_enabled:
                        # 循环到最后一张可见图片
                        self._mutator.set_current_index(visible_indices[-1])
                        self._logger.debug(f"[循环翻页-过滤] 第1张可见 -> 第{len(visible_indices)}张可见")
                        self.image_changed.emit(visible_indices[-1])
                        self.show_current_image()
                    else:
                        self._ui.show_toast('info', "已经是第一张图片了！")
            except ValueError:
                # 当前图片不在可见列表中（被过滤掉了）
                # 找到当前索引之前的最后一张可见图片（而不是跳到第一张）
                prev_visible = None
                for idx in reversed(visible_indices):
                    if idx < current_index:
                        prev_visible = idx
                        break

                if prev_visible is not None:
                    # 找到了上一张可见图片
                    self._mutator.set_current_index(prev_visible)
                    self.image_changed.emit(prev_visible)
                    self.show_current_image()
                else:
                    # 当前索引之前没有可见图片了
                    loop_enabled = self._should_enable_loop()
                    if loop_enabled:
                        # 循环到最后一张可见图片
                        self._mutator.set_current_index(visible_indices[-1])
                        self.image_changed.emit(visible_indices[-1])
                        self.show_current_image()
                    else:
                        self._ui.show_toast('info', "已经是第一张图片了！")
        else:
            # 没有过滤：原始逻辑
            if current_index > 0:
                self._mutator.set_current_index(current_index - 1)
                self._record_direction(-1)
                self.image_changed.emit(current_index - 1)
                self.show_current_image()
            else:
                loop_enabled = self._should_enable_loop()
                if loop_enabled:
                    new_index = len(image_files) - 1
                    self._mutator.set_current_index(new_index)
                    self._logger.debug(f"[循环翻页] 第1张 -> 第{new_index + 1}张（最后一张）")
                    self.image_changed.emit(new_index)
                    self.show_current_image()
                else:
                    self._ui.show_toast('info', "已经是第一张图片了！")

    def next_image(self):
        """下一张图片（支持循环翻页、过滤列表导航）"""
        image_files = self._state.image_files
        current_index = self._state.current_index

        # Codex最终Review修复：区分"未过滤"和"过滤结果为空"
        visible_indices = self._get_visible_indices()

        if visible_indices is not None:
            # 过滤已激活
            if not visible_indices:
                # 过滤结果为空，不允许导航
                self._ui.show_toast('info', "当前过滤条件下没有图片")
                return

            # 有可见图片：在可见列表中导航
            try:
                current_pos = visible_indices.index(current_index)
                if current_pos < len(visible_indices) - 1:
                    # 移动到下一张可见图片
                    self._mutator.set_current_index(visible_indices[current_pos + 1])
                    self._record_direction(1)
                    self.image_changed.emit(visible_indices[current_pos + 1])
                    self.show_current_image()
                else:
                    # 已经是最后一张可见图片
                    loop_enabled = self._should_enable_loop()
                    if loop_enabled:
                        # 循环到第一张可见图片
                        self._mutator.set_current_index(visible_indices[0])
                        self._logger.debug(f"[循环翻页-过滤] 第{len(visible_indices)}张可见 -> 第1张可见")
                        self.image_changed.emit(visible_indices[0])
                        self.show_current_image()
                    else:
                        self._ui.show_toast('info', "已经是最后一张图片了！")
            except ValueError:
                # 当前图片不在可见列表中（被过滤掉了）
                # 找到当前索引之后的第一张可见图片（而不是跳到第一张）
                next_visible = None
                for idx in visible_indices:
                    if idx > current_index:
                        next_visible = idx
                        break

                if next_visible is not None:
                    # 找到了下一张可见图片
                    self._mutator.set_current_index(next_visible)
                    self.image_changed.emit(next_visible)
                    self.show_current_image()
                else:
                    # 当前索引之后没有可见图片了
                    loop_enabled = self._should_enable_loop()
                    if loop_enabled:
                        # 循环到第一张可见图片
                        self._mutator.set_current_index(visible_indices[0])
                        self.image_changed.emit(visible_indices[0])
                        self.show_current_image()
                    else:
                        self._ui.show_toast('info', "已经是最后一张图片了！")
        else:
            # 没有过滤：原始逻辑
            if current_index < len(image_files) - 1:
                self._mutator.set_current_index(current_index + 1)
                self._record_direction(1)
                self.image_changed.emit(current_index + 1)
                self.show_current_image()
            else:
                loop_enabled = self._should_enable_loop()
                if loop_enabled:
                    self._mutator.set_current_index(0)
                    self._logger.debug(f"[循环翻页] 第{len(image_files)}张（最后一张） -> 第1张")
                    self.image_changed.emit(0)
                    self.show_current_image()
                else:
                    self._ui.show_toast('info', "已经是最后一张图片了！")

    def _record_direction(self, direction: int):
        """记录翻页方向（优化3：智能预加载）

        Args:
            direction: 1=向前（下一张），-1=向后（上一张）
        """
        if 'direction_history' not in self._user_behavior:
            self._user_behavior['direction_history'] = []

        self._user_behavior['direction_history'].append(direction)

        # 只保留最近10次
        if len(self._user_behavior['direction_history']) > 10:
            self._user_behavior['direction_history'] = self._user_behavior['direction_history'][-10:]

    def _should_enable_loop(self) -> bool:
        """判断当前是否应该启用循环翻页（保持与原逻辑一致）"""
        try:
            # 动态刷新配置，确保开关即时生效（避免重启才能应用）
            app_config = self._state.app_config
            if hasattr(app_config, 'reload_config'):
                app_config.reload_config()
        except Exception as e:
            self._logger.debug(f"[循环翻页] 刷新配置失败: {e}")

        # 检查是否为网络路径
        is_network = self._state.is_network_path

        app_config = self._state.app_config
        if is_network:
            # 网络路径：使用网络循环开关
            loop_enabled = getattr(app_config, 'network_loop_enabled', True) if app_config else True
            self._logger.debug(f"[循环翻页] 网络路径，循环开关：{'开启' if loop_enabled else '关闭'}")
            return loop_enabled
        else:
            # 本地路径：使用本地循环开关
            loop_enabled = getattr(app_config, 'local_loop_enabled', True) if app_config else True
            self._logger.debug(f"[循环翻页] 本地路径，循环开关：{'开启' if loop_enabled else '关闭'}")
            return loop_enabled

    # ========== 图片跳转 ==========

    def jump_to_image(self, index: int):
        """跳转到指定索引的图片

        Args:
            index: 目标图片的索引（0-based）
        """
        try:
            image_files = self._state.image_files

            if not image_files or index < 0 or index >= len(image_files):
                self._logger.warning(f"无效的图片索引: {index}, 总图片数: {len(image_files) if image_files else 0}")
                return

            # 设置当前索引
            self._mutator.set_current_index(index)
            self._logger.info(f"跳转到图片索引: {index} / {len(image_files)}")

            # 发射信号
            self.image_changed.emit(index)

            # 显示图片
            self.show_current_image()

            # 同步图片列表选中状态
            self.sync_image_list_selection()

        except Exception as e:
            self._logger.error(f"跳转到图片索引 {index} 失败: {e}")

    # ========== 列表同步 ==========

    def sync_image_list_selection(self):
        """同步图片列表的选中状态（保留原有的索引映射和滚动逻辑）"""
        try:
            from PyQt6.QtCore import QItemSelectionModel
            from PyQt6.QtWidgets import QAbstractItemView

            model = self._image_list_model
            if not model:
                return

            current_index = self._state.current_index

            # Codex Review修复：过滤后需要将original_index转换为filtered_row
            original_to_filtered = self._get_original_to_filtered_index()
            if original_to_filtered is not None:
                # 有过滤：查找当前图片在过滤列表中的行号
                filtered_row = original_to_filtered.get(current_index)
                if filtered_row is not None:
                    # 当前图片在过滤列表中
                    idx = model.index(filtered_row, 0)
                    if idx.isValid():
                        self._image_list.selectionModel().setCurrentIndex(
                            idx,
                            QItemSelectionModel.SelectionFlag.ClearAndSelect
                        )
                        self._image_list.scrollTo(idx, QAbstractItemView.ScrollHint.EnsureVisible)
                else:
                    # 当前图片被过滤掉了，清除选中
                    self._image_list.selectionModel().clearSelection()
            else:
                # 没有过滤：直接使用current_index作为行号
                if 0 <= current_index < model.rowCount():
                    idx = model.index(current_index, 0)
                    if idx.isValid():
                        self._image_list.selectionModel().setCurrentIndex(
                            idx,
                            QItemSelectionModel.SelectionFlag.ClearAndSelect
                        )
                        self._image_list.scrollTo(idx, QAbstractItemView.ScrollHint.EnsureVisible)

        except Exception as e:
            self._logger.debug(f"同步图片列表选中状态失败: {e}")

    # ========== 预加载 ==========

    def preload_adjacent_images(self):
        """预加载相邻图片（优化3：智能预加载范围）"""
        image_files = self._state.image_files
        current_index = self._state.current_index

        if not image_files or current_index < 0:
            return

        # 优化3：判断翻页方向（基于最近10次翻页的众数）
        direction_history = self._user_behavior.get('direction_history', [])
        if len(direction_history) >= 3:
            # 计算众数方向：1=向前（下一张），-1=向后（上一张）
            from collections import Counter
            direction_counts = Counter(direction_history[-10:])  # 最近10次
            primary_direction = direction_counts.most_common(1)[0][0]
        else:
            # 历史不足，默认向前
            primary_direction = 1

        # 优化3：根据网络/本地环境调整预加载范围
        is_network = self._state.is_network_path

        if is_network:
            # 网络路径：保守策略
            forward_range = 10  # 主方向10张
            backward_range = 3  # 反方向3张
        else:
            # 本地路径：激进策略（本地快，可多预加载）
            forward_range = 30  # 主方向30张
            backward_range = 10  # 反方向10张

        # 根据主方向调整范围
        if primary_direction == 1:  # 向前翻页
            start_idx = max(0, current_index - backward_range)
            end_idx = min(len(image_files), current_index + forward_range + 1)
        else:  # 向后翻页
            start_idx = max(0, current_index - forward_range)
            end_idx = min(len(image_files), current_index + backward_range + 1)

        # 预加载指定范围内的图片
        preload_paths = []
        for i in range(start_idx, end_idx):
            if i != current_index:  # 跳过当前图片
                img_path = image_files[i]
                # 计算文件的实际路径（根据操作模式和分类状态）
                real_path = self._state.get_real_file_path(img_path)
                preload_paths.append(real_path)

        # 批量预加载
        if preload_paths:
            self._loader.preload_images(preload_paths)
