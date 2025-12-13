"""图片显示面板 - 负责图片显示区域的布局和交互"""
import logging
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QLabel, QPushButton
from PyQt6.QtCore import pyqtSignal, Qt

from ...components.widgets.enhanced_image_label import EnhancedImageLabel
from ...components.styles.theme import default_theme


class ImageViewPanel(QWidget):
    """图片显示面板 - 管理左侧图片显示区域

    信号：
        remove_requested: 用户点击移除按钮
    """

    # 信号定义
    remove_requested = pyqtSignal()

    def __init__(self, parent=None):
        """初始化图片显示面板

        Args:
            parent: 父窗口
        """
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)

        # UI组件
        self.image_scroll_area = None
        self.image_label = None
        self.delete_button = None
        self.title_label = None

        self._init_ui()
        self.apply_theme()  # 初始化时应用主题

    def _init_ui(self):
        """初始化UI"""
        # 设置面板对象名用于样式
        self.setObjectName("left_panel")

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(0)

        # 创建标题栏
        self._create_header(main_layout)

        # 创建图片显示区域
        self.image_scroll_area = QScrollArea()
        self.image_scroll_area.setObjectName("image_preview_container")
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

        main_layout.addWidget(self.image_scroll_area, 1)  # 主要拉伸权重

    def _create_header(self, layout):
        """创建标题栏"""
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

        # 标题
        self.title_label = QLabel("🖼️ 图片预览")
        self.title_label.setStyleSheet("""
            QLabel {
                font-size: 14px;
                font-weight: bold;
                color: #495057;
                border: none;
            }
        """)
        title_layout.addWidget(self.title_label)
        title_layout.addStretch()

        # 移除按钮
        self.delete_button = self._create_toolbar_button(
            '🗑', 'remove_button',
            '移除当前图片到移除目录',
            self._on_remove_clicked,
            size=(24, 24)
        )
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

        layout.addWidget(title_container, 0)  # 不拉伸

    def _create_toolbar_button(self, text: str, object_name: str, tooltip: str,
                               click_handler=None, size=(40, 40)) -> QPushButton:
        """创建工具栏按钮"""
        btn = QPushButton(text)
        btn.setObjectName(object_name)
        btn.setFixedSize(*size)
        btn.setToolTip(tooltip)
        if click_handler:
            btn.clicked.connect(click_handler)
        return btn

    # ========== Public API ==========

    def get_image_label(self):
        """获取EnhancedImageLabel实例（供主窗口访问）"""
        return self.image_label

    def set_image(self, pixmap):
        """显示图片"""
        if self.image_label:
            self.image_label.set_image(pixmap)

    # ========== Internal Logic ==========

    def _on_remove_clicked(self):
        """处理移除按钮点击"""
        self.remove_requested.emit()

    def apply_theme(self):
        """应用主题到面板"""
        c = default_theme.colors

        # 更新面板背景
        self.setStyleSheet(f"""
            QWidget#left_panel {{
                background-color: {c.BACKGROUND_PRIMARY};
                border: 1px solid {c.BORDER_MEDIUM};
                border-radius: 6px;
            }}
        """)

        # 更新标题容器
        title_container = self.findChild(QWidget, "title_container")
        if title_container:
            title_container.setStyleSheet(f"""
                QWidget#title_container {{
                    border-bottom: 1px solid {c.BORDER_MEDIUM};
                    max-height: 28px;
                    min-height: 28px;
                }}
            """)

        # 更新标题标签
        if self.title_label:
            self.title_label.setStyleSheet(f"""
                QLabel {{
                    font-size: 14px;
                    font-weight: bold;
                    color: {c.TEXT_SECONDARY};
                    border: none;
                }}
            """)

        # 更新滚动区域
        if self.image_scroll_area:
            self.image_scroll_area.setStyleSheet(f"""
                QScrollArea {{
                    border: 1px solid {c.BORDER_MEDIUM};
                    border-radius: 4px;
                    background-color: {c.BACKGROUND_SECONDARY};
                }}
            """)

        # 更新移除按钮（保持红色主题）
        if self.delete_button:
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
        if self.image_label and hasattr(self.image_label, 'apply_theme'):
            self.image_label.apply_theme()
