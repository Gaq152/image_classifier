"""帮助对话框模块"""

import logging
import subprocess
import sys
from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QWidget, QTextBrowser, QMessageBox, QApplication
)
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QIcon

from ..components.toast import toast_success, toast_error
from ..components.styles.theme import default_theme
from _version_ import CONTACT_INFO, VERSION_HISTORY, get_about_info

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
        
    def _get_html_colors(self):
        """获取用于 HTML 内容的主题颜色映射"""
        c = default_theme.colors
        return {
            'bg_primary': c.BACKGROUND_PRIMARY,
            'bg_secondary': c.BACKGROUND_SECONDARY,
            'bg_hover': c.BACKGROUND_HOVER,
            'text_primary': c.TEXT_PRIMARY,
            'text_secondary': c.TEXT_SECONDARY,
            'border': c.BORDER_MEDIUM,
            'primary': c.PRIMARY,
            'primary_light': c.PRIMARY_LIGHT,
        }

    def _get_git_branch(self):
        """获取当前 git 分支名称"""
        try:
            result = subprocess.run(
                ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
                capture_output=True,
                text=True,
                timeout=3,
                cwd=Path(__file__).parent.parent  # 项目根目录
            )
            if result.returncode == 0:
                branch = result.stdout.strip()
                return branch if branch else 'main'
        except Exception as e:
            self.logger.debug(f"获取 git 分支失败: {e}")

        # 默认返回 main
        return 'main'

    def _get_dialog_style(self):
        """根据当前主题获取对话框样式"""
        c = default_theme.colors

        return f"""
                QDialog {{
                    background-color: {c.BACKGROUND_PRIMARY};
                    color: {c.TEXT_PRIMARY};
                }}
                QTabWidget {{
                    background-color: {c.BACKGROUND_PRIMARY};
                    border: 1px solid {c.BORDER_MEDIUM};
                    border-radius: 4px;
                }}
                QTabWidget::pane {{
                    background-color: {c.BACKGROUND_PRIMARY};
                    border: 1px solid {c.BORDER_MEDIUM};
                    border-radius: 4px;
                    top: -1px;
                }}
                QTabBar::tab {{
                    background-color: {c.BACKGROUND_SECONDARY};
                    color: {c.TEXT_SECONDARY};
                    border: 1px solid {c.BORDER_MEDIUM};
                    padding: 8px 16px;
                    margin-right: 2px;
                    border-top-left-radius: 4px;
                    border-top-right-radius: 4px;
                    font-weight: normal;
                    min-width: 80px;
                }}
                QTabBar::tab:selected {{
                    background-color: {c.BACKGROUND_PRIMARY};
                    color: {c.TEXT_PRIMARY};
                    border-bottom-color: {c.BACKGROUND_PRIMARY};
                    font-weight: 500;
                }}
                QTabBar::tab:hover {{
                    background-color: {c.BACKGROUND_HOVER};
                }}
                QTabBar::tab:selected:hover {{
                    background-color: {c.BACKGROUND_PRIMARY};
                }}
                QPushButton {{
                    background-color: {c.PRIMARY};
                    color: white;
                    border: none;
                    border-radius: 4px;
                    padding: 8px 16px;
                    font-size: 13px;
                    font-weight: normal;
                    min-width: 80px;
                }}
                QPushButton:hover {{
                    background-color: {c.PRIMARY_DARK};
                }}
                QPushButton:pressed {{
                    background-color: {c.PRIMARY_DARK};
                }}
                QPushButton#clearCacheBtn {{
                    background-color: {c.WARNING};
                }}
                QPushButton#clearCacheBtn:hover {{
                    background-color: {c.WARNING_DARK};
                }}
                QPushButton#clearCacheBtn:pressed {{
                    background-color: {c.WARNING_DARK};
                }}
                QTextBrowser {{
                    background-color: {c.BACKGROUND_PRIMARY};
                    color: {c.TEXT_PRIMARY};
                    border: none;
                    selection-background-color: {c.PRIMARY};
                    selection-color: white;
                }}
                QLabel {{
                    color: {c.TEXT_PRIMARY};
                }}
            """

    def _apply_theme(self):
        """应用主题到对话框"""
        try:
            c = default_theme.colors

            # 更新对话框样式
            self.setStyleSheet(self._get_dialog_style())

            # 更新所有 QTextBrowser 的样式并重新生成HTML内容
            if hasattr(self, 'findChildren'):
                # 找到所有QTextBrowser并重新生成其HTML内容
                tab_widget = self.findChild(QTabWidget)
                if tab_widget:
                    for i in range(tab_widget.count()):
                        tab = tab_widget.widget(i)
                        if tab:
                            text_browser = tab.findChild(QTextBrowser)
                            if text_browser:
                                # 更新样式
                                text_browser.setStyleSheet(f"""
                                    QTextBrowser {{
                                        background-color: {c.BACKGROUND_PRIMARY};
                                        color: {c.TEXT_PRIMARY};
                                        font-size: 13px;
                                        line-height: 1.6;
                                        selection-background-color: {c.PRIMARY};
                                        selection-color: white;
                                        border: none;
                                    }}
                                """)

                                # 根据标签页名称重新生成HTML内容
                                tab_title = tab_widget.tabText(i)
                                if tab_title == '快速入门':
                                    text_browser.setHtml(self._generate_quick_start_html())
                                elif tab_title == '使用指南':
                                    text_browser.setHtml(self._generate_help_html())
                                elif tab_title == '常见问题':
                                    text_browser.setHtml(self._generate_faq_html())
                                elif tab_title == '关于':
                                    text_browser.setHtml(self._generate_about_html())

            # 强制重绘
            self.update()
        except Exception as e:
            self.logger.error(f"应用主题失败: {e}")

    def initUI(self):
        """初始化UI"""
        try:
            self.setWindowTitle('帮助和关于')
            self.setMinimumSize(700, 500)
            self.setModal(True)

            # 设置对话框整体样式
            self.setStyleSheet(self._get_dialog_style())

            # 旧的样式代码已移到_get_dialog_style方法中
            old_style = """
                QDialog {
                    background-color: #FFFFFF;
                    color: #212121;
                }
                QTabWidget {
                    background-color: #FFFFFF;
                    border: 1px solid #E0E0E0;
                    border-radius: 4px;
                }
                QTabWidget::pane {
                    background-color: #FFFFFF;
                    border: 1px solid #E0E0E0;
                    border-radius: 4px;
                    top: -1px;
                }
                QTabBar::tab {
                    background-color: #F5F5F5;
                    color: #616161;
                    border: 1px solid #E0E0E0;
                    padding: 8px 16px;
                    margin-right: 2px;
                    border-top-left-radius: 4px;
                    border-top-right-radius: 4px;
                    font-weight: normal;
                    min-width: 80px;
                }
                QTabBar::tab:selected {
                    background-color: #FFFFFF;
                    color: #212121;
                    border-bottom-color: #FFFFFF;
                    font-weight: 500;
                }
                QTabBar::tab:hover {
                    background-color: #EEEEEE;
                }
                QTabBar::tab:selected:hover {
                    background-color: #FFFFFF;
                }
                QPushButton {
                    background-color: #3498DB;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    padding: 8px 16px;
                    font-size: 13px;
                    font-weight: normal;
                    min-width: 80px;
                }
                QPushButton:hover {
                    background-color: #2980B9;
                }
                QPushButton:pressed {
                    background-color: #21618C;
                }
                QPushButton#clearCacheBtn {
                    background-color: #FF9800;
                }
                QPushButton#clearCacheBtn:hover {
                    background-color: #F57C00;
                }
                QPushButton#clearCacheBtn:pressed {
                    background-color: #E65100;
                }
            """
            
            layout = QVBoxLayout(self)

            # 创建标签页控件
            tab_widget = QTabWidget()

            # 添加快速入门标签页
            quick_start_tab = self.create_quick_start_tab()
            tab_widget.addTab(quick_start_tab, '快速入门')

            # 添加详细帮助标签页
            help_tab = self.create_help_tab()
            tab_widget.addTab(help_tab, '使用指南')

            # 添加常见问题标签页
            faq_tab = self.create_faq_tab()
            tab_widget.addTab(faq_tab, '常见问题')

            # 添加关于标签页
            about_tab = self.create_about_tab()
            tab_widget.addTab(about_tab, '关于')
            
            layout.addWidget(tab_widget)

            # 提示：更多设置请打开设置页面
            hint_layout = QHBoxLayout()
            hint_layout.addStretch()
            hint_label = QLabel("💡 提示：更多设置请点击工具栏的 ⚙️ 设置按钮")
            hint_label.setStyleSheet("font-size: 12px; padding: 10px;")
            hint_layout.addWidget(hint_label)
            hint_layout.addStretch()
            layout.addLayout(hint_layout)

            # 应用当前主题
            self._apply_theme()

        except Exception as e:
            self.logger.error(f"初始化帮助对话框UI失败: {e}")

    def _handle_link_click(self, url):
        """处理链接点击事件"""
        try:
            url_str = url.toString()

            # 处理复制邮箱地址的链接
            if url_str.startswith('copy://'):
                email = url_str.replace('copy://', '')
                # 复制到剪贴板
                clipboard = QApplication.clipboard()
                clipboard.setText(email)
                toast_success(self, f'邮箱地址已复制: {email}')
                self.logger.info(f"复制邮箱地址到剪贴板: {email}")
            else:
                # 其他链接使用默认浏览器打开
                QDesktopServices.openUrl(url)
        except Exception as e:
            self.logger.error(f"处理链接点击失败: {e}")
            toast_error(self, f'操作失败: {e}')

    def _show_styled_message(self, msg_type, title, text):
        """显示样式化的消息框"""     
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
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setText(text)
        # 统一图标/样式
        box.setIcon(QMessageBox.Icon.Question)
        try:
            icon_path = self._get_resource_path('assets/icon.ico')
            if icon_path and icon_path.exists():
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
        
    def _generate_quick_start_html(self):
        """生成快速入门标签页的HTML内容"""
        colors = self._get_html_colors()

        return f'''
        <h2 style="border-bottom: 2px solid {colors['primary']}; padding-bottom: 8px; color: {colors['text_primary']};">快速入门指南</h2>

        <div style="background-color: {colors['bg_hover']}; padding: 15px; border-left: 4px solid {colors['primary']}; margin: 15px 0;">
        <h3 style="color: {colors['primary']}; margin-top: 0;">三步快速开始</h3>
        <ol style="line-height: 1.8; color: {colors['text_primary']};">
        <li><b>选择文件夹</b>：点击"打开目录"选择包含图片的文件夹</li>
        <li><b>创建类别</b>：点击"新增类别"添加分类标签</li>
        <li><b>开始分类</b>：双击类别按钮或使用快捷键分类图片</li>
        </ol>
        </div>

        <h3 style="color: {colors['text_primary']}; margin-top: 20px;">支持的图片格式</h3>
        <p style="background-color: {colors['bg_secondary']}; padding: 10px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">
        JPG, JPEG, PNG, BMP, GIF, TIFF, WebP
        </p>

        <h3 style="color: {colors['text_primary']}; margin-top: 20px;">核心操作</h3>
        <table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse; width: 100%; margin: 10px 0; border: 1px solid {colors['border']};">
        <tr style="background-color: {colors['bg_secondary']};">
        <th style="width: 25%; padding: 8px; border: 1px solid {colors['border']}; text-align: left; color: {colors['text_primary']};">操作</th>
        <th style="width: 35%; padding: 8px; border: 1px solid {colors['border']}; text-align: left; color: {colors['text_primary']};">方法</th>
        <th style="width: 40%; padding: 8px; border: 1px solid {colors['border']}; text-align: left; color: {colors['text_primary']};">说明</th>
        </tr>
        <tr>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">浏览图片</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">← → 键 或 鼠标点击</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">在图片列表中前后导航</td>
        </tr>
        <tr style="background-color: {colors['bg_hover']};">
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">选择类别</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">↑ ↓ 键</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">在类别列表中上下切换选择</td>
        </tr>
        <tr>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">分类图片</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">双击类别按钮 或 Enter键</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">将当前图片分类到选中类别</td>
        </tr>
        <tr style="background-color: {colors['bg_hover']};">
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">缩放图片</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">鼠标滚轮 或 Ctrl +/-</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">放大缩小查看图片细节</td>
        </tr>
        <tr>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">移动图片</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">鼠标左键拖拽</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">移动图片查看不同区域</td>
        </tr>
        <tr style="background-color: {colors['bg_hover']};">
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">移出图片</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">Delete 键</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">将图片移到移出目录</td>
        </tr>
        </table>

        <h3 style="color: {colors['text_primary']}; margin-top: 20px;">高效使用技巧</h3>
        <ul style="line-height: 1.8; color: {colors['text_primary']};">
        <li><b>使用快捷键</b>：按数字键 1-9 快速分类到对应类别</li>
        <li><b>文件模式切换</b>：点击工具栏的"⧉/✂"按钮切换复制/移动模式</li>
        <li><b>多分类模式</b>：点击工具栏的"→/⇶"按钮切换单/多分类</li>
        <li><b>撤销分类</b>：单分类模式下，再次点击已分类的类别可撤销分类</li>
        <li><b>撤销删除</b>：已删除的图片再次按 Delete 键可从移出目录恢复</li>
        <li><b>回车确认</b>：选中类别后按 Enter 键快速分类</li>
        <li><b>自动同步</b>：程序会自动检测外部文件变化</li>
        <li><b>状态保存</b>：工作状态会自动保存，重启后恢复</li>
        <li><b>主题切换</b>：在设置中可切换亮色/暗色主题，或设置跟随系统</li>
        <li><b>缩放配置</b>：可在设置中自定义图片缩放范围和全局缩放行为</li>
        <li><b>新手教程</b>：首次使用时会自动引导，也可在帮助菜单重新开始</li>
        <li><b>自动更新</b>：支持在线检查和下载最新版本（需联网）</li>
        </ul>
        </p>
        </div>
        '''

    def create_quick_start_tab(self):
        """创建快速入门标签页"""

        widget = QWidget()
        layout = QVBoxLayout(widget)

        text_browser = QTextBrowser()

        # 应用主题样式
        c = default_theme.colors
        text_browser.setStyleSheet(f"""
            QTextBrowser {{
                background-color: {c.BACKGROUND_PRIMARY};
                color: {c.TEXT_PRIMARY};
                font-size: 13px;
                line-height: 1.6;
                selection-background-color: {c.PRIMARY};
                selection-color: white;
                border: none;
            }}
        """)

        text_browser.setHtml(self._generate_quick_start_html())
        layout.addWidget(text_browser)

        return widget
        
    def _generate_help_html(self):
        """生成使用指南标签页的HTML内容"""
        colors = self._get_html_colors()

        return f'''
        <h2 style="border-bottom: 2px solid {colors['primary']}; padding-bottom: 8px; color: {colors['text_primary']};">详细使用指南</h2>

        <h3 style="color: {colors['text_primary']}; margin-top: 20px;">文件管理</h3>

        <h4 style="color: {colors['text_primary']};">目录操作</h4>
        <ul style="line-height: 1.8; color: {colors['text_primary']};">
        <li><b>打开目录</b>：选择包含待分类图片的根目录</li>
        <li><b>子目录处理</b>：程序会递归扫描所有子目录中的图片</li>
        <li><b>目录结构</b>：分类后的图片会按类别名创建对应文件夹</li>
        <li><b>移出目录</b>：删除的图片会移动到 "remove" 文件夹</li>
        </ul>

        <h4 style="color: {colors['text_primary']};">类别管理</h4>
        <ul style="line-height: 1.8; color: {colors['text_primary']};">
        <li><b>新增类别</b>：单个添加或批量添加（逗号分隔）</li>
        <li><b>编辑类别</b>：右键类别按钮选择"编辑"</li>
        <li><b>删除类别</b>：右键类别按钮选择"删除"</li>
        <li><b>快捷键设置</b>：右键类别按钮选择"设置快捷键"</li>
        <li><b>类别限制</b>：类别名最长50个字符，支持中英文</li>
        </ul>

        <h3 style="color: {colors['text_primary']}; margin-top: 20px;">图片浏览与操作</h3>

        <h4 style="color: {colors['text_primary']};">视图控制</h4>
        <table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse; width: 100%; margin: 10px 0; border: 1px solid {colors['border']};">
        <tr style="background-color: {colors['bg_secondary']};">
        <th style="width: 20%; padding: 8px; border: 1px solid {colors['border']}; text-align: left; color: {colors['text_primary']};">功能</th>
        <th style="width: 30%; padding: 8px; border: 1px solid {colors['border']}; text-align: left; color: {colors['text_primary']};">操作方法</th>
        <th style="width: 20%; padding: 8px; border: 1px solid {colors['border']}; text-align: left; color: {colors['text_primary']};">快捷键</th>
        <th style="width: 30%; padding: 8px; border: 1px solid {colors['border']}; text-align: left; color: {colors['text_primary']};">说明</th>
        </tr>
        <tr>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">适应窗口</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">菜单/快捷键</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">Ctrl+F</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">自动调整图片大小适应显示区域</td>
        </tr>
        <tr style="background-color: {colors['bg_hover']};">
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">放大图片</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">滚轮向上/菜单</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">Ctrl + =</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">放大图片，最大倍数可在设置中配置（默认3倍，最大20倍）</td>
        </tr>
        <tr>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">缩小图片</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">滚轮向下/菜单</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">Ctrl + -</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">缩小图片显示</td>
        </tr>
        <tr style="background-color: {colors['bg_hover']};">
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">原始大小</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">菜单/快捷键</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">Ctrl + 0</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">显示图片100%原始大小</td>
        </tr>
        <tr>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">拖拽移动</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">鼠标左键拖拽</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">-</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">移动图片查看不同区域</td>
        </tr>
        </table>

        <h4 style="color: {colors['text_primary']};">分类操作</h4>
        <ul style="line-height: 1.8; color: {colors['text_primary']};">
        <li><b>复制模式</b>：保留原文件，复制到目标类别文件夹（默认）</li>
        <li><b>移动模式</b>：直接移动文件到目标类别文件夹</li>
        <li><b>分类方法</b>：双击类别按钮、使用快捷键或按回车键</li>
        <li><b>多分类模式</b>：同一张图片可分配到多个类别</li>
        <li><b>删除图片</b>：按 Delete 键将图片移动到 "remove" 文件夹</li>
        <li><b>撤销操作</b>：支持撤销分类（单/多分类）和撤销删除，再次点击已分类类别或已删除图片的 Delete 键即可撤销</li>
        </ul>

        <h4 style="color: {colors['text_primary']};">分类模式详解</h4>
        <div style="background-color: {colors['bg_hover']}; padding: 15px; border-left: 4px solid {colors['primary']}; margin: 15px 0;">
        <h5 style="color: {colors['primary']}; margin-top: 0;">单分类模式（默认）</h5>
        <ul style="margin: 5px 0; padding-left: 20px; line-height: 1.6; color: {colors['text_primary']};">
        <li>一张图片只能属于一个类别</li>
        <li>重新分类会自动从旧类别移动到新类别</li>
        <li>类别按钮显示绿色背景表示已分类</li>
        <li>适合传统的文件整理需求</li>
        </ul>
        </div>

        <div style="background-color: {colors['bg_hover']}; padding: 15px; border-left: 4px solid {colors['primary']}; margin: 15px 0;">
        <h5 style="color: {colors['primary']}; margin-top: 0;">多分类模式（新功能）</h5>
        <ul style="margin: 5px 0; padding-left: 20px; line-height: 1.6; color: {colors['text_primary']};">
        <li><b>灵活分类</b>：一张图片可以同时属于多个类别</li>
        <li><b>切换方式</b>：点击工具栏的"→/⇶"按钮切换单/多分类</li>
        <li><b>分类操作</b>：点击类别按钮添加分类，再次点击取消分类</li>
        <li><b>视觉反馈</b>：多分类的类别按钮显示蓝色背景</li>
        <li><b>应用场景</b>：标签化管理，如"风景+日落"、"人物+室内"等</li>
        </ul>

        <table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse; width: 100%; margin: 10px 0; border: 1px solid {colors['border']};">
        <tr style="background-color: {colors['bg_secondary']};">
        <th style="padding: 8px; border: 1px solid {colors['border']}; text-align: left; color: {colors['text_primary']};">操作</th>
        <th style="padding: 8px; border: 1px solid {colors['border']}; text-align: left; color: {colors['text_primary']};">多分类模式行为</th>
        <th style="padding: 8px; border: 1px solid {colors['border']}; text-align: left; color: {colors['text_primary']};">单分类模式行为</th>
        </tr>
        <tr>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">首次分类</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">添加到类别列表</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">直接分类到该类别</td>
        </tr>
        <tr style="background-color: {colors['bg_hover']};">
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">已分类的类别</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">从列表中移除（取消分类）</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">撤销分类（复制模式移除该文件，移动模式文件返回原目录）</td>
        </tr>
        <tr>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">其他类别</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">同时添加到类别列表</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">从旧类别移动到新类别</td>
        </tr>
        </table>
        </div>

        <div style="background-color: {colors['bg_hover']}; padding: 15px; border-left: 4px solid {colors['primary']}; margin: 20px 0;">
        <h5 style="color: {colors['primary']}; margin-top: 0;">多分类模式使用技巧</h5>
        <ul style="margin: 5px 0; padding-left: 20px; line-height: 1.6; color: {colors['text_primary']};">
        <li><b>标签化思维</b>：把类别当作标签，一张图片可以有多个标签</li>
        <li><b>快速取消</b>：再次点击已分类的类别按钮可快速取消该分类</li>
        <li><b>状态查看</b>：蓝色背景的类别按钮表示当前图片属于该类别</li>
        <li><b>物理文件</b>：图片会被复制到每个分类的文件夹中</li>
        <li><b>模式切换</b>：可随时在单分类和多分类模式间切换</li>
        </ul>
        </div>

        <h3 style="color: {colors['text_primary']}; margin-top: 20px;">状态与统计</h3>

        <h4 style="color: {colors['text_primary']};">状态标识</h4>
        <ul style="line-height: 1.8; color: {colors['text_primary']};">
        <li><b>已分类</b>：图片已成功分类到某个类别</li>
        <li><b>已移出</b>：图片已移动到移出目录</li>
        <li><b>未处理</b>：尚未分类的图片</li>
        <li><b>进度显示</b>：底部状态栏显示处理进度</li>
        </ul>

        <h4 style="color: {colors['text_primary']};">实时统计</h4>
        <ul style="line-height: 1.8; color: {colors['text_primary']};">
        <li><b>总数统计</b>：显示图片总数和处理进度</li>
        <li><b>类别统计</b>：每个类别的图片数量</li>
        <li><b>效率统计</b>：分类速度和剩余时间估计</li>
        </ul>

        <h3 style="color: {colors['text_primary']}; margin-top: 20px;">同步与刷新</h3>
        <ul style="line-height: 1.8; color: {colors['text_primary']};">
        <li><b>自动同步</b>：程序会定期检测外部文件变化</li>
        <li><b>手动刷新</b>：按 F5 键立即同步文件状态</li>
        <li><b>智能检测</b>：检测新增、删除、移动的文件</li>
        <li><b>状态保存</b>：工作状态自动保存，重启后恢复</li>
        </ul>

        <h3 style="color: {colors['text_primary']}; margin-top: 20px;">高级设置</h3>

        <h4 style="color: {colors['text_primary']};">快捷键系统</h4>
        <ul style="line-height: 1.8; color: {colors['text_primary']};">
        <li><b>自动分配</b>：数字键 1-9 和字母键 a-z 会自动分配给前 35 个类别</li>
        <li><b>手动设置</b>：右键类别按钮选择"设置快捷键"可自定义</li>
        <li><b>组合键</b>：支持 Ctrl、Alt、Shift 组合键，需手动设置</li>
        <li><b>冲突检测</b>：设置快捷键时会自动检测冲突，避开系统保留快捷键</li>
        <li><b>排序模式</b>：支持按类别名称、快捷键或分类数量排列</li>
        </ul>

        <h4 style="color: {colors['text_primary']};">性能优化</h4>
        <ul style="line-height: 1.8; color: {colors['text_primary']};">
        <li><b>智能预加载</b>：自动预加载下一张图片提高浏览速度</li>
        <li><b>内存管理</b>：智能释放不需要的图片内存，减少占用</li>
        <li><b>多线程处理</b>：后台线程处理文件操作，界面保持流畅</li>
        <li><b>大图片优化</b>：自动检测大图并优化加载策略</li>
        <li><b>批量处理</b>：支持高效处理数千张图片</li>
        </ul>

        <h4 style="color: {colors['text_primary']};">网络存储优化</h4>
        <ul style="line-height: 1.8; color: {colors['text_primary']};">
        <li><b>SMB/NAS 支持</b>：支持 \\\\server\\share 格式的网络路径</li>
        <li><b>网络缓存</b>：智能缓存网络图片提高访问速度</li>
        <li><b>自动重试</b>：网络操作失败时自动重试3次</li>
        <li><b>连接优化</b>：维护网络连接池提高效率</li>
        </ul>
        '''

    def create_help_tab(self):
        """创建帮助标签页"""

        widget = QWidget()
        layout = QVBoxLayout(widget)

        text_browser = QTextBrowser()

        # 应用主题样式
        c = default_theme.colors
        text_browser.setStyleSheet(f"""
            QTextBrowser {{
                background-color: {c.BACKGROUND_PRIMARY};
                color: {c.TEXT_PRIMARY};
                font-size: 13px;
                line-height: 1.6;
                selection-background-color: {c.PRIMARY};
                selection-color: white;
                border: none;
            }}
        """)

        text_browser.setHtml(self._generate_help_html())
        layout.addWidget(text_browser)

        return widget

    def _generate_faq_html(self):
        """生成常见问题标签页的HTML内容"""
        colors = self._get_html_colors()

        return f'''
        <h2 style="border-bottom: 2px solid {colors['primary']}; padding-bottom: 8px; color: {colors['text_primary']};">常见问题解答</h2>

        <h3 style="color: {colors['text_primary']}; margin-top: 20px;">图片显示和操作</h3>

        <div style="background-color: {colors['bg_hover']}; padding: 15px; border-left: 4px solid {colors['primary']}; margin: 15px 0;">
        <h4 style="color: {colors['primary']};">Q: 图片显示很慢或模糊？</h4>
        <p style="line-height: 1.6; color: {colors['text_primary']};"><b>A:</b> 对于大图片和网络路径，程序会自动检测并启用性能优化模式，提供最佳的显示效果。</p>

        <h4 style="color: {colors['primary']}; margin-top: 15px;">Q: 缩放后图片位置错乱？</h4>
        <p style="line-height: 1.6; color: {colors['text_primary']};"><b>A:</b> 按 Ctrl+F 键重置为适应窗口模式，或按 Ctrl+0 显示原始大小。</p>

        <h4 style="color: {colors['primary']}; margin-top: 15px;">Q: 删除的图片会永久消失吗？</h4>
        <p style="line-height: 1.6; color: {colors['text_primary']};"><b>A:</b> 不会，删除的图片会移动到 "remove" 目录中。再次按 Delete 键即可撤销删除，将图片从 remove 目录恢复。</p>
        </div>

        <h3 style="color: {colors['text_primary']}; margin-top: 20px;">分类和管理</h3>

        <div style="background-color: {colors['bg_hover']}; padding: 15px; border-left: 4px solid {colors['primary']}; margin: 15px 0;">
        <h4 style="color: {colors['primary']};">Q: 如何撤销错误的分类操作？</h4>
        <p style="line-height: 1.6; color: {colors['text_primary']};"><b>A:</b> <b>单分类模式</b>：再次点击已分类的类别按钮可以撤销分类（复制模式移除该文件，移动模式文件返回原目录）。<b>多分类模式</b>：再次点击已分类的类别按钮可以移除该分类。<b>撤销删除</b>：再次按 Delete 键可以从 remove 目录恢复。</p>

        <h4 style="color: {colors['primary']}; margin-top: 15px;">Q: 如何重新开始新手教程？</h4>
        <p style="line-height: 1.6; color: {colors['text_primary']};"><b>A:</b> 在菜单栏点击"帮助" → "显示新手教程"即可重新启动交互式引导教程。</p>

        <h4 style="color: {colors['primary']}; margin-top: 15px;">Q: 如何开启自动更新功能？</h4>
        <p style="line-height: 1.6; color: {colors['text_primary']};"><b>A:</b> 在菜单栏点击"设置"打开设置面板，在"更新"选项中开启"自动检查更新"。程序会定期检查新版本，下载完成后提示重启更新。也可以在帮助菜单中手动点击"检查更新"。</p>
        </div>

        <h3 style="color: {colors['text_primary']}; margin-top: 20px;">网络存储</h3>

        <div style="background-color: {colors['bg_hover']}; padding: 15px; border-left: 4px solid {colors['primary']}; margin: 15px 0;">
        <h4 style="color: {colors['primary']};">Q: 支持网络驱动器（NAS）吗？</h4>
        <p style="line-height: 1.6; color: {colors['text_primary']};"><b>A:</b> 支持，默认启用"网络路径优化"设置以提高性能。</p>

        <h4 style="color: {colors['primary']}; margin-top: 15px;">Q: 网络断开后程序崩溃？</h4>
        <p style="line-height: 1.6; color: {colors['text_primary']};"><b>A:</b> 程序有文件操作重试机制，网络操作失败时会自动重试3次。建议保持网络稳定以获得最佳性能。</p>

        <h4 style="color: {colors['primary']}; margin-top: 15px;">Q: SMB 共享访问很慢？</h4>
        <p style="line-height: 1.6; color: {colors['text_primary']};"><b>A:</b> 默认启用"SMB缓存优化"，程序会缓存常用图片以提高访问速度。</p>
        </div>

        <h3 style="color: {colors['text_primary']}; margin-top: 20px;">性能和优化</h3>

        <div style="background-color: {colors['bg_hover']}; padding: 15px; border-left: 4px solid {colors['primary']}; margin: 15px 0;">
        <h4 style="color: {colors['primary']};">Q: 处理大量图片时程序卡顿？</h4>
        <p style="line-height: 1.6; color: {colors['text_primary']};"><b>A:</b> 程序会根据图片数量和系统性能自动调整优化策略，包括减少动画效果和智能预加载。</p>

        <h4 style="color: {colors['primary']}; margin-top: 15px;">Q: 内存占用过高？</h4>
        <p style="line-height: 1.6; color: {colors['text_primary']};"><b>A:</b> 程序会自动管理内存，也可以手动清理缓存（帮助对话框中的清理按钮）。</p>

        <h4 style="color: {colors['primary']}; margin-top: 15px;">Q: 如何清理程序产生的缓存？</h4>
        <p style="line-height: 1.6; color: {colors['text_primary']};"><b>A:</b> 在帮助对话框中点击"清理SMB缓存"按钮，或手动删除用户目录下的 .image_classifier_cache 文件夹。</p>
        </div>

        <h3 style="color: {colors['text_primary']}; margin-top: 20px;">故障排除</h3>

        <div style="background-color: {colors['bg_hover']}; padding: 15px; border-left: 4px solid {colors['primary']}; margin: 15px 0;">
        <h4 style="color: {colors['primary']};">常见问题诊断步骤</h4>
        <ol style="line-height: 1.8; color: {colors['text_primary']};">
        <li><b>检查日志</b>：查看 logs/image_classifier.log 了解错误详情</li>
        <li><b>重启程序</b>：简单重启通常能解决临时问题</li>
        <li><b>清理缓存</b>：清理程序缓存解决数据冲突</li>
        <li><b>检查权限</b>：确保对目标目录有读写权限</li>
        <li><b>更新程序</b>：下载最新版本获得 bug 修复</li>
        </ol>

        <h4 style="color: {colors['primary']}; margin-top: 15px;">获取帮助</h4>
        <p style="line-height: 1.6; color: {colors['text_primary']};">如果问题仍未解决，请将错误日志和操作步骤反馈给我们：</p>
        <p style="background-color: {colors['bg_secondary']}; padding: 12px; border-left: 4px solid {colors['primary']}; margin: 10px 0;">
        <b style="color: {colors['text_primary']};">问题反馈邮箱：</b><br>
        <a href="copy://{CONTACT_INFO['support_email']}" style="color: {colors['primary']}; text-decoration: none; font-size: 15px; font-weight: bold; cursor: pointer;">
        {CONTACT_INFO['support_email']}
        </a>
        <span style="color: {colors['text_secondary']}; font-size: 13px; margin-left: 10px;">（点击复制邮箱地址）</span>
        </p>
        </div>
        '''

    def create_faq_tab(self):
        """创建常见问题标签页"""

        widget = QWidget()
        layout = QVBoxLayout(widget)

        text_browser = QTextBrowser()

        # 应用主题样式
        c = default_theme.colors
        text_browser.setStyleSheet(f"""
            QTextBrowser {{
                background-color: {c.BACKGROUND_PRIMARY};
                color: {c.TEXT_PRIMARY};
                font-size: 13px;
                line-height: 1.6;
                selection-background-color: {c.PRIMARY};
                selection-color: white;
                border: none;
            }}
            a {{
                color: {c.PRIMARY};
                text-decoration: underline;
            }}
            a:hover {{
                color: {c.PRIMARY_LIGHT};
                background-color: {c.BACKGROUND_HOVER};
            }}
        """)

        # 连接链接点击事件
        text_browser.setOpenLinks(False)  # 禁用默认的链接打开行为
        text_browser.anchorClicked.connect(self._handle_link_click)

        text_browser.setHtml(self._generate_faq_html())
        layout.addWidget(text_browser)

        return widget
    
    def _generate_version_history_html(self):
        """生成版本历史HTML内容"""
        html_parts = []
        colors = self._get_html_colors()

        # 根据主题选择版本样式配色
        if default_theme.is_dark:
            # 暗色主题配色
            version_styles = [
                {"bg": "#1e3a1e", "border": "#4caf50", "text": "#81c784", "emoji": "🎉", "label": "(当前版本)"},
                {"bg": "#1a2a3a", "border": "#2196f3", "text": "#64b5f6", "emoji": "✨", "label": ""},
                {"bg": "#2a2a2a", "border": "#6c757d", "text": "#b0b0b0", "emoji": "🚀", "label": ""},
                {"bg": "#3a2a1a", "border": "#ff9800", "text": "#ffb74d", "emoji": "🔧", "label": ""},
                {"bg": "#3a1a2a", "border": "#e91e63", "text": "#f48fb1", "emoji": "📦", "label": ""},
            ]
        else:
            # 亮色主题配色
            version_styles = [
                {"bg": "#e8f5e8", "border": "#4caf50", "text": "#2e7d32", "emoji": "🎉", "label": "(当前版本)"},
                {"bg": "#f0f7ff", "border": "#2196f3", "text": "#1565c0", "emoji": "✨", "label": ""},
                {"bg": "#f8f9fa", "border": "#6c757d", "text": "#495057", "emoji": "🚀", "label": ""},
                {"bg": "#fff3e0", "border": "#ff9800", "text": "#ef6c00", "emoji": "🔧", "label": ""},
                {"bg": "#fce4ec", "border": "#e91e63", "text": "#c2185b", "emoji": "📦", "label": ""},
            ]

        # 只展示最近的3个版本
        recent_versions = VERSION_HISTORY[:3]

        for i, version_info in enumerate(recent_versions):
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
                html_part += f'<ul style="margin: 5px 0; padding-left: 20px; color: {colors["text_primary"]};">'
                for highlight in version_info["highlights"]:
                    html_part += f'<li>{highlight}</li>'
                html_part += '</ul>'
            # 如果没有亮点，使用详细信息的前几项
            elif version_info.get("details"):
                html_part += f'<ul style="margin: 5px 0; padding-left: 20px; color: {colors["text_primary"]};">'
                for detail in version_info["details"][:4]:  # 只显示前4项
                    html_part += f'<li>{detail}</li>'
                html_part += '</ul>'

            html_part += '</div>'
            html_parts.append(html_part)

        # 如果版本数超过3个，添加查看完整更新日志的链接
        if len(VERSION_HISTORY) > 3:
            # 动态获取当前分支
            branch = self._get_git_branch()
            changelog_url = f"https://gitlab.desauto.cn/rd/delivery/data_process/image_classifier/-/blob/{branch}/CHANGELOG.md"

            changelog_link = f'''
            <div style="background-color: {colors['bg_hover']}; padding: 15px; border-radius: 8px; margin: 10px 0; text-align: center; border: 1px dashed {colors['border']};">
            <p style="margin: 0; color: {colors['text_secondary']};">
            查看更多版本历史，请访问：<br>
            <a href="{changelog_url}" style="color: {colors['primary']}; text-decoration: none; font-weight: bold; font-size: 14px;">
            📋 完整更新日志 (CHANGELOG.md)
            </a>
            </p>
            </div>
            '''
            html_parts.append(changelog_link)

        return '\n'.join(html_parts)
        
    def _generate_about_html(self):
        """生成关于标签页的HTML内容"""
        about_info = get_about_info()
        colors = self._get_html_colors()

        return f'''
        <h2 style="border-bottom: 2px solid {colors['primary']}; padding-bottom: 8px; color: {colors['text_primary']};">图片分类工具 v{about_info["version"]}</h2>

        <div style="text-align: center; background-color: {colors['bg_hover']}; padding: 20px; border-left: 4px solid {colors['primary']}; margin: 20px 0;">
        <h3 style="margin: 0; color: {colors['primary']};">专业图片分类管理工具</h3>
        <p style="margin: 10px 0 0 0; color: {colors['text_primary']};">提高图片整理效率，让分类工作更简单</p>
        </div>

        <h3 style="color: {colors['text_primary']}; margin-top: 20px;">核心特性</h3>

        <div style="background-color: {colors['bg_hover']}; padding: 15px; border-left: 4px solid {colors['primary']}; margin: 15px 0;">
        <h4 style="color: {colors['primary']}; margin-top: 0;">图片处理</h4>
        <ul style="margin: 5px 0; padding-left: 20px; line-height: 1.6; color: {colors['text_primary']};">
        <li>支持多种常见图片格式（JPG、PNG、BMP、GIF、TIFF、WebP等）</li>
        <li>智能图片预览和缩放（可配置缩放范围）</li>
        <li>拖拽移动查看细节</li>
        <li>实时信息面板显示</li>
        </ul>

        <h4 style="color: {colors['primary']}; margin-top: 15px;">文件管理</h4>
        <ul style="margin: 5px 0; padding-left: 20px; line-height: 1.6; color: {colors['text_primary']};">
        <li>复制/移动双模式操作</li>
        <li>批量分类处理</li>
        <li>智能类别管理</li>
        <li>自动状态同步</li>
        </ul>

        <h4 style="color: {colors['primary']}; margin-top: 15px;">操作体验</h4>
        <ul style="margin: 5px 0; padding-left: 20px; line-height: 1.6; color: {colors['text_primary']};">
        <li>丰富的快捷键支持</li>
        <li>自定义快捷键设置</li>
        <li>直观的状态提示</li>
        <li>实时进度跟踪</li>
        </ul>

        <h4 style="color: {colors['primary']}; margin-top: 15px;">性能优化</h4>
        <ul style="margin: 5px 0; padding-left: 20px; line-height: 1.6; color: {colors['text_primary']};">
        <li>网络存储优化</li>
        <li>智能缓存机制</li>
        <li>多线程处理</li>
        <li>内存自动管理</li>
        </ul>
        </div>

        <h3 style="color: {colors['text_primary']}; margin-top: 20px;">技术架构</h3>

        <table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse; width: 100%; margin: 10px 0; border: 1px solid {colors['border']};">
        <tr style="background-color: {colors['bg_secondary']};">
        <th style="width: 30%; padding: 8px; border: 1px solid {colors['border']}; text-align: left; color: {colors['text_primary']};">技术栈</th>
        <th style="width: 35%; padding: 8px; border: 1px solid {colors['border']}; text-align: left; color: {colors['text_primary']};">版本/库</th>
        <th style="width: 35%; padding: 8px; border: 1px solid {colors['border']}; text-align: left; color: {colors['text_primary']};">说明</th>
        </tr>
        <tr>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};"><b>开发语言</b></td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">Python 3.8+</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">主要开发语言</td>
        </tr>
        <tr style="background-color: {colors['bg_hover']};">
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};"><b>界面框架</b></td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">PyQt6</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">现代化GUI框架</td>
        </tr>
        <tr>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};"><b>图像处理</b></td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">OpenCV + Pillow</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">图片加载和处理</td>
        </tr>
        <tr style="background-color: {colors['bg_hover']};">
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};"><b>数据存储</b></td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">JSON</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">配置和状态存储</td>
        </tr>
        <tr>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};"><b>日志系统</b></td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">Python logging</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">错误跟踪和调试</td>
        </tr>
        <tr style="background-color: {colors['bg_hover']};">
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};"><b>多线程</b></td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">QThread</td>
        <td style="padding: 8px; border: 1px solid {colors['border']}; color: {colors['text_primary']};">后台任务处理</td>
        </tr>
        </table>

        <h3 style="color: {colors['text_primary']}; margin-top: 20px;">版本发展历程</h3>
        <div style="margin: 20px 0;">
        {self._generate_version_history_html()}
        </div>

        <div style="background-color: {colors['bg_hover']}; padding: 20px; border-left: 4px solid {colors['primary']}; text-align: center; margin: 30px 0;">
        <h3 style="margin: 0 0 15px 0; color: {colors['primary']};">版权信息</h3>
        <p style="margin: 5px 0; color: {colors['text_primary']};"><b>© 2024 GDDI</b></p>
        <p style="margin: 5px 0; color: {colors['text_primary']};">专注于提升图片管理效率的专业软件</p>
        <p style="margin: 15px 0 5px 0; color: {colors['text_secondary']}; font-size: 14px; line-height: 1.6;">
        本软件遵循 MIT 开源协议<br>
        感谢所有贡献者和用户的支持
        </p>
        <div style="margin-top: 15px; padding-top: 15px; border-top: 1px solid {colors['border']};">
        <span style="color: {colors['text_secondary']}; font-size: 13px;">
        让图片整理变得简单高效
        </span>
        </div>
        </div>
        '''

    def create_about_tab(self):
        """创建关于标签页"""

        widget = QWidget()
        layout = QVBoxLayout(widget)

        text_browser = QTextBrowser()

        # 应用主题样式
        c = default_theme.colors
        text_browser.setStyleSheet(f"""
            QTextBrowser {{
                background-color: {c.BACKGROUND_PRIMARY};
                color: {c.TEXT_PRIMARY};
                font-size: 13px;
                line-height: 1.6;
                selection-background-color: {c.PRIMARY};
                selection-color: white;
                border: none;
            }}
            a {{
                color: {c.PRIMARY};
                text-decoration: underline;
            }}
            a:hover {{
                color: {c.PRIMARY_LIGHT};
                background-color: {c.BACKGROUND_HOVER};
            }}
        """)

        # 连接链接点击事件
        text_browser.setOpenLinks(False)  # 禁用默认的链接打开行为
        text_browser.anchorClicked.connect(self._handle_link_click)

        text_browser.setHtml(self._generate_about_html())
        layout.addWidget(text_browser)

        return widget


