"""
配置管理模块

提供应用程序配置的加载、保存和管理功能。
"""

import json
import logging
import threading
from pathlib import Path
from utils.exceptions import ConfigError
from utils.app_config import get_app_config


class Config:
    """配置管理类"""
    
    def __init__(self, base_dir=None):
        self.base_dir = base_dir
        self.config_file = Path(base_dir) / 'config.json' if base_dir else None
        self.category_order = []
        self.category_shortcuts = {}
        self.ignored_categories = []  # 被忽略的类别目录列表
        self.category_sort_mode = "name"  # 类别排序模式: "name", "shortcut" 或 "count"
        self.sort_ascending = True  # 排序方向: True=升序, False=降序
        self._lock = threading.Lock()
        self._save_lock = threading.Lock()  # 文件写入锁，防止并发保存
        self._last_save_time = 0  # 上次保存时间戳，用于防抖
        
        # 系统保留的快捷键和类别
        self.reserved_shortcuts = {
            # 基本导航
            'Left', 'Right', 'Up', 'Down', 'Return', 'Delete',
            # 组合键导航
            'Ctrl+Left', 'Ctrl+Right', 'Ctrl+Up', 'Ctrl+Down',
            'Alt+Left', 'Alt+Right', 'Alt+Up', 'Alt+Down',
            # 图像控制快捷键
            'Ctrl+=', 'Ctrl+-', 'Ctrl+0', 'Ctrl+F',
            # 系统功能键
            'F5', 'Escape', 'Tab', 'Shift+Tab',
            # 常用系统快捷键
            'Ctrl+C', 'Ctrl+V', 'Ctrl+X', 'Ctrl+Z', 'Ctrl+Y',
            'Ctrl+A', 'Ctrl+S', 'Ctrl+O', 'Ctrl+N', 'Ctrl+Q',
            'Alt+F4', 'Ctrl+W', 'Ctrl+T', 'Ctrl+R',
        }
        self.reserved_categories = {'remove'}  # 保留的类别名称
        
        if self.config_file:
            self.load_config()
        
    def is_shortcut_available(self, shortcut):
        """检查快捷键是否可用"""
        with self._lock:
            # 标准化快捷键格式，单字母快捷键转为小写进行比较
            normalized_shortcut = self._normalize_shortcut(shortcut)
            
            # 检查是否为保留快捷键
            if normalized_shortcut in self.reserved_shortcuts:
                return False
            
            # 检查是否与现有类别快捷键冲突（大小写不敏感）
            for existing_shortcut in self.category_shortcuts.values():
                if self._normalize_shortcut(existing_shortcut) == normalized_shortcut:
                    return False
            
            return True
    
    def _normalize_shortcut(self, shortcut):
        """标准化快捷键格式，用于一致性比较"""
        if not shortcut:
            return shortcut
            
        # 分割组合键
        parts = shortcut.split('+')
        if len(parts) == 1:
            # 单字母快捷键，转为小写
            if len(shortcut) == 1 and shortcut.isalpha():
                return shortcut.lower()
            else:
                return shortcut
        else:
            # 组合键，只将最后一部分（实际按键）标准化
            modifiers = parts[:-1]
            key_part = parts[-1]
            if len(key_part) == 1 and key_part.isalpha():
                key_part = key_part.lower()
            return '+'.join(modifiers + [key_part])
        
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
                    self.ignored_categories = config_data.get('ignored_categories', [])  # 忽略列表
                    self.category_sort_mode = config_data.get('category_sort_mode', 'name')  # 类别排序模式
                    self.sort_ascending = config_data.get('sort_ascending', True)  # 排序方向

                    # 迁移逻辑：如果旧配置中有更新相关字段，迁移到全局配置
                    self._migrate_update_config(config_data)
        except FileNotFoundError:
            # 配置文件不存在，初始化默认值并尝试保存
            with self._lock:
                self.category_shortcuts = {}
            # 尝试保存配置文件，如果失败则向上抛出异常（通常是权限问题）
            try:
                self.save_config()
            except (OSError, IOError, ConfigError) as e:
                # 如果是权限错误，向上抛出让调用者处理
                # ConfigError 可能是由 save_config() 包装后的异常
                raise ConfigError(f"无法创建配置文件（权限不足）: {e}")
        except (json.JSONDecodeError, OSError) as e:
            raise ConfigError(f"加载配置文件失败: {e}")
            
    def save_config(self):
        """保存配置（带防抖和并发保护）"""
        if not self.config_file:
            return

        # 防抖：如果200ms内已保存过，跳过本次保存
        current_time = time.time()
        if current_time - self._last_save_time < 0.2:
            return

        # 文件写入锁：确保同一时间只有一个线程在写入
        with self._save_lock:
            try:
                config = {
                    'category_order': self.category_order,
                    'category_shortcuts': self.category_shortcuts,
                    'ignored_categories': getattr(self, 'ignored_categories', []),
                    'category_sort_mode': getattr(self, 'category_sort_mode', 'name'),
                    'sort_ascending': getattr(self, 'sort_ascending', True),
                }
                # 确保配置文件目录存在
                self.config_file.parent.mkdir(parents=True, exist_ok=True)

                # 写入文件
                with open(self.config_file, 'w', encoding='utf-8') as f:
                    json.dump(config, f, ensure_ascii=False, indent=4)

                # 更新最后保存时间
                self._last_save_time = time.time()

            except (OSError, IOError) as e:
                raise ConfigError(f"保存配置文件失败: {e}")

    def _migrate_update_config(self, config_data):
        """迁移更新相关配置到全局配置

        Args:
            config_data: 从 config.json 加载的配置数据
        """
        # 检查是否有需要迁移的字段
        update_fields = ['auto_update_enabled', 'last_update_check_ts', 'update_endpoint', 'update_token', 'pending_update']
        has_update_config = any(field in config_data for field in update_fields)

        if has_update_config:
            try:
                # 获取全局配置实例
                app_config = get_app_config()

                # 迁移数据到全局配置
                if 'auto_update_enabled' in config_data:
                    app_config.auto_update_enabled = bool(config_data['auto_update_enabled'])
                if 'last_update_check_ts' in config_data:
                    app_config.last_update_check_ts = int(config_data['last_update_check_ts'])
                if 'update_endpoint' in config_data:
                    app_config.update_endpoint = config_data['update_endpoint']
                if 'update_token' in config_data:
                    app_config.update_token = config_data['update_token']
                if 'pending_update' in config_data:
                    app_config.pending_update = config_data['pending_update']

                # 保存本地配置（不再包含更新相关字段）
                self.save_config()

                logging.getLogger(__name__).info(f"已将更新配置从 {self.config_file} 迁移到全局配置")
            except Exception as e:
                logging.getLogger(__name__).error(f"迁移更新配置失败: {e}")
            
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

    def get_sorted_categories(self, categories, sort_mode=None, category_counts=None, ascending=None):
        """根据排序模式返回排序后的类别列表

        Args:
            categories: 类别集合或列表
            sort_mode: 排序模式 ("name", "shortcut" 或 "count")，默认使用配置的模式
            category_counts: 类别分类数量字典 {category_name: count}，仅 count 模式需要
            ascending: 是否升序，默认使用配置的 sort_ascending

        Returns:
            排序后的类别列表
        """
        if sort_mode is None:
            sort_mode = self.category_sort_mode
        if ascending is None:
            ascending = self.sort_ascending

        if sort_mode == "shortcut":
            # 按快捷键排序
            result = self.sort_categories(categories)
        elif sort_mode == "count":
            # 按分类数量排序
            if category_counts is None:
                category_counts = {}
            # 升序时数量少的在前，降序时数量多的在前
            result = sorted(list(categories), key=lambda c: (category_counts.get(c, 0), c))
        else:  # sort_mode == "name" (默认)
            # 按名称排序
            result = sorted(list(categories))

        # 如果是降序，反转结果
        if not ascending:
            result = list(reversed(result))

        return result

    def add_ignored_category(self, category_name):
        """添加类别到忽略列表"""
        with self._lock:
            if category_name not in self.ignored_categories:
                self.ignored_categories.append(category_name)
                return True
            return False

    def remove_ignored_category(self, category_name):
        """从忽略列表移除类别"""
        with self._lock:
            if category_name in self.ignored_categories:
                self.ignored_categories.remove(category_name)
                return True
            return False

    def is_category_ignored(self, category_name):
        """检查类别是否被忽略"""
        with self._lock:
            return category_name in self.ignored_categories


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
