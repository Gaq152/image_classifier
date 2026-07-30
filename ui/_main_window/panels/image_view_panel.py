"""图片显示面板 - 负责图片显示区域的布局和交互"""
import logging
from PyQt6.QtCore import QEvent, QTimer, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ...components.widgets.enhanced_image_label import EnhancedImageLabel
from ...components.styles.theme import default_theme
from ...components.dialog_utils import style_icon_button


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
        self.prediction_loading_overlay = None
        self.prediction_loading_icon = None
        self.prediction_loading_text = None
        self.prediction_result_card = None
        self.prediction_result_title = None
        self.prediction_result_detail = None
        self._prediction_result_tone = "ready"
        self._prediction_spinner_index = 0
        self._prediction_spinner_frames = ("◐", "◓", "◑", "◒")
        self._prediction_animation_timer = QTimer(self)
        self._prediction_animation_timer.setInterval(90)
        self._prediction_animation_timer.timeout.connect(
            self._advance_prediction_animation
        )

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

        self.image_label = EnhancedImageLabel()
        self.image_scroll_area.setWidget(self.image_label)
        self._create_prediction_overlays()

        main_layout.addWidget(self.image_scroll_area, 1)  # 主要拉伸权重

    def _create_prediction_overlays(self):
        """创建覆盖在图片预览上的推理动画和预测结果卡片。"""
        viewport = self.image_scroll_area.viewport()
        viewport.installEventFilter(self)

        self.prediction_loading_overlay = QFrame(viewport)
        self.prediction_loading_overlay.setObjectName("ai_prediction_loading")
        loading_layout = QVBoxLayout(self.prediction_loading_overlay)
        loading_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        loading_layout.setSpacing(10)

        self.prediction_loading_icon = QLabel(self._prediction_spinner_frames[0])
        self.prediction_loading_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.prediction_loading_text = QLabel("模型正在分析当前图片…")
        self.prediction_loading_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        loading_layout.addWidget(self.prediction_loading_icon)
        loading_layout.addWidget(self.prediction_loading_text)
        self.prediction_loading_overlay.hide()

        self.prediction_result_card = QFrame(viewport)
        self.prediction_result_card.setObjectName("ai_prediction_result")
        self.prediction_result_card.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        result_layout = QVBoxLayout(self.prediction_result_card)
        result_layout.setContentsMargins(16, 10, 16, 10)
        result_layout.setSpacing(3)
        self.prediction_result_title = QLabel()
        self.prediction_result_title.setObjectName("ai_prediction_result_title")
        self.prediction_result_detail = QLabel()
        self.prediction_result_detail.setObjectName("ai_prediction_result_detail")
        self.prediction_result_detail.setWordWrap(True)
        result_layout.addWidget(self.prediction_result_title)
        result_layout.addWidget(self.prediction_result_detail)
        self.prediction_result_card.hide()
        self._position_prediction_overlays()

    def _create_header(self, layout):
        """创建标题栏"""
        title_container = QWidget()
        title_container.setObjectName("title_container")
        title_container.setFixedHeight(40)
        title_layout = QHBoxLayout(title_container)
        title_layout.setContentsMargins(6, 4, 6, 4)
        title_layout.setSpacing(8)

        # 标题
        self.title_label = QLabel("🖼️ 图片预览")
        title_layout.addWidget(self.title_label)
        title_layout.addStretch()

        # 移除按钮
        self.delete_button = self._create_toolbar_button(
            '🗑', 'remove_button',
            '移除当前图片到移除目录',
            self._on_remove_clicked,
            size=(32, 32)
        )
        style_icon_button(self.delete_button, "danger")
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

    def show_prediction_loading(self, text: str = "模型正在分析当前图片…") -> None:
        """显示推理动画；覆盖层会拦截预览区鼠标操作。"""
        if not self.prediction_loading_overlay:
            return
        self.prediction_result_card.hide()
        self.prediction_loading_text.setText(text)
        self._prediction_spinner_index = 0
        self.prediction_loading_icon.setText(self._prediction_spinner_frames[0])
        self._position_prediction_overlays()
        self.prediction_loading_overlay.show()
        self.prediction_loading_overlay.raise_()
        self._prediction_animation_timer.start()

    def hide_prediction_loading(self) -> None:
        """结束推理动画。"""
        self._prediction_animation_timer.stop()
        if self.prediction_loading_overlay:
            self.prediction_loading_overlay.hide()

    def show_prediction_result(
        self,
        title: str,
        detail: str,
        alternatives: list[str],
        tone: str = "ready",
    ) -> None:
        """在图片预览区底部显示模型建议。"""
        if not self.prediction_result_card:
            return
        self.hide_prediction_loading()
        self._prediction_result_tone = tone
        self.prediction_result_title.setText(title)
        self.prediction_result_detail.setText(detail)
        tooltip = "\n".join(alternatives)
        self.prediction_result_card.setToolTip(tooltip)
        self._apply_prediction_overlay_theme()
        self._position_prediction_overlays()
        self.prediction_result_card.show()
        self.prediction_result_card.raise_()

    def clear_prediction_overlay(self) -> None:
        """切换图片或模式时清除旧的预测展示。"""
        self.hide_prediction_loading()
        if self.prediction_result_card:
            self.prediction_result_card.hide()

    @property
    def prediction_loading(self) -> bool:
        return bool(
            self.prediction_loading_overlay
            and self.prediction_loading_overlay.isVisible()
        )

    def _advance_prediction_animation(self) -> None:
        self._prediction_spinner_index = (
            self._prediction_spinner_index + 1
        ) % len(self._prediction_spinner_frames)
        self.prediction_loading_icon.setText(
            self._prediction_spinner_frames[self._prediction_spinner_index]
        )

    def _position_prediction_overlays(self) -> None:
        if not self.image_scroll_area:
            return
        viewport = self.image_scroll_area.viewport()
        if self.prediction_loading_overlay:
            self.prediction_loading_overlay.setGeometry(viewport.rect())
        if self.prediction_result_card:
            available_width = max(220, viewport.width() - 32)
            card_width = min(520, available_width)
            self.prediction_result_card.setFixedWidth(card_width)
            self.prediction_result_card.adjustSize()
            x = max(16, (viewport.width() - card_width) // 2)
            y = max(16, viewport.height() - self.prediction_result_card.height() - 20)
            self.prediction_result_card.move(x, y)

    def eventFilter(self, watched, event):
        if (
            self.image_scroll_area
            and watched is self.image_scroll_area.viewport()
            and event.type() == QEvent.Type.Resize
        ):
            QTimer.singleShot(0, self._position_prediction_overlays)
        return super().eventFilter(watched, event)

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
                }}
            """)

        # 更新标题标签
        if self.title_label:
            self.title_label.setStyleSheet(f"""
                QLabel {{
                    font-size: 14px;
                    font-weight: bold;
                    color: {c.PRIMARY};
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

        if self.delete_button:
            style_icon_button(self.delete_button, "danger")

        # 更新EnhancedImageLabel背景
        if self.image_label and hasattr(self.image_label, 'apply_theme'):
            self.image_label.apply_theme()

        self._apply_prediction_overlay_theme()

    def _apply_prediction_overlay_theme(self):
        """让预测覆盖层跟随应用主题。"""
        c = default_theme.colors
        if self.prediction_loading_overlay:
            self.prediction_loading_overlay.setStyleSheet("""
                QFrame#ai_prediction_loading {
                    background-color: rgba(15, 23, 42, 178);
                    border: none;
                }
            """)
            self.prediction_loading_icon.setStyleSheet("""
                QLabel {
                    color: white;
                    background: transparent;
                    border: none;
                    font-size: 36px;
                    font-weight: 600;
                }
            """)
            self.prediction_loading_text.setStyleSheet("""
                QLabel {
                    color: white;
                    background: transparent;
                    border: none;
                    font-size: 14px;
                    font-weight: 600;
                }
            """)

        if not self.prediction_result_card:
            return
        tones = {
            "ready": (c.SUCCESS_LIGHT, c.SUCCESS),
            "warning": (c.WARNING_LIGHT, c.WARNING),
            "error": (c.ERROR_LIGHT, c.ERROR),
        }
        background, border = tones.get(
            self._prediction_result_tone, tones["ready"]
        )
        self.prediction_result_card.setStyleSheet(f"""
            QFrame#ai_prediction_result {{
                background-color: {background};
                border: 2px solid {border};
                border-radius: 10px;
            }}
        """)
        self.prediction_result_title.setStyleSheet(f"""
            QLabel {{
                color: {c.TEXT_PRIMARY};
                border: none;
                background: transparent;
                font-size: 15px;
                font-weight: 700;
            }}
        """)
        self.prediction_result_detail.setStyleSheet(f"""
            QLabel {{
                color: {c.TEXT_SECONDARY};
                border: none;
                background: transparent;
                font-size: 12px;
            }}
        """)
