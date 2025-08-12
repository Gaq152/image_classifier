# 📋 版本管理系统说明

## 🎯 概述

本项目使用统一的版本管理系统，所有版本相关信息都集中在 `_version_.py` 文件中管理，确保版本信息的一致性和易维护性。

## 📁 相关文件

| 文件 | 作用 | 状态 |
|------|------|------|
| `_version_.py` | 🎯 版本管理核心文件 | ✅ 主要 |
| `update_version_docs.py` | 📝 版本文档更新脚本 | 🔧 工具 |
| `version_demo.py` | 💡 使用演示脚本 | 📖 演示 |
| `VERSION_MANAGEMENT.md` | 📚 使用说明文档 | 📖 文档 |

## 🔧 使用方式

### 1. 获取版本信息

```python
from _version_ import __version__, get_about_info, get_download_urls

# 基础版本号
print(__version__)  # "5.3.0"

# About对话框信息
about = get_about_info()
print(f"{about['release_name']} v{about['version']}")

# 下载链接信息  
urls = get_download_urls()
print(urls['exe_name'])  # "ImageClassifier_v5.3.0.exe"
```

### 2. 在UI中使用

```python
# 主窗口 (ui/main_window.py)
from .._version_ import __version__
self.version = __version__

# 帮助对话框 (ui/dialogs.py)  
from .._version_ import get_about_info, VERSION_HISTORY
about_info = get_about_info()
```

### 3. 在构建脚本中使用

```python  
# build.py
from _version_ import __version__, get_download_urls

version = __version__
final_name = f"ImageClassifier_v{version}"
```

## 🚀 版本更新流程

### 步骤 1: 修改版本号
编辑 `_version_.py` 文件：
```python
# 只需修改这一行
__version__ = "5.4.0"
```

### 步骤 2: 更新版本历史
在 `_version_.py` 的 `VERSION_HISTORY` 列表开头添加新版本：
```python
VERSION_HISTORY = [
    {
        "version": "5.4.0",
        "date": "2025-08-15", 
        "title": "新功能标题",
        "highlights": [
            "🎨 新功能1",
            "🐛 修复问题2", 
            "⚡ 性能优化3"
        ]
    },
    # ... 现有版本
]
```

### 步骤 3: 更新文档
运行自动更新脚本：
```bash
python update_version_docs.py
```

### 步骤 4: 验证和提交
```bash
# 验证版本信息
python version_demo.py

# 提交更改
git add .
git commit -m "chore: 更新版本号到 v5.4.0"
git tag v5.4.0
git push && git push --tags
```

## 📊 自动化特性

### ✅ 已统一的文件
- `main.py` - 应用版本设置
- `ui/main_window.py` - 主窗口版本显示  
- `ui/dialogs.py` - 帮助对话框版本历史
- `build.py` - 构建脚本版本引用
- `__init__.py` - 包版本导出

### 🔧 工具脚本功能
- **`update_version_docs.py`**:
  - 自动更新 README.md 中的版本徽章
  - 更新下载链接中的版本号
  - 验证各文件版本一致性
  - 备份原文件防止意外丢失

- **`version_demo.py`**:
  - 展示所有版本管理功能
  - 演示常见使用场景  
  - 提供版本比较示例
  - 验证系统工作状态

## 🎯 最佳实践

### ✅ 推荐做法
1. **单点维护**: 只在 `_version_.py` 中修改版本号
2. **及时更新**: 每次版本变更后运行更新脚本
3. **详细记录**: 在版本历史中记录详细变更信息
4. **标签管理**: 为每个版本创建对应的 Git 标签

### ❌ 避免做法
1. ❌ 直接在其他文件中硬编码版本号
2. ❌ 忘记更新版本历史信息
3. ❌ 跳过文档更新步骤
4. ❌ 版本号格式不符合 semantic versioning

## 🔍 故障排除

### 版本不一致
运行验证脚本检查：
```bash
python update_version_docs.py
```

### 导入错误
确保 `_version_.py` 在项目根目录且语法正确：
```bash
python -c "from _version_ import __version__; print(__version__)"
```

### 文档更新失败
检查文件权限和备份文件：
```bash
ls -la *.md.bak
```

## 💡 扩展功能

### 版本比较
```python
from _version_ import compare_version, is_newer_version

# 比较版本
result = compare_version("5.4.0", "5.3.0")  # 返回 1 (更新)

# 检查更新
if is_newer_version("5.4.0"):
    print("有新版本可用!")
```

### 构建信息
```python
from _version_ import BUILD_INFO, get_build_string

print(f"构建于: {BUILD_INFO['build_date']}")
print(f"目标平台: {BUILD_INFO['target_platform']}")
```

---

## 📚 相关链接

- 📖 **演示脚本**: `python version_demo.py`
- 🔧 **更新工具**: `python update_version_docs.py`
- 📋 **版本历史**: `_version_.py` 中的 `VERSION_HISTORY`
- 🏷️ **语义化版本**: [semver.org](https://semver.org/lang/zh-CN/)

---
*该文档自动更新于版本管理系统实施时 (2025-08-12)*
