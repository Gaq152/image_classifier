"""
视图状态数据类

存储UI视图的状态数据（排序、过滤、显示选项等）。

设计理念（Codex Review，2025-12-04）：
- 使用 @dataclass 集中存储视图相关状态
- 与会话状态（SessionState）分离，职责更清晰
- 不包含业务逻辑，仅作为数据容器
"""

from dataclasses import dataclass


@dataclass
class ViewState:
    """
    视图状态（排序、过滤、显示选项）

    存储UI视图的所有状态数据。
    """

    # ========== 过滤状态 ==========
    filter_unclassified: bool = False
    """是否过滤未分类图片"""

    filter_classified: bool = False
    """是否过滤已分类图片"""

    filter_removed: bool = False
    """是否过滤已移除图片"""

    # ========== 排序状态 ==========
    sort_mode: str = "name"
    """排序模式：'name'（名称）, 'time'（时间）, 'size'（大小）"""

    sort_ascending: bool = True
    """是否升序排序"""

    category_sort_mode: str = "name"
    """类别排序模式：'name'（名称）, 'count'（数量）, 'shortcut'（快捷键）"""

    category_sort_ascending: bool = True
    """类别是否升序排序"""

    # ========== 显示状态 ==========
    show_image_list: bool = True
    """是否显示图片列表"""

    show_category_panel: bool = True
    """是否显示类别面板"""

    show_status_bar: bool = True
    """是否显示状态栏"""

    # ========== 预览状态 ==========
    preview_scale: float = 1.0
    """预览图缩放比例"""

    fit_to_window: bool = True
    """是否适应窗口大小"""

    # ========== 搜索状态 ==========
    search_text: str = ""
    """搜索文本"""

    search_active: bool = False
    """搜索是否激活"""

    def is_any_filter_active(self) -> bool:
        """检查是否有任何过滤器激活"""
        return (
            self.filter_unclassified
            or self.filter_classified
            or self.filter_removed
        )

    def reset_filters(self) -> None:
        """重置所有过滤器"""
        self.filter_unclassified = False
        self.filter_classified = False
        self.filter_removed = False

    def reset_search(self) -> None:
        """重置搜索状态"""
        self.search_text = ""
        self.search_active = False
