#!/usr/bin/env python3
"""
图像分类工具 - 主入口

一个高性能的图像分类整理工具，支持智能预加载、网络路径优化、
多种图像格式、自定义快捷键等功能。

版本信息由 _version_.py 统一管理
"""

import sys
import os
import logging
import traceback
from pathlib import Path
from _version_ import __version__, get_full_version_string, print_version_info

# 配置环境变量以减少调试输出
os.environ["QT_LOGGING_RULES"] = "qt.qpa.*=false"
os.environ["OPENCV_LOG_LEVEL"] = "ERROR"
os.environ["PYTHONWARNINGS"] = "ignore"
os.environ["EXIFTOOL_DEBUG"] = "0"
os.environ["PIL_DEBUG"] = "0"


def get_log_directory():
    """获取日志目录 - 使用统一路径管理"""
    try:
        from utils.paths import get_logs_dir
        return get_logs_dir()
    except Exception as e:
        # 备用方案 - 当前目录
        print(f"获取日志目录失败，使用当前目录: {e}")
        fallback_dir = Path.cwd() / 'logs'
        fallback_dir.mkdir(parents=True, exist_ok=True)
        return fallback_dir


def setup_logging():
    """设置日志系统 - 支持日志轮转和自动清理"""
    try:
        from logging.handlers import TimedRotatingFileHandler
        import glob
        import time

        # 清除现有handlers，避免冲突
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)

        # 创建日志目录 - 智能选择位置
        log_dir = get_log_directory()
        log_dir.mkdir(exist_ok=True)

        # 禁用第三方库的调试输出
        logging.getLogger('PIL').setLevel(logging.WARNING)
        logging.getLogger('PIL.Image').setLevel(logging.WARNING)
        logging.getLogger('PIL.ExifTags').setLevel(logging.WARNING)
        logging.getLogger('PIL.TiffImagePlugin').setLevel(logging.WARNING)
        logging.getLogger('PIL.TiffTags').setLevel(logging.WARNING)
        logging.getLogger('cv2').setLevel(logging.WARNING)
        logging.getLogger('numpy').setLevel(logging.WARNING)

        # 清理旧日志文件（保留7天）
        try:
            current_time = time.time()
            retention_days = 7
            retention_seconds = retention_days * 24 * 60 * 60

            # 查找所有日志文件（包括轮转的日志）
            log_files = glob.glob(str(log_dir / 'image_classifier*.log*'))
            deleted_count = 0

            for log_file in log_files:
                try:
                    file_path = Path(log_file)
                    # 检查文件修改时间
                    file_mtime = file_path.stat().st_mtime
                    if current_time - file_mtime > retention_seconds:
                        file_path.unlink()
                        deleted_count += 1
                except Exception:
                    continue

            if deleted_count > 0:
                print(f"已清理 {deleted_count} 个超过 {retention_days} 天的旧日志文件")
        except Exception as e:
            print(f"清理旧日志文件时出错: {e}")

        # 创建支持日志轮转的文件处理器
        # when='midnight' - 每天午夜轮转
        # interval=1 - 每1天轮转一次
        # backupCount=6 - 保留6个备份文件（加上当前文件=7天日志）
        # encoding='utf-8' - 使用UTF-8编码
        file_handler = TimedRotatingFileHandler(
            log_dir / 'image_classifier.log',
            when='midnight',
            interval=1,
            backupCount=6,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)

        # 设置日志文件后缀格式（日期格式）
        file_handler.suffix = '%Y-%m-%d'

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
        logger.info(f"日志目录: {log_dir}")
        logger.info(f"日志保留天数: 7天")
        logger.info("=" * 60)

        return True

    except Exception as e:
        print(f"日志设置失败: {e}")
        import traceback
        traceback.print_exc()
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
        app.setApplicationVersion(__version__)
        app.setOrganizationName("ImageClassifier")
        
        # PyQt6默认已启用高DPI支持，无需手动设置
        # app.setAttribute() 调用在PyQt6中已经不需要了
        
        # 设置中文本地化
        QLocale.setDefault(QLocale(QLocale.Language.Chinese, QLocale.Country.China))
        
        # 导入主窗口类 - 支持两种启动方式
        # 使用相对导入
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
