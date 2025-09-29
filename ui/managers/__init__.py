"""
管理器模块

包含各种功能管理器，用于分离main_window中的复杂逻辑。
"""

from .file_state_manager import FileStateManager

__all__ = ['FileStateManager']