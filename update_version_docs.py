#!/usr/bin/env python3
"""
版本文档更新脚本

自动更新项目文档中的版本信息，确保所有文档与 _version_.py 保持同步。
"""

import re
from pathlib import Path
from _version_ import __version__, get_version_badge_info, get_download_urls

def update_readme_version():
    """更新README.md中的版本信息"""
    readme_path = Path("README.md")
    
    if not readme_path.exists():
        print("❌ README.md 文件不存在")
        return False
    
    try:
        # 读取当前内容
        with open(readme_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        download_urls = get_download_urls()
        
        # 更新版本徽章
        version_badge_pattern = r'!\[Version\]\([^)]+version-[^-)]+[^)]*\)'
        new_badge = f'![Version](https://img.shields.io/badge/version-{__version__}-blue.svg)'
        content = re.sub(version_badge_pattern, new_badge, content)
        
        # 更新下载表格中的版本信息
        # 匹配特定版本行
        version_row_pattern = r'\|\s*v[\d\.]+\s*\|\s*Windows\s*\|\s*\[ImageClassifier_v[\d\.]+\.exe\]\([^)]+\)\s*\|\s*~\d+MB\s*\|'
        new_version_row = f'| v{__version__} | Windows | [ImageClassifier_v{__version__}.exe]({download_urls["specific_version"]}) | ~86MB |'
        content = re.sub(version_row_pattern, new_version_row, content)
        
        # 更新 Latest 行
        latest_row_pattern = r'\|\s*Latest\s*\|\s*Windows\s*\|\s*\[ImageClassifier_latest\.exe\]\([^)]+\)\s*\|\s*~\d+MB\s*\|'
        new_latest_row = f'| Latest | Windows | [ImageClassifier_latest.exe]({download_urls["latest"]}) | ~86MB |'
        content = re.sub(latest_row_pattern, new_latest_row, content)
        
        # 更新发布流程中的示例版本号
        release_example_pattern = r'推送版本标签（如 `v[\d\.]+`）'
        new_release_example = f'推送版本标签（如 `v{__version__}`）'
        content = re.sub(release_example_pattern, new_release_example, content)
        
        # 更新最新版本章节
        latest_version_pattern = r'### 🎯 最新版本 - v[\d\.]+ \([\d-]+\)'
        new_latest_version = f'### 🎯 最新版本 - v{__version__} (2025-08-06)'
        content = re.sub(latest_version_pattern, new_latest_version, content)
        
        # 检查是否有更改
        if content != original_content:
            # 备份原文件
            backup_path = readme_path.with_suffix('.md.bak')
            with open(backup_path, 'w', encoding='utf-8') as f:
                f.write(original_content)
            print(f"📝 已备份原文件到: {backup_path}")
            
            # 写入更新后的内容
            with open(readme_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            print(f"✅ README.md 已更新到版本 {__version__}")
            return True
        else:
            print("ℹ️  README.md 版本信息已经是最新的")
            return True
            
    except Exception as e:
        print(f"❌ 更新README.md失败: {e}")
        return False

def update_changelog():
    """更新CHANGELOG.md（如果存在）"""
    changelog_path = Path("CHANGELOG.md")
    
    if not changelog_path.exists():
        print("ℹ️  CHANGELOG.md 不存在，跳过")
        return True
    
    try:
        with open(changelog_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 检查最新版本是否已存在
        if f"## [{__version__}]" in content:
            print(f"ℹ️  CHANGELOG.md 已包含版本 {__version__}")
            return True
        
        print(f"⚠️  需要手动更新 CHANGELOG.md 添加版本 {__version__}")
        return True
        
    except Exception as e:
        print(f"❌ 检查CHANGELOG.md失败: {e}")
        return False

def update_gitlab_ci():
    """检查GitLab CI配置是否需要更新"""
    ci_path = Path(".gitlab-ci.yml")
    
    if not ci_path.exists():
        print("ℹ️  .gitlab-ci.yml 不存在，跳过")
        return True
    
    try:
        with open(ci_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 检查是否有硬编码的版本号需要更新
        version_matches = re.findall(r'v?[\d]+\.[\d]+\.[\d]+', content)
        old_versions = [v for v in version_matches if v != __version__ and v != __version__.lstrip('v')]
        
        if old_versions:
            print(f"⚠️  .gitlab-ci.yml 可能包含旧版本号: {set(old_versions)}")
            print("   建议检查并更新相关版本引用")
        else:
            print("ℹ️  .gitlab-ci.yml 版本信息看起来是最新的")
        
        return True
        
    except Exception as e:
        print(f"❌ 检查.gitlab-ci.yml失败: {e}")
        return False

def validate_version_consistency():
    """验证版本一致性"""
    print(f"🔍 验证版本一致性...")
    
    files_to_check = [
        ("main.py", r'setApplicationVersion\(["\']([^"\']+)["\']'),
        ("ui/main_window.py", r'self\.version = ["\']([^"\']+)["\']'),
        ("build.py", r'version = ["\']([^"\']+)["\']'),
    ]
    
    inconsistent_files = []
    
    for file_path, pattern in files_to_check:
        path = Path(file_path)
        if path.exists():
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                matches = re.findall(pattern, content)
                if matches and matches[0] != __version__:
                    inconsistent_files.append((file_path, matches[0]))
                    
            except Exception as e:
                print(f"⚠️  无法检查 {file_path}: {e}")
    
    if inconsistent_files:
        print("❌ 发现版本不一致:")
        for file_path, found_version in inconsistent_files:
            print(f"   {file_path}: {found_version} (应为 {__version__})")
        return False
    else:
        print("✅ 所有检查的文件版本一致")
        return True

def main():
    """主函数"""
    from _version_ import print_version_info
    
    print("=" * 60)
    print("📝 版本文档更新工具")
    print("=" * 60)
    
    print_version_info()
    
    print("\n🔄 开始更新文档...")
    
    success = True
    
    # 更新各种文档
    if not update_readme_version():
        success = False
    
    if not update_changelog():
        success = False
    
    if not update_gitlab_ci():
        success = False
    
    # 验证版本一致性
    if not validate_version_consistency():
        success = False
    
    print("\n" + "=" * 60)
    if success:
        print("✅ 版本文档更新完成!")
        print(f"📋 当前版本: {__version__}")
        print("💡 提示: 记得提交更改到版本控制系统")
    else:
        print("⚠️  更新过程中遇到一些问题，请检查上述警告")
    print("=" * 60)

if __name__ == "__main__":
    main()
