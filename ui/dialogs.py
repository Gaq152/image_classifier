"""
对话框模块

包含应用程序使用的各种对话框组件。
"""

import logging
from pathlib import Path
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
                            QPushButton, QTextEdit, QListWidget, QListWidgetItem, 
                            QMessageBox, QTabWidget, QProgressBar, QApplication, 
                            QWidget, QTextBrowser)
from PyQt6.QtCore import Qt, pyqtSignal
from typing import Optional
import os
import sys
from PyQt6.QtGui import QKeySequence

from ..utils.file_operations import normalize_folder_name, retry_file_operation
from ..utils.exceptions import FileOperationError
from .._version_ import get_about_info, get_latest_version_info, VERSION_HISTORY, get_manifest_url
from ..core.update_utils import fetch_manifest, download_with_progress, sha256_file, launch_self_update
from .components.toast import toast_info, toast_success, toast_warning, toast_error


class CategoryShortcutDialog(QDialog):
    """类别快捷键设置对话框"""
    
    def __init__(self, config, category, parent=None):
        super().__init__(parent)
        self.config = config
        self.category = category
        self.logger = logging.getLogger(__name__)
        
        self.setWindowTitle(f'设置类别"{category}"的快捷键')
        self.setModal(True)
        
        layout = QVBoxLayout(self)
        
        # 创建快捷键编辑区域
        row = QHBoxLayout()
        label = QLabel('快捷键:')
        self.edit = QLineEdit(self.config.category_shortcuts.get(category, ''))
        self.edit.setReadOnly(True)
        self.edit.setPlaceholderText('点击此处按下新的快捷键')
        row.addWidget(label)
        row.addWidget(self.edit)
        layout.addLayout(row)
        
        # 添加说明标签
        tip_label = QLabel('支持单个按键或组合键(Ctrl+, Alt+, Shift+)\n按ESC清除快捷键')
        tip_label.setStyleSheet('color: gray;')
        layout.addWidget(tip_label)
        
        # 添加确定和取消按钮
        buttons = QHBoxLayout()
        ok_btn = QPushButton('确定')
        cancel_btn = QPushButton('取消')
        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        buttons.addWidget(ok_btn)
        buttons.addWidget(cancel_btn)
        layout.addLayout(buttons)
        
    def keyPressEvent(self, event):
        """处理按键事件"""
        try:
            if event.key() == Qt.Key.Key_Escape:
                self.edit.clear()
                if self.category in self.config.category_shortcuts:
                    del self.config.category_shortcuts[self.category]
                return
                
            # 获取修饰键
            modifiers = event.modifiers()
            key = event.key()
            
            # 忽略单独的修饰键
            if key in (Qt.Key.Key_Control, Qt.Key.Key_Alt, Qt.Key.Key_Shift):
                return
                
            # 构建快捷键文本
            key_text = QKeySequence(key).toString()
            if not key_text:
                return
                
            shortcut = ''
            if modifiers & Qt.KeyboardModifier.ControlModifier:
                shortcut += 'Ctrl+'
            if modifiers & Qt.KeyboardModifier.AltModifier:
                shortcut += 'Alt+'
            if modifiers & Qt.KeyboardModifier.ShiftModifier:
                shortcut += 'Shift+'
            shortcut += key_text
            
            # 检查快捷键是否可用
            if not self.config.is_shortcut_available(shortcut):
                # 详细检查冲突原因
                normalized_shortcut = self.config._normalize_shortcut(shortcut)
                
                # 获取主窗口用于显示Toast
                main_window = self.parent()
                while main_window and not hasattr(main_window, 'current_index'):
                    main_window = main_window.parent()
                toast_parent = main_window if main_window else self

                # 检查是否为保留快捷键
                if normalized_shortcut in self.config.reserved_shortcuts:
                    toast_warning(toast_parent, f'快捷键 "{shortcut}" 是系统保留快捷键，不能使用')
                else:
                    # 找出使用该快捷键的类别（大小写不敏感）
                    conflict_category = None
                    conflict_key = None
                    for cat, key in self.config.category_shortcuts.items():
                        if cat != self.category and self.config._normalize_shortcut(key) == normalized_shortcut:
                            conflict_category = cat
                            conflict_key = key
                            break

                    if conflict_category:
                        case_note = ""
                        if conflict_key != shortcut:
                            case_note = f"\n\n注意：该快捷键已以 \"{conflict_key}\" 的形式被使用。\n字母快捷键不区分大小写。"

                        toast_warning(toast_parent, f'快捷键 "{shortcut}" 已被类别 "{conflict_category}" 使用，请选择其他快捷键')
                    else:
                        toast_warning(toast_parent, f'快捷键 "{shortcut}" 已被占用，请选择其他快捷键')
                return
                
            # 统一存储格式：单字母快捷键存储为小写
            stored_shortcut = shortcut
            if len(shortcut) == 1 and shortcut.isalpha():
                stored_shortcut = shortcut.lower()
            elif '+' in shortcut:
                # 组合键，只将最后的字母部分转为小写
                parts = shortcut.split('+')
                if len(parts[-1]) == 1 and parts[-1].isalpha():
                    parts[-1] = parts[-1].lower()
                    stored_shortcut = '+'.join(parts)
            
            self.edit.setText(shortcut)  # 显示用户输入的原始格式
            self.config.category_shortcuts[self.category] = stored_shortcut  # 存储标准化格式

        except Exception as e:
            self.logger.error(f"处理快捷键事件失败: {e}")

    def accept(self):
        """确认按钮点击时的处理"""
        shortcut = self.edit.text().strip()
        if shortcut:
            # 获取主窗口用于显示Toast
            main_window = self.parent()
            while main_window and not hasattr(main_window, 'current_index'):
                main_window = main_window.parent()
            toast_parent = main_window if main_window else self
            toast_success(toast_parent, f'类别 "{self.category}" 快捷键已设置为 "{shortcut}"')

        # 调用父类的accept方法
        super().accept()


class AddCategoriesDialog(QDialog):
    """批量添加类别对话框"""
    
    def __init__(self, existing_categories, parent=None):
        super().__init__(parent)
        self.existing_categories = existing_categories
        self.added_categories = set()
        self.logger = logging.getLogger(__name__)
        self.initUI()
        
    def initUI(self):
        """初始化UI"""
        try:
            self.setWindowTitle('批量添加类别')
            self.setMinimumWidth(400)
            layout = QVBoxLayout(self)
            
            # 添加说明标签
            tip_label = QLabel('请输入类别名称，多个类别用逗号或换行分隔\n已存在的类别会被自动忽略')
            tip_label.setStyleSheet('color: gray;')
            layout.addWidget(tip_label)
            
            # 添加文本编辑框
            self.edit = QTextEdit()
            self.edit.setPlaceholderText('例如: 类别1, 类别2\n类别3\n类别4')
            self.edit.setMinimumHeight(100)
            layout.addWidget(self.edit)
            
            # 添加预览区域
            preview_group = QWidget()
            preview_layout = QVBoxLayout(preview_group)
            preview_layout.addWidget(QLabel('预览:'))
            self.preview_list = QListWidget()
            self.preview_list.setMaximumHeight(150)
            preview_layout.addWidget(self.preview_list)
            layout.addWidget(preview_group)
            
            # 添加按钮
            btn_layout = QHBoxLayout()
            add_btn = QPushButton('添加')
            add_btn.clicked.connect(self.add_categories)
            continue_btn = QPushButton('添加并继续')
            continue_btn.clicked.connect(self.add_and_continue)
            cancel_btn = QPushButton('取消')
            cancel_btn.clicked.connect(self.reject)
            btn_layout.addWidget(add_btn)
            btn_layout.addWidget(continue_btn)
            btn_layout.addWidget(cancel_btn)
            layout.addLayout(btn_layout)
            
            # 连接文本变化信号
            self.edit.textChanged.connect(self.update_preview)
            
        except Exception as e:
            self.logger.error(f"初始化添加类别对话框UI失败: {e}")
        
    def update_preview(self):
        """更新预览列表"""
        try:
            self.preview_list.clear()
            text = self.edit.toPlainText()
            if not text.strip():
                return
                
            # 分割文本并处理
            categories = set()
            for line in text.split('\n'):  # 修复：使用正确的换行符
                # 同时支持中英文逗号
                parts = []
                for part in line.replace('，', ',').split(','):
                    parts.append(part)
                for cat in parts:
                    cat = normalize_folder_name(cat.strip())  # 添加规范化处理
                    if cat and cat not in self.existing_categories and cat not in categories:
                        categories.add(cat)
                        item = QListWidgetItem(cat)
                        self.preview_list.addItem(item)
        except Exception as e:
            self.logger.error(f"更新预览失败: {e}")
        
    def add_categories(self):
        """添加类别并关闭对话框"""
        if self._add_categories():
            self.accept()
        
    def _add_categories(self):
        """实际添加类别的逻辑"""
        try:
            text = self.edit.toPlainText()
            if not text.strip():
                return False
                
            # 分割文本并处理
            added = False
            errors = []  # 记录错误信息
            
            for line in text.split('\n'):  # 修复：使用正确的换行符
                # 同时支持中英文逗号
                parts = []
                for part in line.replace('，', ',').split(','):
                    parts.append(part)
                for cat in parts:
                    chinese_name = normalize_folder_name(cat.strip())  # 规范化类别名称
                    if not chinese_name:  # 跳过空类别名
                        continue
                        
                    # 检查类别名称长度
                    if len(chinese_name) > 50:
                        errors.append(f'类别名称 "{chinese_name}" 超过50个字符')
                        continue
                        
                    if chinese_name in self.existing_categories:
                        toast_warning(self, f'类别 "{chinese_name}" 已存在，将跳过')
                        continue
                        
                    try:
                        # 创建目录(直接使用类别名)
                        parent = self.parent()
                        if parent and hasattr(parent, 'current_dir'):
                            category_dir = Path(parent.current_dir).parent / chinese_name
                            def create_dir():
                                category_dir.mkdir(exist_ok=True)
                            retry_file_operation(create_dir)
                            self.added_categories.add(chinese_name)
                            self.existing_categories.add(chinese_name)
                            added = True
                            self.logger.info(f"成功创建类别目录: {category_dir}")
                        else:
                            errors.append(f'无法获取父目录信息')
                    except Exception as e:
                        errors.append(f'创建类别 "{chinese_name}" 失败: {str(e)}')
                        continue
            
            # 如果有错误但也有成功添加的类别
            if errors and added:
                error_msg = '\n'.join(errors)
                toast_warning(self, f'部分类别添加失败: {error_msg}')
            # 如果只有错误没有成功添加的类别
            elif errors and not added:
                error_msg = '\n'.join(errors)
                toast_error(self, f'添加类别失败: {error_msg}')
                return False
                
            if added:
                # 强制刷新父窗口的类别列表
                parent = self.parent()
                if parent and hasattr(parent, 'load_categories'):
                    QApplication.processEvents()  # 处理挂起的事件
                    parent.load_categories()
                if parent and hasattr(parent, 'update_category_buttons'):
                    parent.update_category_buttons()
                    
            return added
                
        except Exception as e:
            self.logger.error(f"添加类别失败: {e}")
            toast_error(self, f'添加类别失败: {str(e)}')
            return False

    def add_and_continue(self):
        """添加类别并清空输入框"""
        try:
            if self._add_categories():
                # 强制刷新父窗口类别按钮
                parent = self.parent()
                if parent and hasattr(parent, 'load_categories'):
                    QApplication.processEvents()  # 处理挂起的事件
                    parent.load_categories()
                if parent and hasattr(parent, 'update_category_buttons'):
                    parent.update_category_buttons()
                    
                # 清空输入框并更新预览
                self.edit.clear()
                self.preview_list.clear()
                self.edit.setFocus()
                
                # 重置已添加类别集合
                self.added_categories = set()
                
                # 强制更新UI
                self.update()
                QApplication.processEvents()
        except Exception as e:
            self.logger.error(f"添加并继续失败: {e}")


class TabbedHelpDialog(QDialog):
    """带标签页的帮助对话框"""
    
    def __init__(self, version, parent=None, config=None):
        super().__init__(parent)
        self.version = version
        self.config = getattr(parent, 'config', None) if config is None else config
        self.logger = logging.getLogger(__name__)
        self.initUI()
    
    def _get_resource_path(self, relative_path):
        """获取资源文件路径，兼容开发环境和打包环境"""
        try:
            import sys
            from pathlib import Path
            # PyInstaller 打包后的临时目录
            if hasattr(sys, '_MEIPASS'):
                base_path = Path(sys._MEIPASS)
                resource_path = base_path / relative_path
                if resource_path.exists():
                    return resource_path
                
            # 开发环境 - 从当前文件位置查找
            base_path = Path(__file__).parent.parent
            resource_path = base_path / relative_path
            if resource_path.exists():
                return resource_path
                
            # 尝试从程序运行目录查找
            base_path = Path.cwd()
            resource_path = base_path / relative_path
            if resource_path.exists():
                return resource_path
                
            return None
        except Exception:
            return None
        
    def initUI(self):
        """初始化UI"""
        try:
            self.setWindowTitle('帮助和关于')
            self.setMinimumSize(700, 500)
            self.setModal(True)
            
            # 设置对话框整体样式
            self.setStyleSheet("""
                QDialog {
                    background-color: #F8F9FA;
                    color: #2C3E50;
                }
                QTabWidget {
                    background-color: #FFFFFF;
                    border: 1px solid #BDC3C7;
                    border-radius: 6px;
                }
                QTabWidget::pane {
                    background-color: #FFFFFF;
                    border: 1px solid #BDC3C7;
                    border-radius: 6px;
                    top: -1px;
                }
                QTabBar::tab {
                    background-color: #ECF0F1;
                    color: #2C3E50;
                    border: 1px solid #BDC3C7;
                    padding: 8px 16px;
                    margin-right: 2px;
                    border-top-left-radius: 6px;
                    border-top-right-radius: 6px;
                    font-weight: bold;
                    min-width: 80px;
                }
                QTabBar::tab:selected {
                    background-color: #3498DB;
                    color: white;
                    border-bottom-color: #3498DB;
                }
                QTabBar::tab:hover {
                    background-color: #D5DBDB;
                }
                QTabBar::tab:selected:hover {
                    background-color: #2980B9;
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
                QPushButton#clearCacheBtn {
                    background-color: #E74C3C;
                }
                QPushButton#clearCacheBtn:hover {
                    background-color: #C0392B;
                }
            """)
            
            layout = QVBoxLayout(self)
            
            # 创建标签页控件
            tab_widget = QTabWidget()
            
            # 顶部操作区：更新相关
            top_btn_bar = QHBoxLayout()
            check_btn = QPushButton('检查更新')
            # 使用带平滑动画的拨动开关（自绘QSS实现简单动画感）
            from PyQt6.QtWidgets import QCheckBox
            auto_chk = QCheckBox('')
            auto_chk.setToolTip('启动时自动检查更新')
            auto_chk.setStyleSheet('''
                QCheckBox { spacing: 8px; }
                QCheckBox::indicator {
                    width: 44px; height: 24px;
                }
                QCheckBox::indicator:unchecked {
                    border-radius: 12px;
                    background-color: #cfd8dc;
                }
                QCheckBox::indicator:checked {
                    border-radius: 12px;
                    background-color: #66bb6a;
                }
            ''')
            auto_enabled = True
            if self.config and hasattr(self.config, 'auto_update_enabled'):
                auto_enabled = bool(self.config.auto_update_enabled)
            auto_chk.setChecked(auto_enabled)
            def toggle_auto():
                if not self.config:
                    return
                self.config.auto_update_enabled = bool(auto_chk.isChecked())
                try:
                    self.config.save_config()
                except Exception as e:
                    self.logger.error(f"保存自动更新配置失败: {e}")
            auto_chk.clicked.connect(toggle_auto)
            check_btn.clicked.connect(self._handle_check_update)
            top_btn_bar.addWidget(check_btn)
            top_btn_bar.addStretch()
            # 右侧只显示拨动开关和标签，不重复文字
            auto_label = QLabel('自动检查')
            top_btn_bar.addWidget(auto_label)
            top_btn_bar.addWidget(auto_chk)

            layout.addLayout(top_btn_bar)

            # 添加快速入门标签页
            quick_start_tab = self.create_quick_start_tab()
            tab_widget.addTab(quick_start_tab, '🚀 快速入门')
            
            # 添加详细帮助标签页
            help_tab = self.create_help_tab()
            tab_widget.addTab(help_tab, '📖 使用指南')
            
            # 添加高级功能标签页
            advanced_tab = self.create_advanced_tab()
            tab_widget.addTab(advanced_tab, '⚡ 高级功能')
            
            # 添加常见问题标签页
            faq_tab = self.create_faq_tab()
            tab_widget.addTab(faq_tab, '❓ 常见问题')
            
            # 添加关于标签页
            about_tab = self.create_about_tab()
            tab_widget.addTab(about_tab, 'ℹ️ 关于')
            
            layout.addWidget(tab_widget)
            
            # 添加关闭按钮
            button_layout = QHBoxLayout()
            
            # 添加清理SMB缓存按钮
            clear_cache_btn = QPushButton('🗑️ 清理SMB缓存')
            clear_cache_btn.setObjectName("clearCacheBtn")
            clear_cache_btn.clicked.connect(self.clear_smb_cache)
            button_layout.addWidget(clear_cache_btn)
            
            button_layout.addStretch()
            
            close_btn = QPushButton('✖️ 关闭')
            close_btn.clicked.connect(self.accept)
            button_layout.addWidget(close_btn)
            
            layout.addLayout(button_layout)
            
        except Exception as e:
            self.logger.error(f"初始化帮助对话框UI失败: {e}")

    def _handle_check_update(self, suppress_if_latest: bool = False):
        try:
            endpoint = None
            token = ''
            if self.config:
                endpoint = getattr(self.config, 'update_endpoint', None)
                token = getattr(self.config, 'update_token', '')
            if not endpoint:
                endpoint = get_manifest_url(latest=True)

            self.logger.debug(f"更新检查：开始，endpoint={endpoint}")
            manifest = fetch_manifest(endpoint, token or None)
            new_ver = str(manifest.get('version', '')).strip()
            url = str(manifest.get('url', '')).strip()
            sha256 = str(manifest.get('sha256', '')).strip()
            size_bytes = int(manifest.get('size_bytes', 0) or 0)
            notes = str(manifest.get('notes', '')).strip()
            display_name = str(manifest.get('display_name', '')).strip()
            self.logger.info(f"检查更新：发现新版本 v{new_ver}")
            display_name = str(manifest.get('display_name', '')).strip()

            from .._version_ import compare_version, __version__
            if not new_ver or compare_version(new_ver, __version__) <= 0:
                if not suppress_if_latest:
                    toast_info(self, '当前已是最新版本')
                return

            # 发现新版本，显示Toast通知
            toast_warning(self, f'发现新版本 v{new_ver}')

            size_mb = f"{size_bytes/1024/1024:.1f} MB" if size_bytes else "未知"
            msg = f"发现新版本: v{new_ver}\n大小: {size_mb}\n\n更新说明:\n{notes or '无'}\n\n是否立即下载并更新？"
            reply = self._ask_yes_no('发现新版本', msg)
            if reply != QMessageBox.StandardButton.Yes:
                self.logger.info("检查更新：用户选择暂不更新")
                return

            # 下载到程序目录下的 update 子目录，确保有权限；失败则回退到 TEMP
            exe_dir = Path(sys.executable).parent
            update_dir = exe_dir / 'update'
            try:
                update_dir.mkdir(parents=True, exist_ok=True)
                # 权限探测
                test_file = update_dir / '.perm_test'
                test_file.write_text('ok', encoding='utf-8')
                test_file.unlink(missing_ok=True)
                dest_root = update_dir
            except Exception:
                dest_root = Path(os.getenv('TEMP') or Path.cwd())

            # 优先使用 manifest.display_name（中文友好），否则从 URL 解码
            try:
                from urllib.parse import urlparse, unquote
                parsed = urlparse(url)
                url_name = unquote(Path(parsed.path).name)
            except Exception:
                url_name = ''
            fname = display_name or url_name or f"图像分类工具_v{new_ver}.exe"
            dest = dest_root / fname

            progress_dialog = QDialog(self)
            progress_dialog.setWindowTitle('下载更新')
            p_layout = QVBoxLayout(progress_dialog)
            p_label = QLabel('正在下载更新包...')
            p_bar = QProgressBar()
            p_bar.setRange(0, 0)
            p_layout.addWidget(p_label)
            p_layout.addWidget(p_bar)
            progress_dialog.setModal(True)
            progress_dialog.show()
            QApplication.processEvents()

            def on_progress(done: int, total: Optional[int]):
                if total and total > 0:
                    p_bar.setRange(0, total)
                    p_bar.setValue(done)
                else:
                    p_bar.setRange(0, 0)
                QApplication.processEvents()

            try:
                self.logger.debug("更新下载：开始")
                download_with_progress(url, dest, token or None, on_progress)
                self.logger.info("更新下载：完成")
            finally:
                progress_dialog.close()

            # 校验哈希
            if sha256:
                self.logger.debug("更新校验：开始")
                actual = sha256_file(dest)
                if actual.lower() != sha256.lower():
                    toast_error(self, f'更新失败: 文件校验失败')
                    self.logger.error(f"更新校验：失败 expected={sha256} actual={actual}")
                    try:
                        dest.unlink(missing_ok=True)
                    except Exception:
                        pass
                    return
                self.logger.debug("更新校验：通过")

            # 生成更新脚本，但不立即执行；由用户确认是否重启
            exe_path = Path(sys.executable)
            self.logger.debug("更新安装：准备安装脚本")
            batch_path = launch_self_update(exe_path, dest)

            # 记录待更新信息到配置
            if self.config:
                self.config.pending_update = {
                    'version': new_ver,
                    'download_path': str(dest),
                    'batch_path': str(batch_path),
                    'sha256': sha256,
                }
                try:
                    self.config.save_config()
                except Exception as e:
                    self.logger.debug(f"保存pending_update失败: {e}")

            # 询问是否立即重启更新
            reply = self._ask_yes_no(
                '更新下载完成',
                '更新包已准备就绪，是否立即重启并完成更新？\n\n选择“取消”将暂不重启，下次启动会继续提示。'
            )
            if reply == QMessageBox.StandardButton.Yes:
                # 启动批处理并退出
                try:
                    import subprocess
                    # 将已下载的新包绝对路径作为参数传递给 update.bat
                    subprocess.Popen(["cmd", "/c", "start", "", str(batch_path), str(dest)], shell=False)
                    self.logger.info("更新安装：已启动安装脚本")
                except Exception as e:
                    toast_error(self, f'更新失败: 无法启动更新程序')
                    self.logger.error(f"更新安装：启动脚本失败 {e}")
                    return
                # 尝试关闭主窗口并处理事件，给批处理释放句柄的时间
                try:
                    if self.parent():
                        self.parent().close()
                except Exception:
                    pass
                QApplication.processEvents()
                # 立即退出进程，确保释放可执行文件句柄
                try:
                    self.logger.debug("更新安装：应用即将退出以释放句柄")
                    os._exit(0)
                except Exception:
                    QApplication.quit()
            else:
                self.logger.info("更新已准备：用户选择稍后安装")
                toast_info(self, '已保存更新包，稍后可在帮助中手动执行更新')
        except Exception as e:
            self.logger.error(f"检查/更新失败: {e}")
            toast_error(self, f'检查更新失败: {str(e)}')
        
    def clear_smb_cache(self):
        """清理SMB缓存"""
        try:
            cache_dir = Path.home() / '.image_classifier_cache'
            if cache_dir.exists():
                import shutil
                shutil.rmtree(cache_dir)
                toast_success(self, 'SMB缓存已清理完成')
            else:
                toast_info(self, '未发现SMB缓存文件')
        except Exception as e:
            self.logger.error(f"清理SMB缓存失败: {e}")
            toast_error(self, f'清理SMB缓存失败: {e}')
    
    def _show_styled_message(self, msg_type, title, text):
        """显示样式化的消息框"""
        from PyQt6.QtWidgets import QMessageBox
        from PyQt6.QtGui import QIcon
        
        msgBox = QMessageBox(self)
        if msg_type == '信息':
            msgBox.setIcon(QMessageBox.Icon.Information)
        elif msg_type == '警告':
            msgBox.setIcon(QMessageBox.Icon.Warning)
        elif msg_type == '错误':
            msgBox.setIcon(QMessageBox.Icon.Critical)
            
        msgBox.setWindowTitle(title)
        msgBox.setText(text)
        
        # 设置程序图标
        try:
            icon_path = self._get_resource_path('assets/icon.ico')
            if icon_path and icon_path.exists():
                msgBox.setWindowIcon(QIcon(str(icon_path)))
        except Exception:
            pass
        
        # 设置美化样式
        msgBox.setStyleSheet("""
            QMessageBox {
                background-color: #F8F9FA;
                color: #2C3E50;
                border: 1px solid #BDC3C7;
                border-radius: 8px;
                font-size: 14px;
            }
            QMessageBox QLabel {
                color: #2C3E50;
                font-size: 14px;
                padding: 10px;
            }
            QMessageBox QPushButton {
                background-color: #3498DB;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 13px;
                font-weight: bold;
                min-width: 80px;
            }
            QMessageBox QPushButton:hover {
                background-color: #2980B9;
            }
            QMessageBox QPushButton:pressed {
                background-color: #21618C;
            }
        """)
        
        # 中文化按钮
        msgBox.setStandardButtons(QMessageBox.StandardButton.Ok)
        msgBox.button(QMessageBox.StandardButton.Ok).setText("确定")
        
        msgBox.exec()

    def _ask_yes_no(self, title: str, text: str):
        from PyQt6.QtWidgets import QMessageBox
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setText(text)
        # 统一图标/样式
        box.setIcon(QMessageBox.Icon.Question)
        try:
            icon_path = self._get_resource_path('assets/icon.ico')
            if icon_path and icon_path.exists():
                from PyQt6.QtGui import QIcon
                box.setWindowIcon(QIcon(str(icon_path)))
        except Exception:
            pass
        # 样式
        box.setStyleSheet("""
            QMessageBox {
                background-color: #F8F9FA;
                color: #2C3E50;
                border: 1px solid #BDC3C7;
                border-radius: 8px;
                font-size: 14px;
            }
            QMessageBox QLabel {
                color: #2C3E50;
                font-size: 14px;
                padding: 10px;
            }
            QMessageBox QPushButton {
                background-color: #3498DB;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 13px;
                font-weight: bold;
                min-width: 80px;
            }
            QMessageBox QPushButton:hover { background-color: #2980B9; }
            QMessageBox QPushButton:pressed { background-color: #21618C; }
        """)
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        # 中文化按钮
        yes_btn = box.button(QMessageBox.StandardButton.Yes)
        no_btn = box.button(QMessageBox.StandardButton.No)
        if yes_btn:
            yes_btn.setText("确定")
        if no_btn:
            no_btn.setText("取消")
        return box.exec()
        
    def create_quick_start_tab(self):
        """创建快速入门标签页"""
        from PyQt6.QtWidgets import QWidget, QTextBrowser
        
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        text_browser = QTextBrowser()
        
        quick_start_text = '''
        <h2>🚀 快速入门指南</h2>
        
        <div style="background-color: #e3f2fd; padding: 15px; border-radius: 8px; margin: 10px 0;">
        <h3>🎯 三步快速开始</h3>
        <ol style="font-size: 16px; line-height: 1.8;">
        <li><b>📁 选择文件夹</b>：点击"打开目录"选择包含图片的文件夹</li>
        <li><b>🏷️ 创建类别</b>：点击"新增类别"添加分类标签</li>
        <li><b>🖱️ 开始分类</b>：双击类别按钮或使用快捷键分类图片</li>
        </ol>
        </div>
        
        <h3>🖼️ 支持的图片格式</h3>
        <div style="background-color: #f3e5f5; padding: 10px; border-radius: 6px;">
        <span style="background-color: #4caf50; color: white; padding: 3px 8px; border-radius: 3px; margin-right: 5px;">JPG</span>
        <span style="background-color: #2196f3; color: white; padding: 3px 8px; border-radius: 3px; margin-right: 5px;">JPEG</span>
        <span style="background-color: #ff9800; color: white; padding: 3px 8px; border-radius: 3px; margin-right: 5px;">PNG</span>
        <span style="background-color: #9c27b0; color: white; padding: 3px 8px; border-radius: 3px; margin-right: 5px;">BMP</span>
        <span style="background-color: #607d8b; color: white; padding: 3px 8px; border-radius: 3px; margin-right: 5px;">GIF</span>
        <span style="background-color: #795548; color: white; padding: 3px 8px; border-radius: 3px;">TIFF</span>
        </div>
        
        <h3>⚡ 核心操作</h3>
        <table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse; width: 100%; margin: 10px 0; border: 1px solid #ddd;">
        <tr style="background-color: #f8f9fa;">
        <th style="width: 25%; padding: 8px; border: 1px solid #ddd;">操作</th>
        <th style="width: 35%; padding: 8px; border: 1px solid #ddd;">方法</th>
        <th style="width: 40%; padding: 8px; border: 1px solid #ddd;">说明</th>
        </tr>
        <tr>
        <td style="padding: 8px; border: 1px solid #ddd;">🖼️ 浏览图片</td>
        <td style="padding: 8px; border: 1px solid #ddd;">← → 键 或 鼠标点击</td>
        <td style="padding: 8px; border: 1px solid #ddd;">在图片列表中前后导航</td>
        </tr>
        <tr>
        <td style="padding: 8px; border: 1px solid #ddd;">🏷️ 选择类别</td>
        <td style="padding: 8px; border: 1px solid #ddd;">↑ ↓ 键</td>
        <td style="padding: 8px; border: 1px solid #ddd;">在类别列表中上下切换选择</td>
        </tr>
        <tr>
        <td style="padding: 8px; border: 1px solid #ddd;">📁 分类图片</td>
        <td style="padding: 8px; border: 1px solid #ddd;">双击类别按钮 或 Enter键</td>
        <td style="padding: 8px; border: 1px solid #ddd;">将当前图片分类到选中类别</td>
        </tr>
        <tr>
        <td style="padding: 8px; border: 1px solid #ddd;">🔍 缩放图片</td>
        <td style="padding: 8px; border: 1px solid #ddd;">鼠标滚轮 或 Ctrl +/-</td>
        <td style="padding: 8px; border: 1px solid #ddd;">放大缩小查看图片细节</td>
        </tr>
        <tr>
        <td style="padding: 8px; border: 1px solid #ddd;">🖱️ 移动图片</td>
        <td style="padding: 8px; border: 1px solid #ddd;">鼠标左键拖拽</td>
        <td style="padding: 8px; border: 1px solid #ddd;">移动图片查看不同区域</td>
        </tr>
        <tr>
        <td style="padding: 8px; border: 1px solid #ddd;">🗑️ 移出图片</td>
        <td style="padding: 8px; border: 1px solid #ddd;">Delete 键</td>
        <td style="padding: 8px; border: 1px solid #ddd;">将图片移到移出目录</td>
        </tr>
        </table>
        
        <h3>💡 高效使用技巧</h3>
        <ul style="line-height: 2;">
        <li><b>🎹 使用快捷键</b>：按数字键 1-9 快速分类到对应类别</li>
        <li><b>🔄 文件模式切换</b>：点击工具栏的"复制模式"/"移动模式"按钮切换</li>
        <li><b>🔀 多分类模式</b>：点击"🔂 单分类模式"按钮开启多分类，一图多标签</li>
        <li><b>⏎ 回车确认</b>：选中类别后按 Enter 键快速分类</li>
        <li><b>🔄 自动同步</b>：程序会自动检测外部文件变化</li>
        <li><b>💾 状态保存</b>：工作状态会自动保存，重启后恢复</li>
        </ul>
        
        <div style="background-color: #fff3e0; padding: 15px; border-radius: 8px; border-left: 4px solid #ff9800; margin: 20px 0;">
        <h4>🔥 专业提示</h4>
        <p>• 使用右键点击类别按钮可以自定义快捷键<br>
        • 按 F5 键可以刷新文件列表同步外部变化<br>
        • 按 Ctrl+F 键可以让图片适应窗口大小<br>
        • 支持批量添加类别，用逗号分隔多个类别名<br>
        • <b>🔀 多分类模式</b>：再次点击已分类的类别可取消分类<br>
        • <b>蓝色按钮</b>：表示当前图片属于该类别（多分类模式下）</p>
        </div>
        '''
        
        # 设置样式确保文本颜色对比度
        text_browser.setStyleSheet("""
            QTextBrowser {
                background-color: white;
                color: black;
                selection-background-color: #0078d4;
                selection-color: white;
            }
        """)
        
        text_browser.setHtml(quick_start_text)
        layout.addWidget(text_browser)
        
        return widget
        
    def create_help_tab(self):
        """创建帮助标签页"""
        from PyQt6.QtWidgets import QWidget, QTextBrowser
        
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        text_browser = QTextBrowser()
        
        help_text = '''
        <h2>📖 详细使用指南</h2>
        
        <h3>�️ 文件管理</h3>
        <h4>📁 目录操作</h4>
        <ul>
        <li><b>打开目录</b>：选择包含待分类图片的根目录</li>
        <li><b>子目录处理</b>：程序会递归扫描所有子目录中的图片</li>
        <li><b>目录结构</b>：分类后的图片会按类别名创建对应文件夹</li>
        <li><b>移出目录</b>：删除的图片会移动到 "remove" 文件夹</li>
        </ul>
        
        <h4>📋 类别管理</h4>
        <ul>
        <li><b>新增类别</b>：单个添加或批量添加（逗号分隔）</li>
        <li><b>编辑类别</b>：右键类别按钮选择"编辑"</li>
        <li><b>删除类别</b>：右键类别按钮选择"删除"</li>
        <li><b>快捷键设置</b>：右键类别按钮选择"设置快捷键"</li>
        <li><b>类别限制</b>：类别名最长50个字符，支持中英文</li>
        </ul>
        
        <h3>🖼️ 图片浏览与操作</h3>
        <h4>🔍 视图控制</h4>
        <table border="1" cellpadding="6" cellspacing="0" style="border-collapse: collapse; width: 100%; border: 1px solid #ddd;">
        <tr style="background-color: #f8f9fa;">
        <th style="padding: 6px; border: 1px solid #ddd;">功能</th>
        <th style="padding: 6px; border: 1px solid #ddd;">操作方法</th>
        <th style="padding: 6px; border: 1px solid #ddd;">快捷键</th>
        <th style="padding: 6px; border: 1px solid #ddd;">详细说明</th>
        </tr>
        <tr>
        <td style="padding: 6px; border: 1px solid #ddd;">适应窗口</td>
        <td style="padding: 6px; border: 1px solid #ddd;">菜单/快捷键</td>
        <td style="padding: 6px; border: 1px solid #ddd;">Ctrl+F</td>
        <td style="padding: 6px; border: 1px solid #ddd;">自动调整图片大小适应显示区域</td>
        </tr>
        <tr>
        <td style="padding: 6px; border: 1px solid #ddd;">放大图片</td>
        <td style="padding: 6px; border: 1px solid #ddd;">滚轮向上/菜单</td>
        <td style="padding: 6px; border: 1px solid #ddd;">Ctrl + =</td>
        <td style="padding: 6px; border: 1px solid #ddd;">放大图片，最大3倍</td>
        </tr>
        <tr>
        <td style="padding: 6px; border: 1px solid #ddd;">缩小图片</td>
        <td style="padding: 6px; border: 1px solid #ddd;">滚轮向下/菜单</td>
        <td style="padding: 6px; border: 1px solid #ddd;">Ctrl + -</td>
        <td style="padding: 6px; border: 1px solid #ddd;">缩小图片显示</td>
        </tr>
        <tr>
        <td style="padding: 6px; border: 1px solid #ddd;">原始大小</td>
        <td style="padding: 6px; border: 1px solid #ddd;">菜单/快捷键</td>
        <td style="padding: 6px; border: 1px solid #ddd;">Ctrl + 0</td>
        <td style="padding: 6px; border: 1px solid #ddd;">显示图片100%原始大小</td>
        </tr>
        <tr>
        <td style="padding: 6px; border: 1px solid #ddd;">拖拽移动</td>
        <td style="padding: 6px; border: 1px solid #ddd;">鼠标左键拖拽</td>
        <td style="padding: 6px; border: 1px solid #ddd;">-</td>
        <td style="padding: 6px; border: 1px solid #ddd;">移动图片查看不同区域</td>
        </tr>
        </table>
        
        <h4>📂 分类操作</h4>
        <ul>
        <li><b>复制模式</b>：保留原文件，复制到目标类别文件夹（默认）</li>
        <li><b>移动模式</b>：直接移动文件到目标类别文件夹</li>
        <li><b>分类方法</b>：双击类别按钮、使用快捷键或按回车键</li>
        <li><b>多分类模式</b>：同一张图片可分配到多个类别</li>
        </ul>
        
        <h4>🔀 分类模式详解</h4>
        <div style="background-color: #e8f5e8; padding: 15px; border-radius: 8px; margin: 10px 0; border-left: 4px solid #4caf50;">
        <h5 style="color: #2e7d32; margin: 0 0 10px 0;">🔂 单分类模式（默认）</h5>
        <ul style="margin: 5px 0; padding-left: 20px;">
        <li>一张图片只能属于一个类别</li>
        <li>重新分类会自动从旧类别移动到新类别</li>
        <li>类别按钮显示绿色背景表示已分类</li>
        <li>适合传统的文件整理需求</li>
        </ul>
        </div>
        
        <div style="background-color: #e3f2fd; padding: 15px; border-radius: 8px; margin: 10px 0; border-left: 4px solid #2196f3;">
        <h5 style="color: #1565c0; margin: 0 0 10px 0;">🔀 多分类模式（新功能）</h5>
        <ul style="margin: 5px 0; padding-left: 20px;">
        <li><b>灵活分类</b>：一张图片可以同时属于多个类别</li>
        <li><b>切换方式</b>：点击工具栏"🔂 单分类模式"按钮切换</li>
        <li><b>分类操作</b>：点击类别按钮添加分类，再次点击取消分类</li>
        <li><b>视觉反馈</b>：多分类的类别按钮显示蓝色背景</li>
        <li><b>应用场景</b>：标签化管理，如"风景+日落"、"人物+室内"等</li>
        </ul>
        
        <table border="1" cellpadding="6" cellspacing="0" style="border-collapse: collapse; width: 100%; margin: 10px 0; border: 1px solid #ddd;">
        <tr style="background-color: #f8f9fa;">
        <th style="padding: 6px; border: 1px solid #ddd;">操作</th>
        <th style="padding: 6px; border: 1px solid #ddd;">多分类模式行为</th>
        <th style="padding: 6px; border: 1px solid #ddd;">单分类模式行为</th>
        </tr>
        <tr>
        <td style="padding: 6px; border: 1px solid #ddd;">首次分类</td>
        <td style="padding: 6px; border: 1px solid #ddd;">添加到类别列表</td>
        <td style="padding: 6px; border: 1px solid #ddd;">直接分类到该类别</td>
        </tr>
        <tr>
        <td style="padding: 6px; border: 1px solid #ddd;">已分类的类别</td>
        <td style="padding: 6px; border: 1px solid #ddd;">从列表中移除（取消分类）</td>
        <td style="padding: 6px; border: 1px solid #ddd;">不执行操作</td>
        </tr>
        <tr>
        <td style="padding: 6px; border: 1px solid #ddd;">其他类别</td>
        <td style="padding: 6px; border: 1px solid #ddd;">同时添加到类别列表</td>
        <td style="padding: 6px; border: 1px solid #ddd;">从旧类别移动到新类别</td>
        </tr>
        </table>
        </div>
        
        <div style="background-color: #fff3e0; padding: 15px; border-radius: 8px; border-left: 4px solid #ff9800; margin: 20px 0;">
        <h5 style="color: #ef6c00; margin: 0 0 10px 0;">💡 多分类模式使用技巧</h5>
        <ul style="margin: 5px 0; padding-left: 20px;">
        <li><b>标签化思维</b>：把类别当作标签，一张图片可以有多个标签</li>
        <li><b>快速取消</b>：再次点击已分类的类别按钮可快速取消该分类</li>
        <li><b>状态查看</b>：蓝色背景的类别按钮表示当前图片属于该类别</li>
        <li><b>物理文件</b>：图片会被复制到每个分类的文件夹中</li>
        <li><b>模式切换</b>：可随时在单分类和多分类模式间切换</li>
        </ul>
        </div>
        
        <h3>� 状态与统计</h3>
        <h4>🏷️ 状态标识</h4>
        <ul>
        <li><b>🟢 已分类</b>：图片已成功分类到某个类别</li>
        <li><b>🔴 已移出</b>：图片已移动到移出目录</li>
        <li><b>🟡 未处理</b>：尚未分类的图片</li>
        <li><b>📊 进度显示</b>：底部状态栏显示处理进度</li>
        </ul>
        
        <h4>📈 实时统计</h4>
        <ul>
        <li><b>总数统计</b>：显示图片总数和处理进度</li>
        <li><b>类别统计</b>：每个类别的图片数量</li>
        <li><b>效率统计</b>：分类速度和剩余时间估计</li>
        </ul>
        
        <h3>� 同步与刷新</h3>
        <ul>
        <li><b>自动同步</b>：程序会定期检测外部文件变化</li>
        <li><b>手动刷新</b>：按 F5 键立即同步文件状态</li>
        <li><b>智能检测</b>：检测新增、删除、移动的文件</li>
        <li><b>状态保存</b>：工作状态自动保存，重启后恢复</li>
        </ul>
        
        <h3>⚙️ 高级设置</h3>
        <ul>
        <li><b>性能优化</b>：针对大量图片的性能优化</li>
        <li><b>网络优化</b>：SMB/NAS网络存储专项优化</li>
        <li><b>缓存管理</b>：智能图片缓存提高浏览速度</li>
        </ul>
        '''
        
        # 设置样式确保文本颜色对比度
        text_browser.setStyleSheet("""
            QTextBrowser {
                background-color: white;
                color: black;
                selection-background-color: #0078d4;
                selection-color: white;
            }
        """)
        
        text_browser.setHtml(help_text)
        layout.addWidget(text_browser)
        
        return widget
        
    def create_advanced_tab(self):
        """创建高级功能标签页"""
        from PyQt6.QtWidgets import QWidget, QTextBrowser
        
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        text_browser = QTextBrowser()
        
        advanced_text = '''
        <h2>⚡ 高级功能详解</h2>
        
        <h3>🔧 分类操作</h3>
        <div style="background-color: #e8f5e8; padding: 15px; border-radius: 8px; margin: 10px 0;">
        <h4>📋 当前分类功能</h4>
        <ul>
        <li><b>单张分类</b>：双击类别按钮分类当前图片</li>
        <li><b>快捷键分类</b>：使用数字键1-9或自定义快捷键</li>
        <li><b>多分类模式</b>：一张图片可同时分配到多个类别</li>
        <li><b>快速导航</b>：使用方向键浏览图片和选择类别</li>
        </ul>
        
        <h4>🏷️ 类别管理</h4>
        <ul>
        <li><b>批量添加</b>：输入多个类别名，用逗号分隔</li>
        <li><b>快捷键绑定</b>：右键类别按钮自定义快捷键</li>
        <li><b>类别排序</b>：拖拽调整类别显示顺序</li>
        <li><b>状态统计</b>：实时显示每个类别的图片数量</li>
        </ul>
        </div>
        
        <h3>🎨 自定义功能</h3>
        <div style="background-color: #fff8e1; padding: 15px; border-radius: 8px; margin: 10px 0;">
        <h4>⌨️ 快捷键自定义</h4>
        <ul>
        <li><b>数字键</b>：1-9 对应前9个类别</li>
        <li><b>字母键</b>：a-z 可自定义对应不同类别</li>
        <li><b>功能键</b>：F1-F12 可绑定特殊操作</li>
        <li><b>组合键</b>：支持 Ctrl、Alt、Shift 组合</li>
        </ul>
        
        <h4>🎭 界面特性</h4>
        <ul>
        <li><b>响应式布局</b>：界面自动适应窗口大小</li>
        <li><b>分割面板</b>：可拖拽调整各区域大小</li>
        <li><b>状态保存</b>：界面布局自动保存和恢复</li>
        </ul>
        </div>
        
        <h3>🌐 网络存储优化</h3>
        <div style="background-color: #e3f2fd; padding: 15px; border-radius: 8px; margin: 10px 0;">
        <h4>📡 SMB/NAS 支持</h4>
        <ul>
        <li><b>网络路径</b>：支持 \\\\server\\share 格式</li>
        <li><b>连接池</b>：维护网络连接池提高效率</li>
        <li><b>操作重试</b>：网络操作失败时自动重试</li>
        <li><b>缓存优化</b>：智能缓存网络图片</li>
        </ul>
        
        <h4>🚀 性能优化</h4>
        <ul>
        <li><b>预加载</b>：提前加载下一张图片</li>
        <li><b>内存管理</b>：智能释放不需要的图片内存</li>
        <li><b>多线程</b>：后台线程处理文件操作</li>
        <li><b>进度缓存</b>：缓存处理进度避免重复扫描</li>
        </ul>
        </div>
        
        <h3>🔄 同步与备份</h3>
        <div style="background-color: #fce4ec; padding: 15px; border-radius: 8px; margin: 10px 0;">
        <h4>📂 文件同步</h4>
        <ul>
        <li><b>实时监控</b>：监控目录变化自动更新</li>
        <li><b>增量同步</b>：只处理变化的文件</li>
        <li><b>冲突解决</b>：智能处理文件名冲突</li>
        <li><b>分类撤销</b>：多分类模式支持快速取消分类</li>
        </ul>
        
        <h4>💾 状态备份</h4>
        <ul>
        <li><b>自动保存</b>：定期保存工作状态</li>
        <li><b>手动备份</b>：导出当前分类状态</li>
        <li><b>状态恢复</b>：从备份文件恢复工作状态</li>
        </ul>
        </div>
        
        <h3>🔍 图片分析</h3>
        <div style="background-color: #f3e5f5; padding: 15px; border-radius: 8px; margin: 10px 0;">
        <h4>📊 图片信息</h4>
        <ul>
        <li><b>EXIF 数据</b>：显示拍摄时间、相机信息等</li>
        <li><b>文件属性</b>：大小、分辨率、格式信息</li>
        </ul>
        
        </div>
        '''
        
        # 设置样式确保文本颜色对比度
        text_browser.setStyleSheet("""
            QTextBrowser {
                background-color: white;
                color: black;
                selection-background-color: #0078d4;
                selection-color: white;
            }
        """)
        
        text_browser.setHtml(advanced_text)
        layout.addWidget(text_browser)
        
        return widget
        
    def create_faq_tab(self):
        """创建常见问题标签页"""
        from PyQt6.QtWidgets import QWidget, QTextBrowser
        
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        text_browser = QTextBrowser()
        
        faq_text = '''
        <h2>❓ 常见问题解答</h2>
        

        <h3>📁 文件和目录</h3>
        <div style="background-color: #f8f9fa; padding: 15px; border-radius: 8px; margin: 10px 0; border-left: 4px solid #28a745;">
        <h4>Q: 程序支持哪些图片格式？</h4>
        <p><b>A:</b> 支持 JPG、JPEG、PNG、BMP、GIF、TIFF 等常见格式，区分大小写。</p>
        
        <h4>Q: 可以处理子目录中的图片吗？</h4>
        <p><b>A:</b> 是的，程序会递归扫描选定目录下的所有子目录，自动发现图片文件。</p>
        
        <h4>Q: 分类后的图片存储在哪里？</h4>
        <p><b>A:</b> 在原目录下创建以类别名命名的文件夹，图片会复制或移动到相应文件夹中。</p>
        
        <h4>Q: 删除的图片会永久消失吗？</h4>
        <p><b>A:</b> 不会，删除的图片会移动到 "remove" 目录中，可以手动恢复。</p>
        </div>
        
        <h3>🖼️ 图片显示和操作</h3>
        <div style="background-color: #f8f9fa; padding: 15px; border-radius: 8px; margin: 10px 0; border-left: 4px solid #ffc107;">
        <h4>Q: 图片显示很慢或模糊？</h4>
        <p><b>A:</b> 对于大图片和网络路径，程序会自动检测并启用性能优化模式，提供最佳的显示效果。</p>
        
        <h4>Q: 如何查看图片的详细信息？</h4>
        <p><b>A:</b> 点击图片右上角的 ℹ️ 按钮即可显示半透明的信息面板，查看图片的基本信息、尺寸属性和分类状态。点击"更多信息"可展开查看详细的文件信息。</p>
        
        <h4>Q: 缩放后图片位置错乱？</h4>
        <p><b>A:</b> 按 Ctrl+F 键重置为适应窗口模式，或按 Ctrl+0 显示原始大小。</p>
        </div>
        
        <h3>⚙️ 分类和管理</h3>
        <div style="background-color: #f8f9fa; padding: 15px; border-radius: 8px; margin: 10px 0; border-left: 4px solid #dc3545;">
        <h4>Q: 复制模式和移动模式有什么区别？</h4>
        <p><b>A:</b> 复制模式保留原文件并创建副本；移动模式直接移动文件到目标位置。</p>
        
        <h4>Q: 如何撤销错误的分类操作？</h4>
        <p><b>A:</b> <b>单分类模式</b>：只能更改分类，不能变为未分类状态，需手动移除文件后按F5刷新。<b>多分类模式</b>：再次点击已分类的类别按钮可直接取消该分类。</p>
        
        <h4>Q: 类别名称有长度限制吗？</h4>
        <p><b>A:</b> 类别名称最长50个字符，支持中英文和常见符号，但不能包含文件系统禁用字符。</p>
        </div>
        
        <h3>🌐 网络存储</h3>
        <div style="background-color: #f8f9fa; padding: 15px; border-radius: 8px; margin: 10px 0; border-left: 4px solid #6f42c1;">
        <h4>Q: 支持网络驱动器（NAS）吗？</h4>
        <p><b>A:</b> 支持，默认启用"网络路径优化"设置以提高性能。</p>
        
        <h4>Q: 网络断开后程序崩溃？</h4>
        <p><b>A:</b> 程序有文件操作重试机制，网络操作失败时会自动重试3次。建议保持网络稳定以获得最佳性能。</p>
        
        <h4>Q: SMB 共享访问很慢？</h4>
        <p><b>A:</b> 默认启用"SMB缓存优化"，程序会缓存常用图片以提高访问速度。</p>
        </div>
        
        <h3>🔧 性能和优化</h3>
        <div style="background-color: #f8f9fa; padding: 15px; border-radius: 8px; margin: 10px 0; border-left: 4px solid #20c997;">
        <h4>Q: 处理大量图片时程序卡顿？</h4>
        <p><b>A:</b> 程序会根据图片数量和系统性能自动调整优化策略，包括减少动画效果和智能预加载。</p>
        
        <h4>Q: 内存占用过高？</h4>
        <p><b>A:</b> 程序会自动管理内存，也可以手动清理缓存（帮助对话框中的清理按钮）。</p>
        
        <h4>Q: 如何清理程序产生的缓存？</h4>
        <p><b>A:</b> 在帮助对话框中点击"清理SMB缓存"按钮，或手动删除用户目录下的 .image_classifier_cache 文件夹。</p>
        </div>
        
        <h3>❗ 故障排除</h3>
        <div style="background-color: #fff3cd; padding: 15px; border-radius: 8px; margin: 10px 0; border-left: 4px solid #856404;">
        <h4>🔍 常见问题诊断步骤</h4>
        <ol>
        <li><b>检查日志</b>：查看 logs/image_classifier.log 了解错误详情</li>
        <li><b>重启程序</b>：简单重启通常能解决临时问题</li>
        <li><b>清理缓存</b>：清理程序缓存解决数据冲突</li>
        <li><b>检查权限</b>：确保对目标目录有读写权限</li>
        <li><b>更新程序</b>：下载最新版本获得 bug 修复</li>
        </ol>
        
        <h4>📞 获取帮助</h4>
        <p>如果问题仍未解决，请将错误日志和操作步骤通过以下方式反馈：<br>
        • 创建 GitHub Issue 描述问题<br>
        • 发送错误日志到开发者邮箱<br>
        • 在用户社区寻求帮助</p>
        </div>
        '''
        
        # 设置样式确保文本颜色对比度
        text_browser.setStyleSheet("""
            QTextBrowser {
                background-color: white;
                color: black;
                selection-background-color: #0078d4;
                selection-color: white;
            }
        """)
        
        text_browser.setHtml(faq_text)
        layout.addWidget(text_browser)
        
        return widget
    
    def _generate_version_history_html(self):
        """生成版本历史HTML内容"""
        html_parts = []
        
        # 版本样式配色
        version_styles = [
            {"bg": "#e8f5e8", "border": "#4caf50", "text": "#2e7d32", "emoji": "🎉", "label": "(当前版本)"},
            {"bg": "#f0f7ff", "border": "#2196f3", "text": "#1565c0", "emoji": "✨", "label": ""},
            {"bg": "#f8f9fa", "border": "#6c757d", "text": "#495057", "emoji": "🚀", "label": ""},
            {"bg": "#fff3e0", "border": "#ff9800", "text": "#ef6c00", "emoji": "🔧", "label": ""},
            {"bg": "#fce4ec", "border": "#e91e63", "text": "#c2185b", "emoji": "📦", "label": ""},
        ]
        
        for i, version_info in enumerate(VERSION_HISTORY):
            style = version_styles[min(i, len(version_styles) - 1)]
            
            # 当前版本标记
            version_label = style["label"] if i == 0 else ""
            
            html_part = f'''
            <div style="background-color: {style["bg"]}; padding: 15px; border-radius: 8px; margin: 10px 0; border-left: 4px solid {style["border"]};">
            <h4 style="color: {style["text"]}; margin: 0 0 10px 0;">{style["emoji"]} v{version_info["version"]} {version_label} - {version_info["date"]}</h4>
            '''
            
            if version_info.get("title"):
                html_part += f'<p style="margin: 0 0 10px 0; font-weight: bold; color: {style["text"]};">{version_info["title"]}</p>'
            
            # 添加亮点
            if version_info.get("highlights"):
                html_part += '<ul style="margin: 5px 0; padding-left: 20px;">'
                for highlight in version_info["highlights"]:
                    html_part += f'<li>{highlight}</li>'
                html_part += '</ul>'
            # 如果没有亮点，使用详细信息的前几项
            elif version_info.get("details"):
                html_part += '<ul style="margin: 5px 0; padding-left: 20px;">'
                for detail in version_info["details"][:4]:  # 只显示前4项
                    html_part += f'<li>{detail}</li>'
                html_part += '</ul>'
            
            html_part += '</div>'
            html_parts.append(html_part)
        
        return '\n'.join(html_parts)
        
    def create_about_tab(self):
        """创建关于标签页"""
        from PyQt6.QtWidgets import QWidget, QTextBrowser
        
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        text_browser = QTextBrowser()
        
        # 获取版本信息
        about_info = get_about_info()
        
        about_text = f'''
        <h2>📱 图片分类工具 v{about_info["version"]}</h2>
        
        <div style="text-align: center; background: linear-gradient(135deg, #e3f2fd 0%, #f3e5f5 100%); color: black; padding: 20px; border-radius: 10px; margin: 20px 0; box-shadow: 0 2px 10px rgba(0,0,0,0.1); border: 1px solid #ddd;">
        <h3 style="margin: 0; color: black;">🎯 专业图片分类管理工具</h3>
        <p style="margin: 10px 0 0 0; color: #333;">提高图片整理效率，让分类工作更简单</p>
        </div>
        
        <h3>✨ 核心特性</h3>
        <div style="background-color: #f8f9fa; padding: 15px; border-radius: 8px; margin: 10px 0;">
        <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 15px;">
        <div>
        <h4 style="color: #2196f3; margin: 0 0 10px 0;">🖼️ 图片处理</h4>
        <ul style="margin: 0; padding-left: 20px;">
        <li>支持多种常见图片格式</li>
        <li>智能图片预览和缩放</li>
        <li>拖拽移动查看细节</li>
        <li>EXIF信息显示</li>
        </ul>
        </div>
        <div>
        <h4 style="color: #4caf50; margin: 0 0 10px 0;">� 文件管理</h4>
        <ul style="margin: 0; padding-left: 20px;">
        <li>复制/移动双模式操作</li>
        <li>批量分类处理</li>
        <li>智能类别管理</li>
        <li>自动状态同步</li>
        </ul>
        </div>
        <div>
        <h4 style="color: #ff9800; margin: 0 0 10px 0;">⌨️ 操作体验</h4>
        <ul style="margin: 0; padding-left: 20px;">
        <li>丰富的快捷键支持</li>
        <li>自定义快捷键设置</li>
        <li>直观的状态提示</li>
        <li>实时进度跟踪</li>
        </ul>
        </div>
        <div>
        <h4 style="color: #9c27b0; margin: 0 0 10px 0;">� 性能优化</h4>
        <ul style="margin: 0; padding-left: 20px;">
        <li>网络存储优化</li>
        <li>智能缓存机制</li>
        <li>多线程处理</li>
        <li>内存自动管理</li>
        </ul>
        </div>
        </div>
        </div>
        
        <h3>🛠️ 技术架构</h3>
        <table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse; width: 100%; margin: 10px 0; border: 1px solid #ddd;">
        <tr style="background-color: #f8f9fa;">
        <th style="width: 30%; padding: 8px; border: 1px solid #ddd;">技术栈</th>
        <th style="width: 35%; padding: 8px; border: 1px solid #ddd;">版本/库</th>
        <th style="width: 35%; padding: 8px; border: 1px solid #ddd;">说明</th>
        </tr>
        <tr>
        <td style="padding: 8px; border: 1px solid #ddd;"><b>开发语言</b></td>
        <td style="padding: 8px; border: 1px solid #ddd;">Python 3.8+</td>
        <td style="padding: 8px; border: 1px solid #ddd;">主要开发语言</td>
        </tr>
        <tr>
        <td style="padding: 8px; border: 1px solid #ddd;"><b>界面框架</b></td>
        <td style="padding: 8px; border: 1px solid #ddd;">PyQt6</td>
        <td style="padding: 8px; border: 1px solid #ddd;">现代化GUI框架</td>
        </tr>
        <tr>
        <td style="padding: 8px; border: 1px solid #ddd;"><b>图像处理</b></td>
        <td style="padding: 8px; border: 1px solid #ddd;">OpenCV + Pillow</td>
        <td style="padding: 8px; border: 1px solid #ddd;">图片加载和处理</td>
        </tr>
        <tr>
        <td style="padding: 8px; border: 1px solid #ddd;"><b>数据存储</b></td>
        <td style="padding: 8px; border: 1px solid #ddd;">JSON</td>
        <td style="padding: 8px; border: 1px solid #ddd;">配置和状态存储</td>
        </tr>
        <tr>
        <td style="padding: 8px; border: 1px solid #ddd;"><b>日志系统</b></td>
        <td style="padding: 8px; border: 1px solid #ddd;">Python logging</td>
        <td style="padding: 8px; border: 1px solid #ddd;">错误跟踪和调试</td>
        </tr>
        <tr>
        <td style="padding: 8px; border: 1px solid #ddd;"><b>多线程</b></td>
        <td style="padding: 8px; border: 1px solid #ddd;">QThread</td>
        <td style="padding: 8px; border: 1px solid #ddd;">后台任务处理</td>
        </tr>
        </table>
        
        <h3>📈 版本发展历程</h3>
        <div style="margin: 20px 0;">
        {self._generate_version_history_html()}
        </div>

        
        <div style="background: linear-gradient(135deg, #e8f5e8 0%, #f0f4f8 100%); color: black; padding: 20px; border-radius: 10px; text-align: center; margin: 30px 0; box-shadow: 0 2px 10px rgba(0,0,0,0.1); border: 1px solid #ddd;">
        <h3 style="margin: 0 0 15px 0; color: black;">📝 版权信息</h3>
        <p style="margin: 5px 0; color: #333;"><b>© 2025 图片分类工具开发团队</b></p>
        <p style="margin: 5px 0; color: #333;">专注于提升图片管理效率的专业软件</p>
        <p style="margin: 15px 0 5px 0; color: #555; font-size: 14px;">
        本软件遵循 MIT 开源协议<br>
        感谢所有贡献者和用户的支持
        </p>
        <div style="margin-top: 15px; padding-top: 15px; border-top: 1px solid #ccc;">
        <span style="color: #666; font-size: 13px;">
        🌟 让图片整理变得简单高效 🌟
        </span>
        </div>
        </div>
        '''
        
        # 设置样式确保文本颜色对比度
        text_browser.setStyleSheet("""
            QTextBrowser {
                background-color: white;
                color: black;
                selection-background-color: #0078d4;
                selection-color: white;
            }
        """)
        
        text_browser.setHtml(about_text)
        layout.addWidget(text_browser)
        
        return widget


class ProgressDialog(QDialog):
    """增强的进度对话框，支持取消和详细信息"""
    cancelled = pyqtSignal()
    
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(400)
        self.cancelled_flag = False
        self._force_closed = False  # 添加强制关闭标志
        self.logger = logging.getLogger(__name__)
        
        layout = QVBoxLayout(self)
        
        # 主要进度信息
        self.main_label = QLabel("正在处理...")
        layout.addWidget(self.main_label)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        layout.addWidget(self.progress_bar)
        
        # 详细信息
        self.detail_label = QLabel("")
        self.detail_label.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(self.detail_label)
        
        # 取消按钮
        button_layout = QHBoxLayout()
        self.cancel_button = QPushButton("取消")
        self.cancel_button.clicked.connect(self.cancel_operation)
        button_layout.addStretch()
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)
        
        # 设置样式
        self.setStyleSheet("""
            QDialog {
                background-color: white;
            }
            QLabel {
                padding: 4px;
            }
            QProgressBar {
                text-align: center;
                min-height: 20px;
                border: 1px solid #6C757D;
                border-radius: 10px;
                background-color: #E9ECEF;
                font-size: 11px;
                font-weight: bold;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0 #28A745, stop: 1 #20C997);
                border-radius: 8px;
                margin: 1px;
            }
            QPushButton {
                padding: 6px 20px;
                background-color: #dc3545;
                color: white;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #c82333;
            }
        """)
        
    def update_progress(self, value, maximum=100):
        """更新进度"""
        try:
            self.progress_bar.setMaximum(maximum)
            self.progress_bar.setValue(value)
        except Exception as e:
            self.logger.error(f"更新进度失败: {e}")
        
    def update_main_text(self, text):
        """更新主要文本"""
        try:
            self.main_label.setText(text)
        except Exception as e:
            self.logger.error(f"更新主要文本失败: {e}")
        
    def update_detail_text(self, text):
        """更新详细信息"""
        try:
            self.detail_label.setText(text)
        except Exception as e:
            self.logger.error(f"更新详细信息失败: {e}")
        
    def cancel_operation(self):
        """取消操作"""
        try:
            self.cancelled_flag = True
            self.cancelled.emit()
            self.cancel_button.setEnabled(False)
            self.cancel_button.setText("正在取消...")
        except Exception as e:
            self.logger.error(f"取消操作失败: {e}")
        
    def force_close(self):
        """强制关闭对话框"""
        self._force_closed = True
        self.close()
        
    def is_cancelled(self):
        """检查是否已取消"""
        return self.cancelled_flag
        
    def closeEvent(self, event):
        """重写关闭事件"""
        if self._force_closed:
            event.accept()
        else:
            # 正常情况下需要等待操作完成
            event.accept()


