from typing import Dict
from PyQt6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem, QStyle, QApplication
from PyQt6.QtGui import QPainter, QPen, QBrush, QColor, QIcon, QPixmap
from PyQt6.QtCore import Qt, QSize, QRect

from ..models.image_list_model import ImageListModel
from ..components.styles.theme import default_theme

class ImageListDelegate(QStyledItemDelegate):
    """
    高性能列表项代理（紧凑模式）
    负责绘制状态图标和文本
    特点：零 paint 时内存分配，全缓存复用
    Gemini优化：行高44px，图标20px，间距6px
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        # 布局常量（必须在_init_icons()之前定义）
        # Gemini紧凑方案：提高信息密度，状态图标降级为轻量指示器
        self.ICON_SIZE = 20     # 状态图标大小（原36px）
        self.PADDING = 6        # 间距（原8px）

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

        # 绘制阴影（20px画布，线宽调整为1px）
        painter.setPen(QPen(shadow_color, 1))
        painter.setBrush(QBrush(shadow_color, Qt.BrushStyle.SolidPattern))
        painter.drawEllipse(2, 2, 16, 16)

        # 绘制主圆形
        painter.setPen(QPen(color, 1))
        painter.setBrush(QBrush(color, Qt.BrushStyle.SolidPattern))
        painter.drawEllipse(1, 1, 16, 16)

        # 绘制状态符号（线宽2px，确保小尺寸下清晰）
        painter.setPen(QPen(Qt.GlobalColor.white, 2))

        if symbol == "check":
            # 对勾：缩小并居中
            painter.drawLine(5, 9, 8, 12)
            painter.drawLine(8, 12, 14, 6)
        elif symbol == "cross":
            # 叉号：6,6 <-> 13,13
            painter.drawLine(6, 6, 13, 13)
            painter.drawLine(13, 6, 6, 13)
        elif symbol == "multi":
            # 多分类：两个重叠方块
            painter.setPen(QPen(Qt.GlobalColor.white, 1))
            painter.drawRect(5, 5, 7, 7)
            painter.drawRect(8, 8, 7, 7)
        elif symbol == "warning":
            # 警告：感叹号（Codex修正：x=9居中）
            painter.setPen(QPen(Qt.GlobalColor.white, 1))
            painter.drawLine(9, 5, 9, 11)
            painter.drawPoint(9, 13)
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
        text = index.data(Qt.ItemDataRole.DisplayRole) or ""  # 空值兜底

        # 5. 布局计算（紧凑模式：无缩略图）
        rect = opt.rect

        # -- A. 状态图标 (左侧固定，垂直居中) --
        icon_rect = QRect(rect.left() + self.PADDING,
                          rect.top() + (rect.height() - self.ICON_SIZE) // 2,
                          self.ICON_SIZE, self.ICON_SIZE)

        # 从缓存获取图标并绘制
        status_icon = self._icon_cache.get(status_type, self._icon_cache["pending"])
        status_icon.paint(painter, icon_rect, Qt.AlignmentFlag.AlignCenter)

        # -- B. 文本偏移（紧凑模式：直接在图标后） --
        text_offset = self.PADDING + self.ICON_SIZE + self.PADDING

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
        # Gemini紧凑方案：行高44px，提高信息密度
        height = 44

        # Phase 1.1: 计算实际宽度以支持横向滚动（长文件名）
        text = index.data(Qt.ItemDataRole.DisplayRole) or ""

        # 计算文本实际宽度
        font_metrics = option.fontMetrics
        text_width = font_metrics.horizontalAdvance(text)

        # 计算总宽度：左边距 + 状态图标 + 间距 + 文本 + 右边距（无缩略图）
        total_width = (self.PADDING +           # 左边距
                       self.ICON_SIZE +          # 状态图标
                       self.PADDING +            # 图标后间距
                       text_width +              # 文本宽度
                       self.PADDING)             # 右边距

        return QSize(total_width, height)
