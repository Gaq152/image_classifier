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
    
    # 设置工作目录为项目根目录
    os.chdir(script_dir)
    
    try:
        # 直接导入main模块（在同一目录下）
        from main import main as app_main
        return app_main()
    except ImportError as e:
        print(f"导入错误: {e}")
        print("请确保所有依赖库已安装")
        return 1

if __name__ == '__main__':
    sys.exit(main())