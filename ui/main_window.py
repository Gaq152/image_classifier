"""
主窗口模块

包含应用程序的主窗口类ImageClassifier。
"""

import logging
import time
import psutil
import os
import cv2
import functools
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from PyQt6.QtWidgets import (QMainWindow, QVBoxLayout, QHBoxLayout, QWidget, 
                            QSplitter, QLabel, QScrollArea, QStatusBar, QToolBar, 
                            QMenu, QToolButton, QSizePolicy, QFileDialog, 
                            QMessageBox, QApplication, QProgressDialog, QListWidget,
                            QButtonGroup, QPushButton, QAbstractItemView, QFrame)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QSize
from PyQt6.QtGui import QAction, QKeySequence, QPixmap, QColor, QIcon

from .widgets import (CategoryButton, ImageListItem, EnhancedImageLabel, 
                     StatisticsPanel)
from .dialogs import (CategoryShortcutDialog, AddCategoriesDialog, 
                     TabbedHelpDialog, ProgressDialog)
from ..core.config import Config
from ..core.scanner import FileScannerThread
from ..core.image_loader import HighPerformanceImageLoader
from ..utils.exceptions import ImageClassifierError, FileOperationError
from ..utils.file_operations import normalize_folder_name, retry_file_operation
from ..core.file_manager import FileOperationManager
from ..utils.performance import performance_monitor


class ImageClassifier(QMainWindow):
    """主图像分类器窗口"""
    
    # 信号定义
    file_moved = pyqtSignal(str, str)  # 文件移动信号(源路径, 目标路径)
    category_added = pyqtSignal(str)   # 类别添加信号
    
    def __init__(self):
        super().__init__()
        self.version = "5.3.0"
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
        
        # 创建用户界面
        self.init_ui()
        
        # 设置快捷键
        self.setup_shortcuts()
    
    def _get_resource_path(self, relative_path):
        """获取资源文件路径，兼容开发环境和打包环境"""
        try:
            import sys
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
            
            # 文件扫描器
            self.file_scanner = FileScannerThread()
            self.file_scanner.files_found.connect(self.on_files_found)
            self.file_scanner.initial_batch_ready.connect(self.on_initial_batch_ready)
            self.file_scanner.scan_progress.connect(self.on_scan_progress)
            self.file_scanner.scan_finished.connect(self.on_scan_completed)
            
            # 图像加载器
            self.image_loader = HighPerformanceImageLoader()
            # 连接图像加载器的信号
            self.image_loader.image_loaded.connect(self.on_image_loaded)
            self.image_loader.thumbnail_loaded.connect(self.on_thumbnail_loaded)
            self.image_loader.loading_progress.connect(self.on_loading_progress)
            self.image_loader.cache_status.connect(self.on_cache_status_updated)
            
            # 文件操作管理器
            self.file_manager = FileOperationManager()
            
            # 线程池（用于文件操作）
            self.thread_pool = ThreadPoolExecutor(max_workers=4)
            
            self.logger.info("核心组件初始化完成")
            
        except Exception as e:
            self.logger.error(f"核心组件初始化失败: {e}")
            raise ImageClassifierError(f"核心组件初始化失败: {e}")
    
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
        import threading
        self.ui_update_lock = threading.Lock()
        self.pending_ui_updates = set()
        self.ui_update_timer = QTimer()
        self.ui_update_timer.setSingleShot(True)
        self.ui_update_timer.timeout.connect(self.perform_batch_ui_update)
        
        # 类别计数缓存
        self.category_counts = {}
        self.category_count_cache_time = 0
        self.category_count_cache_ttl = 30  # 30秒TTL
    
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
            
            # 设置简洁的主窗口样式
            self.setStyleSheet("""
                QMainWindow {
                    background-color: #F8F9FA;
                }
                QSplitter::handle {
                    background-color: #BDC3C7;
                    border: 1px solid #95A5A6;
                    width: 4px;
                    border-radius: 2px;
                }
                QSplitter::handle:hover {
                    background-color: #3498DB;
                }
            """)
            
            # 创建中央控件
            central_widget = QWidget()
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

            self.logger.info("用户界面初始化完成")
            
        except Exception as e:
            self.logger.error(f"用户界面初始化失败: {e}")
            raise ImageClassifierError(f"用户界面初始化失败: {e}")
    
    def create_left_panel(self, parent):
        """创建简洁的左侧图片显示面板"""
        left_widget = QWidget()
        left_widget.setStyleSheet("""
            QWidget {
                background-color: #FFFFFF;
                border: 1px solid #DEE2E6;
                border-radius: 6px;
            }
        """)
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(6, 6, 6, 6)
        
        # 简化的标题 - 固定高度，不参与拉伸
        title_label = QLabel("🖼️ 图片预览")
        title_label.setStyleSheet("""
            QLabel {
                font-size: 14px;
                font-weight: bold;
                color: #495057;
                padding: 4px 6px;
                border-bottom: 1px solid #DEE2E6;
                max-height: 28px;
                min-height: 28px;
            }
        """)
        left_layout.addWidget(title_label, 0)  # 不拉伸
        
        # 图片显示区域 - 主要拉伸区域
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        scroll_area.setStyleSheet("""
            QScrollArea {
                border: 1px solid #ADB5BD;
                border-radius: 4px;
                background-color: #F8F9FA;
            }
        """)
        
        self.image_label = EnhancedImageLabel()
        scroll_area.setWidget(self.image_label)
        
        left_layout.addWidget(scroll_area, 1)  # 主要拉伸权重
        
        parent.addWidget(left_widget)
    
    def create_right_panel(self, parent):
        """创建简洁的右侧控制面板"""
        right_widget = QWidget()
        right_widget.setMaximumWidth(380)
        right_widget.setMinimumWidth(300)
        right_widget.setStyleSheet("""
            QWidget {
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
        
        # 删除按钮（放在底部）- 固定高度
        self.delete_button = QPushButton("🗑️ 删除图片 (Del)")
        self.delete_button.setObjectName("deleteButton")  # 设置对象名以应用特殊样式
        self.delete_button.clicked.connect(self.move_to_remove)
        # 确保删除按钮保持原有的红色样式
        self.delete_button.setStyleSheet("""
            QPushButton {
                background-color: #dc3545 !important;
                color: white !important;
                border: none !important;
                border-radius: 4px !important;
                padding: 12px 16px !important;
                font-size: 14px !important;
                font-weight: bold !important;
                margin: 8px 0px !important;
                max-height: 50px !important;
                min-height: 50px !important;
            }
            QPushButton:hover {
                background-color: #c82333 !important;
            }
            QPushButton:pressed {
                background-color: #bd2130 !important;
            }
        """)
        self.delete_button.setToolTip('删除当前图片到删除目录 (Del键)')
        right_layout.addWidget(self.delete_button, 0)  # 不拉伸
        
        # 版本信息 - 固定高度
        version_label = QLabel(f"版本 {self.version}")
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version_label.setStyleSheet("""
            QLabel {
                color: #666;
                padding: 4px;
                max-height: 20px;
                min-height: 20px;
            }
        """)
        right_layout.addWidget(version_label, 0)  # 不拉伸
        
        parent.addWidget(right_widget)
    
    def create_image_list_area(self, layout):
        """创建简洁的图片列表区域"""
        # 图片列表标题 - 固定高度
        list_label = QLabel("📂 图片列表")
        list_label.setStyleSheet("""
            QLabel {
                font-size: 13px;
                font-weight: bold;
                color: #0D6EFD;
                padding: 4px 6px;
                border-bottom: 2px solid #0D6EFD;
                margin-bottom: 4px;
                max-height: 24px;
                min-height: 24px;
            }
        """)
        layout.addWidget(list_label, 0)  # 不拉伸
        
        # 图片列表容器 - 可随窗口拉伸
        from PyQt6.QtWidgets import QListWidget
        self.image_list = QListWidget()
        self.image_list.setMinimumHeight(120)  # 设置最小高度
        # 移除最大高度限制，让它能够拉伸
        self.image_list.setStyleSheet("""
            QListWidget {
                border: 1px solid #B3D9FF;
                border-radius: 4px;
                background-color: #FFFFFF;
                padding: 2px;
            }
            QListWidget::item {
                border: 1px solid transparent;
                border-radius: 3px;
                padding: 4px 6px;
                margin: 1px;
            }
            QListWidget::item:hover {
                background-color: #E3F2FD;
                border-color: #2196F3;
            }
            QListWidget::item:selected {
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
        self.image_list.itemClicked.connect(self.on_image_list_item_clicked)
        layout.addWidget(self.image_list, 1)  # 设置拉伸权重1
    
    def create_category_area(self, layout):
        """创建简洁的类别按钮区域"""
        # 类别标题 - 固定高度
        category_label = QLabel("🏷️ 分类类别")
        category_label.setStyleSheet("""
            QLabel {
                font-size: 13px;
                font-weight: bold;
                color: #E65100;
                padding: 4px 6px;
                border-bottom: 2px solid #FF9800;
                margin-bottom: 4px;
                max-height: 24px;
                min-height: 24px;
            }
        """)
        layout.addWidget(category_label, 0)  # 不拉伸
        
        # 类别按钮滚动区域 - 可随窗口拉伸
        self.category_scroll = QScrollArea()
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
    
    def create_toolbar(self):
        """创建工具栏"""
        toolbar = QToolBar()
        toolbar.setMovable(False)
        # 设置工具栏的基础样式
        toolbar.setStyleSheet("""
            QToolBar {
                background-color: #F8F9FA;
                border: 1px solid #E1E8ED;
                border-radius: 6px;
                spacing: 8px;
                padding: 8px;
                margin: 2px;
            }
            /* QAction 按钮样式 */
            QToolBar QToolButton {
                background-color: #3498DB;
                color: white;
                border: 1px solid #2980B9;
                border-radius: 6px;
                padding: 6px 12px;
                margin: 2px;
                font-size: 13px;
                font-weight: bold;
                min-width: 80px;
                min-height: 34px;
                max-height: 34px;
            }
            QToolBar QToolButton:hover {
                background-color: #2980B9;
                border-color: #21618C;
            }
            QToolBar QToolButton:pressed {
                background-color: #21618C;
                border-color: #1B4F72;
            }
            /* 普通QPushButton样式 - 不影响模式按钮 */
            QToolBar QPushButton:not([objectName="mode_button"]) {
                background-color: #3498DB;
                color: white;
                border: 1px solid #2980B9;
                border-radius: 6px;
                padding: 6px 12px;
                margin: 2px;
                font-size: 13px;
                font-weight: bold;
                min-width: 80px;
                min-height: 34px;
                max-height: 34px;
            }
            QToolBar QPushButton:not([objectName="mode_button"]):hover {
                background-color: #2980B9;
                border-color: #21618C;
            }
            QToolBar QPushButton:not([objectName="mode_button"]):pressed {
                background-color: #21618C;
                border-color: #1B4F72;
            }
        """)
        self.addToolBar(toolbar)
        
        # 打开目录
        open_action = QAction('📁 打开目录', self)
        open_action.triggered.connect(self.open_directory)
        open_action.setToolTip('选择包含图片的目录')
        toolbar.addAction(open_action)
        
        # 新增类别
        add_category_action = QAction('➕ 新增类别', self)
        add_category_action.triggered.connect(self.add_category)
        add_category_action.setToolTip('批量添加分类类别')
        toolbar.addAction(add_category_action)
        
        toolbar.addSeparator()
        
        # 模式选择
        self.create_mode_button(toolbar)
        
        # 分类模式按钮（单分类/多分类）
        self.create_category_mode_button(toolbar)
        
        toolbar.addSeparator()
        
        # 刷新按钮
        refresh_action = QAction('🔄 刷新', self)
        refresh_action.triggered.connect(self.refresh_categories)
        refresh_action.setToolTip('刷新类别目录，同步外部变化 (F5)')
        toolbar.addAction(refresh_action)
        
        # 帮助按钮
        help_action = QAction('📖 帮助', self)
        help_action.triggered.connect(self.show_help_dialog)
        help_action.setToolTip('查看使用指南和快捷键')
        toolbar.addAction(help_action)
        
        # 添加弹性空间
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)
        
        # 操作提示
        tips_label = QLabel('提示: ↑↓选择类别 | Enter确认 | 双击快速分类 | 智能滑动窗口 | SMB/NAS优化 | 滚轮缩放')
        tips_label.setStyleSheet("""
            QLabel {
                color: #666;
                font-size: 11px;
                padding: 4px 8px;
                background-color: #fff;
                border: 1px solid #ddd;
                border-radius: 3px;
            }
        """)
        toolbar.addWidget(tips_label)
        
        toolbar.addSeparator()
    
    def create_mode_button(self, toolbar):
        """创建简化的模式选择按钮 - 直接点击切换"""
        # 创建一个简单的QPushButton，直接切换模式
        self.mode_button = QPushButton()
        self.mode_button.setText('📋 复制模式')
        self.mode_button.setObjectName("mode_button")
        self.mode_button.setToolTip('点击切换复制/移动模式')
        
        # 设置按钮尺寸 - 与其他按钮保持一致的尺寸
        self.mode_button.setFixedSize(110, 34)
        
        # 点击事件：直接切换模式
        self.mode_button.clicked.connect(lambda: self.set_mode(not self.is_copy_mode))
        
        # 设置与其他按钮一致的样式
        self.mode_button.setStyleSheet("""
            QPushButton#mode_button {
                background-color: #3498DB;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 13px;
                font-weight: bold;
                text-align: center;
                min-width: 90px;
                min-height: 34px;
                max-height: 34px;
            }
            QPushButton#mode_button:hover { 
                background-color: #2980B9; 
            }
            QPushButton#mode_button:pressed { 
                background-color: #21618C; 
            }
        """)

        # 添加到工具栏
        toolbar.addWidget(self.mode_button)
        self.set_mode(self.is_copy_mode)
    
    def create_status_bar(self):
        """创建状态栏"""
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.statusBar.showMessage("准备就绪")
    
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
                Qt.Key.Key_F: lambda: self.image_label.fit_to_window() if hasattr(self, 'image_label') else None,
                Qt.Key.Key_F5: self.refresh_categories,
            }
            
            # 设置组合快捷键（用于图像控制）
            combo_shortcuts = {
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
                
            if func:
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
            
            self.logger.info(base_info + extra_info)
            
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
            
            # 不需要特殊处理，EnhancedImageLabel会自动处理图像缩放
            
        except Exception as e:
            if hasattr(self, 'logger'):
                self.logger.error(f"窗口大小改变处理失败: {e}")
    
    # ===== 目录和文件处理方法 =====
    
    def open_directory(self):
        """打开图片目录"""
        dir_path = QFileDialog.getExistingDirectory(self, '选择图片目录')
        if dir_path:
            self.current_dir = Path(dir_path)
            
            # 检查是否为网络路径
            path_str = str(self.current_dir)
            is_network_path = path_str.startswith('\\\\')
            
            if is_network_path:
                # 网络路径提醒
                self.show_info_message('SMB/NAS路径检测', 
                    f'检测到SMB/NAS网络路径：\n{self.current_dir}\n\n'
                    f'🚀 已启用SMB专项优化：\n'
                    f'• 本地缓存：自动缓存图片到本地\n'
                    f'• 分块读取：大文件采用分块策略减少网络延迟\n'
                    f'• 智能预加载：减少网络文件预加载量\n'
                    f'• 连接优化：复用SMB连接，减少建连开销\n'
                    f'• 渐进式显示：先显示缩略图，后加载完整图片\n\n'
                    f'⚠️ 使用建议：\n'
                    f'• 确保网络连接稳定\n'
                    f'• 首次加载会建立本地缓存，后续访问将显著加速\n'
                    f'• 支持格式：JPG、JPEG、PNG、BMP\n'
                    f'• 本地缓存最大5GB，会自动清理')
                    
                self.logger.info(f"用户选择网络路径: {self.current_dir}")
            else:
                self.logger.info(f"用户选择本地路径: {self.current_dir}")
            
            # 设置配置文件路径为图片目录的父目录
            self.config.set_base_dir(str(self.current_dir.parent))
            
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
                    
                    if not is_reserved and not is_current_dir:
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
            
            # 按名称排序，确保类别显示顺序一致
            self.ordered_categories = sorted(list(self.categories))
            
            # 保存更新后的配置
            self.config.save_config()
            
            # 初始化类别计数
            self.init_category_counts()
            
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
                
                # 连接同步完成信号
                if hasattr(self.file_manager, 'file_sync'):
                    self.file_manager.file_sync.sync_completed.connect(self._on_sync_completed)
                    self.file_manager.file_sync.sync_progress.connect(self._on_sync_progress)
                
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
        """开始智能加载目录下的图片"""
        if not self.current_dir:
            return
            
        # 清理图片缓存
        self.image_loader.clear_cache()
        
        # 重置状态
        self.all_image_files = []
        self.image_files = []
        self.current_index = -1
        self.total_images = 0
        self.loading_in_progress = True
        self.initial_batch_loaded = False
        self.background_loading = False
        
        # 显示加载提示
        self.statusBar.showMessage("🔍 正在后台扫描图片文件...")
        
        # 启动智能文件扫描
        self.file_scanner.scan_directory(self.current_dir)
    
    # ===== 文件扫描事件处理 =====
    
    def on_initial_batch_ready(self, initial_files):
        """处理初始批次文件"""
        if not self.loading_in_progress:
            return
            
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
        
        # 后台标记：程序已可用，全量扫描在后台继续
        self.background_loading = True
        
        self.logger.info("🚀 程序UI已完全启用，用户可立即使用")

    
    
    def _delayed_load_state(self):
        """延迟加载状态文件，避免阻塞UI"""
        try:
            self.load_state()
            
            # 检查并修复当前列表中的重复文件
            self._remove_duplicates_from_current_list()
            
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

    def on_scan_progress(self, message):
        """处理扫描进度"""
        self.statusBar.showMessage(message)
    
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
        
        finally:
            # 恢复重绘
            self.setUpdatesEnabled(True)
            self.update()
    
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
            self.image_list.clear()
            
            if not self.image_files:
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
            
            # 添加所有图片到列表中
            for i in range(start_index, end_index):
                file_path = self.image_files[i]
                file_path_str = str(file_path)
                
                # 检查分类和移除状态
                is_classified = file_path_str in self.classified_images
                is_removed = file_path_str in self.removed_images
                
                # 检查是否是多分类
                is_multi_classified = False
                if is_classified:
                    category = self.classified_images.get(file_path_str)
                    is_multi_classified = isinstance(category, list) and len(category) > 1
                
                item = ImageListItem(file_path_str, is_classified, is_removed)
                item.image_index = i  # 添加索引属性
                item.is_multi_classified = is_multi_classified  # 设置多分类状态
                
                # 设置状态图标
                item.set_status_icon()
                
                self.image_list.addItem(item)
                
                # 设置当前选中状态和高亮
                if i == self.current_index:
                    # 高亮当前项
                    item.setSelected(True)
                    self.image_list.setCurrentItem(item)
                    # 确保当前项可见
                    self.image_list.scrollToItem(item, QAbstractItemView.ScrollHint.EnsureVisible)
            
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
                import json
                with open(state_file, 'r', encoding='utf-8') as f:
                    state = json.load(f)
                    
                self.classified_images = state.get('classified_images', {})
                self.removed_images = set(state.get('removed_images', []))
                
                # 恢复操作模式状态
                saved_copy_mode = state.get('is_copy_mode', True)  # 默认为复制模式
                self.set_mode(saved_copy_mode)
                
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
                # 确保按钮状态正确（默认单分类模式）
                self.is_multi_category = False
                QTimer.singleShot(10, lambda: self._update_category_mode_button_state())
                
        except Exception as e:
            self.logger.error(f"加载状态失败: {e}")
    
    def _update_category_mode_button_state(self):
        """更新分类模式按钮状态"""
        try:
            if hasattr(self, 'category_mode_button') and self.category_mode_button:
                mode_text = "🔀 多分类模式" if self.is_multi_category else "🔂 单分类模式"
                self.category_mode_button.setText(mode_text)
                self.logger.debug(f"分类模式按钮状态已更新: {mode_text}")
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
    
    @performance_monitor
    def show_current_image(self):
        """显示当前图片 - 防止多图刷新"""
        # 防重入检查，避免多次触发
        if hasattr(self, '_showing_image') and self._showing_image:
            return
            
        self._showing_image = True
        try:
            # 直接调用内部方法，避免额外的事件处理
            self._show_current_image_internal()
            
            # 仅异步更新UI状态，避免阻塞
            QTimer.singleShot(10, lambda: self.schedule_ui_update('ui_state'))
        finally:
            self._showing_image = False
        
    def _show_current_image_internal(self):
        """内部显示当前图片方法 - 优化防止多图刷新"""
        if 0 <= self.current_index < len(self.image_files):
            img_path = str(self.image_files[self.current_index])
            
            # 记录图片文件信息
            self.log_image_info(img_path)
            
            # 立即更新窗口标题和状态信息
            self.update_window_title(img_path)
            
            # 设置当前图片索引用于智能缓存
            self.image_loader.set_current_image_index(self.current_index)
            
            # 检查缓存命中情况
            cache_key = self.image_loader._get_cache_key(img_path)
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
                cached_pixmap = self.image_loader._get_from_cache(cache_key)
                # 安全检查缓存数据类型
                if cached_pixmap is not None:
                    # 检查是否为QPixmap类型
                    from PyQt6.QtGui import QPixmap
                    if isinstance(cached_pixmap, QPixmap) and not cached_pixmap.isNull():
                        self.image_label.set_image(cached_pixmap)
                        self.statusBar.showMessage(f"📷 {Path(img_path).name}")
                    else:
                        # 如果是其他类型数据（如numpy数组），显示占位符等待转换
                        self.show_loading_placeholder(img_path)
                else:
                    self.show_loading_placeholder(img_path)
            else:
                self.show_loading_placeholder(img_path)
            
            # 异步加载完整图片（即使缓存命中也要确保是最新的）
            self.image_loader.load_image(img_path, priority=True)
            
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
    
    def show_loading_placeholder(self, image_path):
        """显示加载占位符"""
        try:
            # 创建简单的加载占位符
            placeholder_size = QSize(400, 300)
            placeholder = QPixmap(placeholder_size)
            placeholder.fill(QColor(240, 240, 240))
            
            # 立即显示占位符
            self.image_label.set_image(placeholder)
            
            # 更新状态栏
            self.statusBar.showMessage(f"🔄 正在加载: {Path(image_path).name}")
            
        except Exception as e:
            self.logger.debug(f"显示加载占位符失败: {e}")
    
    def sync_image_list_selection(self):
        """同步图片列表的选中状态"""
        try:
            # 找到当前图片在列表中的项并选中
            for i in range(self.image_list.count()):
                item = self.image_list.item(i)
                if hasattr(item, 'image_index') and item.image_index == self.current_index:
                    self.image_list.setCurrentItem(item)
                    # 确保当前项可见
                    self.image_list.scrollToItem(item, QAbstractItemView.ScrollHint.EnsureVisible)
                    break
        except Exception as e:
            self.logger.debug(f"同步图片列表选中状态失败: {e}")
    
    def preload_adjacent_images(self):
        """预加载相邻图片"""
        if not self.image_files or self.current_index < 0:
            return
        
        # 计算预加载范围
        preload_range = 5  # 前后各5张图片
        start_idx = max(0, self.current_index - preload_range)
        end_idx = min(len(self.image_files), self.current_index + preload_range + 1)
        
        # 预加载指定范围内的图片
        for i in range(start_idx, end_idx):
            if i != self.current_index:  # 跳过当前图片
                img_path = str(self.image_files[i])
                self.image_loader.load_image(img_path, priority=False)
    
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
    
    def prev_image(self):
        """上一张图片"""
        if self.current_index > 0:
            self.current_index -= 1
            self.show_current_image()
        else:
            # 已经是第一张，显示提示
            self.show_info_message("提示", "已经是第一张图片了！")
    
    def next_image(self):
        """下一张图片"""
        if self.current_index < len(self.image_files) - 1:
            self.current_index += 1
            self.show_current_image()
        else:
            # 已经是最后一张，显示提示
            self.show_info_message("提示", "已经是最后一张图片了！")
    
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
    
    def on_image_list_item_clicked(self, item):
        """处理图片列表项点击"""
        if hasattr(item, 'image_index'):
            self.current_index = item.image_index
            self.show_current_image()
    
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
        """移动当前图片到指定类别 - 支持重新分类和多分类"""
        if not self.image_files or self.current_index < 0:
            return
            
        current_path = str(self.image_files[self.current_index])
        old_category = self.classified_images.get(current_path)
        
        # 检查是否从移除状态恢复
        was_removed = current_path in self.removed_images
        
        # 多分类模式处理 - 当前分类存储为列表
        if self.is_multi_category:
            # 初始化分类列表（如果不存在）
            if not isinstance(old_category, list):
                if old_category:
                    old_categories = [old_category]  # 转换单个类别为列表
                else:
                    old_categories = []
                    
                # 更新存储的类别列表
                self.classified_images[current_path] = old_categories
                old_category = old_categories
                
            # 检查是否已经在这个类别中
            if category_name in old_category:
                # 从列表中移除这个类别（取消分类）
                old_category.remove(category_name)
                self.logger.info(f"多分类模式: 从 {category_name} 中移除 {Path(current_path).name}")
                
                # 在复制模式下，需要删除已复制的文件
                if self.is_copy_mode:
                    self._remove_copied_file_from_category(current_path, category_name)
                
                # 如果列表为空，则完全移除分类记录
                if not old_category:
                    del self.classified_images[current_path]
                    self.logger.info(f"多分类模式: 图片不再属于任何类别")
            else:
                # 添加新类别到列表
                old_category.append(category_name)
                self.logger.info(f"多分类模式: 添加 {Path(current_path).name} 到 {category_name}")
                
                # 在物理文件系统中执行操作
                if was_removed:
                    self._move_from_remove_to_category(current_path, category_name)
                else:
                    # 无论内存状态如何，都检查目标文件是否存在
                    self._execute_file_operation_with_check(current_path, category_name, is_remove=False)
        else:
            # 单分类模式 - 原有逻辑
            # 如果是重新分类，需要从旧目录移动到新目录
            if old_category and old_category != category_name:
                if isinstance(old_category, list):
                    # 从多分类模式切换回单分类模式的情况
                    self.logger.info(f"从多分类切换回单分类: {Path(current_path).name} 设置为 {category_name}")
                    # 对每个旧类别执行清理
                    for old_cat in old_category:
                        if old_cat != category_name:
                            # 这里可以添加清理旧分类的逻辑，如删除多余的副本等
                            pass
                else:
                    self.logger.info(f"重新分类: {Path(current_path).name} 从 {old_category} 到 {category_name}")
                    # 无论复制模式还是移动模式，重新分类都要从旧目录移动到新目录
                    self._move_between_categories(current_path, old_category, category_name)
            elif was_removed:
                # 从移除状态恢复：从remove目录移动到分类目录
                self.logger.info(f"从移除状态恢复: {Path(current_path).name} 恢复到 {category_name}")
                self._move_from_remove_to_category(current_path, category_name)
            else:
                # 首次分类：从原目录复制/移动到分类目录
                # 无论内存状态如何，都检查目标文件是否存在
                self._execute_file_operation_with_check(current_path, category_name, is_remove=False)
            
            # 单分类模式下，直接更新为新类别
            self.classified_images[current_path] = category_name
        
        # 记录此次操作的类别，用于保持选中状态
        self.last_operation_category = category_name
        
        # 如果是从移除状态恢复，清除移除记录
        if was_removed:
            self.removed_images.discard(current_path)
            self.logger.info(f"图片从移除状态恢复: {Path(current_path).name}")
        
        # 立即保存状态到文件
        self.save_state()
        
        # 只更新当前图片在列表中的状态图标，而非全量刷新
        self._update_single_image_status(self.current_index, current_path)
        
        # 异步更新统计信息和类别计数
        QTimer.singleShot(10, lambda: self.schedule_ui_update('category_buttons', 'category_counts', 'statistics'))
        
        # 只在单分类模式下自动移动到下一张图片
        if not self.is_multi_category:
            # 单分类模式下，自动移动到下一张
            self.next_image()
        else:
            # 多分类模式下，保持在当前图片，但刷新UI显示状态
            self.refresh_category_buttons_style()  # 刷新按钮样式，确保多分类状态正确显示
            self.update_category_selection_for_current_image(current_path)
        
        # 根据分类模式和操作类型确定日志信息
        if self.is_multi_category:
            # 多分类模式不使用"重新分类"概念，因为图片可以同时属于多个类别
            current_categories = self.classified_images.get(current_path, [])
            if isinstance(current_categories, list) and category_name in current_categories:
                action = "添加"
            else:
                # 如果类别被移除了，则是"移除"操作
                action = "移除"
        else:
            # 单分类模式使用"重新分类"概念
            action = "重新分类" if old_category else "分类"
        
        self.logger.info(f"图片已{action}到 {category_name}: {Path(current_path).name}")
    
    def _move_between_categories(self, image_path, old_category, new_category):
        """在类别之间移动图片文件，包括从remove目录恢复"""
        try:
            source_file = Path(image_path)
            file_name = source_file.name
            parent_dir = self.current_dir.parent
            
            # 确定旧文件位置（优先检查是否在remove目录）
            if image_path in self.removed_images:
                # 如果图片在移除列表中，则从remove目录查找
                old_dir = parent_dir / 'remove'
                self.logger.debug(f"从removed_images确定旧位置为remove目录: {old_dir}")
            elif old_category == 'remove':
                # 如果明确指定旧类别是remove
                old_dir = parent_dir / 'remove'
            else:
                # 正常的类别间移动
                old_dir = parent_dir / old_category
            old_file = old_dir / file_name
            
            # 确定新文件位置
            new_dir = parent_dir / new_category
            new_dir.mkdir(parents=True, exist_ok=True)
            new_file = new_dir / file_name
            
            # 如果新目标文件已存在，添加编号
            if new_file.exists():
                counter = 1
                name_stem = source_file.stem
                suffix = source_file.suffix
                while new_file.exists():
                    new_name = f"{name_stem}_{counter}{suffix}"
                    new_file = new_dir / new_name
                    counter += 1
            
            # 移动文件（总是移动，不管原模式）
            if old_file.exists():
                import shutil
                shutil.move(str(old_file), str(new_file))
                self.logger.info(f"文件移动成功: {old_file} -> {new_file}")
            else:
                # 如果旧文件不存在，执行正常的文件操作
                self._execute_file_operation(image_path, new_category, is_remove=False)
                
        except Exception as e:
            self.logger.error(f"类别间移动文件失败: {e}")
            # 失败时回退到正常操作
            self._execute_file_operation(image_path, new_category, is_remove=False)
    
    def _update_single_image_status(self, image_index, image_path):
        """更新单个图片在列表中的状态图标"""
        try:
            # 遍历图片列表找到对应的项目
            for i in range(self.image_list.count()):
                item = self.image_list.item(i)
                if hasattr(item, 'image_index') and item.image_index == image_index:
                    # 更新状态
                    is_classified = image_path in self.classified_images
                    is_removed = image_path in self.removed_images
                    
                    # 多分类模式 - 添加标记表示多个分类
                    if is_classified:
                        current_category = self.classified_images.get(image_path)
                        is_multi_classified = isinstance(current_category, list) and len(current_category) > 1
                        if hasattr(item, 'is_multi_classified'):
                            item.is_multi_classified = is_multi_classified
                    
                    # 更新item的状态
                    item.is_classified = is_classified
                    item.is_removed = is_removed
                    
                    # 重新设置状态图标
                    item.set_status_icon()
                    break
        except Exception as e:
            self.logger.debug(f"更新单个图片状态失败: {e}")
    
    def move_to_remove(self):
        """移动图片到remove文件夹 - 支持从分类目录移除"""
        if not self.image_files or self.current_index < 0:
            return
            
        current_path = str(self.image_files[self.current_index])
        old_category = self.classified_images.get(current_path)
        
        # 记录为已移除
        self.removed_images.add(current_path)
        
        # 记录此次操作为移除，清空选中类别保持状态
        self.last_operation_category = None
        
        # 从分类记录中移除
        if current_path in self.classified_images:
            del self.classified_images[current_path]
        
        # 如果图片已分类，需要从分类目录移动到remove目录
        if old_category:
            # 多分类模式 - 图片可能有多个类别
            if isinstance(old_category, list) and old_category:
                # 对于多分类图片，选择第一个类别作为源目录
                self._move_from_category_to_remove(current_path, old_category[0])
                self.logger.info(f"多分类图片已移除: {Path(current_path).name} 从 {old_category[0]} 目录")
            else:
                # 单分类模式
                self._move_from_category_to_remove(current_path, old_category)
        else:
            # 如果图片未分类，直接从原目录移动到remove目录
            self._execute_file_operation(current_path, 'remove', is_remove=True)
        
        # 立即保存状态到文件
        self.save_state()
        
        # 只更新当前图片在列表中的状态图标，而非全量刷新
        self._update_single_image_status(self.current_index, current_path)
        
        # 异步更新统计信息和类别计数
        QTimer.singleShot(10, lambda: self.schedule_ui_update('category_buttons', 'category_counts', 'statistics'))
        
        # 只在单分类模式下自动移动到下一张图片
        if not self.is_multi_category:
            # 单分类模式下，自动移动到下一张
            self.next_image()
        else:
            # 多分类模式下，保持在当前图片，但刷新UI显示状态
            self.update_category_selection_for_current_image(current_path)
        
        self.logger.info(f"图片已移除: {Path(current_path).name}")
    
    def _move_from_category_to_remove(self, image_path, old_category):
        """从分类目录移动图片到remove目录"""
        try:
            source_file = Path(image_path)
            file_name = source_file.name
            parent_dir = self.current_dir.parent
            
            # 确定旧文件位置（分类目录中）
            old_dir = parent_dir / old_category
            old_file = old_dir / file_name
            
            # 确定新文件位置（remove目录）
            remove_dir = parent_dir / 'remove'
            remove_dir.mkdir(parents=True, exist_ok=True)
            remove_file = remove_dir / file_name
            
            # 如果remove目录中已存在同名文件，添加编号
            if remove_file.exists():
                counter = 1
                name_stem = source_file.stem
                suffix = source_file.suffix
                while remove_file.exists():
                    new_name = f"{name_stem}_{counter}{suffix}"
                    remove_file = remove_dir / new_name
                    counter += 1
            
            # 移动文件
            if old_file.exists():
                import shutil
                shutil.move(str(old_file), str(remove_file))
                self.logger.info(f"文件从分类目录移除: {old_file} -> {remove_file}")
            else:
                # 如果旧文件不存在，执行正常的移除操作
                self._execute_file_operation(image_path, 'remove', is_remove=True)
                
        except Exception as e:
            self.logger.error(f"从分类目录移除文件失败: {e}")
            # 失败时回退到正常操作
            self._execute_file_operation(image_path, 'remove', is_remove=True)
    
    def _move_from_remove_to_category(self, image_path, category_name):
        """从remove目录移动图片到分类目录"""
        try:
            source_file = Path(image_path)
            file_name = source_file.name
            parent_dir = self.current_dir.parent
            
            # 确定remove目录中的文件位置
            remove_dir = parent_dir / 'remove'
            remove_file = remove_dir / file_name
            
            # 如果remove目录中没有这个文件，记录警告但继续操作
            if not remove_file.exists():
                self.logger.warning(f"Remove目录中未找到文件: {remove_file}")
                # 仍然从原目录复制到分类目录（兜底方案）
                self._execute_file_operation(image_path, category_name, is_remove=False)
                return
            
            # 确定目标分类目录
            target_dir = parent_dir / category_name
            target_dir.mkdir(parents=True, exist_ok=True)
            target_file = target_dir / file_name
            
            # 如果目标文件已存在，添加编号
            if target_file.exists():
                base_name = source_file.stem
                ext = source_file.suffix
                counter = 1
                while target_file.exists():
                    target_file = target_dir / f"{base_name}_{counter}{ext}"
                    counter += 1
            
            # 执行移动操作（从remove目录移动到分类目录）
            import shutil
            shutil.move(str(remove_file), str(target_file))
            
            self.logger.info(f"文件从remove目录恢复到分类目录: {file_name} -> {category_name}")
            
        except Exception as e:
            self.logger.error(f"从remove目录恢复失败: {e}")
            # 作为备用方案，尝试从原目录复制
            try:
                self._execute_file_operation(image_path, category_name, is_remove=False)
                self.logger.info(f"使用备用方案从原目录复制: {file_name}")
            except Exception as backup_error:
                self.logger.error(f"备用方案也失败: {backup_error}")
                raise FileOperationError(f"文件恢复失败: {e}")
    
    def _execute_file_operation(self, source_path, category_name, is_remove=False):
        """执行实际的文件操作"""
        try:
            source_file = Path(source_path)
            if not source_file.exists():
                self.logger.warning(f"源文件不存在: {source_path}")
                return
            
            # 修复：目标目录统一在图片目录的父目录下创建
            parent_dir = self.current_dir.parent
            if is_remove:
                # 移除操作：在父目录下创建remove文件夹
                target_dir = parent_dir / 'remove'
            else:
                # 分类操作：在父目录下的类别文件夹中
                target_dir = parent_dir / category_name
            
            # 创建目标目录
            target_dir.mkdir(parents=True, exist_ok=True)
            
            # 确定目标文件路径
            target_file = target_dir / source_file.name
            
            # 如果目标文件已存在，添加编号
            if target_file.exists():
                base_name = source_file.stem
                ext = source_file.suffix
                counter = 1
                while target_file.exists():
                    target_file = target_dir / f"{base_name}_{counter}{ext}"
                    counter += 1
            
            # 执行文件操作
            if self.is_copy_mode:
                import shutil
                shutil.copy2(source_file, target_file)
                operation_type = "复制"
            else:
                source_file.rename(target_file)
                operation_type = "移动"
            
            self.logger.info(f"文件{operation_type}成功: {source_file.name} -> {target_file}")
            
        except Exception as e:
            self.logger.error(f"文件操作失败: {e}")
            # 操作失败时回滚状态
            if is_remove:
                self.removed_images.discard(source_path)
            else:
                if source_path in self.classified_images:
                    if isinstance(self.classified_images[source_path], list):
                        # 多分类模式：从列表中移除这个类别
                        if category_name in self.classified_images[source_path]:
                            self.classified_images[source_path].remove(category_name)
                            if not self.classified_images[source_path]:
                                del self.classified_images[source_path]
                    else:
                        # 单分类模式：完全移除记录
                        del self.classified_images[source_path]
            raise FileOperationError(f"文件操作失败: {e}")
    
    def _remove_copied_file_from_category(self, source_path, category_name):
        """从指定类别目录中删除已复制的文件"""
        try:
            source_file = Path(source_path)
            parent_dir = self.current_dir.parent
            category_dir = parent_dir / category_name
            
            # 查找目标文件（可能有编号后缀）
            target_files = []
            base_name = source_file.stem
            ext = source_file.suffix
            
            # 检查原文件名
            original_target = category_dir / source_file.name
            if original_target.exists():
                target_files.append(original_target)
            
            # 检查带编号后缀的文件
            counter = 1
            while True:
                numbered_target = category_dir / f"{base_name}_{counter}{ext}"
                if numbered_target.exists():
                    target_files.append(numbered_target)
                    counter += 1
                else:
                    break
            
            # 删除找到的文件（通常只有一个）
            for target_file in target_files:
                # 简单的验证：检查文件大小是否相同
                if target_file.stat().st_size == source_file.stat().st_size:
                    target_file.unlink()
                    self.logger.info(f"已删除复制的文件: {target_file}")
                    break
            
        except Exception as e:
            self.logger.error(f"删除复制文件失败: {e}")
    
    def _get_file_hash(self, file_path):
        """计算文件的MD5哈希值"""
        import hashlib
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
        
        # 设置统一样式
        msg.setStyleSheet("""
            QMessageBox {
                background-color: #F8F9FA;
                color: #2C3E50;
                border: 1px solid #BDC3C7;
                border-radius: 8px;
                font-size: 14px;
                min-width: 400px;
            }
            QMessageBox QLabel {
                color: #2C3E50;
                font-size: 14px;
                padding: 10px;
            }
            QMessageBox QPushButton {
                background-color: #3498DB;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 13px;
                font-weight: bold;
                min-width: 80px;
                margin: 2px;
            }
            QMessageBox QPushButton:hover {
                background-color: #2980B9;
            }
            QMessageBox QPushButton:pressed {
                background-color: #21618C;
            }
            QMessageBox QPushButton[text="覆盖"] {
                background-color: #E74C3C;
            }
            QMessageBox QPushButton[text="覆盖"]:hover {
                background-color: #C0392B;
            }
            QMessageBox QPushButton[text="重命名"] {
                background-color: #F39C12;
            }
            QMessageBox QPushButton[text="重命名"]:hover {
                background-color: #E67E22;
            }
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

    def _execute_file_operation_with_check(self, source_path, category_name, is_remove=False):
        """执行文件操作前先检查目标文件是否存在，确保重复检测不被绕过"""
        try:
            source_file = Path(source_path)
            if not source_file.exists():
                self.logger.warning(f"源文件不存在: {source_path}")
                return
            
            # 计算目标路径
            parent_dir = self.current_dir.parent
            if is_remove:
                target_dir = parent_dir / 'remove'
            else:
                target_dir = parent_dir / category_name
            
            target_file = target_dir / source_file.name
            
            # 关键：无论内存状态如何，都检查目标文件是否已存在
            if target_file.exists():
                self.logger.info(f"检测到目标文件已存在，触发重复处理: {target_file}")
                # 触发重复文件处理逻辑
                handled_target = self._handle_duplicate_file(source_path, str(target_file))
                if handled_target is None:
                    # 用户选择取消
                    self.logger.info(f"用户取消文件操作: {source_file.name}")
                    return
                # 如果用户选择了重命名，更新目标路径
                target_file = Path(handled_target)
                
                # 如果选择覆盖，需要在执行时直接覆盖
                if str(target_file) == str(target_dir / source_file.name):
                    self.logger.info(f"用户选择覆盖现有文件: {target_file}")
            
            # 执行实际的文件操作
            self._execute_file_operation_direct(source_path, str(target_file), is_remove)
            
        except Exception as e:
            self.logger.error(f"文件操作检查失败: {e}")
            # 回退到原来的逻辑
            self._execute_file_operation(source_path, category_name, is_remove)
    
    def _execute_file_operation_direct(self, source_path, target_path, is_remove=False):
        """直接执行文件操作，不再检查重复"""
        try:
            source_file = Path(source_path)
            target_file = Path(target_path)
            
            # 创建目标目录
            target_file.parent.mkdir(parents=True, exist_ok=True)
            
            # 执行文件操作
            if self.is_copy_mode:
                import shutil
                shutil.copy2(source_file, target_file)
                operation_type = "复制"
            else:
                source_file.rename(target_file)
                operation_type = "移动"
            
            self.logger.info(f"文件{operation_type}成功: {source_file.name} -> {target_file}")
            
        except Exception as e:
            self.logger.error(f"直接文件操作失败: {e}")
            raise

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
                
                # 显示同步结果（只有在有变化时才显示）
                if sync_results['changes_detected']:
                    self._show_sync_results(sync_results)
                else:
                    # 即使没有检测到变化，也要显示刷新完成的信息
                    self.statusBar.showMessage("🔄 目录状态已刷新")
                    
                self.logger.info("目录状态刷新完成")
                
            except Exception as e:
                self.logger.error(f"刷新目录状态失败: {e}")
                self.show_error_message("错误", f"刷新失败: {str(e)}")
    
    def _check_and_fix_shortcuts(self):
        """检查并修复快捷键状态 - 这是解决按键失效的关键方法"""
        try:
            self.logger.debug("开始快捷键健康检查...")
            
            # 检查当前快捷键数量
            current_actions = len(self.actions())
            expected_minimum = 10  # 预期最少应该有10个快捷键
            
            if current_actions < expected_minimum:
                self.logger.warning(f"检测到快捷键数量异常: {current_actions} < {expected_minimum}，正在重新设置")
                self.setup_shortcuts()
            
            # 重新激活快捷键状态
            self._shortcuts_active = True
            
            # 确保窗口有焦点时快捷键可用
            if self.isActiveWindow():
                self.setFocus()
                self.logger.debug("窗口焦点已恢复")
            
            self.logger.debug(f"快捷键健康检查完成 - 当前快捷键数量: {len(self.actions())}")
            
        except Exception as e:
            self.logger.error(f"快捷键健康检查失败: {e}")
            # 作为最后手段，重新设置快捷键
            try:
                self.setup_shortcuts()
            except Exception as setup_error:
                self.logger.error(f"紧急修复快捷键也失败: {setup_error}")
    
    def _periodic_shortcut_check(self):
        """定期检查快捷键状态（每30秒执行一次）"""
        try:
            current_actions = len(self.actions())
            expected_minimum = 8  # 至少应有的基本快捷键数量
            
            if current_actions < expected_minimum:
                self.logger.warning(f"定期检查发现快捷键丢失: {current_actions} < {expected_minimum}")
                self._check_and_fix_shortcuts()
            elif not self._shortcuts_active and self.isActiveWindow():
                # 如果窗口是激活的但快捷键被禁用，重新激活
                self._shortcuts_active = True
                self.logger.debug("定期检查：重新激活快捷键状态")
                
        except Exception as e:
            self.logger.error(f"定期快捷键检查失败: {e}")
    
    def _sync_file_states(self):
        """同步文件状态与实际目录"""
        sync_results = {
            'changes_detected': False,
            'removed_files': [],
            'moved_files': [],
            'new_classifications': [],
            'invalid_classifications': []
        }
        
        try:
            parent_dir = self.current_dir.parent
            
            # 检查已分类图片的状态
            invalid_classifications = []
            for img_path, category in list(self.classified_images.items()):
                img_file = Path(img_path)
                
                # 处理多分类模式（category可能是列表）
                if isinstance(category, list):
                    # 多分类模式：检查每个类别
                    categories_to_remove = []
                    for cat in category:
                        category_dir = parent_dir / cat
                        expected_file = category_dir / img_file.name
                        
                        # 检查文件是否还在预期的分类目录中
                        if not expected_file.exists():
                            categories_to_remove.append(cat)
                            sync_results['moved_files'].append({
                                'file': img_file.name,
                                'from': cat,
                                'to': '已移动或删除'
                            })
                    
                    # 移除不存在的类别
                    if categories_to_remove:
                        for cat in categories_to_remove:
                            category.remove(cat)
                        
                        # 如果所有类别都被移除，则移除整个分类记录
                        if not category:
                            invalid_classifications.append(img_path)
                else:
                    # 单分类模式
                    category_dir = parent_dir / category
                    expected_file = category_dir / img_file.name
                    
                    # 检查文件是否还在预期的分类目录中
                    if not expected_file.exists():
                        # 检查文件是否回到了原目录
                        original_file = self.current_dir / img_file.name
                        if original_file.exists():
                            # 文件被移回原目录
                            invalid_classifications.append(img_path)
                            sync_results['moved_files'].append({
                                'file': img_file.name,
                                'from': category,
                                'to': '原目录'
                            })
                        else:
                            # 文件被删除或移动到其他地方
                            invalid_classifications.append(img_path)
                            sync_results['removed_files'].append({
                                'file': img_file.name,
                                'category': category
                            })
            
            # 移除无效的分类记录
            for img_path in invalid_classifications:
                del self.classified_images[img_path]
                sync_results['invalid_classifications'].append(img_path)
            
            # 检查分类目录中是否有新图片
            for category in self.categories:
                category_dir = parent_dir / category
                if category_dir.exists():
                    for file_path in category_dir.iterdir():
                        if (file_path.is_file() and 
                            file_path.suffix.lower() in ['.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff']):
                            
                            # 查找对应的原图片路径
                            original_path = str(self.current_dir / file_path.name)
                            
                            # 如果这个文件没有分类记录，添加记录
                            if original_path not in self.classified_images:
                                self.classified_images[original_path] = category
                                sync_results['new_classifications'].append({
                                    'file': file_path.name,
                                    'category': category
                                })
            
            # 更新已移除图片状态
            removed_files = []
            for img_path in list(self.removed_images):
                img_file = Path(img_path)
                remove_dir = parent_dir / 'remove'
                expected_file = remove_dir / img_file.name
                
                # 检查文件是否还在remove目录中
                if not expected_file.exists():
                    # 检查文件是否回到了原目录
                    original_file = self.current_dir / img_file.name
                    if original_file.exists():
                        removed_files.append(img_path)
                        sync_results['moved_files'].append({
                            'file': img_file.name,
                            'from': 'remove',
                            'to': '原目录'
                        })
            
            # 移除无效的删除记录
            for img_path in removed_files:
                self.removed_images.discard(img_path)
            
            # 检查是否有变化
            sync_results['changes_detected'] = (
                len(sync_results['removed_files']) > 0 or
                len(sync_results['moved_files']) > 0 or
                len(sync_results['new_classifications']) > 0 or
                len(sync_results['invalid_classifications']) > 0
            )
            
            # 如果有变化，保存状态
            if sync_results['changes_detected']:
                self.save_state()
                
        except Exception as e:
            self.logger.error(f"同步文件状态失败: {e}")
            
        return sync_results
    
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
                self.show_info_message(
                "目录同步完成", 
                "文件状态已同步更新：\n\n" + "\n".join(messages) + 
                "\n\n分类状态和UI已更新。"
            )        
        except Exception as e:
            self.logger.error(f"显示同步结果失败: {e}")
    
    def set_mode(self, is_copy):
        """设置操作模式"""
        # 如果要切换到移动模式，但当前是多分类模式，拒绝切换
        if not is_copy and self.is_multi_category:
            self._create_styled_message_box(
                QMessageBox.Icon.Warning,
                "模式切换",
                "移动模式不支持多分类功能。\n请先切换为单分类模式，然后再切换到移动模式。"
            ).exec()
            # 拒绝切换，保持原来的复制模式
            return
        
        self.is_copy_mode = is_copy
        
        # 更新按钮文本
        mode_text = "📋 复制模式" if is_copy else "✂️ 移动模式"
        self.mode_button.setText(mode_text)
        
        self.logger.info(f"操作模式已切换为: {'复制' if is_copy else '移动'}")
    
    def create_category_mode_button(self, toolbar):
        """创建分类模式切换按钮 - 单分类/多分类"""
        # 创建按钮
        self.category_mode_button = QPushButton()
        self.category_mode_button.setText('🔂 单分类模式')
        self.category_mode_button.setObjectName("category_mode_button")
        self.category_mode_button.setToolTip('点击切换单分类/多分类模式')
        
        # 设置按钮尺寸 - 与其他按钮保持一致的尺寸
        self.category_mode_button.setFixedSize(110, 34)
        
        # 点击事件：切换模式
        self.category_mode_button.clicked.connect(self.toggle_category_mode)
        
        # 设置与其他按钮一致的样式
        self.category_mode_button.setStyleSheet("""
            QPushButton#category_mode_button {
                background-color: #3498DB;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 13px;
                font-weight: bold;
                text-align: center;
                min-width: 90px;
                min-height: 34px;
                max-height: 34px;
            }
            QPushButton#category_mode_button:hover { 
                background-color: #2980B9; 
            }
            QPushButton#category_mode_button:pressed { 
                background-color: #21618C; 
            }
        """)

        # 添加到工具栏
        toolbar.addWidget(self.category_mode_button)
    
    def toggle_category_mode(self):
        """切换单分类/多分类模式"""
        # 移动模式不支持多分类
        if not self.is_copy_mode and not self.is_multi_category:
            self._create_styled_message_box(
                QMessageBox.Icon.Warning,
                "模式限制",
                "移动模式不支持多分类功能。\n请先切换到复制模式。"
            ).exec()
            return
        
        self.is_multi_category = not self.is_multi_category
        
        # 更新按钮文本
        mode_text = "🔀 多分类模式" if self.is_multi_category else "🔂 单分类模式"
        self.category_mode_button.setText(mode_text)
        
        # 显示提示
        mode_desc = "多分类模式（一张图片可以同时属于多个类别）" if self.is_multi_category else "单分类模式（一张图片只能属于一个类别）"
        self.statusBar.showMessage(f"已切换为{mode_desc}")
        
        # 保存分类模式状态
        self.save_state()
        
        self.logger.info(f"分类模式已切换为: {'多分类' if self.is_multi_category else '单分类'}")

    def fit_to_window(self):
        """适应窗口大小"""
        if hasattr(self, 'image_label'):
            self.image_label.fit_to_window()
    
    def add_category(self):
        """添加新类别"""
        if not self.current_dir:
            self.show_warning_message('警告', '请先选择图片目录')
            return
            
        dialog = AddCategoriesDialog(self.categories, self)
        dialog.exec()
    
    # ===== 图像加载器回调方法 =====
    
    def on_image_loaded(self, image_path, image_data):
        """图像加载完成回调 - 只显示当前选中的图片"""
        try:
            # 关键修复：只有当前选中的图片才显示，其他都是预加载缓存
            if self.image_files and 0 <= self.current_index < len(self.image_files):
                current_path = str(self.image_files[self.current_index])
                if current_path != image_path:
                    # 不是当前图片，只是预加载缓存，不显示UI
                    self.logger.debug(f"预加载完成(不显示): {Path(image_path).name}")
                    return
            
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
            import traceback
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
    
    def on_cache_status_updated(self, status):
        """缓存状态更新回调"""
        try:
            # 更新统计面板中的缓存信息
            if hasattr(self, 'statistics_panel'):
                # StatisticsPanel没有update_cache_info方法，暂时跳过
                pass
        except Exception as e:
            self.logger.error(f"更新缓存状态时出错: {e}")
    
    def convert_to_pixmap(self, image_data):
        """将图像数据转换为QPixmap"""
        try:
            from PyQt6.QtGui import QPixmap, QImage
            import numpy as np
            
            if isinstance(image_data, np.ndarray):
                # numpy数组图像数据
                height, width, channel = image_data.shape
                bytes_per_line = 3 * width
                
                # 直接使用numpy数组创建QImage，因为image_loader已经将BGR转为RGB
                # 避免二次颜色通道转换
                q_image = QImage(image_data.data, width, height, bytes_per_line, QImage.Format.Format_RGB888)
                return QPixmap.fromImage(q_image)
                
            elif hasattr(image_data, 'mode'):
                # PIL图像
                if image_data.mode == 'RGB':
                    rgb_array = np.array(image_data)
                    height, width, channel = rgb_array.shape
                    bytes_per_line = 3 * width
                    q_image = QImage(rgb_array.data, width, height, bytes_per_line, QImage.Format.Format_RGB888)
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
    
    def scale_pixmap(self, pixmap):
        """缩放图像以适应显示区域（已废弃，由EnhancedImageLabel处理）"""
        # 这个方法现在由EnhancedImageLabel的set_image方法处理
        return pixmap
    
    def update_image_list_thumbnail(self, image_path, thumbnail_data):
        """更新图片列表中的缩略图"""
        try:
            # 在图片列表中找到对应项并更新缩略图
            for i in range(self.image_list.count()):
                item = self.image_list.item(i)
                if item and item.data(Qt.ItemDataRole.UserRole) == image_path:
                    # 更新项目的图标
                    if hasattr(thumbnail_data, 'copy'):
                        # QPixmap
                        item.setIcon(QIcon(thumbnail_data))
                    else:
                        # 需要转换
                        thumbnail_pixmap = self.convert_to_pixmap(thumbnail_data)
                        if thumbnail_pixmap:
                            item.setIcon(QIcon(thumbnail_pixmap))
                    break
        except Exception as e:
            self.logger.error(f"更新缩略图时出错: {e}")

    def show_help_dialog(self):
        """显示帮助对话框"""
        dialog = TabbedHelpDialog(self.version, self)
        dialog.exec()
    
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

    def keyPressEvent(self, event):
        """处理键盘事件 - 恢复上下键选择类别功能"""
        try:
            # 检查快捷键是否激活
            if not self._shortcuts_active:
                self.logger.debug("快捷键未激活，尝试重新激活")
                self._shortcuts_active = True
                
            key = event.key()
            self.logger.debug(f"键盘按键: {key} ({event.text()}) - 快捷键状态: {'激活' if self._shortcuts_active else '禁用'}")
            
            # 上下键选择类别
            if key == Qt.Key.Key_Up:
                self.logger.debug("检测到上箭头键，选择上一个类别")
                self.select_previous_category()
                event.accept()
                return
            elif key == Qt.Key.Key_Down:
                self.logger.debug("检测到下箭头键，选择下一个类别")
                self.select_next_category()
                event.accept()
                return
            elif key == Qt.Key.Key_Return or key == Qt.Key.Key_Enter:
                self.logger.debug("检测到回车键，确认选择类别")
                # Enter键确认选择当前高亮的类别
                if (hasattr(self, 'current_category_index') and 
                    self.current_category_index >= 0 and 
                    self.current_category_index < len(self.category_buttons)):
                    button = self.category_buttons[self.current_category_index]
                    category = button.category_name
                    self.logger.info(f"通过回车键确认分类到: {category}")
                    self.move_to_category(category)
                    event.accept()
                    return
                else:
                    self.logger.debug(f"无法确认类别: current_category_index={getattr(self, 'current_category_index', 'None')}, 类别按钮数量={len(self.category_buttons) if hasattr(self, 'category_buttons') else 0}")
            
            # 其他键盘快捷键继续传递给父类处理
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
                self.show_warning_message("错误", "当前目录未设置")
                return
                
            old_path = self.current_dir.parent / old_name
            new_path = self.current_dir.parent / new_name
            
            if not old_path.exists():
                self.show_warning_message("错误", f"类别目录不存在: {old_name}")
                return
                
            if new_path.exists():
                self.show_warning_message("错误", f"目标类别已存在: {new_name}")
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
            
            self.show_info_message("成功", f"类别已重命名: {old_name} → {new_name}")
            self.logger.info(f"类别重命名成功: {old_name} → {new_name}")
            
        except Exception as e:
            self.logger.error(f"重命名类别失败: {e}")
            self.show_error_message("错误", f"重命名失败: {str(e)}")
    
    def delete_category(self, category_name):
        """删除类别 - 带二次确认"""
        try:
            if not self.current_dir:
                self.show_warning_message("错误", "当前目录未设置")
                return
                
            category_path = self.current_dir.parent / category_name
            
            if not category_path.exists():
                self.show_warning_message("错误", f"类别目录不存在: {category_name}")
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
            import shutil
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
                self.show_info_message("成功", f"类别已删除: {category_name}\n删除了 {image_count} 张图片文件")
                self.logger.info(f"类别删除成功: {category_name}，删除了 {image_count} 张图片")
            else:
                # 空目录删除成功，不需要弹窗，只记录日志
                self.logger.info(f"空类别删除成功: {category_name}")
            
        except Exception as e:
            self.logger.error(f"删除类别失败: {e}")
            self.show_error_message("错误", f"删除失败: {str(e)}")
    
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
    
    def _async_save_state(self, state_file, state_data):
        """异步执行状态保存"""
        try:
            import json
            with open(state_file, 'w', encoding='utf-8') as f:
                json.dump(state_data, f, ensure_ascii=False, indent=2)
                
            self.logger.debug(f"状态已异步保存到: {state_file}")
                
        except Exception as e:
            self.logger.error(f"异步保存状态失败: {e}")
            # 如果异步保存失败，尝试同步保存作为备份
            try:
                import json
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
        
        # 设置美化样式
        msgBox.setStyleSheet("""
            QMessageBox {
                background-color: #F8F9FA;
                color: #2C3E50;
                border: 1px solid #BDC3C7;
                border-radius: 8px;
                font-size: 14px;
            }
            QMessageBox QLabel {
                color: #2C3E50;
                font-size: 14px;
                padding: 10px;
            }
            QMessageBox QPushButton {
                background-color: #3498DB;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 13px;
                font-weight: bold;
                min-width: 80px;
            }
            QMessageBox QPushButton:hover {
                background-color: #2980B9;
            }
            QMessageBox QPushButton:pressed {
                background-color: #21618C;
            }
            QMessageBox QPushButton:default {
                background-color: #27AE60;
            }
            QMessageBox QPushButton:default:hover {
                background-color: #229954;
            }
        """)
        
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
    
    def show_info_message(self, title, text):
        """显示信息消息框"""
        msgBox = self._create_styled_message_box(QMessageBox.Icon.Information, title, text)
        return msgBox.exec()
    
    def show_warning_message(self, title, text):
        """显示警告消息框"""
        msgBox = self._create_styled_message_box(QMessageBox.Icon.Warning, title, text)
        return msgBox.exec()
    
    def show_error_message(self, title, text):
        """显示错误消息框"""
        msgBox = self._create_styled_message_box(QMessageBox.Icon.Critical, title, text)
        return msgBox.exec()
    
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
