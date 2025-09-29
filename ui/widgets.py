"""
自定义UI组件模块

包含所有自定义的PyQt6组件，如按钮、列表项、标签等。
"""

import logging
from pathlib import Path
from PyQt6.QtWidgets import (QPushButton, QLabel, QHBoxLayout, QVBoxLayout, QListWidgetItem, 
                            QWidget, QScrollArea, QMessageBox, QApplication, QProgressBar, QFrame)
from PyQt6.QtCore import Qt, QTimer, QPoint
from PyQt6.QtGui import QPixmap, QPainter, QPen, QBrush, QColor, QIcon, QFont

from ..utils.file_operations import normalize_folder_name, retry_file_operation
from ..utils.exceptions import FileOperationError
from .components.toast import toast_warning, toast_error, toast_floating


class CategoryButton(QPushButton):
    """自定义类别按钮"""
    
    def __init__(self, category_name, config, is_remove=False, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(30)
        self.setMaximumWidth(250)
        self.is_remove = is_remove
        self.category_name = category_name  # 直接使用类别名称
        self.chinese_name = category_name  # 保持向后兼容
        self.config = config
        self.count = 0
        self.is_multi_classified = False  # 添加多分类状态标记
        self.logger = logging.getLogger(__name__)
        
        # 创建内部布局
        self.inner_layout = QHBoxLayout(self)
        self.inner_layout.setContentsMargins(8, 0, 8, 0)
        self.inner_layout.setSpacing(4)
        
        # 创建标签
        self.text_label = QLabel()
        self.count_label = QLabel()
        self.count_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.count_label.setMinimumWidth(30)
        font = self.count_label.font()
        font.setBold(True)
        self.count_label.setFont(font)
        
        self.inner_layout.addWidget(self.text_label, 1)
        self.inner_layout.addWidget(self.count_label, 0)
        
        # 更新文本
        self.update_text()
        
        # 设置简洁美观的样式 - 减少占用空间
        self.setStyleSheet("""
            QPushButton {
                font-size: 13px;
                padding: 6px 8px;
                border: 1px solid #ddd;
                border-radius: 4px;
                background-color: #ffffff;
                text-align: left;
                margin: 1px 0;
                font-weight: 500;
                min-height: 20px;
            }
            QPushButton:hover {
                border-color: #aaa;
                background-color: #f0f0f0;
            }
            /* 键盘导航或鼠标选中状态 - 蓝色边框 */
            QPushButton:checked {
                border: 2px solid #2196F3;
                background-color: #E3F2FD;
                color: #1565C0;
                font-weight: bold;
            }
            /* 已分类状态 - 绿色背景（多分类模式下已选中的类别）*/
            QPushButton[classified="true"] {
                border: 1px solid #4CAF50;
                background-color: #E8F5E8;
                color: #2E7D32;
                font-weight: bold;
            }
            /* 已分类且当前选中状态 - 蓝色边框，绿色背景 */
            QPushButton[classified="true"]:checked {
                border: 2px solid #2196F3;
                background-color: #C8E6C9;
                color: #1B5E20;
                font-weight: bold;
            }
            /* 多分类状态 - 绿色背景（用于多分类模式下已分类的类别）*/
            QPushButton[multi_classified="true"] {
                border: 1px solid #4CAF50;
                background-color: #E8F5E8;
                color: #2E7D32;
                font-weight: bold;
            }
            /* 多分类且当前选中状态 - 蓝色边框，绿色背景 */
            QPushButton[multi_classified="true"]:checked {
                border: 2px solid #2196F3;
                background-color: #C8E6C9;
                color: #1B5E20;
                font-weight: bold;
            }
            /* 已移除状态 - 红色背景 */
            QPushButton[removed="true"] {
                border: 1px solid #F44336;
                background-color: #FFEBEE;
                color: #C62828;
                font-weight: bold;
            }
            /* 已移除且选中状态 */
            QPushButton[removed="true"]:checked {
                border: 2px solid #2196F3;
                background-color: #FFCDD2;
                color: #B71C1C;
                font-weight: bold;
            }
            QLabel {
                background: transparent;
                border: none;
                font-size: 13px;
                font-weight: inherit;
                color: inherit;
            }
        """)
            
    def update_text(self):
        """更新按钮文本"""
        try:
            shortcut = self.config.category_shortcuts.get(self.category_name, '')
            if shortcut:
                text = f"[{shortcut}] {self.category_name}"
            else:
                text = self.category_name
            self.text_label.setText(text)
        except Exception as e:
            self.logger.error(f"更新按钮文本失败: {e}")
            self.text_label.setText(self.category_name)
        
    def set_count(self, count):
        """设置计数"""
        self.count = count
        self.count_label.setText(str(count))
        
    def set_classified(self, classified):
        """设置分类状态"""
        self.setProperty("classified", classified)
        self.style().unpolish(self)
        self.style().polish(self)
        
    def set_removed(self, removed):
        """设置移除状态"""
        self.setProperty("removed", removed)
        self.style().unpolish(self)
        self.style().polish(self)

    def set_multi_classified(self, multi_classified):
        """设置多分类状态"""
        self.is_multi_classified = multi_classified
        self.setProperty("multi_classified", multi_classified)
        self.style().unpolish(self)
        self.style().polish(self)
        if multi_classified:
            self.logger.debug(f"设置多分类标记: {self.category_name}")
            
    def show_context_menu(self, pos):
        """显示右键菜单"""
        try:
            from PyQt6.QtWidgets import QMenu
            
            menu = QMenu(self)
            
            # 修改类别名称
            rename_action = menu.addAction("🏷️ 修改类别名称")
            rename_action.triggered.connect(self.rename_category)
            
            # 修改快捷键
            shortcut_action = menu.addAction("⌨️ 修改快捷键")
            shortcut_action.triggered.connect(self.change_shortcut)
            
            menu.addSeparator()
            
            # 删除类别（如果不是移除按钮）
            if not self.is_remove:
                delete_action = menu.addAction("🗑️ 删除类别")
                delete_action.triggered.connect(self.delete_category)
            
            # 显示菜单
            menu.exec(self.mapToGlobal(pos))
            
        except Exception as e:
            # 获取主窗口用于显示Toast
            main_window = self.parent()
            while main_window and not hasattr(main_window, 'show_error_toast'):
                main_window = main_window.parent()
            if main_window:
                main_window.show_error_toast(f"显示菜单失败: {e}")
            else:
                toast_error(self, f"显示菜单失败: {e}")

    def rename_category(self):
        """重命名类别"""
        try:
            from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QLabel, QMessageBox
            from PyQt6.QtCore import Qt
            
            # 创建自定义对话框
            dialog = QDialog(self)
            dialog.setWindowTitle("修改类别名称")
            dialog.setModal(True)
            dialog.setFixedSize(350, 150)
            
            # 设置对话框样式
            dialog.setStyleSheet("""
                QDialog {
                    background-color: #F8F9FA;
                    border: 1px solid #BDC3C7;
                    border-radius: 8px;
                }
                QLabel {
                    color: #2C3E50;
                    font-size: 14px;
                    font-weight: bold;
                }
                QLineEdit {
                    background-color: #FFFFFF;
                    border: 2px solid #BDC3C7;
                    border-radius: 6px;
                    padding: 8px 12px;
                    font-size: 13px;
                    color: #2C3E50;
                }
                QLineEdit:focus {
                    border-color: #3498DB;
                }
                QPushButton {
                    background-color: #3498DB;
                    color: white;
                    border: none;
                    border-radius: 6px;
                    padding: 8px 16px;
                    font-size: 13px;
                    font-weight: bold;
                    min-width: 80px;
                }
                QPushButton:hover {
                    background-color: #2980B9;
                }
                QPushButton:pressed {
                    background-color: #21618C;
                }
                QPushButton#cancelButton {
                    background-color: #95A5A6;
                }
                QPushButton#cancelButton:hover {
                    background-color: #7F8C8D;
                }
            """)
            
            layout = QVBoxLayout(dialog)
            layout.setSpacing(15)
            layout.setContentsMargins(20, 20, 20, 20)
            
            # 标签
            label = QLabel(f"请输入新的类别名称:")
            layout.addWidget(label)
            
            # 输入框
            line_edit = QLineEdit(self.category_name)
            line_edit.selectAll()
            layout.addWidget(line_edit)
            
            # 按钮
            button_layout = QHBoxLayout()
            button_layout.addStretch()
            
            cancel_button = QPushButton("取消")
            cancel_button.setObjectName("cancelButton")
            cancel_button.clicked.connect(dialog.reject)
            button_layout.addWidget(cancel_button)
            
            ok_button = QPushButton("确定")
            ok_button.clicked.connect(dialog.accept)
            ok_button.setDefault(True)
            button_layout.addWidget(ok_button)
            
            layout.addLayout(button_layout)
            
            # 设置焦点
            line_edit.setFocus()
            
            # 显示对话框
            if dialog.exec() == QDialog.DialogCode.Accepted:
                new_name = line_edit.text().strip()
                if new_name and new_name != self.category_name:
                    main_window = self.window()
                    if main_window and hasattr(main_window, 'rename_category'):
                        main_window.rename_category(self.category_name, new_name)
                    
        except Exception as e:
            # 获取主窗口用于显示Toast
            main_window = self.parent()
            while main_window and not hasattr(main_window, 'show_error_toast'):
                main_window = main_window.parent()
            if main_window:
                main_window.show_error_toast(f"重命名失败: {e}")
            else:
                toast_error(self, f"重命名失败: {e}")

    def change_shortcut(self):
        """修改快捷键"""
        try:
            from ..ui.dialogs import CategoryShortcutDialog
            
            main_window = self.window()
            if main_window and hasattr(main_window, 'config'):
                dialog = CategoryShortcutDialog(main_window.config, self.category_name, self)
                if dialog.exec():
                    main_window.setup_shortcuts()
                    self.update_text()
                    
        except Exception as e:
            # 获取主窗口用于显示Toast
            main_window = self.parent()
            while main_window and not hasattr(main_window, 'show_error_toast'):
                main_window = main_window.parent()
            if main_window:
                main_window.show_error_toast(f"修改快捷键失败: {e}")
            else:
                toast_error(self, f"修改快捷键失败: {e}")

    def delete_category(self):
        """删除类别"""
        try:
            from PyQt6.QtWidgets import QMessageBox, QPushButton
            
            # 创建自定义消息框
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("🗑️ 确认删除")
            msg_box.setText(f"确定要删除类别 '{self.category_name}' 吗？")
            msg_box.setInformativeText("注意：这将删除对应的文件夹及其中的所有文件！")
            msg_box.setIcon(QMessageBox.Icon.Question)
            
            # 创建中文按钮
            yes_button = QPushButton("是")
            no_button = QPushButton("否")
            
            msg_box.addButton(yes_button, QMessageBox.ButtonRole.YesRole)
            msg_box.addButton(no_button, QMessageBox.ButtonRole.NoRole)
            
            # 设置默认按钮为"否"
            msg_box.setDefaultButton(no_button)
            
            # 设置样式
            msg_box.setStyleSheet("""
                QMessageBox {
                    background-color: #F8F9FA;
                    color: #2C3E50;
                }
                QMessageBox QLabel {
                    color: #2C3E50;
                    font-size: 14px;
                }
                QPushButton {
                    background-color: #3498DB;
                    color: white;
                    border: none;
                    border-radius: 6px;
                    padding: 8px 16px;
                    font-size: 13px;
                    font-weight: bold;
                    min-width: 60px;
                    margin: 2px;
                }
                QPushButton:hover {
                    background-color: #2980B9;
                }
                QPushButton:pressed {
                    background-color: #21618C;
                }
            """)
            
            # 显示对话框并处理结果
            msg_box.exec()
            clicked_button = msg_box.clickedButton()
            
            if clicked_button == yes_button:
                main_window = self.window()
                if main_window and hasattr(main_window, 'delete_category'):
                    main_window.delete_category(self.category_name)
                    
        except Exception as e:
            # 获取主窗口用于显示Toast
            main_window = self.parent()
            while main_window and not hasattr(main_window, 'show_error_toast'):
                main_window = main_window.parent()
            if main_window:
                main_window.show_error_toast(f"删除类别失败: {e}")
            else:
                toast_error(self, f"删除类别失败: {e}")

    def mousePressEvent(self, event):
        """处理鼠标按下事件"""
        from PyQt6.QtCore import Qt
        
        if event.button() == Qt.MouseButton.RightButton:
            self.show_context_menu(event.pos())
        else:
            super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        """处理双击事件 - 支持多分类模式下的选中/取消选择"""
        if not self.is_remove:
            # 获取主窗口并调用分类方法
            main_window = self.window()
            if main_window:
                # 在多分类模式下，双击可以选中或取消选择
                if main_window.is_multi_category:
                    # 多分类模式：双击切换选择状态
                    main_window.move_to_category(self.category_name)
                else:
                    # 单分类模式：保持原有逻辑，检查是否已分类
                    if hasattr(main_window, 'image_files') and hasattr(main_window, 'current_index') and main_window.image_files:
                        if 0 <= main_window.current_index < len(main_window.image_files):
                            current_path = str(main_window.image_files[main_window.current_index])
                            current_category = main_window.classified_images.get(current_path)
                            
                            # 检查是否已分类到该类别
                            already_classified = False
                            if isinstance(current_category, list):
                                already_classified = self.category_name in current_category
                            else:
                                already_classified = current_category == self.category_name

                            # 多分类模式下，已分类的图片再次点击会触发撤销，所以需要继续执行
                            # 单分类模式下，也需要支持撤销，所以也要继续执行
                            # 删除原有的"避免重复处理"逻辑，让 move_to_category 方法处理撤销逻辑
                            # if already_classified:
                            #     main_window.logger.info(f"图片已经分类到 {self.category_name}，避免重复处理")
                            #     event.accept()
                            #     return
                    
                    # 如果未分类或分类到其他类别，则进行分类操作
                    main_window.move_to_category(self.category_name)
        event.accept()
    



class ImageListItem(QListWidgetItem):
    """自定义列表项，显示图片状态和名称"""
    
    def __init__(self, image_path, is_classified, is_removed, parent=None):
        super().__init__(parent)
        self.image_path = image_path
        self.is_classified = is_classified
        self.is_removed = is_removed
        self.is_multi_classified = False  # 多分类状态标记
        self.setText(Path(image_path).name)
        # 延迟icon设置，避免QPixmap在QApplication前创建
        # self.setIcon(self.create_status_icon())
    
    def set_status_icon(self):
        """设置状态图标"""
        self.setIcon(self.create_status_icon())
    
    def create_status_icon(self):
        """创建美化的状态图标"""
        # 创建36x36的图标
        pixmap = QPixmap(36, 36)
        pixmap.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # 根据状态设置颜色和图标
        if self.is_classified:
            if self.is_multi_classified:
                # 多分类 - 蓝色图标
                color = QColor("#2196F3")
                shadow_color = QColor("#1565C0")
            else:
                # 已分类 - 绿色勾选图标
                color = QColor("#4CAF50")
                shadow_color = QColor("#2E7D32")
        elif self.is_removed:
            # 已移除 - 红色删除图标
            color = QColor("#F44336")
            shadow_color = QColor("#C62828")
        else:
            # 待处理 - 橙色警告图标
            color = QColor("#FF9800")
            shadow_color = QColor("#F57C00")
        
        # 绘制阴影效果
        painter.setPen(QPen(shadow_color, 2))
        painter.setBrush(QBrush(shadow_color, Qt.BrushStyle.SolidPattern))
        painter.drawEllipse(3, 3, 28, 28)
        
        # 绘制主圆形
        painter.setPen(QPen(color, 2))
        painter.setBrush(QBrush(color, Qt.BrushStyle.SolidPattern))
        painter.drawEllipse(2, 2, 28, 28)
        
        # 绘制状态符号
        painter.setPen(QPen(Qt.GlobalColor.white, 3))
        if self.is_classified:
            if self.is_multi_classified:
                # 绘制多分类标记 - 双层矩形
                painter.drawRect(8, 8, 14, 14)
                painter.drawRect(14, 14, 14, 14)
            else:
                # 绘制√ - 更优雅的勾选
                painter.drawLine(8, 16, 14, 22)
                painter.drawLine(14, 22, 26, 10)
        elif self.is_removed:
            # 绘制× - 删除符号
            painter.drawLine(10, 10, 24, 24)
            painter.drawLine(24, 10, 10, 24)
        else:
            # 绘制! - 待处理警告
            painter.setPen(QPen(Qt.GlobalColor.white, 2))
            painter.drawLine(16, 8, 16, 18)  # 竖线
            painter.drawEllipse(14, 22, 4, 4)  # 点
        
        painter.end()
        return QIcon(pixmap)
    
    def update_status(self, is_classified, is_removed, is_multi_classified=False):
        """更新状态"""
        self.is_classified = is_classified
        self.is_removed = is_removed
        self.is_multi_classified = is_multi_classified
        self.set_status_icon()


class EnhancedImageLabel(QLabel):
    """增强的图像显示组件，支持缩放和拖拽"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(300, 200)
        self.setStyleSheet("border: 1px solid #ccc; background-color: #f8f8f8;")
        
        self.original_pixmap = None
        self.scale_factor = 1.0
        self.min_scale = 0.1
        self.max_scale = 3.0  # 限制最大3倍，防止卡顿
        self.scale_step = 0.2  # 增大缩放步长，减少细微调整
        self._fit_to_window_mode = True  # 默认适应窗口模式
        
        # 拖拽相关
        self.dragging = False
        self.last_pan_point = None
        self.image_offset = QPoint(0, 0)  # 使用QPoint更精确
        self.drag_threshold = 3  # 拖拽阈值，避免误触
        
        # 启用鼠标追踪，用于拖拽
        self.setMouseTracking(True)
        
        # 创建信息按钮
        self.create_info_button()
        
        self.logger = logging.getLogger(__name__)
        
    def create_info_button(self):
        """创建信息按钮"""
        try:
            from PyQt6.QtWidgets import QPushButton
            from PyQt6.QtCore import Qt
            
            # 创建圆形信息按钮
            self.info_button = QPushButton("ℹ️", self)
            self.info_button.setFixedSize(30, 30)
            self.info_button.setStyleSheet("""
                QPushButton {
                    background-color: rgba(0, 0, 0, 120);
                    color: white;
                    border: none;
                    border-radius: 15px;
                    font-size: 14px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: rgba(0, 0, 0, 180);
                }
                QPushButton:pressed {
                    background-color: rgba(0, 0, 0, 220);
                }
            """)
            
            # 设置提示文本
            self.info_button.setToolTip("点击查看图片详细信息")
            
            # 连接点击事件
            self.info_button.clicked.connect(self.show_image_info_panel)
            
            # 初始位置（右上角）
            self.position_info_button()
            
        except Exception as e:
            self.logger.error(f"创建信息按钮失败: {e}")
    
    def position_info_button(self):
        """定位信息按钮到右上角"""
        try:
            if hasattr(self, 'info_button') and self.info_button:
                x = self.width() - self.info_button.width() - 10
                y = 10
                self.info_button.move(x, y)
        except Exception as e:
            self.logger.debug(f"定位信息按钮失败: {e}")
    
    def set_image(self, pixmap):
        """设置图像"""
        try:
            if pixmap and not pixmap.isNull():
                self.original_pixmap = pixmap
                self.scale_factor = 1.0
                self.image_offset = QPoint(0, 0)
                self._fit_to_window_mode = True  # 新图像默认适应窗口
                self.fit_to_window()
                
                # 更新信息面板内容（如果存在且可见）
                if hasattr(self, 'info_panel') and self.info_panel and self.info_panel.isVisible():
                    QTimer.singleShot(100, self.update_info_panel)
            else:
                self.clear()
                self.original_pixmap = None
                
                # 隐藏信息面板（如果没有图片）
                if hasattr(self, 'info_panel') and self.info_panel:
                    self.info_panel.hide()
                
        except Exception as e:
            self.logger.error(f"设置图像失败: {e}")
        
    def fit_to_window(self):
        """适应窗口大小"""
        if not self.original_pixmap:
            return
            
        try:
            label_size = self.size()
            pixmap_size = self.original_pixmap.size()
            
            # 计算缩放比例
            scale_x = label_size.width() / pixmap_size.width()
            scale_y = label_size.height() / pixmap_size.height()
            self.scale_factor = min(scale_x, scale_y, 1.0)  # 不放大，只缩小
            
            # 重置偏移
            self.image_offset = QPoint(0, 0)
            self._fit_to_window_mode = True
            
            self.update_display()
            # 更新信息面板中的缩放信息
            if hasattr(self, 'info_panel') and self.info_panel and self.info_panel.isVisible():
                QTimer.singleShot(50, self.update_info_panel)
        except Exception as e:
            self.logger.error(f"适应窗口失败: {e}")
        
    def zoom_in(self):
        """放大"""
        if self.scale_factor >= self.max_scale:
            self.logger.info("已达到最大缩放倍数，停止放大防止卡顿")
            toast_floating(self, "📈 已达到最大缩放倍数 (3.0x)", 3000)
            return
            
        self._fit_to_window_mode = False  # 手动缩放时退出适应窗口模式
        self.scale_factor = min(self.scale_factor + self.scale_step, self.max_scale)
        self.update_display()
        # 更新信息面板中的缩放信息
        if hasattr(self, 'info_panel') and self.info_panel and self.info_panel.isVisible():
            QTimer.singleShot(50, self.update_info_panel)
        
    def zoom_out(self):
        """缩小"""
        if self.scale_factor <= self.min_scale:
            toast_floating(self, "📉 已达到最小缩放倍数 (0.1x)", 3000)
            return
            
        self._fit_to_window_mode = False  # 手动缩放时退出适应窗口模式
        self.scale_factor = max(self.scale_factor - self.scale_step, self.min_scale)
        self.update_display()
        # 更新信息面板中的缩放信息
        if hasattr(self, 'info_panel') and self.info_panel and self.info_panel.isVisible():
            QTimer.singleShot(50, self.update_info_panel)
        
    def reset_zoom(self):
        """重置缩放"""
        self.scale_factor = 1.0
        self.image_offset = QPoint(0, 0)
        self._fit_to_window_mode = True  # 重置时回到适应窗口模式
        self.fit_to_window()
        
    def scale_image(self, factor):
        """缩放图像"""
        try:
            self._fit_to_window_mode = False  # 手动缩放时退出适应窗口模式
            new_scale = self.scale_factor * factor
            
            # 限制缩放范围，防止过度放大导致卡顿
            if new_scale > self.max_scale:
                self.logger.info(f"缩放倍数 {new_scale:.1f} 超过限制 {self.max_scale}，已限制")
                toast_floating(self, "📈 已达到最大缩放倍数 (3.0x)", 3000)
                new_scale = self.max_scale
                
            self.scale_factor = max(self.min_scale, min(new_scale, self.max_scale))
            self.update_display()
            # 更新信息面板中的缩放信息
            if hasattr(self, 'info_panel') and self.info_panel and self.info_panel.isVisible():
                QTimer.singleShot(50, self.update_info_panel)
        except Exception as e:
            self.logger.error(f"缩放图像失败: {e}")
            
    def update_display(self):
        """更新显示 - 支持拖拽偏移"""
        if not self.original_pixmap:
            return
            
        try:
            # 缩放图像
            scaled_size = self.original_pixmap.size() * self.scale_factor
            scaled_pixmap = self.original_pixmap.scaled(
                scaled_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            
            # 如果有拖拽偏移，创建带偏移的显示
            if self.image_offset.x() != 0 or self.image_offset.y() != 0:
                # 创建更大的画布来容纳偏移
                canvas_size = self.size()
                canvas = QPixmap(canvas_size)
                canvas.fill(Qt.GlobalColor.transparent)
                
                painter = QPainter(canvas)
                try:
                    # 计算居中位置加上偏移
                    x = (canvas_size.width() - scaled_pixmap.width()) // 2 + self.image_offset.x()
                    y = (canvas_size.height() - scaled_pixmap.height()) // 2 + self.image_offset.y()
                    
                    painter.drawPixmap(x, y, scaled_pixmap)
                finally:
                    painter.end()
                
                self.setPixmap(canvas)
            else:
                self.setPixmap(scaled_pixmap)
                
        except Exception as e:
            self.logger.error(f"更新显示失败: {e}")
        
    def wheelEvent(self, event):
        """处理鼠标滚轮事件 - 优化缩放响应"""
        try:
            # 检查是否按住Ctrl键进行精细缩放
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                # 精细缩放模式
                scale_step = 0.05
            else:
                scale_step = self.scale_step
                
            if event.angleDelta().y() > 0:
                # 向上滚动 - 放大
                if self.scale_factor < self.max_scale:
                    self._fit_to_window_mode = False
                    self.scale_factor = min(self.scale_factor + scale_step, self.max_scale)
                    self.update_display()
                    # 更新信息面板中的缩放信息
                    if hasattr(self, 'info_panel') and self.info_panel and self.info_panel.isVisible():
                        QTimer.singleShot(50, self.update_info_panel)
                else:
                    # 已达到最大缩放，显示提示
                    toast_floating(self, "📈 已达到最大缩放倍数 (3.0x)", 3000)
            else:
                # 向下滚动 - 缩小
                if self.scale_factor > self.min_scale:
                    self._fit_to_window_mode = False
                    self.scale_factor = max(self.scale_factor - scale_step, self.min_scale)
                    self.update_display()
                    # 更新信息面板中的缩放信息
                    if hasattr(self, 'info_panel') and self.info_panel and self.info_panel.isVisible():
                        QTimer.singleShot(50, self.update_info_panel)
                else:
                    # 已达到最小缩放，显示提示
                    toast_floating(self, "📉 已达到最小缩放倍数 (0.1x)", 3000)
                
        except Exception as e:
            self.logger.error(f"滚轮事件处理失败: {e}")
            
    def mousePressEvent(self, event):
        """处理鼠标按下事件 - 开始拖拽或关闭信息面板"""
        try:
            if event.button() == Qt.MouseButton.LeftButton:
                # 检查是否点击了信息面板区域或信息按钮
                if hasattr(self, 'info_panel') and self.info_panel and self.info_panel.isVisible():
                    panel_rect = self.info_panel.geometry()
                    click_pos = event.position().toPoint()
                    
                    # 检查是否点击了信息按钮
                    if hasattr(self, 'info_button') and self.info_button:
                        button_rect = self.info_button.geometry()
                        if button_rect.contains(click_pos):
                            # 点击了信息按钮，不处理拖拽，让按钮事件处理
                            return
                    
                    # 如果点击在面板外部（且不是信息按钮），隐藏面板
                    if not panel_rect.contains(click_pos):
                        self.info_panel.hide()
                        return
                    
                # 允许在任何缩放级别下拖拽图片
                self.dragging = True
                self.last_pan_point = event.position().toPoint()
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
        except Exception as e:
            self.logger.error(f"鼠标按下事件处理失败: {e}")
            
    def mouseMoveEvent(self, event):
        """处理鼠标移动事件 - 拖拽图片"""
        try:
            if self.dragging and self.last_pan_point:
                current_point = event.position().toPoint()
                delta = current_point - self.last_pan_point
                
                # 只有在移动距离超过阈值时才开始拖拽
                if (abs(delta.x()) > self.drag_threshold or 
                    abs(delta.y()) > self.drag_threshold):
                    
                    self.image_offset += delta
                    self.last_pan_point = current_point
                    self.update_display()
            else:
                # 在任何缩放级别下都显示可拖拽光标
                self.setCursor(Qt.CursorShape.OpenHandCursor)
                
        except Exception as e:
            self.logger.error(f"鼠标移动事件处理失败: {e}")
                
    def mouseReleaseEvent(self, event):
        """处理鼠标释放事件 - 结束拖拽"""
        try:
            if event.button() == Qt.MouseButton.LeftButton:
                self.dragging = False
                self.last_pan_point = None
                
                # 恢复可拖拽光标
                self.setCursor(Qt.CursorShape.OpenHandCursor)
        except Exception as e:
            self.logger.error(f"鼠标释放事件处理失败: {e}")
                
    def resizeEvent(self, event):
        """处理窗口大小改变事件"""
        super().resizeEvent(event)
        # 只在适应窗口模式下自动调整
        if self.original_pixmap and self._fit_to_window_mode:
            # 延迟调整，避免频繁刷新
            QTimer.singleShot(50, self.fit_to_window)
        
        # 重新定位信息按钮和面板
        QTimer.singleShot(10, self.position_info_button)
        QTimer.singleShot(10, self.position_info_panel)
            
    def show_image_info_panel(self):
        """显示图片信息面板"""
        try:
            if hasattr(self, 'info_panel') and self.info_panel:
                # 如果面板已存在，切换显示状态
                if self.info_panel.isVisible():
                    self.info_panel.hide()
                else:
                    self.update_info_panel()
                    self.info_panel.show()
            else:
                # 创建新的信息面板
                self.create_info_panel()
                
        except Exception as e:
            self.logger.error(f"显示图片信息面板失败: {e}")
            
    def create_info_panel(self):
        """创建图片信息面板"""
        try:
            from PyQt6.QtWidgets import QFrame, QVBoxLayout, QLabel, QPushButton
            from PyQt6.QtCore import Qt
            from PyQt6.QtGui import QFont
            
            # 创建半透明面板
            self.info_panel = QFrame(self)
            self.info_panel.setFixedWidth(450)
            self.info_panel.setStyleSheet("""
                QFrame {
                    background-color: rgba(0, 0, 0, 180);
                    border-radius: 8px;
                    border: 1px solid rgba(255, 255, 255, 50);
                }
                QLabel {
                    color: white;
                    background: transparent;
                    font-size: 12px;
                    padding: 2px 8px;
                }
                QLabel[objectName="info_title"] {
                    font-size: 14px;
                    font-weight: bold;
                    color: #4CAF50;
                    border-bottom: 1px solid rgba(255, 255, 255, 30);
                    margin-bottom: 5px;
                }
                QPushButton {
                    background-color: rgba(76, 175, 80, 180);
                    color: white;
                    border: none;
                    border-radius: 4px;
                    padding: 4px 8px;
                    font-size: 11px;
                    margin: 2px;
                }
                QPushButton:hover {
                    background-color: rgba(76, 175, 80, 220);
                }
            """)
            
            layout = QVBoxLayout(self.info_panel)
            layout.setContentsMargins(10, 10, 10, 10)
            layout.setSpacing(2)
            
            # 标题
            title_label = QLabel("📷 图片信息")
            title_label.setObjectName("info_title")
            layout.addWidget(title_label)
            
            # 基本信息标签
            self.info_labels = {}
            info_items = [
                ('filename', '文件名', ''),
                ('size', '文件大小', ''),
                ('dimensions', '图片尺寸', ''),
                ('scale', '当前缩放', ''),
                ('status', '分类状态', ''),
                ('categories', '所属类别', '')
            ]
            
            for key, title, value in info_items:
                label = QLabel(f"{title}: {value}")
                self.info_labels[key] = label
                layout.addWidget(label)
            
            # 更多信息按钮
            self.more_info_btn = QPushButton("▼ 更多信息")
            self.more_info_btn.clicked.connect(self.toggle_more_info)
            layout.addWidget(self.more_info_btn)
            
            # 详细信息区域（默认隐藏）
            self.detailed_info_widget = QFrame()
            self.detailed_info_layout = QVBoxLayout(self.detailed_info_widget)
            self.detailed_info_layout.setContentsMargins(0, 5, 0, 0)
            
            # 详细信息标签
            self.detailed_labels = {}
            
            # 特殊处理路径信息（带复制按钮）
            self.create_path_info_widget()
            
            # 其他详细信息
            other_detailed_items = [
                ('created', '创建时间', ''),
                ('modified', '修改时间', ''),
                ('display_mode', '显示模式', '')
            ]
            
            for key, title, value in other_detailed_items:
                label = QLabel(f"{title}: {value}")
                label.setWordWrap(True)
                self.detailed_labels[key] = label
                self.detailed_info_layout.addWidget(label)
            
            self.detailed_info_widget.hide()
            layout.addWidget(self.detailed_info_widget)
            
            # 设置面板位置（右上角）
            self.position_info_panel()
            
            # 更新信息并显示
            self.update_info_panel()
            self.info_panel.show()
            
        except Exception as e:
            self.logger.error(f"创建图片信息面板失败: {e}")
    
    def position_info_panel(self):
        """定位信息面板到右上角"""
        try:
            if hasattr(self, 'info_panel') and self.info_panel:
                panel_width = self.info_panel.width()
                x = self.width() - panel_width - 10
                y = 10
                self.info_panel.move(x, y)
        except Exception as e:
            self.logger.debug(f"定位信息面板失败: {e}")
    
    def toggle_more_info(self):
        """切换更多信息显示"""
        try:
            if self.detailed_info_widget.isVisible():
                self.detailed_info_widget.hide()
                self.more_info_btn.setText("▼ 更多信息")
                self.info_panel.setFixedHeight(self.info_panel.sizeHint().height())
            else:
                self.detailed_info_widget.show()
                self.more_info_btn.setText("▲ 收起")
                self.info_panel.setFixedHeight(self.info_panel.sizeHint().height())
        except Exception as e:
            self.logger.error(f"切换更多信息失败: {e}")
    
    def update_info_panel(self):
        """更新信息面板内容"""
        try:
            if not hasattr(self, 'info_panel') or not self.info_panel:
                return
                
            # 获取当前图片信息
            main_window = self.parent()
            while main_window and not hasattr(main_window, 'image_files'):
                main_window = main_window.parent()
            
            if not main_window or not hasattr(main_window, 'image_files') or not main_window.image_files:
                return
                
            if main_window.current_index < 0 or main_window.current_index >= len(main_window.image_files):
                return
                
            current_image_path = main_window.image_files[main_window.current_index]
            
            from PyQt6.QtCore import QFileInfo
            from pathlib import Path
            import os
            from datetime import datetime
            
            # 收集图片信息
            file_info = QFileInfo(str(current_image_path))
            file_stats = os.stat(str(current_image_path))
            
            # 更新基本信息
            self.info_labels['filename'].setText(f"文件名: {file_info.fileName()}")
            self.info_labels['size'].setText(f"文件大小: {self.format_file_size(file_stats.st_size)}")
            
            # 图片尺寸
            if self.original_pixmap:
                width = self.original_pixmap.width()
                height = self.original_pixmap.height()
                self.info_labels['dimensions'].setText(f"图片尺寸: {width} × {height}")
            else:
                self.info_labels['dimensions'].setText("图片尺寸: 未知")
            
            # 当前缩放
            self.info_labels['scale'].setText(f"当前缩放: {self.scale_factor:.1f}x")
            
            # 分类状态
            image_path_str = str(current_image_path)
            classification = main_window.classified_images.get(image_path_str)
            is_removed = image_path_str in main_window.removed_images
            
            if is_removed:
                self.info_labels['status'].setText("分类状态: 已移出")
                self.info_labels['categories'].setText("所属类别: 无")
            elif classification:
                if isinstance(classification, list) and len(classification) > 0:
                    # 多分类情况：显示已分类，类别显示所有类别名称
                    self.info_labels['status'].setText("分类状态: 已分类")
                    categories = ', '.join(classification)
                    self.info_labels['categories'].setText(f"所属类别: {categories}")
                elif isinstance(classification, str):
                    # 单分类情况：显示已分类，类别显示具体类别名称
                    self.info_labels['status'].setText("分类状态: 已分类")
                    self.info_labels['categories'].setText(f"所属类别: {classification}")
                else:
                    # 空列表或其他异常情况
                    self.info_labels['status'].setText("分类状态: 未处理")
                    self.info_labels['categories'].setText("所属类别: 无")
            else:
                self.info_labels['status'].setText("分类状态: 未处理")
                self.info_labels['categories'].setText("所属类别: 无")
            
            # 更新详细信息
            # 更新路径信息（使用QTextEdit）
            if hasattr(self, 'path_text_edit'):
                self.path_text_edit.setPlainText(file_info.absoluteFilePath())
            
            # 更新其他详细信息
            self.detailed_labels['created'].setText(f"创建时间: {datetime.fromtimestamp(file_stats.st_ctime).strftime('%Y-%m-%d %H:%M:%S')}")
            self.detailed_labels['modified'].setText(f"修改时间: {datetime.fromtimestamp(file_stats.st_mtime).strftime('%Y-%m-%d %H:%M:%S')}")
            self.detailed_labels['display_mode'].setText(f"显示模式: {'适应窗口' if self._fit_to_window_mode else '自由缩放'}")
            
        except Exception as e:
            self.logger.error(f"更新信息面板失败: {e}")
    
    def format_file_size(self, size_bytes):
        """格式化文件大小"""
        try:
            if size_bytes == 0:
                return "0 B"
            size_names = ["B", "KB", "MB", "GB"]
            import math
            i = int(math.floor(math.log(size_bytes, 1024)))
            p = math.pow(1024, i)
            s = round(size_bytes / p, 2)
            return f"{s} {size_names[i]}"
        except:
            return f"{size_bytes} B"
    
    
    def create_path_info_widget(self):
        """创建路径信息组件（带复制按钮）"""
        try:
            from PyQt6.QtWidgets import QHBoxLayout, QVBoxLayout, QTextEdit, QPushButton, QFrame, QLabel
            from PyQt6.QtCore import Qt
            
            # 创建路径信息容器
            path_container = QFrame()
            path_layout = QVBoxLayout(path_container)
            path_layout.setContentsMargins(0, 0, 0, 5)
            path_layout.setSpacing(3)
            
            # 路径标题
            path_title = QLabel("完整路径:")
            path_title.setStyleSheet("font-weight: bold; color: #4CAF50;")
            path_layout.addWidget(path_title)
            
            # 路径显示和复制按钮的容器
            path_content_layout = QHBoxLayout()
            path_content_layout.setContentsMargins(0, 0, 0, 0)
            path_content_layout.setSpacing(5)
            
            # 使用QTextEdit显示路径，支持完整显示和选择
            self.path_text_edit = QTextEdit()
            self.path_text_edit.setMaximumHeight(60)  # 限制高度但允许滚动
            self.path_text_edit.setMinimumHeight(40)
            self.path_text_edit.setReadOnly(True)
            self.path_text_edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            self.path_text_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            self.path_text_edit.setStyleSheet("""
                QTextEdit {
                    background-color: rgba(255, 255, 255, 20);
                    border: 1px solid rgba(255, 255, 255, 50);
                    border-radius: 4px;
                    padding: 4px;
                    font-size: 11px;
                    color: white;
                }
                QTextEdit:focus {
                    border-color: rgba(76, 175, 80, 150);
                }
            """)
            path_content_layout.addWidget(self.path_text_edit, 1)  # 占据大部分空间
            
            # 复制按钮
            copy_button = QPushButton("📋")
            copy_button.setFixedSize(30, 30)
            copy_button.setToolTip("复制完整路径到剪贴板")
            copy_button.setStyleSheet("""
                QPushButton {
                    background-color: rgba(76, 175, 80, 180);
                    color: white;
                    border: none;
                    border-radius: 4px;
                    font-size: 12px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: rgba(76, 175, 80, 220);
                }
                QPushButton:pressed {
                    background-color: rgba(76, 175, 80, 255);
                }
            """)
            copy_button.clicked.connect(self.copy_path_to_clipboard)
            path_content_layout.addWidget(copy_button)
            
            path_layout.addLayout(path_content_layout)
            
            # 将路径容器添加到详细信息布局
            self.detailed_info_layout.addWidget(path_container)
            
            # 保存引用以便后续更新
            self.path_container = path_container
            
        except Exception as e:
            self.logger.error(f"创建路径信息组件失败: {e}")
    
    def copy_path_to_clipboard(self):
        """复制路径到剪贴板"""
        try:
            from PyQt6.QtWidgets import QApplication
            
            if hasattr(self, 'path_text_edit'):
                path_text = self.path_text_edit.toPlainText()
                if path_text:
                    clipboard = QApplication.clipboard()
                    clipboard.setText(path_text)
                    # 显示复制成功提示
                    toast_floating(self, "📋 路径已复制到剪贴板", 2000)
                else:
                    toast_floating(self, "❌ 没有路径可复制", 2000)
            
        except Exception as e:
            self.logger.error(f"复制路径到剪贴板失败: {e}")
            toast_floating(self, "❌ 复制失败", 2000)


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
            from PyQt6.QtWidgets import QGridLayout

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
