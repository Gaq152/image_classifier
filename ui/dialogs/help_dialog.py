"""帮助对话框模块"""

import logging
import re
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
            base_path = Path(__file__).parent.parent.parent
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

    def _get_template_variables(self):
        """获取模板变量，包括颜色和动态数据"""
        c = default_theme.colors
        about_info = get_about_info()

        return {
            # 颜色变量
            'bg_primary': c.BACKGROUND_PRIMARY,
            'bg_secondary': c.BACKGROUND_SECONDARY,
            'bg_hover': c.BACKGROUND_HOVER,
            'text_primary': c.TEXT_PRIMARY,
            'text_secondary': c.TEXT_SECONDARY,
            'border': c.BORDER_MEDIUM,
            'primary': c.PRIMARY,
            'primary_light': c.PRIMARY_LIGHT,
            # 动态数据
            'version': about_info["version"],
            'support_email': CONTACT_INFO['support_email'],
            'version_history': self._generate_version_history_html(),
        }

    def _load_html_template(self, template_name):
        """加载并渲染HTML模板文件"""
        try:
            template_path = self._get_resource_path(f'assets/html/{template_name}')
            if template_path is None or not template_path.exists():
                self.logger.warning(f"模板文件不存在: {template_name}")
                return f"<p>无法加载内容: {template_name}</p>"

            # 读取模板内容
            with open(template_path, 'r', encoding='utf-8') as f:
                template = f.read()

            # 获取模板变量并替换
            variables = self._get_template_variables()

            # 使用正则替换 {{variable}} 格式的占位符
            def replace_var(match):
                var_name = match.group(1)
                return str(variables.get(var_name, match.group(0)))

            html = re.sub(r'\{\{(\w+)\}\}', replace_var, template)
            return html

        except Exception as e:
            self.logger.error(f"加载HTML模板失败: {template_name}, 错误: {e}")
            return f"<p>加载失败: {e}</p>"

    def _get_git_branch(self):
        """获取当前 git 分支名称"""
        try:
            result = subprocess.run(
                ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
                capture_output=True,
                text=True,
                timeout=3,
                cwd=Path(__file__).parent.parent
            )
            if result.returncode == 0:
                branch = result.stdout.strip()
                return branch if branch else 'main'
        except Exception as e:
            self.logger.debug(f"获取 git 分支失败: {e}")
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
            self.setStyleSheet(self._get_dialog_style())

            # 更新所有 QTextBrowser 的样式并重新生成HTML内容
            tab_widget = self.findChild(QTabWidget)
            if tab_widget:
                # Tab名称到模板文件的映射
                tab_template_map = {
                    '快速入门': 'quick_start.html',
                    '使用指南': 'user_guide.html',
                    '常见问题': 'faq.html',
                    '关于': 'about.html',
                }

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

                            # 根据标签页名称重新加载HTML内容
                            tab_title = tab_widget.tabText(i)
                            template_name = tab_template_map.get(tab_title)
                            if template_name:
                                text_browser.setHtml(self._load_html_template(template_name))

            self.update()
        except Exception as e:
            self.logger.error(f"应用主题失败: {e}")

    def _create_browser_tab(self, template_name, enable_links=False):
        """工厂方法：创建带QTextBrowser的标签页

        Args:
            template_name: HTML模板文件名
            enable_links: 是否启用链接点击处理
        """
        widget = QWidget()
        layout = QVBoxLayout(widget)

        text_browser = QTextBrowser()
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

        if enable_links:
            text_browser.setOpenLinks(False)
            text_browser.anchorClicked.connect(self._handle_link_click)

        text_browser.setHtml(self._load_html_template(template_name))
        layout.addWidget(text_browser)

        return widget

    def initUI(self):
        """初始化UI"""
        try:
            self.setWindowTitle('帮助和关于')
            self.setMinimumSize(700, 500)
            self.setModal(True)
            self.setStyleSheet(self._get_dialog_style())

            layout = QVBoxLayout(self)
            tab_widget = QTabWidget()

            # 使用工厂方法创建标签页
            tab_widget.addTab(self._create_browser_tab('quick_start.html'), '快速入门')
            tab_widget.addTab(self._create_browser_tab('user_guide.html'), '使用指南')
            tab_widget.addTab(self._create_browser_tab('faq.html', enable_links=True), '常见问题')
            tab_widget.addTab(self._create_browser_tab('about.html', enable_links=True), '关于')

            layout.addWidget(tab_widget)

            # 提示信息
            hint_layout = QHBoxLayout()
            hint_layout.addStretch()
            hint_label = QLabel("💡 提示：更多设置请点击工具栏的 ⚙️ 设置按钮")
            hint_label.setStyleSheet("font-size: 12px; padding: 10px;")
            hint_layout.addWidget(hint_label)
            hint_layout.addStretch()
            layout.addLayout(hint_layout)

            self._apply_theme()

        except Exception as e:
            self.logger.error(f"初始化帮助对话框UI失败: {e}")

    def _handle_link_click(self, url):
        """处理链接点击事件"""
        try:
            url_str = url.toString()
            if url_str.startswith('copy://'):
                email = url_str.replace('copy://', '')
                clipboard = QApplication.clipboard()
                clipboard.setText(email)
                toast_success(self, f'邮箱地址已复制: {email}')
                self.logger.info(f"复制邮箱地址到剪贴板: {email}")
            else:
                QDesktopServices.openUrl(url)
        except Exception as e:
            self.logger.error(f"处理链接点击失败: {e}")
            toast_error(self, f'操作失败: {e}')

    def _generate_version_history_html(self):
        """生成版本历史HTML内容（动态内容，保留在Python中）"""
        html_parts = []
        c = default_theme.colors

        # 根据主题选择版本样式配色
        if default_theme.is_dark:
            version_styles = [
                {"bg": "#1e3a1e", "border": "#4caf50", "text": "#81c784", "emoji": "🎉", "label": "(当前版本)"},
                {"bg": "#1a2a3a", "border": "#2196f3", "text": "#64b5f6", "emoji": "✨", "label": ""},
                {"bg": "#2a2a2a", "border": "#6c757d", "text": "#b0b0b0", "emoji": "🚀", "label": ""},
            ]
        else:
            version_styles = [
                {"bg": "#e8f5e8", "border": "#4caf50", "text": "#2e7d32", "emoji": "🎉", "label": "(当前版本)"},
                {"bg": "#f0f7ff", "border": "#2196f3", "text": "#1565c0", "emoji": "✨", "label": ""},
                {"bg": "#f8f9fa", "border": "#6c757d", "text": "#495057", "emoji": "🚀", "label": ""},
            ]

        # 只展示最近的3个版本
        recent_versions = VERSION_HISTORY[:3]

        for i, version_info in enumerate(recent_versions):
            style = version_styles[min(i, len(version_styles) - 1)]
            version_label = style["label"] if i == 0 else ""

            html_part = f'''
            <div style="background-color: {style["bg"]}; padding: 15px; border-radius: 8px; margin: 10px 0; border-left: 4px solid {style["border"]};">
            <h4 style="color: {style["text"]}; margin: 0 0 10px 0;">{style["emoji"]} v{version_info["version"]} {version_label} - {version_info["date"]}</h4>
            '''

            if version_info.get("title"):
                html_part += f'<p style="margin: 0 0 10px 0; font-weight: bold; color: {style["text"]};">{version_info["title"]}</p>'

            if version_info.get("highlights"):
                html_part += f'<ul style="margin: 5px 0; padding-left: 20px; color: {c.TEXT_PRIMARY};">'
                for highlight in version_info["highlights"]:
                    html_part += f'<li>{highlight}</li>'
                html_part += '</ul>'
            elif version_info.get("details"):
                html_part += f'<ul style="margin: 5px 0; padding-left: 20px; color: {c.TEXT_PRIMARY};">'
                for detail in version_info["details"][:4]:
                    html_part += f'<li>{detail}</li>'
                html_part += '</ul>'

            html_part += '</div>'
            html_parts.append(html_part)

        # 查看更多链接
        if len(VERSION_HISTORY) > 3:
            branch = self._get_git_branch()
            changelog_url = f"https://github.com/Gaq152/image_classifier/blob/{branch}/CHANGELOG.md"
            changelog_link = f'''
            <div style="background-color: {c.BACKGROUND_HOVER}; padding: 15px; border-radius: 8px; margin: 10px 0; text-align: center; border: 1px dashed {c.BORDER_MEDIUM};">
            <p style="margin: 0; color: {c.TEXT_SECONDARY};">
            查看更多版本历史，请访问：<br>
            <a href="{changelog_url}" style="color: {c.PRIMARY}; text-decoration: none; font-weight: bold; font-size: 14px;">
            📋 完整更新日志 (CHANGELOG.md)
            </a>
            </p>
            </div>
            '''
            html_parts.append(changelog_link)

        return '\n'.join(html_parts)
