"""信息面板 - 统计信息和提示文本的容器"""
import logging
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt6.QtCore import Qt

from ...components.widgets.statistics_panel import StatisticsPanel
from ...components.styles.theme import default_theme


class InfoPanel(QWidget):
    """信息面板 - 包含统计面板和提示文本

    提供统计信息显示和操作提示
    """

    def __init__(self, parent=None):
        """初始化信息面板

        Args:
            parent: 父窗口
        """
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)

        # UI组件
        self.statistics_panel = None
        self.tips_label = None

        self._init_ui()
        self.apply_theme()  # 初始化时应用主题

    def _init_ui(self):
        """初始化UI"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(6)

        # 统计面板 - 固定高度，不参与拉伸
        self.statistics_panel = StatisticsPanel()
        main_layout.addWidget(self.statistics_panel, 0)

        # 提示文本 - 固定高度
        self.tips_label = QLabel('💡 ↑↓选择类别 | Enter确认 | 双击快速分类 | 滚轮缩放')
        self.tips_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tips_label.setStyleSheet("""
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
        main_layout.addWidget(self.tips_label, 0)

    # ========== Public API ==========

    def update_statistics(self, total: int, classified: int, removed: int, display_count=None):
        """更新统计信息

        Args:
            total: 总图片数
            classified: 已分类数
            removed: 已移除数
            display_count: 显示数量（可选）
        """
        if self.statistics_panel:
            self.statistics_panel.update_statistics(
                total=total,
                classified=classified,
                removed=removed,
                display_count=display_count
            )

    def apply_theme(self):
        """应用主题到面板"""
        c = default_theme.colors

        # 更新提示文本样式
        if self.tips_label:
            self.tips_label.setStyleSheet(f"""
                QLabel {{
                    color: {c.TEXT_SECONDARY};
                    font-size: 11px;
                    padding: 4px 8px;
                    background-color: {c.WARNING_LIGHT if not default_theme.is_dark else c.BACKGROUND_TERTIARY};
                    border: 1px solid {c.WARNING};
                    border-radius: 4px;
                    margin: 2px 0px;
                    max-height: 24px;
                    min-height: 24px;
                    font-weight: 500;
                }}
            """)

        # 更新StatisticsPanel主题
        if self.statistics_panel and hasattr(self.statistics_panel, 'apply_theme'):
            self.statistics_panel.apply_theme()
