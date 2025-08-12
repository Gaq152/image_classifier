"""
版本管理模块 - 统一管理所有版本相关信息

该文件是版本管理的唯一源头，所有其他文件都应该从此处导入版本信息。
"""

import datetime
from typing import Dict, List, Tuple

# ================================
# 🎯 核心版本信息
# ================================

# 主版本号 - 这是唯一需要手动修改的地方
__version__ = "5.4.0"
__version_info__ = tuple(map(int, __version__.split('.')))

# 发布信息
RELEASE_DATE = "2025-08-12"
RELEASE_NAME = "图像分类工具"

# ================================
# 📋 版本历史和更新信息
# ================================

VERSION_HISTORY = [
    {
        "version": "5.4.0",
        "date": "2025-08-12", 
        "title": "快捷键系统重构与版本管理优化",
        "highlights": [
            "🔧 彻底修复快捷键间歇性失效问题",
            "✨ 实现统一版本管理系统",
            "⚡ 优化异步状态保存机制",
            "🎨 统一版本引用，消除分散管理"
        ],
        "details": [
            "彻底修复快捷键间歇性失效问题，新增窗口焦点事件处理",
            "解决焦点丢失导致的按键无响应问题",
            "修复快捷键设置过程中的资源管理和异常处理",
            "实现统一版本管理系统，创建_version_.py作为版本信息唯一源头",
            "新增快捷键健康检查和自动修复功能",
            "添加定期监控机制，每30秒检查快捷键状态",
            "开发自动化版本文档更新工具和演示脚本",
            "优化状态保存为异步操作，避免I/O阻塞事件循环",
            "实现快捷键安全执行机制，防止异常影响系统稳定性",
            "增强错误恢复能力，支持快捷键丢失时的自动重建",
            "统一所有文件的版本引用，消除版本号分散管理问题",
            "完善日志记录，新增快捷键状态变化的详细追踪",
            "改进刷新操作，自动触发快捷键状态检查和修复",
            "创建VERSION_MANAGEMENT.md详细说明统一版本管理使用方法",
            "新增版本更新流程文档和最佳实践指南",
            "完善版本一致性验证和自动同步机制"
        ]
    },
    {
        "version": "5.3.0",
        "date": "2025-08-06", 
        "title": "CI/CD自动化与用户体验优化",
        "highlights": [
            "🤖 实现GitLab CI/CD自动构建发布",
            "🔧 修复图标和日志文件路径问题", 
            "📊 创建专门的更新日志文档",
            "🎯 改进下载和文档链接"
        ],
        "details": [
            "新增GitLab CI/CD pipeline实现自动构建",
            "修复打包环境下图标和日志路径问题",
            "创建CHANGELOG.md独立更新文档",
            "优化README结构，新增快速下载区域",
            "完善错误处理和资源管理机制"
        ]
    },
    {
        "version": "5.2.0", 
        "date": "2025-07-25",
        "title": "多分类增强与界面统一", 
        "highlights": [
            "🎨 统一滚动条样式设计",
            "🔧 完善多分类撤销机制",
            "⚖️ 智能重复文件处理",
            "🚦 优化模式切换限制"
        ],
        "details": [
            "统一所有滚动条的视觉样式",
            "修复多分类模式的撤销文件操作",
            "新增重复文件hash对比和用户选择",
            "完善移动模式与多分类的互斥限制",
            "改进弹窗样式一致性和中文化"
        ]
    },
    {
        "version": "5.1.0",
        "date": "2025-07-20", 
        "title": "性能优化与稳定性提升",
        "highlights": [
            "⚡ 高性能图像预加载系统",
            "🌐 网络路径访问优化", 
            "📱 内存管理和缓存系统",
            "🔍 智能文件扫描机制"
        ]
    },
    {
        "version": "5.0.0",
        "date": "2025-07-15",
        "title": "PyQt6重构与现代化改造", 
        "highlights": [
            "🎨 全新现代化界面设计",
            "🏗️ 基于PyQt6的完整重构",
            "📋 多分类支持与状态管理",
            "⚡ 异步图像加载与缓存"
        ]
    }
]

# ================================
# 🛠️ 构建和发布信息  
# ================================

BUILD_INFO = {
    "build_date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "python_version": "3.8+",
    "framework": "PyQt6",
    "target_platform": "Windows",
    "min_os_version": "Windows 7+",
    "architecture": "x64"
}

# 下载信息
DOWNLOAD_INFO = {
    "exe_name_template": "ImageClassifier_v{version}.exe",
    "exe_name_chinese_template": "图像分类工具_v{version}.exe", 
    "expected_size_mb": "~86MB",
    "gitlab_project_id": "820",
    "package_registry_base": "https://gitlab.desauto.cn/api/v4/projects/820/packages/generic/image_classifier"
}

# ================================
# 🎯 帮助和About信息
# ================================

def get_about_info() -> Dict:
    """获取About对话框需要的信息"""
    return {
        "version": __version__,
        "release_date": RELEASE_DATE,
        "release_name": RELEASE_NAME,
        "current_year": datetime.datetime.now().year,
        "framework": BUILD_INFO["framework"],
        "python_version": BUILD_INFO["python_version"]
    }

def get_version_badge_info() -> Dict:
    """获取版本徽章信息"""
    return {
        "version": __version__,
        "color": "blue",
        "label": "version"
    }

def get_download_urls() -> Dict:
    """获取下载链接信息"""
    base_url = DOWNLOAD_INFO["package_registry_base"]
    version = __version__
    
    return {
        "specific_version": f"{base_url}/{version}/ImageClassifier_v{version}.exe",
        "latest": f"{base_url}/latest/ImageClassifier_v{version}.exe",
        "exe_name": DOWNLOAD_INFO["exe_name_template"].format(version=version),
        "exe_name_chinese": DOWNLOAD_INFO["exe_name_chinese_template"].format(version=version)
    }

def get_latest_version_info() -> Dict:
    """获取最新版本的详细信息"""
    if not VERSION_HISTORY:
        return {}
    
    latest = VERSION_HISTORY[0]
    return {
        **latest,
        "version_number": __version__,
        "release_date_formatted": RELEASE_DATE
    }

# ================================
# 🔧 版本比较和验证工具
# ================================

def compare_version(version1: str, version2: str) -> int:
    """比较两个版本号
    
    Returns:
        -1: version1 < version2  
         0: version1 == version2
         1: version1 > version2
    """
    def version_tuple(v):
        return tuple(map(int, v.split('.')))
    
    v1 = version_tuple(version1)
    v2 = version_tuple(version2)
    
    if v1 < v2:
        return -1
    elif v1 > v2:
        return 1
    else:
        return 0

def is_newer_version(new_version: str, current_version: str = None) -> bool:
    """检查是否为更新的版本"""
    if current_version is None:
        current_version = __version__
    return compare_version(new_version, current_version) > 0

def validate_version_format(version: str) -> bool:
    """验证版本号格式是否正确 (x.y.z)"""
    try:
        parts = version.split('.')
        if len(parts) != 3:
            return False
        for part in parts:
            int(part)  # 检查是否为数字
        return True
    except (ValueError, AttributeError):
        return False

# ================================
# 📝 格式化输出工具
# ================================

def get_version_string() -> str:
    """获取标准版本字符串"""
    return f"v{__version__}"

def get_full_version_string() -> str:
    """获取完整版本信息字符串"""
    return f"{RELEASE_NAME} v{__version__} ({RELEASE_DATE})"

def get_build_string() -> str:
    """获取构建信息字符串"""
    return f"Build {BUILD_INFO['build_date']} | {BUILD_INFO['framework']} | {BUILD_INFO['target_platform']}"

def print_version_info():
    """打印完整的版本信息"""
    print("="*50)
    print(f" {RELEASE_NAME}")
    print("="*50)
    print(f"版本: {__version__}")
    print(f"发布日期: {RELEASE_DATE}")
    print(f"构建框架: {BUILD_INFO['framework']}")
    print(f"目标平台: {BUILD_INFO['target_platform']}")
    print(f"最低系统: {BUILD_INFO['min_os_version']}")
    print("="*50)

if __name__ == "__main__":
    # 当直接运行此文件时，显示版本信息
    print_version_info()
