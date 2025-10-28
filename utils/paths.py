"""
统一的路径管理模块

集中管理所有应用程序使用的目录路径，确保一致性和可维护性。
"""

from pathlib import Path


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
    r"""获取更新目录（不自动创建，有更新时才创建）

    Returns:
        Path: C:\Users\<username>\image_classifier\update
    """
    return get_app_data_dir() / "update"


# 向后兼容：获取旧的隐藏缓存目录路径（用于迁移）
def get_old_cache_dir() -> Path:
    r"""获取旧的隐藏缓存目录路径

    Returns:
        Path: C:\Users\<username>\.image_classifier_cache
    """
    return Path.home() / ".image_classifier_cache"
