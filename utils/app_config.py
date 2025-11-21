"""
应用配置管理模块

管理应用级别的配置，包括主题、教程状态等。
配置文件存储在用户目录下的 config/app_config.json
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any
from .paths import get_config_dir
from _version_ import __version__


class AppConfig:
    """应用配置管理器（单例模式）

    修复问题1：使用类级单例模式，避免多实例问题
    无论通过何种导入路径访问，都确保只有一个实例存在
    """

    # 类级变量：存储唯一实例和初始化标志
    _instance = None
    _initialized = False

    def __new__(cls):
        """单例模式：确保只创建一个实例"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        # 避免重复初始化（__new__每次都会调用__init__）
        if AppConfig._initialized:
            return

        self.logger = logging.getLogger(__name__)
        self._config_dir = get_config_dir()  # 使用统一的路径管理
        self._config_file = self._config_dir / "app_config.json"
        self._config = self._load_config()

        # 标记已初始化
        AppConfig._initialized = True
        self.logger.debug("[单例模式] AppConfig实例已创建并初始化")

    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            "theme": "light",  # 主题：light 或 dark
            "theme_mode": "manual",  # 主题模式：manual(手动), auto(自动跟随时间), system(跟随系统)
            "tutorial_completed": False,  # 是否完成教程
            "tutorial_skipped": False,  # 是否跳过教程
            "version": __version__,  # 配置文件版本（自动同步程序版本）
            # 自动更新相关配置
            "auto_update_enabled": True,  # 自动检查更新开关
            "last_update_check_ts": 0,  # 最后检查更新的时间戳
            "update_endpoint": "https://gitlab.desauto.cn/api/v4/projects/820/packages/generic/image_classifier/latest/manifest.json",  # 更新检查端点
            "update_token": "",  # 更新令牌（可选）
            "pending_update": {},  # 待处理的更新信息
            # 工作目录相关配置
            "last_opened_directory": "",  # 最后打开的图片目录
            "last_opened_drive_is_network": False,  # 最后打开目录的盘符是否为网络路径
            # 日志和提示相关配置
            "log_level": "INFO",  # 日志级别：DEBUG, INFO, WARNING, ERROR, CRITICAL
            "toast_level": "INFO",  # Toast提示级别：DEBUG, INFO, WARNING, ERROR
            # 图像预览相关配置
            "image_zoom_max": 3.0,  # 最大缩放倍数（范围：1.0-20.0）
            "image_zoom_min": 0.1,  # 最小缩放倍数（范围：0.01-1.0）
            "global_zoom_enabled": False,  # 是否启用全局缩放（将缩放倍数应用到所有图片）
            "last_zoom_factor": 1.0,  # 最后使用的缩放倍数（自动记录）
            # 缓存预热相关配置（优化8）
            "cache_warmup_enabled": True,  # 缓存预热开关（仅网络路径有效）
            "cache_warmup_count": 100,  # 预热图片数量（范围：10-500）
            # 循环翻页相关配置
            "local_loop_enabled": True,  # 本地路径循环翻页（默认开启）
            "network_loop_enabled": False  # 网络路径循环翻页（默认关闭，开启后会预热末尾图片）
        }

    def _load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        try:
            if self._config_file.exists():
                with open(self._config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    self.logger.info(f"已加载应用配置: {self._config_file}")

                    # 合并默认配置（处理新增配置项）
                    default_config = self._get_default_config()
                    for key, value in default_config.items():
                        if key not in config:
                            config[key] = value

                    # 检查并更新版本号
                    if config.get('version') != __version__:
                        old_version = config.get('version', '未知')
                        config['version'] = __version__
                        self.logger.info(f"配置文件版本已更新: {old_version} -> {__version__}")
                        # 立即保存更新后的配置
                        with open(self._config_file, 'w', encoding='utf-8') as f:
                            json.dump(config, f, ensure_ascii=False, indent=2)

                    return config
            else:
                self.logger.info("配置文件不存在，创建默认配置文件")
                default_config = self._get_default_config()
                # 立即保存默认配置到文件
                with open(self._config_file, 'w', encoding='utf-8') as f:
                    json.dump(default_config, f, ensure_ascii=False, indent=2)
                self.logger.info(f"已创建默认配置文件: {self._config_file}")
                return default_config
        except Exception as e:
            self.logger.error(f"加载配置文件失败: {e}，使用默认配置")
            return self._get_default_config()

    def _save_config(self):
        """保存配置文件"""
        try:
            with open(self._config_file, 'w', encoding='utf-8') as f:
                json.dump(self._config, f, ensure_ascii=False, indent=2)
            self.logger.debug(f"已保存应用配置: {self._config_file}")
        except Exception as e:
            self.logger.error(f"保存配置文件失败: {e}")

    # ==================== 主题配置 ====================

    @property
    def theme(self) -> str:
        """获取主题设置"""
        return self._config.get("theme", "light")

    @theme.setter
    def theme(self, value: str):
        """设置主题"""
        if value in ("light", "dark"):
            self._config["theme"] = value
            self._save_config()
            self.logger.debug(f"主题已设置为: {value}")
        else:
            self.logger.warning(f"无效的主题值: {value}，应为 'light' 或 'dark'")

    def is_dark_theme(self) -> bool:
        """是否为暗色主题"""
        return self.theme == "dark"

    @property
    def theme_mode(self) -> str:
        """获取主题模式"""
        return self._config.get("theme_mode", "manual")

    @theme_mode.setter
    def theme_mode(self, value: str):
        """设置主题模式"""
        if value in ("manual", "auto", "system"):
            self._config["theme_mode"] = value
            self._save_config()

            # 获取切换后实际生效的主题
            if value == "auto":
                actual_theme = self.get_auto_theme_by_time()
            elif value == "system":
                actual_theme = self.get_system_theme()
            else:
                actual_theme = self.theme

            self.logger.info(f"主题模式已设置为: {value}, 当前主题: {actual_theme}")
        else:
            self.logger.warning(f"无效的主题模式值: {value}，应为 'manual', 'auto' 或 'system'")

    def get_auto_theme_by_time(self) -> str:
        """
        根据当前时间自动判断应该使用的主题

        Returns:
            str: "light" 或 "dark"
        """
        from datetime import datetime
        current_hour = datetime.now().hour

        # 8:00-18:00 使用亮色主题，其他时间使用暗色主题
        if 8 <= current_hour < 18:
            return "light"
        else:
            return "dark"

    def get_system_theme(self) -> str:
        """
        获取系统主题设置

        Returns:
            str: "light" 或 "dark"
        """
        try:
            import winreg
            # Windows 10/11 系统主题设置位置
            registry = winreg.ConnectRegistry(None, winreg.HKEY_CURRENT_USER)
            key = winreg.OpenKey(registry, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            winreg.CloseKey(key)

            # 0 = 暗色主题, 1 = 亮色主题
            return "light" if value == 1 else "dark"
        except Exception as e:
            self.logger.warning(f"无法获取系统主题设置: {e}，使用默认亮色主题")
            return "light"

    def should_use_dark_theme(self) -> bool:
        """
        判断当前是否应该使用暗色主题（考虑自动模式和系统模式）

        Returns:
            bool: True 表示应该使用暗色主题
        """
        if self.theme_mode == "auto":
            return self.get_auto_theme_by_time() == "dark"
        elif self.theme_mode == "system":
            return self.get_system_theme() == "dark"
        else:
            return self.theme == "dark"

    # ==================== 教程配置 ====================

    @property
    def tutorial_completed(self) -> bool:
        """教程是否已完成"""
        return self._config.get("tutorial_completed", False)

    @tutorial_completed.setter
    def tutorial_completed(self, value: bool):
        """设置教程完成状态"""
        self._config["tutorial_completed"] = value
        self._save_config()
        self.logger.info(f"教程完成状态已设置为: {value}")

    @property
    def tutorial_skipped(self) -> bool:
        """教程是否已跳过"""
        return self._config.get("tutorial_skipped", False)

    @tutorial_skipped.setter
    def tutorial_skipped(self, value: bool):
        """设置教程跳过状态"""
        self._config["tutorial_skipped"] = value
        self._save_config()
        self.logger.info(f"教程跳过状态已设置为: {value}")

    def should_show_tutorial(self) -> bool:
        """是否应该显示教程"""
        return not (self.tutorial_completed or self.tutorial_skipped)

    def mark_tutorial_finished(self, completed: bool = True):
        """
        标记教程结束

        Args:
            completed: True表示完成，False表示跳过
        """
        if completed:
            self.tutorial_completed = True
        else:
            self.tutorial_skipped = True

    # ==================== 自动更新配置 ====================

    @property
    def auto_update_enabled(self) -> bool:
        """获取自动更新开关"""
        return self._config.get("auto_update_enabled", True)

    @auto_update_enabled.setter
    def auto_update_enabled(self, value: bool):
        """设置自动更新开关"""
        self._config["auto_update_enabled"] = value
        self._save_config()
        self.logger.info(f"自动更新已{'启用' if value else '禁用'}")

    @property
    def last_update_check_ts(self) -> int:
        """获取最后检查更新的时间戳"""
        return self._config.get("last_update_check_ts", 0)

    @last_update_check_ts.setter
    def last_update_check_ts(self, value: int):
        """设置最后检查更新的时间戳"""
        self._config["last_update_check_ts"] = value
        self._save_config()

    @property
    def update_endpoint(self) -> str:
        """获取更新检查端点"""
        return self._config.get("update_endpoint",
            "https://gitlab.desauto.cn/api/v4/projects/820/packages/generic/image_classifier/latest/manifest.json")

    @update_endpoint.setter
    def update_endpoint(self, value: str):
        """设置更新检查端点"""
        self._config["update_endpoint"] = value
        self._save_config()
        self.logger.info(f"更新端点已设置为: {value}")

    @property
    def update_token(self) -> str:
        """获取更新令牌"""
        return self._config.get("update_token", "")

    @update_token.setter
    def update_token(self, value: str):
        """设置更新令牌"""
        self._config["update_token"] = value
        self._save_config()

    @property
    def pending_update(self) -> dict:
        """获取待处理的更新信息"""
        return self._config.get("pending_update", {})

    @pending_update.setter
    def pending_update(self, value: dict):
        """设置待处理的更新信息"""
        self._config["pending_update"] = value
        self._save_config()

    # ==================== 工作目录配置 ====================

    @property
    def last_opened_directory(self) -> str:
        """获取最后打开的目录"""
        return self._config.get("last_opened_directory", "")

    @last_opened_directory.setter
    def last_opened_directory(self, value: str):
        """设置最后打开的目录"""
        self._config["last_opened_directory"] = value
        self._save_config()
        self.logger.warning(f"最后打开的目录已设置为: {value}")

    @property
    def last_opened_drive_is_network(self) -> bool:
        """获取最后打开的盘符是否为网络路径"""
        return self._config.get("last_opened_drive_is_network", False)

    @last_opened_drive_is_network.setter
    def last_opened_drive_is_network(self, value: bool):
        """设置最后打开的盘符是否为网络路径"""
        self._config["last_opened_drive_is_network"] = value
        self._save_config()

    def get_last_opened_drive(self) -> str:
        """
        从最后打开的目录路径中提取盘符

        Returns:
            str: 盘符（如 "D:"），如果无法提取则返回空字符串
        """
        from pathlib import Path
        last_dir = self.last_opened_directory
        if last_dir:
            return Path(last_dir).drive
        return ""

    def update_last_opened_drive_info(self, directory: str, is_network: bool):
        """
        更新最后打开的目录及其网络状态信息

        Args:
            directory: 目录路径
            is_network: 是否为网络路径
        """
        from pathlib import Path
        path = Path(directory)
        drive = path.drive  # 例如 "D:"

        self._config["last_opened_directory"] = directory
        self._config["last_opened_drive_is_network"] = is_network
        self._save_config()

        path_type = "网络" if is_network else "本地"
        self.logger.info(f"已更新最后打开的目录: {directory} (盘符: {drive}, 类型: {path_type})")

    # ==================== 日志和提示配置 ====================

    @property
    def log_level(self) -> str:
        """获取日志级别"""
        return self._config.get("log_level", "INFO")

    @log_level.setter
    def log_level(self, value: str):
        """设置日志级别"""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if value.upper() in valid_levels:
            self._config["log_level"] = value.upper()
            self._save_config()
            self.logger.info(f"日志级别已设置为: {value.upper()}")
        else:
            self.logger.warning(f"无效的日志级别: {value}，已忽略")

    @property
    def toast_level(self) -> str:
        """获取Toast提示级别"""
        return self._config.get("toast_level", "INFO")

    @toast_level.setter
    def toast_level(self, value: str):
        """设置Toast提示级别"""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR"]
        if value.upper() in valid_levels:
            self._config["toast_level"] = value.upper()
            self._save_config()
            self.logger.info(f"Toast提示级别已设置为: {value.upper()}")
        else:
            self.logger.warning(f"无效的Toast级别: {value}，已忽略")

    # ==================== 图像预览配置 ====================

    @property
    def image_zoom_max(self) -> float:
        """获取最大缩放倍数"""
        return self._config.get("image_zoom_max", 3.0)

    @image_zoom_max.setter
    def image_zoom_max(self, value: float):
        """设置最大缩放倍数"""
        # 限制范围：1.0 - 20.0
        if 1.0 <= value <= 20.0:
            self._config["image_zoom_max"] = value
            self._save_config()
            self.logger.info(f"最大缩放倍数已设置为: {value}")
        else:
            self.logger.warning(f"无效的最大缩放倍数: {value}，应在 1.0-20.0 之间")

    @property
    def image_zoom_min(self) -> float:
        """获取最小缩放倍数"""
        return self._config.get("image_zoom_min", 0.1)

    @image_zoom_min.setter
    def image_zoom_min(self, value: float):
        """设置最小缩放倍数"""
        # 限制范围：0.01 - 1.0
        if 0.01 <= value <= 1.0:
            self._config["image_zoom_min"] = value
            self._save_config()
            self.logger.info(f"最小缩放倍数已设置为: {value}")
        else:
            self.logger.warning(f"无效的最小缩放倍数: {value}，应在 0.01-1.0 之间")

    @property
    def global_zoom_enabled(self) -> bool:
        """获取是否启用全局缩放（将缩放倍数应用到所有图片）"""
        return self._config.get("global_zoom_enabled", False)

    @global_zoom_enabled.setter
    def global_zoom_enabled(self, value: bool):
        """设置是否启用全局缩放（将缩放倍数应用到所有图片）"""
        self._config["global_zoom_enabled"] = value
        self._save_config()
        self.logger.info(f"全局缩放功能已{'启用' if value else '禁用'}")

    @property
    def last_zoom_factor(self) -> float:
        """获取最后使用的缩放倍数（自动记录）"""
        return self._config.get("last_zoom_factor", 1.0)

    @last_zoom_factor.setter
    def last_zoom_factor(self, value: float):
        """设置最后使用的缩放倍数（自动记录，无需手动调用）"""
        self._config["last_zoom_factor"] = value
        self._save_config()

    # ==================== 缓存预热配置（优化8） ====================

    @property
    def cache_warmup_enabled(self) -> bool:
        """获取缓存预热开关（仅网络路径有效）"""
        return self._config.get("cache_warmup_enabled", True)

    @cache_warmup_enabled.setter
    def cache_warmup_enabled(self, value: bool):
        """设置缓存预热开关"""
        self._config["cache_warmup_enabled"] = value
        self._save_config()
        self.logger.info(f"缓存预热功能已{'启用' if value else '禁用'}")

    @property
    def cache_warmup_count(self) -> int:
        """获取预热图片数量（范围：10-500）"""
        return self._config.get("cache_warmup_count", 100)

    @cache_warmup_count.setter
    def cache_warmup_count(self, value: int):
        """设置预热图片数量"""
        # 限制范围：10 - 500
        if 10 <= value <= 500:
            self._config["cache_warmup_count"] = value
            self._save_config()
            self.logger.info(f"预热图片数量已设置为: {value}")
        else:
            self.logger.warning(f"无效的预热图片数量: {value}，应在 10-500 之间")

    # ==================== 循环翻页配置 ====================

    @property
    def local_loop_enabled(self) -> bool:
        """获取本地路径循环翻页开关"""
        return self._config.get("local_loop_enabled", True)

    @local_loop_enabled.setter
    def local_loop_enabled(self, value: bool):
        """设置本地路径循环翻页开关"""
        self._config["local_loop_enabled"] = value
        self._save_config()
        self.logger.info(f"本地路径循环翻页已{'启用' if value else '禁用'}")

    @property
    def network_loop_enabled(self) -> bool:
        """获取网络路径循环翻页开关"""
        return self._config.get("network_loop_enabled", False)

    @network_loop_enabled.setter
    def network_loop_enabled(self, value: bool):
        """设置网络路径循环翻页开关"""
        self._config["network_loop_enabled"] = value
        self._save_config()
        self.logger.info(f"网络路径循环翻页已{'启用' if value else '禁用'}")

    # ==================== 其他方法 ====================

    def reset_tutorial(self):
        """重置教程状态（用于"重新开始教程"功能）"""
        self._config["tutorial_completed"] = False
        self._config["tutorial_skipped"] = False
        self._save_config()
        self.logger.info("教程状态已重置")

    def get_all_config(self) -> Dict[str, Any]:
        """获取所有配置"""
        return self._config.copy()

    def reload_config(self):
        """重新加载配置文件（用于确保配置同步）"""
        try:
            if self._config_file.exists():
                with open(self._config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    # 合并默认配置
                    default_config = self._get_default_config()
                    for key, value in default_config.items():
                        if key not in config:
                            config[key] = value
                    self._config = config
                    self.logger.info("配置已重新加载")
                    return True
        except Exception as e:
            self.logger.error(f"重新加载配置失败: {e}")
            return False

    def save_config(self):
        """公开的保存配置方法"""
        self._save_config()

    def __repr__(self):
        return f"AppConfig(theme={self.theme}, tutorial_completed={self.tutorial_completed}, tutorial_skipped={self.tutorial_skipped})"


def get_app_config() -> AppConfig:
    """获取应用配置单例

    修复问题1：直接调用AppConfig()即可获得单例
    单例逻辑在类的__new__方法中实现，无需模块级变量
    """
    return AppConfig()
