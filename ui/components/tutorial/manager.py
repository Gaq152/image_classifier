"""
教程管理器

协调整个教程流程，管理步骤导航、遮罩层和提示气泡的显示。
"""

import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import QTimer

from .overlay import TutorialOverlay
from .bubble import TutorialBubble, ArrowPosition
from utils.app_config import get_app_config


@dataclass
class TutorialStep:
    """教程步骤数据类"""
    title: str  # 步骤标题
    content: str  # 步骤说明文本
    target_widget_name: str  # 目标控件的对象名称（用于定位气泡）
    arrow_position: ArrowPosition  # 箭头位置
    highlight_padding: int = 8  # 高亮区域内边距
    offset_x: int = 0  # 气泡X轴偏移
    offset_y: int = 0  # 气泡Y轴偏移
    highlight_widget_names: Optional[List[str]] = None  # 需要高亮的控件列表，默认为None则使用target_widget_name


class TutorialManager:
    """教程管理器

    管理整个教程流程，包括步骤定义、导航控制、UI协调等。
    """

    def __init__(self, main_window: QWidget):
        """初始化教程管理器

        Args:
            main_window: 主窗口实例
        """
        self.logger = logging.getLogger(__name__)
        self.main_window = main_window
        self.app_config = get_app_config()

        # 创建UI组件
        self.overlay = TutorialOverlay(main_window)
        self.bubble = TutorialBubble(main_window)

        # 教程状态
        self.current_step_index = 0
        self.is_active = False

        # 定义教程步骤
        self.steps = self._define_tutorial_steps()

        # 连接信号
        self._connect_signals()

        self.logger.info("教程管理器初始化完成")

    def _define_tutorial_steps(self) -> List[TutorialStep]:
        """定义教程步骤

        Returns:
            教程步骤列表
        """
        return [
            TutorialStep(
                title="欢迎使用图像分类工具",
                content='欢迎使用图像分类工具！\n\n让我们通过快速教程了解基本操作。\n\n点击「下一步」继续，或点击「跳过教程」直接开始使用。',
                target_widget_name="toolbar",
                arrow_position=ArrowPosition.TOP,
                offset_y=20
            ),
            TutorialStep(
                title="图片列表",
                content='点击工具栏的「打开文件夹」后，扫描的图片会显示在这个列表中。\n\n你可以点击图片进行预览和分类操作。',
                target_widget_name="image_list",
                arrow_position=ArrowPosition.RIGHT,  # 改为RIGHT，气泡在左侧
                offset_x=-20  # 向左偏移
            ),
            TutorialStep(
                title="图片预览",
                content='选中的图片会在左侧预览区域显示。\n\n你可以使用鼠标滚轮缩放图片，拖动查看细节。',
                target_widget_name="image_preview_container",
                arrow_position=ArrowPosition.LEFT,
                offset_x=20
            ),
            TutorialStep(
                title="分类区域",
                content='点击工具栏的「添加类别」可以创建新的分类目录。\n\n创建的类别会显示在这里。你可以为每个类别设置快捷键，方便快速分类。',
                target_widget_name="category_list",
                arrow_position=ArrowPosition.RIGHT,  # 改为RIGHT，气泡在左侧
                offset_x=-20  # 向左偏移
            ),
            TutorialStep(
                title="操作模式",
                content='这里可以切换复制/移动模式和分类模式：\n\n• 复制/移动模式：保留原文件或移动文件\n• 单/多分类模式：一张图片分配到一个或多个类别',
                target_widget_name="mode_button",
                arrow_position=ArrowPosition.TOP,  # 箭头在顶部，气泡在下方
                highlight_padding=12,
                offset_y=20,  # 向下偏移，避免遮挡
                highlight_widget_names=["mode_button", "category_mode_button"]  # 同时高亮两个按钮
            ),
            TutorialStep(
                title="快捷键导航",
                content='使用键盘快捷键可以大幅提升效率：\n\n• ← → 切换图片\n• 1-9, A-Z 快速分类\n• Delete 移除图片\n• F5 刷新目录',
                target_widget_name="central_widget",  # 改为中央控件，覆盖整个窗口
                arrow_position=ArrowPosition.TOP,
                offset_y=100  # 向下偏移，显示在中间区域
            ),
            TutorialStep(
                title="完成教程",
                content='教程完成！\n\n现在你可以开始使用图像分类工具了。\n\n如需再次查看教程，可以在「帮助」对话框中点击「重新开始教程」按钮。',
                target_widget_name="toolbar",
                arrow_position=ArrowPosition.TOP,
                offset_y=20
            )
        ]

    def _connect_signals(self):
        """连接信号槽"""
        self.bubble.next_clicked.connect(self.next_step)
        self.bubble.prev_clicked.connect(self.prev_step)
        self.bubble.skip_clicked.connect(self.skip_tutorial)
        self.bubble.finish_clicked.connect(self.finish_tutorial)
        self.overlay.overlay_clicked.connect(self.next_step)  # 点击遮罩也前进

    def should_show_tutorial(self) -> bool:
        """检查是否应该显示教程

        Returns:
            是否应该显示教程
        """
        return self.app_config.should_show_tutorial()

    def start_tutorial(self):
        """开始教程"""
        if self.is_active:
            self.logger.warning("教程已在运行中")
            return

        self.logger.info("开始教程")
        self.is_active = True
        self.current_step_index = 0

        # 延迟显示，确保主窗口已完全初始化
        QTimer.singleShot(500, self._show_current_step)

    def _show_current_step(self):
        """显示当前步骤"""
        if not self.is_active or self.current_step_index >= len(self.steps):
            return

        step = self.steps[self.current_step_index]
        self.logger.info(f"显示教程步骤 {self.current_step_index + 1}/{len(self.steps)}: {step.title}")

        # 查找目标控件
        target_widget = self._find_widget_by_name(step.target_widget_name)
        if target_widget is None:  # 使用 is None 而不是 not，避免空QListWidget被判断为False
            self.logger.error(f"未找到目标控件: {step.target_widget_name}")
            self.next_step()  # 跳过此步骤
            return

        # 确保目标控件可见
        if hasattr(target_widget, 'isVisible') and not target_widget.isVisible():
            self.logger.warning(f"目标控件不可见: {step.target_widget_name}")
            self.next_step()  # 跳过此步骤
            return

        try:
            # 显示遮罩层并高亮目标
            self.logger.debug(f"开始显示遮罩层，目标控件: {target_widget}")

            # 判断是否需要高亮多个控件
            if step.highlight_widget_names:
                # 查找所有需要高亮的控件
                highlight_widgets = []
                for widget_name in step.highlight_widget_names:
                    widget = self._find_widget_by_name(widget_name)
                    if widget is not None:
                        highlight_widgets.append(widget)
                        self.logger.debug(f"添加高亮控件: {widget_name}")
                    else:
                        self.logger.warning(f"未找到高亮控件: {widget_name}")

                if highlight_widgets:
                    self.overlay.highlight_widgets(highlight_widgets, step.highlight_padding)
                else:
                    self.logger.error("没有找到任何需要高亮的控件")
                    self.next_step()
                    return
            else:
                # 只高亮一个控件
                self.overlay.highlight_widget(target_widget, step.highlight_padding)

            self.overlay.show_overlay()
            self.logger.debug("遮罩层显示完成")

            # 设置气泡内容
            self.logger.debug("开始设置气泡内容")
            self.bubble.set_content(f"<h3>{step.title}</h3><p>{step.content}</p>")
            self.bubble.set_arrow_position(step.arrow_position)
            self.bubble.set_step_info(self.current_step_index + 1, len(self.steps))
            self.logger.debug("气泡内容设置完成")

            # 显示气泡
            self.logger.debug(f"开始显示气泡，offset_x={step.offset_x}, offset_y={step.offset_y}")
            self.logger.debug(f"目标控件geometry: {target_widget.geometry()}")
            self.logger.debug(f"目标控件size: {target_widget.size()}")
            self.bubble.show_at(target_widget, step.offset_x, step.offset_y)

            # 确保气泡在遮罩层之上
            self.bubble.raise_()

            # 告诉overlay bubble的位置，避免拦截bubble的点击
            from PyQt6.QtCore import QRect
            bubble_rect = QRect(self.bubble.x(), self.bubble.y(), self.bubble.width(), self.bubble.height())
            self.overlay.set_bubble_region(bubble_rect)

            self.logger.debug(f"气泡显示完成，位置: ({self.bubble.x()}, {self.bubble.y()}), 大小: ({self.bubble.width()}, {self.bubble.height()}), 可见: {self.bubble.isVisible()}")
        except Exception as e:
            self.logger.error(f"显示教程步骤时出错: {e}", exc_info=True)
            self.next_step()  # 出错则跳过此步骤

    def next_step(self):
        """前进到下一步"""
        if not self.is_active:
            return

        self.current_step_index += 1

        if self.current_step_index >= len(self.steps):
            # 教程结束
            self.finish_tutorial()
        else:
            # 显示下一步
            self._show_current_step()

    def prev_step(self):
        """返回上一步"""
        if not self.is_active or self.current_step_index <= 0:
            return

        self.current_step_index -= 1
        self._show_current_step()

    def skip_tutorial(self):
        """跳过教程"""
        self.logger.info("用户跳过教程")
        self._end_tutorial(completed=False)

    def finish_tutorial(self):
        """完成教程"""
        self.logger.info("用户完成教程")
        self._end_tutorial(completed=True)

    def _end_tutorial(self, completed: bool):
        """结束教程

        Args:
            completed: 是否完成（True）或跳过（False）
        """
        if not self.is_active:
            return

        self.is_active = False
        self.current_step_index = 0

        # 隐藏UI
        self.overlay.hide_overlay()
        self.bubble.hide()

        # 保存状态到配置
        self.app_config.mark_tutorial_finished(completed)

        self.logger.info(f"教程已{'完成' if completed else '跳过'}")

    def _find_widget_by_name(self, widget_name: str) -> Optional[QWidget]:
        """通过对象名称查找控件

        Args:
            widget_name: 控件的对象名称

        Returns:
            找到的控件，未找到返回None
        """
        # 优先尝试直接通过属性访问（更可靠）
        self.logger.debug(f"查找控件: {widget_name}")
        self.logger.debug(f"hasattr结果: {hasattr(self.main_window, widget_name)}")

        if hasattr(self.main_window, widget_name):
            widget = getattr(self.main_window, widget_name)
            self.logger.debug(f"获取到的对象类型: {type(widget).__name__}, 是否为QWidget: {isinstance(widget, QWidget)}")
            if isinstance(widget, QWidget):
                self.logger.info(f"[OK] 通过属性找到控件: {widget_name} (类型: {type(widget).__name__})")
                self.logger.debug(f"即将return widget: {widget}, id={id(widget)}")
                return widget
            else:
                self.logger.warning(f"对象不是QWidget: {widget_name}, 类型: {type(widget).__name__}")

        # 回退到使用findChildren查找
        from PyQt6.QtCore import QObject
        widgets = self.main_window.findChildren(QObject, widget_name)
        self.logger.debug(f"findChildren找到 {len(widgets)} 个对象")

        # 过滤出QWidget类型的控件
        for widget in widgets:
            self.logger.debug(f"检查对象: {type(widget).__name__}, 是否为QWidget: {isinstance(widget, QWidget)}")
            if isinstance(widget, QWidget):
                self.logger.info(f"[OK] 通过findChildren找到控件: {widget_name} (类型: {type(widget).__name__})")
                return widget

        self.logger.error(f"[FAIL] 未找到控件: {widget_name}")
        return None

    def reset_tutorial(self):
        """重置教程状态（用于"重新开始教程"功能）"""
        self.logger.info("重置教程状态")
        self.app_config.reset_tutorial()
        self.start_tutorial()
