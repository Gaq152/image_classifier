"""
统一的路径管理模块

集中管理所有应用程序使用的目录路径，确保一致性和可维护性。
"""

from pathlib import Path

from product_channel import get_product_info


def get_app_data_dir() -> Path:
    r"""获取应用程序数据目录

    Returns:
        Path: C:\Users\<username>\image_classifier
    """
    return Path.home() / "image_classifier"


def get_cache_dir() -> Path:
    r"""获取SMB缓存目录

    Returns:
        Path: C:\Users\<username>\image_classifier\cache
    """
    cache_dir = get_app_data_dir() / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def get_logs_dir() -> Path:
    r"""获取日志目录

    Returns:
        Path: C:\Users\<username>\image_classifier\logs
    """
    logs_dir = get_app_data_dir() / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir


def get_update_dir() -> Path:
    r"""获取当前产品通道的更新目录（不自动创建）。

    Returns:
        标准版为 ``...\update``，AI 版为 ``...\update\ai``。
    """
    subdirectory = str(get_product_info()["update_subdirectory"])
    return get_app_data_dir().joinpath(*subdirectory.split("/"))


def get_ai_cache_dir() -> Path:
    """获取本地 AI 特征缓存目录。"""
    cache_dir = get_app_data_dir() / "ai_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def get_ai_model_dir(model_dir_name: str = "resnet18_embedding_v1") -> Path:
    """获取指定的外置 AI 基础模型包目录。"""
    return get_app_data_dir() / "ai_models" / model_dir_name


def get_config_dir() -> Path:
    r"""获取配置目录

    Returns:
        Path: C:\Users\<username>\image_classifier\config
    """
    config_dir = get_app_data_dir() / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


# 向后兼容：获取旧的隐藏缓存目录路径（用于迁移）
def get_old_cache_dir() -> Path:
    r"""获取旧的隐藏缓存目录路径

    Returns:
        Path: C:\Users\<username>\.image_classifier_cache
    """
    return Path.home() / ".image_classifier_cache"
