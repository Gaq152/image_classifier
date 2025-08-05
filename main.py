#!/usr/bin/env python3
"""
图像分类工具 - 主入口

一个高性能的图像分类整理工具，支持智能预加载、网络路径优化、
多种图像格式、自定义快捷键等功能。

版本: 5.0.0
"""

import sys
import os
import logging
import traceback
from pathlib import Path

# 配置环境变量以减少调试输出
os.environ["QT_LOGGING_RULES"] = "qt.qpa.*=false"
os.environ["OPENCV_LOG_LEVEL"] = "ERROR"
os.environ["PYTHONWARNINGS"] = "ignore"
os.environ["EXIFTOOL_DEBUG"] = "0"
os.environ["PIL_DEBUG"] = "0"


def setup_logging():
    """设置日志系统"""
    try:
        # 清除现有handlers，避免冲突
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        
        # 创建日志目录 - 在程序运行目录下
        current_dir = Path.cwd()
        log_dir = current_dir / 'logs'
        log_dir.mkdir(exist_ok=True)
        
        # 禁用第三方库的调试输出
        logging.getLogger('PIL').setLevel(logging.WARNING)
        logging.getLogger('PIL.Image').setLevel(logging.WARNING)
        logging.getLogger('PIL.ExifTags').setLevel(logging.WARNING)
        logging.getLogger('PIL.TiffImagePlugin').setLevel(logging.WARNING)
        logging.getLogger('PIL.TiffTags').setLevel(logging.WARNING)
        logging.getLogger('cv2').setLevel(logging.WARNING)
        logging.getLogger('numpy').setLevel(logging.WARNING)
        
        # 创建文件处理器
        file_handler = logging.FileHandler(
            log_dir / 'image_classifier.log', 
            encoding='utf-8',
            mode='a'
        )
        file_handler.setLevel(logging.DEBUG)
        
        # 创建控制台处理器（用于重要信息）
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        
        # 设置格式 - 添加毫秒精度用于性能分析
        file_formatter = logging.Formatter(
            '%(asctime)s.%(msecs)03d - %(name)s - %(levelname)s - %(message)s', 
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        console_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%H:%M:%S'
        )
        
        file_handler.setFormatter(file_formatter)
        console_handler.setFormatter(console_formatter)
        
        # 添加处理器到根日志器
        root_logger.addHandler(file_handler)
        root_logger.addHandler(console_handler)
        root_logger.setLevel(logging.DEBUG)
        
        logger = logging.getLogger(__name__)
        logger.info("=" * 60)
        logger.info("图像分类工具启动")
        logger.info("=" * 60)
        
        return True
        
    except Exception as e:
        print(f"日志设置失败: {e}")
        return False


def check_dependencies():
    """检查必要的依赖"""
    missing_deps = []
    
    try:
        from PyQt6.QtWidgets import QApplication, QMessageBox
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QIcon
    except ImportError:
        missing_deps.append("PyQt6")
    
    try:
        import cv2
    except ImportError:
        missing_deps.append("opencv-python")
    
    try:
        from PIL import Image
    except ImportError:
        missing_deps.append("Pillow")
    
    try:
        import psutil
    except ImportError:
        missing_deps.append("psutil")
    
    if missing_deps:
        error_msg = f"缺少以下依赖包：\n" + "\n".join(f"• {dep}" for dep in missing_deps)
        error_msg += "\n\n请使用以下命令安装：\n"
        error_msg += f"pip install {' '.join(missing_deps)}"
        
        print(error_msg)
        return False
    
    return True


def handle_exception(exc_type, exc_value, exc_traceback):
    """全局异常处理器"""
    if issubclass(exc_type, KeyboardInterrupt):
        # 忽略键盘中断
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    
    logger = logging.getLogger(__name__)
    logger.critical(
        "未捕获的异常",
        exc_info=(exc_type, exc_value, exc_traceback)
    )
    
    # 显示错误对话框
    try:
        from PyQt6.QtWidgets import QMessageBox
        error_msg = f"程序遇到未预期的错误：\n{exc_value}\n\n请查看日志文件获取详细信息。"
        QMessageBox.critical(None, "程序错误", error_msg)
    except:
        print(f"未捕获的异常: {exc_value}")


def main():
    """主函数"""
    try:
        # 检查依赖
        if not check_dependencies():
            sys.exit(1)
        
        # 设置日志
        if not setup_logging():
            print("警告: 日志设置失败，程序将继续运行")
        
        # 设置全局异常处理器
        sys.excepthook = handle_exception
        
        # 导入PyQt6
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import Qt, QLocale
        from PyQt6.QtGui import QIcon
        
        # 创建应用程序实例
        app = QApplication(sys.argv)
        app.setApplicationName("图像分类工具")
        app.setApplicationVersion("5.0.0")
        app.setOrganizationName("ImageClassifier")
        
        # PyQt6默认已启用高DPI支持，无需手动设置
        # app.setAttribute() 调用在PyQt6中已经不需要了
        
        # 设置中文本地化
        QLocale.setDefault(QLocale(QLocale.Language.Chinese, QLocale.Country.China))
        
        # 导入主窗口类 - 支持两种启动方式
        try:
            # 作为模块运行时使用相对导入
            from .ui.main_window import ImageClassifier
        except ImportError:
            # 作为脚本运行时使用绝对导入
            from pathlib import Path
            # 添加项目根目录到Python路径
            project_root = Path(__file__).parent.parent
            if str(project_root) not in sys.path:
                sys.path.insert(0, str(project_root))
            from .ui.main_window import ImageClassifier
        
        # 创建主窗口
        window = ImageClassifier()
        window.show()
        
        logger = logging.getLogger(__name__)
        logger.info("应用程序启动成功")
        
        # 运行应用程序
        try:
            exit_code = app.exec()
            logger.info(f"应用程序退出，退出代码: {exit_code}")
            return exit_code
            
        except Exception as e:
            logger.error(f"应用程序运行时错误: {e}")
            logger.error(traceback.format_exc())
            return 1
        
        finally:
            logger.info("程序正常退出")
            logger.info("=" * 60)
        
    except ImportError as e:
        print(f"导入错误: {e}")
        print("请确保安装了所有必要的依赖库")
        return 1
    except Exception as e:
        print(f"应用程序启动失败: {e}")
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
