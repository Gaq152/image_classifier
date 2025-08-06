# 图像分类工具 (Image Classifier)

<div align="center">

![Version](https://img.shields.io/badge/version-5.2.0-blue.svg)
![Python](https://img.shields.io/badge/python-3.8+-green.svg)
![Platform](https://img.shields.io/badge/platform-Windows-lightgrey.svg)
![License](https://img.shields.io/badge/license-MIT-orange.svg)

一个高性能的图像分类整理工具，支持智能预加载、网络路径优化、多种图像格式、自定义快捷键等功能。



[功能特性](#功能特性) • [安装使用](#安装使用) • [开发指南](#开发指南) • [构建发布](#构建发布)

</div>

## 📖 项目简介

图像分类工具是一个基于 PyQt6 开发的桌面应用程序，专为需要快速整理和分类大量图片的用户设计。该工具具有直观的用户界面，支持多种图像格式，提供了高效的图像预加载和智能分类功能。

### 🎯 适用场景

- 📸 摄影师整理作品集
- 🎨 设计师管理素材库
- 📂 个人照片分类整理
- 🏢 企业图片资产管理
- 🔍 大批量图片快速筛选

## ✨ 功能特性

### 🚀 核心功能

- **🖼️ 多格式支持**: 支持 JPG、JPEG、PNG、BMP、GIF、TIFF、WebP 等主流图像格式
- **⚡ 智能预加载**: 高性能图像加载机制，支持大图片快速预览
- **🏷️ 快速分类**: 自定义分类按钮，支持快捷键操作
- **🌐 网络路径优化**: 针对网络共享路径进行性能优化
- **📁 批量处理**: 支持文件夹扫描和批量图片操作
- **💾 状态保存**: 自动保存工作进度和用户设置

### 🎛️ 用户界面

- **现代化设计**: 简洁美观的用户界面，支持高DPI显示
- **双面板布局**: 图片列表 + 分类操作区域
- **实时预览**: 高质量图片预览，支持缩放和全屏查看
- **进度显示**: 实时显示扫描和处理进度
- **状态栏信息**: 显示当前文件信息和系统状态

### ⌨️ 操作特性

- **自定义快捷键**: 为每个分类设置专属快捷键（1-9, A-Z）
- **键盘导航**: 支持方向键浏览图片和选择类别
- **多种分类模式**: 支持移动/复制模式，单分类/多分类模式切换
- **右键菜单**: 丰富的上下文菜单操作

### 🔧 技术特性

- **高性能**: 多线程处理，优化内存使用
- **日志系统**: 完整的操作日志记录
- **错误处理**: 完善的异常处理机制
- **配置管理**: 灵活的配置文件系统
- **性能监控**: 内置性能监控功能

## 🛠️ 技术栈

| 组件 | 技术 | 版本要求 | 用途 |
|------|------|----------|------|
| **GUI框架** | PyQt6 | >= 6.4.0 | 用户界面框架 |
| **图像处理** | OpenCV | >= 4.5.0 | 图像读取和处理 |
| **图像库** | Pillow | >= 9.0.0 | 图像格式支持 |
| **系统监控** | psutil | >= 5.8.0 | 系统资源监控 |
| **打包工具** | PyInstaller | >= 5.0.0 | 应用程序打包 |

## 📋 系统要求

### 最低要求
- **操作系统**: Windows 7 或更高版本
- **Python版本**: Python 3.8+
- **内存**: 4GB RAM
- **存储空间**: 200MB 可用空间

### 推荐配置
- **操作系统**: Windows 10/11 64位
- **Python版本**: Python 3.10+
- **内存**: 8GB RAM 或更多
- **存储空间**: 1GB 可用空间
- **显示器**: 1920x1080 分辨率或更高

## 🚀 安装使用

### 方式一：直接运行（推荐）

下载已编译的可执行文件，无需安装Python环境：

1. 访问项目地址：https://gitlab.desauto.cn/rd/delivery/data_process/image_classifier
2. 进入 `dist/` 目录下载最新版本的 `图像分类工具_vx.x.x.exe`
3. 双击运行即可使用

### 方式二：源码运行

适合开发者或需要自定义的用户：

```bash
# 1. 克隆项目
git clone https://gitlab.desauto.cn/rd/delivery/data_process/image_classifier.git
cd image-classifier

# 2. 安装依赖
pip install -r requirements.txt

# 3. 运行程序
python run.py
```

## 📖 使用指南

### 基本操作流程

1. **启动程序**: 运行 `图像分类工具_v5.2.0.exe` 或 `python run.py`
2. **选择目录**: 点击工具栏的"打开文件夹"按钮，选择包含图片的目录
3. **创建分类**: 在分类区域添加需要的分类类别
4. **开始分类**: 
   - 在图片列表中选择图片
   - 点击对应的分类按钮或使用快捷键
   - 图片将被移动到相应的分类文件夹

### 快捷键说明

| 快捷键 | 功能 | 说明 |
|--------|------|------|
| `←` `→` | 图片导航 | 在图片列表中前后浏览 |
| `↑` `↓` | 类别导航 | 在类别列表中上下选择 |
| `Enter` | 确认分类 | 将当前图片分类到选中类别 |
| `1`-`9`, `A`-`Z` | 快速分类 | 使用数字或字母快捷键快速分类 |
| `Delete` | 移出图片 | 将图片移动到remove目录 |
| `F5` | 刷新 | 重新扫描当前目录 |
| `F` | 适应窗口 | 图片适应窗口大小 |
| `Ctrl +/-/0` | 缩放控制 | 放大/缩小/重置图片缩放 |

### 配置文件

程序会在当前目录生成以下配置文件：
- `logs/image_classifier.log`: 操作日志

程序会在图片目录的同级目录下生成以下配置文件：
- `config.json`: 类别记录和快捷键配置
- `classification_state.json`: 工作状态以及分类信息保存

## 🏗️ 项目结构

```
image_classifier/
├── 📁 assets/              # 资源文件
│   └── icon.ico            # 应用程序图标
├── 📁 core/                # 核心功能模块
│   ├── config.py           # 配置管理
│   ├── file_manager.py     # 文件操作管理
│   ├── image_loader.py     # 图像加载器
│   └── scanner.py          # 文件扫描器
├── 📁 ui/                  # 用户界面模块
│   ├── main_window.py      # 主窗口
│   ├── dialogs.py          # 对话框
│   └── widgets.py          # 自定义组件
├── 📁 utils/               # 工具模块
│   ├── exceptions.py       # 异常定义
│   ├── file_operations.py  # 文件操作工具
│   └── performance.py      # 性能监控
├── 📁 logs/                # 日志目录
├── main.py                 # 主入口文件
├── run.py                  # 启动脚本
├── build.py                # 构建脚本
├── requirements.txt        # 依赖列表
└── README.md              # 项目说明
```

## 🔨 开发指南

### 开发环境搭建

```bash
# 1. 克隆项目
git clone https://gitlab.desauto.cn/rd/delivery/data_process/image_classifier.git
cd image-classifier

# 2. 创建虚拟环境（推荐）
python -m venv venv
venv\Scripts\activate  # Windows

# 3. 安装开发依赖
pip install -r requirements.txt

# 4. 运行开发版本
python run.py
```

### 代码规范

- 使用 Python 3.8+ 语法特性
- 遵循 PEP 8 代码风格
- 使用类型注解提高代码可读性
- 完善的错误处理和日志记录
- 模块化设计，职责单一

### 主要模块说明

#### Core模块
- **config.py**: 管理应用配置、快捷键设置等
- **image_loader.py**: 高性能图像加载，支持多线程和缓存
- **scanner.py**: 文件系统扫描，支持多种图像格式
- **file_manager.py**: 文件操作管理，包括移动、复制等

#### UI模块
- **main_window.py**: 主界面实现，包含所有用户交互逻辑
- **widgets.py**: 自定义UI组件，如图片预览、分类按钮等
- **dialogs.py**: 各种对话框实现

#### Utils模块
- **file_operations.py**: 文件操作工具函数
- **performance.py**: 性能监控和优化工具
- **exceptions.py**: 自定义异常类定义

## 📦 构建发布

### 构建可执行文件

项目提供了自动化构建脚本：

```bash
# 使用优化的构建脚本
python build.py
```

构建特性：
- ✅ 单文件exe，无需额外依赖
- ✅ 包含应用图标和资源文件  
- ✅ 优化文件体积（约86MB）
- ✅ 支持Windows 7+系统
- ✅ 自动处理编码问题

### 构建输出

构建完成后会在 `dist/` 目录生成：
- `图像分类工具_vx.x.x.exe` - 主程序文件

## 🐛 问题排查

### 常见问题

**Q: 程序启动失败？**
A: 确保系统满足最低要求，Windows 7+ 和足够的内存空间。

**Q: 图片加载缓慢？**
A: 检查图片大小和格式，程序对超大图片（>50MB）可能需要更长加载时间。

**Q: 快捷键不响应？**
A: 确保程序窗口获得焦点，避免与其他程序的快捷键冲突。

**Q: 网络路径访问问题？**
A: 确保有足够的网络权限，程序对网络路径进行了特殊优化。

### 日志查看

程序运行时会生成详细日志：
- 位置：`logs/image_classifier.log`
- 包含：操作记录、错误信息、性能数据
- 用途：问题诊断和性能分析

## 🤝 贡献指南

欢迎提交问题报告和功能请求！

### 报告问题

1. 在 GitLab 项目的 Issues 页面创建新问题
2. 描述问题的重现步骤
3. 提供错误日志和系统信息
4. 如可能，提供截图说明

### 贡献代码

1. Fork 项目到您的 GitLab 账户
2. 创建特性分支：`git checkout -b feature/amazing-feature`
3. 提交更改：`git commit -m 'Add amazing feature'`
4. 推送分支：`git push origin feature/amazing-feature`
5. 创建 Merge Request

## 📄 更新日志

### v5.2.0 (2025-08-06)
- ✨ 统一滚动条样式设计，美化界面
- 🐛 修复构建脚本编码问题
- ⚡ 优化exe文件体积（减少37%，降至86MB）
- 🎨 改进用户界面细节和交互体验
- 🔧 完善快捷键系统和类别管理
- 📝 完善项目文档和使用说明
- 🚀 支持移动/复制模式切换
- 🏷️ 支持单分类/多分类模式


## 📜 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情。

## 🙏 致谢

- [PyQt6](https://www.riverbankcomputing.com/software/pyqt/) - 强大的GUI框架
- [OpenCV](https://opencv.org/) - 计算机视觉库
- [Pillow](https://pillow.readthedocs.io/) - Python图像处理库
- [PyInstaller](https://pyinstaller.org/) - Python应用打包工具

---

<div align="center">

**如果这个项目对您有帮助，请给它一个 ⭐ Star！**

Made with ❤️ by [GDDI-wanqing Team]

</div>
