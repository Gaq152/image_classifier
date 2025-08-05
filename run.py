#!/usr/bin/env python3
"""
图像分类工具启动脚本

这个脚本确保以正确的方式启动应用程序，支持相对导入。
"""

import sys
import os
from pathlib import Path

def main():
    """启动图像分类工具"""
    # 获取脚本所在目录
    script_dir = Path(__file__).parent.absolute()
    parent_dir = script_dir.parent
    
    # 将父目录添加到Python路径，这样可以作为包导入
    if str(parent_dir) not in sys.path:
        sys.path.insert(0, str(parent_dir))
    
    # 设置工作目录
    os.chdir(script_dir)
    
    try:
        # 作为包导入和运行
        from image_classifier.main import main as app_main  # type: ignore
        return app_main()
    except ImportError as e:
        print(f"导入错误: {e}")
        print("请确保所有依赖库已安装")
        return 1

if __name__ == '__main__':
    sys.exit(main())