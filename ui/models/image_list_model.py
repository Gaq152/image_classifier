from typing import List, Dict, Optional, Any, Set
from collections import OrderedDict
from pathlib import Path

from PyQt6.QtCore import QAbstractListModel, Qt, QModelIndex
from PyQt6.QtGui import QIcon

class ImageItem:
    """
    轻量级图片数据对象
    使用 __slots__ 减少内存占用，每个对象约减少 60% 内存开销
    """
    __slots__ = ['path', 'index', 'status', 'is_removed', 'is_multi', 'thumbnail']

    def __init__(self, path: str, index: int, status: bool = False,
                 is_removed: bool = False, is_multi: bool = False):
        self.path = path
        self.index = index
        self.status = status          # True 表示已分类
        self.is_removed = is_removed  # True 表示已删除
        self.is_multi = is_multi      # True 表示多标签分类
        self.thumbnail: Optional[QIcon] = None

class ImageListModel(QAbstractListModel):
    """
    高性能图像列表模型
    支持 O(1) 状态更新和 LRU 缩略图缓存
    """

    # 自定义数据角色
    ROLE_IMAGE_INDEX = Qt.ItemDataRole.UserRole + 1  # 获取图片在原始列表中的索引
    ROLE_FULL_PATH = Qt.ItemDataRole.UserRole + 2    # 获取完整文件路径
    ROLE_STATUS_TYPE = Qt.ItemDataRole.UserRole + 3  # 获取状态字符串 (pending/classified/...)

    def __init__(self, image_files: List[str], classified_images: Dict[str, Any],
                 removed_images: Set[str], multi_classified: Set[str] = None, parent=None):
        """
        初始化模型

        Args:
            image_files: 图片路径列表
            classified_images: 已分类图片字典
            removed_images: 已删除图片集合
            multi_classified: 多分类图片集合
            parent: 父对象
        """
        super().__init__(parent)

        self._data: List[ImageItem] = []
        self._index_map: Dict[int, int] = {}      # image_index -> row 映射
        self._path_map: Dict[str, int] = {}       # path_str -> row 映射

        # 缩略图缓存 (LRU策略)
        self._thumbnail_lru = OrderedDict()
        self._thumbnail_cache_limit = 1000

        # 初始化数据
        self._init_data(image_files, classified_images, removed_images, multi_classified or set())

    def _init_data(self, image_files: List[str], classified_images: Dict[str, Any],
                   removed_images: Set[str], multi_classified: Set[str]):
        """初始化内部数据结构，构建快速查找映射"""
        self.beginResetModel()
        self._data.clear()
        self._index_map.clear()
        self._path_map.clear()
        self._thumbnail_lru.clear()

        for i, path in enumerate(image_files):
            is_classified = path in classified_images
            is_removed = path in removed_images
            is_multi = path in multi_classified

            item = ImageItem(str(path), i, is_classified, is_removed, is_multi)
            self._data.append(item)

            # 建立 O(1) 查找索引
            self._index_map[i] = i
            self._path_map[str(path)] = i

        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:
        """返回行数"""
        if parent.isValid():
            return 0
        return len(self._data)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        """
        获取数据
        注意：严禁在此触发 I/O 操作
        """
        if not index.isValid() or not (0 <= index.row() < len(self._data)):
            return None

        item = self._data[index.row()]

        if role == Qt.ItemDataRole.DisplayRole:
            return Path(item.path).name

        elif role == Qt.ItemDataRole.DecorationRole:
            # 返回缓存的缩略图，如果没有则返回 None
            # View/Delegate 收到 None 后会留空或显示占位，并触发异步加载
            return item.thumbnail

        elif role == self.ROLE_IMAGE_INDEX:
            return item.index

        elif role == self.ROLE_FULL_PATH:
            return item.path

        elif role == self.ROLE_STATUS_TYPE:
            # 聚合状态逻辑，返回给 Delegate 决定绘制哪个图标
            # 优先级：已分类 > 多分类 > 已删除 > 未处理（与旧版一致）
            if item.status:
                return "classified"
            elif item.is_multi:
                return "multi"
            elif item.is_removed:
                return "removed"
            else:
                return "pending"

        return None

    def update_status(self, image_index: int, is_classified: bool,
                      is_removed: bool, is_multi: bool):
        """
        O(1) 更新图片状态
        通过 index_map 快速定位行号
        """
        if image_index not in self._index_map:
            return

        row = self._index_map[image_index]
        # 边界检查：防止索引失步导致越界
        if row < 0 or row >= len(self._data):
            return

        item = self._data[row]

        # 检查状态是否真的改变，避免不必要的信号发射
        if (item.status != is_classified or
            item.is_removed != is_removed or
            item.is_multi != is_multi):

            item.status = is_classified
            item.is_removed = is_removed
            item.is_multi = is_multi

            idx = self.index(row, 0)
            # 仅通知状态角色改变，触发 Delegate 重绘
            self.dataChanged.emit(idx, idx, [self.ROLE_STATUS_TYPE])

    def set_thumbnail(self, path, icon: QIcon):
        """
        更新缩略图并管理 LRU 缓存
        当异步加载器完成加载后调用此方法
        """
        # 标准化路径为字符串（兼容Path对象）
        path_str = str(path)

        if path_str not in self._path_map:
            return

        row = self._path_map[path_str]
        item = self._data[row]

        # 更新 Item 数据
        item.thumbnail = icon

        # 更新 LRU：如果存在先移除，再重新加入到末尾（标记为最近使用）
        if path_str in self._thumbnail_lru:
            self._thumbnail_lru.move_to_end(path_str)
        else:
            self._thumbnail_lru[path_str] = row
            # 检查容量
            if len(self._thumbnail_lru) > self._thumbnail_cache_limit:
                # 移除最久未使用的 (FIFO)
                old_path_str, old_row = self._thumbnail_lru.popitem(last=False)
                # 清除旧 Item 的缩略图引用以释放显存
                # 使用_path_map动态查找当前row，避免row失步问题
                current_old_row = self._path_map.get(old_path_str)
                if current_old_row is not None and 0 <= current_old_row < len(self._data):
                    self._data[current_old_row].thumbnail = None

        # 通知 View 刷新 DecorationRole
        idx = self.index(row, 0)
        self.dataChanged.emit(idx, idx, [Qt.ItemDataRole.DecorationRole])
