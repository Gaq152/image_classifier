"""从 SVG 源文件生成应用使用的 PNG 和多尺寸 Windows ICO。"""

from pathlib import Path

from PIL import Image
from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtSvg import QSvgRenderer


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ASSETS_DIR = PROJECT_ROOT / "assets"
SVG_PATH = ASSETS_DIR / "icon.svg"
PNG_PATH = ASSETS_DIR / "icon.png"
ICO_PATH = ASSETS_DIR / "icon.ico"
ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def render_svg(size: int) -> Image.Image:
    """按指定尺寸渲染 SVG，并返回 RGBA Pillow 图像。"""
    renderer = QSvgRenderer(str(SVG_PATH))
    if not renderer.isValid():
        raise RuntimeError(f"无法读取 SVG 图标: {SVG_PATH}")

    image = QImage(size, size, QImage.Format.Format_RGBA8888)
    image.fill(0)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()

    pixels = image.bits().asstring(image.sizeInBytes())
    return Image.frombytes("RGBA", (size, size), pixels)


def main() -> None:
    """生成预览 PNG 和包含常用 Windows 尺寸的 ICO。"""
    largest = render_svg(256)
    largest.save(PNG_PATH, format="PNG", optimize=True)
    largest.save(ICO_PATH, format="ICO", sizes=[(size, size) for size in ICON_SIZES])

    with Image.open(ICO_PATH) as icon:
        generated_sizes = set(icon.info.get("sizes", []))
    expected_sizes = {(size, size) for size in ICON_SIZES}
    if not expected_sizes.issubset(generated_sizes):
        raise RuntimeError(f"ICO 尺寸不完整: {sorted(generated_sizes)}")

    print(f"已生成 {PNG_PATH.relative_to(PROJECT_ROOT)}")
    print(f"已生成 {ICO_PATH.relative_to(PROJECT_ROOT)}: {sorted(generated_sizes)}")


if __name__ == "__main__":
    main()
