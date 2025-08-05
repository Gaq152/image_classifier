"""
自定义异常类模块

提供应用程序特定的异常类，用于统一错误处理机制。
"""


class ImageClassifierError(Exception):
    """应用程序的异常基类"""
    pass


class ConfigError(ImageClassifierError):
    """配置加载/保存错误"""
    pass


class FileOperationError(ImageClassifierError):
    """文件操作（复制/移动/删除）错误"""
    pass


class ImageLoadError(ImageClassifierError):
    """图像加载或解码错误"""
    pass


class DirectoryScanError(ImageClassifierError):
    """目录扫描错误"""
    pass


class SyncError(ImageClassifierError):
    """文件同步错误"""
    pass
