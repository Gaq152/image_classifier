#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
更新工具：拉取 manifest、比较版本、下载文件（带进度）、校验 SHA256、触发自更新。

不引入第三方依赖，使用标准库实现网络与哈希。

鉴权策略：
1) 若提供 config 中 token 则优先使用
2) 否则读取环境变量 IMAGE_CLASSIFIER_UPDATE_TOKEN
3) 否则使用内置 BUILTIN_UPDATE_TOKEN（可按需填写只读访问令牌）
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Callable, Dict, Optional
from urllib.error import HTTPError, URLError

# 可选：在企业内网环境下内置只读访问令牌，默认为空
BUILTIN_UPDATE_TOKEN = "qBo4xpZnkcphq_uT-cXA"

def resolve_token(preferred: Optional[str] = None) -> Optional[str]:
    if preferred:
        return preferred
    env_val = os.getenv('IMAGE_CLASSIFIER_UPDATE_TOKEN')
    if env_val:
        return env_val
    return BUILTIN_UPDATE_TOKEN or None
from urllib.request import Request, urlopen


def sha256_file(file_path: Path, chunk_size: int = 1024 * 1024) -> str:
    hasher = hashlib.sha256()
    with open(file_path, 'rb') as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def _build_request(url: str, token: Optional[str]) -> Request:
    req = Request(url)
    # GitLab 私有仓库鉴权：
    # - 若 token 形如 "user:token" 或以 "Basic " 开头，则使用 Basic Auth
    # - 若 token 以 "Bearer " 开头，则使用 Bearer Token
    # - 其他情况，默认使用 PRIVATE-TOKEN 头
    if token:
        token = token.strip()
        try:
            if token.lower().startswith('basic '):
                # 直接传入完整的 Basic 头
                req.add_header('Authorization', token)
            elif ':' in token:
                # user:token -> Basic
                import base64
                b64 = base64.b64encode(token.encode('utf-8')).decode('ascii')
                req.add_header('Authorization', f'Basic {b64}')
            elif token.lower().startswith('bearer '):
                req.add_header('Authorization', token)
            else:
                req.add_header('PRIVATE-TOKEN', token)
        except Exception:
            # 兜底：按 PRIVATE-TOKEN 处理
            req.add_header('PRIVATE-TOKEN', token)
    # 避免被缓存
    req.add_header('Cache-Control', 'no-cache')
    req.add_header('Pragma', 'no-cache')
    return req


def fetch_manifest(url: str, token: Optional[str] = None, timeout: int = 8) -> Dict:
    token = resolve_token(token)
    req = _build_request(url, token)
    try:
        with urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            return json.loads(data.decode('utf-8'))
    except HTTPError as e:
        # 401/403 代表需要鉴权
        raise RuntimeError(f"拉取manifest失败: HTTP {e.code}")
    except URLError as e:
        raise RuntimeError(f"网络错误: {e}")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"manifest解析失败: {e}")


def download_with_progress(url: str, dest: Path, token: Optional[str] = None,
                           progress_cb: Optional[Callable[[int, Optional[int]], None]] = None,
                           timeout: int = 20, chunk_size: int = 1024 * 256) -> None:
    token = resolve_token(token)
    req = _build_request(url, token)
    with urlopen(req, timeout=timeout) as resp, open(dest, 'wb') as f:
        total = resp.length if hasattr(resp, 'length') else None
        downloaded = 0
        while True:
            chunk = resp.read(chunk_size)
            if not chunk:
                break
            f.write(chunk)
            downloaded += len(chunk)
            if progress_cb:
                progress_cb(downloaded, total)


def build_update_batch(target_exe: Path, new_file: Path) -> str:
    """生成用于覆盖更新并重启的批处理脚本内容。

    改进点：
    - 初始等待 3 秒，确保主进程和文件句柄释放
    - 循环尝试覆盖，失败则继续等待
    - 覆盖成功后再延迟 1 秒再启动，避免杀软/索引器干扰
    """
    target = str(target_exe.resolve())
    source = str(new_file.resolve())
    lines = [
        "@echo off",
        "setlocal enabledelayedexpansion",
        "echo Updating...",
        ":: 初始等待，确保主程序完全退出",
        "ping -n 4 127.0.0.1 >nul",
        ":waitloop",
        ":: 尝试覆盖",
        f'copy /y "{source}" "{target}" >nul',
        "if %errorlevel% neq 0 (",
        "    echo Waiting for file handle to release...",
        "    ping -n 2 127.0.0.1 >nul",
        "    goto waitloop",
        ")",
        ":: 覆盖成功后稍等再启动",
        "ping -n 2 127.0.0.1 >nul",
        f'start "" "{target}"',
        "echo Update done.",
        "del /f /q %~f0",
    ]
    return "\r\n".join(lines) + "\r\n"


def launch_self_update(target_exe: Path, new_file: Path) -> Path:
    """写入批处理脚本并返回路径；由调用方决定何时启动、是否退出应用。"""
    temp_dir = Path(os.getenv('TEMP') or Path.cwd())
    batch_path = temp_dir / f"update_{int(time.time())}.cmd"
    batch_path.write_text(build_update_batch(target_exe, new_file), encoding='utf-8')
    return batch_path


