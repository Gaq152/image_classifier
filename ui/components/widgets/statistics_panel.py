"""
统计面板组件

显示图像分类统计信息的面板组件，包括进度条和各种状态计数。
"""

import logging
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QGridLayout, QLabel, QProgressBar


class StatisticsPanel(QWidget):
    """分类统计面板"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)
        self.initUI()

        # 立即调用一次统计更新，确保进度条初始样式正确
        self.update_statistics(0, 0, 0)

    def _apply_progress_style(self, chunk_color="stop: 0 #28A745, stop: 1 #20C997"):
        """统一的进度条样式应用方法，确保圆角始终生效"""
        style = f"""
            QProgressBar {{
                border: 1px solid #6C757D;
                border-radius: 10px;
                background-color: #E9ECEF;
                text-align: center;
                font-weight: bold;
                font-size: 12px;
                height: 24px;
                margin: 2px 0px;
            }}
            QProgressBar::chunk {{
                background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 0,
                    {chunk_color});
                border-radius: 8px;
                margin: 0px;
                border: none;
            }}
        """
        self.progress_bar.setStyleSheet(style)

    def initUI(self):
        """初始化简洁的UI - 2x2网格布局"""
        try:
            layout = QVBoxLayout(self)
            layout.setContentsMargins(8, 6, 8, 6)
            layout.setSpacing(4)

            # 简化的标题
            title_label = QLabel("📊 统计")
            title_label.setStyleSheet("""
                QLabel {
                    font-size: 13px;
                    font-weight: bold;
                    color: #1565C0;
                    border-bottom: 2px solid #2196F3;
                    padding: 4px 6px;
                    margin-bottom: 4px;
                }
            """)
            layout.addWidget(title_label)

            # 创建2x2网格布局的统计信息
            stats_grid = QGridLayout()
            stats_grid.setContentsMargins(0, 0, 0, 0)
            stats_grid.setSpacing(3)

            # 创建统计标签
            self.total_label = QLabel("📁 总计: 0")
            self.classified_label = QLabel("✅ 已分类: 0")
            self.removed_label = QLabel("🗑️ 已移出: 0")
            self.remaining_label = QLabel("⏳ 待处理: 0")

            # 紧凑的标签样式
            label_style = """
                QLabel {
                    padding: 4px 6px;
                    margin: 1px;
                    font-size: 11px;
                    border-radius: 3px;
                    background-color: #F8F9FA;
                }
            """

            for label in [self.total_label, self.classified_label, self.removed_label, self.remaining_label]:
                label.setStyleSheet(label_style)

            # 按2x2网格排列统计信息
            stats_grid.addWidget(self.total_label, 0, 0)        # 第1行第1列
            stats_grid.addWidget(self.classified_label, 0, 1)   # 第1行第2列
            stats_grid.addWidget(self.removed_label, 1, 0)      # 第2行第1列
            stats_grid.addWidget(self.remaining_label, 1, 1)    # 第2行第2列

            layout.addLayout(stats_grid)

            # 单一进度条（去掉重复的进度标题和标签）
            self.progress_bar = QProgressBar()
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)
            self.progress_bar.setMinimumHeight(24)
            self.progress_bar.setMaximumHeight(24)
            # 使用统一的样式方法设置进度条样式
            self._apply_progress_style()

            # 立即调用初始化统计更新，确保样式应用
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat("0%")
            layout.addWidget(self.progress_bar)

        except Exception as e:
            self.logger.error(f"初始化统计面板UI失败: {e}")

    def update_statistics(self, total, classified, removed, display_count=None):
        """更新统计信息和进度条"""
        try:
            remaining = total - classified - removed
            processed = classified + removed

            # 更新统计标签
            self.total_label.setText(f"📁 总计: {total}")
            self.classified_label.setText(f"✅ 已分类: {classified}")
            self.removed_label.setText(f"🗑️ 已移出: {removed}")
            self.remaining_label.setText(f"⏳ 待处理: {remaining}")

            if display_count is not None:
                self.total_label.setText(f"📁 总计: {total} (显示: {display_count})")

            # 更新进度条
            if total > 0:
                progress_percentage = int((processed / total) * 100)
                self.progress_bar.setValue(progress_percentage)
                self.progress_bar.setFormat(f"{progress_percentage}%")

                # 根据进度调整颜色
                if progress_percentage >= 100:
                    chunk_color = "stop: 0 #28A745, stop: 1 #20C997"  # 绿色 - 完成
                elif progress_percentage >= 75:
                    chunk_color = "stop: 0 #17A2B8, stop: 1 #20C997"  # 青色 - 接近完成
                elif progress_percentage >= 50:
                    chunk_color = "stop: 0 #FFC107, stop: 1 #FFD700"  # 黄色 - 进行中
                else:
                    chunk_color = "stop: 0 #DC3545, stop: 1 #FF6B6B"  # 红色 - 刚开始

                # 使用统一的样式方法
                self._apply_progress_style(chunk_color)
            else:
                self.progress_bar.setValue(0)
                self.progress_bar.setFormat("0%")
                # 使用统一的样式方法，确保即使在total=0时也应用圆角样式
                self._apply_progress_style("stop: 0 #DC3545, stop: 1 #FF6B6B")

        except Exception as e:
            self.logger.error(f"更新统计信息失败: {e}")