"""
配置管理模块

提供应用程序配置的加载、保存和管理功能。
"""

import json
import logging
import threading
from pathlib import Path
from ..utils.exceptions import ConfigError


class Config:
    """配置管理类"""
    
    def __init__(self, base_dir=None):
        self.base_dir = base_dir
        self.config_file = Path(base_dir) / 'config.json' if base_dir else None
        self.category_order = []
        self.category_shortcuts = {}
        self._lock = threading.Lock()
        
        # 系统保留的快捷键和类别
        self.reserved_shortcuts = {
            # 基本导航
            'Left', 'Right', 'Up', 'Down', 'Return', 'Delete',
            # 组合键导航
            'Ctrl+Left', 'Ctrl+Right', 'Ctrl+Up', 'Ctrl+Down',
            'Alt+Left', 'Alt+Right', 'Alt+Up', 'Alt+Down',
            # 图像控制快捷键
            'Ctrl+=', 'Ctrl+-', 'Ctrl+0', 'F',
            # 系统功能键
            'F5', 'Escape', 'Tab', 'Shift+Tab',
            # 常用系统快捷键
            'Ctrl+C', 'Ctrl+V', 'Ctrl+X', 'Ctrl+Z', 'Ctrl+Y',
            'Ctrl+A', 'Ctrl+S', 'Ctrl+O', 'Ctrl+N', 'Ctrl+Q',
            'Alt+F4', 'Ctrl+W', 'Ctrl+T', 'Ctrl+R', 'Ctrl+F',
        }
        self.reserved_categories = {'remove'}  # 保留的类别名称
        
        if self.config_file:
            self.load_config()
        
    def is_shortcut_available(self, shortcut):
        """检查快捷键是否可用"""
        with self._lock:
            if shortcut in self.reserved_shortcuts:
                return False
            return shortcut not in self.category_shortcuts.values()
        
    def get_default_shortcut(self, index):
        """获取默认快捷键"""
        if index < 10:  # 0-9
            return str(index)
        elif index < 36:  # a-z
            return chr(ord('a') + index - 10)
        return None
        
    def assign_default_shortcuts(self, categories):
        """为新类别分配默认快捷键"""
        with self._lock:
            # 清除已不存在的类别的快捷键
            self.category_shortcuts = {k: v for k, v in self.category_shortcuts.items() if k in categories}
            
            # 获取已使用的快捷键，包括保留快捷键
            used_shortcuts = set(self.category_shortcuts.values()) | self.reserved_shortcuts
            
            # 为没有快捷键的类别按顺序分配快捷键
            categories_without_shortcut = [cat for cat in categories if cat not in self.category_shortcuts]
            shortcut_index = 1  # 从1开始，跳过0（为了避免和Ctrl+0冲突的混淆）
            
            for category in categories_without_shortcut:
                # 找到下一个可用的快捷键
                while True:
                    shortcut = self.get_default_shortcut(shortcut_index)
                    if shortcut is None or shortcut not in used_shortcuts:
                        if shortcut:
                            self.category_shortcuts[category] = shortcut
                            used_shortcuts.add(shortcut)
                        break
                    shortcut_index += 1
                shortcut_index += 1
        
    def load_config(self):
        """加载配置"""
        if not self.config_file:
            return
            
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
                with self._lock:
                    self.category_order = config_data.get('category_order', [])
                    self.category_shortcuts = config_data.get('category_shortcuts', {})
        except FileNotFoundError:
            with self._lock:
                self.category_shortcuts = {}
            self.save_config()
        except (json.JSONDecodeError, OSError) as e:
            raise ConfigError(f"加载配置文件失败: {e}")
            
    def save_config(self):
        """保存配置"""
        if not self.config_file:
            return
            
        try:
            config = {
                'category_order': self.category_order,
                'category_shortcuts': self.category_shortcuts
            }
            # 确保配置文件目录存在
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=4)
        except (OSError, IOError) as e:
            raise ConfigError(f"保存配置文件失败: {e}")
            
    def set_base_dir(self, base_dir):
        """设置基础目录并重新加载配置"""
        self.base_dir = base_dir
        self.config_file = Path(base_dir) / 'config.json'
        self.load_config()
        
    def get_state_file_path(self):
        """获取状态文件路径"""
        if not self.base_dir:
            raise ConfigError("基础目录未设置")
        return Path(self.base_dir) / 'state.json'

    def sort_categories(self, categories):
        """根据快捷键对类别进行排序"""
        def get_shortcut_weight(category):
            shortcut = self.category_shortcuts.get(category, '')
            if not shortcut:
                return (3, category)  # 没有快捷键的放最后
            if shortcut.isdigit():
                return (0, int(shortcut), category)  # 数字快捷键优先
            if len(shortcut) == 1 and shortcut.isalpha():
                return (1, shortcut, category)  # 字母快捷键次之
            return (2, shortcut, category)  # 组合键放最后
            
        return sorted(categories, key=get_shortcut_weight)


class ConfigurationManager:
    """配置管理器 - 统一管理所有配置相关功能"""
    
    def __init__(self, base_dir=None):
        self.config = Config(base_dir)
        self.logger = logging.getLogger(__name__)
        
    def load_application_config(self):
        """加载应用配置"""
        try:
            return self.config.load_config()
        except ConfigError as e:
            self.logger.error(f"配置加载失败: {e}")
            raise
        
    def save_application_config(self):
        """保存应用配置"""
        try:
            return self.config.save_config()
        except ConfigError as e:
            self.logger.error(f"配置保存失败: {e}")
            raise
        
    def get_category_config(self, categories):
        """获取类别配置"""
        return self.config.sort_categories(categories)
        
    def update_shortcuts(self, categories):
        """更新快捷键配置"""
        try:
            self.config.assign_default_shortcuts(categories)
            self.save_application_config()
        except ConfigError as e:
            self.logger.error(f"快捷键更新失败: {e}")
            raise
