"""
文件扫描器模块

提供目录文件的智能扫描功能，支持分批加载和网络路径优化。
"""

import os
import logging
import time
from pathlib import Path
from PyQt6.QtCore import QThread, pyqtSignal
from utils.exceptions import DirectoryScanError
from utils.performance import performance_monitor


class FileScannerThread(QThread):
    """文件扫描线程 - 智能分批扫描策略"""
    initial_batch_ready = pyqtSignal(list)  # 初始批次准备就绪
    files_found = pyqtSignal(list)  # 发现新的文件批次
    scan_progress = pyqtSignal(str)  # 扫描进度
    scan_finished = pyqtSignal(int)  # 扫描完成，传递总文件数
    
    def __init__(self):
        super().__init__()
        self.current_dir = None
        self.cancelled = False
        self.image_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', '.webp'}
        self.logger = logging.getLogger(__name__)
        
    def scan_directory(self, directory):
        """开始扫描目录"""
        try:
            # 修复：如果线程已在运行，先等待完成
            if self.isRunning():
                self.logger.warning("扫描线程已在运行，取消当前扫描并等待完成")
                self.cancel_scan()
                self.wait(2000)  # 等待最多2秒
                if self.isRunning():
                    self.logger.error("无法终止正在运行的扫描线程")
                    raise DirectoryScanError("扫描线程已在运行，无法启动新扫描")

            self.current_dir = Path(directory)
            self.cancelled = False
            self.start()
        except Exception as e:
            raise DirectoryScanError(f"开始扫描目录失败: {e}")
        
    def cancel_scan(self):
        """取消扫描"""
        self.cancelled = True
        
    def _is_network_path(self, path):
        """检查是否为网络路径"""
        return str(path).startswith('\\\\')
        
    @performance_monitor
    def _quick_scan_for_initial_batch(self, directory, target_count=100):
        """快速扫描获取初始批次文件（用于立即显示）"""
        files = []
        # 针对网络路径大幅减少初始批次，提高响应速度
        is_network = self._is_network_path(directory)
        if is_network:
            actual_target = min(10, target_count)  # 网络路径只取10张，极速响应
        else:
            actual_target = min(30, target_count)  # 本地路径取30张，平衡响应性和展示效果
        
        try:
            # 优先扫描根目录
            for file_path in directory.iterdir():
                if self.cancelled:
                    break
                    
                if file_path.is_file() and file_path.suffix.lower() in self.image_extensions:
                    files.append(file_path)
                    if len(files) >= actual_target:
                        break
            
            # 网络路径优化：如果已有文件就立即返回，不继续扫描子目录
            if is_network and len(files) > 0:
                self.logger.info(f"[快速扫描] 网络路径获得{len(files)}张图片，立即返回避免延迟")
                return self._smart_sort_files(files)[:actual_target]
            
            # 如果根目录文件不够，扫描子目录（本地路径或网络路径无文件时）
            if len(files) < actual_target and not self.cancelled:
                scan_count = 0  # 限制扫描的子目录数量
                max_scan_dirs = 5 if is_network else 20  # 网络路径限制扫描目录数
                
                for root in directory.rglob('*'):
                    if self.cancelled:
                        break
                    
                    # 网络路径限制扫描深度，避免长时间等待
                    if is_network:
                        scan_count += 1
                        if scan_count > max_scan_dirs:
                            self.logger.info(f"[快速扫描] 网络路径已扫描{max_scan_dirs}个子目录，停止扫描")
                            break
                        
                    if root.is_file() and root.suffix.lower() in self.image_extensions:
                        files.append(root)
                        if len(files) >= actual_target:
                            break
                            
            # 智能排序：优先显示可能的图片
            sorted_files = self._smart_sort_files(files)
            return sorted_files[:actual_target]
            
        except Exception as e:
            self.logger.error(f"快速扫描失败: {e}")
            raise DirectoryScanError(f"快速扫描失败: {e}")
            
    def _smart_sort_files(self, files):
        """智能排序文件：优先显示重要文件"""
        def sort_key(file_path):
            name = file_path.name.lower()
            # 优先级：jpg > png > 其他，按文件名排序
            ext_priority = {'jpg': 1, 'jpeg': 1, 'png': 2, 'bmp': 3}
            ext = file_path.suffix.lower().lstrip('.')
            priority = ext_priority.get(ext, 9)
            return (priority, name)
            
        return sorted(files, key=sort_key)
        
    @performance_monitor
    def run(self):
        """执行智能扫描"""
        if not self.current_dir or not self.current_dir.exists():
            self.scan_finished.emit(0)
            return
            
        try:
            is_network = self._is_network_path(self.current_dir)
            self.logger.info(f"开始智能扫描目录: {self.current_dir}")
            
            if is_network:
                self.logger.info("检测到网络路径，使用保守扫描策略")
            
            # 第一阶段：快速获取目录项统计（网络路径跳过统计避免延迟）
            if is_network:
                self.logger.info("检测到网络路径，跳过目录统计直接开始扫描")
                self.scan_progress.emit("网络路径快速扫描中...")
            else:
                self.scan_progress.emit("正在分析目录结构...")
                try:
                    total_items = sum(1 for _ in self.current_dir.iterdir())
                    self.logger.info(f"目录访问正常，共有 {total_items} 个项目")
                except Exception as e:
                    self.logger.error(f"目录访问失败: {e}")
                    self.scan_finished.emit(0)
                    return
                
            # 第二阶段：快速准备初始批次
            self.scan_progress.emit("正在准备初始批次文件...")
            initial_batch = self._quick_scan_for_initial_batch(self.current_dir, 100)
            
            if initial_batch and not self.cancelled:
                self.logger.info(f"初始批次准备完成: {len(initial_batch)} 个文件")
                self.initial_batch_ready.emit(initial_batch)
                
            # 第三阶段：全面扫描剩余文件
            if is_network:
                self.scan_progress.emit("网络路径后台扫描中...")
                self.logger.info("开始网络路径优化扫描...")
            else:
                self.scan_progress.emit("开始全面扫描...")
                self.logger.info("开始全面扫描...")
            
            all_files = []
            # 网络路径使用更大的批次减少频繁更新，本地路径保持响应性
            batch_size = 200 if is_network else 100
            current_batch = []
            initial_paths = {str(f) for f in initial_batch}  # 避免重复
            
            # 使用os.walk进行更快的文件扫描
            try:
                for root, dirs, files in os.walk(str(self.current_dir)):
                    if self.cancelled:
                        break
                    
                    # 过滤并处理图片文件
                    for filename in files:
                        if self.cancelled:
                            break
                            
                        # 快速检查扩展名
                        ext = os.path.splitext(filename)[1].lower()
                        if ext in self.image_extensions:
                            file_path = Path(root) / filename
                            
                            if str(file_path) not in initial_paths:  # 避免重复
                                all_files.append(file_path)
                                current_batch.append(file_path)
                                
                                # 批次发送
                                if len(current_batch) >= batch_size:
                                    self.files_found.emit(current_batch)
                                    current_batch = []
                    
                    # 每处理一个目录，让出CPU时间，避免阻塞
                    if len(dirs) > 0:
                        # 网络路径减少延迟频率，本地路径保持响应性
                        if is_network:
                            # 网络路径每处理5个目录才休眠一次，提高扫描速度
                            if len(all_files) % 50 == 0:  # 每扫描50个文件休眠一次
                                self.msleep(2)
                        else:
                            self.msleep(1)  # 本地路径保持原来的频率
                        
            except Exception as e:
                self.logger.error(f"扫描过程出错: {e}")
                raise DirectoryScanError(f"扫描过程出错: {e}")
            
            # 发送最后一批
            if current_batch and not self.cancelled:
                self.files_found.emit(current_batch)
            
            # 计算总数（包括初始批次）
            total_count = len(initial_batch) + len(all_files)
            
            if not self.cancelled:
                self.logger.info(f"文件扫描完成，总计 {total_count} 个图片文件")
                self.scan_finished.emit(total_count)
                
        except DirectoryScanError:
            raise
        except Exception as e:
            self.logger.error(f"文件扫描异常: {e}")
            raise DirectoryScanError(f"文件扫描异常: {e}")
