"""
文件管理器模块

提供文件操作、同步和管理功能，包括文件移动、复制、同步等操作。
"""

import os
import logging
import shutil
import threading
from pathlib import Path
from PyQt6.QtCore import QThread, pyqtSignal
from utils.exceptions import FileOperationError, SyncError
from utils.file_operations import retry_file_operation, is_network_path
from utils.performance import performance_monitor


class FileSyncThread(QThread):
    """后台文件同步线程，处理分类状态同步"""
    sync_progress = pyqtSignal(str)  # 同步进度信号
    sync_completed = pyqtSignal(dict)  # 同步完成信号
    
    def __init__(self):
        super().__init__()
        self.current_dir = None
        self.categories = set()
        self.classified_images = {}
        self.removed_images = set()
        self.running = True
        self.quick_mode = False
        self.logger = logging.getLogger(__name__)
        self._lock = threading.Lock()
        
    def sync_classification(self, current_dir, categories, classified_images, removed_images, quick_mode=False):
        """开始同步分类状态"""
        with self._lock:
            self.current_dir = Path(current_dir)
            self.categories = categories.copy()
            self.classified_images = classified_images.copy()
            self.removed_images = removed_images.copy()
            self.quick_mode = quick_mode
        
        if not self.isRunning():
            self.start()
            
    @performance_monitor
    def run(self):
        """执行文件同步"""
        if not self.current_dir:
            return
            
        try:
            self.sync_progress.emit("开始同步文件分类状态...")
            self.logger.info("开始后台文件分类同步...")
            
            # 1. 收集所有实际存在的图片文件信息
            actual_files = {}  # {file_path: {'category': str, 'name': str, 'size': int}}
            file_name_map = {}  # {file_name: [file_paths]} 用于快速查找
            duplicate_names = []  # 重复文件名列表
            
            self.sync_progress.emit("扫描原图片目录...")
            
            # 扫描原图片目录中未分类的文件
            for ext in ('*.jpg', '*.jpeg', '*.png', '*.bmp'):
                for img_file in self.current_dir.glob(ext):
                    if not self.running:
                        return
                        
                    if img_file.exists():
                        file_path = str(img_file)
                        try:
                            file_size = img_file.stat().st_size
                            actual_files[file_path] = {
                                'category': None,  # 未分类
                                'name': img_file.name,
                                'path': file_path,
                                'size': file_size
                            }
                            if img_file.name not in file_name_map:
                                file_name_map[img_file.name] = []
                            file_name_map[img_file.name].append(file_path)
                        except Exception as e:
                            self.logger.error(f"获取文件信息失败 {file_path}: {str(e)}")
                            continue
            
            # 扫描所有类别目录
            for i, category in enumerate(self.categories):
                if not self.running:
                    return
                    
                self.sync_progress.emit(f"扫描类别目录: {category} ({i+1}/{len(self.categories)})")
                
                category_dir = self.current_dir.parent / category
                if category_dir.exists():
                    for ext in ('*.jpg', '*.jpeg', '*.png', '*.bmp'):
                        for img_file in category_dir.glob(ext):
                            if not self.running:
                                return
                                
                            file_path = str(img_file)
                            try:
                                file_size = img_file.stat().st_size
                                actual_files[file_path] = {
                                    'category': category,
                                    'name': img_file.name,
                                    'path': file_path,
                                    'size': file_size
                                }
                                if img_file.name not in file_name_map:
                                    file_name_map[img_file.name] = []
                                file_name_map[img_file.name].append(file_path)
                            except Exception as e:
                                self.logger.error(f"获取文件信息失败 {file_path}: {str(e)}")
                                continue
            
            # 扫描移出目录
            self.sync_progress.emit("扫描移出目录...")
            remove_dir = self.current_dir.parent / 'remove'
            if remove_dir and remove_dir.exists():
                for ext in ('*.jpg', '*.jpeg', '*.png', '*.bmp'):
                    for img_file in remove_dir.glob(ext):
                        if not self.running:
                            return
                            
                        file_path = str(img_file)
                        try:
                            file_size = img_file.stat().st_size
                            actual_files[file_path] = {
                                'category': 'remove',
                                'name': img_file.name,
                                'path': file_path,
                                'size': file_size
                            }
                            if img_file.name not in file_name_map:
                                file_name_map[img_file.name] = []
                            file_name_map[img_file.name].append(file_path)
                        except Exception as e:
                            self.logger.error(f"获取文件信息失败 {file_path}: {str(e)}")
                            continue
            
            if not self.running:
                return
                
            self.sync_progress.emit("分析文件状态...")
            
            # 2. 检测重复文件名和状态变化
            duplicates = {}
            new_classified_images = {}
            new_removed_images = set()
            invalid_records = []
            new_discoveries = []
            
            # 处理重复文件
            for file_name, paths in file_name_map.items():
                if len(paths) > 1:
                    classified_paths = []
                    categories_found = set()
                    
                    for path in paths:
                        if str(self.current_dir) in path and actual_files[path]['category'] is None:
                            continue  # 跳过基础目录中的原始文件
                            
                        classified_paths.append(path)
                        category = actual_files[path]['category']
                        if category:
                            categories_found.add(category)
                    
                    if len(classified_paths) > 1 and len(categories_found) > 1:
                        duplicates[file_name] = classified_paths
            
            # 更新分类记录
            for original_path, category in list(self.classified_images.items()):
                if not self.running:
                    return
                    
                original_name = Path(original_path).name
                
                # 查找文件当前位置
                current_location = None
                current_category = None
                
                for file_path, file_info in actual_files.items():
                    if file_info['name'] == original_name:
                        current_location = file_path
                        current_category = file_info['category']
                        break
                
                if current_location:
                    if current_category == 'remove':
                        new_removed_images.add(original_path)
                        invalid_records.append((original_path, category, '文件已移出'))
                    elif current_category and current_category != category:
                        new_classified_images[original_path] = current_category
                        self.logger.info(f"文件类别变更: {original_name} {category} -> {current_category}")
                    else:
                        new_classified_images[original_path] = category
                else:
                    invalid_records.append((original_path, category, '文件已删除'))
            
            # 处理移出记录
            for original_path in list(self.removed_images):
                if not self.running:
                    return
                    
                original_name = Path(original_path).name
                
                current_location = None
                current_category = None
                
                for file_path, file_info in actual_files.items():
                    if file_info['name'] == original_name:
                        current_location = file_path
                        current_category = file_info['category']
                        break
                
                if current_location:
                    if current_category == 'remove':
                        new_removed_images.add(original_path)
                    elif current_category:
                        new_classified_images[original_path] = current_category
                        self.logger.info(f"文件从移出状态恢复: {original_name} -> {current_category}")
                else:
                    invalid_records.append((original_path, 'remove', '文件已删除'))
            
            # 发现新分类的文件
            for file_path, file_info in actual_files.items():
                if not self.running:
                    return
                    
                if file_info['category'] and file_info['category'] != 'remove':
                    original_path = str(self.current_dir / file_info['name'])
                    
                    if (original_path not in new_classified_images and 
                        original_path not in self.classified_images):
                        new_classified_images[original_path] = file_info['category']
                        new_discoveries.append((file_info['name'], file_info['category']))
            
            # 发现新移出的文件
            for file_path, file_info in actual_files.items():
                if not self.running:
                    return
                    
                if file_info['category'] == 'remove':
                    original_path = str(self.current_dir / file_info['name'])
                    
                    if (original_path not in new_removed_images and 
                        original_path not in new_classified_images and 
                        original_path not in self.removed_images):
                        new_removed_images.add(original_path)
                        new_discoveries.append((file_info['name'], 'remove'))
            
            if not self.running:
                return
                
            self.sync_progress.emit("同步完成，准备结果...")
            
            # 生成同步结果
            sync_result = {
                'classified_images': new_classified_images,
                'removed_images': new_removed_images,
                'invalid_records': len(invalid_records),
                'new_discoveries': len(new_discoveries),
                'duplicates': len(duplicates),
                'sync_report': [],
                'has_more': False
            }
            
            # 生成报告
            if invalid_records:
                sync_result['sync_report'].append(f"清理了 {len(invalid_records)} 条无效记录")
            if new_discoveries:
                classified_discoveries = [d for d in new_discoveries if d[1] != 'remove']
                removed_discoveries = [d for d in new_discoveries if d[1] == 'remove']
                
                if classified_discoveries:
                    sync_result['sync_report'].append(f"发现 {len(classified_discoveries)} 个新分类文件")
                if removed_discoveries:
                    sync_result['sync_report'].append(f"发现 {len(removed_discoveries)} 个新移出文件")
            if duplicates:
                sync_result['sync_report'].append(f"检测到 {len(duplicates)} 组重复文件")
            
            self.logger.info("后台文件同步完成")
            self.sync_completed.emit(sync_result)
            
        except Exception as e:
            self.logger.error(f"后台文件同步失败: {str(e)}")
            error_result = {
                'error': str(e),
                'classified_images': {},
                'removed_images': set(),
                'invalid_records': 0,
                'new_discoveries': 0,
                'duplicates': 0
            }
            self.sync_completed.emit(error_result)
            raise SyncError(f"文件同步失败: {e}")
            
    def stop(self):
        """停止同步"""
        self.running = False
        self.wait()


class FileOperationManager:
    """文件操作管理器 - 统一管理文件移动、复制、同步等操作"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.file_sync = FileSyncThread()
        self._lock = threading.Lock()
        
    def setup_sync_connections(self, progress_callback, completed_callback):
        """设置文件同步回调连接"""
        try:
            self.file_sync.sync_progress.connect(progress_callback)
            self.file_sync.sync_completed.connect(completed_callback)
        except Exception as e:
            raise FileOperationError(f"设置同步连接失败: {e}")
        
    def start_background_sync(self, current_dir, categories, classified_images, removed_images, quick_mode=False):
        """启动后台文件同步"""
        with self._lock:
            if not self.file_sync.isRunning():
                try:
                    self.file_sync.sync_classification(current_dir, categories, classified_images, removed_images, quick_mode)
                except Exception as e:
                    raise FileOperationError(f"启动后台同步失败: {e}")
        
    def execute_file_operation(self, operation_func, max_retries=3):
        """执行文件操作（带重试机制）"""
        try:
            return retry_file_operation(operation_func, max_retries)
        except Exception as e:
            raise FileOperationError(f"文件操作执行失败: {e}")
        
    def is_network_path(self, path):
        """检查是否为网络路径"""
        return is_network_path(path)
    
    def move_file(self, src_path, dst_path):
        """移动文件"""
        def move_operation():
            shutil.move(str(src_path), str(dst_path))
            
        return self.execute_file_operation(move_operation)
    
    def copy_file(self, src_path, dst_path):
        """复制文件"""
        def copy_operation():
            shutil.copy2(str(src_path), str(dst_path))
            
        return self.execute_file_operation(copy_operation)
    
    def delete_file(self, file_path):
        """删除文件"""
        def delete_operation():
            os.remove(str(file_path))
            
        return self.execute_file_operation(delete_operation)
    
    def create_directory(self, dir_path):
        """创建目录"""
        def create_operation():
            Path(dir_path).mkdir(parents=True, exist_ok=True)
            
        return self.execute_file_operation(create_operation)
    
    def stop_sync(self):
        """停止文件同步"""
        if self.file_sync.isRunning():
            self.file_sync.stop()
