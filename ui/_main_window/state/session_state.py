"""
会话状态数据类

存储当前浏览会话的状态数据（纯数据容器，不包含业务逻辑）。

设计理念（Codex Review，2025-12-04）：
- 使用 @dataclass 集中存储状态数据
- 不继承 QObject，不包含信号（信号由 UI 层托管）
- 主窗口持有此对象，通过 StateView 接口暴露给 Manager
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Set, Dict, Any, Optional, Union


@dataclass
class SessionState:
    """
    会话状态（当前浏览状态）

    存储用户当前会话的所有状态数据。
    """

    # ========== 路径相关 ==========
    current_dir: Optional[Path] = None
    """当前工作目录"""

    # ========== 图片相关 ==========
    image_files: List[Path] = field(default_factory=list)
    """当前图片文件列表（可能经过过滤）"""

    all_image_files: List[Path] = field(default_factory=list)
    """所有图片文件列表（未过滤）"""

    current_index: int = -1
    """当前图片索引"""

    # ========== 分类状态 ==========
    categories: Set[str] = field(default_factory=set)
    """类别集合"""

    ordered_categories: List[str] = field(default_factory=list)
    """排序后的类别列表"""

    classified_images: Dict[str, Union[str, List[str]]] = field(default_factory=dict)
    """
    已分类图片映射
    单分类模式: {路径: 类别名(str)}
    多分类模式: {路径: 类别列表(List[str])}
    """

    removed_images: Set[str] = field(default_factory=set)
    """已移除图片集合"""

    # ========== 模式状态 ==========
    is_copy_mode: bool = True
    """是否为复制模式（False 为移动模式）"""

    is_multi_category: bool = False
    """是否为多分类模式（False 为单分类模式）"""

    # ========== 临时状态 ==========
    last_operation_category: Optional[str] = None
    """最后一次操作的类别"""

    current_category_index: int = 0
    """当前选中的类别索引"""

    selected_category: Optional[str] = None
    """当前选中的类别名"""

    def __post_init__(self):
        """初始化后的额外处理"""
        # 确保 current_dir 是 Path 对象
        if self.current_dir and not isinstance(self.current_dir, Path):
            self.current_dir = Path(self.current_dir)

    @property
    def total_images(self) -> int:
        """图片总数"""
        return len(self.image_files)

    @property
    def base_dir(self) -> Optional[Path]:
        """基础目录（current_dir 的父目录）"""
        return self.current_dir.parent if self.current_dir else None

    def is_classified(self, path: str) -> bool:
        """检查图片是否已分类"""
        return path in self.classified_images

    def is_removed(self, path: str) -> bool:
        """检查图片是否已移除"""
        return path in self.removed_images

    def get_category(self, path: str) -> Optional[Union[str, List[str]]]:
        """获取图片的分类（单分类返回str，多分类返回List[str]，未分类返回None）"""
        return self.classified_images.get(path)
