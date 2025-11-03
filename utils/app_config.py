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


class AppConfig:
    """应用配置管理器"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._config_dir = get_config_dir()  # 使用统一的路径管理
        self._config_file = self._config_dir / "app_config.json"
        self._config = self._load_config()

    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            "theme": "light",  # 主题：light 或 dark
            "tutorial_completed": False,  # 是否完成教程
            "tutorial_skipped": False,  # 是否跳过教程
            "version": "6.3.3",  # 配置文件版本
            # 自动更新相关配置
            "auto_update_enabled": True,  # 自动检查更新开关
            "last_update_check_ts": 0,  # 最后检查更新的时间戳
            "update_endpoint": "https://gitlab.desauto.cn/api/v4/projects/820/packages/generic/image_classifier/latest/manifest.json",  # 更新检查端点
            "update_token": "",  # 更新令牌（可选）
            "pending_update": {},  # 待处理的更新信息
            # 工作目录相关配置
            "last_opened_directory": ""  # 最后打开的图片目录
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
            self.logger.info(f"已保存应用配置: {self._config_file}")
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
            self.logger.info(f"主题已设置为: {value}")
        else:
            self.logger.warning(f"无效的主题值: {value}，应为 'light' 或 'dark'")

    def is_dark_theme(self) -> bool:
        """是否为暗色主题"""
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
        self.logger.info(f"最后打开的目录已设置为: {value}")

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

    def save_config(self):
        """公开的保存配置方法"""
        self._save_config()

    def __repr__(self):
        return f"AppConfig(theme={self.theme}, tutorial_completed={self.tutorial_completed}, tutorial_skipped={self.tutorial_skipped})"


# 全局单例
_app_config_instance = None


def get_app_config() -> AppConfig:
    """获取应用配置单例"""
    global _app_config_instance
    if _app_config_instance is None:
        _app_config_instance = AppConfig()
    return _app_config_instance
