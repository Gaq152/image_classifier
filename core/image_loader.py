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


class HighPerformanceImageLoader(QThread):
    """超高性能图像加载器，专门针对大图片和网络路径优化"""
    image_loaded = pyqtSignal(str, object)  # 发送原始图片数据（numpy array 或 PIL Image）
    thumbnail_loaded = pyqtSignal(str, object)  # 发送原始缩略图数据
    loading_progress = pyqtSignal(str)
    cache_status = pyqtSignal(dict)
    
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
        
        # 初始化日志器（需要在_init_smb_optimization之前）
        self.logger = logging.getLogger(__name__)
        
        # 初始化SMB优化
        self._init_smb_optimization()
        
        # 多线程优化 - 自适应线程池配置
        self.thread_pool = self._create_adaptive_thread_pool()
        
        # 初始化图片加载器 - 网络路径优化策略
        self.use_opencv = True  # 网络路径下OpenCV性能更好
        
        # 动态内存管理
        self.max_cache_memory = self._get_optimal_cache_size()
        self.current_cache_memory = 0
        self.cache_hit_count = 0
        self.cache_miss_count = 0
        
        # 性能监控
        self.load_times = []  # 加载时间记录
        self.concurrent_loads = 0  # 当前并发加载数
        self.concurrent_lock = threading.Lock()  # 并发计数器线程锁
        
        # 资源清理定时器 - 防止内存泄漏
        self.cleanup_timer = QTimer()
        self.cleanup_timer.timeout.connect(self._periodic_resource_cleanup)
        self.cleanup_timer.start(30000)  # 每30秒清理一次
    
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
    
    def _cleanup_local_cache(self):
        """清理本地缓存"""
        try:
            cache_dir = self.smb_optimization['cache_dir']
            if not cache_dir.exists():
                return
                
            # 计算缓存大小
            total_size = 0
            cache_files = []
            
            for cache_file in cache_dir.rglob('*'):
                if cache_file.is_file():
                    try:
                        size = cache_file.stat().st_size
                        mtime = cache_file.stat().st_mtime
                        total_size += size
                        cache_files.append((cache_file, size, mtime))
                    except:
                        continue
            
            total_size_gb = total_size / (1024**3)
            max_size_gb = self.smb_optimization['cache_max_size_gb']

            self.logger.debug(f"[SMB缓存] 当前大小: {total_size_gb:.2f}GB, 上限: {max_size_gb}GB")
            
            # 如果超过限制，删除最旧的文件
            if total_size_gb > max_size_gb:
                # 按修改时间排序，删除最旧的
                cache_files.sort(key=lambda x: x[2])  # 按mtime排序
                
                removed_size = 0
                target_remove_size = (total_size_gb - max_size_gb * 0.8) * (1024**3)  # 清理到80%
                
                for cache_file, size, mtime in cache_files:
                    if removed_size >= target_remove_size:
                        break
                    try:
                        cache_file.unlink()
                        removed_size += size
                    except:
                        continue
                
                self.logger.info(f"[SMB缓存] 清理完成，释放 {removed_size / (1024**3):.2f}GB")
            
        except Exception as e:
            self.logger.warning(f"[SMB缓存] 清理失败: {e}")
    
    def _get_local_cache_path(self, image_path):
        """获取本地缓存文件路径"""
        if not self.smb_optimization['enable_local_cache']:
            return None
            
        try:
            # 使用文件路径的hash作为缓存文件名
            path_hash = hashlib.md5(str(image_path).encode()).hexdigest()
            
            # 保留原始扩展名
            original_ext = Path(image_path).suffix.lower()
            cache_filename = f"{path_hash}{original_ext}"
            
            cache_dir = self.smb_optimization['cache_dir']
            return cache_dir / cache_filename
            
        except Exception as e:
            self.logger.debug(f"[SMB缓存] 获取缓存路径失败: {e}")
            return None
    
    def _load_from_local_cache(self, image_path):
        """从本地缓存加载图片"""
        cache_path = self._get_local_cache_path(image_path)
        if not cache_path or not cache_path.exists():
            return None
            
        try:
            # 检查缓存是否比原文件新
            original_mtime = Path(image_path).stat().st_mtime
            cache_mtime = cache_path.stat().st_mtime
            
            # 如果原文件更新了，删除缓存
            if original_mtime > cache_mtime:
                cache_path.unlink()
                return None
            
            # 从缓存加载
            pixmap = self._load_with_opencv(str(cache_path))
            if self._is_valid_pixmap(pixmap):
                self.logger.info(f"[SMB缓存] 命中本地缓存: {Path(image_path).name}")
                return pixmap
                
        except Exception as e:
            self.logger.debug(f"[SMB缓存] 加载失败: {e}")
            # 删除损坏的缓存文件
            try:
                if cache_path and cache_path.exists():
                    cache_path.unlink()
            except:
                pass
        
        return None
    
    def _save_to_local_cache(self, image_path, image_data):
        """保存图片到本地缓存"""
        if not self.smb_optimization['enable_local_cache']:
            return
            
        cache_path = self._get_local_cache_path(image_path)
        if not cache_path:
            return
            
        try:
            # 确保缓存目录存在
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 保存图片数据
            if isinstance(image_data, bytes):
                with open(cache_path, 'wb') as f:
                    f.write(image_data)
            else:
                # 如果是PIL Image或其他格式，先转换
                if hasattr(image_data, 'save'):
                    image_data.save(cache_path, quality=95, optimize=True)
                else:
                    return  # 不支持的格式
            
            self.logger.debug(f"[SMB缓存] 已缓存: {Path(image_path).name}")
            
        except Exception as e:
            self.logger.debug(f"[SMB缓存] 保存失败: {e}")
    
    @performance_monitor  
    def _load_with_opencv(self, image_path):
        """使用OpenCV加载图片（快速且稳定）"""
        try:
            # 使用imdecode支持中文路径
            img_array_file = np.fromfile(image_path, dtype=np.uint8)
            img = cv2.imdecode(img_array_file, cv2.IMREAD_COLOR)
            
            # 正确检查OpenCV解码结果：既要检查None，也要检查空数组
            if img is None or img.size == 0:
                raise ImageLoadError("无法读取图片")
            
            # OpenCV默认是BGR，转换为RGB
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            
            # 对于大图片，进行智能缩放（网络路径更激进）
            height, width = img.shape[:2]
            is_network = is_network_path(image_path)
            max_size = 1536 if is_network else 4096  # 网络路径进一步减小尺寸，提高加载速度
            
            if max(height, width) > max_size:
                scale = max_size / max(height, width)
                new_width = int(width * scale)
                new_height = int(height * scale)
                # 网络路径使用更快的插值算法
                interpolation = cv2.INTER_LINEAR if is_network else cv2.INTER_AREA
                img = cv2.resize(img, (new_width, new_height), interpolation=interpolation)
                self.logger.info(f"[OpenCV缩放] {'网络' if is_network else '本地'}大图片: {width}x{height} -> {new_width}x{new_height}")
            
            return img  # 返回numpy array
            
        except Exception as e:
            self.logger.error(f"[OpenCV加载失败] {Path(image_path).name}: {e}")
            raise ImageLoadError(f"OpenCV加载失败: {e}")
    
    def _load_with_pil_optimized(self, image_path):
        """使用PIL优化加载（支持更多格式）"""
        try:
            # 网络路径的大图片性能优化：避免使用draft模式
            is_network = is_network_path(image_path)
            
            with Image.open(image_path) as pil_img:
                # 获取原始尺寸
                original_size = pil_img.size
                
                # 对于网络路径的大图片，使用直接resize而非draft模式
                if is_network and max(original_size) > 3000:
                    # 网络大图片：直接resize到合适尺寸，比draft模式更快更稳定
                    max_size = 2048
                    scale = max_size / max(original_size)
                    new_size = (int(original_size[0] * scale), int(original_size[1] * scale))
                    
                    # 确保是RGB模式
                    if pil_img.mode != 'RGB':
                        pil_img = pil_img.convert('RGB')
                    
                    # 直接resize，避免draft模式的性能问题
                    pil_img = pil_img.resize(new_size, Image.Resampling.LANCZOS)
                    self.logger.info(f"网络大图片直接缩放: {original_size} -> {new_size}")
                    
                elif max(original_size) > 4000:  # 本地大图片仍使用draft
                    pil_img.draft('RGB', (2048, 2048))
                    self.logger.info(f"本地大图片使用draft模式: {original_size} -> {pil_img.size}")
                
                # 确保是RGB模式
                if pil_img.mode != 'RGB':
                    pil_img = pil_img.convert('RGB')
                
                # 转换为numpy数组（比直接转QImage快）
                img_array = np.array(pil_img)
                
                # 转换为QImage - 处理不同维度的图像
                if len(img_array.shape) == 2:  # 灰度图像
                    height, width = img_array.shape
                    # 将灰度图像转换为RGB
                    img_array = np.stack([img_array] * 3, axis=-1)
                elif len(img_array.shape) == 3:
                    height, width = img_array.shape[:2]
                    # 确保是3通道
                    if img_array.shape[2] == 4:  # RGBA
                        img_array = img_array[:, :, :3]
                    elif img_array.shape[2] != 3:
                        raise ValueError(f"不支持的通道数: {img_array.shape[2]}")
                else:
                    raise ValueError(f"不支持的图像形状: {img_array.shape}")
                    
                # 线程安全：返回numpy数组而非QPixmap
                return img_array
                
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
        """智能图片加载调度 - 使用线程池并行加载"""
        try:
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
                else:
                    # 低优先级任务：只在并发数严重超标时才跳过
                    if current_concurrent >= max_concurrent * 1.5:
                        self.logger.debug(f"[并发控制] 跳过低优先级任务，当前并发:{current_concurrent}/{max_concurrent}")
                        return
                    else:
                        # 轻度超标时仍然执行，只记录信息
                        self.logger.debug(f"[并发控制] 低优先级任务继续执行，当前并发:{current_concurrent}/{max_concurrent}")
            
            with self.concurrent_lock:
                self.concurrent_loads += 1
            
            # 检查线程池状态，避免在关闭后提交任务
            if not self.running or not hasattr(self, 'thread_pool') or self.thread_pool._shutdown:
                self.logger.debug(f"[并行加载] 线程池已关闭，跳过任务: {Path(image_path).name}")
                with self.concurrent_lock:
                    self.concurrent_loads -= 1  # 恢复计数器
                return
            
            # 使用线程池并行加载
            if priority:
                self.current_task = image_path
                future = self.thread_pool.submit(self._load_image_worker, image_path, True)
                future.add_done_callback(lambda f: self._on_load_complete(image_path, f))
            else:
                future = self.thread_pool.submit(self._load_image_worker, image_path, False)
                future.add_done_callback(lambda f: self._on_load_complete(image_path, f))
                
        except Exception as e:
            # 修复：只有在成功增加计数器后才减少，线程安全
            with self.concurrent_lock:
                self.concurrent_loads = max(0, self.concurrent_loads - 1)
            self.logger.error(f"[并行加载] 提交加载任务失败，重置并发计数器: {e}")
            raise ImageLoadError(f"提交加载任务失败: {e}")
    
    def _load_image_worker(self, image_path, is_priority):
        """线程池工作函数"""
        load_start = time.time()
        try:
            cache_key = self._get_cache_key(image_path)
            
            # 检查缓存
            cached_pixmap = self._get_from_cache(cache_key)
            if self._is_valid_pixmap(cached_pixmap):
                load_time = (time.time() - load_start) * 1000
                self.logger.debug(f"[并行加载-缓存命中] {Path(image_path).name} 耗时:{load_time:.1f}ms")
                return {'image_data': cached_pixmap, 'cached': True, 'load_time': load_time}
            
            # 根据文件大小和环境选择加载策略
            file_size = Path(image_path).stat().st_size
            file_size_mb = file_size / 1024 / 1024
            
            # 使用OpenCV或PIL加载
            if self.use_opencv and cv2 is not None:
                try:
                    pixmap = self._load_with_opencv(image_path)
                except ImageLoadError:
                    # OpenCV失败时回退到PIL
                    if PIL_AVAILABLE:
                        pixmap = self._load_with_pil_optimized(image_path)
                    else:
                        raise
            else:
                if PIL_AVAILABLE:
                    pixmap = self._load_with_pil_optimized(image_path)
                else:
                    raise ImageLoadError("没有可用的图像加载库")
            
            # 检查加载结果
            if self._is_valid_pixmap(pixmap):
                # 缓存原始数据
                self._update_cache(cache_key, pixmap)
                load_time = (time.time() - load_start) * 1000
                    
                # 记录性能统计
                self.load_times.append(load_time)
                if len(self.load_times) > 100:
                    self.load_times = self.load_times[-100:]
                    
                avg_load_time = sum(self.load_times) / len(self.load_times)

                self.logger.debug(f"[并行加载-成功] {Path(image_path).name} {file_size_mb:.1f}MB "
                               f"耗时:{load_time:.1f}ms 平均:{avg_load_time:.1f}ms 优先级:{is_priority}")

                return {'image_data': pixmap, 'cached': False, 'load_time': load_time}
            else:
                raise ImageLoadError("图片加载失败")
                
        except Exception as e:
            load_time = (time.time() - load_start) * 1000
            self.logger.error(f"[并行加载-失败] {Path(image_path).name} 耗时:{load_time:.1f}ms 错误:{e}")
            return {'image_data': None, 'error': str(e), 'load_time': load_time}
    
    def _on_load_complete(self, image_path, future):
        """加载完成回调"""
        # 先减少并发计数，避免重复减少，线程安全
        with self.concurrent_lock:
            self.concurrent_loads = max(0, self.concurrent_loads - 1)
        
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
    
    def clear_cache(self):
        """清理缓存"""
        with self.concurrent_lock:
            self.cache.clear()
            self.thumbnail_cache.clear()
            self.cache_hit_count = 0
            self.cache_miss_count = 0
        
    def _periodic_resource_cleanup(self):
        """定期资源清理"""
        try:
            # 清理过期缓存
            if len(self.cache) > self.cache_size * 0.8:
                self._gentle_cache_cleanup()
                
            # 清理本地SMB缓存
            if self.smb_optimization['enable_local_cache']:
                self._cleanup_local_cache()
                
        except Exception as e:
            self.logger.debug(f"定期资源清理失败: {e}")
    
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
        
    def stop(self):
        """停止加载器"""
        self.running = False
        if hasattr(self, 'thread_pool'):
            self.thread_pool.shutdown(wait=True)
        if hasattr(self, 'cleanup_timer'):
            self.cleanup_timer.stop()
        self.wait()


class ImageProcessingManager:
    """图片处理管理器 - 统一管理图片加载、缓存、转换等功能"""
    
    def __init__(self, cache_size=30):
        self.image_loader = HighPerformanceImageLoader(cache_size)
        self.logger = logging.getLogger(__name__)
        
    def setup_loader_connections(self, image_loaded_callback, thumbnail_loaded_callback, 
                                progress_callback, cache_status_callback):
        """设置加载器回调连接"""
        try:
            self.image_loader.image_loaded.connect(image_loaded_callback)
            self.image_loader.thumbnail_loaded.connect(thumbnail_loaded_callback)
            self.image_loader.loading_progress.connect(progress_callback)
            self.image_loader.cache_status.connect(cache_status_callback)
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
