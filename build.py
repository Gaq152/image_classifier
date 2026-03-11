#!/usr/bin/env python3
"""
图像分类工具优化打包脚本
精简依赖，修复编码问题，生成最小体积的exe文件
版本信息由 _version_.py 统一管理
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path
from _version_ import __version__, get_full_version_string, get_download_urls, print_version_info


def check_pyinstaller():
    """检查PyInstaller是否已安装"""
    try:
        import PyInstaller
        print(f"✓ PyInstaller已安装，版本: {PyInstaller.__version__}")
        return True
    except ImportError:
        print("✗ PyInstaller未安装")
        response = input("是否自动安装PyInstaller? (y/n): ").lower()
        if response == 'y':
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
                print("✓ PyInstaller安装成功")
                return True
            except subprocess.CalledProcessError:
                print("✗ PyInstaller安装失败")
                return False
        return False


def clean_build_dirs():
    """清理之前的构建目录"""
    dirs_to_clean = ['build', 'dist', '__pycache__']
    for dir_name in dirs_to_clean:
        if os.path.exists(dir_name):
            print(f"清理目录: {dir_name}")
            shutil.rmtree(dir_name)

    # 清理.spec文件
    spec_files = list(Path('.').glob('*.spec'))
    for spec_file in spec_files:
        print(f"删除spec文件: {spec_file}")
        spec_file.unlink()


def clean_build_artifacts():
    """构建完成后清理构建产物，只保留最终的exe文件"""
    print("\n开始清理构建产物...")

    # 清理build目录
    if os.path.exists('build'):
        print("清理build目录...")
        shutil.rmtree('build')

    # 清理.spec文件
    spec_files = list(Path('.').glob('*.spec'))
    for spec_file in spec_files:
        print(f"删除spec文件: {spec_file}")
        spec_file.unlink()

    # 清理__pycache__目录
    pycache_dirs = list(Path('.').rglob('__pycache__'))
    for pycache_dir in pycache_dirs:
        if pycache_dir.exists():
            print(f"清理缓存目录: {pycache_dir}")
            shutil.rmtree(pycache_dir)

    # 显示保留的文件
    dist_dir = Path('dist')
    if dist_dir.exists():
        exe_files = list(dist_dir.glob('*.exe'))
        if exe_files:
            print(f"✓ 保留最终产物: {len(exe_files)} 个exe文件")
            for exe_file in exe_files:
                size_mb = exe_file.stat().st_size / (1024 * 1024)
                print(f"  - {exe_file.name} ({size_mb:.1f} MB)")

    print("✓ 构建产物清理完成")


def check_dependencies():
    """检查必要的依赖库"""
    required_deps = {
        'PyQt6': 'PyQt6',
        'cv2': 'opencv-python',
        'PIL': 'Pillow',
        'psutil': 'psutil'
    }
    
    missing_deps = []
    for import_name, package_name in required_deps.items():
        try:
            __import__(import_name)
            print(f"✓ {package_name} 已安装")
        except ImportError:
            print(f"✗ {package_name} 未安装")
            missing_deps.append(package_name)
    
    if missing_deps:
        print(f"\n缺少以下依赖包: {', '.join(missing_deps)}")
        response = input("是否自动安装缺少的依赖? (y/n): ").lower()
        if response == 'y':
            for dep in missing_deps:
                try:
                    subprocess.check_call([sys.executable, "-m", "pip", "install", dep])
                    print(f"✓ {dep} 安装成功")
                except subprocess.CalledProcessError:
                    print(f"✗ {dep} 安装失败")
                    return False
        else:
            return False
    
    return True


def build_executable():
    """构建可执行文件 - 优化版本"""
    print("开始构建可执行文件（优化版本）...")
    
    # 项目信息 - 使用英文名称避免编码问题
    app_name = "ImageClassifier"
    version = __version__
    final_name = f"ImageClassifier_v{version}"
    
    # 构建PyInstaller命令 - 精简版本
    cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--onefile',  # 打包为单一文件
        '--windowed',  # Windows下不显示控制台
        '--name', final_name,  # 设置输出文件名
        '--icon', 'assets/icon.ico',  # 设置图标
        '--add-data', 'assets;assets',  # 包含assets目录
        
        # ========= 精简的必要导入 - 仅包含实际使用的模块 =========
        '--hidden-import', 'PyQt6.QtWidgets',
        '--hidden-import', 'PyQt6.QtCore',
        '--hidden-import', 'PyQt6.QtGui',
        '--hidden-import', 'cv2',
        '--hidden-import', 'PIL.Image',  # 只导入Image，不导入其他PIL子模块
        '--hidden-import', 'psutil',
        '--hidden-import', 'ssl',  # HTTPS 请求必需
        '--hidden-import', '_ssl',  # ssl 底层 C 扩展
        
        # ========= 优化选项 =========
        '--optimize', '2',  # Python字节码优化
        '--clean',  # 清理临时文件
        '--noconfirm',  # 不询问确认
        
        # ========= 排除不需要的模块以减小体积 =========
        '--exclude-module', 'tkinter',  # 排除tkinter
        '--exclude-module', 'matplotlib',  # 排除matplotlib
        '--exclude-module', 'scipy',  # 排除scipy
        '--exclude-module', 'pandas',  # 排除pandas
        '--exclude-module', 'numpy.testing',  # 排除numpy测试模块
        '--exclude-module', 'PIL.ImageQt',  # 排除不需要的PIL模块
        '--exclude-module', 'PIL.ImageDraw',
        '--exclude-module', 'PIL.ImageFilter',
        '--exclude-module', 'test',  # 排除测试模块
        '--exclude-module', 'unittest',  # 排除单元测试
        '--exclude-module', 'doctest',  # 排除文档测试
        
        'run.py'  # 入口文件
    ]

    # ========= 自动查找 OpenSSL DLL（GitHub Actions 等非标准环境需要）=========
    _ssl_dlls_found = []
    _python_root = os.path.dirname(sys.executable)
    _search_dirs = [
        _python_root,
        os.path.join(_python_root, 'DLLs'),
        os.path.join(_python_root, 'Library', 'bin'),
    ]
    for _dir in _search_dirs:
        if not os.path.isdir(_dir):
            continue
        for _f in os.listdir(_dir):
            _fl = _f.lower()
            if ('libssl' in _fl or 'libcrypto' in _fl) and _fl.endswith('.dll'):
                _full = os.path.join(_dir, _f)
                cmd.insert(-1, '--add-binary')
                cmd.insert(-1, f'{_full};.')
                _ssl_dlls_found.append(_f)
    if _ssl_dlls_found:
        print(f"✓ 发现 OpenSSL DLL: {', '.join(_ssl_dlls_found)}")
    else:
        print("⚠ 未找到 OpenSSL DLL，HTTPS 功能可能不可用")

    print(f"执行命令: {' '.join(cmd[:10])}... (命令过长，已截断)")
    print("注意: 使用精简依赖配置以减小文件体积")
    
    try:
        # 运行PyInstaller - 修复编码问题
        print("正在执行PyInstaller...")
        result = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True, 
            encoding='cp936',  # Windows中文编码
            errors='replace'  # 替换无法解码的字符
        )
        
        if result.returncode == 0:
            print("✓ 构建成功!")
            
            # 检查输出文件
            exe_path = Path('dist') / f'{final_name}.exe'
            if exe_path.exists():
                size_mb = exe_path.stat().st_size / (1024 * 1024)
                print(f"✓ 可执行文件已生成: {exe_path}")
                print(f"✓ 文件大小: {size_mb:.1f} MB")
                
                # 重命名为中文名称
                chinese_name = f"图像分类工具_v{version}.exe"
                chinese_path = Path('dist') / chinese_name
                try:
                    exe_path.rename(chinese_path)
                    print(f"✓ 文件已重命名为: {chinese_name}")
                except Exception as e:
                    print(f"重命名警告: {e}")
                    print(f"请手动将 {exe_path.name} 重命名为 {chinese_name}")
                
                return True
            else:
                print("✗ 可执行文件生成失败")
                return False
        else:
            print("✗ 构建失败")
            if result.stderr:
                print("错误输出:")
                print(result.stderr)
            if result.stdout:
                print("标准输出:")
                print(result.stdout)
            return False
            
    except Exception as e:
        print(f"✗ 构建过程中出现异常: {e}")
        return False


def main():
    """主函数"""
    print("=" * 60)
    print("图像分类工具 - 优化构建脚本")
    print(f"版本: {__version__}")
    print("特点: 精简依赖 + 修复编码 + 最小体积")
    print("=" * 60)
    
    # 检查当前目录
    if not Path('run.py').exists():
        print("✗ 请在项目根目录下运行此脚本")
        return 1
    
    # 检查图标文件
    if not Path('assets/icon.ico').exists():
        print("✗ 图标文件 assets/icon.ico 不存在")
        return 1
    
    # 检查PyInstaller
    if not check_pyinstaller():
        print("✗ PyInstaller检查失败")
        return 1
    
    # 检查依赖
    if not check_dependencies():
        print("✗ 依赖检查失败")
        return 1
    
    # 清理构建目录
    clean_build_dirs()
    
    # 构建可执行文件
    if not build_executable():
        print("✗ 构建失败")
        return 1

    # 构建完成后清理构建产物
    clean_build_artifacts()

    print("\n" + "=" * 60)
    print("✅ 优化构建完成!")
    download_urls = get_download_urls()
    print(f"📁 可执行文件: dist/{download_urls['exe_name_chinese']}")
    print("✨ 包含完整功能，去除冗余依赖")
    print("🧹 构建产物已清理，仅保留最终exe文件")
    print("=" * 60)
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
