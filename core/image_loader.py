"""
图像加载器模块

提供高性能的图像加载功能，支持多线程、缓存、网络路径优化等。
"""

import os
import sys
import cv2
import logging
import hashlib
import time
import threading
import shutil
import struct
from pathlib import Path
from queue import Queue
from concurrent.futures import ThreadPoolExecutor
from PyQt6.QtCore import QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QPixmap, QImage

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

import psutil

from ..utils.exceptions import ImageLoadError
from ..utils.file_operations import is_network_path
from ..utils.performance import performance_monitor
from ..utils.paths import get_cache_dir, get_old_cache_dir
from ..utils.cache_meta import SimpleCacheMeta
from ..utils.cache_index import CacheIndex


class HighPerformanceImageLoader(QThread):
    """超高性能图像加载器，专门针对大图片和网络路径优化"""
    image_loaded = pyqtSignal(str, object)  # 发送原始图片数据（numpy array 或 PIL Image）
    thumbnail_loaded = pyqtSignal(str, object)  # 发送原始缩略图数据
    loading_progress = pyqtSignal(str)
    # Task 3.3：已删除 cache_status 信号，监控UI已移除
    
    def __init__(self, cache_size=30):
        super().__init__()
        self.queue = Queue()
        self.preload_queue = Queue()
        self.cache = {}  # 全尺寸图片缓存
        self.thumbnail_cache = {}  # 缩略图缓存（快速预览）
        self.cache_size = cache_size
        self.thumbnail_cache_size = 500  # 大幅增加缩略图缓存（占用内存很少）
        self.running = True
        self.current_task = None
        self.access_counter = 0

        # 缩略图设置（用于快速预览）
        self.thumbnail_size = (400, 300)  # 缩略图尺寸

        # SMB/NAS 专项优化配置
        self.smb_optimization = {
            'enable_local_cache': True,  # 启用本地临时缓存
            'cache_dir': get_cache_dir(),  # 本地缓存目录: C:\Users\<username>\image_classifier\cache
            'cache_max_size_gb': 5,  # 本地缓存最大5GB
            'batch_read_size': 32 * 1024,  # 32KB批量读取
            'connection_pool': {},  # SMB连接池
            'read_ahead_mb': 2,  # 预读2MB数据
            'use_memory_mapping': True,  # 使用内存映射
        }

        # Task 1.2 P1修复：使用独立的SimpleCacheMeta模块管理元信息
        self.cache_meta = None  # 将在_init_smb_optimization中初始化

        # Task 2.1收尾P2：使用CacheIndex管理缓存文件元数据
        self.cache_index = None  # 将在_init_smb_optimization中初始化

        # 路径感知配置（Task 1.1）
        self.current_working_path = None  # 当前工作路径
        self.is_network_working_path = False  # 当前工作路径是否为网络路径
        self.active_network_sources = 0  # 活跃的网络加载任务数
        self.last_network_activity_ts = 0  # 最后一次网络活动时间
        self._network_counter_lock = threading.Lock()  # 网络计数器线程锁

        # Task 3.1：7天兜底扫描的时间戳记录
        self.last_reconcile_ts = 0  # 最后一次全盘扫描时间戳
        self.reconcile_interval = 7 * 24 * 3600  # 7天（秒）

        # Task 2.1：缩放策略配置（文件大小 + 分辨率驱动）
        self.scaling_profiles = {
            'S0': {  # 原图策略
                'name': '原图',
                'file_size_min_mb': 0,
                'file_size_max_mb': 1,  # <1MB小图片保持原图
                'max_dim': None,  # 不限制尺寸
                'is_network': False,  # 本地小文件优先原图
                'target_format': 'original',  # 保持原格式
            },
            'S1': {  # 中等缩放策略
                'name': '中等缩放',
                'file_size_min_mb': 1,
                'file_size_max_mb': 20,  # 1-20MB中等文件
                'max_dim': 2000,  # 最大边≤2000px
                'is_network': None,  # 不限制网络/本地
                'target_format': 'original',  # 保持原格式
            },
            'S2': {  # 激进缩放策略
                'name': '激进缩放',
                'file_size_min_mb': 20,
                'file_size_max_mb': float('inf'),  # >20MB大文件
                'max_dim': 1600,  # 最大边≤1600px
                'is_network': None,  # 不限制网络/本地
                'target_format': 'jpeg',  # 转换为JPEG节省空间
            }
        }

        # 初始化日志器（需要在_init_smb_optimization之前）
        self.logger = logging.getLogger(__name__)

        # 初始化SMB优化
        self._init_smb_optimization()

        # 多线程优化 - 自适应线程池配置
        self.thread_pool = self._create_adaptive_thread_pool()

        # 优化4：创建高优先级主图专用线程池
        self.priority_pool = None  # 默认为None，表示未启用双线程池模式
        self.use_dual_thread_pools = False  # 标志是否启用双线程池模式
        try:
            self.priority_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ImageLoaderPriority")
            self.use_dual_thread_pools = True
            self.logger.info("[优化4-双线程池] 成功创建主图专用线程池 (2个工作线程)")
        except Exception as e:
            self.logger.warning(f"[优化4-双线程池] 创建主图线程池失败，回退到单线程池模式: {e}")
            self.priority_pool = None
            self.use_dual_thread_pools = False

        # 初始化图片加载器 - 网络路径优化策略
        self.use_opencv = True  # 网络路径下OpenCV性能更好

        # 动态内存管理
        self.max_cache_memory = self._get_optimal_cache_size()
        self.current_cache_memory = 0
        self.cache_hit_count = 0
        self.cache_miss_count = 0

        # Task 2.3：缩放缓存命中率统计（线程安全）
        self.scaled_cache_hit_count = 0  # 缩放缓存命中计数
        self.scaled_cache_miss_count = 0  # 缩放缓存未命中计数
        self._scaled_cache_lock = threading.Lock()  # 缩放缓存计数器线程锁

        # 优化6：细粒度缓存命中率统计（全局累计，永不归零）
        self.memory_hits = 0      # 内存缓存命中次数
        self.disk_hits = 0        # 磁盘缓存命中次数
        self.network_miss = 0     # 网络加载次数（缓存未命中）
        self._stats_lock = threading.Lock()  # 统计计数器线程锁

        # 性能监控
        self.load_times = []  # 加载时间记录
        self.concurrent_loads = 0  # 当前并发加载数（全局计数）
        self.concurrent_lock = threading.Lock()  # 并发计数器线程锁

        # 优化4：双线程池统计字段（仅用于诊断，不影响调度逻辑）
        self.priority_loads = 0  # 主图线程池当前任务数
        self.background_loads = 0  # 预加载线程池当前任务数

        # 紧急修复：预加载任务去重和限流（阶段三紧急修复）
        self.pending_preload_jobs = set()  # 记录已提交的预加载任务路径
        self.preload_jobs_lock = threading.Lock()  # 预加载任务集合线程锁

        # 资源清理定时器 - 防止内存泄漏（Task 1.1：按需启动，Task 1.3：自适应周期）
        self.cleanup_timer = QTimer()
        self.cleanup_timer.timeout.connect(self._periodic_resource_cleanup)
        # Task 1.3：设置初始默认周期（30秒），实际周期将根据占用率动态调整
        self.cleanup_timer.setInterval(30000)  # 30秒默认值
        # 不自动启动，等待网络活动触发（本地路径不需要定时器）
    
    def _init_smb_optimization(self):
        """初始化SMB专项优化"""
        try:
            # 创建本地缓存目录
            if self.smb_optimization['enable_local_cache']:
                cache_dir = self.smb_optimization['cache_dir']
                cache_dir.mkdir(parents=True, exist_ok=True)
                self.logger.debug(f"[SMB优化] 本地缓存目录: {cache_dir}")

                # 迁移旧的隐藏缓存目录数据
                self._migrate_old_cache()

                # 优化9：检查缓存健康状态，异常时清空重建
                # 修复BUG：只有在缓存目录有内容时才检查健康状态
                cache_files = list(cache_dir.glob('*'))
                if len(cache_files) > 0:
                    need_rebuild = self._check_cache_health(cache_dir)
                    if need_rebuild:
                        self._rebuild_cache_from_scratch(cache_dir)
                else:
                    self.logger.debug("[优化9-健康检查] 缓存目录为空，跳过健康检查")

                # Task 1.2 P1修复：使用SimpleCacheMeta模块
                self.cache_meta = SimpleCacheMeta(cache_dir)

                # Task 2.1收尾P2：初始化CacheIndex
                self.cache_index = CacheIndex(cache_dir)

                summary = self.cache_meta.get_summary()
                if summary['total_files'] > 0:
                    self.logger.info(f"[SMB优化] 加载元信息成功: {summary['total_files']}个文件, {summary['total_gb']:.2f}GB")

                    # 阶段1修复-问题5: 检查元信息是否超过7天未更新
                    days_since_update = (time.time() - summary['last_update']) / (24 * 3600)
                    if days_since_update > 7:
                        self.logger.info(f"[SMB优化] 元信息已{days_since_update:.1f}天未更新，执行兜底校准扫描")
                        # 强制执行一次完整扫描以校准元信息（Task 3.1：会更新last_reconcile_ts）
                        self._force_reconcile_cache()
                    else:
                        # Task 3.1：元信息在7天内，设置last_reconcile_ts为元信息的最后更新时间
                        self.last_reconcile_ts = summary['last_update']
                else:
                    # Task 3.1修复：缓存为空时，设置last_reconcile_ts为当前时间
                    # 这样后续7天扫描机制才能正常工作
                    self.last_reconcile_ts = time.time()
                    self.logger.debug("[SMB优化] 元信息文件已创建，当前无缓存数据，初始化7天扫描时间戳")

                # 清理过期缓存
                self._cleanup_local_cache()

            self.logger.debug("[SMB优化] SMB/NAS专项优化已启用")

        except Exception as e:
            self.logger.error(f"[SMB优化] 初始化失败: {e}")
            self.smb_optimization['enable_local_cache'] = False

    def _migrate_old_cache(self):
        """迁移旧的隐藏缓存目录数据到新位置"""
        try:
            old_cache_dir = get_old_cache_dir()
            new_cache_dir = get_cache_dir()

            # 如果旧缓存目录存在且新目录为空，则迁移
            if old_cache_dir.exists() and old_cache_dir.is_dir():
                # 检查新目录是否已有缓存文件
                new_cache_files = list(new_cache_dir.rglob('*'))
                if len(new_cache_files) <= 1:  # 只有目录本身
                    self.logger.debug(f"[SMB缓存迁移] 发现旧缓存目录，开始迁移...")

                    migrated_count = 0
                    for old_file in old_cache_dir.rglob('*'):
                        if old_file.is_file():
                            try:
                                # 保持相对路径结构
                                rel_path = old_file.relative_to(old_cache_dir)
                                new_file = new_cache_dir / rel_path
                                new_file.parent.mkdir(parents=True, exist_ok=True)
                                shutil.copy2(old_file, new_file)
                                migrated_count += 1
                            except Exception as e:
                                self.logger.debug(f"[SMB缓存迁移] 迁移文件失败 {old_file.name}: {e}")

                    if migrated_count > 0:
                        self.logger.debug(f"[SMB缓存迁移] 成功迁移 {migrated_count} 个缓存文件")
                        # 迁移成功后删除旧目录
                        try:
                            shutil.rmtree(old_cache_dir)
                            self.logger.debug(f"[SMB缓存迁移] 已删除旧缓存目录")
                        except Exception as e:
                            self.logger.warning(f"[SMB缓存迁移] 删除旧目录失败: {e}")
                else:
                    self.logger.debug("[SMB缓存迁移] 新缓存目录已有数据，跳过迁移")
        except Exception as e:
            self.logger.debug(f"[SMB缓存迁移] 迁移过程出错: {e}")

    def _check_cache_health(self, cache_dir):
        """检查缓存健康状态（优化9：元数据缺失/损坏时重建）

        检测以下异常情况：
        1. cache_meta.bin 不存在或无法解析
        2. cache_scaling_index.jsonl 不存在或损坏
        3. 缓存目录存在非规范文件（无 _S? 后缀的旧缓存）

        Args:
            cache_dir: 缓存目录路径（Path对象）

        Returns:
            bool: True表示需要重建缓存，False表示健康
        """
        try:
            meta_file = cache_dir / 'cache_meta.bin'
            index_file = cache_dir / 'cache_scaling_index.jsonl'

            # 检查1：cache_meta.bin 存在性和可解析性
            if not meta_file.exists():
                self.logger.warning(f"[优化9-健康检查] cache_meta.bin 不存在，需要重建缓存")
                return True

            # 尝试解析 cache_meta.bin
            try:
                with open(meta_file, 'rb') as f:
                    # SimpleCacheMeta 格式：魔数(4B) + 版本(2B) + 其他(42B) = 48B
                    header = f.read(48)
                    if len(header) < 48:
                        self.logger.warning(f"[优化9-健康检查] cache_meta.bin 文件不完整，需要重建缓存")
                        return True

                    # 解析魔数和版本号
                    magic = header[0:4]
                    version = struct.unpack('<H', header[4:6])[0]  # 小端序uint16

                    # 检查魔数
                    if magic != b'CACH':
                        self.logger.warning(f"[优化9-健康检查] cache_meta.bin 魔数错误，需要重建缓存")
                        return True

                    # 检查版本（当前版本是1）
                    if version != 1:
                        self.logger.warning(f"[优化9-健康检查] cache_meta.bin 版本不匹配(v{version})，需要重建缓存")
                        return True

            except Exception as e:
                self.logger.warning(f"[优化9-健康检查] cache_meta.bin 解析失败: {e}，需要重建缓存")
                return True

            # 检查2：cache_scaling_index.jsonl 存在性
            if not index_file.exists():
                self.logger.warning(f"[优化9-健康检查] cache_scaling_index.jsonl 不存在，需要重建缓存")
                return True

            # 尝试读取 index 文件的第一行验证格式
            try:
                with open(index_file, 'r', encoding='utf-8') as f:
                    first_line = f.readline().strip()
                    if first_line:
                        import json
                        json.loads(first_line)  # 验证JSON格式
            except Exception as e:
                self.logger.warning(f"[优化9-健康检查] cache_scaling_index.jsonl 格式错误: {e}，需要重建缓存")
                return True

            # 检查3：是否存在非规范缓存文件（旧格式：无 _S? 后缀）
            has_legacy_files = False
            for cache_file in cache_dir.iterdir():
                if cache_file.is_file():
                    # 跳过元数据文件
                    if cache_file.name in ['cache_meta.bin', 'cache_scaling_index.jsonl']:
                        continue
                    if cache_file.suffix in ['.tmp', '.bak']:
                        continue

                    # 检查文件名是否符合新格式：<hash>_S<n>.<ext>
                    stem = cache_file.stem
                    if '_S' not in stem:
                        # 没有策略后缀，是旧格式文件
                        has_legacy_files = True
                        self.logger.debug(f"[优化9-健康检查] 发现旧格式缓存文件: {cache_file.name}")
                        break  # 发现一个即可

            if has_legacy_files:
                self.logger.warning(f"[优化9-健康检查] 存在旧格式缓存文件（无_S?后缀），需要重建缓存")
                return True

            # 所有检查通过
            self.logger.debug("[优化9-健康检查] 缓存健康状态良好")
            return False

        except Exception as e:
            self.logger.warning(f"[优化9-健康检查] 检查过程出错: {e}，为安全起见重建缓存")
            return True

    def _rebuild_cache_from_scratch(self, cache_dir):
        """清空缓存目录并重建（优化9：元数据缺失/损坏时的恢复机制）

        执行步骤：
        1. 记录当前缓存大小（如果可获取）
        2. 删除缓存目录中的所有文件
        3. 重新创建空目录
        4. 初始化空的元数据文件

        Args:
            cache_dir: 缓存目录路径（Path对象）
        """
        try:
            self.logger.warning(f"[优化9-缓存重建] 检测到元数据缺失/损坏，开始清空缓存目录...")

            # 1. 统计当前缓存大小（如果可能）
            total_size = 0
            file_count = 0
            try:
                for cache_file in cache_dir.rglob('*'):
                    if cache_file.is_file():
                        total_size += cache_file.stat().st_size
                        file_count += 1
            except:
                pass

            if file_count > 0:
                total_gb = total_size / (1024**3)
                self.logger.info(f"[优化9-缓存重建] 将清空 {file_count} 个缓存文件 ({total_gb:.2f}GB)")

            # 2. 删除整个缓存目录
            try:
                shutil.rmtree(cache_dir)
                self.logger.info(f"[优化9-缓存重建] 缓存目录已删除")
            except Exception as e:
                self.logger.warning(f"[优化9-缓存重建] 删除缓存目录失败: {e}，尝试逐个删除文件")
                # 备用方案：逐个删除文件
                for cache_file in list(cache_dir.rglob('*')):
                    try:
                        if cache_file.is_file():
                            cache_file.unlink()
                    except:
                        pass

            # 3. 重新创建空目录
            cache_dir.mkdir(parents=True, exist_ok=True)
            self.logger.info(f"[优化9-缓存重建] 缓存目录已重建: {cache_dir}")

            # 4. 更新 last_reconcile_ts
            self.last_reconcile_ts = time.time()

            self.logger.warning(f"[优化9-缓存重建] 完成！首次加载图片时将重新建立缓存，可能较慢")

        except Exception as e:
            self.logger.error(f"[优化9-缓存重建] 重建失败: {e}")
            # 确保目录至少存在
            try:
                cache_dir.mkdir(parents=True, exist_ok=True)
            except:
                pass


    def _force_reconcile_cache(self):
        """强制校准缓存元信息（优化5：仅容量控制和索引重建）

        执行全量扫描并更新元信息，用于处理：
        - 容量统计和索引重建
        - 外部手动删除/添加的缓存文件
        - 元信息与实际磁盘不一致的情况

        优化5改动：
        - 不再校验源文件是否存在/修改（完全信任缓存）
        - 不再7天定期触发（仅容量超过90%时触发）
        - 仅扫描缓存目录，重建CacheIndex和CacheMeta

        问题6修复：使用批量更新模式，避免扫描期间的add_entry/remove_entry被覆盖
        Task 3.4：同步验证和修复CacheIndex，确保索引与实际文件一致
        """
        try:
            cache_dir = self.smb_optimization['cache_dir']
            if not cache_dir.exists():
                self.logger.debug("[缓存校准] 缓存目录不存在，无需校准")
                return

            self.logger.info("[缓存校准] 开始全量扫描校准...")
            start_time = time.time()

            # 阶段1修复-问题6: 进入批量更新模式
            self.cache_meta.begin_bulk_update()

            # Task 3.4：准备CacheIndex验证数据
            scanned_cache_files = {}  # {path_hash: (cache_file, strategy_id, format)}
            meta_file = self.cache_meta.meta_path
            index_file = cache_dir / 'cache_scaling_index.jsonl'

            try:
                total_size = 0
                file_count = 0

                for cache_file in cache_dir.rglob('*'):
                    # Task 2.1收尾P3：跳过元信息文件、CacheIndex文件和临时文件
                    if cache_file == meta_file or cache_file == index_file or cache_file.name.endswith('.tmp') or cache_file.name.endswith('.bak'):
                        continue

                    if cache_file.is_file():
                        try:
                            size = cache_file.stat().st_size
                            total_size += size
                            file_count += 1

                            # Task 3.4：解析缓存文件名，提取path_hash和strategy_id
                            filename = cache_file.stem  # 例如：a3f2d8b9_S1
                            if '_' in filename:
                                path_hash = filename.split('_')[0]
                                # 提取策略ID（例如S1, S2）
                                strategy_id = None
                                for part in filename.split('_'):
                                    if part in ['S0', 'S1', 'S2']:
                                        strategy_id = part
                                        break
                            else:
                                path_hash = filename
                                strategy_id = 'S0'  # 旧格式默认S0

                            # 推断格式
                            ext = cache_file.suffix.lower()
                            if ext in ['.jpg', '.jpeg']:
                                fmt = 'jpeg'
                            elif ext == '.png':
                                fmt = 'png'
                            elif ext == '.webp':
                                fmt = 'webp'
                            else:
                                fmt = 'jpeg'

                            scanned_cache_files[path_hash] = (cache_file, strategy_id, fmt)

                        except:
                            continue

                # 阶段1修复-问题6: 提交批量更新，合并扫描结果和增量操作
                self.cache_meta.commit_bulk_update(file_count, total_size)

                # Task 3.4：同步CacheIndex
                if self.cache_index is not None:
                    self._sync_cache_index_with_files(scanned_cache_files)

                # Task 3.1：更新最后扫描时间戳
                self.last_reconcile_ts = time.time()

                elapsed = (time.time() - start_time) * 1000
                total_gb = total_size / (1024**3)
                self.logger.info(f"[缓存校准] 扫描完成: {file_count}个文件, {total_gb:.2f}GB, 耗时{elapsed:.1f}ms, "
                               f"索引已同步, 下次扫描时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.last_reconcile_ts + self.reconcile_interval))}")

            except Exception as scan_error:
                # 扫描失败时中止批量更新
                self.cache_meta.abort_bulk_update()
                raise scan_error

        except Exception as e:
            self.logger.warning(f"[缓存校准] 校准失败: {e}")

    def _sync_cache_index_with_files(self, scanned_files):
        """同步CacheIndex与实际文件（Task 3.4）

        Args:
            scanned_files: 扫描到的缓存文件字典 {path_hash: (cache_file, strategy_id, format)}
        """
        try:
            self.logger.info("[Task3.4-索引同步] 开始同步CacheIndex...")

            # 获取当前索引中的所有记录
            index_stats = self.cache_index.get_statistics()
            index_entries_count = index_stats['total_entries']

            # 1. 删除索引中不存在文件的记录
            # 修复死锁问题：先收集要删除的path_hash，再释放锁后调用remove_entry
            removed_count = 0
            path_hashes_to_remove = []
            with self.cache_index._lock:
                for path_hash in list(self.cache_index._index.keys()):
                    if path_hash not in scanned_files:
                        path_hashes_to_remove.append(path_hash)

            # 释放锁后再调用remove_entry，避免锁嵌套死锁
            for path_hash in path_hashes_to_remove:
                self.cache_index.remove_entry(path_hash)
                removed_count += 1

            # 2. 为缺失索引的文件添加记录
            added_count = 0
            for path_hash, (cache_file, strategy_id, fmt) in scanned_files.items():
                if path_hash not in self.cache_index._index:
                    try:
                        # 读取文件大小
                        cache_size = cache_file.stat().st_size

                        # 尝试从文件推断原始尺寸（如果无法推断，使用0）
                        # 注意：这里无法获取原始路径和精确尺寸，只能填充基本信息
                        self.cache_index.add_entry(
                            path_hash=path_hash,
                            original_path=f"unknown_{path_hash}",  # 原始路径未知
                            strategy_id=strategy_id or 'S1',
                            scale_ratio=1.0,  # 无法精确推断
                            target_format=fmt,
                            original_width=0,  # 无法获取
                            original_height=0,
                            cached_width=0,
                            cached_height=0,
                            cache_size=cache_size
                        )
                        added_count += 1
                    except Exception as e:
                        self.logger.debug(f"[Task3.4-索引同步] 添加索引失败 {cache_file.name}: {e}")

            # 3. 重建索引文件，清理重复记录
            if removed_count > 0 or added_count > 0:
                self.cache_index.rebuild_index()

            self.logger.info(f"[Task3.4-索引同步] 同步完成: "
                           f"原索引{index_entries_count}条, "
                           f"删除{removed_count}条, "
                           f"添加{added_count}条, "
                           f"最终{len(self.cache_index._index)}条")

        except Exception as e:
            self.logger.warning(f"[Task3.4-索引同步] 同步失败: {e}")

    def _cleanup_local_cache(self):
        """清理本地缓存（Task 1.2：使用元信息优化）"""
        try:
            # Task 1.2 P1修复：检查cache_meta是否已初始化
            if self.cache_meta is None:
                self.logger.warning("[SMB缓存] cache_meta未初始化，跳过清理")
                return

            cache_dir = self.smb_optimization['cache_dir']
            if not cache_dir.exists():
                return

            # Task 1.2：先从元信息快速判断是否需要清理（<1ms）
            max_size_gb = self.smb_optimization['cache_max_size_gb']
            max_size_bytes = max_size_gb * (1024**3)

            # 尝试从元信息获取当前大小
            summary = self.cache_meta.get_summary()
            total_size_bytes = summary['total_bytes']
            file_count = summary['total_files']

            # 如果元信息中有数据，使用快速判断
            if total_size_bytes > 0:
                total_size_gb = total_size_bytes / (1024**3)
                self.logger.debug(f"[SMB缓存] 当前大小(元信息): {total_size_gb:.2f}GB ({file_count}个文件), 上限: {max_size_gb}GB")

                # 如果未超限，直接返回，节省扫描时间
                if total_size_bytes <= max_size_bytes:
                    self.logger.debug("[SMB缓存] 未超限，跳过清理")
                    return
            else:
                # 元信息不可用，记录日志并继续完整扫描
                self.logger.debug("[SMB缓存] 元信息不可用，执行完整扫描")

            # 超限或元信息不可用时，执行完整扫描和清理
            self.logger.info(f"[SMB缓存] 开始完整扫描和清理...")

            # 阶段1修复-问题6: 进入批量更新模式
            self.cache_meta.begin_bulk_update()

            try:
                total_size = 0
                cache_files = []
                # Task 1.2 P1修复：使用SimpleCacheMeta的meta_path
                meta_file = self.cache_meta.meta_path

                for cache_file in cache_dir.rglob('*'):
                    # Task 2.1收尾P3：跳过元信息文件和CacheIndex文件
                    if cache_file == meta_file or cache_file.name == 'cache_scaling_index.jsonl':
                        continue

                    if cache_file.is_file():
                        try:
                            size = cache_file.stat().st_size
                            mtime = cache_file.stat().st_mtime
                            total_size += size
                            cache_files.append((cache_file, size, mtime))
                        except:
                            continue

                total_size_gb = total_size / (1024**3)
                self.logger.info(f"[SMB缓存] 扫描完成: {total_size_gb:.2f}GB ({len(cache_files)}个文件)")

                # 如果未超限，直接提交扫描结果
                if total_size_gb <= max_size_gb:
                    # 阶段1修复-问题6: 提交批量更新（未超限，不需要清理）
                    self.cache_meta.commit_bulk_update(len(cache_files), total_size)
                    self.logger.debug("[SMB缓存] 未超限，更新元信息后返回")
                    return

                # 超限时，执行清理
                # 按修改时间排序，删除最旧的
                cache_files.sort(key=lambda x: x[2])  # 按mtime排序

                removed_size = 0
                removed_count = 0
                target_size_bytes = max_size_gb * 0.8 * (1024**3)  # 清理到80%

                # 阶段1修复-问题2: 记录成功删除的文件，避免失败时统计偏差
                successfully_deleted = []

                for cache_file, size, mtime in cache_files:
                    if total_size - removed_size <= target_size_bytes:
                        break
                    try:
                        # Task 2.1收尾P3：删除前查询策略信息，用于回滚策略统计
                        strategy_id = None
                        scale_ratio = None
                        target_format = None

                        # 方法1：从CacheIndex查询策略信息（最准确）
                        if self.cache_index is not None:
                            # 从文件名反推path_hash
                            filename = cache_file.stem  # 例如：a3f2d8b9_S1
                            if '_' in filename:
                                path_hash = filename.split('_')[0]
                            else:
                                path_hash = filename

                            index_entry = self.cache_index.get_entry(path_hash)
                            if index_entry:
                                strategy_id = index_entry.get('strategy_id')
                                scale_ratio = index_entry.get('scale_ratio')
                                target_format = index_entry.get('target_format')
                                self.logger.debug(f"[SMB缓存清理] 从索引查询策略: {cache_file.name} -> {strategy_id}")

                        # 方法2：从文件名解析策略ID（备用方案）
                        if not strategy_id:
                            filename = cache_file.stem  # 例如：a3f2d8b9_S1
                            if '_S' in filename:
                                # 提取策略ID（例如S1, S2）
                                parts = filename.split('_')
                                for part in parts:
                                    if part in ['S0', 'S1', 'S2']:
                                        strategy_id = part
                                        break

                            # 从扩展名推断格式
                            ext = cache_file.suffix.lower()
                            if ext in ['.jpg', '.jpeg']:
                                target_format = 'jpeg'
                            elif ext == '.png':
                                target_format = 'png'
                            elif ext == '.webp':
                                target_format = 'webp'

                            if strategy_id:
                                self.logger.debug(f"[SMB缓存清理] 从文件名解析策略: {cache_file.name} -> {strategy_id}")

                        # 删除文件
                        cache_file.unlink()

                        # 删除成功后，从CacheIndex中移除记录
                        if self.cache_index is not None:
                            filename = cache_file.stem
                            if '_' in filename:
                                path_hash = filename.split('_')[0]
                            else:
                                path_hash = filename
                            self.cache_index.remove_entry(path_hash)

                        # Task 2.1收尾P3：调用remove_entry回滚策略统计（传递完整策略信息）
                        self.cache_meta.remove_entry(
                            size,
                            strategy_id=strategy_id,
                            scale_ratio=scale_ratio,
                            target_format=target_format
                        )

                        # 只有删除成功才记录
                        removed_size += size
                        removed_count += 1
                        successfully_deleted.append((cache_file, size, mtime))

                    except Exception as e:
                        self.logger.debug(f"删除缓存文件失败: {cache_file.name}, {e}")
                        # 删除失败，不计入removed_count，继续尝试下一个文件
                        continue

                # 阶段1修复-问题6: 提交批量更新，合并扫描结果和清理期间的增量操作
                # Task 2.1收尾P3：传递扫描结果（不是剩余结果），因为删除操作已通过remove_entry记录
                # commit_bulk_update会将扫描结果与pending_remove合并得到最终结果
                self.cache_meta.commit_bulk_update(len(cache_files), total_size)

                self.logger.info(f"[SMB缓存] 清理完成，删除{removed_count}个文件，释放 {removed_size / (1024**3):.2f}GB")

                # Task 3.2：清理完成后归零命中率统计
                self.reset_scaled_cache_stats()

            except Exception as cleanup_error:
                # 扫描或清理失败时中止批量更新
                self.cache_meta.abort_bulk_update()
                raise cleanup_error

        except Exception as e:
            self.logger.warning(f"[SMB缓存] 清理失败: {e}")
    
    def _get_local_cache_path(self, image_path, strategy_id=None, target_format=None):
        """获取本地缓存文件路径（Task 2.1收尾：支持策略后缀）

        Args:
            image_path: 原始图片路径
            strategy_id: 策略ID（S0/S1/S2），用于生成带策略后缀的文件名
            target_format: 目标格式（jpeg/png/webp），用于确定扩展名

        Returns:
            Path: 缓存文件路径，格式为 <hash>_<strategy>.<ext> （如果提供strategy_id）
                  或 <hash>.<ext> （兼容旧版本）
        """
        if not self.smb_optimization['enable_local_cache']:
            return None

        try:
            # 使用文件路径的hash作为缓存文件名
            path_hash = hashlib.md5(str(image_path).encode()).hexdigest()

            # Task 2.1收尾：如果提供了strategy_id，生成带策略后缀的文件名
            if strategy_id:
                # 根据target_format确定扩展名
                if target_format:
                    if target_format == 'jpeg':
                        ext = '.jpg'
                    else:
                        ext = f'.{target_format}'
                else:
                    # 默认使用原始扩展名
                    ext = Path(image_path).suffix.lower()

                cache_filename = f"{path_hash}_{strategy_id}{ext}"
            else:
                # 兼容旧版本：不带策略后缀
                original_ext = Path(image_path).suffix.lower()
                cache_filename = f"{path_hash}{original_ext}"

            cache_dir = self.smb_optimization['cache_dir']
            return cache_dir / cache_filename

        except Exception as e:
            self.logger.debug(f"[SMB缓存] 获取缓存路径失败: {e}")
            return None
    
    def _load_from_local_cache(self, image_path, file_size_mb=None, max_dim=None):
        """从本地缓存加载图片（优化1+2：CacheIndex命中即读，未命中直接返回）

        性能优化: 完全信任缓存索引（优化1+2实施后）
        - 优化1：CacheIndex命中 → 直接加载，不调用exists()检查
        - 优化2：CacheIndex未命中 → 立即返回None，不枚举9种组合
        - 失败处理：文件读取失败时自动清理索引并返回None

        原理：
        1. CacheIndex是缓存文件的唯一来源，未在索引中即视为miss
        2. 失败时清理索引，让下次加载走网络重建缓存
        3. 彻底消除网络stat()调用，命中延迟从~150ms降至~30ms

        Args:
            image_path: 原始图片路径
            file_size_mb: 文件大小（MB），用于策略选择（已废弃，保留兼容）
            max_dim: 最大边长，用于策略选择（已废弃，保留兼容）

        Returns:
            numpy数组或None
        """
        # 优化1+2：CacheIndex命中即读，未命中直接返回None
        if self.cache_index is not None:
            path_hash = hashlib.md5(str(image_path).encode()).hexdigest()
            index_entry = self.cache_index.get_entry(path_hash)

            if index_entry:
                # 优化1：CacheIndex命中后直接读取，不再调用exists()检查
                strategy_id = index_entry.get('strategy_id')
                target_format = index_entry.get('target_format')
                cache_path = self._get_local_cache_path(image_path, strategy_id=strategy_id, target_format=target_format)

                try:
                    # 直接尝试加载，失败即清理索引
                    image_array, width, height = self._load_with_opencv(str(cache_path))
                    if self._is_valid_pixmap(image_array):
                        # 缓存命中，增加计数
                        with self._scaled_cache_lock:
                            self.scaled_cache_hit_count += 1

                        # 优化6：磁盘缓存命中计数
                        with self._stats_lock:
                            self.disk_hits += 1

                        self.logger.debug(f"[优化1-CacheIndex命中] {Path(image_path).name} 策略:{strategy_id}")
                        return image_array

                except Exception as e:
                    # 优化1：文件读取失败，清理索引并视为miss
                    self.logger.warning(f"[优化1-索引失效] {Path(image_path).name} 读取失败: {e}，已移除索引")
                    try:
                        self.cache_index.remove_entry(path_hash)
                    except:
                        pass
                    return None

        # 优化2：CacheIndex未命中，直接返回None，不再枚举9种组合
        self.logger.debug(f"[优化2-索引未命中] {Path(image_path).name}，走网络加载")
        return None
    
    def _save_to_local_cache(self, image_path, image_data, strategy_id='S1', scale_ratio=1.0,
                            target_format='jpeg', original_width=None, original_height=None):
        """保存图片到本地缓存（Task 2.1收尾：支持策略信息传递）

        Args:
            image_path: 原始图片路径
            image_data: 图片数据（numpy数组、bytes或PIL Image）
            strategy_id: 缩放策略ID（S0/S1/S2）
            scale_ratio: 缩放比例
            target_format: 目标格式（jpeg/png/webp/original）
            original_width: 原始图片宽度
            original_height: 原始图片高度
        """
        if not self.smb_optimization['enable_local_cache']:
            return

        # Task 1.2 P1修复：检查cache_meta是否已初始化
        if self.cache_meta is None:
            return

        # 检查PIL是否可用
        if not PIL_AVAILABLE:
            self.logger.debug("[SMB缓存] PIL不可用，无法保存缓存")
            return

        # Task 2.1收尾：传递策略ID和格式信息生成带策略后缀的缓存路径
        cache_path = self._get_local_cache_path(image_path, strategy_id=strategy_id, target_format=target_format)
        if not cache_path:
            return

        try:
            # 优化7：直接覆盖写入，不再检查旧文件
            # 确保缓存目录存在
            cache_path.parent.mkdir(parents=True, exist_ok=True)

            # Task 2.1收尾：根据target_format保存，不再硬编码JPEG
            save_format = target_format.upper() if target_format != 'jpeg' else 'JPEG'
            save_kwargs = {}

            # 根据格式设置参数
            if target_format == 'jpeg':
                save_kwargs = {'quality': 95, 'optimize': True}
            elif target_format == 'png':
                save_kwargs = {'optimize': True, 'compress_level': 6}
            elif target_format == 'webp':
                save_kwargs = {'quality': 95, 'method': 6}

            # 保存图片数据
            if NUMPY_AVAILABLE and isinstance(image_data, np.ndarray):
                # numpy array -> PIL Image -> 按格式保存
                pil_image = Image.fromarray(image_data)
                pil_image.save(cache_path, format=save_format, **save_kwargs)

                # 记录缓存大小
                cache_size_bytes = cache_path.stat().st_size
                cache_size_mb = cache_size_bytes / 1024 / 1024

                # Task 2.1收尾：记录策略信息到日志和元数据
                self.logger.info(f"[SMB缓存] 已缓存: {Path(image_path).name} | "
                               f"策略:{strategy_id} | "
                               f"缩放比:{scale_ratio:.2f} | "
                               f"格式:{target_format} | "
                               f"大小:{cache_size_mb:.2f}MB")

                # 优化7：直接添加新记录，不再检查和删除旧记录
                self.cache_meta.add_entry(
                    cache_size_bytes,
                    strategy_id=strategy_id,
                    scale_ratio=scale_ratio,
                    target_format=target_format,
                    original_width=original_width,
                    original_height=original_height
                )

                # Task 2.1收尾P2：添加到CacheIndex
                if self.cache_index is not None:
                    path_hash = hashlib.md5(str(image_path).encode()).hexdigest()
                    scaled_height, scaled_width = image_data.shape[:2] if isinstance(image_data, np.ndarray) else (original_height, original_width)
                    self.cache_index.add_entry(
                        path_hash=path_hash,
                        original_path=str(image_path),
                        strategy_id=strategy_id,
                        scale_ratio=scale_ratio,
                        target_format=target_format,
                        original_width=original_width,
                        original_height=original_height,
                        cached_width=scaled_width,
                        cached_height=scaled_height,
                        cache_size=cache_size_bytes
                    )

            elif isinstance(image_data, bytes):
                # bytes数据直接写入（已经是编码后的格式）
                with open(cache_path, 'wb') as f:
                    f.write(image_data)
                cache_size_bytes = cache_path.stat().st_size
                cache_size_mb = cache_size_bytes / 1024 / 1024

                # Task 2.1收尾P1修复：bytes分支也记录策略信息
                self.logger.info(f"[SMB缓存] 已缓存: {Path(image_path).name} | "
                               f"策略:{strategy_id} | "
                               f"缩放比:{scale_ratio:.2f} | "
                               f"格式:{target_format} | "
                               f"大小:{cache_size_mb:.2f}MB")

                # 优化7：直接添加新记录，不再检查和删除旧记录
                self.cache_meta.add_entry(
                    cache_size_bytes,
                    strategy_id=strategy_id,
                    scale_ratio=scale_ratio,
                    target_format=target_format,
                    original_width=original_width,
                    original_height=original_height
                )

                # Task 2.1收尾P2：添加到CacheIndex
                if self.cache_index is not None:
                    path_hash = hashlib.md5(str(image_path).encode()).hexdigest()
                    scaled_width = int(original_width * scale_ratio) if original_width else None
                    scaled_height = int(original_height * scale_ratio) if original_height else None
                    self.cache_index.add_entry(
                        path_hash=path_hash,
                        original_path=str(image_path),
                        strategy_id=strategy_id,
                        scale_ratio=scale_ratio,
                        target_format=target_format,
                        original_width=original_width,
                        original_height=original_height,
                        cached_width=scaled_width,
                        cached_height=scaled_height,
                        cache_size=cache_size_bytes
                    )

            elif hasattr(image_data, 'save'):
                # PIL Image或其他格式 - 按照target_format保存
                image_data.save(cache_path, format=save_format, **save_kwargs)
                cache_size_bytes = cache_path.stat().st_size
                cache_size_mb = cache_size_bytes / 1024 / 1024

                # Task 2.1收尾P1修复：PIL Image分支也记录策略信息
                self.logger.info(f"[SMB缓存] 已缓存: {Path(image_path).name} | "
                               f"策略:{strategy_id} | "
                               f"缩放比:{scale_ratio:.2f} | "
                               f"格式:{target_format} | "
                               f"大小:{cache_size_mb:.2f}MB")

                # 优化7：直接添加新记录，不再检查和删除旧记录
                self.cache_meta.add_entry(
                    cache_size_bytes,
                    strategy_id=strategy_id,
                    scale_ratio=scale_ratio,
                    target_format=target_format,
                    original_width=original_width,
                    original_height=original_height
                )

                # Task 2.1收尾P2：添加到CacheIndex
                if self.cache_index is not None:
                    path_hash = hashlib.md5(str(image_path).encode()).hexdigest()
                    # PIL Image尺寸
                    cached_width, cached_height = image_data.size if hasattr(image_data, 'size') else (original_width, original_height)
                    self.cache_index.add_entry(
                        path_hash=path_hash,
                        original_path=str(image_path),
                        strategy_id=strategy_id,
                        scale_ratio=scale_ratio,
                        target_format=target_format,
                        original_width=original_width,
                        original_height=original_height,
                        cached_width=cached_width,
                        cached_height=cached_height,
                        cache_size=cache_size_bytes
                    )

            else:
                self.logger.debug(f"[SMB缓存] 不支持的数据格式: {type(image_data)}")
                return

        except Exception as e:
            self.logger.debug(f"[SMB缓存] 保存失败: {e}")
    
    def _select_scaling_strategy(self, file_size_mb, max_dim, is_network):
        """选择缩放策略（Task 2.1）

        根据文件大小、分辨率和网络环境综合判断使用哪种缩放策略。

        Args:
            file_size_mb: 文件大小（MB）
            max_dim: 图片最大边长（像素）
            is_network: 是否为网络路径

        Returns:
            (strategy_id, strategy_config): 策略ID和配置字典
        """
        try:
            # 遍历策略，按优先级匹配
            for strategy_id in ['S0', 'S1', 'S2']:
                strategy = self.scaling_profiles[strategy_id]

                # 检查文件大小是否在范围内
                if not (strategy['file_size_min_mb'] <= file_size_mb < strategy['file_size_max_mb']):
                    continue

                # 检查网络环境约束
                if strategy['is_network'] is not None:
                    if strategy['is_network'] != is_network:
                        continue

                # 检查分辨率约束（S0策略没有max_dim限制）
                if strategy['max_dim'] is not None and max_dim is not None:
                    # 如果图片已经小于目标尺寸，可以使用S0（不缩放）
                    if max_dim < strategy['max_dim']:
                        # 图片比目标尺寸小，跳过缩放
                        continue

                # 匹配成功
                self.logger.debug(f"[策略选择] {strategy_id}: 文件{file_size_mb:.1f}MB, "
                                f"分辨率{max_dim if max_dim else 'unknown'}px, "
                                f"{'网络' if is_network else '本地'}路径")
                return strategy_id, strategy

            # 默认使用S1策略
            self.logger.debug(f"[策略选择] 使用默认S1策略: 文件{file_size_mb:.1f}MB")
            return 'S1', self.scaling_profiles['S1']

        except Exception as e:
            self.logger.warning(f"[策略选择] 选择失败，使用默认S1: {e}")
            return 'S1', self.scaling_profiles['S1']

    def _apply_scaling_strategy(self, image_data, strategy_id, strategy_config, original_width, original_height):
        """应用缩放策略（Task 2.1）

        根据策略配置对图片进行缩放处理，统一OpenCV和PIL的输出为numpy数组。

        Args:
            image_data: 图片数据（numpy array）
            strategy_id: 策略ID（S0/S1/S2）
            strategy_config: 策略配置字典
            original_width: 原始宽度
            original_height: 原始高度

        Returns:
            (scaled_image, scale_ratio): 缩放后的图片数据和缩放比例
        """
        try:
            max_dim = strategy_config.get('max_dim')

            # S0策略：不缩放
            if strategy_id == 'S0' or max_dim is None:
                self.logger.debug(f"[缩放策略] {strategy_id} 保持原图: {original_width}x{original_height}")
                return image_data, 1.0

            # 计算是否需要缩放
            current_max_dim = max(original_width, original_height)
            if current_max_dim <= max_dim:
                self.logger.debug(f"[缩放策略] {strategy_id} 图片已小于目标尺寸，跳过缩放: {original_width}x{original_height}")
                return image_data, 1.0

            # 计算缩放比例
            scale_ratio = max_dim / current_max_dim
            new_width = int(original_width * scale_ratio)
            new_height = int(original_height * scale_ratio)

            # 执行缩放
            scaled_image = cv2.resize(image_data, (new_width, new_height), interpolation=cv2.INTER_AREA)

            self.logger.debug(f"[缩放策略] {strategy_id} {original_width}x{original_height} -> "
                           f"{new_width}x{new_height} (缩放比{scale_ratio:.2f})")

            return scaled_image, scale_ratio

        except Exception as e:
            self.logger.warning(f"[缩放策略] 应用失败，返回原图: {e}")
            return image_data, 1.0

    @performance_monitor
    def _load_with_opencv(self, image_path):
        """使用OpenCV加载图片（Task 2.1：返回numpy array和原始尺寸）

        Returns:
            (image_array, width, height): numpy数组和原始宽高
        """
        try:
            # 使用imdecode支持中文路径
            img_array_file = np.fromfile(image_path, dtype=np.uint8)
            img = cv2.imdecode(img_array_file, cv2.IMREAD_COLOR)

            # 正确检查OpenCV解码结果：既要检查None，也要检查空数组
            if img is None or img.size == 0:
                raise ImageLoadError("无法读取图片")

            # OpenCV默认是BGR，转换为RGB
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

            # Task 2.1：返回原始尺寸，缩放由_apply_scaling_strategy统一处理
            height, width = img.shape[:2]
            return img, width, height

        except Exception as e:
            self.logger.error(f"[OpenCV加载失败] {Path(image_path).name}: {e}")
            raise ImageLoadError(f"OpenCV加载失败: {e}")
    
    def _load_with_pil_optimized(self, image_path):
        """使用PIL优化加载（Task 2.1：返回numpy array和原始尺寸）

        Returns:
            (image_array, width, height): numpy数组和原始宽高
        """
        try:
            with Image.open(image_path) as pil_img:
                # Task 2.1：保存原始尺寸
                original_width, original_height = pil_img.size

                # 确保是RGB模式
                if pil_img.mode != 'RGB':
                    pil_img = pil_img.convert('RGB')

                # 转换为numpy数组
                img_array = np.array(pil_img)

                # 处理不同维度的图像
                if len(img_array.shape) == 2:  # 灰度图像
                    # 将灰度图像转换为RGB
                    img_array = np.stack([img_array] * 3, axis=-1)
                elif len(img_array.shape) == 3:
                    # 确保是3通道
                    if img_array.shape[2] == 4:  # RGBA
                        img_array = img_array[:, :, :3]
                    elif img_array.shape[2] != 3:
                        raise ValueError(f"不支持的通道数: {img_array.shape[2]}")
                else:
                    raise ValueError(f"不支持的图像形状: {img_array.shape}")

                # Task 2.1：返回原始尺寸，缩放由_apply_scaling_strategy统一处理
                return img_array, original_width, original_height

        except Exception as e:
            self.logger.error(f"PIL优化加载失败: {e}")
            raise ImageLoadError(f"PIL加载失败: {e}")
    
    def _create_adaptive_thread_pool(self):
        """创建自适应线程池，根据系统性能和网络环境调整"""
        try:
            cpu_count = psutil.cpu_count(logical=False)  # 物理核心数
            logical_cpu_count = psutil.cpu_count(logical=True)  # 逻辑核心数
            memory_gb = psutil.virtual_memory().total / (1024**3)
            
            # 检测网络环境（如果当前目录是网络路径）
            is_network_env = hasattr(self, 'current_directory') and is_network_path(getattr(self, 'current_directory', ''))
            
            if is_network_env:
                # 网络环境：大幅减少线程数，避免网络拥塞
                base_threads = max(2, int(cpu_count * 0.5))  # 物理核心数的一半
                max_limit = 3  # 网络环境最多3个线程
                self.logger.info(f"[线程池优化] 检测到网络环境，降低并发度避免网络拥塞")
            else:
                # 本地环境：正常配置
                base_threads = min(int(cpu_count * 1.5), logical_cpu_count)
                max_limit = 8  # 本地环境最多8个线程
            
            # 根据内存调整
            if memory_gb >= 16:
                max_threads = min(base_threads + 1, max_limit)
            elif memory_gb >= 8:
                max_threads = min(base_threads, max_limit - 1)
            else:
                max_threads = min(base_threads, max_limit - 2)
            
            # 确保至少有2个线程
            max_threads = max(2, max_threads)
            
            # 为exe打包优化：进一步限制
            if hasattr(sys, 'frozen'):  # 检测是否为exe
                if is_network_env:
                    max_threads = min(max_threads, 2)  # 网络+EXE环境最多2个线程
                else:
                    max_threads = min(max_threads, 3)  # 本地+EXE环境最多3个线程
                self.logger.info(f"[线程池] EXE环境限制线程数为:{max_threads}")

            env_type = "网络" if is_network_env else "本地"
            self.logger.debug(f"[线程池配置] {env_type}环境 CPU核心:{cpu_count}物理/{logical_cpu_count}逻辑 "
                             f"内存:{memory_gb:.1f}GB 线程池大小:{max_threads}")
            
            return ThreadPoolExecutor(max_workers=max_threads, thread_name_prefix="ImageLoader")
            
        except Exception as e:
            self.logger.warning(f"线程池自适应配置失败，使用默认配置: {e}")
            return ThreadPoolExecutor(max_workers=3, thread_name_prefix="ImageLoader")
        
    def _get_optimal_cache_size(self):
        """根据系统内存动态确定缓存大小 - 针对17-20MB大图片优化"""
        try:
            total_memory = psutil.virtual_memory().total
            available_memory = psutil.virtual_memory().available
            
            # 针对大图片优化：确保能缓存足够多的17-20MB图片
            # 平均图片大小按20MB估算，滑动窗口50张，需要约1GB
            estimated_large_image_cache = 30 * 20 * 1024 * 1024  # 30张 * 20MB (网络路径进一步减少缓存)
            
            # 更激进的策略：使用85%的可用内存，为大图片预留更多空间
            target_usage = available_memory * 0.85
            
            # 设置针对大图片的最小值
            min_cache = max(2 * 1024 * 1024 * 1024, estimated_large_image_cache)  # 最少2GB或大图片缓存需求
            max_cache = min(total_memory * 0.7, 12 * 1024 * 1024 * 1024)  # 最多12GB或总内存70%
            
            optimal_size = max(min_cache, min(max_cache, target_usage))
            
            # 计算理论缓存图片数量
            avg_image_size = 15 * 1024 * 1024  # 假设平均15MB
            estimated_image_count = optimal_size // avg_image_size

            self.logger.debug(f"大图片优化缓存策略: {optimal_size / 1024 / 1024:.0f}MB "
                             f"(可用内存: {available_memory / 1024 / 1024 / 1024:.1f}GB, "
                             f"使用率: {optimal_size / available_memory * 100:.0f}%, "
                             f"预计可缓存: {estimated_image_count}张15MB图片)")
            return int(optimal_size)
        except ImportError:
            return 3 * 1024 * 1024 * 1024  # 默认3GB，为大图片预留更多
    
    def _is_valid_pixmap(self, pixmap):
        """安全检查pixmap是否有效，避免numpy数组布尔值判断错误"""
        if pixmap is None:
            return False
        try:
            # numpy数组检查
            if hasattr(pixmap, 'shape') and hasattr(pixmap, 'dtype'):
                return pixmap.shape is not None and len(pixmap.shape) > 0 and pixmap.shape[0] > 0
            # PIL图片检查
            elif hasattr(pixmap, 'size') and hasattr(pixmap, 'mode'):
                return pixmap.size[0] > 0 and pixmap.size[1] > 0
            # QPixmap检查
            elif hasattr(pixmap, 'width') and hasattr(pixmap, 'height'):
                return pixmap.width() > 0 and pixmap.height() > 0
            # 其他情况，尝试转换为bool
            else:
                return bool(pixmap)
        except (ValueError, TypeError, AttributeError):
            return False
    
    def load_image(self, image_path, priority=True):
        """智能图片加载调度 - 使用线程池并行加载（紧急修复：添加预加载去重和限流）"""
        try:
            # 快速检查内存缓存，避免不必要的线程池任务
            # 这可以显著减少线程切换开销和并发计数操作
            cache_key = self._get_cache_key(image_path)
            cached_pixmap = self._get_from_cache(cache_key)
            if self._is_valid_pixmap(cached_pixmap):
                # 内存缓存命中，直接返回，不进入线程池
                # 这避免了：线程锁操作、Future对象创建、回调函数添加、线程切换

                # 优化6：内存缓存命中计数
                with self._stats_lock:
                    self.memory_hits += 1

                return

            # 检查并发限制，网络环境使用更保守策略
            is_network_env = is_network_path(image_path)

            if is_network_env:
                # 网络环境：2倍线程池大小的并发，提高响应性
                max_concurrent = max(4, self.thread_pool._max_workers * 2)
            else:
                # 本地环境：3倍线程池大小的并发，充分利用本地I/O
                max_concurrent = max(8, int(self.thread_pool._max_workers * 3))

            # 线程安全地检查并发数
            with self.concurrent_lock:
                current_concurrent = self.concurrent_loads

            # 紧急修复：低优先级任务的去重和限流机制
            if not priority:
                # 1. 去重：检查该路径是否已经在预加载队列中
                with self.preload_jobs_lock:
                    if image_path in self.pending_preload_jobs:
                        self.logger.debug(f"[预加载去重] 跳过重复任务: {Path(image_path).name}")
                        return

                # 2. 限流：当并发数达到上限时，直接跳过低优先级任务
                if current_concurrent >= max_concurrent:
                    self.logger.debug(f"[预加载限流] 并发已满，跳过预加载: {Path(image_path).name} ({current_concurrent}/{max_concurrent})")
                    return

                # 3. 添加到预加载任务集合
                with self.preload_jobs_lock:
                    self.pending_preload_jobs.add(image_path)

            # 高优先级任务的处理逻辑（保持原有逻辑）
            if current_concurrent >= max_concurrent:
                if priority:
                    # 高优先级任务：短暂等待后强制执行
                    env_type = "网络" if is_network_env else "本地"
                    self.logger.info(f"[并发控制] {env_type}环境高优先级任务等待，当前并发:{current_concurrent}/{max_concurrent}")
                    # 只等待很短时间，避免UI卡死
                    wait_count = 0
                    while current_concurrent >= max_concurrent and wait_count < 5:  # 最多等待0.5秒
                        time.sleep(0.1)
                        wait_count += 1
                        with self.concurrent_lock:
                            current_concurrent = self.concurrent_loads

                    # 高优先级任务总是执行，不会被阻塞
                    if current_concurrent >= max_concurrent:
                        self.logger.info(f"[并发控制] 高优先级任务强制执行，当前并发:{current_concurrent}/{max_concurrent}")

            # 优化4：根据优先级选择线程池
            if priority and self.use_dual_thread_pools:
                pool = self.priority_pool
                pool_name = "主图"
            else:
                pool = self.thread_pool
                pool_name = "预加载" if not priority else "主图"

            # 增加全局并发计数，同时增加对应的统计字段
            with self.concurrent_lock:
                self.concurrent_loads += 1
                # 优化4：根据优先级增加对应的统计字段
                if priority:
                    self.priority_loads += 1
                else:
                    self.background_loads += 1

            # 检查线程池状态，避免在关闭后提交任务
            if not self.running or not hasattr(self, 'thread_pool') or self.thread_pool._shutdown:
                self.logger.debug(f"[并行加载] 线程池已关闭，跳过任务: {Path(image_path).name}")
                with self.concurrent_lock:
                    self.concurrent_loads -= 1  # 恢复计数器
                    if priority:
                        self.priority_loads -= 1
                    else:
                        self.background_loads -= 1
                return

            # 如果使用主图线程池，还需要检查它的状态
            if priority and self.use_dual_thread_pools:
                if not hasattr(self, 'priority_pool') or self.priority_pool is None or self.priority_pool._shutdown:
                    self.logger.warning(f"[优化4-双线程池] 主图线程池不可用，回退到预加载线程池")
                    pool = self.thread_pool
                    pool_name = "主图(回退)"

            # 使用选定的线程池并行加载
            try:
                if priority:
                    self.current_task = image_path

                future = pool.submit(self._load_image_worker, image_path, priority)
                # 优化4：回调函数传入is_priority参数
                future.add_done_callback(lambda f, p=priority: self._on_load_complete(image_path, p, f))

                # 优化4：日志输出线程池信息和统计
                self.logger.debug(f"[优化4-{pool_name}] 提交任务: {Path(image_path).name} "
                               f"并发:{self.concurrent_loads} (主图:{self.priority_loads}/预加载:{self.background_loads})")
            except Exception as submit_error:
                # 提交失败时需要回滚计数器
                with self.concurrent_lock:
                    self.concurrent_loads = max(0, self.concurrent_loads - 1)
                    if priority:
                        self.priority_loads = max(0, self.priority_loads - 1)
                    else:
                        self.background_loads = max(0, self.background_loads - 1)

                # 从预加载集合中移除
                if not priority:
                    with self.preload_jobs_lock:
                        self.pending_preload_jobs.discard(image_path)

                # 如果是网络路径，回滚网络计数器（在下面的代码中会增加）
                # 这里先不处理，因为网络计数器在任务成功提交后才增加

                self.logger.error(f"[优化4-{pool_name}] 提交任务失败: {submit_error}")
                raise submit_error

            # Task 1.1 P0修复：任务成功提交后再增加网络计数器
            # 这样可以避免在任务被拒绝或提交失败时需要回滚计数器
            if is_network_env:
                with self._network_counter_lock:
                    self.active_network_sources += 1
                    self.last_network_activity_ts = time.time()

                    # 如果定时器未运行，启动它
                    if not self.cleanup_timer.isActive():
                        self.cleanup_timer.start(30000)
                        self.logger.info("[路径感知] 检测到网络路径，启动清理定时器")

        except Exception as e:
            # Task 1.1 P0修复：异常时需要同时回滚两个计数器
            # 优化4：同时回滚统计字段
            with self.concurrent_lock:
                self.concurrent_loads = max(0, self.concurrent_loads - 1)
                if priority:
                    self.priority_loads = max(0, self.priority_loads - 1)
                else:
                    self.background_loads = max(0, self.background_loads - 1)

            # 紧急修复：异常时也要从预加载集合中移除
            if not priority:
                with self.preload_jobs_lock:
                    self.pending_preload_jobs.discard(image_path)

            # 如果是网络路径，还需要回滚网络计数器
            if is_network_env:
                with self._network_counter_lock:
                    self.active_network_sources = max(0, self.active_network_sources - 1)

            self.logger.error(f"[并行加载] 提交加载任务失败，重置并发计数器: {e}")
            raise ImageLoadError(f"提交加载任务失败: {e}")
    
    def _load_image_worker(self, image_path, is_priority):
        """线程池工作函数（优化4：根据优先级使用不同的日志前缀）"""
        load_start = time.time()
        # 优化4：根据优先级选择日志前缀
        log_prefix = "[主图加载]" if is_priority else "[预加载]"

        try:
            cache_key = self._get_cache_key(image_path)

            # 检查内存缓存
            cached_pixmap = self._get_from_cache(cache_key)
            if self._is_valid_pixmap(cached_pixmap):
                # Task 2.3修复：内存缓存命中也要增加hit计数
                with self._scaled_cache_lock:
                    self.scaled_cache_hit_count += 1
                load_time = (time.time() - load_start) * 1000
                self.logger.debug(f"{log_prefix}-内存缓存命中 {Path(image_path).name} 耗时:{load_time:.1f}ms")
                return {'image_data': cached_pixmap, 'cached': True, 'load_time': load_time}

            # Task 2.1收尾P2修复：先检查磁盘缓存，避免在缓存命中前访问网络
            is_network = is_network_path(image_path)

            if is_network:
                # Task 2.1收尾P2修复：使用CacheIndex查询元数据（不访问网络）
                cached_pixmap = self._load_from_local_cache(image_path)
                if self._is_valid_pixmap(cached_pixmap):
                    # Task 2.3修复：磁盘缓存命中也要增加hit计数（_load_from_local_cache内部已经增加了）
                    # 更新内存缓存，避免下次再读磁盘
                    self._update_cache(cache_key, cached_pixmap)
                    load_time = (time.time() - load_start) * 1000
                    self.logger.debug(f"{log_prefix}-磁盘缓存命中 {Path(image_path).name} 耗时:{load_time:.1f}ms")
                    return {'image_data': cached_pixmap, 'cached': True, 'load_time': load_time}

            # Task 2.3修复：缓存完全未命中，增加miss计数
            with self._scaled_cache_lock:
                self.scaled_cache_miss_count += 1

            # 优化6：网络加载计数（缓存未命中）
            with self._stats_lock:
                self.network_miss += 1

            # 缓存未命中，现在才访问网络获取文件信息
            file_size = Path(image_path).stat().st_size
            file_size_mb = file_size / 1024 / 1024

            # 使用OpenCV或PIL加载（Task 2.1：解包返回的元组）
            if self.use_opencv and cv2 is not None:
                try:
                    image_array, width, height = self._load_with_opencv(image_path)
                except ImageLoadError:
                    # OpenCV失败时回退到PIL
                    if PIL_AVAILABLE:
                        image_array, width, height = self._load_with_pil_optimized(image_path)
                    else:
                        raise
            else:
                if PIL_AVAILABLE:
                    image_array, width, height = self._load_with_pil_optimized(image_path)
                else:
                    raise ImageLoadError("没有可用的图像加载库")

            # Task 2.1：选择并应用缩放策略
            max_dim = max(width, height)
            strategy_id, strategy_config = self._select_scaling_strategy(file_size_mb, max_dim, is_network)
            scaled_array, scale_ratio = self._apply_scaling_strategy(image_array, strategy_id, strategy_config, width, height)

            # Task 2.1收尾：获取目标格式
            target_format = strategy_config.get('target_format', 'original')

            # 确定实际保存格式
            if target_format == 'original':
                # 保持原格式：从文件扩展名推断
                original_ext = Path(image_path).suffix.lower()
                if original_ext in ['.jpg', '.jpeg']:
                    actual_format = 'jpeg'
                elif original_ext in ['.png']:
                    actual_format = 'png'
                elif original_ext in ['.webp']:
                    actual_format = 'webp'
                else:
                    actual_format = 'jpeg'  # 默认JPEG
            else:
                actual_format = target_format

            # Task 2.1：记录策略应用信息到日志
            scaled_height, scaled_width = scaled_array.shape[:2]
            self.logger.debug(f"[Task2.1-策略应用] {Path(image_path).name} | "
                           f"策略:{strategy_id} | "
                           f"原始:{width}x{height}({file_size_mb:.1f}MB) | "
                           f"缩放:{scaled_width}x{scaled_height}(比例{scale_ratio:.2f}) | "
                           f"格式:{actual_format} | "
                           f"{'网络' if is_network else '本地'}路径")

            # 检查加载结果（scaled_array是numpy数组，不是QPixmap）
            if self._is_valid_pixmap(scaled_array):
                # 缓存缩放后的numpy数组到内存
                self._update_cache(cache_key, scaled_array)

                # Task 2.1收尾：保存到本地磁盘缓存（仅对网络路径），传递完整策略信息
                if is_network_path(image_path):
                    try:
                        self._save_to_local_cache(
                            image_path,
                            scaled_array,
                            strategy_id=strategy_id,
                            scale_ratio=scale_ratio,
                            target_format=actual_format,
                            original_width=width,
                            original_height=height
                        )
                    except Exception as e:
                        # 缓存保存失败不影响正常加载
                        self.logger.debug(f"[并行加载] 保存磁盘缓存失败: {e}")

                load_time = (time.time() - load_start) * 1000

                # 记录性能统计
                self.load_times.append(load_time)
                if len(self.load_times) > 100:
                    self.load_times = self.load_times [-100:]

                avg_load_time = sum(self.load_times) / len(self.load_times)

                self.logger.debug(f"{log_prefix}-成功 {Path(image_path).name} {file_size_mb:.1f}MB "
                               f"耗时:{load_time:.1f}ms 平均:{avg_load_time:.1f}ms")

                # 返回缩放后的numpy数组（不是QPixmap！由UI层负责转换）
                return {'image_data': scaled_array, 'cached': False, 'load_time': load_time}
            else:
                raise ImageLoadError("图片加载失败")

        except Exception as e:
            load_time = (time.time() - load_start) * 1000
            self.logger.error(f"{log_prefix}-失败 {Path(image_path).name} 耗时:{load_time:.1f}ms 错误:{e}")
            return {'image_data': None, 'error': str(e), 'load_time': load_time}
    
    def _on_load_complete(self, image_path, is_priority, future):
        """加载完成回调（优化4：增加is_priority参数）"""
        # 先减少并发计数，避免重复减少，线程安全
        with self.concurrent_lock:
            self.concurrent_loads = max(0, self.concurrent_loads - 1)

            # 优化4：根据优先级减少对应的统计字段
            if is_priority:
                self.priority_loads = max(0, self.priority_loads - 1)
            else:
                self.background_loads = max(0, self.background_loads - 1)

        # 紧急修复：从预加载任务集合中移除（如果存在）
        with self.preload_jobs_lock:
            self.pending_preload_jobs.discard(image_path)

        # Task 1.1：递减网络计数器并控制定时器
        if is_network_path(image_path):
            with self._network_counter_lock:
                self.active_network_sources = max(0, self.active_network_sources - 1)

                # 如果没有活跃任务且超过5分钟无活动，暂停定时器
                if self.active_network_sources == 0:
                    idle_time = time.time() - self.last_network_activity_ts
                    if idle_time > 300 and self.cleanup_timer.isActive():
                        self.cleanup_timer.stop()
                        self.logger.info("[路径感知] 无网络活动，暂停清理定时器")

        try:
            result = future.result()

            # 检查加载结果
            image_data = result.get('image_data')
            if self._is_valid_pixmap(image_data):
                # 发射信号，将图像数据传递给主线程
                self.image_loaded.emit(image_path, image_data)
            elif 'error' in result:
                self.logger.error(f"图像加载错误: {result['error']}")

        except Exception as e:
            self.logger.error(f"处理加载完成回调时出错: {e}")
    
    def _get_cache_key(self, image_path):
        """生成缓存键"""
        return str(image_path)
        
    def _update_cache(self, cache_key, pixmap):
        """更新缓存"""
        with self.concurrent_lock:
            if len(self.cache) >= self.cache_size:
                # 简单的LRU策略：删除最旧的条目
                oldest_key = next(iter(self.cache))
                del self.cache[oldest_key]
            
            self.cache[cache_key] = pixmap
        
    def _get_from_cache(self, cache_key):
        """从缓存获取图像"""
        with self.concurrent_lock:
            return self.cache.get(cache_key)
    
    def get_cache_info(self):
        """获取缓存信息"""
        with self.concurrent_lock:
            return {
                'cache_size': len(self.cache),
                'max_cache_size': self.cache_size,
                'hit_count': self.cache_hit_count,
                'miss_count': self.cache_miss_count
            }

    def get_cache_stats(self):
        """获取细粒度缓存统计信息（优化6：全局累计统计）

        返回三层缓存的命中情况：
        - memory_hits: 内存缓存命中次数
        - disk_hits: 磁盘缓存命中次数
        - network_miss: 网络加载次数（缓存未命中）

        Returns:
            dict: 包含命中率、总请求数等统计信息
        """
        with self._stats_lock:
            total = self.memory_hits + self.disk_hits + self.network_miss

            if total == 0:
                return {
                    'memory_hits': 0,
                    'disk_hits': 0,
                    'network_miss': 0,
                    'total_requests': 0,
                    'memory_hit_rate': '0.0%',
                    'disk_hit_rate': '0.0%',
                    'overall_hit_rate': '0.0%',
                    'network_miss_rate': '0.0%'
                }

            memory_rate = self.memory_hits / total * 100
            disk_rate = self.disk_hits / total * 100
            overall_hit_rate = (self.memory_hits + self.disk_hits) / total * 100
            network_rate = self.network_miss / total * 100

            return {
                'memory_hits': self.memory_hits,
                'disk_hits': self.disk_hits,
                'network_miss': self.network_miss,
                'total_requests': total,
                'memory_hit_rate': f"{memory_rate:.1f}%",
                'disk_hit_rate': f"{disk_rate:.1f}%",
                'overall_hit_rate': f"{overall_hit_rate:.1f}%",
                'network_miss_rate': f"{network_rate:.1f}%"
            }

    def clear_cache(self):
        """清理缓存"""
        with self.concurrent_lock:
            self.cache.clear()
            self.thumbnail_cache.clear()
            self.cache_hit_count = 0
            self.cache_miss_count = 0

        # Task 3.2：清理缓存时同时归零缩放缓存统计
        self.reset_scaled_cache_stats()

    def reset_scaled_cache_stats(self):
        """重置缩放缓存统计（Task 3.2：周期归零）

        在以下场景调用：
        - clear_cache(): 清理内存缓存时
        - _cleanup_local_cache(): 清理磁盘缓存后
        - set_working_path(): 切换工作路径时
        - _periodic_resource_cleanup(): 每个清理周期后（记录日志后归零）

        目的：让命中率反映"最近一个周期"的表现，而不是启动以来的累积平均
        """
        with self._scaled_cache_lock:
            old_hit = self.scaled_cache_hit_count
            old_miss = self.scaled_cache_miss_count
            total = old_hit + old_miss

            # 归零前记录当前周期的命中率（如果有数据）
            if total > 0:
                hit_rate = old_hit / total
                self.logger.info(f"[Task3.2-命中率归零] 本周期统计: "
                               f"命中{old_hit}次, 未命中{old_miss}次, "
                               f"命中率{hit_rate:.1%} → 计数器已归零")

            # 归零计数器
            self.scaled_cache_hit_count = 0
            self.scaled_cache_miss_count = 0

    def get_monitoring_metrics(self):
        """获取监控指标（仅供开发调试使用，默认不发送信号）

        注意：此方法仅用于开发诊断，需要时由开发者手动调用。
        产品版本不包含监控UI，不会自动发送cache_status信号。

        Returns:
            dict: 包含以下4个监控指标的字典
                - usage_ratio: 缓存占用率（0.0-1.0）
                - timer_interval_ms: 当前清理定时器周期（毫秒）
                - active_network_sources: 活跃的SMB/网络加载任务数
                - scaled_cache_hit_rate: 缩放缓存命中率（0.0-1.0）
        """
        metrics = {}

        # 1. usage_ratio: 缓存占用率
        if self.cache_meta:
            max_bytes = self.smb_optimization['cache_max_size_gb'] * (1024**3)
            metrics['usage_ratio'] = self.cache_meta.get_usage_ratio(max_bytes)
        else:
            metrics['usage_ratio'] = 0.0

        # 2. timer_interval_ms: 当前定时器周期
        metrics['timer_interval_ms'] = self.cleanup_timer.interval()

        # 3. active_network_sources: 活跃SMB任务数
        with self._network_counter_lock:
            metrics['active_network_sources'] = self.active_network_sources

        # 4. scaled_cache_hit_rate: 缩放缓存命中率（线程安全读取）
        with self._scaled_cache_lock:
            hit_count = self.scaled_cache_hit_count
            miss_count = self.scaled_cache_miss_count

        total = hit_count + miss_count
        if total > 0:
            metrics['scaled_cache_hit_rate'] = hit_count / total
        else:
            metrics['scaled_cache_hit_rate'] = 0.0

        return metrics

    def _periodic_resource_cleanup(self):
        """定期资源清理 - 自适应调度（Task 1.3）

        根据缓存占用率动态调整定时器周期：
        - 占用率 <40%: 5分钟周期
        - 占用率 40-70%: 1分钟周期
        - 占用率 70-90%: 30秒周期
        - 占用率 >90%: 10秒周期
        """
        start_time = time.time()

        try:
            # 内存缓存清理（快速，始终执行）
            if len(self.cache) > self.cache_size * 0.8:
                self._gentle_cache_cleanup()

            # 磁盘缓存自适应调度
            if not self.smb_optimization['enable_local_cache']:
                return

            # 阶段1修复-问题4: 修改触发条件，避免清理盲区
            # 优先使用active_network_sources判断，作为备用才使用is_network_working_path
            # 这样即使set_working_path未被调用，只要有网络任务活跃，清理仍会执行
            with self._network_counter_lock:
                has_network_activity = self.active_network_sources > 0

            # 如果没有网络活跃任务，且工作路径明确是本地路径，则跳过清理
            if not has_network_activity and self.current_working_path is not None and not self.is_network_working_path:
                self.logger.debug("[路径感知] 本地路径环境且无网络活动，跳过磁盘缓存清理")
                return

            # 如果有网络活动或缓存占用>0，则继续执行清理逻辑
            # Task 1.3：自适应调度核心逻辑
            if self.cache_meta is None:
                self.logger.warning("[自适应调度] cache_meta未初始化，跳过")
                return

            # 1. 快速读取占用率（<1ms）
            max_bytes = self.smb_optimization['cache_max_size_gb'] * (1024**3)
            usage_ratio = self.cache_meta.get_usage_ratio(max_bytes)

            # 2. 根据占用率动态调整定时器周期
            old_interval = self.cleanup_timer.interval()

            if usage_ratio < 0.4:
                new_interval = 5 * 60 * 1000  # 5分钟
            elif usage_ratio < 0.7:
                new_interval = 60 * 1000  # 1分钟
            elif usage_ratio < 0.9:
                new_interval = 30 * 1000  # 30秒
            else:
                new_interval = 10 * 1000  # 10秒

            # 3. 更新定时器周期（仅当变化时）
            if new_interval != old_interval:
                self.cleanup_timer.setInterval(new_interval)
                self.logger.info(f"[自适应调度] 占用率:{usage_ratio:.1%}, "
                               f"定时器周期:{old_interval//1000}s → {new_interval//1000}s")

            # 4. 只有超过阈值才执行清理（避免不必要的文件扫描）
            threshold = 1.0  # 100%占用率
            if usage_ratio > threshold:
                self.logger.info(f"[自适应调度] 占用率{usage_ratio:.1%}超限，开始清理")
                self._cleanup_local_cache()
            else:
                self.logger.debug(f"[自适应调度] 占用率{usage_ratio:.1%}正常，跳过清理")

            # 优化5：容量控制触发索引重建（90%阈值）
            reconcile_threshold = 0.9  # 90%占用率
            if usage_ratio > reconcile_threshold:
                # 检查是否最近已经执行过（避免频繁扫描）
                current_time = time.time()
                time_since_last = current_time - self.last_reconcile_ts if self.last_reconcile_ts > 0 else float('inf')

                # 至少间隔1小时才重新扫描
                if time_since_last > 3600:
                    self.logger.info(f"[优化5-容量触发] 占用率{usage_ratio:.1%}超过90%，触发索引重建")
                    self._force_reconcile_cache()
                else:
                    self.logger.debug(f"[优化5-容量触发] 占用率{usage_ratio:.1%}超过90%，但距上次扫描仅{time_since_last/60:.1f}分钟，跳过")

            # 性能监控
            elapsed = (time.time() - start_time) * 1000
            self.logger.debug(f"[性能监控] 清理周期耗时: {elapsed:.1f}ms")

            # Task 3.2：每个清理周期结束后归零命中率统计
            # 目的：让命中率反映"最近一个周期"的表现，而不是启动以来的累积平均
            self.reset_scaled_cache_stats()

        except Exception as e:
            elapsed = (time.time() - start_time) * 1000
            self.logger.warning(f"定期资源清理失败（耗时{elapsed:.1f}ms）: {e}")
    
    def _gentle_cache_cleanup(self):
        """温和的缓存清理"""
        with self.concurrent_lock:
            if len(self.cache) > self.cache_size:
                # 删除超出的缓存项
                excess = len(self.cache) - self.cache_size
                for _ in range(excess):
                    if self.cache:
                        oldest_key = next(iter(self.cache))
                        del self.cache[oldest_key]
    
    def set_image_files_reference(self, image_files):
        """设置图片文件列表引用（用于索引解析）"""
        self.image_files = image_files
        
    def set_current_image_index(self, index):
        """设置当前图片索引（用于智能缓存）"""
        self.current_index = index

    def set_working_path(self, path):
        """设置当前工作路径（Task 1.1：路径感知触发）

        当用户打开新的图片目录时调用此方法，用于判断是否需要磁盘缓存清理。
        本地路径不需要清理，可节省100%清理开销（约180秒/小时）。

        Args:
            path: 图片目录路径（str或Path对象）
        """
        try:
            if path is None:
                self.current_working_path = None
                self.is_network_working_path = False
                self.logger.debug("[路径感知] 工作路径已清除")
                return

            self.current_working_path = str(path)
            self.is_network_working_path = is_network_path(self.current_working_path)

            path_type = "网络" if self.is_network_working_path else "本地"
            self.logger.info(f"[路径感知] 工作路径已设置为{path_type}路径: {Path(path).name}")

            # Task 3.2：切换工作路径时归零命中率统计
            self.reset_scaled_cache_stats()

        except Exception as e:
            self.logger.warning(f"[路径感知] 设置工作路径失败: {e}")
            self.current_working_path = None
            self.is_network_working_path = False

    def warmup_cache(self, image_files, count=100, enable_tail_warmup=False, callback=None):
        """缓存预热工具（优化8：主动预加载 + 循环翻页末尾预热）

        在后台按顺序加载指定数量的图片，提前建立缓存。
        如果开启循环翻页，还会预热末尾 count//2 张图片。

        Args:
            image_files: 图片文件路径列表
            count: 前段预热数量（默认100张）
            enable_tail_warmup: 是否开启末尾预热（循环翻页功能）
            callback: 进度回调函数 callback(current, total, filename)

        Returns:
            bool: 是否启动成功
        """
        try:
            # 检查是否为网络路径（本地路径无需预热）
            if not self.is_network_working_path:
                self.logger.info("[优化8-预热] 本地路径无需预热，已跳过")
                if callback:
                    callback(0, 0, "本地路径无需预热")
                return False

            if not image_files:
                self.logger.warning("[优化8-预热] 图片列表为空，无法预热")
                return False

            total_files = len(image_files)

            # 计算预热范围
            head_count = min(count, total_files)
            head_indices = list(range(head_count))

            tail_indices = []
            if enable_tail_warmup and total_files > count:
                tail_count = count // 2
                tail_start = max(head_count, total_files - tail_count)
                tail_indices = list(range(tail_start, total_files))
                self.logger.info(f"[循环翻页] 开启末尾预热: 前{head_count}张 + 末尾{len(tail_indices)}张")

            # 合并预热列表（去重）
            warmup_indices = list(dict.fromkeys(head_indices + tail_indices))
            actual_count = len(warmup_indices)
            if actual_count == 0:
                return False

            self.logger.info(f"[优化8-预热] 开始预热缓存，目标: {actual_count}张图片")

            # 在后台线程中执行预热
            import threading
            def warmup_worker():
                success_count = 0
                for idx, file_index in enumerate(warmup_indices):
                    try:
                        path = str(image_files[file_index])
                        filename = Path(path).name

                        # 低优先级加载（不影响用户操作）
                        self.load_image(path, priority=False)

                        success_count += 1

                        # 回调进度
                        if callback:
                            callback(idx + 1, actual_count, filename)

                        # 节流：避免占满带宽（每张间隔100ms）
                        time.sleep(0.1)

                    except Exception as e:
                        self.logger.debug(f"[优化8-预热] 预热失败: {filename}, {e}")
                        continue

                self.logger.info(f"[优化8-预热] 预热完成: {success_count}/{actual_count}张图片")

                # 完成回调
                if callback:
                    callback(actual_count, actual_count, "预热完成")

            # 启动后台线程
            warmup_thread = threading.Thread(target=warmup_worker, daemon=True)
            warmup_thread.start()

            return True

        except Exception as e:
            self.logger.error(f"[优化8-预热] 启动失败: {e}")
            return False

    def stop(self):
        """停止加载器（优化4：按顺序关闭两个线程池）"""
        self.running = False

        # 优化4：先关闭主图线程池
        if hasattr(self, 'priority_pool') and self.priority_pool is not None:
            try:
                self.logger.info("[优化4-双线程池] 正在关闭主图线程池...")
                self.priority_pool.shutdown(wait=True)
                self.logger.info("[优化4-双线程池] 主图线程池已关闭")
            except Exception as e:
                self.logger.warning(f"[优化4-双线程池] 关闭主图线程池时出错: {e}")

        # 再关闭预加载线程池
        if hasattr(self, 'thread_pool'):
            try:
                self.logger.info("[优化4-双线程池] 正在关闭预加载线程池...")
                self.thread_pool.shutdown(wait=True)
                self.logger.info("[优化4-双线程池] 预加载线程池已关闭")
            except Exception as e:
                self.logger.warning(f"[优化4-双线程池] 关闭预加载线程池时出错: {e}")

        # 停止清理定时器
        if hasattr(self, 'cleanup_timer'):
            self.cleanup_timer.stop()

        self.wait()


class ImageProcessingManager:
    """图片处理管理器 - 统一管理图片加载、缓存、转换等功能"""
    
    def __init__(self, cache_size=30):
        self.image_loader = HighPerformanceImageLoader(cache_size)
        self.logger = logging.getLogger(__name__)
        
    def setup_loader_connections(self, image_loaded_callback, thumbnail_loaded_callback,
                                progress_callback):
        """设置加载器回调连接（Task 3.3：已删除cache_status_callback）"""
        try:
            self.image_loader.image_loaded.connect(image_loaded_callback)
            self.image_loader.thumbnail_loaded.connect(thumbnail_loaded_callback)
            self.image_loader.loading_progress.connect(progress_callback)
        except Exception as e:
            raise ImageLoadError(f"设置加载器连接失败: {e}")
        
    def start_background_loading(self):
        """启动后台加载"""
        if not self.image_loader.isRunning():
            self.image_loader.start()
            
    def stop_background_loading(self):
        """停止后台加载"""
        if self.image_loader.isRunning():
            self.image_loader.stop()
            
    def load_image_with_priority(self, image_path, priority=True):
        """优先加载指定图片"""
        try:
            self.image_loader.load_image(image_path, priority)
        except Exception as e:
            raise ImageLoadError(f"加载图片失败: {e}")
        
    def get_cache_status(self):
        """获取缓存状态"""
        return self.image_loader.get_cache_info()
        
    def clear_image_cache(self):
        """清理图片缓存"""
        self.image_loader.clear_cache()
        
    def set_image_files_reference(self, image_files):
        """设置图片文件列表引用（用于索引解析）"""
        self.image_loader.set_image_files_reference(image_files)
        
    def set_current_image_index(self, index):
        """设置当前图片索引（用于智能缓存）"""
        self.image_loader.set_current_image_index(index)
