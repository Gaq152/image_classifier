"""
主题颜色和尺寸定义模块

集中管理应用程序的颜色方案、字体、尺寸等主题相关的常量。
支持统一的视觉风格和主题切换功能。
"""


class Colors:
    """颜色方案定义"""

    # 主色调
    PRIMARY = "#3498DB"
    PRIMARY_DARK = "#2980B9"
    PRIMARY_LIGHT = "#5DADE2"

    # 成功色
    SUCCESS = "#27AE60"
    SUCCESS_DARK = "#229954"
    SUCCESS_LIGHT = "#58D68D"

    # 警告色
    WARNING = "#F39C12"
    WARNING_DARK = "#E67E22"
    WARNING_LIGHT = "#F7DC6F"

    # 错误色
    ERROR = "#E74C3C"
    ERROR_DARK = "#C0392B"
    ERROR_LIGHT = "#F1948A"

    # 中性色
    WHITE = "#FFFFFF"
    BLACK = "#000000"

    # 灰色系
    GRAY_50 = "#FAFAFA"
    GRAY_100 = "#F5F5F5"
    GRAY_200 = "#EEEEEE"
    GRAY_300 = "#E0E0E0"
    GRAY_400 = "#BDBDBD"
    GRAY_500 = "#9E9E9E"
    GRAY_600 = "#757575"
    GRAY_700 = "#616161"
    GRAY_800 = "#424242"
    GRAY_900 = "#212121"

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

    def __init__(self):
        self.colors = Colors()
        self.sizes = Sizes()
        self.fonts = Fonts()
        self.shadows = Shadows()
        self.animations = Animations()

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


# 默认主题实例
default_theme = Theme()