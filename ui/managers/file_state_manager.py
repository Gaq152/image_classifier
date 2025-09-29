"""
文件状态管理器

负责管理图片文件的状态同步，包括分类状态检查、
新分类检测、删除文件同步等功能。
"""

import logging
from pathlib import Path
from typing import Dict, List, Any, Set


class FileStateManager:
    """文件状态管理器"""

    def __init__(self, current_dir: Path, categories: List[str],
                 classified_images: Dict[str, Any], removed_images: Set[str]):
        """
        初始化文件状态管理器

        Args:
            current_dir: 当前工作目录
            categories: 分类列表
            classified_images: 已分类图片字典
            removed_images: 已删除图片集合
        """
        self.current_dir = current_dir
        self.categories = categories
        self.classified_images = classified_images
        self.removed_images = removed_images
        self.logger = logging.getLogger(__name__)

    def sync_classified_files(self, sync_results: Dict[str, Any]) -> None:
        """检查已分类图片的状态"""
        parent_dir = self.current_dir.parent
        invalid_classifications = []

        for img_path, category in list(self.classified_images.items()):
            img_file = Path(img_path)

            # 处理多分类模式（category可能是列表）
            if isinstance(category, list):
                # 多分类模式：检查每个类别
                categories_to_remove = []
                for cat in category:
                    category_dir = parent_dir / cat
                    expected_file = category_dir / img_file.name

                    # 检查文件是否还在预期的分类目录中
                    if not expected_file.exists():
                        categories_to_remove.append(cat)
                        sync_results['moved_files'].append({
                            'file': img_file.name,
                            'from': cat,
                            'to': '已移动或删除'
                        })

                # 移除不存在的类别
                if categories_to_remove:
                    for cat in categories_to_remove:
                        category.remove(cat)

                    # 如果所有类别都被移除，则移除整个分类记录
                    if not category:
                        invalid_classifications.append(img_path)
            else:
                # 单分类模式
                category_dir = parent_dir / category
                expected_file = category_dir / img_file.name

                # 检查文件是否还在预期的分类目录中
                if not expected_file.exists():
                    # 检查文件是否回到了原目录
                    original_file = self.current_dir / img_file.name
                    if original_file.exists():
                        # 文件被移回原目录
                        invalid_classifications.append(img_path)
                        sync_results['moved_files'].append({
                            'file': img_file.name,
                            'from': category,
                            'to': '原目录'
                        })
                    else:
                        # 文件被删除或移动到其他地方
                        invalid_classifications.append(img_path)
                        sync_results['removed_files'].append({
                            'file': img_file.name,
                            'category': category
                        })

        # 移除无效的分类记录
        for img_path in invalid_classifications:
            del self.classified_images[img_path]
            sync_results['invalid_classifications'].append(img_path)

    def detect_new_classifications(self, sync_results: Dict[str, Any]) -> None:
        """检查分类目录中是否有新图片"""
        parent_dir = self.current_dir.parent

        for category in self.categories:
            category_dir = parent_dir / category
            if category_dir.exists():
                for file_path in category_dir.iterdir():
                    if (file_path.is_file() and
                        file_path.suffix.lower() in ['.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff']):

                        # 查找对应的原图片路径
                        original_path = str(self.current_dir / file_path.name)

                        # 如果这个文件没有分类记录，添加记录
                        if original_path not in self.classified_images:
                            self.classified_images[original_path] = category
                            sync_results['new_classifications'].append({
                                'file': file_path.name,
                                'category': category
                            })

    def sync_removed_files(self, sync_results: Dict[str, Any]) -> None:
        """更新已移除图片状态"""
        parent_dir = self.current_dir.parent
        removed_files = []

        for img_path in list(self.removed_images):
            img_file = Path(img_path)
            remove_dir = parent_dir / 'remove'
            expected_file = remove_dir / img_file.name

            # 检查文件是否还在remove目录中
            if not expected_file.exists():
                # 检查文件是否回到了原目录
                original_file = self.current_dir / img_file.name
                if original_file.exists():
                    removed_files.append(img_path)
                    sync_results['moved_files'].append({
                        'file': img_file.name,
                        'from': 'remove',
                        'to': '原目录'
                    })

        # 移除无效的删除记录
        for img_path in removed_files:
            self.removed_images.discard(img_path)

    def generate_sync_results(self, sync_results: Dict[str, Any]) -> None:
        """生成最终同步结果"""
        sync_results['changes_detected'] = (
            len(sync_results['removed_files']) > 0 or
            len(sync_results['moved_files']) > 0 or
            len(sync_results['new_classifications']) > 0 or
            len(sync_results['invalid_classifications']) > 0
        )

    def sync_file_states(self) -> Dict[str, Any]:
        """同步文件状态与实际目录"""
        sync_results = {
            'changes_detected': False,
            'removed_files': [],
            'moved_files': [],
            'new_classifications': [],
            'invalid_classifications': []
        }

        try:
            # 检查已分类图片的状态
            self.sync_classified_files(sync_results)

            # 检查分类目录中是否有新图片
            self.detect_new_classifications(sync_results)

            # 更新已移除图片状态
            self.sync_removed_files(sync_results)

            # 生成最终同步结果
            self.generate_sync_results(sync_results)

            return sync_results

        except Exception as e:
            self.logger.error(f"同步文件状态时发生错误: {e}")
            sync_results['changes_detected'] = False
            return sync_results