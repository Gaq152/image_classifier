"""
文件操作工具函数模块

提供文件操作相关的工具函数，包括MD5计算、重试机制、文件夹名称规范化等。
"""

import hashlib
import time
import unicodedata
import logging
from .exceptions import FileOperationError


def calculate_md5(file_path, chunk_size=8192):
    """
    计算文件的MD5值，使用增量哈希
    
    Args:
        file_path: 文件路径
        chunk_size: 读取块大小
        
    Returns:
        str: MD5哈希值
        
    Raises:
        FileOperationError: 文件读取错误
    """
    try:
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(chunk_size), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except (OSError, IOError) as e:
        raise FileOperationError(f"计算MD5失败: {file_path} - {e}")


def retry_file_operation(operation, max_retries=3, delay=1):
    """
    重试文件操作
    
    Args:
        operation: 要执行的操作函数
        max_retries: 最大重试次数
        delay: 重试间隔（秒）
        
    Returns:
        操作结果，失败返回None
    """
    logger = logging.getLogger(__name__)
    
    for attempt in range(max_retries):
        try:
            return operation()
        except Exception as e:
            logger.warning(f"文件操作失败 (尝试 {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(delay)
            else:
                logger.error(f"文件操作最终失败: {e}")
                raise FileOperationError(f"重试{max_retries}次后仍然失败: {e}")
    return None


def normalize_folder_name(name):
    """
    规范化文件夹名称，确保编码一致性
    
    Args:
        name: 原始文件夹名称
        
    Returns:
        str: 规范化后的文件夹名称
    """
    if not name:
        return name
        
    # 移除首尾空格
    name = name.strip()
    # 转换为 NFKC 标准形式(兼容等价分解后再标准等价合成)
    name = unicodedata.normalize('NFKC', name)
    # 移除不可见字符
    name = ''.join(char for char in name if not unicodedata.category(char).startswith('C'))
    return name


def is_network_path(path):
    """
    检查路径是否为网络路径
    
    Args:
        path: 文件路径
        
    Returns:
        bool: 是否为网络路径
    """
    path_str = str(path)
    return path_str.startswith(('\\\\', '//', 'smb://', 'ftp://', 'http://', 'https://'))


def validate_file_operation_preconditions(src_path, dst_path=None):
    """
    验证文件操作的前置条件
    
    Args:
        src_path: 源文件路径
        dst_path: 目标文件路径（可选）
        
    Raises:
        FileOperationError: 前置条件不满足时抛出异常
    """
    from pathlib import Path
    
    src = Path(src_path)
    if not src.exists():
        raise FileOperationError(f"源文件不存在: {src_path}")
    
    if not src.is_file():
        raise FileOperationError(f"源路径不是文件: {src_path}")
    
    if dst_path:
        dst = Path(dst_path)
        if dst.exists() and dst.is_dir():
            raise FileOperationError(f"目标路径是目录，不能覆盖: {dst_path}")
        
        # 检查目标目录是否存在，不存在则尝试创建
        dst.parent.mkdir(parents=True, exist_ok=True)
