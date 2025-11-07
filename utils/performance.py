"""
性能监控模块

提供性能监控装饰器和性能统计管理功能。
"""

import time
import logging
import threading
from functools import wraps
from collections import defaultdict


def performance_monitor(func):
    """
    性能监控装饰器
    
    自动记录函数执行时间，并输出到日志。
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        duration = (time.time() - start_time) * 1000
        logging.debug(f"[Performance] {func.__name__} executed in {duration:.2f}ms")
        return result
    return wrapper


class PerformanceMonitor:
    """性能监控管理器 - 统一管理性能监控和日志"""
    
    def __init__(self, enabled=True):
        self.enabled = enabled
        self.timers = {}
        self.performance_stats = defaultdict(lambda: {
            'count': 0,
            'total_time': 0,
            'avg_time': 0,
            'min_time': float('inf'),
            'max_time': 0
        })
        self.logger = logging.getLogger(__name__)
        self._lock = threading.Lock()
        
    def start_timer(self, operation_name):
        """开始计时"""
        if self.enabled:
            with self._lock:
                self.timers[operation_name] = time.time()
            
    def end_timer(self, operation_name, **kwargs):
        """结束计时并记录"""
        if not self.enabled:
            return
            
        with self._lock:
            if operation_name not in self.timers:
                return
                
            elapsed = (time.time() - self.timers[operation_name]) * 1000
            del self.timers[operation_name]
            
            # 记录性能统计
            stats = self.performance_stats[operation_name]
            stats['count'] += 1
            stats['total_time'] += elapsed
            stats['avg_time'] = stats['total_time'] / stats['count']
            stats['min_time'] = min(stats['min_time'], elapsed)
            stats['max_time'] = max(stats['max_time'], elapsed)
            
            # 记录详细日志
            extra_info = ' '.join([f"{k}:{v}" for k, v in kwargs.items()])
            self.logger.debug(f"[{operation_name}] 耗时:{elapsed:.1f}ms 平均:{stats['avg_time']:.1f}ms {extra_info}")
        
    def get_performance_summary(self):
        """获取性能摘要"""
        with self._lock:
            return dict(self.performance_stats)
        
    def log_system_status(self, **status_info):
        """记录系统状态"""
        if self.enabled:
            status_str = ' '.join([f"{k}:{v}" for k, v in status_info.items()])
            self.logger.debug(f"[System] {status_str}")
            
    def reset_stats(self):
        """重置统计数据"""
        with self._lock:
            self.performance_stats.clear()
            self.timers.clear()
