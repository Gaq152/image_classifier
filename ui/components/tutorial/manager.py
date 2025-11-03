"""
教程管理器

协调整个教程流程，管理步骤导航、遮罩层和提示气泡的显示。
"""

import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import QTimer, QPoint, QRect

from .overlay import TutorialOverlay
from .bubble import TutorialBubble, ArrowPosition
from .mock_widgets import MockMenu, MockDialog, MockMessageBox, MockTabbedDialog
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
    secondary_target_widget_name: Optional[str] = None  # 第二个目标控件（用于双箭头）
    mock_widget_type: Optional[str] = None  # 虚拟组件类型: "menu", "dialog", "messagebox"
    mock_widget_content: Optional[Dict[str, Any]] = None  # 虚拟组件内容配置
    mock_widget_position: Optional[str] = None  # 虚拟组件位置: "at_target", "center", 或自定义


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
        self.current_mock_widget = None  # 当前显示的虚拟组件

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
            # 步骤1: 欢迎
            TutorialStep(
                title="欢迎使用图像分类工具",
                content='欢迎使用图像分类工具！<br><br>这个工具可以帮助你快速整理和分类大量图片。<br><br>让我们通过详细教程了解所有功能。',
                target_widget_name="main_window",
                arrow_position=ArrowPosition.TOP,
                offset_y=100
            ),

            # 步骤2: 打开目录按钮
            TutorialStep(
                title="打开图片目录",
                content='点击顶部的<b>「📁 打开目录」</b>按钮，或者图片列表旁边的小图标，都可以选择包含图片的文件夹。<br><br>'
                        '程序会自动扫描目录中的所有图片文件（支持JPG、PNG、BMP等格式）。',
                target_widget_name="open_directory_toolbar_button",
                arrow_position=ArrowPosition.LEFT_RIGHT,
                highlight_padding=12,
                offset_x=0,
                offset_y=0,
                highlight_widget_names=["open_directory_toolbar_button", "folder_button"],
                secondary_target_widget_name="folder_button"
            ),

            # 步骤3: 图片列表
            TutorialStep(
                title="图片列表",
                content='打开目录后，扫描到的图片会以列表形式显示在这里。<br><br>'
                        '• 点击图片可以预览<br>'
                        '• 使用 <b>← →</b> 键切换图片',
                target_widget_name="image_list",
                arrow_position=ArrowPosition.RIGHT,
                offset_x=-20
            ),

            # 步骤4: 筛选功能
            TutorialStep(
                title="筛选图片",
                content='点击这个<b>「▼」</b>按钮可以筛选要显示的图片：<br><br>'
                        '• <b>⚠️</b> 显示未分类图片<br>'
                        '• <b>✅</b> 显示已分类图片<br>'
                        '• <b>❌</b> 显示已移除图片<br><br>'
                        '可以同时勾选多个选项。',
                target_widget_name="filter_button",
                arrow_position=ArrowPosition.RIGHT,  # 气泡在左侧，箭头在气泡右侧指向按钮
                highlight_padding=12,
                offset_x=20,  # 气泡向右偏移，留出空间给箭头
                offset_y=0,
                mock_widget_type="menu",
                mock_widget_content={
                    "items": [
                        ("☑", "⚠️ 显示未分类图片"),
                        ("☑", "✅ 显示已分类图片"),
                        ("☐", "❌ 显示已移除图片")
                    ]
                },
                mock_widget_position="at_target"
            ),

            # 步骤5: 图片预览
            TutorialStep(
                title="图片预览区",
                content='选中的图片会在这里大图显示。<br><br>'
                        '<b>缩放操作：</b><br>'
                        '• 鼠标滚轮：快速缩放<br>'
                        '• <b>Ctrl + =/-</b>：放大/缩小<br>'
                        '• <b>Ctrl + 0</b>：重置缩放<br><br>'
                        '<b>查看操作：</b><br>'
                        '• 拖拽图片：查看细节<br>'
                        '• 点击右上角 <b>ℹ️</b>：查看图片信息并复制',
                target_widget_name="image_preview_container",
                arrow_position=ArrowPosition.LEFT,
                offset_x=20
            ),

            # 步骤6: 添加类别按钮
            TutorialStep(
                title="添加分类类别",
                content='点击顶部的<b>「➕ 添加类别」</b>按钮，或者分类列表旁边的小图标，都可以创建新的分类类别。<br><br>'
                        '你可以批量添加多个类别，多个类别用逗号或换行分隔。',
                target_widget_name="add_category_toolbar_button",
                arrow_position=ArrowPosition.LEFT_RIGHT,
                highlight_padding=12,
                offset_x=0,
                offset_y=0,
                highlight_widget_names=["add_category_toolbar_button", "add_category_button"],
                secondary_target_widget_name="add_category_button",
                mock_widget_type="dialog",
                mock_widget_content={
                    "title": "批量添加类别",
                    "items": [],
                    "buttons": ["添加", "添加并继续", "取消"],
                    "content_type": "text_edit",
                    "has_preview": True
                },
                mock_widget_position="bottom_center"  # 改为底部居中，避免与气泡重叠
            ),

            # 步骤7: 分类区域
            TutorialStep(
                title="分类类别列表",
                content='创建的类别会显示在这里。<br><br>'
                        '• 双击类别按钮：将当前图片分类到该类别<br>'
                        '• 按快捷键（<b>1-9, A-Z</b>）：快速分类<br>'
                        '• 右键点击类别：更多管理选项',
                target_widget_name="category_list",
                arrow_position=ArrowPosition.RIGHT,
                offset_x=-20
            ),

            # 步骤8: 移除功能
            TutorialStep(
                title="移除图片",
                content='点击这个<b>「🗑」</b>按钮可以将当前图片移除到移除目录。<br><br>'
                        '移除的图片不会被删除，只是移动到专门的 <b>remove</b> 文件夹中。<br><br>'
                        '按 <b>Delete</b> 键也可以快速移除图片。',
                target_widget_name="remove_button",
                arrow_position=ArrowPosition.TOP,
                highlight_padding=12,
                offset_y=20
            ),

            # 步骤9: 类别右键菜单
            TutorialStep(
                title="类别管理菜单",
                content='右键点击任意类别可以进行管理：<br><br>'
                        '• <b>🏷️ 修改类别名称</b><br>'
                        '• <b>⌨️ 修改快捷键</b><br>'
                        '• <b>⊘ 忽略该类别</b>：从列表中隐藏<br>'
                        '• <b>⚙️ 管理忽略类别</b>：查看和恢复已忽略的类别<br>'
                        '• <b>🗑️ 删除类别</b>：永久删除',
                target_widget_name="category_list",
                arrow_position=ArrowPosition.RIGHT,
                offset_x=-20,
                mock_widget_type="menu",
                mock_widget_content={
                    "items": [
                        ("🏷️", "修改类别名称"),
                        ("⌨️", "修改快捷键"),
                        ("⊘", "忽略该类别"),
                        ("⚙️", "管理忽略类别"),
                        ("🗑️", "删除类别")
                    ],
                    "separator_after": 1  # 在"修改快捷键"后添加分隔线
                },
                mock_widget_position="at_target"
            ),

            # 步骤10: 排序功能
            TutorialStep(
                title="类别排序",
                content='点击这个<b>「▼」</b>按钮可以调整类别的排序方式：<br><br>'
                        '• 按名称排序<br>'
                        '• 按快捷键排序',
                target_widget_name="sort_button",
                arrow_position=ArrowPosition.RIGHT,  # 气泡在左侧，箭头在气泡右侧指向按钮
                highlight_padding=12,
                offset_x=20,  # 气泡向右偏移，留出空间给箭头
                offset_y=0,
                mock_widget_type="menu",
                mock_widget_content={
                    "items": [
                        ("☑", "按名称排序"),
                        ("☐", "按快捷键排序")
                    ]
                },
                mock_widget_position="at_target"
            ),

            # 步骤11: 操作模式（复制/移动）
            TutorialStep(
                title="操作模式",
                content='切换文件操作模式：<br><br>'
                        '• <b>⧉ 复制模式</b>：保留原文件，复制到分类目录<br>'
                        '• <b>✂ 移动模式</b>：将文件移动到分类目录<br><br>'
                        '点击按钮可以切换模式。',
                target_widget_name="mode_button",
                arrow_position=ArrowPosition.TOP,
                highlight_padding=12,
                offset_y=20
            ),

            # 步骤12: 分类模式（单/多分类）
            TutorialStep(
                title="分类模式",
                content='切换分类模式：<br><br>'
                        '• <b>→ 单分类模式</b>：一张图片只能属于一个类别<br>'
                        '• <b>⇶ 多分类模式</b>：一张图片可以属于多个类别<br><br>'
                        '注意：多分类模式只在复制模式下可用。',
                target_widget_name="category_mode_button",
                arrow_position=ArrowPosition.TOP,
                highlight_padding=12,
                offset_y=20
            ),

            # 步骤13: 刷新功能
            TutorialStep(
                title="刷新目录",
                content='点击这个<b>「↻」</b>按钮（或按 <b>F5</b>）可以刷新类别目录。<br><br>'
                        '当你在外部修改了分类文件夹时，使用此功能可以同步最新状态。',
                target_widget_name="refresh_button",
                arrow_position=ArrowPosition.TOP,
                highlight_padding=12,
                offset_y=20
            ),

            # 步骤14: 主题切换
            TutorialStep(
                title="主题切换",
                content='点击这个<b>「☾/☼」</b>按钮可以切换明暗主题：<br><br>'
                        '• <b>☾</b>：切换到暗色主题<br>'
                        '• <b>☼</b>：切换到亮色主题<br><br>'
                        '根据你的使用习惯选择合适的主题。',
                target_widget_name="theme_button",
                arrow_position=ArrowPosition.TOP,
                highlight_padding=12,
                offset_y=20
            ),

            # 步骤15: 帮助按钮
            TutorialStep(
                title="获取帮助",
                content='点击这个<b>「?」</b>按钮可以随时查看：<br><br>'
                        '• 完整的使用指南<br>'
                        '• 快捷键列表<br>'
                        '• 重新开始本教程',
                target_widget_name="help_button",
                arrow_position=ArrowPosition.TOP,
                highlight_padding=12,
                offset_y=20,
                mock_widget_type="tabbed_dialog",
                mock_widget_content={
                    "title": "帮助和关于",
                    "tabs": ["快速入门", "使用指南", "高级功能", "常见问题", "关于"],
                    "buttons": ["🗑️ 清理SMB缓存", "📖 重新开始教程"]
                },
                mock_widget_position="center"
            ),

            # 步骤16: 快捷键
            TutorialStep(
                title="快捷键操作",
                content='使用键盘快捷键可以大幅提升分类效率：<br><br>'
                        '<b>导航：</b><br>'
                        '• <b>← →</b> 切换到上一张/下一张图片<br><br>'
                        '<b>分类：</b><br>'
                        '• <b>1-9, A-Z</b> 快速分类到对应类别<br>'
                        '• <b>Delete</b> 移除当前图片<br><br>'
                        '<b>其他：</b><br>'
                        '• <b>F5</b> 刷新类别目录<br>'
                        '• <b>再次点击</b>已分类的类别或移除按钮可撤销操作',
                target_widget_name="central_widget",
                arrow_position=ArrowPosition.TOP,
                offset_y=100
            ),

            # 步骤17: 完成
            TutorialStep(
                title="教程完成！",
                content='恭喜你完成了所有教程！<br><br>'
                        '现在你已经掌握了图像分类工具的所有功能。<br><br>'
                        '开始整理你的图片吧！<br><br>'
                        '如需再次查看教程，可以在帮助对话框中点击<b>「重新开始教程」</b>按钮。',
                target_widget_name="main_window",
                arrow_position=ArrowPosition.TOP,
                offset_y=100
            )
        ]

    def _connect_signals(self):
        """连接信号槽"""
        self.bubble.next_clicked.connect(self.next_step)
        self.bubble.prev_clicked.connect(self.prev_step)
        self.bubble.skip_clicked.connect(self.skip_tutorial)
        self.bubble.finish_clicked.connect(self.finish_tutorial)
        # 注意：不连接 overlay.overlay_clicked，避免误触导航

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

        # 清理上一步的虚拟组件
        self._hide_mock_widget()

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

            # 显示气泡前，检查是否需要为虚拟组件调整位置
            adjusted_offset_x = step.offset_x
            adjusted_offset_y = step.offset_y

            # 如果有虚拟菜单且arrow_position是RIGHT（气泡在左侧），需要考虑虚拟菜单的宽度
            if (step.mock_widget_type == "menu" and
                step.mock_widget_position == "at_target" and
                step.arrow_position == ArrowPosition.RIGHT):

                # MockMenu的固定宽度是200px（从mock_widgets.py得知）
                menu_width = 200
                spacing = 20  # 气泡和菜单之间的间距

                # 计算虚拟菜单的位置
                target_pos = target_widget.mapTo(self.main_window, target_widget.rect().topLeft())
                target_rect = target_widget.rect()

                # 虚拟菜单右对齐：菜单右边缘 = 按钮右边缘
                menu_right = target_pos.x() + target_rect.width()
                menu_left = menu_right - menu_width

                # 气泡应该在虚拟菜单左侧
                # adjusted_offset_x应该让气泡显示在menu_left左侧
                # 计算需要的偏移量：从按钮位置算起，要移动到菜单左侧再减去气泡宽度和间距
                # 简化：直接使用负的偏移量
                adjusted_offset_x = -(menu_width + spacing)

                self.logger.info(f"调整气泡位置以避开虚拟菜单: offset_x从{step.offset_x}调整为{adjusted_offset_x}")

            self.logger.debug(f"开始显示气泡，offset_x={adjusted_offset_x}, offset_y={adjusted_offset_y}")
            self.logger.debug(f"目标控件geometry: {target_widget.geometry()}")
            self.logger.debug(f"目标控件size: {target_widget.size()}")

            # 如果有第二个目标控件（双箭头模式），查找它
            secondary_widget = None
            if step.secondary_target_widget_name:
                secondary_widget = self._find_widget_by_name(step.secondary_target_widget_name)
                if secondary_widget is None:
                    self.logger.warning(f"未找到第二个目标控件: {step.secondary_target_widget_name}")

            self.bubble.show_at(target_widget, adjusted_offset_x, adjusted_offset_y, secondary_widget)

            # 确保气泡在遮罩层之上
            self.bubble.raise_()

            # 告诉overlay bubble的位置，避免拦截bubble的点击
            from PyQt6.QtCore import QRect, QPoint
            bubble_rect = QRect(self.bubble.x(), self.bubble.y(), self.bubble.width(), self.bubble.height())
            self.overlay.set_bubble_region(bubble_rect)

            # 如果是双箭头模式，告诉overlay绘制箭头
            if step.arrow_position == ArrowPosition.LEFT_RIGHT and secondary_widget is not None:
                # 计算气泡中心位置（全局坐标）
                bubble_center = QPoint(
                    self.bubble.x() + self.bubble.width() // 2,
                    self.bubble.y() + self.bubble.height() // 2
                )

                # 计算两个目标的边缘位置（箭头指向控件最近的边缘）
                target_pos_in_parent = target_widget.mapTo(self.main_window, target_widget.rect().topLeft())
                target_rect = target_widget.rect()
                # 左侧目标：箭头指向右边缘的中点
                left_target = QPoint(
                    target_pos_in_parent.x() + target_rect.width(),  # 右边缘
                    target_pos_in_parent.y() + target_rect.height() // 2  # 垂直中心
                )

                secondary_pos_in_parent = secondary_widget.mapTo(self.main_window, secondary_widget.rect().topLeft())
                secondary_rect = secondary_widget.rect()
                # 右侧目标：箭头指向左边缘的中点
                right_target = QPoint(
                    secondary_pos_in_parent.x(),  # 左边缘
                    secondary_pos_in_parent.y() + secondary_rect.height() // 2  # 垂直中心
                )

                self.logger.info(f"设置双箭头: bubble_center={bubble_center}, left={left_target}, right={right_target}")
                self.overlay.set_dual_arrows(bubble_center, left_target, right_target)
            else:
                # 非双箭头模式，清除箭头
                self.overlay.clear_arrows()

            # 创建并显示虚拟组件（如果配置了）
            self._show_mock_widget(step, target_widget)

            self.logger.debug(f"气泡显示完成，位置: ({self.bubble.x()}, {self.bubble.y()}), 大小: ({self.bubble.width()}, {self.bubble.height()}), 可见: {self.bubble.isVisible()}")
        except Exception as e:
            self.logger.error(f"显示教程步骤时出错: {e}", exc_info=True)
            self.next_step()  # 出错则跳过此步骤

    def _show_mock_widget(self, step: TutorialStep, target_widget: QWidget):
        """显示虚拟组件

        Args:
            step: 教程步骤
            target_widget: 目标控件
        """
        if not step.mock_widget_type or not step.mock_widget_content:
            return

        self.logger.info(f"创建虚拟组件: {step.mock_widget_type}")

        try:
            # 创建虚拟组件
            if step.mock_widget_type == "menu":
                mock_widget = MockMenu(self.main_window)
                items = step.mock_widget_content.get("items", [])
                separator_after = step.mock_widget_content.get("separator_after")

                # 如果有第二组菜单项（分隔线后的）
                items2 = step.mock_widget_content.get("items2")
                if items2:
                    all_items = items + items2
                    mock_widget.add_items(all_items, separator_after)
                else:
                    mock_widget.add_items(items, separator_after)

            elif step.mock_widget_type == "dialog":
                mock_widget = MockDialog(self.main_window)
                title = step.mock_widget_content.get("title", "")
                items = step.mock_widget_content.get("items", [])
                buttons = step.mock_widget_content.get("buttons", [])
                content_type = step.mock_widget_content.get("content_type", "form")
                has_preview = step.mock_widget_content.get("has_preview", False)
                mock_widget.set_content(title, items, buttons, content_type, has_preview)

            elif step.mock_widget_type == "messagebox":
                mock_widget = MockMessageBox(self.main_window)
                title = step.mock_widget_content.get("title", "")
                message = step.mock_widget_content.get("message", "")
                buttons = step.mock_widget_content.get("buttons", [])
                mock_widget.set_content(title, message, buttons)

            elif step.mock_widget_type == "tabbed_dialog":
                mock_widget = MockTabbedDialog(self.main_window)
                title = step.mock_widget_content.get("title", "")
                tabs = step.mock_widget_content.get("tabs", [])
                buttons = step.mock_widget_content.get("buttons", [])
                mock_widget.set_content(title, tabs, buttons)

            else:
                self.logger.warning(f"未知的虚拟组件类型: {step.mock_widget_type}")
                return

            # 定位虚拟组件
            parent_rect = self.main_window.rect()

            if step.mock_widget_position == "center":
                # 居中显示
                x = (parent_rect.width() - mock_widget.width()) // 2
                y = (parent_rect.height() - mock_widget.height()) // 2
                mock_widget.move(x, y)
            elif step.mock_widget_position == "bottom_center":
                # 底部居中显示
                x = (parent_rect.width() - mock_widget.width()) // 2
                y = parent_rect.height() - mock_widget.height() - 20  # 距离底部20px
                mock_widget.move(x, y)
            elif step.mock_widget_position == "at_target":
                # 显示在目标控件附近
                target_pos = target_widget.mapTo(self.main_window, target_widget.rect().topLeft())
                target_rect = target_widget.rect()

                # 根据组件类型和目标控件决定位置
                if step.mock_widget_type == "menu":
                    # 菜单显示逻辑
                    if step.target_widget_name == "category_list":
                        # 右键菜单显示在列表内部中央
                        x = target_pos.x() + (target_rect.width() - mock_widget.width()) // 2
                        y = target_pos.y() + (target_rect.height() - mock_widget.height()) // 2
                    elif step.target_widget_name in ["filter_button", "sort_button"]:
                        # 下拉菜单显示在按钮下方，右对齐
                        x = target_pos.x() + target_rect.width() - mock_widget.width()
                        y = target_pos.y() + target_rect.height()
                    else:
                        # 默认显示在目标控件下方
                        x = target_pos.x()
                        y = target_pos.y() + target_rect.height()
                else:
                    # 对话框显示在目标控件右侧
                    x = target_pos.x() + target_rect.width() + 20
                    y = target_pos.y()

                # 确保不超出窗口边界（但不改变虚拟组件的基本位置，保持模拟真实）
                if x + mock_widget.width() > parent_rect.width():
                    x = parent_rect.width() - mock_widget.width() - 10
                if x < 10:
                    x = 10
                if y + mock_widget.height() > parent_rect.height():
                    y = parent_rect.height() - mock_widget.height() - 10
                if y < 10:
                    y = 10

                mock_widget.move(x, y)

            # 显示虚拟组件
            mock_widget.show()

            # 调整z-order：虚拟组件应该在遮罩层之上，气泡之下
            mock_widget.raise_()  # 先提升到顶层
            self.bubble.raise_()  # 然后气泡提升到最顶层

            # 将虚拟组件的区域添加到高亮区域（cut-out）
            mock_rect = QRect(mock_widget.x(), mock_widget.y(), mock_widget.width(), mock_widget.height())
            self.overlay.add_highlight_region(mock_rect, padding=0)

            # 保存引用
            self.current_mock_widget = mock_widget

            self.logger.info(f"虚拟组件已显示: 位置({mock_widget.x()}, {mock_widget.y()}), 大小({mock_widget.width()}x{mock_widget.height()})")

        except Exception as e:
            self.logger.error(f"创建虚拟组件时出错: {e}", exc_info=True)

    def _hide_mock_widget(self):
        """隐藏并销毁当前虚拟组件"""
        if self.current_mock_widget is not None:
            self.logger.info("隐藏虚拟组件")
            self.current_mock_widget.hide()
            self.current_mock_widget.deleteLater()
            self.current_mock_widget = None

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
        self._hide_mock_widget()

        # 保存状态到配置
        self.app_config.mark_tutorial_finished(completed)

        self.logger.info(f"教程已{'完成' if completed else '跳过'}")

        # 教程结束后，延迟检查是否需要恢复上次目录
        from PyQt6.QtCore import QTimer
        if hasattr(self.main_window, '_check_and_restore_last_directory'):
            QTimer.singleShot(500, self.main_window._check_and_restore_last_directory)

    def _find_widget_by_name(self, widget_name: str) -> Optional[QWidget]:
        """通过对象名称查找控件

        Args:
            widget_name: 控件的对象名称

        Returns:
            找到的控件，未找到返回None
        """
        # 特殊处理：如果要查找整个主窗口
        if widget_name == "main_window":
            self.logger.info(f"[OK] 返回主窗口: main_window")
            return self.main_window

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
