from typing import Dict
from PyQt6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem, QStyle, QApplication
from PyQt6.QtGui import QPainter, QPen, QBrush, QColor, QIcon, QPixmap
from PyQt6.QtCore import Qt, QSize, QRect

from ..models.image_list_model import ImageListModel
from ..components.styles.theme import default_theme

class ImageListDelegate(QStyledItemDelegate):
    """
    高性能列表项代理
    负责绘制状态图标、缩略图和文本
    特点：零 paint 时内存分配，全缓存复用
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        # 布局常量（必须在_init_icons()之前定义）
        self.ICON_SIZE = 36     # 状态图标大小
        self.THUMB_SIZE = 48    # 缩略图大小
        self.PADDING = 8        # 间距

        # 预生成图标缓存 { status_type: QIcon }
        self._icon_cache: Dict[str, QIcon] = {}
        self._init_icons()

    def _init_icons(self):
        """预生成所有状态的图标，避免在 paint 中重复创建"""
        self._icon_cache["classified"] = self._create_status_icon(
            "#4CAF50", "#2E7D32", "check"   # 绿色
        )
        self._icon_cache["removed"] = self._create_status_icon(
            "#F44336", "#C62828", "cross"   # 红色
        )
        self._icon_cache["multi"] = self._create_status_icon(
            "#2196F3", "#1565C0", "multi"   # 蓝色
        )
        self._icon_cache["warning"] = self._create_status_icon(
            "#FFC107", "#F57C00", "warning" # 黄色（保留备用）
        )
        self._icon_cache["pending"] = self._create_status_icon(
            "#FF9800", "#F57C00", "warning" # 橙色（与旧版一致）
        )

    def _create_status_icon(self, color_str: str, shadow_str: str, symbol: str) -> QIcon:
        """
        绘制矢量图标并缓存为QIcon
        """
        size = self.ICON_SIZE
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        color = QColor(color_str)
        shadow_color = QColor(shadow_str)

        # 绘制阴影
        painter.setPen(QPen(shadow_color, 2))
        painter.setBrush(QBrush(shadow_color, Qt.BrushStyle.SolidPattern))
        painter.drawEllipse(3, 3, 28, 28)

        # 绘制主圆形
        painter.setPen(QPen(color, 2))
        painter.setBrush(QBrush(color, Qt.BrushStyle.SolidPattern))
        painter.drawEllipse(2, 2, 28, 28)

        # 绘制状态符号
        painter.setPen(QPen(Qt.GlobalColor.white, 3))

        if symbol == "check":
            painter.drawLine(8, 16, 14, 22)
            painter.drawLine(14, 22, 26, 10)
        elif symbol == "cross":
            painter.drawLine(10, 10, 24, 24)
            painter.drawLine(24, 10, 10, 24)
        elif symbol == "multi":
            painter.setPen(QPen(Qt.GlobalColor.white, 2))
            painter.drawRect(8, 8, 14, 14)
            painter.drawRect(14, 14, 14, 14)
        elif symbol == "warning":
            painter.setPen(QPen(Qt.GlobalColor.white, 2))
            painter.drawLine(16, 8, 16, 18)
            painter.drawEllipse(14, 22, 4, 4)
        # "none" 绘制空圆点或不做额外绘制

        painter.end()
        return QIcon(pixmap)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        """
        自定义绘制方法
        """
        if not index.isValid():
            return

        # 1. 初始化样式选项（Qt最佳实践）
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)

        # 2. 保存 Painter 状态
        painter.save()

        # 3. 绘制背景 (处理选中/悬停状态)
        # 使用 Style 绘制标准列表背景，保持与系统主题一致
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawPrimitive(QStyle.PrimitiveElement.PE_PanelItemViewItem, opt, painter, opt.widget)

        # 4. 获取数据 (从 Model 快速获取)
        status_type = index.data(ImageListModel.ROLE_STATUS_TYPE)
        thumbnail = index.data(Qt.ItemDataRole.DecorationRole)
        text = index.data(Qt.ItemDataRole.DisplayRole) or ""  # 空值兜底

        # 5. 布局计算
        rect = opt.rect

        # -- A. 状态图标 (左侧固定) --
        # 垂直居中
        icon_rect = QRect(rect.left() + self.PADDING,
                          rect.top() + (rect.height() - self.ICON_SIZE) // 2,
                          self.ICON_SIZE, self.ICON_SIZE)

        # 从缓存获取图标并绘制
        status_icon = self._icon_cache.get(status_type, self._icon_cache["pending"])
        status_icon.paint(painter, icon_rect, Qt.AlignmentFlag.AlignCenter)

        # -- B. 缩略图 (可选，状态图标右侧) --
        text_offset = self.PADDING + self.ICON_SIZE + self.PADDING

        if thumbnail and isinstance(thumbnail, QIcon):
             # 如果有缩略图，绘制在状态图标右侧
            thumb_rect = QRect(rect.left() + text_offset,
                               rect.top() + (rect.height() - self.THUMB_SIZE) // 2,
                               self.THUMB_SIZE, self.THUMB_SIZE)
            # 保持纵横比绘制
            thumbnail.paint(painter, thumb_rect, Qt.AlignmentFlag.AlignCenter)
            text_offset += self.THUMB_SIZE + self.PADDING

        # -- C. 文本 (剩余区域) --
        text_rect = QRect(rect.left() + text_offset, rect.top(),
                          rect.width() - text_offset - self.PADDING, rect.height())

        # 设置文本颜色 (选中时为白色，否则使用主题文本色)
        # Phase 1.1: 从主题系统获取颜色，确保暗主题下文字可见
        if opt.state & QStyle.StateFlag.State_Selected:
            painter.setPen(QColor("white"))
        else:
            painter.setPen(QColor(default_theme.colors.TEXT_PRIMARY))

        # 垂直居中绘制文本，超出部分自动省略号
        painter.drawText(text_rect,
                         Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                         text)

        painter.restore()

    def sizeHint(self, option, index):
        """返回 Item 建议大小"""
        # 固定高度 60px，确保能容纳 48px 缩略图和适当的 Padding
        height = 60

        # Phase 1.1: 计算实际宽度以支持横向滚动（长文件名）
        # 获取文本内容
        text = index.data(Qt.ItemDataRole.DisplayRole) or ""

        # 计算文本实际宽度
        font_metrics = option.fontMetrics
        text_width = font_metrics.horizontalAdvance(text)

        # 计算总宽度：左边距 + 状态图标 + 间距 + 缩略图 + 间距 + 文本 + 右边距
        # 检查是否有缩略图
        has_thumbnail = index.data(Qt.ItemDataRole.DecorationRole) is not None
        thumb_width = self.THUMB_SIZE if has_thumbnail else 0
        thumb_padding = self.PADDING if has_thumbnail else 0

        total_width = (self.PADDING +           # 左边距
                       self.ICON_SIZE +          # 状态图标
                       self.PADDING +            # 图标后间距
                       thumb_width +             # 缩略图宽度
                       thumb_padding +           # 缩略图后间距
                       text_width +              # 文本宽度
                       self.PADDING)             # 右边距

        return QSize(total_width, height)
