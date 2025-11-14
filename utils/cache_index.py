"""
缓存策略索引管理（Task 2.2准备）

JSONL格式索引文件，每行一个JSON记录：
{
    "path_hash": "abc123...",
    "original_path": "\\\\nas\\photos\\img.jpg",
    "strategy_id": "S1",
    "scale_ratio": 0.5,
    "target_format": "jpeg",
    "original_width": 4000,
    "original_height": 3000,
    "cached_width": 2000,
    "cached_height": 1500,
    "cache_size": 1234567,
    "timestamp": 1234567890.123
}
"""

import json
import threading
import logging
from pathlib import Path
from typing import Optional, Dict, List


class CacheIndex:
    """缓存策略索引管理器（Task 2.2准备）"""

    def __init__(self, cache_dir: Path):
        """
        初始化缓存索引管理器

        Args:
            cache_dir: 缓存目录路径
        """
        self.cache_dir = Path(cache_dir)
        self.index_path = self.cache_dir / 'cache_scaling_index.jsonl'
        self._lock = threading.Lock()
        self.logger = logging.getLogger(__name__)

        # 内存索引：path_hash -> 记录字典
        self._index = {}

        # 确保缓存目录存在
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # 加载索引
        self._load_index()

    def _load_index(self):
        """从JSONL文件加载索引到内存"""
        if not self.index_path.exists():
            self.logger.debug("[CacheIndex] 索引文件不存在，创建空索引")
            return

        try:
            with open(self.index_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        record = json.loads(line)
                        path_hash = record.get('path_hash')
                        if path_hash:
                            self._index[path_hash] = record
                    except json.JSONDecodeError as e:
                        self.logger.warning(f"[CacheIndex] 索引文件第{line_num}行格式错误: {e}")
                        continue

            self.logger.info(f"[CacheIndex] 加载索引成功: {len(self._index)}条记录")

        except Exception as e:
            self.logger.error(f"[CacheIndex] 加载索引失败: {e}")
            self._index = {}

    def add_entry(self, path_hash: str, original_path: str, strategy_id: str,
                  scale_ratio: float, target_format: str,
                  original_width: int, original_height: int,
                  cached_width: int, cached_height: int,
                  cache_size: int):
        """
        添加或更新索引记录

        Args:
            path_hash: 路径哈希值
            original_path: 原始图片路径
            strategy_id: 策略ID
            scale_ratio: 缩放比例
            target_format: 目标格式
            original_width: 原始宽度
            original_height: 原始高度
            cached_width: 缓存宽度
            cached_height: 缓存高度
            cache_size: 缓存文件大小（字节）
        """
        with self._lock:
            import time

            # 检查是否为更新操作（同一path_hash的文件已存在）
            is_update = path_hash in self._index

            record = {
                'path_hash': path_hash,
                'original_path': original_path,
                'strategy_id': strategy_id,
                'scale_ratio': scale_ratio,
                'target_format': target_format,
                'original_width': original_width,
                'original_height': original_height,
                'cached_width': cached_width,
                'cached_height': cached_height,
                'cache_size': cache_size,
                'timestamp': time.time()
            }

            # 更新内存索引
            self._index[path_hash] = record

            # 追加到JSONL文件
            try:
                with open(self.index_path, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(record, ensure_ascii=False) + '\n')

                # 如果是更新操作且索引文件行数过多，触发重建以清理重复记录
                if is_update:
                    # 检查文件行数是否超过内存索引的2倍（说明有大量重复）
                    if self.index_path.exists():
                        with open(self.index_path, 'r', encoding='utf-8') as f:
                            line_count = sum(1 for line in f if line.strip())

                        # 如果JSONL行数超过内存索引的1.5倍，说明有重复记录需要清理
                        if line_count > len(self._index) * 1.5:
                            self.logger.info(f"[CacheIndex] 检测到重复记录过多({line_count}行 vs {len(self._index)}条记录)，触发索引重建")
                            # 在后台重建索引，清理重复记录
                            self.rebuild_index()

            except Exception as e:
                self.logger.error(f"[CacheIndex] 写入索引失败: {e}")

    def get_entry(self, path_hash: str) -> Optional[Dict]:
        """
        查询索引记录

        Args:
            path_hash: 路径哈希值

        Returns:
            dict: 索引记录，如果不存在返回None
        """
        with self._lock:
            return self._index.get(path_hash)

    def remove_entry(self, path_hash: str):
        """
        删除索引记录（仅从内存删除，文件重建时清理）

        Args:
            path_hash: 路径哈希值
        """
        with self._lock:
            if path_hash in self._index:
                del self._index[path_hash]

    def rebuild_index(self):
        """
        重建索引文件（清理已删除的记录）

        扫描缓存目录，只保留仍然存在的缓存文件的索引记录。
        """
        with self._lock:
            # Task 2.2修复：初始化backup_path避免UnboundLocalError
            backup_path = None

            try:
                # 备份旧索引（仅当文件存在时）
                if self.index_path.exists():
                    backup_path = self.index_path.with_suffix('.jsonl.bak')
                    self.index_path.rename(backup_path)
                    self.logger.debug(f"[CacheIndex] 已备份旧索引: {backup_path.name}")
                else:
                    self.logger.debug("[CacheIndex] 索引文件不存在，将创建新索引")

                # 扫描缓存文件，验证哪些记录仍有效
                valid_records = []
                for path_hash, record in self._index.items():
                    # 根据path_hash和strategy_id构造缓存文件名
                    strategy_id = record.get('strategy_id', 'S1')
                    target_format = record.get('target_format', 'jpeg')
                    ext = '.jpg' if target_format == 'jpeg' else f'.{target_format}'
                    cache_filename = f"{path_hash}_{strategy_id}{ext}"
                    cache_file = self.cache_dir / cache_filename

                    # 如果缓存文件存在，保留记录
                    if cache_file.exists():
                        valid_records.append(record)

                # 写入新索引文件
                with open(self.index_path, 'w', encoding='utf-8') as f:
                    for record in valid_records:
                        f.write(json.dumps(record, ensure_ascii=False) + '\n')

                # 更新内存索引
                self._index = {r['path_hash']: r for r in valid_records}

                self.logger.info(f"[CacheIndex] 重建索引完成: 保留{len(valid_records)}条有效记录")

                # 删除备份（仅当备份存在时）
                if backup_path and backup_path.exists():
                    backup_path.unlink()
                    self.logger.debug("[CacheIndex] 已删除备份文件")

            except Exception as e:
                self.logger.error(f"[CacheIndex] 重建索引失败: {e}")
                # 恢复备份（仅当备份存在时）
                if backup_path and backup_path.exists():
                    backup_path.rename(self.index_path)
                    self._load_index()
                    self.logger.info("[CacheIndex] 已从备份恢复索引")

    def get_statistics(self) -> Dict:
        """
        获取索引统计信息

        Returns:
            dict: 统计信息，包括总记录数、策略分布等
        """
        with self._lock:
            strategy_counts = {}
            format_counts = {}
            total_cache_size = 0

            for record in self._index.values():
                # 策略分布
                strategy_id = record.get('strategy_id', 'unknown')
                strategy_counts[strategy_id] = strategy_counts.get(strategy_id, 0) + 1

                # 格式分布
                target_format = record.get('target_format', 'unknown')
                format_counts[target_format] = format_counts.get(target_format, 0) + 1

                # 总大小
                total_cache_size += record.get('cache_size', 0)

            return {
                'total_entries': len(self._index),
                'strategy_distribution': strategy_counts,
                'format_distribution': format_counts,
                'total_cache_size_gb': total_cache_size / (1024**3)
            }
