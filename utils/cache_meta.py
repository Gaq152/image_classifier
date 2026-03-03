"""
轻量级缓存元数据管理

Meta文件格式（48字节）：
- 4字节: 魔数 b'CACH'
- 2字节: 版本号 (uint16)
- 8字节: total_bytes (uint64)
- 8字节: total_files (uint64)
- 8字节: avg_image_size (uint64)
- 8字节: last_update_ts (uint64)
- 10字节: 保留
"""

import struct
import time
import threading
import logging
from pathlib import Path

# 魔数和版本
MAGIC = b'CACH'
VERSION = 1
META_FORMAT = '<4sHQQQQ10x'  # 小端序，48字节
META_SIZE = 48


class SimpleCacheMeta:
    """简单的缓存元数据管理（不含JSONL索引）"""

    def __init__(self, cache_dir: Path):
        """
        初始化缓存元数据管理器

        Args:
            cache_dir: 缓存目录路径
        """
        self.cache_dir = Path(cache_dir)
        self.meta_path = self.cache_dir / 'cache_meta.bin'
        self._lock = threading.Lock()
        self.logger = logging.getLogger(__name__)

        # 阶段1修复-问题6: 批量更新模式
        self._bulk_update_mode = False  # 是否在批量更新模式
        self._pending_add = []  # 缓冲的add操作（文件大小列表）
        self._pending_remove = []  # 缓冲的remove操作（文件大小列表）

        # Task 2.1收尾：内存中维护策略统计信息（不写入二进制meta文件）
        self._strategy_stats = {
            'S0': {'count': 0, 'total_size': 0},
            'S1': {'count': 0, 'total_size': 0},
            'S2': {'count': 0, 'total_size': 0},
        }
        self._scale_ratios = []  # 缩放比例列表（最多保留1000个样本）
        self._format_stats = {}  # 格式统计 {'jpeg': count, 'png': count, ...}

        # 确保缓存目录存在
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # 初始化或加载meta
        self._ensure_meta_file()

    def _ensure_meta_file(self):
        """确保meta文件存在，不存在则创建"""
        if not self.meta_path.exists():
            self._write_meta(0, 0, 0, time.time())
            self.logger.info(f"[CacheMeta] 创建新的元数据文件: {self.meta_path}")

    def _read_meta_unlocked(self):
        """
        读取meta文件（不加锁，内部使用）

        Returns:
            tuple: (total_bytes, total_files, avg_size, last_update)

        Raises:
            ValueError: 魔数或版本不匹配
        """
        if not self.meta_path.exists():
            return (0, 0, 0, time.time())

        try:
            with open(self.meta_path, 'rb') as f:
                data = f.read(META_SIZE)

            if len(data) < META_SIZE:
                self.logger.warning(f"[CacheMeta] 元数据文件不完整，重新创建")
                return (0, 0, 0, time.time())

            magic, version, total_bytes, total_files, avg_size, last_update = \
                struct.unpack(META_FORMAT, data)

            if magic != MAGIC:
                raise ValueError(f"Invalid magic: {magic}, expected {MAGIC}")
            if version != VERSION:
                raise ValueError(f"Unsupported version: {version}, expected {VERSION}")

            return (total_bytes, total_files, avg_size, last_update)

        except (struct.error, ValueError) as e:
            # 尝试读取旧格式（QQd24x，无魔数）
            self.logger.info(f"[CacheMeta] 检测到旧格式元数据，尝试自动升级...")
            try:
                # 旧格式: file_count(Q), total_size_bytes(Q), last_cleanup_time(d), 24字节填充
                total_files, total_bytes, last_cleanup = struct.unpack('QQd24x', data)

                # 计算平均文件大小
                avg_size = total_bytes // total_files if total_files > 0 else 0

                # 自动升级为新格式（这里会调用_write_meta_unlocked，因为已经在锁外）
                self._write_meta_unlocked(total_bytes, total_files, avg_size, last_cleanup)
                self.logger.info(f"[CacheMeta] 元数据已自动升级: {total_files}个文件, {total_bytes/(1024**3):.2f}GB")

                return (total_bytes, total_files, avg_size, last_cleanup)

            except Exception as upgrade_error:
                # 完全失败，返回空数据
                self.logger.error(f"[CacheMeta] 读取旧格式也失败: {upgrade_error}，重新初始化")
                return (0, 0, 0, time.time())

    def _read_meta(self):
        """
        读取meta文件（带锁，外部使用）

        Returns:
            tuple: (total_bytes, total_files, avg_size, last_update)

        Raises:
            ValueError: 魔数或版本不匹配
        """
        with self._lock:
            return self._read_meta_unlocked()

    def _write_meta_unlocked(self, total_bytes: int, total_files: int, avg_size: int, last_update: float):
        """
        写入meta文件（不加锁，内部使用）

        Args:
            total_bytes: 缓存总字节数
            total_files: 缓存文件数量
            avg_size: 平均文件大小
            last_update: 最后更新时间戳
        """
        try:
            # 原子写入：先写临时文件，再replace
            temp_path = self.meta_path.with_suffix('.tmp')

            data = struct.pack(META_FORMAT,
                               MAGIC, VERSION,
                               total_bytes, total_files,
                               avg_size, int(last_update))

            with open(temp_path, 'wb') as f:
                f.write(data)

            # 原子替换
            temp_path.replace(self.meta_path)

        except Exception as e:
            self.logger.error(f"[CacheMeta] 写入元数据失败: {e}")

    def _write_meta(self, total_bytes: int, total_files: int, avg_size: int, last_update: float):
        """
        写入meta文件（带锁，外部使用）

        Args:
            total_bytes: 缓存总字节数
            total_files: 缓存文件数量
            avg_size: 平均文件大小
            last_update: 最后更新时间戳
        """
        with self._lock:
            self._write_meta_unlocked(total_bytes, total_files, avg_size, last_update)

    def add_entry(self, file_size: int, strategy_id=None, scale_ratio=None,
                  target_format=None, original_width=None, original_height=None):
        """
        添加一个缓存文件记录（原子操作，Task 2.1收尾：支持策略信息）

        Args:
            file_size: 文件大小（字节）
            strategy_id: 缩放策略ID（S0/S1/S2），可选
            scale_ratio: 缩放比例，可选
            target_format: 目标格式（jpeg/png/webp），可选
            original_width: 原始图片宽度，可选
            original_height: 原始图片高度，可选
        """
        # 阶段1修复-问题6 锁粒度修复: 先获取锁，再检查批量模式标志（原子化check-then-act）
        with self._lock:
            # 在锁内检查批量模式，避免竞态条件
            if self._bulk_update_mode:
                self._pending_add.append(file_size)
                self.logger.debug(f"[CacheMeta-批量模式] 缓冲添加记录: +{file_size} bytes")
                return

            # 非批量模式：执行正常的读→改→写
            total_bytes, total_files, avg_size, _ = self._read_meta_unlocked()

            new_total_bytes = total_bytes + file_size
            new_total_files = total_files + 1
            new_avg_size = new_total_bytes // new_total_files if new_total_files > 0 else 0

            self._write_meta_unlocked(new_total_bytes, new_total_files, new_avg_size, time.time())

            # Task 2.1收尾：更新内存中的策略统计信息
            if strategy_id and strategy_id in self._strategy_stats:
                self._strategy_stats[strategy_id]['count'] += 1
                self._strategy_stats[strategy_id]['total_size'] += file_size

            if scale_ratio is not None:
                self._scale_ratios.append(scale_ratio)
                # 保持样本数量上限
                if len(self._scale_ratios) > 1000:
                    self._scale_ratios.pop(0)

            if target_format:
                self._format_stats[target_format] = self._format_stats.get(target_format, 0) + 1

            self.logger.debug(f"[CacheMeta] 添加记录: +{file_size} bytes, 总计 {new_total_files} 文件, {new_total_bytes / (1024**3):.2f}GB")

    def remove_entry(self, file_size: int, strategy_id=None, scale_ratio=None, target_format=None):
        """
        删除一个缓存文件记录（原子操作，Task 2.1收尾P2：支持策略信息回滚）

        Args:
            file_size: 文件大小（字节）
            strategy_id: 缩放策略ID（S0/S1/S2），可选 - 用于回滚策略统计
            scale_ratio: 缩放比例，可选 - 用于回滚缩放比例样本
            target_format: 目标格式（jpeg/png/webp），可选 - 用于回滚格式统计
        """
        # 阶段1修复-问题6 锁粒度修复: 先获取锁，再检查批量模式标志（原子化check-then-act）
        with self._lock:
            # Task 2.1收尾P3修复：无论批量模式还是正常模式，都立即回滚策略统计
            # 策略统计只存在于内存，不写入二进制文件，可以立即更新
            if strategy_id and strategy_id in self._strategy_stats:
                self._strategy_stats[strategy_id]['count'] = max(0, self._strategy_stats[strategy_id]['count'] - 1)
                self._strategy_stats[strategy_id]['total_size'] = max(0, self._strategy_stats[strategy_id]['total_size'] - file_size)

            if scale_ratio is not None and scale_ratio in self._scale_ratios:
                try:
                    self._scale_ratios.remove(scale_ratio)
                except ValueError:
                    pass  # 样本可能已被覆盖，忽略

            if target_format and target_format in self._format_stats:
                self._format_stats[target_format] = max(0, self._format_stats[target_format] - 1)
                if self._format_stats[target_format] == 0:
                    del self._format_stats[target_format]

            # 在锁内检查批量模式，避免竞态条件
            if self._bulk_update_mode:
                self._pending_remove.append(file_size)
                self.logger.debug(f"[CacheMeta-批量模式] 缓冲删除记录: -{file_size} bytes, 策略已回滚")
                return

            # 非批量模式：执行正常的读→改→写
            total_bytes, total_files, avg_size, _ = self._read_meta_unlocked()

            new_total_bytes = max(0, total_bytes - file_size)
            new_total_files = max(0, total_files - 1)
            new_avg_size = new_total_bytes // new_total_files if new_total_files > 0 else 0

            self._write_meta_unlocked(new_total_bytes, new_total_files, new_avg_size, time.time())

            self.logger.debug(f"[CacheMeta] 删除记录: -{file_size} bytes, 剩余 {new_total_files} 文件, {new_total_bytes / (1024**3):.2f}GB")

    def get_usage_ratio(self, max_bytes: int) -> float:
        """
        获取缓存占用率

        Args:
            max_bytes: 最大缓存字节数

        Returns:
            float: 占用率 (0.0 ~ 1.0)
        """
        total_bytes, _, _, _ = self._read_meta()
        return total_bytes / max_bytes if max_bytes > 0 else 0.0

    def get_summary(self) -> dict:
        """
        获取缓存摘要信息（Task 2.1收尾：包含策略统计）

        Returns:
            dict: 包含total_bytes, total_files, avg_image_size, last_update, total_gb,
                  strategy_stats, avg_scale_ratio, format_stats
        """
        total_bytes, total_files, avg_size, last_update = self._read_meta()

        # Task 2.1收尾：计算平均缩放比
        avg_scale_ratio = sum(self._scale_ratios) / len(self._scale_ratios) if self._scale_ratios else 1.0

        # 计算策略分布百分比
        strategy_distribution = {}
        for sid, stats in self._strategy_stats.items():
            if total_files > 0:
                percentage = (stats['count'] / total_files) * 100
                strategy_distribution[sid] = {
                    'count': stats['count'],
                    'percentage': percentage,
                    'avg_size_mb': stats['total_size'] / stats['count'] / (1024**2) if stats['count'] > 0 else 0
                }

        return {
            'total_bytes': total_bytes,
            'total_files': total_files,
            'avg_image_size': avg_size,
            'last_update': last_update,
            'total_gb': total_bytes / (1024**3),
            # Task 2.1收尾：新增策略信息
            'strategy_stats': strategy_distribution,
            'avg_scale_ratio': avg_scale_ratio,
            'format_stats': dict(self._format_stats),
        }

    def reset(self):
        """重置元数据（清空所有记录）"""
        self._write_meta(0, 0, 0, time.time())
        self.logger.info("[CacheMeta] 元数据已重置")

    def update_from_scan(self, file_count: int, total_size_bytes: int):
        """
        从全量扫描更新元数据

        Args:
            file_count: 扫描到的文件数量
            total_size_bytes: 扫描到的总大小
        """
        avg_size = total_size_bytes // file_count if file_count > 0 else 0
        self._write_meta(total_size_bytes, file_count, avg_size, time.time())
        self.logger.info(f"[CacheMeta] 从扫描更新: {file_count} 文件, {total_size_bytes / (1024**3):.2f}GB")

    def begin_bulk_update(self):
        """
        进入批量更新模式（阶段1修复-问题6）

        在全量扫描期间调用，会暂停add_entry/remove_entry的立即写入，
        改为缓冲操作，等待commit_bulk_update时合并提交。

        使用场景：
        - _force_reconcile_cache() 全量校准扫描
        - _cleanup_local_cache() 清理扫描
        """
        with self._lock:
            if self._bulk_update_mode:
                self.logger.warning("[CacheMeta] 已在批量更新模式，重复调用begin_bulk_update")
                return

            self._bulk_update_mode = True
            self._pending_add = []
            self._pending_remove = []
            self.logger.info("[CacheMeta] 进入批量更新模式，缓冲增量操作")

    def commit_bulk_update(self, scanned_count: int, scanned_size: int):
        """
        提交批量更新，合并扫描结果和缓冲的增量操作（阶段1修复-问题6）

        Args:
            scanned_count: 扫描到的文件数量
            scanned_size: 扫描到的总大小（字节）

        说明：
            最终结果 = 扫描结果 + 扫描期间的增量操作
            - 增量文件数 = len(pending_add) - len(pending_remove)
            - 增量大小 = sum(pending_add) - sum(pending_remove)
        """
        with self._lock:
            if not self._bulk_update_mode:
                self.logger.warning("[CacheMeta] 未在批量更新模式，commit_bulk_update调用无效")
                return

            # 计算扫描期间的增量
            net_count = len(self._pending_add) - len(self._pending_remove)
            net_size = sum(self._pending_add) - sum(self._pending_remove)

            # 合并扫描结果和增量
            final_count = max(0, scanned_count + net_count)
            final_size = max(0, scanned_size + net_size)

            # 计算平均文件大小
            avg_size = final_size // final_count if final_count > 0 else 0

            # 写入最终结果
            self._write_meta_unlocked(final_size, final_count, avg_size, time.time())

            # 日志记录
            if net_count != 0 or net_size != 0:
                self.logger.info(
                    f"[CacheMeta-批量提交] 扫描:{scanned_count}文件/{scanned_size/(1024**3):.2f}GB, "
                    f"增量:{net_count:+d}文件/{net_size/(1024**3):+.2f}GB, "
                    f"最终:{final_count}文件/{final_size/(1024**3):.2f}GB"
                )
            else:
                self.logger.info(
                    f"[CacheMeta-批量提交] 扫描期间无增量操作, "
                    f"最终:{final_count}文件/{final_size/(1024**3):.2f}GB"
                )

            # 退出批量模式
            self._bulk_update_mode = False
            self._pending_add = []
            self._pending_remove = []

    def abort_bulk_update(self):
        """
        中止批量更新，丢弃缓冲的增量操作（阶段1修复-问题6）

        使用场景：扫描过程中发生异常，需要回滚批量更新状态
        """
        with self._lock:
            if not self._bulk_update_mode:
                return

            discarded_add = len(self._pending_add)
            discarded_remove = len(self._pending_remove)

            self._bulk_update_mode = False
            self._pending_add = []
            self._pending_remove = []

            self.logger.warning(
                f"[CacheMeta-批量中止] 丢弃缓冲操作: "
                f"{discarded_add}个添加, {discarded_remove}个删除"
            )
