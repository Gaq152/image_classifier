"""
性能监控模块

提供轻量级性能监控装饰器，用于记录函数执行时间。
项目采用分散式性能管理策略，各模块自行实现性能控制逻辑。
"""

import time
import logging
from functools import wraps


def performance_monitor(func):
    """
    性能监控装饰器

    自动记录函数执行时间，并输出到日志。
    项目采用轻量级装饰器模式，各模块自行管理性能控制。
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        duration = (time.time() - start_time) * 1000
        logging.debug(f"[Performance] {func.__name__} executed in {duration:.2f}ms")
        return result
    return wrapper
