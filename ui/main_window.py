"""
主窗口模块

包含应用程序的主窗口类ImageClassifier。
"""

import logging
import time
import psutil
import sys
import json
import re
import threading
import functools
import shutil
import hashlib
import traceback
import subprocess
from pathlib import Path
from typing import Optional, List, Dict, Set, Union
import numpy as np
from concurrent.futures import ThreadPoolExecutor
from PyQt6.QtWidgets import (QMainWindow, QVBoxLayout, QHBoxLayout, QWidget,
                            QSplitter, QLabel, QScrollArea, QStatusBar, QToolBar
                            , QSizePolicy, QFileDialog,
                            QMessageBox, QApplication, QListView,
                            QButtonGroup, QPushButton, QAbstractItemView, QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox, QMenu, QDialog)
# Phase 1.1: QListWidget已废弃，Model/View架构使用QListView
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QSize, QPoint, QObject, QEvent, QThread, QItemSelectionModel
from PyQt6.QtGui import QAction, QKeySequence, QPixmap, QColor, QIcon, QImage, QPainter, QPen, QBrush, QFont
from .components.widgets import (CategoryButton, EnhancedImageLabel,
                                StatisticsPanel, ExpandableSearch)
# Phase 1.1: ImageListItem已废弃，Model/View架构不再需要
from .models.image_list_model import ImageListModel
from .delegates.image_list_delegate import ImageListDelegate
from .components.toast import toast_info, toast_success, toast_warning, toast_error
from .components.styles import ButtonStyles, DialogStyles, ToolbarStyles, MainWindowStyles, WidgetStyles
from .components.styles.theme import default_theme
from .components.styles.widget_styles import WidgetStyles as WS, apply_category_button_style
from .components.tutorial import TutorialManager
from .dialogs import (CategoryShortcutDialog, AddCategoriesDialog,
                     TabbedHelpDialog, ProgressDialog, SettingsDialog, ManageIgnoredCategoriesDialog,
                     UpdateCheckerThread)
from .managers import FileStateManager
from .managers.image_navigation_manager import ImageNavigationManager
from .managers.file_operation_manager import FileOperationManager as UIFileOperationManager
from .managers.category_manager import CategoryManager
from ._main_window.state.interfaces import (
    StateView, StateMutator, UIHooks, ImageLoader as ImageLoaderInterface,
    ImageNavigator
)
from .update_dialog import UpdateInfoDialog
from core.config import Config
from utils.app_config import get_app_config
from core.scanner import FileScannerThread
from core.image_loader import HighPerformanceImageLoader
from utils.exceptions import ImageClassifierError, FileOperationError, ConfigError
from utils.file_operations import normalize_folder_name, retry_file_operation, is_network_path
from core.file_manager import FileOperationManager
from core.update_utils import fetch_manifest, launch_self_update
from utils.performance import performance_monitor
from utils.paths import get_update_dir
from _version_ import __version__, get_manifest_url, compare_version


class DisabledButtonEventFilter(QObject):
    """禁用按钮的事件过滤器，用于捕获禁用按钮的点击事件"""

    def __init__(self, parent_window):
        super().__init__(parent_window)
        self.parent_window = parent_window

    def eventFilter(self, obj, event):
        """过滤事件，捕获禁用按钮的鼠标点击"""
        if event.type() == QEvent.Type.MouseButtonPress:
            # 检查按钮是否被禁用
            if not obj.isEnabled():
                # 获取当前主题模式 - 重新加载配置确保同步
                try:
                    app_config = get_app_config()
                    # 重新加载配置文件，确保获取最新值
                    app_config.reload_config()
                    theme_mode = app_config.theme_mode

                    if theme_mode == "auto":
                        toast_warning(self.parent_window, "当前为自动切换模式，请在设置中切换到手动模式")
                    elif theme_mode == "system":
                        toast_warning(self.parent_window, "当前为跟随系统模式，请在设置中切换到手动模式")
                except Exception as e:
                    self.parent_window.logger.error(f"获取主题模式失败: {e}")

                # 返回True表示事件已处理，不再传递
                return True

        # 对于其他事件，继续传递
        return super().eventFilter(obj, event)


class ImageClassifier(QMainWindow):
    """
    主图像分类器窗口

    通过实例变量和方法实现StateView/StateMutator/UIHooks/ImageLoader/ImageNavigator协议，
    使用鸭子类型（Protocol）而非显式继承。
    """
    
    # 信号定义
    file_moved = pyqtSignal(str, str)  # 文件移动信号(源路径, 目标路径)
    category_added = pyqtSignal(str)   # 类别添加信号
    
    def __init__(self):
        super().__init__()

        self.version = __version__
        self.logger = logging.getLogger(__name__)
        
        # 初始化焦点管理
        self._shortcuts_active = True
        self._last_focus_time = time.time()
        
        # 设置定期的快捷键状态检查定时器
        self._shortcut_monitor_timer = QTimer()
        self._shortcut_monitor_timer.timeout.connect(self._periodic_shortcut_check)
        self._shortcut_monitor_timer.start(30000)  # 每30秒检查一次
        
        # 初始化核心组件
        self.init_core_components()

        # 初始化状态变量
        self.init_state_variables()

        # 初始化Manager（在状态变量之后）
        self._init_managers()

        # 创建用户界面
        self.init_ui()

        # UI初始化后，更新Manager的UI组件引用
        if self._nav_manager and hasattr(self, 'image_list') and hasattr(self, 'image_list_model'):
            self._nav_manager.set_ui_components(self.image_list, self.image_list_model)

        # 设置快捷键
        self.setup_shortcuts()

        # 初始化教程管理器
        try:
            self.tutorial_manager = TutorialManager(self)
        except Exception as e:
            self.logger.error(f"教程管理器初始化失败: {e}")
            self.tutorial_manager = None

        # 启动后自动检查更新（非阻塞，可配置开关）
        try:
            app_config = get_app_config()
            if app_config.auto_update_enabled:
                self._schedule_auto_update_check()
            else:
                self.logger.info("自动检查更新：已关闭")
        except Exception as e:
            self.logger.debug(f"启动自动检查更新调度失败: {e}")

        # 初始化自动主题定时器
        self._auto_theme_timer = QTimer()
        self._auto_theme_timer.timeout.connect(self._check_and_apply_auto_theme)
        # 如果配置了自动模式，启动定时器（每1分钟检查一次）
        try:
            app_config = get_app_config()
            if app_config.theme_mode == "auto":
                self.start_auto_theme_timer()
                self.logger.info("自动主题模式已启用")
        except Exception as e:
            self.logger.debug(f"自动主题定时器初始化失败: {e}")

        # 延迟检查是否显示教程（确保窗口已完全初始化）
        QTimer.singleShot(1000, self._check_and_show_tutorial)

        # 注意：恢复目录的检查会在教程完成/跳过后自动触发，不在这里直接调用
    
    def _get_resource_path(self, relative_path):
        """获取资源文件路径，兼容开发环境和打包环境"""
        try:
            # PyInstaller 打包后的临时目录
            if hasattr(sys, '_MEIPASS'):
                base_path = Path(sys._MEIPASS)
                resource_path = base_path / relative_path
                if resource_path.exists():
                    self.logger.debug(f"使用打包环境资源路径: {resource_path}")
                    return resource_path
                
            # 开发环境 - 从当前文件位置查找
            base_path = Path(__file__).parent.parent
            resource_path = base_path / relative_path
            if resource_path.exists():
                self.logger.debug(f"使用开发环境资源路径: {resource_path}")
                return resource_path
                
            # 尝试从程序运行目录查找
            base_path = Path.cwd()
            resource_path = base_path / relative_path
            if resource_path.exists():
                self.logger.debug(f"使用运行目录资源路径: {resource_path}")
                return resource_path
                
            self.logger.warning(f"未找到资源文件: {relative_path}")
            return None
        except Exception as e:
            self.logger.error(f"获取资源路径失败: {e}")
            return None
        
        # 启动性能监控
        if self.enable_performance_logging:
            self.log_system_info()
    
    def init_core_components(self):
        """初始化核心组件"""
        try:
            # 配置管理器
            self.config = Config()

            # 应用配置管理器（优化8）
            from utils.app_config import get_app_config
            self.app_config = get_app_config()

            # 文件扫描器
            self.file_scanner = FileScannerThread()
            # 由 ImageNavigationManager 统一监听 scanner 信号，主窗口不再直连
            # self.file_scanner.files_found.connect(self.on_files_found)
            # self.file_scanner.initial_batch_ready.connect(self.on_initial_batch_ready)
            # self.file_scanner.scan_progress.connect(self.on_scan_progress)
            # self.file_scanner.scan_finished.connect(self.on_scan_completed)
            
            # 图像加载器
            self.image_loader = HighPerformanceImageLoader()
            # 连接图像加载器的信号
            self.image_loader.image_loaded.connect(self.on_image_loaded)
            self.image_loader.thumbnail_loaded.connect(self.on_thumbnail_loaded)
            self.image_loader.loading_progress.connect(self.on_loading_progress)

            # 文件操作管理器
            self.file_manager = FileOperationManager()


            # 线程池（用于文件操作）
            self.thread_pool = ThreadPoolExecutor(max_workers=4)

            self.logger.info("核心组件初始化完成")

        except Exception as e:
            self.logger.error(f"核心组件初始化失败: {e}")
            raise ImageClassifierError(f"核心组件初始化失败: {e}")

    def _init_managers(self):
        """
        初始化业务逻辑Manager

        Manager通过依赖注入接收接口（self实现StateView/StateMutator/UIHooks等），
        避免Manager直接访问主窗口（消除Parent Reaching反模式）。
        """
        try:
            # 图片导航管理器
            self._nav_manager = ImageNavigationManager(
                state=self,
                mutator=self,
                ui=self,
                loader=self.image_loader,  # 传入实际的image_loader而非self
                scanner=self.file_scanner,
                image_list=None,  # UI组件在init_ui后设置
                image_list_model=None,
                get_visible_indices=self._get_visible_indices,
                get_original_to_filtered_index=self._get_original_to_filtered_index_dict,
                update_category_selection_callback=self._update_category_selection_for_path,
                load_state_callback=self._load_state,
                log_image_info_callback=self._log_image_info,
                log_performance_info_callback=self._log_performance_info,
                is_network_path_callback=lambda p: is_network_path(str(p)) if p else False,
                show_loading_placeholder_callback=self._show_loading_placeholder_for_path,
                logger=self.logger
            )

            # 文件操作管理器
            self._file_ops_manager = UIFileOperationManager(
                state=self,
                mutator=self,
                ui=self,
                navigator=self,  # self实现ImageNavigator接口
                logger=self.logger
            )

            # 类别管理器
            self._category_manager = CategoryManager(
                state=self,
                mutator=self,
                ui=self,
                navigator=self._nav_manager,
                file_ops=self._file_ops_manager,
                logger=self.logger
            )

            self.logger.info("Manager初始化完成")

            # 连接 Manager 信号（替代 scanner 直连）
            self._nav_manager.list_updated.connect(self.on_list_updated)
            self._nav_manager.scan_progress.connect(self.on_scan_progress)
            self._nav_manager.scan_completed.connect(self.on_scan_completed)

            # 连接 FileOperationManager 信号
            self._file_ops_manager.file_moved.connect(self.on_file_moved)
            self._file_ops_manager.file_removed.connect(self.on_file_removed)
            self._file_ops_manager.file_restored.connect(self.on_file_restored)
            self._file_ops_manager.mode_changed.connect(self.on_mode_changed)
            self._file_ops_manager.operation_failed.connect(self.on_operation_failed)

            # 连接 CategoryManager 信号
            self._category_manager.categories_changed.connect(self.on_categories_changed)
            self._category_manager.selection_changed.connect(self.on_category_selection_changed)

        except Exception as e:
            self.logger.error(f"Manager初始化失败: {e}")
            # Manager初始化失败不中断程序，降级到原有实现
            self._nav_manager = None
            self._file_ops_manager = None
            self._category_manager = None

    def _get_visible_indices(self) -> Optional[List[int]]:
        """获取可见图片的原始索引列表（供Manager回调）"""
        # 优先返回 apply_image_filter 维护的缓存
        if hasattr(self, '_visible_indices') and self._visible_indices:
            return self._visible_indices
        # 兜底：未过滤时返回 None
        return None

    def _get_original_to_filtered_index_dict(self) -> Optional[Dict[int, int]]:
        """获取原始索引到过滤后行号的映射（供Manager回调）"""
        # 优先返回 apply_image_filter 维护的缓存
        if hasattr(self, '_original_to_filtered_index') and self._original_to_filtered_index:
            return self._original_to_filtered_index
        # 兜底：未过滤时返回 None
        return None

    def _update_category_selection_for_path(self, img_path: str) -> None:
        """更新类别选中状态（带路径参数，供Manager回调）"""
        # 使用带路径参数的版本，正确更新分类状态
        self.update_category_selection_for_current_image(img_path)

    def _show_loading_placeholder_for_path(self, img_path: str) -> None:
        """显示加载占位符（带路径参数，供Manager回调）"""
        self.show_loading_placeholder()

    def _log_image_info(self, info) -> None:
        """记录图片信息（供Manager回调）"""
        self.logger.debug(f"图片信息: {info}")

    def _log_performance_info(self, *args) -> None:
        """记录性能信息（供Manager回调，支持多个参数）"""
        self.logger.debug(f"性能信息: {' '.join(str(arg) for arg in args)}")

    def _load_state(self) -> None:
        """加载状态（供Manager回调）"""
        self.load_state()

    def init_state_variables(self):
        """初始化状态变量"""
        # 文件和目录状态
        self.current_dir = None
        self.image_files = []
        self.all_image_files = []
        self.current_index = -1
        self.total_images = 0
        self.categories = set()
        self.ordered_categories = []
        self.category_buttons = []
        self.current_category_index = 0
        self.is_network_working_path = False  # 当前工作路径是否为网络路径（默认本地）

        # 操作模式
        self.is_copy_mode = True  # 复制/移动模式
        self.is_multi_category = False  # 多分类模式：False=单分类，True=多分类
        
        # 加载状态
        self.loading_in_progress = False
        self.initial_batch_loaded = False
        self.background_loading = False
        
        # 分类状态
        self.classified_images = {}  # 文件路径 -> 分类
        self.removed_images = set()  # 已移除的图片
        self.last_operation_category = None  # 上次操作的类别，用于保持选中状态
        self.selected_category = None
        self.last_move_time = 0
        self.saved_last_index = -1  # 从状态文件加载的上次图片索引
        
        # 性能监控
        self.enable_performance_logging = True
        self.performance_stats = {
            'switch_times': [],
            'total_switches': 0,
            'last_switch_start': 0,
            'current_image_info': {}
        }
        
        # 用户行为分析
        self.user_behavior = {
            'last_index': -1,
            'last_direction': None,
            'consecutive_forward': 0,
            'consecutive_backward': 0,
            'direction_history': []
        }
        
        # UI更新优化
        self.ui_update_lock = threading.Lock()
        self.pending_ui_updates = set()
        # Codex方案：F5刷新后等待批量更新完成再套用过滤（避免硬编码延迟）
        self._pending_reapply_filter = False

        # 文件状态管理器（延迟初始化）
        self.file_state_manager = None

        # 修复问题4：后台更新检查线程
        self.update_checker_thread = None

        # 快捷键管理器
        self.shortcut_manager = None
        self.ui_update_timer = QTimer()
        self.ui_update_timer.setSingleShot(True)
        self.ui_update_timer.timeout.connect(self.perform_batch_ui_update)
        
        # 类别计数缓存
        self.category_counts = {}
        self.category_count_cache_time = 0
        self.category_count_cache_ttl = 30  # 30秒TTL

        # 过滤状态（ViewState）
        self.filter_unclassified_state = False
        self.filter_classified_state = False
        self.filter_removed_state = False

        # 排序状态（ViewState）
        self.sort_mode_state = 'name'
        self.sort_ascending_state = True
        self.category_sort_mode_state = 'name'
        self.category_sort_ascending_state = True

        # 显示状态（ViewState）
        self.show_image_list_state = True
        self.show_category_panel_state = True
        self.show_status_bar_state = True

        # 预览状态（ViewState）
        self.preview_scale_state = 1.0
        self.fit_to_window_state = True

        # 搜索状态（ViewState）
        self.search_text_state = ''
        self.search_active_state = False

        # Manager实例（在init_core_components后初始化）
        self._nav_manager = None
        self._file_ops_manager = None
        self._category_manager = None

    # ==================== StateView 接口实现 ====================

    # Protocol使用鸭子类型，实例变量（如self.current_dir）自动满足接口要求
    # 以下只需实现接口中定义的非实例变量属性

    @property
    def base_dir(self) -> Optional[Path]:
        """基础目录（current_dir 的父目录）"""
        return self.current_dir.parent if self.current_dir else None

    @property
    def filter_unclassified(self) -> bool:
        """是否过滤未分类图片"""
        return self.filter_unclassified_state

    @filter_unclassified.setter
    def filter_unclassified(self, value: bool) -> None:
        """设置是否过滤未分类图片"""
        self.filter_unclassified_state = value

    @property
    def filter_classified(self) -> bool:
        """是否过滤已分类图片"""
        return self.filter_classified_state

    @filter_classified.setter
    def filter_classified(self, value: bool) -> None:
        """设置是否过滤已分类图片"""
        self.filter_classified_state = value

    @property
    def filter_removed(self) -> bool:
        """是否过滤已移除图片"""
        return self.filter_removed_state

    @filter_removed.setter
    def filter_removed(self, value: bool) -> None:
        """设置是否过滤已移除图片"""
        self.filter_removed_state = value

    @property
    def is_network_path(self) -> bool:
        """当前是否为网络路径"""
        return self.is_network_working_path

    def get_image_at_index(self, index: int) -> Optional[Path]:
        """获取指定索引的图片路径"""
        if 0 <= index < len(self.image_files):
            return Path(self.image_files[index])
        return None

    # ==================== StateMutator 接口实现 ====================

    def set_current_index(self, index: int) -> None:
        """设置当前图片索引"""
        self.current_index = index

    def set_classified_image(self, path: str, category) -> None:
        """设置图片的分类"""
        self.classified_images[path] = category

    def remove_classified_image(self, path: str) -> None:
        """移除图片的分类记录"""
        if path in self.classified_images:
            del self.classified_images[path]

    def add_removed_image(self, path: str) -> None:
        """添加到已移除列表"""
        self.removed_images.add(path)

    def remove_from_removed(self, path: str) -> None:
        """从已移除列表中移除"""
        self.removed_images.discard(path)

    def set_classified_images(self, images: dict) -> None:
        """设置已分类图片映射"""
        self.classified_images = images

    def set_removed_images(self, images: set) -> None:
        """设置已移除图片集合"""
        self.removed_images = images

    def set_copy_mode(self, is_copy: bool) -> None:
        """设置复制/移动模式"""
        self.is_copy_mode = is_copy

    def set_multi_category(self, is_multi: bool) -> None:
        """设置单/多分类模式"""
        self.is_multi_category = is_multi

    def set_current_dir(self, dir_path: Optional[Path]) -> None:
        """设置当前工作目录"""
        self.current_dir = dir_path

    def set_image_files(self, files: list) -> None:
        """设置当前图片文件列表"""
        self.image_files = files

    def set_all_image_files(self, files: list) -> None:
        """设置所有图片文件列表"""
        self.all_image_files = files

    def set_total_images(self, total: int) -> None:
        """设置图片总数"""
        self.total_images = total

    def set_categories(self, categories: set) -> None:
        """设置类别集合"""
        self.categories = categories

    def set_ordered_categories(self, categories: list) -> None:
        """设置排序后的类别列表"""
        self.ordered_categories = categories

    def add_category(self, category: str) -> None:
        """添加类别"""
        self.categories.add(category)

    def remove_category(self, category: str) -> None:
        """移除类别"""
        self.categories.discard(category)

    def set_last_operation_category(self, category: Optional[str]) -> None:
        """设置最后一次操作的类别"""
        self.last_operation_category = category

    def set_current_category_index(self, index: int) -> None:
        """设置当前选中的类别索引"""
        self.current_category_index = index

    def set_selected_category(self, category: Optional[str]) -> None:
        """设置当前选中的类别名"""
        self.selected_category = category

    def set_filter_unclassified(self, value: bool) -> None:
        """设置是否过滤未分类图片"""
        self.filter_unclassified_state = value

    def set_filter_classified(self, value: bool) -> None:
        """设置是否过滤已分类图片"""
        self.filter_classified_state = value

    def set_filter_removed(self, value: bool) -> None:
        """设置是否过滤已移除图片"""
        self.filter_removed_state = value

    def set_sort_mode(self, mode: str) -> None:
        """设置排序模式"""
        self.sort_mode_state = mode

    def set_sort_ascending(self, value: bool) -> None:
        """设置是否升序排序"""
        self.sort_ascending_state = value

    def set_category_sort_mode(self, mode: str) -> None:
        """设置类别排序模式"""
        self.category_sort_mode_state = mode

    def set_category_sort_ascending(self, value: bool) -> None:
        """设置类别是否升序排序"""
        self.category_sort_ascending_state = value

    def set_show_image_list(self, value: bool) -> None:
        """设置是否显示图片列表"""
        self.show_image_list_state = value

    def set_show_category_panel(self, value: bool) -> None:
        """设置是否显示类别面板"""
        self.show_category_panel_state = value

    def set_show_status_bar(self, value: bool) -> None:
        """设置是否显示状态栏"""
        self.show_status_bar_state = value

    def set_preview_scale(self, scale: float) -> None:
        """设置预览图缩放比例"""
        self.preview_scale_state = scale

    def set_fit_to_window(self, value: bool) -> None:
        """设置是否适应窗口大小"""
        self.fit_to_window_state = value

    def set_search_text(self, text: str) -> None:
        """设置搜索文本"""
        self.search_text_state = text

    def set_search_active(self, value: bool) -> None:
        """设置搜索是否激活"""
        self.search_active_state = value

    def set_current_requested_image(self, path: str) -> None:
        """设置当前请求加载的图片路径（用于异步回调验证）"""
        self._current_requested_image = path

    # ==================== UIHooks 接口实现 ====================

    def save_state_sync(self) -> None:
        """同步保存状态"""
        self._save_state_sync()

    def update_status_bar(self, message: str) -> None:
        """更新状态栏"""
        if hasattr(self, 'statusBar') and self.statusBar:
            self.statusBar.showMessage(message)

    def show_toast(self, toast_type: str, message: str) -> None:
        """显示Toast通知"""
        if toast_type == 'info':
            toast_info(self, message)
        elif toast_type == 'success':
            toast_success(self, message)
        elif toast_type == 'warning':
            toast_warning(self, message)
        elif toast_type == 'error':
            toast_error(self, message)

    def show_message_box(self, title: str, message: str, msg_type: str = 'info') -> None:
        """显示消息框"""
        if msg_type == 'info':
            QMessageBox.information(self, title, message)
        elif msg_type == 'warning':
            QMessageBox.warning(self, title, message)
        elif msg_type == 'error':
            QMessageBox.critical(self, title, message)

    def show_question(self, title: str, message: str) -> bool:
        """显示确认对话框"""
        reply = QMessageBox.question(
            self, title, message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        return reply == QMessageBox.StandardButton.Yes

    def show_progress_dialog(self, title: str, message: str, maximum: int = 100):
        """显示进度对话框"""
        from PyQt6.QtWidgets import QProgressDialog
        progress = QProgressDialog(message, "取消", 0, maximum, self)
        progress.setWindowTitle(title)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.show()
        return progress

    def refresh_image_list(self) -> None:
        """刷新图片列表"""
        if hasattr(self, 'image_list_model') and self.image_list_model:
            self.image_list_model.layoutChanged.emit()

    def refresh_category_buttons_style(self) -> None:
        """刷新类别按钮样式"""
        for btn in self.category_buttons:
            if hasattr(btn, 'update_style'):
                btn.update_style()

    def get_category_button_layout(self):
        """获取类别按钮所在的布局"""
        if hasattr(self, 'category_buttons_layout'):
            return self.category_buttons_layout
        return None

    def clear_category_buttons(self) -> None:
        """清空所有类别按钮"""
        for btn in self.category_buttons:
            btn.deleteLater()
        self.category_buttons.clear()

    def create_category_button(self, name: str, shortcut: Optional[str], count: int):
        """创建类别按钮"""
        btn = CategoryButton(name, shortcut, count, self)
        self.category_buttons.append(btn)
        if hasattr(self, 'category_buttons_layout'):
            self.category_buttons_layout.addWidget(btn)
        return btn

    def set_category_button_count(self, name: str, count: int) -> None:
        """更新类别按钮计数"""
        for btn in self.category_buttons:
            if btn.category_name == name:
                btn.set_count(count)
                break

    def ensure_category_visible(self, index: int) -> None:
        """滚动使指定索引的类别按钮可见"""
        if 0 <= index < len(self.category_buttons):
            btn = self.category_buttons[index]
            if hasattr(self, 'category_scroll_area'):
                self.category_scroll_area.ensureWidgetVisible(btn)

    def highlight_category_button(self, index: int) -> None:
        """高亮指定索引的类别按钮"""
        for i, btn in enumerate(self.category_buttons):
            btn.setSelected(i == index)

    def display_image(self, image_data, path: Path) -> None:
        """显示图片"""
        if hasattr(self, 'image_label'):
            if isinstance(image_data, QPixmap):
                self.image_label.set_image(image_data)
            else:
                pixmap = self.convert_to_pixmap(image_data)
                self.image_label.set_image(pixmap)

    # ==================== ImageLoader 接口实现 ====================

    def load_image(self, path: Path, priority: bool = False) -> None:
        """请求加载图片"""
        self.image_loader.load_image(str(path), priority=priority)

    def preload_images(self, paths: list) -> None:
        """预加载多张图片"""
        self.image_loader.preload_images([str(p) for p in paths])

    def is_cached(self, path: Path) -> bool:
        """检查图片是否已缓存"""
        return self.image_loader.is_cached(str(path))

    def get_from_cache(self, path: Path):
        """从缓存获取图片"""
        return self.image_loader._get_from_cache(str(path))

    def clear_cache(self) -> None:
        """清理缓存"""
        self.image_loader.clear_cache()

    # ==================== ImageNavigator 接口实现 ====================

    def select_after_removal(self, original_index: int) -> None:
        """删除图片后智能选择下一张可见图片"""
        if self._nav_manager:
            self._nav_manager.select_after_removal(original_index)
        else:
            # 降级处理：直接设置索引
            if self.image_files:
                new_index = min(original_index, len(self.image_files) - 1)
                self.current_index = max(0, new_index)
            else:
                self.current_index = -1
    
    def init_ui(self):
        """初始化美化的用户界面"""
        try:
            self.setWindowTitle(f"图像分类工具 v{self.version}")
            # 设定更大的最小窗口大小，确保所有UI组件完整显示
            self.setMinimumSize(1400, 900)
            
            # 设置应用程序图标
            try:
                icon_path = self._get_resource_path('assets/icon.ico')
                if icon_path and icon_path.exists():
                    app_icon = QIcon(str(icon_path))
                    self.setWindowIcon(app_icon)
                    # 同时设置应用程序图标
                    QApplication.instance().setWindowIcon(app_icon)
                    self.logger.debug(f"程序图标已加载: {icon_path}")
                else:
                    self.logger.warning(f"图标文件不存在: {icon_path}")
            except Exception as e:
                self.logger.warning(f"加载程序图标失败: {e}")
            
            # 应用主窗口样式
            self.setStyleSheet(MainWindowStyles.get_main_window_style())
            
            # 创建中央控件
            central_widget = QWidget()
            central_widget.setObjectName("central_widget")  # 教程系统需要
            self.setCentralWidget(central_widget)
            
            # 创建主要布局
            main_layout = QHBoxLayout(central_widget)
            main_layout.setContentsMargins(5, 5, 5, 5)
            main_layout.setSpacing(5)
            
            # 创建分割器
            splitter = QSplitter(Qt.Orientation.Horizontal)
            main_layout.addWidget(splitter)
            
            # 创建左侧面板（图片显示）
            self.create_left_panel(splitter)
            
            # 创建右侧面板（控制区域）
            self.create_right_panel(splitter)
            
            # 设置分割器比例
            splitter.setSizes([800, 400])
            
            # 创建工具栏
            self.create_toolbar()
            
            # 创建状态栏
            self.create_status_bar()

            # 应用主题到所有UI组件（在所有组件创建完成后）
            try:
                self.apply_theme()
                self.logger.info(f"已应用主题: {default_theme.get_current_theme()}")
            except Exception as e:
                self.logger.error(f"应用主题失败: {e}")

            self.logger.info("用户界面初始化完成")

        except Exception as e:
            self.logger.error(f"用户界面初始化失败: {e}")
            raise ImageClassifierError(f"用户界面初始化失败: {e}")
    
    def create_left_panel(self, parent):
        """创建简洁的左侧图片显示面板"""
        left_widget = QWidget()
        left_widget.setObjectName("left_panel")  # 设置对象名用于精确样式选择
        left_widget.setStyleSheet("""
            QWidget#left_panel {
                background-color: #FFFFFF;
                border: 1px solid #DEE2E6;
                border-radius: 6px;
            }
        """)
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(6, 6, 6, 6)
        
        # 图片预览标题行 - 包含标题和移除按钮
        title_container = QWidget()
        title_container.setObjectName("title_container")
        title_container.setStyleSheet("""
            QWidget#title_container {
                border-bottom: 1px solid #DEE2E6;
                max-height: 28px;
                min-height: 28px;
            }
        """)
        title_layout = QHBoxLayout(title_container)
        title_layout.setContentsMargins(6, 4, 6, 4)
        title_layout.setSpacing(8)

        # 图片预览标题
        title_label = QLabel("🖼️ 图片预览")
        title_label.setStyleSheet("""
            QLabel {
                font-size: 14px;
                font-weight: bold;
                color: #495057;
                border: none;
            }
        """)
        title_layout.addWidget(title_label)

        # 添加弹性空间，推送移除按钮到右侧
        title_layout.addStretch()

        # 移除按钮 - 现代化工具栏图标样式（红色）
        self.delete_button = self.create_toolbar_button('🗑', 'remove_button',
                                                       '移除当前图片到移除目录',
                                                       self.move_to_remove,
                                                       size=(24, 24))
        # 重写样式为红色主题 - 正方形圆角设计
        self.delete_button.setStyleSheet("""
            QPushButton#remove_button {
                background-color: #f44336;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 14px;
                font-weight: normal;
                text-align: center;
            }
            QPushButton#remove_button:hover {
                background-color: #e53935;
            }
            QPushButton#remove_button:pressed {
                background-color: #d32f2f;
            }
        """)
        title_layout.addWidget(self.delete_button)

        left_layout.addWidget(title_container, 0)  # 不拉伸
        
        # 图片显示区域 - 主要拉伸区域
        self.image_scroll_area = QScrollArea()
        self.image_scroll_area.setObjectName("image_preview_container")  # 设置对象名以便教程系统找到
        self.image_scroll_area.setWidgetResizable(True)
        self.image_scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_scroll_area.setStyleSheet("""
            QScrollArea {
                border: 1px solid #ADB5BD;
                border-radius: 4px;
                background-color: #F8F9FA;
            }
        """)

        self.image_label = EnhancedImageLabel()
        self.image_scroll_area.setWidget(self.image_label)

        left_layout.addWidget(self.image_scroll_area, 1)  # 主要拉伸权重
        
        parent.addWidget(left_widget)
    
    def create_right_panel(self, parent):
        """创建简洁的右侧控制面板"""
        right_widget = QWidget()
        right_widget.setObjectName("right_panel")  # 设置对象名用于精确样式选择
        right_widget.setMaximumWidth(380)
        right_widget.setMinimumWidth(300)
        right_widget.setStyleSheet("""
            QWidget#right_panel {
                background-color: #FFFFFF;
                border: 1px solid #DEE2E6;
                border-radius: 6px;
            }
        """)
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(6, 6, 6, 6)
        right_layout.setSpacing(6)
        
        # 图片列表区域 - 设置拉伸权重
        self.create_image_list_area(right_layout)
        
        # 类别按钮区域 - 设置拉伸权重  
        self.create_category_area(right_layout)
        
        # 统计面板 - 固定高度，不参与拉伸
        self.statistics_panel = StatisticsPanel()
        right_layout.addWidget(self.statistics_panel, 0)  # 不拉伸
        

        # 提示文本 - 固定高度，添加灯泡图标
        tips_label = QLabel('💡 ↑↓选择类别 | Enter确认 | 双击快速分类 | 滚轮缩放')
        tips_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tips_label.setStyleSheet("""
            QLabel {
                color: #555;
                font-size: 11px;
                padding: 4px 8px;
                background-color: #FFF8E1;
                border: 1px solid #FFD54F;
                border-radius: 4px;
                margin: 2px 0px;
                max-height: 24px;
                min-height: 24px;
                font-weight: 500;
            }
        """)
        right_layout.addWidget(tips_label, 0)  # 不拉伸

        
        parent.addWidget(right_widget)
    
    def create_image_list_area(self, layout):
        """创建简洁的图片列表区域"""
        # 图片列表标题行 - 包含标题和文件夹图标按钮
        list_title_container = QWidget()
        list_title_container.setObjectName("list_title_container")
        list_title_container.setStyleSheet("""
            QWidget#list_title_container {
                border-bottom: 2px solid #0D6EFD;
                margin-bottom: 4px;
                max-height: 28px;
                min-height: 28px;
            }
        """)
        list_title_layout = QHBoxLayout(list_title_container)
        list_title_layout.setContentsMargins(6, 0, 6, 4)  # 底部留4px给蓝色边框
        list_title_layout.setSpacing(8)
        list_title_layout.setAlignment(Qt.AlignmentFlag.AlignTop)  # 顶部对齐，避免遮挡底边框

        # 图片列表标题
        list_label = QLabel("📂 图片列表")
        list_label.setStyleSheet("""
            QLabel {
                font-size: 13px;
                font-weight: bold;
                color: #0D6EFD;
                border: none;
                background-color: transparent;
                padding: 0px;
                margin: 0px;
            }
        """)
        list_title_layout.addWidget(list_label)

        # 添加弹性空间，推送右侧按钮到最右边
        list_title_layout.addStretch()

        # 搜索组件 - 可展开的文件名搜索
        self.image_search_widget = ExpandableSearch()
        self.image_search_widget.search_confirmed.connect(self._on_image_search)
        self.image_search_widget.search_cleared.connect(self._on_image_search_cleared)
        list_title_layout.addWidget(self.image_search_widget)

        # 筛选按钮 - 筛选图片显示条件
        self.filter_button = self.create_toolbar_button('▼', 'filter_button',
                                                       '筛选图片显示条件',
                                                       self.show_filter_menu,
                                                       size=(18, 18))
        # 初始化过滤器状态（默认全部显示）
        self.filter_unclassified = True
        self.filter_classified = True
        self.filter_removed = True
        self._image_search_text = ""  # 图片列表搜索关键字

        # 应用样式
        self.filter_button.setStyleSheet("""
            QPushButton#filter_button {
                background-color: transparent;
                color: #0D6EFD;
                border: none;
                border-radius: 3px;
                font-size: 11px;
                font-weight: normal;
                text-align: center;
                margin: 0px;
                padding: 0px;
            }
            QPushButton#filter_button:hover {
                background-color: rgba(245, 245, 245, 180);
            }
            QPushButton#filter_button:pressed {
                background-color: rgba(224, 224, 224, 180);
            }
            QPushButton#filter_button[active="true"] {
                color: #2196F3;
                font-weight: bold;
            }
        """)
        list_title_layout.addWidget(self.filter_button)

        # 文件夹图标按钮 - 打开目录功能
        folder_button = self.create_toolbar_button('📁', 'folder_button',
                                                  '选择包含图片的目录',
                                                  self.open_directory,
                                                  size=(18, 18))
        # 重写样式为透明背景蓝色图标，确保不遮挡蓝色边框
        folder_button.setStyleSheet("""
            QPushButton#folder_button {
                background-color: transparent;
                color: #0D6EFD;
                border: none;
                border-radius: 3px;
                font-size: 11px;
                font-weight: normal;
                text-align: center;
                margin: 0px;
                padding: 0px;
            }
            QPushButton#folder_button:hover {
                background-color: rgba(245, 245, 245, 180);
            }
            QPushButton#folder_button:pressed {
                background-color: rgba(224, 224, 224, 180);
            }
        """)
        list_title_layout.addWidget(folder_button)

        layout.addWidget(list_title_container, 0)  # 不拉伸

        # 图片列表容器 - 可随窗口拉伸
        # Phase 1.1 Migration: Replace QListWidget with QListView for performance
        self.image_list = QListView()
        self.image_list.setObjectName("image_list")  # 设置对象名以便教程系统找到
        self.image_list.setMinimumHeight(120)  # 设置最小高度

        # Initialize empty Model and Delegate
        self.image_list_model = ImageListModel([], {}, set(), set(), self)
        self.image_list.setModel(self.image_list_model)
        self.image_list.setItemDelegate(ImageListDelegate(self))

        # Phase 1.1 关键性能优化：防止主题切换时重新计算所有条目（Codex + Gemini 诊断）
        # 问题：setStyleSheet() 触发 QListView 重新计算 24k 条目的几何，导致 6 秒卡顿
        # 解决：开启 UniformItemSizes（列表项高度固定）+ Batched 布局模式
        self.image_list.setUniformItemSizes(True)  # ← P0 修复：避免逐条测量 24k 项
        self.image_list.setLayoutMode(QListView.LayoutMode.Batched)  # 批处理布局
        self.image_list.setBatchSize(256)  # 每批 256 项

        # Phase 1.1: 配置滚动条行为 - 支持长文件名横向滚动
        self.image_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.image_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.image_list.setWordWrap(False)  # 禁用文字换行，允许横向滚动

        # 移除最大高度限制，让它能够拉伸
        self.image_list.setStyleSheet("""
            QListView {
                border: 1px solid #B3D9FF;
                border-radius: 4px;
                background-color: #FFFFFF;
                padding: 2px;
            }
            QListView::item {
                border: 1px solid transparent;
                border-radius: 3px;
                padding: 4px 6px;
                margin: 1px;
            }
            QListView::item:hover {
                background-color: #E3F2FD;
                border-color: #2196F3;
            }
            QListView::item:selected {
                background-color: #2196F3;
                color: white;
                border-color: #0D47A1;
            }
            QScrollBar:vertical {
                border: 1px solid #B3D9FF;
                background: #F3F9FF;
                width: 10px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background: #2196F3;
                border-radius: 3px;
                min-height: 15px;
            }
            QScrollBar::handle:vertical:hover {
                background: #1976D2;
            }
            QScrollBar::handle:vertical:pressed {
                background: #0D47A1;
            }
            QScrollBar:horizontal {
                border: 1px solid #B3D9FF;
                background: #F3F9FF;
                height: 10px;
                border-radius: 3px;
            }
            QScrollBar::handle:horizontal {
                background: #2196F3;
                border-radius: 3px;
                min-width: 15px;
            }
            QScrollBar::handle:horizontal:hover {
                background: #1976D2;
            }
            QScrollBar::handle:horizontal:pressed {
                background: #0D47A1;
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical,
            QScrollBar::add-line:horizontal,
            QScrollBar::sub-line:horizontal {
                border: none;
                background: none;
            }
        """)
        # Signal changed from itemClicked(QListWidgetItem) to clicked(QModelIndex)
        self.image_list.clicked.connect(self.on_image_list_item_clicked)
        layout.addWidget(self.image_list, 1)  # 设置拉伸权重1
    
    def create_category_area(self, layout):
        """创建简洁的类别按钮区域"""
        # 分类类别标题行 - 包含标题和添加按钮
        category_title_container = QWidget()
        category_title_container.setObjectName("category_title_container")
        category_title_container.setStyleSheet("""
            QWidget#category_title_container {
                border-bottom: 2px solid #FF9800;
                margin-bottom: 4px;
                max-height: 28px;
                min-height: 28px;
            }
        """)
        category_title_layout = QHBoxLayout(category_title_container)
        category_title_layout.setContentsMargins(6, 0, 6, 4)  # 底部留4px给橙色边框
        category_title_layout.setSpacing(8)
        category_title_layout.setAlignment(Qt.AlignmentFlag.AlignTop)  # 顶部对齐，避免遮挡底边框

        # 分类类别标题
        category_label = QLabel("🏷️ 分类类别")
        category_label.setStyleSheet("""
            QLabel {
                font-size: 13px;
                font-weight: bold;
                color: #E65100;
                border: none;
                background-color: transparent;
                padding: 0px;
                margin: 0px;
            }
        """)
        category_title_layout.addWidget(category_label)

        # 添加弹性空间，推送右侧按钮到最右边
        category_title_layout.addStretch()

        # 排序方向按钮 - 升序/降序切换（tooltip在后面动态设置）
        self.sort_direction_button = self.create_toolbar_button(
            '↑' if self.config.sort_ascending else '↓',
            'sort_direction_button',
            '',  # tooltip将在_update_direction_button_tooltip中动态设置
            self.toggle_sort_direction,
            size=(18, 18)
        )
        self.sort_direction_button.setStyleSheet("""
            QPushButton#sort_direction_button {
                background-color: transparent;
                color: #E65100;
                border: none;
                border-radius: 3px;
                font-size: 12px;
                font-weight: bold;
                text-align: center;
                margin: 0px;
                padding: 0px;
            }
            QPushButton#sort_direction_button:hover {
                background-color: rgba(245, 245, 245, 180);
            }
            QPushButton#sort_direction_button:pressed {
                background-color: rgba(224, 224, 224, 180);
            }
        """)
        category_title_layout.addWidget(self.sort_direction_button)
        # 设置初始tooltip（动态显示当前排序状态）
        self._update_direction_button_tooltip()

        # 排序按钮 - 类别排序选项
        self.sort_button = self.create_toolbar_button('▼', 'sort_button',
                                                     '类别排序方式',
                                                     self.show_sort_menu,
                                                     size=(18, 18))
        # 应用样式
        self.sort_button.setStyleSheet("""
            QPushButton#sort_button {
                background-color: transparent;
                color: #E65100;
                border: none;
                border-radius: 3px;
                font-size: 11px;
                font-weight: normal;
                text-align: center;
                margin: 0px;
                padding: 0px;
            }
            QPushButton#sort_button:hover {
                background-color: rgba(245, 245, 245, 180);
            }
            QPushButton#sort_button:pressed {
                background-color: rgba(224, 224, 224, 180);
            }
        """)
        category_title_layout.addWidget(self.sort_button)

        # 添加类别图标按钮 - "+"字符
        add_button = self.create_toolbar_button('+', 'add_category_button',
                                               '批量添加分类类别',
                                               self.add_category,
                                               size=(18, 18))
        # 重写样式为透明背景橙色图标，与分类类别标题保持一致
        add_button.setStyleSheet("""
            QPushButton#add_category_button {
                background-color: transparent;
                color: #E65100;
                border: none;
                border-radius: 3px;
                font-size: 14px;
                font-weight: bold;
                text-align: center;
                margin: 0px;
                padding: 0px;
            }
            QPushButton#add_category_button:hover {
                background-color: rgba(245, 245, 245, 180);
            }
            QPushButton#add_category_button:pressed {
                background-color: rgba(224, 224, 224, 180);
            }
        """)
        category_title_layout.addWidget(add_button)

        layout.addWidget(category_title_container, 0)  # 不拉伸
        
        # 类别按钮滚动区域 - 可随窗口拉伸
        self.category_scroll = QScrollArea()
        self.category_scroll.setObjectName("category_list")  # 设置对象名以便教程系统找到
        self.category_scroll.setWidgetResizable(True)
        self.category_scroll.setMinimumHeight(150)  # 设置最小高度
        # 移除最大高度限制，让它能够拉伸
        self.category_scroll.setStyleSheet("""
            QScrollArea {
                border: 1px solid #FFB74D;
                border-radius: 4px;
                background-color: #FFFFFF;
            }
            QScrollBar:vertical {
                border: 1px solid #FFB74D;
                background: #FFF8E1;
                width: 10px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background: #FF9800;
                border-radius: 3px;
                min-height: 15px;
            }
            QScrollBar::handle:vertical:hover {
                background: #F57C00;
            }
            QScrollBar::handle:vertical:pressed {
                background: #E65100;
            }
            QScrollBar:horizontal {
                border: 1px solid #FFB74D;
                background: #FFF8E1;
                height: 10px;
                border-radius: 3px;
            }
            QScrollBar::handle:horizontal {
                background: #FF9800;
                border-radius: 3px;
                min-width: 15px;
            }
            QScrollBar::handle:horizontal:hover {
                background: #F57C00;
            }
            QScrollBar::handle:horizontal:pressed {
                background: #E65100;
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical,
            QScrollBar::add-line:horizontal,
            QScrollBar::sub-line:horizontal {
                border: none;
                background: none;
            }
        """)
        
        self.category_widget = QWidget()
        self.button_layout = QVBoxLayout(self.category_widget)
        self.button_layout.setSpacing(3)
        self.button_layout.setContentsMargins(4, 4, 4, 4)
        
        self.category_scroll.setWidget(self.category_widget)
        layout.addWidget(self.category_scroll, 1)  # 设置拉伸权重1

    def create_toolbar_button(self, text: str, object_name: str, tooltip: str,
                             click_handler=None, size=(40, 40)) -> QPushButton:
        """创建标准化的工具栏按钮

        Args:
            text: 按钮显示文本/图标
            object_name: 按钮对象名称（用于样式）
            tooltip: 提示文本
            click_handler: 点击事件处理函数（可选）
            size: 按钮尺寸，默认(40, 40)

        Returns:
            QPushButton: 配置好的按钮实例
        """
        button = QPushButton()
        button.setText(text)
        button.setObjectName(object_name)
        button.setToolTip(tooltip)
        button.setFixedSize(*size)

        # 应用统一样式 - 使用新的样式系统
        button.setStyleSheet(ButtonStyles.get_square_button_style(object_name))

        # 绑定点击事件
        if click_handler:
            button.clicked.connect(click_handler)

        return button

    def create_toolbar(self):
        """创建工具栏"""
        toolbar = QToolBar()
        toolbar.setObjectName("toolbar")  # 设置对象名以便教程系统找到
        toolbar.setMovable(False)
        toolbar.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)  # 禁用右键菜单
        # 应用工具栏样式
        toolbar.setStyleSheet(ToolbarStyles.get_main_toolbar_style())
        self.addToolBar(toolbar)
        
        # 打开目录
        open_action = QAction('📁 打开目录', self)
        open_action.triggered.connect(self.open_directory)
        open_action.setToolTip('选择包含图片的目录')
        toolbar.addAction(open_action)
        # 获取toolbar中对应的widget并设置objectName
        self.open_directory_toolbar_button = toolbar.widgetForAction(open_action)
        if self.open_directory_toolbar_button:
            self.open_directory_toolbar_button.setObjectName('open_directory_toolbar_button')

        # 添加类别
        add_category_action = QAction('➕ 添加类别', self)
        add_category_action.triggered.connect(self.add_category)
        add_category_action.setToolTip('批量添加分类类别')
        toolbar.addAction(add_category_action)
        # 获取toolbar中对应的widget并设置objectName
        self.add_category_toolbar_button = toolbar.widgetForAction(add_category_action)
        if self.add_category_toolbar_button:
            self.add_category_toolbar_button.setObjectName('add_category_toolbar_button')

        # 添加弹性空间 - 推送右侧按钮到最右边
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)

        # 模式选择
        self.create_mode_button(toolbar)

        # 分类模式按钮（单分类/多分类）
        self.create_category_mode_button(toolbar)

        toolbar.addSeparator()

        # 刷新按钮 - 使用统一样式
        refresh_button = self.create_toolbar_button('↻', 'refresh_button',
                                                   '刷新类别目录，同步外部变化 (F5)',
                                                   self.refresh_categories)
        toolbar.addWidget(refresh_button)

        # 从应用配置中读取主题设置
        current_theme = "light"
        try:
            app_config = get_app_config()
            current_theme = app_config.theme
            self.logger.info(f"从应用配置加载主题: {current_theme}")
        except Exception as e:
            self.logger.warning(f"加载主题配置失败，使用默认: {e}")
        default_theme.set_theme(current_theme)

        # 主题切换按钮 - 使用简洁线条图标
        theme_icon = '☾' if current_theme == "light" else '☼'  # ☾ 月亮(暗色) ☼ 太阳(亮色)
        theme_tooltip = '切换到暗色主题' if current_theme == "light" else '切换到亮色主题'
        self.theme_button = self.create_toolbar_button(theme_icon, 'theme_button',
                                                      theme_tooltip,
                                                      self.toggle_theme)
        toolbar.addWidget(self.theme_button)

        # 安装事件过滤器，使禁用的按钮也能响应点击
        self.theme_button_filter = DisabledButtonEventFilter(self)
        self.theme_button.installEventFilter(self.theme_button_filter)

        # 根据theme_mode设置主题按钮的启用状态
        try:
            theme_mode = app_config.theme_mode
            if theme_mode in ("auto", "system"):
                self.theme_button.setEnabled(False)
                mode_name = "自动切换" if theme_mode == "auto" else "跟随系统"
                self.theme_button.setToolTip(f"已启用{mode_name}，点击查看提示")
        except Exception as e:
            self.logger.warning(f"设置主题按钮状态失败: {e}")

        # 设置按钮 - 使用齿轮图标
        settings_button = self.create_toolbar_button('⚙', 'settings_button',
                                                     '打开设置',
                                                     self.show_settings_dialog)
        toolbar.addWidget(settings_button)

        # 帮助按钮 - 使用统一样式
        help_button = self.create_toolbar_button('?', 'help_button',
                                                '查看使用指南和快捷键',
                                                self.show_help_dialog)
        toolbar.addWidget(help_button)
    
    def create_mode_button(self, toolbar):
        """创建图标化的模式选择按钮 - 直接点击切换"""
        # 使用统一样式创建按钮
        self.mode_button = self.create_toolbar_button('⧉', 'mode_button',
                                                     '复制模式 - 点击切换到移动模式',
                                                     lambda: self.set_mode(not self.is_copy_mode))

        # 添加到工具栏
        toolbar.addWidget(self.mode_button)
        self.set_mode(self.is_copy_mode)
    
    def create_status_bar(self):
        """创建状态栏"""
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.statusBar.showMessage("准备就绪")

        # 在状态栏右侧添加版本信息
        self.version_label = QLabel(f"版本 {__version__}")
        # 使用主题颜色
        c = default_theme.colors
        self.version_label.setStyleSheet(f"""
            QLabel {{
                color: {c.TEXT_SECONDARY};
                padding: 2px 8px;
                font-size: 11px;
            }}
        """)
        self.statusBar.addPermanentWidget(self.version_label)
    
    @performance_monitor
    def setup_shortcuts(self):
        """设置快捷键 - 改进版本，增加错误处理和状态检查"""
        try:
            self.logger.debug("开始设置快捷键...")

            # 清除现有的快捷键，但保留系统默认的
            existing_actions = self.actions()
            for action in existing_actions[:]:  # 使用副本避免迭代时修改列表
                try:
                    self.removeAction(action)
                    action.deleteLater()  # 确保清理资源
                except Exception as e:
                    self.logger.warning(f"清除快捷键失败: {e}")

            # 设置基本导航快捷键
            shortcuts = {
                Qt.Key.Key_Left: self.prev_image,
                Qt.Key.Key_Right: self.next_image,
                Qt.Key.Key_Up: self.prev_category,
                Qt.Key.Key_Down: self.next_category,
                Qt.Key.Key_Return: self.confirm_category,
                Qt.Key.Key_Delete: self.move_to_remove,
                Qt.Key.Key_F5: self.refresh_categories,
            }

            # 设置组合快捷键（用于图像控制）
            combo_shortcuts = {
                'Ctrl+F': lambda: self.image_label.fit_to_window() if hasattr(self, 'image_label') else None,
                'Ctrl+=': lambda: self.image_label.zoom_in() if hasattr(self, 'image_label') else None,
                'Ctrl+-': lambda: self.image_label.zoom_out() if hasattr(self, 'image_label') else None,
                'Ctrl+0': lambda: self.image_label.reset_zoom() if hasattr(self, 'image_label') else None,
            }

            # 创建基本快捷键
            success_count = 0
            for key, func in shortcuts.items():
                try:
                    action = QAction(self)
                    action.setShortcut(QKeySequence(key))
                    # 使用安全的连接方式
                    action.triggered.connect(lambda checked, f=func: self._safe_execute_shortcut(f))
                    self.addAction(action)
                    success_count += 1
                except Exception as e:
                    self.logger.error(f"创建基本快捷键失败 {key}: {e}")

            # 创建组合快捷键
            for key_combo, func in combo_shortcuts.items():
                try:
                    action = QAction(self)
                    action.setShortcut(QKeySequence(key_combo))
                    action.triggered.connect(lambda checked, f=func: self._safe_execute_shortcut(f))
                    self.addAction(action)
                    success_count += 1
                except Exception as e:
                    self.logger.error(f"创建组合快捷键失败 {key_combo}: {e}")

            # 设置类别快捷键
            if hasattr(self, 'config') and self.config and hasattr(self, 'categories'):
                for category_name, key in self.config.category_shortcuts.items():
                    try:
                        if key and category_name in self.categories:
                            action = QAction(self)
                            action.setShortcut(QKeySequence(key))
                            action.triggered.connect(lambda checked, name=category_name: self._safe_execute_shortcut(lambda: self.quick_classify_by_name(name)))
                            self.addAction(action)
                            success_count += 1
                    except Exception as e:
                        self.logger.error(f"创建类别快捷键失败 {category_name}->{key}: {e}")

            self.logger.debug(f"快捷键设置完成，成功创建 {success_count} 个快捷键")

        except Exception as e:
            self.logger.error(f"设置快捷键时发生严重错误: {e}")
            # 尝试恢复基本功能
            self._setup_minimal_shortcuts()

    def _safe_execute_shortcut(self, func):
        """安全执行快捷键函数"""
        try:
            if not self._shortcuts_active:
                self.logger.debug("快捷键被禁用，跳过执行")
                return

            # 检查是否在输入模式（输入框聚焦时不执行快捷键）
            if self._is_in_input_mode():
                self.logger.debug("输入模式，跳过快捷键执行")
                # 手动触发QLineEdit的returnPressed信号（QAction会拦截事件导致信号不触发）
                focused = self.focusWidget()
                if focused and isinstance(focused, QLineEdit):
                    focused.returnPressed.emit()
                return

            if func:
                # INFO级别记录QAction快捷键触发（简化记录）
                func_name = getattr(func, '__name__', 'lambda')
                if func_name == '<lambda>':
                    func_name = 'lambda'
                self.logger.info(f"快捷键执行: {func_name}")
                func()
        except Exception as e:
            self.logger.error(f"执行快捷键函数失败: {e}")

    def _setup_minimal_shortcuts(self):
        """设置最小化快捷键集合（紧急恢复用）"""
        try:
            self.logger.info("尝试设置最小化快捷键...")
            minimal_shortcuts = {
                Qt.Key.Key_Left: self.prev_image,
                Qt.Key.Key_Right: self.next_image,
                Qt.Key.Key_F5: self.refresh_categories,
            }

            for key, func in minimal_shortcuts.items():
                try:
                    action = QAction(self)
                    action.setShortcut(QKeySequence(key))
                    action.triggered.connect(func)
                    self.addAction(action)
                except Exception as e:
                    self.logger.error(f"最小化快捷键设置失败 {key}: {e}")

        except Exception as e:
            self.logger.error(f"最小化快捷键设置严重失败: {e}")

    def quick_classify_by_name(self, category):
        """通过类别名称快速分类"""
        if self.current_dir and category in self.categories:
            self.move_to_category(category)

    def _is_defined_shortcut(self, key: int, modifiers) -> bool:
        """检查是否为已定义的快捷键"""
        try:
            # 基本快捷键列表
            basic_shortcuts = {
                Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down,
                Qt.Key.Key_Return, Qt.Key.Key_Delete, Qt.Key.Key_F5
            }

            # 检查基本快捷键
            if key in basic_shortcuts:
                return True

            # 检查类别快捷键
            if hasattr(self, 'config') and self.config and hasattr(self, 'categories'):
                for category_name, shortcut_key in self.config.category_shortcuts.items():
                    if shortcut_key and category_name in self.categories:
                        try:
                            sequence = QKeySequence(shortcut_key)
                            if len(sequence) > 0:
                                key_combination = sequence[0]
                                if (key_combination.key() == key and
                                    key_combination.keyboardModifiers() == modifiers):
                                    return True
                        except Exception:
                            continue

            return False

        except Exception as e:
            self.logger.error(f"检查快捷键定义失败: {e}")
            return False

    def _is_network_path(self, path):
        """检查是否为网络路径"""
        path_str = str(path)
        return path_str.startswith('\\\\') or '://' in path_str
    
    def log_performance_info(self, operation, **kwargs):
        """记录详细的性能信息"""
        if not self.enable_performance_logging:
            return
            
        try:
            # 获取内存信息
            process = psutil.Process()
            memory_info = process.memory_info()
            memory_mb = memory_info.rss / 1024 / 1024
            
            # 获取系统内存信息
            system_memory = psutil.virtual_memory()
            system_available_mb = system_memory.available / 1024 / 1024
            
            # 获取缓存信息
            cache_info = {}
            if hasattr(self, 'image_loader'):
                cache_info = self.image_loader.get_cache_info()
            
            # 格式化基本信息
            base_info = f"[{operation}] "
            base_info += f"内存:{memory_mb:.1f}MB "
            base_info += f"系统可用:{system_available_mb:.1f}MB "
            
            if cache_info:
                base_info += f"缓存:{cache_info.get('cache_size', 0)}/{cache_info.get('max_size', 0)} "
                base_info += f"内存:{cache_info.get('memory_usage_mb', 0):.1f}/{cache_info.get('max_memory_mb', 0):.1f}MB "
                base_info += f"命中率:{cache_info.get('hit_rate', '0%')}"
            
            # 添加额外信息
            extra_info = ""
            for key, value in kwargs.items():
                extra_info += f" {key}:{value}"

            self.logger.debug(base_info + extra_info)
            
        except Exception as e:
            self.logger.debug(f"性能日志记录失败: {e}")
    
    def log_system_info(self):
        """输出系统和程序配置信息"""
        try:
            # 系统信息
            memory = psutil.virtual_memory()
            cpu_count = psutil.cpu_count()
            
            # 图片加载器配置
            cache_size_mb = self.image_loader.max_cache_memory / 1024 / 1024
            
            self.logger.info("=" * 80)
            self.logger.info(f"[系统配置] 图片分类工具 v{self.version} - 性能监控已启用")
            self.logger.info(f"[系统信息] CPU核心:{cpu_count} 系统内存:{memory.total / 1024 / 1024 / 1024:.1f}GB "
                        f"可用内存:{memory.available / 1024 / 1024 / 1024:.1f}GB")
            self.logger.info(f"[缓存配置] 图片缓存:{self.image_loader.cache_size}张 "
                        f"内存上限:{cache_size_mb:.0f}MB 缩略图缓存:{self.image_loader.thumbnail_cache_size}张")
            self.logger.info(f"[加载策略] OpenCV优先:{self.image_loader.use_opencv} "
                        f"网络优化:启用 滑动窗口:智能预加载")
            self.logger.info(f"[性能监控] 详细日志:启用 切换计时:启用 内存监控:启用 预加载追踪:启用")
            self.logger.info("=" * 80)
            
        except Exception as e:
            self.logger.error(f"系统信息输出失败: {e}")
    
    # ===== 响应式布局处理方法 =====
    
    def resizeEvent(self, event):
        """处理窗口大小改变事件"""
        try:
            super().resizeEvent(event)
            
            # 记录窗口大小变化
            if hasattr(self, 'logger'):
                self.logger.debug(f"窗口大小改变: {event.size().width()}x{event.size().height()}")
               
        except Exception as e:
            if hasattr(self, 'logger'):
                self.logger.error(f"窗口大小改变处理失败: {e}")
    
    # ===== 目录和文件处理方法 =====
    
    def open_directory(self):
        """打开图片目录"""

        dir_path = QFileDialog.getExistingDirectory(self, '选择图片目录')
        if dir_path:
            self.current_dir = Path(dir_path)
            current_drive = self.current_dir.drive  # 例如 "D:"

            # 尝试从全局配置中获取盘符缓存
            try:
                app_config = get_app_config()
                cached_drive = app_config.get_last_opened_drive()  # 从路径中实时提取盘符
                cached_is_network = app_config.last_opened_drive_is_network

                # 如果缓存命中（盘符相同），使用缓存值
                if cached_drive == current_drive:
                    is_network = cached_is_network
                    self.logger.debug(f"盘符缓存命中: {current_drive} ({'网络' if is_network else '本地'})")
                else:
                    # 缓存未命中，需要检测
                    is_network = is_network_path(self.current_dir)
                    self.logger.debug(f"盘符缓存未命中，重新检测: {current_drive} ({'网络' if is_network else '本地'})")
            except Exception as e:
                # 如果获取缓存失败，回退到直接检测
                self.logger.warning(f"获取盘符缓存失败: {e}，使用直接检测")
                is_network = is_network_path(self.current_dir)

            # Task 1.1：通知图像加载器当前工作路径类型
            # 本地路径将跳过磁盘缓存清理，节省100%清理开销
            try:
                self.image_loader.set_working_path(self.current_dir)
            except Exception as e:
                self.logger.warning(f"设置图像加载器工作路径失败: {e}")

            # 设置配置文件路径为图片目录的父目录
            # 这个操作可能会因为权限问题失败（尤其是网络路径）
            try:
                self.config.set_base_dir(str(self.current_dir.parent))
            except ConfigError as e:
                # 检查是否是权限错误
                if "Permission denied" in str(e) or "权限" in str(e):
                    self.logger.error(f"目录访问权限不足: {self.current_dir.parent}")
                    toast_error(self, f"⚠️ 无法打开目录：该路径没有写入权限\n路径：{self.current_dir.parent}")
                else:
                    self.logger.error(f"配置初始化失败: {e}")
                    toast_error(self, f"⚠️ 打开目录失败：{e}")

                # 重置当前目录，取消打开操作
                self.current_dir = None
                return  # 提前退出，不执行后续操作

            # 保存路径类型到实例变量，供循环翻页等功能使用
            self.is_network_working_path = is_network

            if is_network:
                # 网络路径提醒
                toast_info(self,'🚀 检测到网络路径，已启用专项优化')
                self.logger.info(f"[网络路径] 用户选择: {self.current_dir}")
            else:
                self.logger.info(f"[本地路径] 用户选择: {self.current_dir}")
                # 显示本地目录打开成功通知
                toast_success(self,f"已打开目录：{self.current_dir.name}")

            # 保存最后打开的目录和盘符信息到全局配置
            try:
                app_config = get_app_config()
                app_config.update_last_opened_drive_info(str(self.current_dir), is_network)
            except Exception as e:
                self.logger.error(f"保存最后打开的目录信息失败: {e}")

            # 清除搜索状态
            self._image_search_text = ""
            if hasattr(self, 'image_search_widget'):
                self.image_search_widget.clear_and_collapse()

            # 先启动图片扫描，让UI立即响应
            self.load_images()

            # 延迟类别加载和同步操作
            QTimer.singleShot(100, self._delayed_load_categories)

    def _delayed_load_categories(self):
        """延迟加载类别，避免阻塞UI"""
        try:
            # 先快速加载类别（不启动同步操作）
            self._load_categories_only()
            
            # 显示当前图片
            self.show_current_image()
            
            # 进一步延迟同步操作，确保UI完全就绪后再进行
            QTimer.singleShot(1000, self._delayed_start_sync)
            
        except Exception as e:
            self.logger.error(f"延迟加载类别失败: {e}")
    
    def _load_categories_only(self):
        """只加载类别，不启动同步操作"""
        if not self.current_dir:
            self.logger.warning("当前目录未设置，无法加载类别")
            return
            
        try:
            self.logger.info("开始加载类别...")
            self.categories = set()
            removed_categories = []
            
            # 扫描图片目录的父目录下的同级目录作为类别
            parent_dir = self.current_dir.parent
            self.logger.info(f"扫描类别目录: {parent_dir}")
            
            for item in parent_dir.iterdir():
                if item.is_dir():
                    is_reserved = item.name in self.config.reserved_categories
                    is_current_dir = item == self.current_dir
                    is_ignored = self.config.is_category_ignored(item.name)

                    if is_ignored:
                        self.logger.info(f"⊘ 忽略类别目录: {item.name}")
                    elif not is_reserved and not is_current_dir:
                        self.categories.add(item.name)
                        self.logger.info(f"✅ 发现类别目录: {item.name}")
            
            # 检查配置中的类别是否还存在对应目录
            config_categories = set(self.config.category_shortcuts.keys())
            
            for category_name in config_categories:
                category_dir = parent_dir / category_name
                if category_dir.exists() and category_dir.is_dir():
                    self.categories.add(category_name)
                else:
                    removed_categories.append(category_name)
            
            # 清理config.json中不存在的类别
            if removed_categories:
                for category in removed_categories:
                    if category in self.config.category_shortcuts:
                        del self.config.category_shortcuts[category]
                        
                # 清理分类状态中的无效类别
                invalid_classifications = []
                for img_path, category in self.classified_images.items():
                    if category in removed_categories:
                        invalid_classifications.append(img_path)
                        
                for img_path in invalid_classifications:
                    del self.classified_images[img_path]
            
            self.logger.info(f"加载完成，共有类别: {len(self.categories)}")
            
            # 分配默认快捷键
            self.config.assign_default_shortcuts(self.categories)

            # 根据配置的排序模式排序类别（count模式需要分类数量统计）
            category_counts = self._get_category_counts() if self.config.category_sort_mode == "count" else None
            self.ordered_categories = self.config.get_sorted_categories(
                self.categories, category_counts=category_counts
            )

            # 保存更新后的配置
            self.config.save_config()

            # 初始化类别计数
            self.init_category_counts()

            # 更新排序方向按钮的UI状态（从配置加载后同步）
            self._sync_sort_button_state()

            # 更新UI
            self.update_category_buttons()
            self.setup_shortcuts()
            
        except Exception as e:
            self.logger.error(f"加载类别失败: {str(e)}")
            self.categories = set()
            self.ordered_categories = []
    
    def load_categories(self):
        """公共的加载类别方法，供对话框调用"""
        try:
            self._load_categories_only()
            self.logger.info("类别列表已刷新")
        except Exception as e:
            self.logger.error(f"刷新类别失败: {e}")
    
    def _delayed_start_sync(self):
        """延迟启动同步操作，确保不阻塞UI"""
        try:
            if self.categories and hasattr(self, 'file_manager'):
                self.logger.info("🔄 开始后台同步操作...")
                self.statusBar.showMessage("🔄 后台同步分类状态中...")
                
                # 连接同步完成信号（使用UniqueConnection防止重复连接）
                if hasattr(self.file_manager, 'file_sync'):
                    try:
                        self.file_manager.file_sync.sync_completed.connect(
                            self._on_sync_completed, Qt.ConnectionType.UniqueConnection)
                        self.file_manager.file_sync.sync_progress.connect(
                            self._on_sync_progress, Qt.ConnectionType.UniqueConnection)
                    except TypeError:
                        # 已连接，忽略
                        pass
                
                # 启动真正的同步操作
                try:
                    self.file_manager.start_background_sync(
                        self.current_dir, 
                        self.categories, 
                        self.classified_images, 
                        self.removed_images, 
                        quick_mode=True
                    )
                except Exception as sync_error:
                    self.logger.error(f"启动同步失败: {sync_error}")
                    self._update_status_with_current_image()
            else:
                self.logger.debug("无类别或文件管理器，跳过文件同步")
                self._update_status_with_current_image()
        except Exception as e:
            self.logger.error(f"延迟同步启动失败: {e}")
            self.statusBar.showMessage("❌ 同步启动失败，请查看日志")
    
    def _on_sync_completed(self, result):
        """同步完成回调"""
        try:
            self.logger.info("后台同步操作完成")
            self._update_status_with_current_image()
        except Exception as e:
            self.logger.error(f"处理同步完成回调失败: {e}")
    
    def _on_sync_progress(self, message):
        """同步进度回调"""
        try:
            # 更新状态栏显示同步进度
            self.statusBar.showMessage(f"🔄 {message}")
        except Exception as e:
            self.logger.error(f"处理同步进度回调失败: {e}")
    
    def _update_status_with_current_image(self):
        """使用当前图片信息更新状态栏"""
        try:
            if self.image_files and 0 <= self.current_index < len(self.image_files):
                current_image = self.image_files[self.current_index]
                image_name = Path(current_image).name
                self.statusBar.showMessage(f"📷 {image_name}")
            else:
                self.statusBar.showMessage("✅ 图片分类工具已就绪")
        except Exception as e:
            self.logger.error(f"更新状态栏失败: {e}")
            self.statusBar.showMessage("✅ 图片分类工具已就绪")
    
    def load_images(self):
        """开始智能加载目录下的图片（委托给ImageNavigationManager）"""
        # 设置加载状态，确保信号处理正常工作
        self.loading_in_progress = True
        self.background_loading = False  # 初始为False，on_initial_batch_ready中设为True

        if self._nav_manager:
            self._nav_manager.load_images()
        elif self.current_dir:
            # 降级：Manager未初始化
            self.logger.warning("[降级模式] ImageNavigationManager未初始化，使用直接扫描")
            self.image_loader.clear_cache()
            self.file_scanner.scan_directory(self.current_dir)
    
    # ===== 文件扫描事件处理 =====

    def on_list_updated(self, file_list):
        """接收 Manager 的列表更新信号，执行 UI 层刷新"""
        # Manager已经更新了状态（image_files, all_image_files, total_images）
        # 这里只需要刷新UI
        self.schedule_ui_update('image_list', 'statistics')

    def on_initial_batch_ready(self, initial_files):
        """处理初始批次文件"""
        if not self.loading_in_progress:
            return

        # 立即设置后台加载标记，确保files_found信号不会被丢弃
        self.background_loading = True

        self.logger.info(f"接收到初始批次: {len(initial_files)} 个文件")
        
        # 设置初始显示文件
        self.image_files = initial_files.copy()
        self.all_image_files = initial_files.copy()
        self.current_index = 0 if self.image_files else -1
        self.initial_batch_loaded = True
        
        # 立即设置总数，让UI完全可用
        self.total_images = len(initial_files)
        
        # 设置图片加载器的文件列表引用
        self.image_loader.set_image_files_reference(self.image_files)
        
        # 立即完全启用UI
        self.loading_in_progress = False
        
        # 异步加载状态文件，避免阻塞UI
        QTimer.singleShot(50, self._delayed_load_state)
        
        # 立即更新UI组件（不包括current_image，避免重复刷新）
        self.schedule_ui_update('image_list', 'statistics', 'ui_state')
        
        # 立即显示成功信息
        path_str = str(self.current_dir) if self.current_dir else ""
        is_network_path = path_str.startswith('\\\\')
        location_type = "网络路径" if is_network_path else "本地路径"
        
        self.statusBar.showMessage(f"✅ {location_type}已就绪 {len(initial_files)} 张图片，后台继续扫描...")

        self.logger.info("🚀 程序UI已完全启用，用户可立即使用")

    def _delayed_load_state(self):
        """延迟加载状态文件，避免阻塞UI"""
        try:
            self.load_state()

            # 检查并修复当前列表中的重复文件
            self._remove_duplicates_from_current_list()

            # 移动模式下，补充已分类和已移除的图片到列表
            self._supplement_moved_files_to_list()

            # 应用过滤器（如果按钮已创建）
            if hasattr(self, 'filter_button'):
                self.apply_image_filter()
            else:
                # 状态加载完成后，更新UI显示（不包括current_image，避免重复刷新）
                self.schedule_ui_update('image_list', 'statistics')

            self.logger.debug("状态文件异步加载完成")
        except Exception as e:
            self.logger.error(f"延迟加载状态文件失败: {e}")
    
    def _remove_duplicates_from_current_list(self):
        """移除当前文件列表中的重复项"""
        if not self.image_files:
            return
            
        original_count = len(self.image_files)
        
        # 去重处理
        unique_files = []
        seen_paths = set()
        for file_path in self.image_files:
            path_str = str(file_path)
            if path_str not in seen_paths:
                unique_files.append(file_path)
                seen_paths.add(path_str)
        
        # 更新文件列表
        self.image_files = unique_files
        self.all_image_files = unique_files.copy()
        self.total_images = len(unique_files)
        
        # 更新图片加载器的文件列表引用
        self.image_loader.set_image_files_reference(self.image_files)
        
        if original_count != len(unique_files):
            removed_count = original_count - len(unique_files)
            self.logger.info(f"[去重修复] 移除了 {removed_count} 个重复文件，剩余 {len(unique_files)} 个文件")
            self.statusBar.showMessage(f"✅ 已修复重复文件问题，移除 {removed_count} 个重复项")

    def _supplement_moved_files_to_list(self):
        """移动模式下，补充已分类和已移除的图片到列表"""
        if not self.image_files:
            return

        # 复制模式下不需要补充，因为文件本来就在原目录
        if self.is_copy_mode:
            return

        # 收集当前列表中已有的路径
        existing_paths = {str(f) for f in self.image_files}
        added_files = []

        # 补充已分类的图片
        for img_path in self.classified_images.keys():
            if img_path not in existing_paths:
                # 验证文件实际存在
                real_path = self.get_real_file_path(img_path)
                if real_path.exists():
                    added_files.append(Path(img_path))
                    self.logger.debug(f"补充已分类图片到列表: {Path(img_path).name}")

        # 补充已移除的图片
        for img_path in self.removed_images:
            if img_path not in existing_paths:
                # 验证文件实际存在
                real_path = self.get_real_file_path(img_path)
                if real_path.exists():
                    added_files.append(Path(img_path))
                    self.logger.debug(f"补充已移除图片到列表: {Path(img_path).name}")

        # 将补充的文件添加到列表
        if added_files:
            # 保存当前查看的图片路径（如果有）
            current_image_path = None
            if self.image_files and 0 <= self.current_index < len(self.image_files):
                current_image_path = str(self.image_files[self.current_index])

            self.image_files.extend(added_files)
            self.all_image_files.extend(added_files)

            # 补充后重新排序，保持文件的自然顺序（按文件名）
            self.image_files.sort(key=lambda p: p.name.lower())
            self.all_image_files.sort(key=lambda p: p.name.lower())

            self.total_images = len(self.image_files)

            # 如果之前在查看某张图片，重新定位到该图片
            if current_image_path:
                try:
                    self.current_index = next(i for i, p in enumerate(self.image_files) if str(p) == current_image_path)
                    self.logger.debug(f"排序后重新定位到图片: {Path(current_image_path).name}，新索引: {self.current_index}")
                except StopIteration:
                    # 如果找不到原图片，保持索引不变或重置为0
                    if self.current_index >= len(self.image_files):
                        self.current_index = 0

            # 更新图片加载器的文件列表引用
            self.image_loader.set_image_files_reference(self.image_files)

            self.logger.info(f"[移动模式补充] 添加了 {len(added_files)} 个已移动的图片到列表，总计 {self.total_images} 个文件（已重新排序）")

    def on_files_found(self, file_batch):
        """处理后续发现的文件批次"""
        if not self.background_loading:
            return
            
        # 静默扩展文件列表 - 去重处理
        existing_paths = {str(f) for f in self.image_files}
        new_files = [f for f in file_batch if str(f) not in existing_paths]
        
        if new_files:
            self.image_files.extend(new_files)
            self.all_image_files.extend(new_files)
            
            # 更新图片加载器的文件列表引用
            self.image_loader.set_image_files_reference(self.image_files)
            
            # 减少UI更新频率
            current_total = len(self.all_image_files)
            
            # 只在每发现1000个文件时才更新UI
            if current_total % 1000 == 0:
                self.schedule_ui_update('image_list')
                self.statusBar.showMessage(f"📈 后台发现 {current_total} 张图片...")
                self.logger.info(f"[后台扫描] 里程碑更新: 总计 {current_total} 个文件")
    
    def on_scan_completed(self, total_count):
        """全量扫描完成处理"""
        self.background_loading = False
        self.initial_batch_loaded = True  # 标记扫描完成
        
        # 最终数据同步和去重处理
        original_count = len(self.image_files)
        
        # 对文件列表进行最终去重
        unique_files = []
        seen_paths = set()
        for file_path in self.image_files:
            path_str = str(file_path)
            if path_str not in seen_paths:
                unique_files.append(file_path)
                seen_paths.add(path_str)
        
        # 更新文件列表
        self.image_files = unique_files
        self.all_image_files = unique_files.copy()
        
        # 更新总数为实际去重后的数量
        actual_count = len(self.image_files)
        self.total_images = actual_count
        
        # 最终更新图片加载器的文件列表引用
        self.image_loader.set_image_files_reference(self.image_files)

        # 移动模式下，补充已分类和已移除的图片到列表
        self._supplement_moved_files_to_list()

        # 更新实际总数（可能在补充后增加）
        actual_count = len(self.image_files)
        self.total_images = actual_count

        # 补充后再次更新图片加载器的文件列表引用
        self.image_loader.set_image_files_reference(self.image_files)

        # 延迟启动同步操作
        if hasattr(self, 'categories') and self.categories:
            QTimer.singleShot(2000, lambda: self._delayed_start_sync())

        self.update_category_counts()

        # 重新更新UI以显示完整列表
        self.schedule_ui_update('image_list', 'statistics')

        # 静默完成通知
        path_str = str(self.current_dir) if self.current_dir else ""
        is_network_path = path_str.startswith('\\\\')
        location_type = "网络路径" if is_network_path else "本地路径"

        self.statusBar.showMessage(f"🎯 {location_type}扫描完成，总计 {actual_count} 张图片")

        # 强制更新UI列表
        self.schedule_ui_update('image_list', 'statistics')

        self.logger.info(f"🎯 后台扫描完成: 实际文件 {actual_count} 个")

        # 更新主题按钮状态（根据图片数量）
        self.update_theme_button_state()

        # 检查是否需要提示用户跳转到上次位置
        QTimer.singleShot(500, self._check_and_prompt_last_position)

        # 优化8：启动缓存预热（仅网络路径且已启用）
        if is_network_path and self.app_config.cache_warmup_enabled:
            warmup_count = self.app_config.cache_warmup_count
            if actual_count > 0:
                QTimer.singleShot(1000, lambda: self._start_cache_warmup(warmup_count))

    def _check_and_prompt_last_position(self):
        """检查并提示用户是否跳转到上次处理的位置"""
        try:
            # 检查是否有保存的索引
            if not hasattr(self, 'saved_last_index'):
                return

            last_index = self.saved_last_index

            # 检查索引是否有效（大于0且小于图片总数）
            if last_index <= 0 or not self.image_files or last_index >= len(self.image_files):
                self.logger.debug(f"last_index 无效或为初始值: {last_index}, 不提示跳转")
                return

            # 弹出确认对话框

            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("恢复上次位置")
            msg_box.setText(f"检测到上次处理到第 {last_index + 1} 张图片")
            msg_box.setInformativeText("是否跳转到上次处理的位置继续工作？")
            msg_box.setIcon(QMessageBox.Icon.Question)

            # 设置程序图标
            try:
                icon_path = self._get_resource_path('assets/icon.ico')
                if icon_path and icon_path.exists():
                    msg_box.setWindowIcon(QIcon(str(icon_path)))
            except Exception:
                pass

            # 添加按钮
            yes_btn = msg_box.addButton("跳转", QMessageBox.ButtonRole.YesRole)
            no_btn = msg_box.addButton("从头开始", QMessageBox.ButtonRole.NoRole)
            msg_box.setDefaultButton(yes_btn)

            # 应用主题样式（支持亮色和暗色主题）
            c = default_theme.colors
            msg_box.setStyleSheet(f"""
                QMessageBox {{
                    background-color: {c.BACKGROUND_PRIMARY};
                    color: {c.TEXT_PRIMARY};
                    border: 1px solid {c.BORDER_MEDIUM};
                    border-radius: 8px;
                    font-size: 14px;
                }}
                QMessageBox QLabel {{
                    color: {c.TEXT_PRIMARY};
                    font-size: 14px;
                    padding: 10px;
                    background: transparent;
                }}
                QPushButton {{
                    background-color: {c.PRIMARY};
                    color: white;
                    border: none;
                    border-radius: 6px;
                    padding: 8px 16px;
                    font-size: 13px;
                    font-weight: bold;
                    min-width: 80px;
                }}
                QPushButton:hover {{
                    background-color: {c.PRIMARY_DARK};
                }}
                QPushButton:pressed {{
                    background-color: {c.PRIMARY_DARK};
                }}
            """)

            # 显示对话框并获取用户选择
            msg_box.exec()
            clicked_button = msg_box.clickedButton()

            if clicked_button == yes_btn:
                # 用户选择跳转
                self.logger.info(f"用户选择跳转到上次位置: 索引 {last_index}")
                self.jump_to_image(last_index)
                toast_info(self, f"已跳转到第 {last_index + 1} 张图片")
            else:
                # 用户选择从头开始
                self.logger.info("用户选择从头开始")

        except Exception as e:
            self.logger.error(f"检查上次位置失败: {e}")

    def _start_cache_warmup(self, count: int):
        """启动缓存预热（优化8 + 循环翻页末尾预热）

        Args:
            count: 预热图片数量
        """
        try:
            if not self.image_files:
                return

            # 检查是否开启网络路径循环翻页
            enable_tail_warmup = (
                self.app_config.network_loop_enabled and
                hasattr(self, 'is_network_working_path') and
                self.is_network_working_path
            )

            # 调用图片加载器的预热方法
            success = self.image_loader.warmup_cache(
                self.image_files,
                count=count,
                enable_tail_warmup=enable_tail_warmup,
                callback=self._on_warmup_progress
            )

            if success:
                if enable_tail_warmup:
                    tail_count = count // 2
                    total_warmup = count + tail_count
                    self.logger.info(f"[循环翻页] 网络循环已开启，预热前{count}张+末尾{tail_count}张，共{total_warmup}张")
                    toast_info(self, f"开始预热缓存（前{count}张+末尾{tail_count}张）...")
                else:
                    self.logger.info(f"[优化8-预热] 开始预热前 {count} 张图片...")
                    toast_info(self, f"开始预热缓存（{count}张图片）...")
            else:
                self.logger.info("[优化8-预热] 本地路径无需预热，已跳过")

        except Exception as e:
            self.logger.error(f"[优化8-预热] 启动预热失败: {e}")

    def _on_warmup_progress(self, current: int, total: int, filename: str):
        """预热进度回调（优化8）

        Args:
            current: 当前进度
            total: 总数
            filename: 当前文件名

        注意：此方法在后台线程中调用，Toast等UI操作需要通过QTimer发送到主线程
        """
        try:
            if current == total:
                # 预热完成
                self.logger.info(f"[优化8-预热] 预热完成: {total}/{total}张图片")
                # 修复BUG：使用QTimer将Toast发送到主线程
                QTimer.singleShot(0, lambda: toast_success(self, f"缓存预热完成（{total}张图片）"))
            elif current % 10 == 0:
                # 每10张输出一次进度日志
                self.logger.debug(f"[优化8-预热] 预热进度: {current}/{total} | {filename}")
        except Exception as e:
            self.logger.error(f"[优化8-预热] 进度回调错误: {e}")

    def jump_to_image(self, index):
        """跳转到指定索引的图片（委托给ImageNavigationManager）"""
        self.logger.info(f"[跳转] 请求跳转到索引 {index}, 当前文件数 {len(self.image_files)}")

        # 先设置当前请求的图片路径，用于回调时判断
        if 0 <= index < len(self.image_files):
            img_path = str(self.image_files[index])
            real_path = str(self.get_real_file_path(img_path))
            self._current_requested_image = str(Path(real_path).resolve())

        if self._nav_manager:
            self._nav_manager.jump_to_image(index)
        else:
            # 降级：直接设置索引并显示
            self.logger.warning("[降级模式] ImageNavigationManager未初始化")
            if 0 <= index < len(self.image_files):
                self.current_index = index
                self.show_current_image()

    def on_scan_progress(self, message):
        """处理扫描进度"""
        self.statusBar.showMessage(message)

    # ===== 文件操作事件处理（来自FileOperationManager）=====

    def on_file_moved(self, src: str, dst: str):
        """文件移动完成"""
        # Manager已更新状态，这里只需UI刷新
        self.schedule_ui_update('image_list', 'statistics', 'category_buttons')
        self.statusBar.showMessage(f"✅ 已分类到 {Path(dst).parent.name}")

    def on_file_removed(self, path: str):
        """文件移除完成"""
        self.schedule_ui_update('image_list', 'statistics')
        self.statusBar.showMessage(f"✅ 已移除")

    def on_file_restored(self, path: str):
        """文件恢复完成"""
        self.schedule_ui_update('image_list', 'statistics', 'category_buttons')
        self.statusBar.showMessage(f"✅ 已撤销")

    def on_mode_changed(self, is_copy_mode: bool):
        """操作模式变更"""
        mode_text = "复制模式" if is_copy_mode else "移动模式"
        self.statusBar.showMessage(f"✅ 已切换到{mode_text}")
        self.schedule_ui_update('ui_state')

    def on_operation_failed(self, path: str, reason: str):
        """文件操作失败"""
        from ui.components.toast import toast_error
        toast_error(self, f"操作失败: {reason}")

    # ===== 类别管理事件处理（来自CategoryManager）=====

    def on_categories_changed(self, categories: list):
        """类别列表变更"""
        # Manager已更新状态，这里只需UI刷新
        self.update_category_buttons()
        self.schedule_ui_update('statistics', 'category_counts')

    def on_category_selection_changed(self, index: int, name: str):
        """类别选中状态变更"""
        self.current_category_index = index
        self.selected_category = name

    # ===== UI更新和显示方法 =====
    
    def schedule_ui_update(self, *components):
        """调度UI更新，批量处理以提高性能"""
        if not components:
            return
            
        with self.ui_update_lock:
            for component in components:
                self.pending_ui_updates.add(component)
        
        # 延迟200ms后执行批量更新
        if not self.ui_update_timer.isActive():
            self.ui_update_timer.start(200)
        
    def perform_batch_ui_update(self):
        """执行批量UI更新 - 优化防止重复更新"""
        with self.ui_update_lock:
            if not self.pending_ui_updates:
                return
            components_to_update = self.pending_ui_updates.copy()
            self.pending_ui_updates.clear()

        # Codex方案：检查是否需要在image_list更新后重新应用过滤
        reapply_filter = False

        try:
            # 暂时阻止重绘
            self.setUpdatesEnabled(False)

            # 优化：如果包含current_image更新，只执行一次，并移除其他可能冲突的更新
            if 'current_image' in components_to_update:
                self._show_current_image_internal()
                # 移除其他可能导致重复刷新的组件
                components_to_update.discard('current_image')
                components_to_update.discard('ui_state')  # ui_state会在current_image中处理

            for component in components_to_update:
                if component == 'category_buttons':
                    self._update_category_buttons_internal()
                elif component == 'category_counts':
                    self._update_category_counts_internal()
                elif component == 'image_list':
                    self._update_image_list_internal()
                elif component == 'statistics':
                    self._update_statistics_internal()
                elif component == 'ui_state':
                    self._update_ui_state_internal()

            # Codex方案：本轮包含image_list更新时，刷新完成后再统一套用过滤
            if self._pending_reapply_filter and 'image_list' in components_to_update:
                reapply_filter = True

        finally:
            # 恢复重绘
            self.setUpdatesEnabled(True)
            self.update()

        # Codex方案：在批量更新完成后再应用过滤（避免被_update_image_list_internal覆盖）
        if reapply_filter:
            self._pending_reapply_filter = False
            self.apply_image_filter()
    
    def _update_category_buttons_internal(self):
        """内部类别按钮更新方法"""
        # 清除现有按钮
        for i in reversed(range(self.button_layout.count())):
            widget = self.button_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)
        self.category_buttons.clear()
        
        # 创建按钮容器
        container = QWidget()
        container.setLayout(QVBoxLayout())
        container.layout().setSpacing(2)
        container.layout().setContentsMargins(0, 0, 0, 0)
        
        # 创建按钮组
        button_group = QButtonGroup(self)
        button_group.setExclusive(True)
        
        # 获取当前图片的分类状态
        current_category = None
        if self.image_files and 0 <= self.current_index < len(self.image_files):
            current_path = str(self.image_files[self.current_index])
            current_category = self.classified_images.get(current_path)
        
        # 确保ordered_categories存在且有效
        if not hasattr(self, 'ordered_categories'):
            self.ordered_categories = []
        if not self.ordered_categories:
            return
            
        # 按排序后的顺序添加按钮
        for category_name in self.ordered_categories:
            try:
                btn = CategoryButton(category_name, self.config)         
                
                # 设置按钮为可切换状态，支持选中显示
                btn.setCheckable(True)
                
                # 使用functools.partial来避免lambda的late binding问题
                btn.clicked.connect(functools.partial(self.select_category, category_name))
                
                # 设置分类状态
                if current_category is not None:
                    if isinstance(current_category, list):
                        # 多分类模式
                        is_classified = category_name in current_category
                        is_multi = len(current_category) > 1 and is_classified
                        btn.set_classified(is_classified)
                        btn.set_multi_classified(is_multi)
                    else:
                        # 单分类模式
                        btn.set_classified(category_name == current_category)
                        btn.set_multi_classified(False)
                else:
                    btn.set_classified(False)
                    btn.set_multi_classified(False)
                    
                # 确保按钮的UI样式更新
                btn.style().unpolish(btn)
                btn.style().polish(btn)
                
                # 设置类别计数
                btn.set_count(self.category_counts.get(category_name, 0))
                
                container.layout().addWidget(btn)
                self.category_buttons.append(btn)
                button_group.addButton(btn)
                
                # 如果是当前选中的类别，设置为选中状态
                if (self.current_category_index < len(self.ordered_categories) and 
                    category_name == self.ordered_categories[self.current_category_index]):
                    btn.setChecked(True)
                    
            except Exception as e:
                self.logger.error(f"创建类别按钮失败: {category_name}, 错误: {str(e)}")
                continue
        
        # 添加弹性空间
        container.layout().addStretch()
        
        # 将容器添加到滚动区域
        self.button_layout.addWidget(container)
        
        # 确保初始状态正确：如果没有当前图片分类，默认选中第一个类别
        if (self.category_buttons and self.current_category_index >= 0 and 
            self.current_category_index < len(self.category_buttons)):
            self.category_buttons[self.current_category_index].setChecked(True)
        elif self.category_buttons and not any(btn.isChecked() for btn in self.category_buttons):
            # 如果没有任何按钮被选中，默认选中第一个
            self.current_category_index = 0
            self.category_buttons[0].setChecked(True)
    
    def _update_image_list_internal(self):
        """内部图片列表更新方法 - 完整显示所有图片"""
        try:
            # Phase 1.1 Migration: 使用 Model API 替代 QListWidget API
            # 不再需要 clear()，_init_data 会重置模型

            if not self.image_files:
                # 如果没有文件，初始化空模型以清空视图
                if hasattr(self, 'image_list_model'):
                    self.image_list_model._init_data([], {}, set(), set())
                return

            total_count = len(self.image_files)

            # 图片列表始终显示完整内容，不使用滑动窗口
            # 滑动窗口只用于内部预加载优化，不影响用户可见的列表
            if hasattr(self, 'initial_batch_loaded') and not self.initial_batch_loaded:
                # 初始加载阶段：只显示前200张，快速启动
                start_index = 0
                end_index = min(200, total_count)
                self.logger.info(f"初始加载阶段，显示前 {end_index} 张图片")
            else:
                # 扫描完成后：始终显示完整列表
                start_index = 0
                end_index = total_count
                self.logger.info(f"显示完整图片列表，共 {total_count} 张图片")

            # 1. 准备数据
            # 将 Path 对象转换为字符串，适配 Model 接口
            display_files = [str(f) for f in self.image_files[start_index:end_index]]

            # 2. 预计算多分类集合 (O(N) -> Set lookup)
            multi_classified = {
                p for p, c in self.classified_images.items()
                if isinstance(c, list) and len(c) > 1
            }

            # 3. 批量初始化 Model (高性能)
            self.image_list_model._init_data(
                display_files,
                self.classified_images,
                self.removed_images,
                multi_classified
            )

            # 4. 恢复选中状态
            # 确保当前索引在显示范围内
            if 0 <= self.current_index < len(display_files):
                # 获取 ModelIndex (Row=current_index, Col=0)
                idx = self.image_list_model.index(self.current_index, 0)
                if idx.isValid():
                    # 使用 SelectionModel API 设置选中
                    self.image_list.selectionModel().setCurrentIndex(
                        idx,
                        QItemSelectionModel.SelectionFlag.ClearAndSelect
                    )
                    # 使用 View API 滚动
                    self.image_list.scrollTo(idx, QAbstractItemView.ScrollHint.EnsureVisible)

            # 如果列表是完整的，同步当前选中状态
            if start_index == 0 and end_index == total_count:
                QTimer.singleShot(100, self.sync_image_list_selection)
                
        except Exception as e:
            self.logger.error(f"更新图片列表失败: {e}")
    
    def _update_statistics_internal(self):
        """内部统计更新方法"""
        try:
            total_images = len(self.image_files)
            classified_count = len(self.classified_images)
            removed_count = len(self.removed_images)
            
            # 统计面板显示真实的数据，不显示滑动窗口信息
            display_count = None  # 不显示单独的显示数量
            
            if hasattr(self, 'initial_batch_loaded') and not self.initial_batch_loaded:
                # 初始加载阶段：显示加载进度
                display_count = min(200, total_images)
                self.logger.debug(f"统计显示：初始加载阶段 {display_count}/{total_images}")
            else:
                # 扫描完成后：始终显示完整统计，不显示滑动窗口信息
                display_count = None
                self.logger.debug(f"统计显示：完整列表 {total_images}")
            
            self.statistics_panel.update_statistics(
                total=total_images,
                classified=classified_count, 
                removed=removed_count,
                display_count=display_count
            )
        except Exception as e:
            self.logger.error(f"更新统计信息失败: {e}")
    
    def _update_ui_state_internal(self):
        """内部UI状态更新方法"""
        # 更新窗口标题
        if self.current_dir and self.image_files:
            title = f"图像分类工具 v{self.version} - {self.current_dir.name} ({self.current_index + 1}/{len(self.image_files)})"
            self.setWindowTitle(title)
    
    def _update_category_counts_internal(self):
        """内部类别计数更新方法"""
        # 重新计算类别计数
        self.category_counts.clear()
        
        for img_path, category in self.classified_images.items():
            # 处理多分类情况
            if isinstance(category, list):
                for cat in category:
                    if cat in self.categories:
                        self.category_counts[cat] = self.category_counts.get(cat, 0) + 1
            elif category in self.categories:
                self.category_counts[category] = self.category_counts.get(category, 0) + 1
        
        # 更新按钮显示
        for btn in self.category_buttons:
            category_name = btn.category_name
            btn.set_count(self.category_counts.get(category_name, 0))
    
    # ===== 状态管理方法 =====
    
    def load_state(self):
        """加载分类状态 - 从图片同级目录"""
        try:
            if not self.current_dir:
                return

            # 从图片目录的父目录加载状态文件
            parent_dir = self.current_dir.parent
            state_file = parent_dir / 'classification_state.json'

            if state_file.exists():
                with open(state_file, 'r', encoding='utf-8') as f:
                    state = json.load(f)

                self.classified_images = state.get('classified_images', {})
                self.removed_images = set(state.get('removed_images', []))

                # 恢复上次的图片索引
                self.saved_last_index = state.get('last_index', -1)
                self.logger.debug(f"加载的 last_index: {self.saved_last_index}")

                # 恢复操作模式状态
                saved_copy_mode = state.get('is_copy_mode', True)  # 默认为复制模式
                self._set_mode_direct(saved_copy_mode)  # 直接设置模式，不触发迁移逻辑

                # 恢复分类模式状态
                saved_multi_category = state.get('is_multi_category', False)  # 默认为单分类模式
                self.is_multi_category = saved_multi_category
                # 延迟更新按钮状态，确保UI组件已完全初始化
                QTimer.singleShot(10, lambda: self._update_category_mode_button_state())

                modes = []
                if saved_copy_mode:
                    modes.append("复制")
                else:
                    modes.append("移动")

                if saved_multi_category:
                    modes.append("多分类")
                else:
                    modes.append("单分类")

                self.logger.info(f"状态加载完成: {len(self.classified_images)} 个分类记录，操作模式: {' + '.join(modes)}")
                self.logger.debug(f"状态文件路径: {state_file}")
            else:
                self.logger.info("状态文件不存在，使用空状态")
                self.saved_last_index = -1
                # 确保按钮状态正确（默认单分类模式）
                self.is_multi_category = False
                QTimer.singleShot(10, lambda: self._update_category_mode_button_state())

        except Exception as e:
            self.logger.error(f"加载状态失败: {e}")
            self.saved_last_index = -1
    
    def _update_category_mode_button_state(self):
        """更新分类模式按钮状态 - 统一方法"""
        self.update_category_mode_button()

    def update_category_mode_button(self):
        """统一的分类模式按钮状态更新方法"""
        try:
            if hasattr(self, 'category_mode_button') and self.category_mode_button:
                # 更新按钮图标和提示
                if self.is_multi_category:
                    self.category_mode_button.setText('⇶')  # 多箭头表示多分类
                    self.category_mode_button.setToolTip('多分类模式 - 点击切换到单分类模式')
                else:
                    self.category_mode_button.setText('→')  # 单箭头表示单分类
                    self.category_mode_button.setToolTip('单分类模式 - 点击切换到多分类模式')

                mode_desc = "多分类" if self.is_multi_category else "单分类"
                self.logger.debug(f"分类模式按钮状态已更新: {mode_desc}")
            else:
                self.logger.warning("分类模式按钮不存在，无法更新状态")
        except Exception as e:
            self.logger.error(f"更新分类模式按钮状态失败: {e}")
    
    def init_category_counts(self):
        """初始化类别计数"""
        self.category_counts.clear()
        
        # 从 classified_images 获取分类记录计数
        for img_path, category in self.classified_images.items():
            # 处理多分类情况
            if isinstance(category, list):
                for cat in category:
                    if cat in self.categories:
                        self.category_counts[cat] = self.category_counts.get(cat, 0) + 1
            elif category in self.categories:
                self.category_counts[category] = self.category_counts.get(category, 0) + 1
        
        # 更新按钮显示
        self.update_category_buttons()
    
    def update_category_counts(self):
        """更新类别计数"""
        self.schedule_ui_update('category_counts')
    
    def update_category_buttons(self):
        """更新类别按钮"""
        self.schedule_ui_update('category_buttons')
    
    # ===== 图片显示和导航方法 =====

    def get_real_file_path(self, original_path: str) -> Path:
        """
        根据操作模式和分类状态计算文件的实际路径

        Args:
            original_path: JSON中存储的原始路径

        Returns:
            文件的实际路径
        """
        original_file = Path(original_path)

        # 复制模式：文件始终在原目录（包括多分类模式）
        if self.is_copy_mode:
            return original_file

        # 移动模式：检查分类状态
        # 已移除：文件在 remove 目录
        if original_path in self.removed_images:
            remove_dir = self.current_dir.parent / 'remove'
            return remove_dir / original_file.name

        # 已分类：文件在分类目录
        if original_path in self.classified_images:
            category = self.classified_images[original_path]
            category_dir = self.current_dir.parent / category
            return category_dir / original_file.name

        # 未分类：文件在原目录
        return original_file

    @performance_monitor
    def show_current_image(self):
        """显示当前图片（委托给ImageNavigationManager）"""
        # 先设置当前请求的图片路径，用于回调时判断
        if 0 <= self.current_index < len(self.image_files):
            img_path = str(self.image_files[self.current_index])
            real_path = str(self.get_real_file_path(img_path))
            self._current_requested_image = str(Path(real_path).resolve())

        if self._nav_manager:
            self._nav_manager.show_current_image()
        else:
            # 降级：直接调用内部方法
            self.logger.debug("[降级模式] ImageNavigationManager未初始化，使用内部方法显示图片")
            self._show_current_image_internal()
        
    def _show_current_image_internal(self):
        """内部显示当前图片方法 - 优化防止多图刷新"""
        if 0 <= self.current_index < len(self.image_files):
            img_path = str(self.image_files[self.current_index])

            # 计算文件的实际路径（根据操作模式和分类状态）
            real_path = str(self.get_real_file_path(img_path))

            # 记录图片文件信息（使用真实路径）
            self.log_image_info(real_path)

            # 立即更新窗口标题和状态信息
            self.update_window_title(img_path)

            # 设置当前图片索引用于智能缓存
            self.image_loader.set_current_image_index(self.current_index)

            # 检查缓存命中情况（使用真实路径）
            cache_key = self.image_loader._get_cache_key(real_path)
            is_cached = cache_key in self.image_loader.cache

            self.log_performance_info(
                "显示图片_开始",
                文件=Path(img_path).name,
                索引=f"{self.current_index + 1}/{len(self.image_files)}",
                缓存命中=is_cached
            )

            # 检查当前图片的分类状态并更新类别选择
            self.update_category_selection_for_current_image(img_path)

            # 如果缓存命中，直接显示；否则显示占位符
            if is_cached:
                # 直接从缓存加载，避免闪烁
                cached_data = self.image_loader._get_from_cache(cache_key)
                # 安全检查缓存数据类型
                if cached_data is not None:
                    # 检查是否为QPixmap类型
                    if isinstance(cached_data, QPixmap) and not cached_data.isNull():
                        self.image_label.set_image(cached_data)
                        self.statusBar.showMessage(f"📷 {Path(img_path).name}")
                    else:
                        # 缓存中可能是numpy数组或其他格式，转换为QPixmap后显示
                        cached_pixmap = self.convert_to_pixmap(cached_data)
                        if cached_pixmap is not None and not cached_pixmap.isNull():
                            self.image_label.set_image(cached_pixmap)
                            self.statusBar.showMessage(f"📷 {Path(img_path).name}")
                        else:
                            # 转换失败，显示占位符等待异步加载
                            self.show_loading_placeholder(img_path)
                else:
                    self.show_loading_placeholder(img_path)
            else:
                self.show_loading_placeholder(img_path)

            # 记录当前请求的图片路径（用于回调时判断）
            self._current_requested_image = str(Path(real_path).resolve())

            # 异步加载完整图片（使用真实路径）
            self.image_loader.load_image(real_path, priority=True)
            
            # 延迟预加载相邻图片，避免影响当前图片显示
            is_network_current = self._is_network_path(img_path)
            delay_time = 300 if is_network_current else 100
            
            QTimer.singleShot(delay_time, self.preload_adjacent_images)
            
            # 延迟更新图片列表高亮选中状态，避免阻塞当前图片显示
            QTimer.singleShot(50, self.sync_image_list_selection)
            
            # 调度UI状态更新
            self.schedule_ui_update('ui_state')
    
    def update_category_selection_for_current_image(self, image_path):
        """根据当前图片的分类状态更新类别选择"""
        try:
            # 获取当前图片的分类状态
            current_category = self.classified_images.get(image_path)
            
            # 处理多分类模式 - 当多个类别同时标记为已分类
            if isinstance(current_category, list) and current_category:
                # 标记所有已分类的类别
                for i, btn in enumerate(self.category_buttons):
                    # 如果类别在已分类列表中，设置为已分类状态
                    is_classified = btn.category_name in current_category
                    
                    # 设置标准分类状态
                    btn.set_classified(is_classified)
                    
                    # 设置多分类状态标记 - 当列表长度>1且当前类别在列表中时
                    is_multi = len(current_category) > 1 and is_classified
                    btn.set_multi_classified(is_multi)
                    
                    # 选中上次操作的类别或第一个已分类的类别
                    if self.last_operation_category and self.last_operation_category in self.ordered_categories:
                        # 优先选中上次操作的类别
                        should_check = btn.category_name == self.last_operation_category
                        if btn.category_name == self.last_operation_category:
                            self.current_category_index = i
                    elif btn.category_name == current_category[0]:
                        # 如果没有上次操作记录，选中第一个已分类的类别
                        should_check = True
                        self.current_category_index = i
                    else:
                        should_check = False
                        
                    btn.setChecked(should_check)
                
                self.logger.debug(f"图片 {Path(image_path).name} 已分类到多个类别: {current_category}")
                return
                
            # 优先保持上次操作的类别选择，以便快速连续分类
            if (self.last_operation_category and 
                self.last_operation_category in self.ordered_categories):
                # 保持上次操作的类别选中状态
                self.current_category_index = self.ordered_categories.index(self.last_operation_category)
                
                # 更新类别按钮状态：选中状态 + 分类状态
                for i, btn in enumerate(self.category_buttons):
                    btn.setChecked(i == self.current_category_index)
                    is_classified = btn.category_name == current_category
                    btn.set_classified(is_classified)
                    # 清除多分类状态
                    btn.set_multi_classified(False)
                
                self.logger.debug(f"保持上次操作类别选择: {self.last_operation_category}")
                return
            
            # 如果没有上次操作记录，则根据当前图片的分类状态设置
            if current_category and current_category in self.ordered_categories:
                # 找到对应类别的索引
                self.current_category_index = self.ordered_categories.index(current_category)
                
                # 更新类别按钮选中状态
                for i, btn in enumerate(self.category_buttons):
                    btn.setChecked(i == self.current_category_index)
                    # 设置已分类状态
                    is_classified = btn.category_name == current_category
                    btn.set_classified(is_classified)
                    # 清除多分类状态
                    btn.set_multi_classified(False)
                
                self.logger.debug(f"图片 {Path(image_path).name} 已分类到: {current_category}")
            else:
                # 未分类图片，保持当前选择或选择第一个类别
                if self.current_category_index < 0 and self.category_buttons:
                    self.current_category_index = 0
                    
                for i, btn in enumerate(self.category_buttons):
                    btn.setChecked(i == self.current_category_index)
                    btn.set_classified(False)
                    # 清除多分类状态
                    btn.set_multi_classified(False)
                
                self.logger.debug(f"图片 {Path(image_path).name} 未分类，保持当前选择")
                
        except Exception as e:
            self.logger.error(f"更新图片类别选择状态失败: {e}")
        
        # 强制刷新按钮样式
        self.refresh_category_buttons_style()
      
    def update_window_title(self, image_path):
        """更新窗口标题 - 顶部显示目录名+进度"""
        try:
            if self.current_dir and self.image_files:
                # 窗口标题：目录名 + 进度
                dir_name = self.current_dir.name
                progress = f"({self.current_index + 1}/{len(self.image_files)})"
                title = f"图像分类工具 v{self.version} - {dir_name} {progress}"
                self.setWindowTitle(title)
                
                # 状态栏：图片名称
                filename = Path(image_path).name
                self.statusBar.showMessage(f"📷 {filename}")
                
        except Exception as e:
            self.logger.debug(f"更新窗口标题失败: {e}")
    
    def show_loading_placeholder(self, image_path=None):
        """显示加载占位符"""
        try:
            # 创建简单的加载占位符
            placeholder_size = QSize(400, 300)
            placeholder = QPixmap(placeholder_size)
            placeholder.fill(QColor(240, 240, 240))

            # 立即显示占位符
            self.image_label.set_image(placeholder)

            # 更新状态栏
            if image_path:
                self.statusBar.showMessage(f"🔄 正在加载: {Path(image_path).name}")
            else:
                self.statusBar.showMessage("🔄 正在加载图片...")

        except Exception as e:
            self.logger.debug(f"显示加载占位符失败: {e}")

    def sync_image_list_selection(self):
        """同步图片列表的选中状态（委托给ImageNavigationManager）"""
        if self._nav_manager:
            self._nav_manager.sync_image_list_selection()

    def preload_adjacent_images(self):
        """预加载相邻图片（委托给ImageNavigationManager）"""
        if self._nav_manager:
            self._nav_manager.preload_adjacent_images()

    def log_image_info(self, image_path, pixmap=None):
        """记录图片详细信息"""
        if not self.enable_performance_logging:
            return
            
        try:
            file_path = Path(image_path)
            if file_path.exists():
                file_size = file_path.stat().st_size
                file_size_mb = file_size / 1024 / 1024
                
                # 获取图片尺寸
                width, height = 0, 0
                if pixmap and not pixmap.isNull():
                    width, height = pixmap.width(), pixmap.height()
                    resolution_mp = (width * height) / 1000000
                    
                    self.performance_stats['current_image_info'] = {
                        'path': str(file_path),
                        'size_mb': file_size_mb,
                        'width': width,
                        'height': height,
                        'resolution_mp': resolution_mp
                    }
                    
                    self.log_performance_info(
                        "图片信息",
                        文件=file_path.name,
                        大小=f"{file_size_mb:.2f}MB",
                        分辨率=f"{width}x{height}",
                        像素=f"{resolution_mp:.1f}MP"
                    )
                else:
                    self.log_performance_info(
                        "图片文件",
                        文件=file_path.name,
                        大小=f"{file_size_mb:.2f}MB"
                    )
        except Exception as e:
            self.logger.debug(f"图片信息记录失败: {e}")
    
    # ===== 导航方法 =====

    def _should_enable_loop(self) -> bool:
        """判断当前是否应该启用循环翻页

        Returns:
            bool: True表示启用循环，False表示不启用
        """
        try:
            # 动态刷新配置，确保开关即时生效（避免重启才能应用）
            if hasattr(self, 'app_config'):
                self.app_config.reload_config()
        except Exception as e:
            self.logger.debug(f"[循环翻页] 刷新配置失败: {e}")

        # 检查是否为网络路径
        is_network = hasattr(self, 'is_network_working_path') and self.is_network_working_path

        if is_network:
            # 网络路径：使用网络循环开关
            loop_enabled = self.app_config.network_loop_enabled
            self.logger.debug(f"[循环翻页] 网络路径，循环开关：{'开启' if loop_enabled else '关闭'}")
            return loop_enabled
        else:
            # 本地路径：使用本地循环开关
            loop_enabled = self.app_config.local_loop_enabled
            self.logger.debug(f"[循环翻页] 本地路径，循环开关：{'开启' if loop_enabled else '关闭'}")
            return loop_enabled

    def prev_image(self):
        """上一张图片（委托给ImageNavigationManager）"""
        if self._nav_manager:
            self._nav_manager.prev_image()

    def _record_direction(self, direction):
        """记录翻页方向（优化3：智能预加载）"""
        if 'direction_history' not in self.user_behavior:
            self.user_behavior['direction_history'] = []
        self.user_behavior['direction_history'].append(direction)
        if len(self.user_behavior['direction_history']) > 10:
            self.user_behavior['direction_history'] = self.user_behavior['direction_history'][-10:]

    def next_image(self):
        """下一张图片（委托给ImageNavigationManager）"""
        if self._nav_manager:
            self._nav_manager.next_image()

    def prev_category(self):
        """选择上一个类别 - 参考原始实现"""
        if not self.category_buttons:
            return
            
        # 取消当前选中
        if 0 <= self.current_category_index < len(self.category_buttons):
            self.category_buttons[self.current_category_index].setChecked(False)
            
        # 循环选择上一个（支持从头到尾的循环）
        if self.current_category_index <= 0:
            self.current_category_index = len(self.category_buttons) - 1
        else:
            self.current_category_index -= 1
            
        # 设置新的选中状态
        self.category_buttons[self.current_category_index].setChecked(True)
        
        # 确保选中的按钮可见
        scroll_area = self.findChild(QScrollArea)
        if scroll_area:
            scroll_area.ensureWidgetVisible(self.category_buttons[self.current_category_index])
            
        self.logger.info(f"选择类别: {self.ordered_categories[self.current_category_index]}")
    
    def next_category(self):
        """选择下一个类别 - 参考原始实现"""
        if not self.category_buttons:
            return
            
        # 取消当前选中
        if 0 <= self.current_category_index < len(self.category_buttons):
            self.category_buttons[self.current_category_index].setChecked(False)
            
        # 循环选择下一个（支持从尾到头的循环）
        if self.current_category_index >= len(self.category_buttons) - 1:
            self.current_category_index = 0
        else:
            self.current_category_index += 1
            
        # 设置新的选中状态
        self.category_buttons[self.current_category_index].setChecked(True)
        
        # 确保选中的按钮可见
        scroll_area = self.findChild(QScrollArea)
        if scroll_area:
            scroll_area.ensureWidgetVisible(self.category_buttons[self.current_category_index])
            
        self.logger.info(f"选择类别: {self.ordered_categories[self.current_category_index]}")
    
    def update_category_selection(self):
        """更新类别选择状态"""
        if (self.category_buttons and 
            0 <= self.current_category_index < len(self.category_buttons)):
            # 清除所有按钮的选中状态
            for btn in self.category_buttons:
                btn.setChecked(False)
            
            # 设置当前按钮为选中状态
            self.category_buttons[self.current_category_index].setChecked(True)
    
    def confirm_category(self):
        """确认当前选中的类别"""
        if (self.ordered_categories and 
            0 <= self.current_category_index < len(self.ordered_categories)):
            category_name = self.ordered_categories[self.current_category_index]
            self.move_to_category(category_name)
    
    # ===== 事件处理方法 =====
    
    def on_image_list_item_clicked(self, index):
        """处理图片列表项点击

        Args:
            index: QModelIndex, 点击的列表项索引
        """
        # Phase 1.1 Migration: 适配 QListView 的 clicked 信号 (传递 QModelIndex)
        if index.isValid():
            # 从自定义数据角色获取原始图片索引
            img_idx = index.data(ImageListModel.ROLE_IMAGE_INDEX)

            if img_idx is not None:
                self.current_index = img_idx
                self.show_current_image()

    def create_filter_status_icon(self, status_type, is_checked=False):
        """创建筛选菜单的状态图标（带checkbox）

        Args:
            status_type: 状态类型，'unclassified', 'classified', 'removed'
            is_checked: 是否选中

        Returns:
            QIcon: 状态图标
        """
        # 创建72x40的图标（左侧checkbox + 右侧状态图标）

        pixmap = QPixmap(72, 40)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 绘制checkbox（左侧，增大尺寸）
        checkbox_x = 4
        checkbox_y = 6
        checkbox_size = 28

        # Checkbox背景
        if is_checked:
            painter.setPen(QPen(QColor("#0D6EFD"), 2))
            painter.setBrush(QBrush(QColor("#0D6EFD"), Qt.BrushStyle.SolidPattern))
        else:
            painter.setPen(QPen(QColor("#ADB5BD"), 2))
            painter.setBrush(QBrush(QColor("#FFFFFF"), Qt.BrushStyle.SolidPattern))

        painter.drawRoundedRect(checkbox_x, checkbox_y, checkbox_size, checkbox_size, 5, 5)

        # 绘制勾选标记（调整位置和大小）
        if is_checked:
            painter.setPen(QPen(Qt.GlobalColor.white, 3))
            painter.drawLine(checkbox_x + 7, checkbox_y + 14, checkbox_x + 11, checkbox_y + 19)
            painter.drawLine(checkbox_x + 11, checkbox_y + 19, checkbox_x + 21, checkbox_y + 8)

        # 绘制状态图标（右侧，偏移36像素）
        offset_x = 36

        # 根据状态设置颜色和图标
        if status_type == 'classified':
            # 已分类 - 绿色勾选图标
            color = QColor("#4CAF50")
            shadow_color = QColor("#2E7D32")
        elif status_type == 'removed':
            # 已移除 - 红色删除图标
            color = QColor("#F44336")
            shadow_color = QColor("#C62828")
        else:  # unclassified
            # 待处理 - 橙色警告图标
            color = QColor("#FF9800")
            shadow_color = QColor("#F57C00")

        # 绘制阴影效果（垂直居中）
        painter.setPen(QPen(shadow_color, 2))
        painter.setBrush(QBrush(shadow_color, Qt.BrushStyle.SolidPattern))
        painter.drawEllipse(offset_x + 3, 7, 28, 28)

        # 绘制主圆形（垂直居中）
        painter.setPen(QPen(color, 2))
        painter.setBrush(QBrush(color, Qt.BrushStyle.SolidPattern))
        painter.drawEllipse(offset_x + 2, 6, 28, 28)

        # 绘制状态符号（调整y坐标以居中）
        painter.setPen(QPen(Qt.GlobalColor.white, 3))
        if status_type == 'classified':
            # 绘制√ - 更优雅的勾选
            painter.drawLine(offset_x + 8, 20, offset_x + 14, 26)
            painter.drawLine(offset_x + 14, 26, offset_x + 26, 14)
        elif status_type == 'removed':
            # 绘制× - 删除符号
            painter.drawLine(offset_x + 10, 14, offset_x + 24, 28)
            painter.drawLine(offset_x + 24, 14, offset_x + 10, 28)
        else:  # unclassified
            # 绘制! - 待处理警告
            painter.setPen(QPen(Qt.GlobalColor.white, 2))
            painter.drawLine(offset_x + 16, 12, offset_x + 16, 22)  # 竖线
            painter.drawEllipse(offset_x + 14, 26, 4, 4)  # 点

        painter.end()
        return QIcon(pixmap)

    def create_checkbox_icon(self, checked=False):
        """创建复选框图标

        Args:
            checked: 是否选中状态
        """

        # 创建18x18的图标
        pixmap = QPixmap(18, 18)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if checked:
            # 选中状态 - 蓝色背景 + 白色打勾
            painter.setPen(QPen(QColor(default_theme.colors.PRIMARY_DARK), 2))
            painter.setBrush(QBrush(QColor(default_theme.colors.PRIMARY)))
            painter.drawRoundedRect(1, 1, 16, 16, 3, 3)

            # 绘制白色打勾符号
            painter.setPen(QPen(Qt.GlobalColor.white, 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.drawLine(4, 9, 7, 13)
            painter.drawLine(7, 13, 14, 5)
        else:
            # 未选中状态 - 灰色边框 + 空白背景
            painter.setPen(QPen(QColor(default_theme.colors.BORDER_MEDIUM), 2))
            painter.setBrush(QBrush(QColor(default_theme.colors.BACKGROUND_CARD)))
            painter.drawRoundedRect(1, 1, 16, 16, 3, 3)

        painter.end()
        return QIcon(pixmap)

    def show_sort_menu(self):
        """显示排序方式菜单"""

        menu = QMenu(self)
        menu.setStyleSheet(WidgetStyles.get_context_menu_style())

        # 获取当前排序模式
        current_mode = getattr(self.config, 'category_sort_mode', 'name')

        # 三个单选菜单项 - 使用自定义复选框图标
        action_name = QAction(self.create_checkbox_icon(current_mode == 'name'), "按名称排序", self)
        action_name.triggered.connect(lambda: self.change_category_sort_mode('name'))
        menu.addAction(action_name)

        action_shortcut = QAction(self.create_checkbox_icon(current_mode == 'shortcut'), "按快捷键排序", self)
        action_shortcut.triggered.connect(lambda: self.change_category_sort_mode('shortcut'))
        menu.addAction(action_shortcut)

        action_count = QAction(self.create_checkbox_icon(current_mode == 'count'), "按分类数量排序", self)
        action_count.triggered.connect(lambda: self.change_category_sort_mode('count'))
        menu.addAction(action_count)

        # 在排序按钮下方显示菜单 - 智能定位防止超出窗口
        # 先让菜单调整大小以获得准确的尺寸
        menu.adjustSize()

        # 获取按钮的右下角位置（改为右对齐）
        button_global_rect = self.sort_button.mapToGlobal(self.sort_button.rect().bottomRight())
        menu_size = menu.sizeHint()

        # 获取主窗口的实际可见区域
        window_rect = self.rect()
        window_global_pos = self.mapToGlobal(window_rect.topLeft())
        window_right = window_global_pos.x() + window_rect.width()
        window_bottom = window_global_pos.y() + window_rect.height()

        # 初始位置：按钮右下角，菜单右对齐
        x = button_global_rect.x() - menu_size.width()
        y = button_global_rect.y()

        # 确保菜单不超出窗口左边界
        if x < window_global_pos.x():
            x = window_global_pos.x() + 5

        # 如果菜单超出窗口底部，显示在按钮上方
        if y + menu_size.height() > window_bottom - 10:  # 留10px底部边距
            y = self.sort_button.mapToGlobal(self.sort_button.rect().topRight()).y() - menu_size.height()

        menu.exec(QPoint(x, y))

    def _on_image_search(self, text: str):
        """处理图片列表搜索

        Args:
            text: 搜索关键字
        """
        self._image_search_text = text.strip()
        self.apply_image_filter()

        # 搜索后自动选中第一个匹配项
        if self.image_list_model.rowCount() > 0:
            first_index = self.image_list_model.index(0, 0)
            self.image_list.setCurrentIndex(first_index)
            # 获取原始索引并跳转到该图片
            original_idx = first_index.data(ImageListModel.ROLE_IMAGE_INDEX)
            if original_idx is not None:
                self.current_index = original_idx
                self.show_current_image()

        # 显示搜索结果提示
        total_count = len(self.image_files) if hasattr(self, 'image_files') else 0
        match_count = self.image_list_model.rowCount()
        toast_info(self, f"搜索 \"{text}\"：找到 {match_count}/{total_count} 个匹配项")

    def _on_image_search_cleared(self):
        """处理搜索清除/关闭"""
        if self._image_search_text:  # 仅在有搜索词时才需要刷新
            self._image_search_text = ""
            self.apply_image_filter()

    def show_filter_menu(self):
        """显示筛选菜单"""

        menu = QMenu(self)
        menu.setStyleSheet(WidgetStyles.get_context_menu_style())

        # 三个可勾选的菜单项 - 使用自定义复选框图标
        action_unclassified = QAction(self.create_checkbox_icon(self.filter_unclassified), "⚠️ 显示未分类图片", self)
        action_unclassified.triggered.connect(lambda: self.toggle_filter('unclassified'))
        menu.addAction(action_unclassified)

        action_classified = QAction(self.create_checkbox_icon(self.filter_classified), "✅ 显示已分类图片", self)
        action_classified.triggered.connect(lambda: self.toggle_filter('classified'))
        menu.addAction(action_classified)

        action_removed = QAction(self.create_checkbox_icon(self.filter_removed), "❌ 显示已移除图片", self)
        action_removed.triggered.connect(lambda: self.toggle_filter('removed'))
        menu.addAction(action_removed)

        menu.addSeparator()

        # 统计信息（不可点击）
        if hasattr(self, 'image_files') and self.image_files:
            stats = self.get_filter_stats()
            stats_text = f"未分类: {stats['unclassified']} | 已分类: {stats['classified']} | 已移除: {stats['removed']}"
            action_stats = QAction(stats_text, self)
            action_stats.setEnabled(False)  # 不可点击
            menu.addAction(action_stats)

        # 在筛选按钮下方显示菜单 - 智能定位防止超出窗口
        # 先让菜单调整大小以获得准确的尺寸
        menu.adjustSize()

        # 获取按钮的右下角位置（改为右对齐）
        button_global_rect = self.filter_button.mapToGlobal(self.filter_button.rect().bottomRight())
        menu_size = menu.sizeHint()

        # 获取主窗口的实际可见区域
        window_rect = self.rect()
        window_global_pos = self.mapToGlobal(window_rect.topLeft())
        window_right = window_global_pos.x() + window_rect.width()
        window_bottom = window_global_pos.y() + window_rect.height()

        # 初始位置：按钮右下角，菜单右对齐
        x = button_global_rect.x() - menu_size.width()
        y = button_global_rect.y()

        # 确保菜单不超出窗口左边界
        if x < window_global_pos.x():
            x = window_global_pos.x() + 5

        # 如果菜单超出窗口底部，显示在按钮上方
        if y + menu_size.height() > window_bottom - 10:  # 留10px底部边距
            y = self.filter_button.mapToGlobal(self.filter_button.rect().topRight()).y() - menu_size.height()

        menu.exec(QPoint(x, y))

    def toggle_filter(self, filter_type):
        """切换过滤器状态"""
        # 切换状态
        if filter_type == 'unclassified':
            self.filter_unclassified = not self.filter_unclassified
        elif filter_type == 'classified':
            self.filter_classified = not self.filter_classified
        elif filter_type == 'removed':
            self.filter_removed = not self.filter_removed

        # 至少保留一个选项
        if not (self.filter_unclassified or self.filter_classified or self.filter_removed):
            toast_warning(self, "至少需要选择一种图片类型")
            # 恢复刚才的选择
            if filter_type == 'unclassified':
                self.filter_unclassified = True
            elif filter_type == 'classified':
                self.filter_classified = True
            elif filter_type == 'removed':
                self.filter_removed = True
            return

        # 应用过滤
        self.apply_image_filter()

        # 更新按钮状态（有过滤时高亮）
        is_filtering = not (self.filter_unclassified and self.filter_classified and self.filter_removed)
        self.filter_button.setProperty("active", is_filtering)
        self.filter_button.style().unpolish(self.filter_button)
        self.filter_button.style().polish(self.filter_button)

    def apply_image_filter(self):
        """
        应用过滤器到图片列表
        Phase 1.1: Model/View架构版本，保留缩略图缓存
        Codex Review修复：空数据处理
        """
        # Codex Review修复：空数据时也要更新Model，避免保留旧数据
        if not hasattr(self, 'image_files') or not self.image_files:
            # 清空Model
            if hasattr(self, 'image_list_model'):
                self.image_list_model.update_data([], {}, set(), set())
                self._visible_indices = []
                self._original_to_filtered_index = {}
            # 清空图像显示
            self.current_index = -1
            self.image_label.clear()
            return

        # 保存当前选中的图片路径
        current_index = self.image_list.currentIndex()
        current_path = None
        if current_index.isValid():
            current_path = current_index.data(ImageListModel.ROLE_FULL_PATH)

        # Phase 1.1: 计算多分类集合（Codex Review发现multi_classified_images不存在）
        multi_classified = {
            p for p, c in self.classified_images.items()
            if isinstance(c, list) and len(c) > 1
        }

        # 过滤图片列表并测量最大文本宽度（Codex+Gemini方案：供横向滚动宽度计算）
        filtered_files = []
        original_indices = []  # 保存原始索引映射
        font_metrics = self.image_list.fontMetrics()
        max_text_width = 0

        # 搜索关键字预处理（小写，用于大小写不敏感匹配）
        search_keyword = self._image_search_text.lower() if self._image_search_text else ""

        for idx, img_path in enumerate(self.image_files):
            img_path_str = str(img_path)
            file_name = Path(img_path_str).name

            # 判断状态
            is_removed = img_path_str in self.removed_images
            is_classified = img_path_str in self.classified_images
            is_unclassified = not is_removed and not is_classified

            # 检查状态过滤
            status_show = (
                (is_unclassified and self.filter_unclassified) or
                (is_classified and self.filter_classified) or
                (is_removed and self.filter_removed)
            )

            # 检查搜索关键字匹配（大小写不敏感）
            search_match = (not search_keyword) or (search_keyword in file_name.lower())

            # 同时满足状态过滤和搜索匹配
            should_show = status_show and search_match

            if should_show:
                filtered_files.append(img_path)
                original_indices.append(idx)
                # Codex方案：记录最长文件名宽度（单次遍历，24k规模可接受）
                file_name = Path(img_path_str).name
                max_text_width = max(max_text_width, font_metrics.horizontalAdvance(file_name))

        # 更新Model数据（保留缩略图缓存，传递原始索引）
        self.image_list_model.update_data(
            filtered_files,
            self.classified_images,
            self.removed_images,
            multi_classified,  # 使用局部计算的多分类集合
            original_indices  # 传递原始索引，确保ROLE_IMAGE_INDEX返回正确值
        )

        # Codex+Gemini方案：根据最长文件名设置列表项宽度，保证横向滚动显示完整
        self._update_image_list_grid_width(max_text_width)

        # 保存过滤索引映射（用于滚动定位等场景）
        # original_index -> filtered_row
        self._original_to_filtered_index = {v: k for k, v in enumerate(original_indices)}

        # Codex Review修复：保存可见索引列表，用于next/prev导航
        # 这是一个有序列表，包含所有过滤后可见图片的original_index
        self._visible_indices = original_indices  # [0, 2, 5, 7, ...] 按顺序排列

        # 恢复选中
        # Codex优化：使用Model的_path_map进行O(1)查找而不是线性扫描
        # Bug修复-P0：处理当前图片被过滤掉的情况（row=None）
        if current_path:
            # O(1)查找路径对应的行
            row = self.image_list_model._path_map.get(str(current_path))
            if row is not None and 0 <= row < self.image_list_model.rowCount():
                # 当前图片仍在过滤列表中，恢复选中
                model_index = self.image_list_model.index(row, 0)
                self.image_list.setCurrentIndex(model_index)
                # 更新current_index为原始索引（从Model获取）
                self.current_index = model_index.data(ImageListModel.ROLE_IMAGE_INDEX)
            elif self.image_list_model.rowCount() > 0:
                # 当前图片被过滤掉（row=None），回退到第一张可见图片
                # Gemini建议：自动跳转比清空预览更符合用户工作流
                model_index = self.image_list_model.index(0, 0)
                self.image_list.setCurrentIndex(model_index)
                self.current_index = model_index.data(ImageListModel.ROLE_IMAGE_INDEX)
        elif self.image_list_model.rowCount() > 0:
            # 没有当前路径（首次加载），默认选中第一项
            model_index = self.image_list_model.index(0, 0)
            self.image_list.setCurrentIndex(model_index)
            # 更新current_index为原始索引（从Model获取）
            self.current_index = model_index.data(ImageListModel.ROLE_IMAGE_INDEX)

        # 更新图片显示
        # Codex Review修复：过滤结果为空时清空显示
        if self.image_list_model.rowCount() > 0:
            self.show_current_image()
        else:
            # 过滤结果为空，清空显示
            self.current_index = -1
            self.image_label.clear()
            toast_info(self, "当前过滤条件下没有图片")

    def get_filter_stats(self):
        """获取过滤统计信息"""
        stats = {
            'unclassified': 0,
            'classified': 0,
            'removed': 0
        }

        if not hasattr(self, 'image_files') or not self.image_files:
            return stats

        for img_path in self.image_files:
            img_path_str = str(img_path)
            if img_path_str in self.removed_images:
                stats['removed'] += 1
            elif img_path_str in self.classified_images:
                stats['classified'] += 1
            else:
                stats['unclassified'] += 1

        return stats

    def _update_image_list_grid_width(self, max_text_width: int):
        """
        Codex+Gemini方案：根据最长文件名计算列表项宽度，保证横向滚动显示完整

        Args:
            max_text_width: 最长文件名的像素宽度（由QFontMetrics.horizontalAdvance计算）
        """
        try:
            # 获取Delegate的布局常量（紧凑模式：无缩略图）
            delegate = self.image_list.itemDelegate()
            padding = getattr(delegate, 'PADDING', 6)
            icon_size = getattr(delegate, 'ICON_SIZE', 20)

            # 计算基础宽度：padding + 图标 + padding + 文本 + padding（紧凑模式）
            base_width = padding + icon_size + padding + padding
            item_width = base_width + max_text_width

            # Gemini建议：设置最大宽度上限（400-500px），防止超长文件名撑爆布局
            MAX_WIDTH = 500
            item_width = min(item_width, MAX_WIDTH)
            # 确保最小宽度
            item_width = max(item_width, 200)

            # 获取行高（紧凑模式：44px）
            if self.image_list_model.rowCount() > 0:
                row_height = self.image_list.sizeHintForRow(0)
            else:
                row_height = max(44, icon_size + 2 * padding)

            # 设置统一的GridSize，配合setUniformItemSizes(True)保持性能
            from PyQt6.QtCore import QSize
            self.image_list.setGridSize(QSize(item_width, row_height))
            self.image_list.updateGeometry()

        except Exception as e:
            self.logger.debug(f"更新列表项宽度失败: {e}")

    def select_category(self, category_name):
        """选择类别并更新视觉状态"""
        self.selected_category = category_name
        if category_name in self.ordered_categories:
            # 更新当前选中的索引
            self.current_category_index = self.ordered_categories.index(category_name)
            
            # 清除所有按钮的选中状态
            for btn in self.category_buttons:
                btn.setChecked(False)
            
            # 设置当前按钮为选中状态
            if 0 <= self.current_category_index < len(self.category_buttons):
                self.category_buttons[self.current_category_index].setChecked(True)
                
                # 确保选中的按钮可见
                scroll_area = self.findChild(QScrollArea)
                if scroll_area:
                    scroll_area.ensureWidgetVisible(self.category_buttons[self.current_category_index])
                    
            self.logger.info(f"鼠标选择类别: {category_name}")
    
    def move_to_category(self, category_name):
        """分类当前图片到指定类别（通过FileOperationManager）"""
        if not self._file_ops_manager:
            self.logger.error("FileOperationManager未初始化")
            return
        current_path = self.get_current_image_path()
        if current_path:
            self._file_ops_manager.move_to_category(str(current_path), category_name)
            # Manager会触发file_moved信号，UI刷新在on_file_moved中处理

    def _update_single_image_status(self, image_index, image_path):
        """更新单个图片在列表中的状态图标"""
        try:
            # Phase 1.1 Migration: 使用 Model API O(1) 更新状态
            # 避免遍历 View，提高交互响应速度

            if not hasattr(self, 'image_list_model'):
                return

            # 1. 计算新状态
            is_classified = image_path in self.classified_images
            is_removed = image_path in self.removed_images

            is_multi = False
            if is_classified:
                current_category = self.classified_images.get(image_path)
                is_multi = isinstance(current_category, list) and len(current_category) > 1

            # 2. 调用 Model 接口更新 (O(1) 查找 + 自动刷新 Delegate)
            self.image_list_model.update_status(image_index, is_classified, is_removed, is_multi)

        except Exception as e:
            self.logger.debug(f"更新单个图片状态失败: {e}")
    
    def move_to_remove(self):
        """移除当前图片（通过FileOperationManager）"""
        if not self._file_ops_manager:
            self.logger.error("FileOperationManager未初始化")
            return
        current_path = self.get_current_image_path()
        if current_path:
            self._file_ops_manager.move_to_remove(str(current_path))
            # Manager会触发file_removed信号，UI刷新在on_file_removed中处理

    def _undo_classification(self, image_path, category):
        """撤销分类（通过FileOperationManager）"""
        if not self._file_ops_manager:
            self.logger.error("FileOperationManager未初始化")
            return
        self._file_ops_manager._undo_classification(image_path, category)
        # Manager会触发file_restored信号，UI刷新在on_file_restored中处理

    def _get_file_hash(self, file_path):
        """计算文件的MD5哈希值"""
        try:
            hash_md5 = hashlib.md5()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
            return hash_md5.hexdigest()
        except Exception as e:
            self.logger.error(f"计算文件哈希失败: {e}")
            return None
    
    def _handle_duplicate_file(self, source_path, target_path):
        """处理文件重复的情况"""
        source_file = Path(source_path)
        target_file = Path(target_path)
        
        # 计算哈希值比较
        source_hash = self._get_file_hash(source_path)
        target_hash = self._get_file_hash(target_path)
        
        # 判断是否为相同文件
        is_same_file = (source_hash == target_hash and source_hash is not None)
        
        # 准备提示信息
        if is_same_file:
            hash_info = "✅ 文件内容完全相同（哈希值匹配）"
            main_text = f"目标位置已存在同名文件：\n{target_file.name}"
            detail_text = f"{hash_info}\n\n这是同一张图片，建议选择「覆盖」或「取消」。"
        else:
            hash_info = "⚠️ 文件内容不同（哈希值不匹配）"
            main_text = f"目标位置已存在同名文件：\n{target_file.name}"
            detail_text = f"{hash_info}\n\n虽然文件名相同，但这是不同的图片。"
        
        # 创建自定义消息框
        msg = QMessageBox(self)
        msg.setWindowTitle("文件名冲突")
        msg.setText(main_text)
        msg.setInformativeText(detail_text)
        msg.setIcon(QMessageBox.Icon.Question)
        
        # 设置程序图标
        try:
            icon_path = self._get_resource_path('assets/icon.ico')
            if icon_path and icon_path.exists():
                msg.setWindowIcon(QIcon(str(icon_path)))
        except Exception:
            pass
        
        # 设置主题样式
        c = default_theme.colors
        msg.setStyleSheet(f"""
            QMessageBox {{
                background-color: {c.BACKGROUND_CARD};
                color: {c.TEXT_PRIMARY};
                border: 1px solid {c.BORDER_MEDIUM};
                border-radius: 8px;
                font-size: 14px;
                min-width: 400px;
            }}
            QMessageBox QLabel {{
                color: {c.TEXT_PRIMARY};
                font-size: 14px;
                padding: 10px;
            }}
            QMessageBox QPushButton {{
                background-color: {c.PRIMARY};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 13px;
                font-weight: bold;
                min-width: 80px;
                margin: 2px;
            }}
            QMessageBox QPushButton:hover {{
                background-color: {c.PRIMARY_DARK};
            }}
            QMessageBox QPushButton:pressed {{
                background-color: {c.PRIMARY_DARK};
            }}
            QMessageBox QPushButton[text="覆盖"] {{
                background-color: {c.ERROR};
            }}
            QMessageBox QPushButton[text="覆盖"]:hover {{
                background-color: {c.ERROR_DARK};
            }}
            QMessageBox QPushButton[text="重命名"] {{
                background-color: {c.WARNING};
            }}
            QMessageBox QPushButton[text="重命名"]:hover {{
                background-color: {c.WARNING_DARK};
            }}
        """)
        
        # 添加中文按钮
        overwrite_btn = msg.addButton("覆盖", QMessageBox.ButtonRole.AcceptRole)
        rename_btn = msg.addButton("重命名", QMessageBox.ButtonRole.ActionRole)
        cancel_btn = msg.addButton("取消", QMessageBox.ButtonRole.RejectRole)
        
        # 设置默认按钮
        if is_same_file:
            msg.setDefaultButton(overwrite_btn)
        else:
            msg.setDefaultButton(rename_btn)
        
        # 显示对话框
        msg.exec()
        
        clicked_button = msg.clickedButton()
        
        if clicked_button == overwrite_btn:
            # 覆盖：返回原路径
            self.logger.info(f"用户选择覆盖同名文件: {target_file.name}")
            return target_path
        elif clicked_button == rename_btn:
            # 重命名：返回新路径
            renamed_path = self._get_renamed_target(target_path)
            self.logger.info(f"用户选择重命名文件: {target_file.name} -> {Path(renamed_path).name}")
            return renamed_path
        else:
            # 取消：返回None
            self.logger.info(f"用户取消文件操作: {target_file.name}")
            return None
    
    def _get_renamed_target(self, target_path):
        """获取重命名后的目标路径"""
        target_file = Path(target_path)
        base_name = target_file.stem
        ext = target_file.suffix
        parent_dir = target_file.parent
        
        counter = 1
        while True:
            new_target = parent_dir / f"{base_name}_{counter}{ext}"
            if not new_target.exists():
                return str(new_target)
            counter += 1

    def refresh_categories(self):
        """刷新类别并同步文件状态"""
        if self.current_dir:
            try:
                self.logger.info("开始刷新并同步目录状态...")
                
                # 先重新加载类别
                self._load_categories_only()
                
                # 同步文件状态
                sync_results = self._sync_file_states()
                
                # 强制重新计算类别计数
                self.init_category_counts()
                
                # 健康检查并修复快捷键（这是关键修复）
                QTimer.singleShot(100, self._check_and_fix_shortcuts)
                
                # 强制更新所有UI组件，无论是否检测到变化
                self.schedule_ui_update('image_list', 'category_buttons', 'category_counts', 'statistics')

                # Bug修复-P1：F5刷新后重新应用过滤状态（Codex方案：用标志位替代硬编码延迟）
                # 在perform_batch_ui_update完成image_list更新后自动调用apply_image_filter
                self._pending_reapply_filter = True

                # 显示同步结果（只有在有变化时才显示）
                if sync_results['changes_detected']:
                    self._show_sync_results(sync_results)
                    toast_success(self,"目录状态已刷新并同步")
                else:
                    # 即使没有检测到变化，也要显示刷新完成的信息
                    self.statusBar.showMessage("🔄 目录状态已刷新")
                    toast_success(self,"目录状态已刷新")

                self.logger.info("目录状态刷新完成")
                
            except Exception as e:
                self.logger.error(f"刷新目录状态失败: {e}")
                toast_error(self,f"刷新失败: {str(e)}")
    
    def _check_and_fix_shortcuts(self):
        """检查并修复快捷键"""
        if self.shortcut_manager:
            self.shortcut_manager.check_and_fix_shortcuts()
    
    def _periodic_shortcut_check(self):
        """定期快捷键检查"""
        if self.shortcut_manager:
            self.shortcut_manager.periodic_shortcut_check()
    
    def _ensure_file_state_manager(self):
        """确保FileStateManager实例是最新的"""
        if (self.current_dir is None or
            self.file_state_manager is None or
            self.file_state_manager.current_dir != self.current_dir):

            if self.current_dir is not None:
                self.file_state_manager = FileStateManager(
                    current_dir=self.current_dir,
                    categories=list(self.categories),
                    classified_images=self.classified_images,
                    removed_images=self.removed_images
                )

    def _sync_file_states(self):
        """同步文件状态与实际目录"""
        # 确保FileStateManager实例是最新的
        self._ensure_file_state_manager()

        if self.file_state_manager is None:
            self.logger.warning("FileStateManager未初始化，跳过文件状态同步")
            return {
                'changes_detected': False,
                'removed_files': [],
                'moved_files': [],
                'new_classifications': [],
                'invalid_classifications': []
            }

        try:
            # 使用FileStateManager进行状态同步
            sync_results = self.file_state_manager.sync_file_states()

            # 如果有变化，保存状态
            if sync_results['changes_detected']:
                self.save_state()

            return sync_results

        except Exception as e:
            self.logger.error(f"同步文件状态失败: {e}")
            return {
                'changes_detected': False,
                'removed_files': [],
                'moved_files': [],
                'new_classifications': [],
                'invalid_classifications': []
            }
    
    def _show_sync_results(self, sync_results):
        """显示同步结果"""
        try:
            messages = []
            
            if sync_results['removed_files']:
                count = len(sync_results['removed_files'])
                messages.append(f"🗑️ 发现 {count} 个文件被删除或移动")
            
            if sync_results['moved_files']:
                count = len(sync_results['moved_files'])
                messages.append(f"📦 发现 {count} 个文件位置变化")
            
            if sync_results['new_classifications']:
                count = len(sync_results['new_classifications'])
                messages.append(f"✅ 发现 {count} 个新的分类文件")
            
            if sync_results['invalid_classifications']:
                count = len(sync_results['invalid_classifications'])
                messages.append(f"❌ 清理了 {count} 个无效分类记录")
            
            if messages:
                toast_success(self,"目录同步完成，分类状态已更新")        
        except Exception as e:
            self.logger.error(f"显示同步结果失败: {e}")
    
    def _is_migration_needed(self):
        """检查是否需要迁移"""
        return len(self.classified_images) > 0 or len(self.removed_images) > 0

    def _show_migration_confirmation_dialog(self, target_mode):
        """显示迁移确认对话框"""

        dialog = QDialog(self)
        dialog.setWindowTitle("模式切换迁移确认")
        dialog.setModal(True)
        dialog.setFixedSize(500, 400)

        # 使用统一的样式系统
        dialog.setStyleSheet(DialogStyles.get_form_dialog_style())

        layout = QVBoxLayout(dialog)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        # 标题
        title_label = QLabel(f"⚠️ 检测到分类记录，切换到{'复制' if target_mode else '移动'}模式需要数据迁移")
        title_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #E67E22;")
        layout.addWidget(title_label)

        # 说明文本
        explanation = QTextEdit()
        explanation.setReadOnly(True)
        explanation.setMaximumHeight(200)

        current_mode = "复制" if self.is_copy_mode else "移动"
        target_mode_name = "复制" if target_mode else "移动"

        explanation_text = f"""当前模式：{current_mode}模式
目标模式：{target_mode_name}模式

检测到的数据：
• 已分类图片：{len(self.classified_images)} 张
• 已移出图片：{len(self.removed_images)} 张

迁移说明：
"""

        if target_mode:  # 切换到复制模式
            explanation_text += """• 从移动模式切换到复制模式
• 会将分类目录和移除目录中的文件复制回原目录
• 原始目录将恢复所有图片（包括已分类和已移出的）
• 分类记录会被保留，但文件会存在于多个位置"""
        else:  # 切换到移动模式
            explanation_text += """• 从复制模式切换到移动模式
• 会删除原始目录中已分类和已移出的图片
• 图片只保留在对应的分类目录中
• 这是一个不可逆的操作，请谨慎选择"""

        explanation.setPlainText(explanation_text)
        layout.addWidget(explanation)

        # 警告
        warning_label = QLabel("⚠️ 此操作会修改文件系统，建议在操作前备份重要数据")
        warning_label.setStyleSheet("color: #E74C3C; font-weight: bold;")
        layout.addWidget(warning_label)

        # 按钮
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_button = QPushButton("取消")
        cancel_button.setObjectName("cancelButton")
        cancel_button.clicked.connect(dialog.reject)
        button_layout.addWidget(cancel_button)

        confirm_button = QPushButton(f"确认迁移到{target_mode_name}模式")
        confirm_button.setObjectName("primaryButton")
        confirm_button.clicked.connect(dialog.accept)
        button_layout.addWidget(confirm_button)

        layout.addLayout(button_layout)

        return dialog.exec() == QDialog.DialogCode.Accepted

    def set_mode(self, is_copy):
        """设置操作模式"""
        # 如果要切换到移动模式，但当前是多分类模式，拒绝切换（最高优先级）
        if not is_copy and self.is_multi_category:
            toast_warning(self,"移动模式不支持多分类功能，请先切换为单分类模式")
            # 拒绝切换，保持原来的复制模式
            return

        # 检查是否需要迁移
        if self.is_copy_mode != is_copy and self._is_migration_needed():
            # 显示迁移确认对话框
            if not self._show_migration_confirmation_dialog(is_copy):
                # 用户取消迁移，保持原模式
                return

            # 用户确认迁移，执行迁移逻辑
            try:
                if is_copy:
                    # 从移动模式迁移到复制模式
                    self._migrate_move_to_copy()
                else:
                    # 从复制模式迁移到移动模式
                    self._migrate_copy_to_move()
            except Exception as e:
                self.logger.error(f"模式迁移失败: {e}")
                toast_error(self, f"模式迁移失败: {e}")
                return

        self.is_copy_mode = is_copy

        # 更新按钮图标和提示
        if is_copy:
            self.mode_button.setText('⧉')  # 重叠方块表示复制
            self.mode_button.setToolTip('复制模式 - 点击切换到移动模式')
            # 显示模式切换Toast
            toast_info(self,"已切换到复制模式")
        else:
            self.mode_button.setText('✂')  # 剪刀表示移动
            self.mode_button.setToolTip('移动模式 - 点击切换到复制模式')
            # 显示模式切换Toast
            toast_info(self,"已切换到移动模式")

        self.logger.info(f"操作模式已切换为: {'复制' if is_copy else '移动'}")

        # 立即同步保存状态到文件，确保模式状态与文件系统状态保持一致
        self._save_state_sync()

    def _set_mode_direct(self, is_copy):
        """直接设置操作模式，不触发迁移逻辑（用于状态恢复）"""
        self.is_copy_mode = is_copy

        # 更新按钮图标和提示
        if is_copy:
            self.mode_button.setText('⧉')  # 重叠方块表示复制
            self.mode_button.setToolTip('复制模式 - 点击切换到移动模式')
        else:
            self.mode_button.setText('✂')  # 剪刀表示移动
            self.mode_button.setToolTip('移动模式 - 点击切换到复制模式')

        self.logger.info(f"操作模式已恢复为: {'复制' if is_copy else '移动'}")

    def _migrate_copy_to_move(self):
        """从复制模式迁移到移动模式"""
        self.logger.info("开始从复制模式迁移到移动模式")

        # 收集需要从原目录删除的文件
        files_to_delete = []
        for file_path in self.classified_images.keys():
            if Path(file_path).exists():
                files_to_delete.append(file_path)
        for file_path in self.removed_images:
            if Path(file_path).exists():
                files_to_delete.append(file_path)

        if not files_to_delete:
            self.logger.info("没有需要删除的文件")
            toast_info(self, "没有需要迁移的文件")
            return

        # 显示进度对话框
        progress_dialog = ProgressDialog("模式迁移 - 复制到移动", self)
        progress_dialog.update_main_text(f"正在迁移到移动模式，将删除原目录中的 {len(files_to_delete)} 个文件...")
        progress_dialog.show()
        QApplication.processEvents()

        # 删除原目录中的文件（带错误处理和回滚）
        deleted_files = []  # 记录已删除的文件，用于回滚
        deleted_count = 0
        total_files = len(files_to_delete)

        try:
            for i, file_path in enumerate(files_to_delete):
                # 检查是否被取消
                if progress_dialog.is_cancelled():
                    progress_dialog.force_close()
                    self.logger.info("用户取消了迁移操作")
                    toast_warning(self, "迁移操作已取消")
                    return

                try:
                    # 更新进度
                    progress_dialog.update_progress(i + 1, total_files)
                    progress_dialog.update_detail_text(f"正在删除: {Path(file_path).name}")
                    QApplication.processEvents()

                    # 在删除前验证对应分类文件存在
                    file_path_obj = Path(file_path)
                    if str(file_path) in self.classified_images:
                        category = self.classified_images[str(file_path)]
                        category_name = category[0] if isinstance(category, list) and category else category
                        if category_name:
                            parent_dir = self.current_dir.parent
                            category_dir = parent_dir / normalize_folder_name(category_name)
                            category_file = category_dir / file_path_obj.name
                            if not category_file.exists():
                                raise FileOperationError(f"分类目录中找不到对应文件: {category_file}")

                    # 备份文件信息用于可能的回滚
                    file_backup_info = {
                        'path': file_path,
                        'stat': file_path_obj.stat() if file_path_obj.exists() else None
                    }

                    # 删除原文件
                    file_path_obj.unlink()
                    deleted_files.append(file_backup_info)
                    deleted_count += 1
                    self.logger.debug(f"删除原文件: {file_path}")

                except Exception as e:
                    self.logger.error(f"删除文件失败 {file_path}: {e}")

                    # 尝试回滚已删除的文件
                    self._rollback_copy_to_move_migration(deleted_files)

                    progress_dialog.force_close()
                    raise FileOperationError(f"删除文件失败，已尝试回滚: {e}")

            # 完成
            progress_dialog.update_main_text("迁移完成")
            progress_dialog.update_detail_text(f"已删除 {deleted_count} 个文件")
            progress_dialog.update_progress(total_files, total_files)
            QApplication.processEvents()

            QTimer.singleShot(1000, progress_dialog.force_close)  # 1秒后关闭

            self.logger.info(f"复制到移动模式迁移完成，删除了 {deleted_count} 个文件")
            toast_success(self, f"迁移完成，已删除原目录中的 {deleted_count} 个文件")

        except Exception as e:
            self.logger.error(f"迁移过程中发生严重错误: {e}")
            progress_dialog.force_close()
            toast_error(self, f"迁移失败: {e}")
            raise

    def _rollback_copy_to_move_migration(self, deleted_files):
        """回滚复制到移动模式的迁移操作"""
        self.logger.warning("开始回滚复制到移动模式迁移操作")

        rollback_count = 0
        for file_info in deleted_files:
            try:
                file_path = file_info['path']

                # 从分类目录或移除目录找回文件
                source_file = None

                # 先尝试从分类目录找回
                if str(file_path) in self.classified_images:
                    category = self.classified_images[str(file_path)]
                    category_name = category[0] if isinstance(category, list) and category else category
                    if category_name:
                        parent_dir = self.current_dir.parent
                        category_dir = parent_dir / normalize_folder_name(category_name)
                        category_file = category_dir / Path(file_path).name
                        if category_file.exists():
                            source_file = category_file

                # 再尝试从移除目录找回
                if not source_file and str(file_path) in self.removed_images:
                    parent_dir = self.current_dir.parent
                    remove_dir = parent_dir / "remove"
                    remove_file = remove_dir / Path(file_path).name
                    if remove_file.exists():
                        source_file = remove_file

                # 恢复文件
                if source_file:
                    shutil.copy2(str(source_file), str(file_path))
                    rollback_count += 1
                    self.logger.debug(f"回滚恢复文件: {source_file} -> {file_path}")
                else:
                    self.logger.warning(f"无法找到回滚源文件: {file_path}")

            except Exception as e:
                self.logger.error(f"回滚文件失败 {file_info['path']}: {e}")

        self.logger.info(f"回滚完成，恢复了 {rollback_count} 个文件")
        if rollback_count > 0:
            toast_info(self, f"已回滚恢复 {rollback_count} 个文件")

    def _migrate_move_to_copy(self):
        """从移动模式迁移到复制模式"""
        self.logger.info("开始从移动模式迁移到复制模式")

        # 收集需要复制的文件
        files_to_copy = []

        # 收集分类文件
        parent_dir = self.current_dir.parent
        for file_path, category in self.classified_images.items():
            category_name = category[0] if isinstance(category, list) and category else category
            if category_name:
                category_dir = parent_dir / normalize_folder_name(category_name)
                category_file = category_dir / Path(file_path).name
                if category_file.exists() and not Path(file_path).exists():
                    files_to_copy.append((category_file, Path(file_path), 'classified'))

        # 收集移除文件
        remove_dir = parent_dir / "remove"
        if remove_dir.exists():
            for file_path in self.removed_images:
                remove_file = remove_dir / Path(file_path).name
                if remove_file.exists() and not Path(file_path).exists():
                    files_to_copy.append((remove_file, Path(file_path), 'removed'))

        if not files_to_copy:
            self.logger.info("没有需要复制的文件")
            toast_info(self, "没有需要迁移的文件")
            return

        # 显示进度对话框
        progress_dialog = ProgressDialog("模式迁移 - 移动到复制", self)
        progress_dialog.update_main_text(f"正在迁移到复制模式，将复制 {len(files_to_copy)} 个文件回原目录...")
        progress_dialog.show()
        QApplication.processEvents()

        # 复制文件（带错误处理和回滚）
        copied_files = []  # 记录已复制的文件，用于回滚
        copied_count = 0
        total_files = len(files_to_copy)

        try:
            for i, (source_file, target_file, file_type) in enumerate(files_to_copy):
                # 检查是否被取消
                if progress_dialog.is_cancelled():
                    progress_dialog.force_close()
                    self.logger.info("用户取消了迁移操作")
                    toast_warning(self, "迁移操作已取消")
                    return

                try:
                    # 更新进度
                    progress_dialog.update_progress(i + 1, total_files)
                    file_type_name = '分类' if file_type == 'classified' else '移除'
                    progress_dialog.update_detail_text(f"正在复制{file_type_name}文件: {target_file.name}")
                    QApplication.processEvents()

                    # 验证源文件存在
                    if not source_file.exists():
                        raise FileOperationError(f"源文件不存在: {source_file}")

                    # 检查目标文件是否已存在（避免覆盖）
                    if target_file.exists():
                        self.logger.warning(f"目标文件已存在，跳过: {target_file}")
                        continue

                    # 确保目标目录存在
                    target_file.parent.mkdir(parents=True, exist_ok=True)

                    # 验证磁盘空间
                    source_size = source_file.stat().st_size
                    free_space = shutil.disk_usage(target_file.parent).free
                    if source_size > free_space:
                        raise FileOperationError(f"磁盘空间不足，需要 {source_size} 字节，可用 {free_space} 字节")

                    # 复制文件
                    shutil.copy2(str(source_file), str(target_file))

                    # 验证复制是否成功
                    if not target_file.exists():
                        raise FileOperationError(f"文件复制后验证失败: {target_file}")

                    # 验证文件大小
                    if target_file.stat().st_size != source_file.stat().st_size:
                        raise FileOperationError(f"文件大小不匹配: {source_file} vs {target_file}")

                    copied_files.append(target_file)
                    copied_count += 1
                    self.logger.debug(f"复制文件: {source_file} -> {target_file}")

                except Exception as e:
                    self.logger.error(f"复制文件失败 {source_file} -> {target_file}: {e}")

                    # 尝试回滚已复制的文件
                    self._rollback_move_to_copy_migration(copied_files)

                    progress_dialog.force_close()
                    raise FileOperationError(f"复制文件失败，已尝试回滚: {e}")

            # 完成
            progress_dialog.update_main_text("迁移完成")
            progress_dialog.update_detail_text(f"已复制 {copied_count} 个文件回原目录")
            progress_dialog.update_progress(total_files, total_files)
            QApplication.processEvents()

            QTimer.singleShot(1000, progress_dialog.force_close)  # 1秒后关闭

            self.logger.info(f"移动到复制模式迁移完成，复制了 {copied_count} 个文件")
            toast_success(self, f"迁移完成，已复制 {copied_count} 个文件回原目录")

        except Exception as e:
            self.logger.error(f"迁移过程中发生严重错误: {e}")
            progress_dialog.force_close()
            toast_error(self, f"迁移失败: {e}")
            raise

    def _rollback_move_to_copy_migration(self, copied_files):
        """回滚移动到复制模式的迁移操作"""
        self.logger.warning("开始回滚移动到复制模式迁移操作")

        rollback_count = 0
        for target_file in copied_files:
            try:
                if target_file.exists():
                    target_file.unlink()
                    rollback_count += 1
                    self.logger.debug(f"回滚删除文件: {target_file}")
                else:
                    self.logger.warning(f"回滚时文件不存在: {target_file}")

            except Exception as e:
                self.logger.error(f"回滚删除文件失败 {target_file}: {e}")

        self.logger.info(f"回滚完成，删除了 {rollback_count} 个文件")
        if rollback_count > 0:
            toast_info(self, f"已回滚删除 {rollback_count} 个文件")

    def create_category_mode_button(self, toolbar):
        """创建图标化的分类模式切换按钮 - 单分类/多分类"""
        # 使用统一样式创建按钮
        self.category_mode_button = self.create_toolbar_button('→', 'category_mode_button',
                                                              '单分类模式 - 点击切换到多分类模式',
                                                              self.toggle_category_mode)

        # 添加到工具栏
        toolbar.addWidget(self.category_mode_button)
    
    def toggle_category_mode(self):
        """切换单分类/多分类模式"""
        # 移动模式不支持多分类
        if not self.is_copy_mode and not self.is_multi_category:
            toast_warning(self,"移动模式不支持多分类功能，请先切换到复制模式")
            return
        
        self.is_multi_category = not self.is_multi_category

        # 使用统一的按钮状态更新方法
        self.update_category_mode_button()

        # 显示Toast通知
        if self.is_multi_category:
            toast_info(self, "已切换到多分类模式")
        else:
            toast_info(self, "已切换到单分类模式")

        # 保存分类模式状态
        self.save_state()

        self.logger.info(f"分类模式已切换为: {'多分类' if self.is_multi_category else '单分类'}")

    def change_category_sort_mode(self, new_mode):
        """切换类别排序模式

        Args:
            new_mode: "name", "shortcut" 或 "count"
        """
        try:
            if new_mode not in ["name", "shortcut", "count"]:
                self.logger.error(f"无效的排序模式: {new_mode}")
                return

            # 更新配置
            self.config.category_sort_mode = new_mode
            self.config.save_config()

            # 重新排序类别（count模式需要传入分类数量统计）
            category_counts = self._get_category_counts() if new_mode == "count" else None
            self.ordered_categories = self.config.get_sorted_categories(
                self.categories, category_counts=category_counts
            )

            # 更新UI
            self.update_category_buttons()

            # 更新方向按钮的tooltip（因为排序模式变了）
            self._update_direction_button_tooltip()

            # 显示提示（使用详细描述）
            current_text, _ = self._get_sort_tooltip_texts()
            toast_success(self, f"已切换到：{current_text}")
            self.logger.info(f"类别排序模式已切换为: {new_mode}")

        except Exception as e:
            self.logger.error(f"切换排序模式失败: {e}")
            toast_error(self, f"切换排序模式失败: {str(e)}")

    def toggle_sort_direction(self):
        """切换排序方向（升序/降序）"""
        try:
            # 切换方向
            self.config.sort_ascending = not self.config.sort_ascending
            self.config.save_config()

            # 更新按钮图标和tooltip
            self.sort_direction_button.setText('↑' if self.config.sort_ascending else '↓')
            self._update_direction_button_tooltip()

            # 重新排序类别
            category_counts = self._get_category_counts() if self.config.category_sort_mode == "count" else None
            self.ordered_categories = self.config.get_sorted_categories(
                self.categories, category_counts=category_counts
            )

            # 更新UI
            self.update_category_buttons()

            # 显示提示（使用详细描述）
            _, action_text = self._get_sort_tooltip_texts()
            toast_success(self, f"已切换为：{action_text}")
            self.logger.info(f"排序方向已切换")

        except Exception as e:
            self.logger.error(f"切换排序方向失败: {e}")
            toast_error(self, f"切换排序方向失败: {str(e)}")

    def _get_sort_tooltip_texts(self):
        """获取当前排序状态的tooltip文案

        Returns:
            tuple: (当前状态描述, 切换后状态描述)
        """
        mode = self.config.category_sort_mode
        is_asc = self.config.sort_ascending

        # 状态描述映射表 (mode, is_ascending) -> (当前状态, 切换后状态)
        status_map = {
            ('name', True):     ("按名称 (A → Z)", "名称倒序 (Z → A)"),
            ('name', False):    ("按名称 (Z → A)", "名称顺序 (A → Z)"),
            ('shortcut', True): ("按快捷键 (1 → 9 → A)", "快捷键倒序 (Z → 1)"),
            ('shortcut', False):("按快捷键 (Z → A → 1)", "快捷键顺序 (1 → Z)"),
            ('count', True):    ("按数量 (少 → 多)", "数量从多到少"),
            ('count', False):   ("按数量 (多 → 少)", "数量从少到多"),
        }

        return status_map.get((mode, is_asc), ("未知状态", "切换方向"))

    def _update_direction_button_tooltip(self):
        """根据当前排序模式和方向，动态更新方向按钮的tooltip"""
        current_text, action_text = self._get_sort_tooltip_texts()
        tooltip = f"当前：{current_text}\n点击切换为：{action_text}"
        self.sort_direction_button.setToolTip(tooltip)

    def _sync_sort_button_state(self):
        """同步排序方向按钮的UI状态（从配置加载后调用）"""
        if hasattr(self, 'sort_direction_button'):
            # 更新按钮图标
            self.sort_direction_button.setText('↑' if self.config.sort_ascending else '↓')
            # 更新tooltip
            self._update_direction_button_tooltip()

    def _get_category_counts(self):
        """获取每个类别的分类数量统计

        Returns:
            dict: {category_name: count} 每个类别对应的图片数量
        """
        counts = {}
        for img_path, category in self.classified_images.items():
            if isinstance(category, list):
                # 多分类模式：一张图可能属于多个类别
                for cat in category:
                    counts[cat] = counts.get(cat, 0) + 1
            else:
                # 单分类模式
                counts[category] = counts.get(category, 0) + 1
        return counts

    def fit_to_window(self):
        """适应窗口大小"""
        if hasattr(self, 'image_label'):
            self.image_label.fit_to_window()
    
    def add_category(self):
        """添加新类别"""
        if not self.current_dir:
            toast_warning(self,'请先选择图片目录')
            return

        # 记录添加前的类别数量
        original_count = len(self.categories)

        dialog = AddCategoriesDialog(self.categories, self)
        if dialog.exec():
            # 检查是否有新类别添加
            new_count = len(self.categories)
            added_count = new_count - original_count
            skipped_categories = getattr(dialog, 'skipped_categories', [])

            # 构建合并的 toast 消息
            if added_count > 0 and skipped_categories:
                # 有添加也有跳过
                skipped_text = ', '.join(skipped_categories[:3])
                if len(skipped_categories) > 3:
                    skipped_text += f' 等{len(skipped_categories)}个'
                toast_warning(self, f"已添加 {added_count} 个类别，{skipped_text} 已存在或已忽略")
            elif added_count > 0:
                # 只有添加
                if added_count == 1:
                    toast_success(self, "已添加 1 个新类别")
                else:
                    toast_success(self, f"已添加 {added_count} 个新类别")
            elif skipped_categories:
                # 只有跳过
                skipped_text = ', '.join(skipped_categories[:3])
                if len(skipped_categories) > 3:
                    skipped_text += f' 等{len(skipped_categories)}个'
                toast_warning(self, f"类别 {skipped_text} 已存在或已忽略，未添加新类别")
    
    # ===== 图像加载器回调方法 =====
    
    def on_image_loaded(self, image_path, image_data):
        """图像加载完成回调 - 只显示当前选中的图片"""
        try:
            # 关键修复：只显示最后一次请求的图片，其他都是预加载缓存
            # 使用保存的请求路径而不是当前索引，避免异步加载时索引变化导致判断错误
            normalized_loaded = str(Path(image_path).resolve())

            # 检查是否有记录的当前请求图片
            if hasattr(self, '_current_requested_image'):
                # 比较路径
                if self._current_requested_image != normalized_loaded:
                    # 不是当前图片，只是预加载缓存，不显示UI
                    self.logger.debug(f"预加载完成(不显示): {Path(image_path).name}")
                    return
            else:
                # 没有记录的请求路径（比如程序刚启动），也显示
                pass
            
            # 只有当前图片才进行UI显示
            # 转换图像数据为QPixmap
            if isinstance(image_data, QPixmap):
                # 这是QPixmap
                pixmap = image_data
            else:
                # 这可能是numpy数组或PIL图像，需要转换
                pixmap = self.convert_to_pixmap(image_data)
            
            # 显示图像
            if pixmap is not None and not pixmap.isNull():
                self.display_pixmap(pixmap, image_path)
                self.logger.info(f"当前图片显示完成: {Path(image_path).name}")
            else:
                self.logger.warning(f"无法显示图像: {image_path}")
                
        except Exception as e:
            self.logger.error(f"显示图像时出错: {e}")
            self.logger.error(traceback.format_exc())
    
    def on_thumbnail_loaded(self, image_path, thumbnail_data):
        """缩略图加载完成回调"""
        try:
            # 更新图片列表中的缩略图
            self.update_image_list_thumbnail(image_path, thumbnail_data)
        except Exception as e:
            self.logger.error(f"更新缩略图时出错: {e}")
    
    def on_loading_progress(self, message):
        """加载进度回调"""
        self.statusBar.showMessage(message)
    
    def convert_to_pixmap(self, image_data):
        """将图像数据转换为QPixmap"""
        try:
            if isinstance(image_data, np.ndarray):
                # numpy数组图像数据
                height, width, channel = image_data.shape
                bytes_per_line = 3 * width

                # 确保数组是C连续的，并复制数据避免生命周期问题
                # 这对于从磁盘缓存加载的图片非常重要
                if not image_data.flags['C_CONTIGUOUS']:
                    image_data = np.ascontiguousarray(image_data)

                # 创建QImage并立即复制数据，避免numpy数组被释放后QImage引用无效内存
                q_image = QImage(image_data.data, width, height, bytes_per_line, QImage.Format.Format_RGB888).copy()
                return QPixmap.fromImage(q_image)
                
            elif hasattr(image_data, 'mode'):
                # PIL图像
                if image_data.mode == 'RGB':
                    rgb_array = np.array(image_data)
                    height, width, channel = rgb_array.shape
                    bytes_per_line = 3 * width

                    # 确保数组是C连续的
                    if not rgb_array.flags['C_CONTIGUOUS']:
                        rgb_array = np.ascontiguousarray(rgb_array)

                    # 创建QImage并复制数据
                    q_image = QImage(rgb_array.data, width, height, bytes_per_line, QImage.Format.Format_RGB888).copy()
                    return QPixmap.fromImage(q_image)
                else:
                    # 转换为RGB
                    rgb_image = image_data.convert('RGB')
                    return self.convert_to_pixmap(rgb_image)
            
            return None
            
        except Exception as e:
            self.logger.error(f"转换图像格式时出错: {e}")
            return None
    
    def display_pixmap(self, pixmap, image_path):
        """显示QPixmap - 统一UI显示"""
        try:
            # 直接使用EnhancedImageLabel的set_image方法
            self.image_label.set_image(pixmap)
            
            # 使用统一的窗口标题更新方法
            self.update_window_title(image_path)
            
            # 更新状态栏显示当前图片名称
            filename = Path(image_path).name
            self.statusBar.showMessage(f"📷 {filename}")
            
            # 记录性能信息
            self.log_performance_info(
                "显示图片_完成",
                文件=filename,
                索引=f"{self.current_index + 1}/{len(self.image_files)}"
            )
            
        except Exception as e:
            self.logger.error(f"显示图像时出错: {e}")
    
    def update_image_list_thumbnail(self, image_path, thumbnail_data):
        """更新图片列表中的缩略图"""
        try:
            # Phase 1.1 Migration: 使用 Model API 高效更新缩略图 (O(1))
            # 不再遍历 ListWidget，直接通过 Model 的 Path 映射更新

            if not hasattr(self, 'image_list_model'):
                return

            icon = None

            # 1. 统一转换为 QIcon
            if hasattr(thumbnail_data, 'copy'):
                # 已经是 QPixmap
                icon = QIcon(thumbnail_data)
            else:
                # 可能是 numpy 数组，需要转换
                thumbnail_pixmap = self.convert_to_pixmap(thumbnail_data)
                if thumbnail_pixmap:
                    icon = QIcon(thumbnail_pixmap)

            # 2. 更新 Model (自动处理缓存和 View 刷新)
            if icon:
                self.image_list_model.set_thumbnail(str(image_path), icon)

        except Exception as e:
            self.logger.error(f"更新缩略图时出错: {e}")

    def show_help_dialog(self):
        """显示帮助对话框"""
        dialog = TabbedHelpDialog(self.version, self, config=getattr(self, 'config', None))
        # 确保对话框应用当前主题
        if hasattr(dialog, '_apply_theme'):
            dialog._apply_theme()
        dialog.exec()

    def show_settings_dialog(self):
        """显示设置对话框"""
        try:
            dialog = SettingsDialog(self)
            dialog.exec()
            # 注意：不再自动隐藏红点
            # 红点的显示/隐藏由更新检查逻辑控制
            # - 有待安装更新时：红点保持显示
            # - 用户选择立即安装：隐藏红点并退出
            # - 确认是最新版本：隐藏红点
        except Exception as e:
            self.logger.error(f"打开设置对话框失败: {e}")
            toast_error(self, f"打开设置失败: {str(e)}")

    def _check_and_show_tutorial(self):
        """检查是否需要显示教程"""
        try:
            if self.tutorial_manager and self.tutorial_manager.should_show_tutorial():
                self.logger.info("首次运行，显示教程引导")
                self.tutorial_manager.start_tutorial()
                # 教程显示时，不检查恢复目录（避免冲突）
            else:
                # 教程已完成或跳过，检查是否需要恢复上次目录
                QTimer.singleShot(500, self._check_and_restore_last_directory)
        except Exception as e:
            self.logger.error(f"检查教程显示状态失败: {e}")

    def _check_and_restore_last_directory(self):
        """检查并询问用户是否恢复上次打开的目录"""
        try:
            # 如果已经打开了目录，则不提示
            if self.current_dir is not None:
                return

            # 获取上次打开的目录
            app_config = get_app_config()
            last_dir = app_config.last_opened_directory

            # 如果没有记录或目录不存在，则不提示
            if not last_dir or not Path(last_dir).exists():
                return

            # 检测路径类型
            is_network = is_network_path(last_dir)
            path_type_icon = "🌐" if is_network else "💾"
            path_type_text = "网络路径" if is_network else "本地路径"

            # 提取盘符信息
            last_dir_path = Path(last_dir)
            drive_info = f" ({last_dir_path.drive})" if last_dir_path.drive else ""

            # 创建询问对话框
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("恢复上次任务")
            msg_box.setText(f"检测到上次打开的工作目录")
            msg_box.setInformativeText(
                f"路径：{last_dir}\n"
                f"{path_type_icon} {path_type_text}{drive_info}\n\n"
                f"是否继续上次的任务？"
            )

            # 应用主题样式
            c = default_theme.colors
            msg_box.setStyleSheet(f"""
                QMessageBox {{
                    background-color: {c.BACKGROUND_PRIMARY};
                    color: {c.TEXT_PRIMARY};
                }}
                QMessageBox QLabel {{
                    color: {c.TEXT_PRIMARY};
                    font-size: 13px;
                }}
                QPushButton {{
                    background-color: {c.PRIMARY};
                    color: white;
                    border: none;
                    padding: 6px 16px;
                    border-radius: 4px;
                    font-size: 13px;
                    min-width: 70px;
                }}
                QPushButton:hover {{
                    background-color: {c.PRIMARY_DARK};
                }}
                QPushButton:pressed {{
                    background-color: {c.PRIMARY_DARK};
                }}
            """)

            # 添加按钮
            yes_btn = msg_box.addButton("继续上次任务", QMessageBox.ButtonRole.YesRole)
            no_btn = msg_box.addButton("重新选择", QMessageBox.ButtonRole.NoRole)
            msg_box.setDefaultButton(yes_btn)

            # 显示对话框并获取结果
            msg_box.exec()
            clicked_button = msg_box.clickedButton()

            if clicked_button == yes_btn:
                self.logger.info(f"用户选择恢复上次目录: {last_dir}")
                # 直接设置目录并打开
                self._open_directory_with_path(last_dir)
            else:
                self.logger.info("用户选择重新选择目录")

        except Exception as e:
            self.logger.error(f"检查恢复目录失败: {e}")

    def _open_directory_with_path(self, dir_path: str):
        """使用指定路径打开目录（内部方法，用于恢复上次目录）"""
        try:
            self.current_dir = Path(dir_path)

            # 检查是否为网络路径
            path_str = str(self.current_dir)
            is_network_path = path_str.startswith('\\\\')

            # Task 1.1修复：通知图像加载器当前工作路径类型
            try:
                self.image_loader.set_working_path(self.current_dir)
            except Exception as e:
                self.logger.warning(f"设置图像加载器工作路径失败: {e}")

            if is_network_path:
                # 网络路径提醒
                toast_info(self, '🚀 SMB/NAS路径已启用专项优化')
                self.logger.info(f"恢复网络路径: {self.current_dir}")
            else:
                self.logger.info(f"恢复本地路径: {self.current_dir}")
                # 显示本地目录打开成功通知
                toast_success(self, f"已恢复目录：{self.current_dir.name}")

            # 设置配置文件路径为图片目录的父目录
            self.config.set_base_dir(str(self.current_dir.parent))

            # 先启动图片扫描，让UI立即响应
            self.load_images()

            # 延迟类别加载和同步操作
            QTimer.singleShot(100, self._delayed_load_categories)

        except Exception as e:
            self.logger.error(f"打开指定目录失败: {e}")
            toast_error(self, f"打开目录失败: {str(e)}")

    def start_tutorial(self):
        """开始或重新开始教程（提供给菜单调用）"""
        try:
            if self.tutorial_manager:
                self.tutorial_manager.reset_tutorial()
                toast_info(self, "教程已重新开始")
            else:
                toast_error(self, "教程系统不可用")
        except Exception as e:
            self.logger.error(f"启动教程失败: {e}")
            toast_error(self, f"启动教程失败: {str(e)}")

    def update_theme_button_state(self):
        """更新主题按钮状态（根据主题模式）"""
        if not hasattr(self, 'theme_button'):
            return

        try:
            app_config = get_app_config()
            theme_mode = app_config.theme_mode

            # 检查是否因为自动模式或系统模式需要禁用
            disabled_due_to_mode = theme_mode in ("auto", "system")

            if disabled_due_to_mode:
                # 因模式原因禁用
                self.theme_button.setEnabled(False)
                mode_name = "自动切换" if theme_mode == "auto" else "跟随系统"
                self.theme_button.setToolTip(f"已启用{mode_name}，点击查看提示")
            else:
                # 启用按钮
                self.theme_button.setEnabled(True)
                current_theme = default_theme.get_current_theme()
                theme_tooltip = '切换到暗色主题' if current_theme == "light" else '切换到亮色主题'
                self.theme_button.setToolTip(theme_tooltip)

        except Exception as e:
            self.logger.warning(f"更新主题按钮状态失败: {e}")

    def toggle_theme(self):
        """切换主题"""
        try:
            # 检查是否启用了自动切换
            app_config = get_app_config()

            # 重新加载配置确保使用最新值（防止缓存不一致）
            app_config.reload_config()

            # 如果启用了自动模式，禁止手动切换
            if app_config.theme_mode == "auto":
                toast_warning(self, "已启用自动切换，请先在设置中关闭")
                return

            # 如果启用了系统模式，也禁止手动切换
            if app_config.theme_mode == "system":
                toast_warning(self, "已启用跟随系统，请先在设置中关闭")
                return

            # 获取当前主题并切换
            current_theme = default_theme.get_current_theme()
            new_theme = "dark" if current_theme == "light" else "light"
            default_theme.set_theme(new_theme)

            # 保存到应用配置（app_config.json）
            app_config.theme = new_theme
            self.logger.info(f"主题已切换到: {new_theme}")

            # 应用主题到主窗口和所有组件
            self.apply_theme()

            # 更新按钮图标和提示
            if hasattr(self, 'theme_button'):
                theme_icon = '☾' if new_theme == "light" else '☼'  # ☾ 月亮(暗色) ☼ 太阳(亮色)
                theme_tooltip = '切换到暗色主题' if new_theme == "light" else '切换到亮色主题'
                self.theme_button.setText(theme_icon)
                self.theme_button.setToolTip(theme_tooltip)

            toast_success(self, f'已切换到{"暗色" if new_theme == "dark" else "亮色"}主题')
        except Exception as e:
            self.logger.error(f"切换主题失败: {e}", exc_info=True)
            toast_error(self, f'主题切换失败: {str(e)}')

    def apply_theme(self):
        """应用主题到主窗口和所有组件"""
        try:
            c = default_theme.colors

            # 应用主窗口样式
            self.setStyleSheet(MainWindowStyles.get_main_window_style())

            # 应用工具栏样式
            if hasattr(self, 'findChildren'):
                toolbars = self.findChildren(QToolBar)
                for toolbar in toolbars:
                    toolbar.setStyleSheet(ToolbarStyles.get_main_toolbar_style())

            # 更新左侧面板样式
            left_panel = self.findChild(QWidget, "left_panel")
            if left_panel:
                left_panel.setStyleSheet(f"""
                    QWidget#left_panel {{
                        background-color: {c.BACKGROUND_PRIMARY};
                        border: 1px solid {c.BORDER_MEDIUM};
                        border-radius: 6px;
                    }}
                """)

            # 更新左侧标题容器
            title_container = self.findChild(QWidget, "title_container")
            if title_container:
                title_container.setStyleSheet(f"""
                    QWidget#title_container {{
                        border-bottom: 1px solid {c.BORDER_MEDIUM};
                        max-height: 28px;
                        min-height: 28px;
                    }}
                """)

            # 更新图片预览标题标签
            if hasattr(self, 'findChildren'):
                for label in self.findChildren(QLabel):
                    if label.text() == "🖼️ 图片预览":
                        label.setStyleSheet(f"""
                            QLabel {{
                                font-size: 14px;
                                font-weight: bold;
                                color: {c.TEXT_SECONDARY};
                                border: none;
                            }}
                        """)

            # 更新右侧面板样式
            right_panel = self.findChild(QWidget, "right_panel")
            if right_panel:
                right_panel.setStyleSheet(f"""
                    QWidget#right_panel {{
                        background-color: {c.BACKGROUND_PRIMARY};
                        border: 1px solid {c.BORDER_MEDIUM};
                        border-radius: 6px;
                    }}
                """)

            # 更新图片列表区域
            # Phase 1.1: QListWidget → QListView
            if hasattr(self, 'image_list'):
                self.image_list.setStyleSheet(f"""
                    QListView {{
                        border: 1px solid {c.BORDER_MEDIUM};
                        border-radius: 4px;
                        background-color: {c.BACKGROUND_SECONDARY};
                        padding: 2px;
                    }}
                    QListView::item {{
                        border: 1px solid transparent;
                        border-radius: 3px;
                        padding: 4px 6px;
                        margin: 1px;
                        color: {c.TEXT_PRIMARY};
                    }}
                    QListView::item:hover {{
                        background-color: {c.BACKGROUND_HOVER};
                        border-color: {c.PRIMARY};
                    }}
                    QListView::item:selected {{
                        background-color: {c.PRIMARY};
                        color: white;
                        border-color: {c.PRIMARY_DARK};
                    }}
                    QScrollBar:vertical {{
                        border: 1px solid {c.BORDER_LIGHT};
                        background: {c.BACKGROUND_SECONDARY};
                        width: 14px;
                        border-radius: 4px;
                        margin: 0px;
                    }}
                    QScrollBar::handle:vertical {{
                        background: {c.PRIMARY};
                        border-radius: 3px;
                        min-height: 30px;
                        margin: 2px 2px 2px 2px;
                    }}
                    QScrollBar::handle:vertical:hover {{
                        background: {c.PRIMARY_DARK};
                        margin: 1px 1px 1px 1px;
                    }}
                    QScrollBar::handle:vertical:pressed {{
                        background: {c.PRIMARY_DARK};
                        margin: 0px 0px 0px 0px;
                    }}
                    QScrollBar:horizontal {{
                        border: 1px solid {c.BORDER_LIGHT};
                        background: {c.BACKGROUND_SECONDARY};
                        height: 10px;
                        border-radius: 3px;
                    }}
                    QScrollBar::handle:horizontal {{
                        background: {c.PRIMARY};
                        border-radius: 3px;
                        min-width: 15px;
                    }}
                    QScrollBar::handle:horizontal:hover {{
                        background: {c.PRIMARY_DARK};
                    }}
                    QScrollBar::handle:horizontal:pressed {{
                        background: {c.PRIMARY_DARK};
                    }}
                    QScrollBar::add-line:vertical,
                    QScrollBar::sub-line:vertical,
                    QScrollBar::add-line:horizontal,
                    QScrollBar::sub-line:horizontal {{
                        border: none;
                        background: none;
                    }}
                """)

            # 更新图片列表标题容器
            list_title_container = self.findChild(QWidget, "list_title_container")
            if list_title_container:
                list_title_container.setStyleSheet(f"""
                    QWidget#list_title_container {{
                        border-bottom: 2px solid {c.PRIMARY};
                        margin-bottom: 4px;
                        max-height: 28px;
                        min-height: 28px;
                    }}
                """)

            # 更新搜索组件主题
            if hasattr(self, 'image_search_widget'):
                self.image_search_widget.apply_theme()

            # 更新类别标题容器
            category_title_container = self.findChild(QWidget, "category_title_container")
            if category_title_container:
                category_title_container.setStyleSheet(f"""
                    QWidget#category_title_container {{
                        border-bottom: 2px solid {c.WARNING};
                        margin-bottom: 4px;
                        max-height: 28px;
                        min-height: 28px;
                    }}
                """)

            # 更新图片预览滚动区域
            if hasattr(self, 'image_scroll_area'):
                self.image_scroll_area.setStyleSheet(f"""
                    QScrollArea {{
                        border: 1px solid {c.BORDER_MEDIUM};
                        border-radius: 4px;
                        background-color: {c.BACKGROUND_SECONDARY};
                    }}
                """)

            # 更新类别按钮滚动区域
            if hasattr(self, 'category_scroll'):
                self.category_scroll.setStyleSheet(f"""
                    QScrollArea {{
                        border: 1px solid {c.WARNING};
                        border-radius: 4px;
                        background-color: {c.BACKGROUND_SECONDARY};
                    }}
                    QScrollBar:vertical {{
                        border: 1px solid {c.WARNING};
                        background: {c.BACKGROUND_SECONDARY};
                        width: 10px;
                        border-radius: 3px;
                    }}
                    QScrollBar::handle:vertical {{
                        background: {c.WARNING};
                        border-radius: 3px;
                        min-height: 15px;
                    }}
                    QScrollBar::handle:vertical:hover {{
                        background: {c.WARNING_DARK};
                    }}
                    QScrollBar::handle:vertical:pressed {{
                        background: {c.WARNING_DARK};
                    }}
                    QScrollBar:horizontal {{
                        border: 1px solid {c.WARNING};
                        background: {c.BACKGROUND_SECONDARY};
                        height: 10px;
                        border-radius: 3px;
                    }}
                    QScrollBar::handle:horizontal {{
                        background: {c.WARNING};
                        border-radius: 3px;
                        min-width: 15px;
                    }}
                    QScrollBar::handle:horizontal:hover {{
                        background: {c.WARNING_DARK};
                    }}
                    QScrollBar::handle:horizontal:pressed {{
                        background: {c.WARNING_DARK};
                    }}
                    QScrollBar::add-line:vertical,
                    QScrollBar::sub-line:vertical,
                    QScrollBar::add-line:horizontal,
                    QScrollBar::sub-line:horizontal {{
                        border: none;
                        background: none;
                    }}
                """)

            # 更新类别按钮容器
            if hasattr(self, 'category_widget'):
                self.category_widget.setStyleSheet(f"""
                    QWidget {{
                        background-color: {c.BACKGROUND_SECONDARY};
                    }}
                """)

            # 更新所有类别按钮的样式
            if hasattr(self, 'category_buttons'):
                for btn in self.category_buttons:
                    apply_category_button_style(btn)

            # 更新统计面板
            if hasattr(self, 'statistics_panel') and hasattr(self.statistics_panel, 'apply_theme'):
                self.statistics_panel.apply_theme()

            # 更新移除按钮（红色主题按钮）
            if hasattr(self, 'delete_button'):
                self.delete_button.setStyleSheet(f"""
                    QPushButton#remove_button {{
                        background-color: {c.ERROR};
                        color: white;
                        border: none;
                        border-radius: 4px;
                        font-size: 14px;
                        font-weight: normal;
                        text-align: center;
                    }}
                    QPushButton#remove_button:hover {{
                        background-color: {c.ERROR_DARK};
                    }}
                    QPushButton#remove_button:pressed {{
                        background-color: {c.ERROR_DARK};
                    }}
                """)

            # 更新EnhancedImageLabel背景
            if hasattr(self, 'image_label'):
                # 更新图像标签样式
                self.image_label.setStyleSheet(WidgetStyles.get_image_label_style())

                # 更新信息按钮样式
                if hasattr(self.image_label, 'info_button'):
                    self.image_label.info_button.setStyleSheet(WidgetStyles.get_info_button_style())

            # 更新所有QLabel的颜色
            if hasattr(self, 'findChildren'):
                for label in self.findChildren(QLabel):
                    current_style = label.styleSheet()
                    # 只更新没有特殊样式的标签
                    if "background-color: #FFF8E1" not in current_style and "color:" not in current_style:
                        label.setStyleSheet(f"QLabel {{ color: {c.TEXT_PRIMARY}; }}")

            # 更新状态栏样式
            if hasattr(self, 'statusBar'):
                self.statusBar.setStyleSheet(f"""
                    QStatusBar {{
                        background-color: {c.BACKGROUND_SECONDARY};
                        color: {c.TEXT_PRIMARY};
                        border-top: 1px solid {c.BORDER_MEDIUM};
                    }}
                    QStatusBar::item {{
                        border: none;
                    }}
                """)

            # 更新版本标签样式
            if hasattr(self, 'version_label'):
                self.version_label.setStyleSheet(f"""
                    QLabel {{
                        color: {c.TEXT_SECONDARY};
                        padding: 2px 8px;
                        font-size: 11px;
                    }}
                """)

            # Phase 1.1 性能优化：只更新按钮样式，不重新创建（避免6秒卡顿）
            if hasattr(self, 'category_buttons') and self.category_buttons:
                # 不要调用 _update_category_buttons_internal()，那会重建所有按钮
                # 只更新现有按钮的标签颜色即可
                for button in self.category_buttons:
                    if hasattr(button, 'update_label_colors'):
                        button.update_label_colors()

            # 强制重绘
            self.update()

        except Exception as e:
            self.logger.error(f"应用主题失败: {e}")

    def start_auto_theme_timer(self):
        """启动自动主题定时器"""
        if not self._auto_theme_timer.isActive():
            self._auto_theme_timer.start(60000)  # 每60秒（1分钟）检查一次
            self.logger.info("自动主题定时器已启动")

    def stop_auto_theme_timer(self):
        """停止自动主题定时器"""
        if self._auto_theme_timer.isActive():
            self._auto_theme_timer.stop()
            self.logger.info("自动主题定时器已停止")

    def _check_and_apply_auto_theme(self):
        """检查并应用自动主题（定时器回调）"""
        try:
            app_config = get_app_config()

            # 重新加载配置确保检测到模式变化（防止缓存不一致）
            app_config.reload_config()

            # 只有在自动模式下才进行检查
            if app_config.theme_mode != "auto":
                return

            # 根据时间获取应该使用的主题
            expected_theme = app_config.get_auto_theme_by_time()
            current_theme = app_config.theme

            # 如果主题需要切换
            if expected_theme != current_theme:
                self.logger.info(f"自动主题切换: {current_theme} -> {expected_theme}")

                # 更新配置
                app_config.theme = expected_theme
                default_theme.set_theme(expected_theme)

                # 应用主题到界面
                self.apply_theme()

                # 更新主题按钮图标
                if hasattr(self, 'theme_button'):
                    theme_icon = '☾' if expected_theme == "light" else '☼'
                    theme_tooltip = '切换到暗色主题' if expected_theme == "light" else '切换到亮色主题'
                    self.theme_button.setText(theme_icon)
                    self.theme_button.setToolTip(theme_tooltip)

        except Exception as e:
            self.logger.error(f"自动主题检查失败: {e}")

    def focusInEvent(self, event):
        """窗口获得焦点时的处理"""
        try:
            super().focusInEvent(event)
            self._shortcuts_active = True
            self._last_focus_time = time.time()
            self.logger.debug("窗口获得焦点，快捷键已激活")
        except Exception as e:
            self.logger.error(f"焦点获得事件处理失败: {e}")
    
    def focusOutEvent(self, event):
        """窗口失去焦点时的处理"""
        try:
            super().focusOutEvent(event)
            # 不立即禁用快捷键，给一个短暂的缓冲期
            QTimer.singleShot(500, self._check_focus_status)
            self.logger.debug("窗口失去焦点，延迟检查快捷键状态")
        except Exception as e:
            self.logger.error(f"焦点丢失事件处理失败: {e}")
    
    def _check_focus_status(self):
        """检查焦点状态"""
        try:
            if not self.isActiveWindow():
                self._shortcuts_active = False
                self.logger.debug("窗口非激活状态，快捷键已暂停")
            else:
                self._shortcuts_active = True
                self.logger.debug("窗口恢复激活状态，快捷键已重新激活")
        except Exception as e:
            self.logger.error(f"焦点状态检查失败: {e}")

    def _is_in_input_mode(self):
        """检测是否处于输入模式（有输入控件获得焦点）"""
        try:  
            focused_widget = self.focusWidget()
            if focused_widget:
                # 检查是否是输入控件
                input_widgets = (QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox)
                return isinstance(focused_widget, input_widgets)
            return False
        except Exception:
            return False

    # ===== 更新相关 =====
    def _schedule_auto_update_check(self):
        """根据配置调度一次自动检查更新（应用启动后几秒执行）"""
        try:
            app_config = get_app_config()
            if not app_config.auto_update_enabled:
                self.logger.debug("自动检查更新已关闭")
                return

            # 启动后5秒首次检查
            QTimer.singleShot(5000, self._auto_check_update_once)

            # 启动定期检查定时器（每1小时）
            self._start_periodic_update_check()
        except Exception as e:
            self.logger.debug(f"调度自动检查更新失败: {e}")

    def _start_periodic_update_check(self):
        """启动定期检查更新定时器（每1小时检查一次）"""
        try:
            app_config = get_app_config()
            if not app_config.auto_update_enabled:
                return

            # 创建定时器，每1小时（3600000毫秒）触发一次
            self.periodic_update_timer = QTimer(self)
            self.periodic_update_timer.timeout.connect(self._periodic_check_update)
            self.periodic_update_timer.start(3600000)  # 1小时 = 1 * 60 * 60 * 1000ms

            self.logger.info("定期检查更新已启动：每1小时检查一次")
        except Exception as e:
            self.logger.debug(f"启动定期检查更新定时器失败: {e}")

    def _periodic_check_update(self):
        """定期检查更新（每1小时触发）"""
        try:
            self.logger.info("定期检查更新：开始执行")
            self._auto_check_update_once()
        except Exception as e:
            self.logger.debug(f"定期检查更新失败: {e}")

    def _on_update_check_success(self, manifest, endpoint, token):
        """修复问题4：后台更新检查成功的回调"""
        try:
            online_version = str(manifest.get('version', '')).strip()
            self.logger.info(f"检查线上更新：发现版本 v{online_version}")
            # 调用原有逻辑，传递线上版本信息
            self._process_update_result(online_version, manifest, endpoint, token)
        except Exception as e:
            self.logger.error(f"处理更新检查结果失败: {e}")

    def _on_update_check_failed(self, error_message):
        """修复问题4：后台更新检查失败的回调"""
        self.logger.debug(f"检查线上更新失败: {error_message}")
        # 检查失败时，继续处理本地更新包（如果有的话）
        self._process_update_result(None, None, None, None)

    def _auto_check_update_once(self):
        """执行一次静默检查，有更新则弹窗提示"""

        # 检查 update 目录下是否有更新包
        local_pending_version = None
        local_download_path = None
        local_batch_path = None

        try:
            # 获取用户目录下的 update 文件夹
            update_dir = get_update_dir()

            self.logger.debug(f"检查本地更新目录: {update_dir}")

            if update_dir.exists():
                # 查找 update 目录下的 exe 文件
                exe_files = list(update_dir.glob('*.exe'))
                if exe_files:
                    # 按修改时间排序，取最新的
                    exe_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
                    local_download_path = exe_files[0]

                    # 从文件名提取版本号（例如：图像分类工具_v6.3.2.exe）
                    match = re.search(r'v(\d+\.\d+\.\d+)', local_download_path.name)
                    if match:
                        local_pending_version = match.group(1)

                    # 检查是否有对应的 batch 文件
                    batch_files = list(update_dir.glob('update.bat'))
                    if batch_files:
                        local_batch_path = batch_files[0]

                    self.logger.info(f"检测到本地待安装更新: version={local_pending_version}, exe={local_download_path.name}, batch={local_batch_path}")
        except Exception as e:
            self.logger.debug(f"检查本地更新目录失败: {e}")

        # 修复问题4：使用后台线程检查线上最新版本，避免阻塞UI
        try:
            self.logger.debug("检查线上更新：开始（后台线程）")
            endpoint = None
            token = ''
            if self.config:
                endpoint = getattr(self.config, 'update_endpoint', None)
                token = getattr(self.config, 'update_token', '')
            if not endpoint:
                endpoint = get_manifest_url(latest=True)

            # 停止旧的检查线程（如果存在）
            if self.update_checker_thread and self.update_checker_thread.isRunning():
                self.logger.debug("停止旧的更新检查线程")
                self.update_checker_thread.quit()
                self.update_checker_thread.wait()

            # 创建新的后台检查线程
            self.update_checker_thread = UpdateCheckerThread(endpoint, token)
            self.update_checker_thread.check_success.connect(self._on_update_check_success)
            self.update_checker_thread.check_failed.connect(self._on_update_check_failed)

            # 保存本地更新包信息，供回调使用
            self._local_update_info = {
                'version': local_pending_version,
                'path': local_download_path,
                'batch_path': local_batch_path
            }

            self.update_checker_thread.start()
            self.logger.debug("后台更新检查线程已启动")
        except Exception as e:
            self.logger.debug(f"启动后台更新检查失败: {e}")
            # 失败时调用回调处理
            self._on_update_check_failed(str(e))

    def _process_update_result(self, online_version, manifest, endpoint, token):
        """处理更新检查结果"""
        # 从保存的信息中恢复本地更新包数据
        local_info = getattr(self, '_local_update_info', {})
        local_pending_version = local_info.get('version')
        local_download_path = local_info.get('path')
        local_batch_path = local_info.get('batch_path')

        # 判断是使用本地更新包还是下载新版本
        if local_pending_version and local_download_path:
            # 有本地更新包，比较版本
            if online_version and compare_version(online_version, local_pending_version) > 0:
                # 线上版本更新，清理旧更新包，提示下载新版本
                self.logger.info(f"线上版本v{online_version}比本地v{local_pending_version}更新，清理旧包并提示下载新版本")
                try:
                    # 删除旧更新包
                    if local_download_path.exists():
                        local_download_path.unlink()
                        self.logger.info(f"已删除旧更新包: {local_download_path}")
                    if local_batch_path and local_batch_path.exists():
                        local_batch_path.unlink()
                        self.logger.info(f"已删除旧批处理脚本: {local_batch_path}")
                except Exception as e:
                    self.logger.warning(f"清理旧更新包失败: {e}")

                # 修复问题5：直接使用已传入的manifest参数，避免重复同步调用
                try:
                    if manifest:
                        size_bytes = int(manifest.get('size_bytes', 0) or 0)
                        notes = str(manifest.get('notes', '')).strip()

                        # 显示更新对话框
                        update_dialog = UpdateInfoDialog(
                            new_version=online_version,
                            current_version=__version__,
                            size_bytes=size_bytes,
                            notes=notes,
                            manifest=manifest,
                            token=token,
                            parent=self
                        )
                        update_dialog.exec()
                    else:
                        self.logger.warning("无法获取线上更新详情（manifest为空）")
                except Exception as e:
                    self.logger.error(f"处理线上更新失败: {e}")
            else:
                # 本地更新包是最新的或线上检查失败，检查是否需要安装
                # 如果本地更新包版本等于当前版本，删除更新包（已经是这个版本了）
                if local_pending_version == __version__:
                    self.logger.info(f"本地更新包v{local_pending_version}与当前版本相同，清理更新包")
                    try:
                        if local_download_path.exists():
                            local_download_path.unlink()
                            self.logger.info(f"已删除同版本更新包: {local_download_path}")
                        if local_batch_path and local_batch_path.exists():
                            local_batch_path.unlink()
                            self.logger.info(f"已删除批处理脚本: {local_batch_path}")
                    except Exception as e:
                        self.logger.warning(f"清理同版本更新包失败: {e}")
                    return  # 不提示安装

                # 本地更新包版本高于当前版本，提示安装
                self.logger.info(f"本地更新包v{local_pending_version}比当前版本v{__version__}更新，提示安装")
                try:
                    # 如果批处理脚本不存在，需要重新生成
                    if not local_batch_path or not local_batch_path.exists():
                        self.logger.warning(f"批处理脚本不存在，重新生成")
                        # 获取正确的exe路径（开发环境 vs 打包环境）
                        if getattr(sys, 'frozen', False):
                            # 打包环境：使用exe所在目录
                            exe_path = Path(sys.executable)
                        else:
                            # 开发环境：使用当前工作目录下的模拟exe路径
                            exe_path = Path.cwd() / "ImageClassifier.exe"
                        local_batch_path = launch_self_update(exe_path, local_download_path)
                        self.logger.info(f"已生成批处理脚本: {local_batch_path}")

                    # 创建主题适配的消息框
                    box = QMessageBox(self)
                    box.setWindowTitle('发现已下载更新')
                    box.setText(f'检测到待安装的更新 v{local_pending_version}，是否现在重启并完成更新？')
                    box.setIcon(QMessageBox.Icon.Question)

                    # 设置程序图标
                    try:
                        icon_path = self._get_resource_path('assets/icon.ico')
                        if icon_path and icon_path.exists():
                            box.setWindowIcon(QIcon(str(icon_path)))
                    except Exception:
                        pass

                    # 应用主题适配样式
                    config = get_app_config()
                    default_theme.set_theme(config.theme)
                    c = default_theme.colors

                    box.setStyleSheet(f"""
                        QMessageBox {{
                            background-color: {c.BACKGROUND_PRIMARY};
                            color: {c.TEXT_PRIMARY};
                            border: 1px solid {c.BORDER_MEDIUM};
                            border-radius: 8px;
                            font-size: 14px;
                            min-width: 400px;
                        }}
                        QMessageBox QLabel {{
                            color: {c.TEXT_PRIMARY};
                            font-size: 14px;
                            padding: 10px;
                        }}
                        QPushButton {{
                            background-color: {c.PRIMARY};
                            color: white;
                            border: none;
                            border-radius: 6px;
                            padding: 10px 24px;
                            font-size: 14px;
                            font-weight: bold;
                            min-width: 100px;
                            min-height: 36px;
                        }}
                        QPushButton:hover {{ background-color: {c.PRIMARY_DARK}; }}
                        QPushButton:pressed {{ background-color: {c.PRIMARY_DARK}; }}
                    """)

                    # 使用自定义按钮
                    yes_btn = box.addButton("是", QMessageBox.ButtonRole.YesRole)
                    no_btn = box.addButton("否", QMessageBox.ButtonRole.NoRole)
                    box.setDefaultButton(yes_btn)

                    box.exec()
                    clicked_button = box.clickedButton()

                    if clicked_button == yes_btn:
                        # 立即重启安装
                        try:
                            self.logger.info(f"启动批处理脚本: {local_batch_path}")
                            subprocess.Popen(["cmd", "/c", "start", "", str(local_batch_path), str(local_download_path)], shell=False)
                            self.logger.info("用户选择立即重启安装更新")
                            QApplication.quit()
                        except Exception as e:
                            self.logger.error(f"启动批处理失败: {e}")
                    else:
                        # 用户选择稍后安装，保留红点标记
                        self.logger.info("用户选择稍后安装待更新版本")
                except Exception as e:
                    self.logger.debug(f"提示安装本地更新失败: {e}")
        else:
            # 没有本地更新包，检查线上更新
            if online_version:
                try:
                    # 比较版本
                    cmp_result = compare_version(online_version, __version__)
                    if cmp_result > 0:
                        # 有新版本，弹窗提示
                        self.logger.info(f"检测到新版本 v{online_version}，当前版本 v{__version__}")

                        # 修复问题5：直接使用已传入的manifest参数，避免重复同步调用
                        if manifest:
                            size_bytes = int(manifest.get('size_bytes', 0) or 0)
                            notes = str(manifest.get('notes', '')).strip()

                            # 显示更新对话框
                            update_dialog = UpdateInfoDialog(
                                new_version=online_version,
                                current_version=__version__,
                                size_bytes=size_bytes,
                                notes=notes,
                                manifest=manifest,
                                token=token,
                                parent=self
                            )
                            update_dialog.exec()
                        else:
                            self.logger.warning("无法获取更新详情（manifest为空）")
                    else:
                        self.logger.debug(f"当前版本已是最新: v{__version__}")
                except Exception as e:
                    self.logger.error(f"处理线上更新失败: {e}")
            else:
                self.logger.debug("未获取到线上版本信息")
    
    def keyPressEvent(self, event):
        """处理键盘事件 - 优化按键处理和日志记录"""
        try:
            # 检查快捷键是否激活
            if not self._shortcuts_active:
                self.logger.debug("快捷键未激活，尝试重新激活")
                self._shortcuts_active = True
                
            key = event.key()
            modifiers = event.modifiers()
            
            # 检查是否在输入模式
            in_input_mode = self._is_in_input_mode()
            
            # 过滤掉纯修饰键，避免日志噪音和冲突
            modifier_keys = {
                Qt.Key.Key_Ctrl, Qt.Key.Key_Shift, Qt.Key.Key_Alt, 
                Qt.Key.Key_Meta, Qt.Key.Key_AltGr, Qt.Key.Key_CapsLock,
                Qt.Key.Key_NumLock, Qt.Key.Key_ScrollLock
            }
            
            # 记录按键信息 - 分级别记录
            if not in_input_mode:  # 只在非输入模式下记录按键
                key_text = event.text() or f"Key_{key}"
                modifier_text = []
                if modifiers & Qt.KeyboardModifier.ControlModifier:
                    modifier_text.append("Ctrl")
                if modifiers & Qt.KeyboardModifier.ShiftModifier:
                    modifier_text.append("Shift")
                if modifiers & Qt.KeyboardModifier.AltModifier:
                    modifier_text.append("Alt")
                
                modifier_str = "+".join(modifier_text)
                full_key = f"{modifier_str}+{key_text}" if modifier_str else key_text
                
                # DEBUG级别：记录所有按键（包括修饰键和不支持的按键）
                if key in modifier_keys:
                    self.logger.debug(f"修饰键: {full_key} (code: {key})")
                else:
                    self.logger.debug(f"按键: {full_key} (code: {key}) - 快捷键状态: {'激活' if self._shortcuts_active else '禁用'}")

                # INFO级别：只记录已定义的快捷键
                if self._is_defined_shortcut(key, modifiers):
                    self.logger.info(f"快捷键触发: {full_key}")
            
            # 处理修饰键
            if key in modifier_keys:
                # 纯修饰键不处理，直接传递给父类
                super().keyPressEvent(event)
                return
            
            # 直接传递给父类让QAction系统处理所有快捷键
            super().keyPressEvent(event)
            
        except Exception as e:
            self.logger.error(f"键盘事件处理失败: {e}")
            super().keyPressEvent(event)
    
    def select_previous_category(self):
        """选择上一个类别"""
        try:
            if not hasattr(self, 'current_category_index'):
                self.current_category_index = -1
            
            if self.category_buttons:
                self.current_category_index = (self.current_category_index - 1) % len(self.category_buttons)
                self.logger.debug(f"选择上一个类别: {self.current_category_index}/{len(self.category_buttons)}")
                self.highlight_selected_category()
                
        except Exception as e:
            self.logger.error(f"选择上一个类别失败: {e}")
    
    def select_next_category(self):
        """选择下一个类别"""
        try:
            if not hasattr(self, 'current_category_index'):
                self.current_category_index = -1
            
            if self.category_buttons:
                self.current_category_index = (self.current_category_index + 1) % len(self.category_buttons)
                self.logger.debug(f"选择下一个类别: {self.current_category_index}/{len(self.category_buttons)}")
                self.highlight_selected_category()
                
        except Exception as e:
            self.logger.error(f"选择下一个类别失败: {e}")
    
    def highlight_selected_category(self):
        """高亮选中的类别按钮"""
        try:
            self.logger.debug(f"高亮类别按钮: {self.current_category_index}/{len(self.category_buttons) if hasattr(self, 'category_buttons') else 0}")
            
            # 重置所有按钮样式
            for i, button in enumerate(self.category_buttons):
                if i == self.current_category_index:
                    # 高亮选中的按钮
                    button.setStyleSheet("""
                        QPushButton {
                            background-color: #0078d4;
                            color: white;
                            border: 2px solid #005a9e;
                            font-weight: bold;
                        }
                    """)
                    category_name = button.category_name
                    self.statusBar.showMessage(f"🎯 选中类别: {category_name} (按Enter确认)")
                    self.logger.debug(f"高亮类别按钮: {category_name}")
                else:
                    # 恢复正常样式
                    button.setStyleSheet("")
                        
        except Exception as e:
            self.logger.error(f"高亮类别失败: {e}")
    
    def rename_category(self, old_name, new_name):
        """重命名类别"""
        try:
            if not self.current_dir:
                toast_error(self,"当前目录未设置")
                return
                
            old_path = self.current_dir.parent / old_name
            new_path = self.current_dir.parent / new_name
            
            if not old_path.exists():
                toast_error(self,f"类别目录不存在: {old_name}")
                return
                
            if new_path.exists():
                toast_error(self,f"目标类别已存在: {new_name}")
                return
            
            # 重命名目录
            old_path.rename(new_path)
            
            # 更新配置中的快捷键映射
            if old_name in self.config.category_shortcuts:
                shortcut = self.config.category_shortcuts.pop(old_name)
                self.config.category_shortcuts[new_name] = shortcut
            
            # 更新分类状态中的类别名称
            updates = {}
            for img_path, category in self.classified_images.items():
                if category == old_name:
                    updates[img_path] = new_name
            
            for img_path, new_category in updates.items():
                self.classified_images[img_path] = new_category
            
            # 保存配置和状态
            self.config.save_config()
            self.save_state()
            
            # 重新加载类别
            self.load_categories()
            
            toast_success(self,f"类别已重命名: {old_name} → {new_name}")
            self.logger.info(f"类别重命名成功: {old_name} → {new_name}")
            
        except Exception as e:
            self.logger.error(f"重命名类别失败: {e}")
            toast_error(self,f"重命名失败: {str(e)}")
    
    def ignore_category(self, category_name):
        """忽略类别 - 不删除目录，只是不显示"""
        try:
            if not self.current_dir:
                toast_error(self, "当前目录未设置")
                return

            # 添加到忽略列表
            if self.config.add_ignored_category(category_name):
                # 从快捷键配置中移除该类别
                if category_name in self.config.category_shortcuts:
                    del self.config.category_shortcuts[category_name]

                # 从分类状态中移除相关记录（可选）
                # 注意：这里不删除实际文件，只是清理内存中的分类记录
                to_remove = []
                for img_path, category in self.classified_images.items():
                    # 处理单分类模式
                    if isinstance(category, str) and category == category_name:
                        to_remove.append(img_path)
                    # 处理多分类模式
                    elif isinstance(category, list) and category_name in category:
                        # 从列表中移除该类别
                        category.remove(category_name)
                        # 如果列表为空，则完全移除该记录
                        if not category:
                            to_remove.append(img_path)

                # 清除分类记录
                for img_path in to_remove:
                    del self.classified_images[img_path]

                # 保存配置和状态
                self.config.save_config()
                self.save_state()

                # 重新加载类别
                self.load_categories()

                # 刷新UI
                self.schedule_ui_update('category_buttons', 'category_counts', 'image_list', 'statistics')

                # 显示成功提示
                toast_success(self, f"类别已忽略: {category_name}")
                self.logger.info(f"类别已忽略: {category_name}")
            else:
                toast_warning(self, f"类别 '{category_name}' 已经在忽略列表中")

        except Exception as e:
            self.logger.error(f"忽略类别失败: {e}", exc_info=True)
            toast_error(self, f"忽略类别失败: {str(e)}")

    def show_manage_ignored_dialog(self):
        """显示管理忽略列表对话框"""
        try:

            dialog = ManageIgnoredCategoriesDialog(self.config, self)
            dialog.exec()

        except Exception as e:
            self.logger.error(f"显示管理忽略对话框失败: {e}", exc_info=True)
            toast_error(self, f"显示对话框失败: {str(e)}")

    def delete_category(self, category_name):
        """删除类别 - 带二次确认"""
        try:
            if not self.current_dir:
                toast_error(self,"当前目录未设置")
                return
                
            category_path = self.current_dir.parent / category_name
            
            if not category_path.exists():
                toast_error(self,f"类别目录不存在: {category_name}")
                return
            
            # 统计目录中的图片数量
            image_count = 0
            if category_path.is_dir():
                for file_path in category_path.iterdir():
                    if file_path.is_file() and file_path.suffix.lower() in ['.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff']:
                        image_count += 1
            
            # 二次确认对话框
            if image_count > 0:
                reply = self.show_question_message(
                    "确认删除类别", 
                    f"类别目录 '{category_name}' 中有 {image_count} 张图片文件。\n\n"
                    f"确认删除这个类别目录吗？\n"
                    f"这将永久删除目录及其中的所有文件！"
                )
                
                if reply != QMessageBox.StandardButton.Yes:
                    self.logger.info(f"用户取消删除类别: {category_name}")
                    return
            else:
                # 空目录只需简单确认
                reply = self.show_question_message(
                    "确认删除类别", 
                    f"确认删除空的类别目录 '{category_name}' 吗？"
                )
                
                if reply != QMessageBox.StandardButton.Yes:
                    self.logger.info(f"用户取消删除空类别: {category_name}")
                    return
            
            # 删除目录及其内容
            shutil.rmtree(category_path)
            
            # 从配置中移除
            if category_name in self.config.category_shortcuts:
                del self.config.category_shortcuts[category_name]
            
            # 从分类状态中移除相关记录，并根据操作模式处理文件状态
            to_remove = []
            for img_path, category in self.classified_images.items():
                if category == category_name:
                    to_remove.append(img_path)
            
            # 清除分类记录
            for img_path in to_remove:
                del self.classified_images[img_path]
            
            # 根据操作模式处理文件状态
            if not self.is_copy_mode:
                # 移动模式：图片已从原目录移动到类别目录，删除类别后图片不再存在于原目录
                # 需要从图片文件列表中移除这些图片
                files_to_remove = []
                for img_path in to_remove:
                    img_file = Path(img_path)
                    # 检查原目录中是否还有这个文件
                    if not img_file.exists():
                        files_to_remove.append(img_path)
                
                # 更新图片文件列表
                if files_to_remove:
                    self.image_files = [f for f in self.image_files if str(f) not in files_to_remove]
                    self.total_images = len(self.image_files)
                    
                    # 调整当前索引
                    if self.current_index >= len(self.image_files):
                        self.current_index = max(0, len(self.image_files) - 1)
                        
                    self.logger.info(f"移动模式下删除类别，从图片列表中移除了 {len(files_to_remove)} 张图片")
            
            # 复制模式下不需要特殊处理，图片仍在原目录中，刷新时会自动恢复为未分类状态
            
            # 保存配置和状态
            self.config.save_config()
            self.save_state()
            
            # 重新加载类别
            self.load_categories()
            
            # 刷新UI以反映变化
            self.schedule_ui_update('image_list', 'category_buttons', 'category_counts', 'statistics')
            
            # 如果当前显示的图片被移除，需要重新显示
            if (not self.is_copy_mode and self.image_files and 
                0 <= self.current_index < len(self.image_files)):
                self.show_current_image()
            
            # 根据图片数量显示不同的成功信息
            if image_count > 0:
                toast_success(self,f"类别已删除: {category_name} (删除了 {image_count} 张图片文件)")
                self.logger.info(f"类别删除成功: {category_name}，删除了 {image_count} 张图片")
            else:
                # 空目录删除成功，不需要弹窗，只记录日志
                self.logger.info(f"空类别删除成功: {category_name}")
            
        except Exception as e:
            self.logger.error(f"删除类别失败: {e}")
            toast_error(self,f"删除失败: {str(e)}")
    
    def save_state(self):
        """异步保存当前状态到图片同级目录"""
        try:
            if not self.current_dir:
                return
                
            # 准备状态数据
            state_data = {
                'classified_images': dict(self.classified_images),
                'removed_images': list(self.removed_images),
                'last_index': self.current_index,
                'version': self.version,
                'is_copy_mode': self.is_copy_mode,  # 保存操作模式状态
                'is_multi_category': self.is_multi_category  # 保存分类模式状态
            }
            
            # 状态文件保存在图片目录的父目录（同级目录），而不是图片目录内
            parent_dir = self.current_dir.parent
            state_file = parent_dir / 'classification_state.json'
            
            # 异步保存，避免阻塞UI
            QTimer.singleShot(0, lambda: self._async_save_state(state_file, state_data))
                
        except Exception as e:
            self.logger.error(f"准备保存状态失败: {e}")

    def _save_state_sync(self):
        """立即同步保存当前状态到图片同级目录（用于重要状态变化）"""
        try:
            if not self.current_dir:
                return

            # 准备状态数据
            state_data = {
                'classified_images': dict(self.classified_images),
                'removed_images': list(self.removed_images),
                'last_index': self.current_index,
                'version': self.version,
                'is_copy_mode': self.is_copy_mode,  # 保存操作模式状态
                'is_multi_category': self.is_multi_category  # 保存分类模式状态
            }

            # 状态文件保存在图片目录的父目录（同级目录），而不是图片目录内
            parent_dir = self.current_dir.parent
            state_file = parent_dir / 'classification_state.json'

            # 立即同步保存
            with open(state_file, 'w', encoding='utf-8') as f:
                json.dump(state_data, f, ensure_ascii=False, indent=2)

            self.logger.info(f"模式状态已同步保存到: {state_file}")

        except Exception as e:
            self.logger.error(f"同步保存状态失败: {e}")

    def _async_save_state(self, state_file, state_data):
        """异步执行状态保存"""
        try:
            with open(state_file, 'w', encoding='utf-8') as f:
                json.dump(state_data, f, ensure_ascii=False, indent=2)
                
            self.logger.debug(f"状态已异步保存到: {state_file}")
                
        except Exception as e:
            self.logger.error(f"异步保存状态失败: {e}")
            # 如果异步保存失败，尝试同步保存作为备份
            try:
                with open(state_file, 'w', encoding='utf-8') as f:
                    json.dump(state_data, f, ensure_ascii=False, indent=2)
                self.logger.info(f"备份同步保存成功: {state_file}")
            except Exception as backup_error:
                self.logger.error(f"备份保存也失败: {backup_error}")

    def _create_styled_message_box(self, icon_type, title, text, buttons=None):
        """创建具有统一样式和中文按钮的消息框"""

        msgBox = QMessageBox(self)
        msgBox.setIcon(icon_type)
        msgBox.setWindowTitle(title)
        msgBox.setText(text)

        # 设置程序图标
        try:
            icon_path = self._get_resource_path('assets/icon.ico')
            if icon_path and icon_path.exists():
                msgBox.setWindowIcon(QIcon(str(icon_path)))
        except Exception:
            pass

        # 使用主题样式
        c = default_theme.colors
        message_box_style = f"""
            QMessageBox {{
                background-color: {c.BACKGROUND_CARD};
                color: {c.TEXT_PRIMARY};
                border: 1px solid {c.BORDER_MEDIUM};
                border-radius: 8px;
                font-size: 14px;
            }}
            QMessageBox QLabel {{
                color: {c.TEXT_PRIMARY};
                font-size: 14px;
                padding: 10px;
            }}
            {ButtonStyles.get_primary_button_style()}
            QPushButton:default {{
                background-color: {c.SUCCESS};
            }}
            QPushButton:default:hover {{
                background-color: {c.SUCCESS_DARK};
            }}
        """
        msgBox.setStyleSheet(message_box_style)

        # 设置中文按钮
        if buttons is None:
            msgBox.setStandardButtons(QMessageBox.StandardButton.Ok)
            msgBox.button(QMessageBox.StandardButton.Ok).setText("确定")
        else:
            msgBox.setStandardButtons(buttons)
            # 中文化按钮文本
            if msgBox.button(QMessageBox.StandardButton.Ok):
                msgBox.button(QMessageBox.StandardButton.Ok).setText("确定")
            if msgBox.button(QMessageBox.StandardButton.Cancel):
                msgBox.button(QMessageBox.StandardButton.Cancel).setText("取消")
            if msgBox.button(QMessageBox.StandardButton.Yes):
                msgBox.button(QMessageBox.StandardButton.Yes).setText("是")
            if msgBox.button(QMessageBox.StandardButton.No):
                msgBox.button(QMessageBox.StandardButton.No).setText("否")
            if msgBox.button(QMessageBox.StandardButton.Apply):
                msgBox.button(QMessageBox.StandardButton.Apply).setText("应用")
            if msgBox.button(QMessageBox.StandardButton.Close):
                msgBox.button(QMessageBox.StandardButton.Close).setText("关闭")

        return msgBox
      
    def show_question_message(self, title, text):
        """显示询问消息框"""
        msgBox = self._create_styled_message_box(
            QMessageBox.Icon.Question,
            title,
            text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        msgBox.setDefaultButton(QMessageBox.StandardButton.No)
        return msgBox.exec()

    def refresh_category_buttons_style(self):
        """强制刷新所有类别按钮的样式"""
        if not self.category_buttons:
            return
            
        for btn in self.category_buttons:
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        self.logger.debug("强制刷新类别按钮样式")
