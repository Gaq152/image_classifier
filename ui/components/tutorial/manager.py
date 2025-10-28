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
    target_widget_name: str  # 目标控件的对象名称
    arrow_position: ArrowPosition  # 箭头位置
    highlight_padding: int = 8  # 高亮区域内边距
    offset_x: int = 0  # 气泡X轴偏移
    offset_y: int = 0  # 气泡Y轴偏移


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
                arrow_position=ArrowPosition.LEFT,
                offset_x=20
            ),
            TutorialStep(
                title="图片预览",
                content='选中的图片会在左侧预览区域显示。\n\n你可以使用鼠标滚轮缩放图片，拖动查看细节。',
                target_widget_name="image_preview_container",
                arrow_position=ArrowPosition.RIGHT,
                offset_x=-20
            ),
            TutorialStep(
                title="分类区域",
                content='点击工具栏的「添加类别」可以创建新的分类目录。\n\n创建的类别会显示在这里。你可以为每个类别设置快捷键，方便快速分类。',
                target_widget_name="category_list",
                arrow_position=ArrowPosition.LEFT,
                offset_x=20
            ),
            TutorialStep(
                title="操作模式",
                content='这里可以切换复制/移动模式：\n\n• 复制模式(⧉)：保留原文件，复制到分类目录\n• 移动模式(⭆)：将文件移动到分类目录',
                target_widget_name="mode_button",
                arrow_position=ArrowPosition.BOTTOM,  # 改回底部箭头，气泡在上方
                highlight_padding=12,
                offset_y=-200  # 大幅向上偏移，气泡完全在按钮上方
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
        if not target_widget:
            self.logger.error(f"未找到目标控件: {step.target_widget_name}")
            self.next_step()  # 跳过此步骤
            return

        # 确保目标控件可见
        if hasattr(target_widget, 'isVisible') and not target_widget.isVisible():
            self.logger.warning(f"目标控件不可见: {step.target_widget_name}")
            self.next_step()  # 跳过此步骤
            return

        # 显示遮罩层并高亮目标
        self.overlay.highlight_widget(target_widget, step.highlight_padding)
        self.overlay.show_overlay()

        # 设置气泡内容
        self.bubble.set_content(f"<h3>{step.title}</h3><p>{step.content}</p>")
        self.bubble.set_arrow_position(step.arrow_position)
        self.bubble.set_step_info(self.current_step_index + 1, len(self.steps))

        # 显示气泡
        self.bubble.show_at(target_widget, step.offset_x, step.offset_y)

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
        # 使用findChildren查找所有匹配的控件（不指定类型参数，查找所有QObject）
        from PyQt6.QtCore import QObject
        widgets = self.main_window.findChildren(QObject, widget_name)

        # 过滤出QWidget类型的控件
        for widget in widgets:
            if isinstance(widget, QWidget):
                self.logger.debug(f"找到控件: {widget_name} (类型: {type(widget).__name__})")
                return widget

        self.logger.warning(f"未找到控件: {widget_name}")
        return None

    def reset_tutorial(self):
        """重置教程状态（用于"重新开始教程"功能）"""
        self.logger.info("重置教程状态")
        self.app_config.reset_tutorial()
        self.start_tutorial()
