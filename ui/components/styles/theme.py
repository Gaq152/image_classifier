"""
主题颜色和尺寸定义模块

集中管理应用程序的颜色方案、字体、尺寸等主题相关的常量。
支持统一的视觉风格和主题切换功能。
"""


class LightColors:
    """亮色主题颜色方案"""

    # 主色调
    PRIMARY = "#2563EB"
    PRIMARY_DARK = "#1D4ED8"
    PRIMARY_LIGHT = "#DBEAFE"

    # 成功色
    SUCCESS = "#16A34A"
    SUCCESS_DARK = "#15803D"
    SUCCESS_LIGHT = "#DCFCE7"

    # 警告色
    WARNING = "#D97706"
    WARNING_DARK = "#B45309"
    WARNING_LIGHT = "#FEF3C7"

    # 错误色
    ERROR = "#DC2626"
    ERROR_DARK = "#B91C1C"
    ERROR_LIGHT = "#FEE2E2"

    # 中性色
    WHITE = "#FFFFFF"
    BLACK = "#000000"

    # 灰色系
    GRAY_50 = "#F8FAFC"
    GRAY_100 = "#F1F5F9"
    GRAY_200 = "#E2E8F0"
    GRAY_300 = "#CBD5E1"
    GRAY_400 = "#94A3B8"
    GRAY_500 = "#64748B"
    GRAY_600 = "#475569"
    GRAY_700 = "#334155"
    GRAY_800 = "#1E293B"
    GRAY_900 = "#0F172A"

    # 背景色
    BACKGROUND_PRIMARY = WHITE
    BACKGROUND_SECONDARY = GRAY_50
    BACKGROUND_CARD = WHITE
    BACKGROUND_HOVER = GRAY_100
    BACKGROUND_PRESSED = GRAY_200

    # 文本色
    TEXT_PRIMARY = GRAY_900
    TEXT_SECONDARY = GRAY_600
    TEXT_DISABLED = GRAY_400
    TEXT_ON_PRIMARY = WHITE
    TEXT_ON_DARK = WHITE

    # 边框色
    BORDER_LIGHT = GRAY_200
    BORDER_MEDIUM = GRAY_300
    BORDER_DARK = GRAY_400

    # 特殊用途颜色
    SHADOW = "rgba(0, 0, 0, 0.1)"
    OVERLAY = "rgba(0, 0, 0, 0.5)"
    HIGHLIGHT = "rgba(52, 152, 219, 0.1)"


class DarkColors:
    """暗色主题颜色方案"""

    # 主色调
    PRIMARY = "#3B82F6"
    PRIMARY_DARK = "#2563EB"
    PRIMARY_LIGHT = "#1E3A8A"

    # 成功色
    SUCCESS = "#22C55E"
    SUCCESS_DARK = "#16A34A"
    SUCCESS_LIGHT = "#14532D"

    # 警告色
    WARNING = "#F59E0B"
    WARNING_DARK = "#D97706"
    WARNING_LIGHT = "#78350F"

    # 错误色
    ERROR = "#EF4444"
    ERROR_DARK = "#DC2626"
    ERROR_LIGHT = "#7F1D1D"

    # 中性色
    WHITE = "#FFFFFF"
    BLACK = "#000000"

    # 灰色系（暗色反转）
    GRAY_50 = "#0F172A"  # 最暗
    GRAY_100 = "#111827"
    GRAY_200 = "#1E293B"
    GRAY_300 = "#334155"
    GRAY_400 = "#475569"
    GRAY_500 = "#64748B"
    GRAY_600 = "#94A3B8"
    GRAY_700 = "#CBD5E1"
    GRAY_800 = "#E2E8F0"
    GRAY_900 = "#F1F5F9"  # 最亮

    # 背景色
    BACKGROUND_PRIMARY = "#0F172A"
    BACKGROUND_SECONDARY = "#111827"
    BACKGROUND_CARD = "#1E293B"
    BACKGROUND_HOVER = "#334155"
    BACKGROUND_PRESSED = "#475569"

    # 文本色
    TEXT_PRIMARY = "#F1F5F9"
    TEXT_SECONDARY = "#CBD5E1"
    TEXT_DISABLED = "#64748B"
    TEXT_ON_PRIMARY = WHITE
    TEXT_ON_DARK = WHITE

    # 边框色
    BORDER_LIGHT = "#334155"
    BORDER_MEDIUM = "#475569"
    BORDER_DARK = "#64748B"

    # 特殊用途颜色
    SHADOW = "rgba(0, 0, 0, 0.3)"
    OVERLAY = "rgba(0, 0, 0, 0.7)"
    HIGHLIGHT = "rgba(66, 165, 245, 0.15)"


# 为了向后兼容，保留Colors类指向LightColors
Colors = LightColors


class Sizes:
    """尺寸定义"""

    # 边框圆角
    RADIUS_SMALL = "4px"
    RADIUS_MEDIUM = "6px"
    RADIUS_LARGE = "8px"
    RADIUS_XLARGE = "12px"

    # 间距
    SPACING_XS = "4px"
    SPACING_SM = "8px"
    SPACING_MD = "12px"
    SPACING_LG = "16px"
    SPACING_XL = "20px"
    SPACING_XXL = "24px"

    # 字体大小
    FONT_XS = "10px"
    FONT_SM = "12px"
    FONT_MD = "13px"
    FONT_LG = "14px"
    FONT_XL = "16px"
    FONT_XXL = "18px"
    FONT_XXXL = "20px"

    # 按钮尺寸
    BUTTON_HEIGHT_SM = "28px"
    BUTTON_HEIGHT_MD = "32px"
    BUTTON_HEIGHT_LG = "36px"
    BUTTON_HEIGHT_XL = "40px"

    # Python 布局使用的逻辑像素值（Qt 会按系统 DPI 自动缩放）
    BUTTON_HEIGHT_COMPACT_PX = 32
    BUTTON_HEIGHT_STANDARD_PX = 36
    BUTTON_HEIGHT_LARGE_PX = 40
    BUTTON_MIN_WIDTH_PX = 88
    DIALOG_MARGIN_PX = 24
    DIALOG_SPACING_PX = 16
    CONTROL_SPACING_PX = 12

    # 边框宽度
    BORDER_THIN = "1px"
    BORDER_MEDIUM = "2px"
    BORDER_THICK = "3px"


class Fonts:
    """字体定义"""

    # 字体族
    FAMILY_DEFAULT = "System UI, Arial, sans-serif"
    FAMILY_MONOSPACE = "Consolas, Monaco, monospace"

    # 字重
    WEIGHT_NORMAL = "normal"
    WEIGHT_MEDIUM = "500"
    WEIGHT_BOLD = "bold"

    # 行高
    LINE_HEIGHT_TIGHT = "1.2"
    LINE_HEIGHT_NORMAL = "1.4"
    LINE_HEIGHT_RELAXED = "1.6"


class Shadows:
    """阴影定义"""

    SMALL = "0 1px 3px rgba(0, 0, 0, 0.1)"
    MEDIUM = "0 2px 6px rgba(0, 0, 0, 0.1)"
    LARGE = "0 4px 12px rgba(0, 0, 0, 0.15)"
    XLARGE = "0 8px 24px rgba(0, 0, 0, 0.2)"


class Animations:
    """动画定义"""

    FAST = "0.15s"
    NORMAL = "0.25s"
    SLOW = "0.35s"

    EASE_OUT = "cubic-bezier(0.25, 0.46, 0.45, 0.94)"
    EASE_IN_OUT = "cubic-bezier(0.4, 0, 0.2, 1)"


class Theme:
    """主题配置类"""

    _instance = None
    _current_theme = "light"  # 默认亮色主题

    def __new__(cls):
        """单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, '_initialized'):
            self.sizes = Sizes()
            self.fonts = Fonts()
            self.shadows = Shadows()
            self.animations = Animations()
            self._update_colors()
            self._initialized = True

    def _update_colors(self):
        """根据当前主题更新颜色"""
        if self._current_theme == "dark":
            self.colors = DarkColors()
        else:
            self.colors = LightColors()

    @property
    def is_dark(self):
        """是否为暗色主题"""
        return self._current_theme == "dark"

    def set_theme(self, theme_name: str):
        """设置主题"""
        if theme_name in ("light", "dark"):
            self._current_theme = theme_name
            self._update_colors()

    def get_current_theme(self):
        """获取当前主题名称"""
        return self._current_theme

    @staticmethod
    def get_rgba_color(hex_color: str, alpha: float = 1.0) -> str:
        """将十六进制颜色转换为rgba格式"""
        hex_color = hex_color.lstrip('#')
        if len(hex_color) == 6:
            r = int(hex_color[0:2], 16)
            g = int(hex_color[2:4], 16)
            b = int(hex_color[4:6], 16)
            return f"rgba({r}, {g}, {b}, {alpha})"
        return hex_color

    @staticmethod
    def create_gradient(color1: str, color2: str, direction: str = "to bottom") -> str:
        """创建渐变色"""
        return f"linear-gradient({direction}, {color1}, {color2})"


# 默认主题实例（单例）
default_theme = Theme()
