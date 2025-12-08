"""
状态访问接口

定义 Manager 访问主窗口状态和 UI 回调的抽象接口。
通过依赖注入避免 Manager 直接访问主窗口（消除 Parent Reaching 反模式）。

设计理念（Codex Review，2025-12-04）：
- StateView: 只读状态访问，Manager 通过此接口读取状态
- StateMutator: 状态修改接口，Manager 通过此接口修改状态
- UIHooks: UI 回调接口，Manager 通过此接口触发 UI 更新
- ImageLoader: 图片加载器接口

使用方式：
    # 主窗口实现接口
    class ImageClassifier(QMainWindow, StateView, StateMutator, UIHooks):
        def __init__(self):
            self.session_state = SessionState()
            self.view_state = ViewState()

            # 注入接口实现给 Manager
            self.nav_manager = ImageNavigationManager(
                state=self,      # 主窗口实现 StateView
                mutator=self,    # 主窗口实现 StateMutator
                ui=self          # 主窗口实现 UIHooks
            )

        # 实现接口方法
        @property
        def current_dir(self) -> Path:
            return self.session_state.current_dir
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Dict, Set, Optional, Any, Union, TYPE_CHECKING

if TYPE_CHECKING:
    from PyQt6.QtGui import QPixmap
    from PyQt6.QtWidgets import QProgressDialog
    from core.config import Config
    from utils.app_config import AppConfig
    import numpy as np


class StateView(ABC):
    """
    只读状态视图接口

    Manager 通过此接口访问主窗口的状态数据，而不是直接访问主窗口属性。
    所有方法都是只读的，不会修改状态。
    """

    # ========== 路径相关 ==========

    @property
    @abstractmethod
    def current_dir(self) -> Optional[Path]:
        """当前工作目录"""
        pass

    @property
    @abstractmethod
    def base_dir(self) -> Optional[Path]:
        """基础目录（current_dir 的父目录）"""
        pass

    # ========== 图片相关 ==========

    @property
    @abstractmethod
    def image_files(self) -> List[Path]:
        """当前图片文件列表（可能经过过滤）"""
        pass

    @property
    @abstractmethod
    def all_image_files(self) -> List[Path]:
        """所有图片文件列表（未过滤）"""
        pass

    @property
    @abstractmethod
    def current_index(self) -> int:
        """当前图片索引"""
        pass

    @property
    @abstractmethod
    def total_images(self) -> int:
        """图片总数"""
        pass

    # ========== 分类状态 ==========

    @property
    @abstractmethod
    def classified_images(self) -> Dict[str, Union[str, List[str]]]:
        """
        已分类图片映射

        单分类模式: {路径: 类别名(str)}
        多分类模式: {路径: 类别列表(List[str])}
        """
        pass

    @property
    @abstractmethod
    def removed_images(self) -> Set[str]:
        """已移除图片集合"""
        pass

    @property
    @abstractmethod
    def categories(self) -> Set[str]:
        """类别集合"""
        pass

    @property
    @abstractmethod
    def ordered_categories(self) -> List[str]:
        """排序后的类别列表"""
        pass

    # ========== 模式状态 ==========

    @property
    @abstractmethod
    def is_copy_mode(self) -> bool:
        """是否为复制模式"""
        pass

    @property
    @abstractmethod
    def is_multi_category(self) -> bool:
        """是否为多分类模式"""
        pass

    # ========== 过滤状态 ==========

    @property
    @abstractmethod
    def filter_unclassified(self) -> bool:
        """是否过滤未分类图片"""
        pass

    @property
    @abstractmethod
    def filter_classified(self) -> bool:
        """是否过滤已分类图片"""
        pass

    @property
    @abstractmethod
    def filter_removed(self) -> bool:
        """是否过滤已移除图片"""
        pass

    # ========== 配置相关 ==========

    @property
    @abstractmethod
    def app_config(self) -> "AppConfig":
        """应用配置对象"""
        pass

    @property
    @abstractmethod
    def config(self) -> "Config":
        """分类配置对象"""
        pass

    # ========== 网络状态 ==========

    @property
    @abstractmethod
    def is_network_path(self) -> bool:
        """当前是否为网络路径"""
        pass

    # ========== 辅助方法 ==========

    @abstractmethod
    def get_real_file_path(self, file_path: Path) -> Path:
        """获取文件的真实路径（处理分类后的路径变化）"""
        pass

    @abstractmethod
    def get_image_at_index(self, index: int) -> Optional[Path]:
        """获取指定索引的图片路径"""
        pass


class StateMutator(ABC):
    """
    状态修改接口

    Manager 通过此接口修改主窗口的状态数据。
    与 StateView 分离，便于控制写权限。
    """

    @abstractmethod
    def set_current_index(self, index: int) -> None:
        """设置当前图片索引"""
        pass

    @abstractmethod
    def set_classified_image(self, path: str, category: Union[str, List[str]]) -> None:
        """
        设置图片的分类

        Args:
            path: 图片路径
            category: 类别名（单分类：str，多分类：List[str]）
        """
        pass

    @abstractmethod
    def remove_classified_image(self, path: str) -> None:
        """移除图片的分类记录"""
        pass

    @abstractmethod
    def add_removed_image(self, path: str) -> None:
        """添加到已移除列表"""
        pass

    @abstractmethod
    def remove_from_removed(self, path: str) -> None:
        """从已移除列表中移除"""
        pass

    @abstractmethod
    def set_classified_images(self, images: Dict[str, Union[str, List[str]]]) -> None:
        """设置已分类图片映射"""
        pass

    @abstractmethod
    def set_removed_images(self, images: Set[str]) -> None:
        """设置已移除图片集合"""
        pass

    @abstractmethod
    def set_copy_mode(self, is_copy: bool) -> None:
        """设置复制/移动模式"""
        pass

    @abstractmethod
    def set_multi_category(self, is_multi: bool) -> None:
        """设置单/多分类模式"""
        pass

    # ========== 路径与图片列表 ==========

    @abstractmethod
    def set_current_dir(self, dir_path: Optional[Path]) -> None:
        """设置当前工作目录"""
        pass

    @abstractmethod
    def set_image_files(self, files: List[Path]) -> None:
        """设置当前图片文件列表（可能经过过滤）"""
        pass

    @abstractmethod
    def set_all_image_files(self, files: List[Path]) -> None:
        """设置所有图片文件列表（未过滤）"""
        pass

    # ========== 类别管理 ==========

    @abstractmethod
    def set_categories(self, categories: Set[str]) -> None:
        """设置类别集合"""
        pass

    @abstractmethod
    def set_ordered_categories(self, categories: List[str]) -> None:
        """设置排序后的类别列表"""
        pass

    @abstractmethod
    def add_category(self, category: str) -> None:
        """添加类别"""
        pass

    @abstractmethod
    def remove_category(self, category: str) -> None:
        """移除类别"""
        pass

    # ========== 临时状态 ==========

    @abstractmethod
    def set_last_operation_category(self, category: Optional[str]) -> None:
        """设置最后一次操作的类别"""
        pass

    @abstractmethod
    def set_current_category_index(self, index: int) -> None:
        """设置当前选中的类别索引"""
        pass

    @abstractmethod
    def set_selected_category(self, category: Optional[str]) -> None:
        """设置当前选中的类别名"""
        pass

    # ========== ViewState: 过滤状态 ==========

    @abstractmethod
    def set_filter_unclassified(self, value: bool) -> None:
        """设置是否过滤未分类图片"""
        pass

    @abstractmethod
    def set_filter_classified(self, value: bool) -> None:
        """设置是否过滤已分类图片"""
        pass

    @abstractmethod
    def set_filter_removed(self, value: bool) -> None:
        """设置是否过滤已移除图片"""
        pass

    # ========== ViewState: 排序状态 ==========

    @abstractmethod
    def set_sort_mode(self, mode: str) -> None:
        """设置排序模式：'name'（名称）, 'time'（时间）, 'size'（大小）"""
        pass

    @abstractmethod
    def set_sort_ascending(self, value: bool) -> None:
        """设置是否升序排序"""
        pass

    @abstractmethod
    def set_category_sort_mode(self, mode: str) -> None:
        """设置类别排序模式：'name'（名称）, 'count'（数量）, 'shortcut'（快捷键）"""
        pass

    @abstractmethod
    def set_category_sort_ascending(self, value: bool) -> None:
        """设置类别是否升序排序"""
        pass

    # ========== ViewState: 显示状态 ==========

    @abstractmethod
    def set_show_image_list(self, value: bool) -> None:
        """设置是否显示图片列表"""
        pass

    @abstractmethod
    def set_show_category_panel(self, value: bool) -> None:
        """设置是否显示类别面板"""
        pass

    @abstractmethod
    def set_show_status_bar(self, value: bool) -> None:
        """设置是否显示状态栏"""
        pass

    # ========== ViewState: 预览状态 ==========

    @abstractmethod
    def set_preview_scale(self, scale: float) -> None:
        """设置预览图缩放比例"""
        pass

    @abstractmethod
    def set_fit_to_window(self, value: bool) -> None:
        """设置是否适应窗口大小"""
        pass

    # ========== ViewState: 搜索状态 ==========

    @abstractmethod
    def set_search_text(self, text: str) -> None:
        """设置搜索文本"""
        pass

    @abstractmethod
    def set_search_active(self, value: bool) -> None:
        """设置搜索是否激活"""
        pass


class UIHooks(ABC):
    """
    UI 回调接口

    Manager 通过此接口触发 UI 更新，而不是直接调用主窗口方法。
    这些方法会在主窗口的 UI 线程中执行。
    """

    # ========== 状态保存 ==========

    @abstractmethod
    def save_state(self) -> None:
        """异步保存状态"""
        pass

    @abstractmethod
    def save_state_sync(self) -> None:
        """同步保存状态"""
        pass

    # ========== UI 更新调度 ==========

    @abstractmethod
    def schedule_ui_update(self, *components: str) -> None:
        """
        调度 UI 更新（节流防抖）

        Args:
            *components: 需要更新的组件名称（'image_list', 'statistics', 'ui_state', 'current_image' 等）
                        不传参数则更新所有组件
        """
        pass

    @abstractmethod
    def update_window_title(self, path: Optional[Path] = None) -> None:
        """
        更新窗口标题

        Args:
            path: 可选的图片路径（不传则使用当前图片）
        """
        pass

    @abstractmethod
    def update_status_bar(self, message: str) -> None:
        """更新状态栏"""
        pass

    # ========== 图片显示 ==========

    @abstractmethod
    def show_current_image(self) -> None:
        """显示当前图片"""
        pass

    @abstractmethod
    def show_loading_placeholder(self) -> None:
        """显示加载占位符"""
        pass

    @abstractmethod
    def display_image(self, image_data: Union["QPixmap", "np.ndarray"], path: Path) -> None:
        """
        显示指定图片

        Args:
            image_data: 图片数据（QPixmap 或 numpy 数组）
            path: 图片路径
        """
        pass

    # ========== 列表更新 ==========

    @abstractmethod
    def sync_image_list_selection(self) -> None:
        """同步图片列表选中状态"""
        pass

    @abstractmethod
    def refresh_image_list(self) -> None:
        """刷新图片列表"""
        pass

    # ========== 类别相关 ==========

    @abstractmethod
    def update_category_buttons(self) -> None:
        """更新类别按钮"""
        pass

    @abstractmethod
    def refresh_category_buttons_style(self) -> None:
        """刷新类别按钮样式"""
        pass

    @abstractmethod
    def update_category_selection(self) -> None:
        """更新类别选中状态"""
        pass

    # ========== 过滤相关 ==========

    @abstractmethod
    def apply_image_filter(self) -> None:
        """应用图片过滤"""
        pass

    # ========== 通知提示 ==========

    @abstractmethod
    def show_toast(self, toast_type: str, message: str) -> None:
        """
        显示 Toast 通知

        Args:
            toast_type: 类型 ('info', 'success', 'warning', 'error')
            message: 消息内容
        """
        pass

    @abstractmethod
    def show_message_box(self, title: str, message: str, msg_type: str = 'info') -> None:
        """显示消息框"""
        pass

    @abstractmethod
    def show_question(self, title: str, message: str) -> bool:
        """显示确认对话框，返回是否确认"""
        pass

    # ========== 进度对话框 ==========

    @abstractmethod
    def show_progress_dialog(self, title: str, message: str, maximum: int = 100) -> "QProgressDialog":
        """显示进度对话框，返回对话框对象"""
        pass


class ImageLoader(ABC):
    """
    图片加载器接口

    Manager 通过此接口请求图片加载，而不是直接访问加载器。
    """

    @abstractmethod
    def load_image(self, path: Path, priority: bool = False) -> None:
        """请求加载图片"""
        pass

    @abstractmethod
    def preload_images(self, paths: List[Path]) -> None:
        """预加载多张图片"""
        pass

    @abstractmethod
    def is_cached(self, path: Path) -> bool:
        """检查图片是否已缓存"""
        pass

    @abstractmethod
    def get_from_cache(self, path: Path) -> Optional["np.ndarray"]:
        """
        从缓存获取图片

        Returns:
            numpy 数组格式的图片数据，未命中返回 None
        """
        pass

    @abstractmethod
    def clear_cache(self) -> None:
        """清理缓存"""
        pass


# ========== 便捷类型别名 ==========

StateViewType = StateView
StateMutatorType = StateMutator
UIHooksType = UIHooks
ImageLoaderType = ImageLoader
