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


def build_update_batch(target_exe: Path, new_file: Path, old_pid: int | None = None) -> str:
    """生成用于覆盖更新并重启的批处理脚本内容。

    改进点：
    - 等待旧进程按 PID 退出，必要时强制结束
    - 循环尝试复制到临时文件并原子替换，失败则继续等待
    - 覆盖成功后再延迟再启动，避免杀软/索引器干扰
    """
    target = str(target_exe.resolve())
    source = str(new_file.resolve())
    pid_line = f"set OLD_PID={int(old_pid)}" if old_pid else "set OLD_PID="

    lines = [
        "@echo off",
        "chcp 65001 >nul",
        "setlocal enabledelayedexpansion",
        "echo Updating...",
        pid_line,
        ":: 等待旧进程退出，必要时强杀",
        'set /a _loop=0',
        ':waitproc',
        'if not "%OLD_PID%"=="" (',
        '  tasklist /FI "PID eq %OLD_PID%" | find "%OLD_PID%" >nul',
        '  if %errorlevel%==0 (',
        '    set /a _loop+=1',
        '    if %_loop% gtr 2 taskkill /PID %OLD_PID% /T /F >nul 2>&1',
        '    ping -n 2 127.0.0.1 >nul',
        '    goto waitproc',
        '  )',
        ')',
        ":: 初始等待，确保句柄释放",
        "ping -n 3 127.0.0.1 >nul",
        ":: 尝试以临时文件方式原子替换",
        "set /a _copytries=0",
        ":copyloop",
        "set /a _copytries+=1",
        f'copy /y "{source}" "{target}.new" >nul',
        "if %errorlevel% neq 0 (",
        "    echo Waiting for file handle to release...",
        "    ping -n 2 127.0.0.1 >nul",
        "    goto copyloop",
        ")",
        "attrib -r ""{target}.new"" >nul 2>&1".format(target=target.replace('"', '""')),
        "move /y ""{target}.new"" ""{target}"" >nul 2>&1".format(target=target.replace('"', '""')),
        "if %errorlevel% neq 0 (",
        "    ren ""{target}"" ""{target}.old"" >nul 2>&1".format(target=target.replace('"', '""')),
        "    move /y ""{target}.new"" ""{target}"" >nul 2>&1".format(target=target.replace('"', '""')),
        "    del /f /q ""{target}.old"" >nul 2>&1".format(target=target.replace('"', '""')),
        "    if exist ""{target}.new"" (".format(target=target.replace('"', '""')),
        "        echo Waiting for file handle to release...",
        "        ping -n 2 127.0.0.1 >nul",
        "        goto copyloop",
        "    )",
        ")",
        ":: 覆盖成功后稍等再启动 (3s)",
        "timeout /t 3 /nobreak >nul",
        f'start "" "{target}"',
        "echo Update done.",
        "del /f /q %~f0",
    ]
    return "\r\n".join(lines) + "\r\n"


def _escape_win_path(path: str) -> str:
    return path.replace('"', '""')


def ensure_persistent_updater(target_exe: Path) -> Path:
    """在当前程序目录下创建/覆盖通用更新脚本 update/update.bat，并返回其路径。

    统一一个脚本：
    - 无参数：自行从 update/ 目录寻找最新包；若不存在则联机下载 latest/manifest.json 并保存到 update/；完成后安装并删除安装包
    - 有参数：使用传入的新包路径进行安装（程序内调用），完成后删除该包
    """
    exe_path = target_exe.resolve()
    exe_dir = exe_path.parent
    update_dir = exe_dir / "update"
    update_dir.mkdir(parents=True, exist_ok=True)
    batch_path = update_dir / "update.bat"

    manifest_url = (
        "https://gitlab.desauto.cn/api/v4/projects/820/packages/generic/image_classifier/latest/manifest.json"
    )
    escaped_target = _escape_win_path(str(exe_path))
    escaped_dir = _escape_win_path(str(exe_dir))
    escaped_update = _escape_win_path(str(update_dir))
    exe_name = exe_path.name

    content = (
        "@echo off\r\n"
        "chcp 65001 >nul\r\n"
        "setlocal enabledelayedexpansion\r\n"
        f"set TARGET=\"{escaped_target}\"\r\n"
        f"set TARGET_DIR=\"{escaped_dir}\"\r\n"
        f"set EXE_NAME={exe_name}\r\n"
        "set UPDATE_DIR=%~dp0\r\n"
        f"set MANIFEST_URL={manifest_url}\r\n"
        "set TOKEN=%IMAGE_CLASSIFIER_UPDATE_TOKEN%\r\n"
        "echo Updating...\r\n"
        "REM 1) 解析参数或本地已有新包\r\n"
        "set NEW_FILE=%~1\r\n"
        "if not \"%NEW_FILE%\"==\"\" goto do_update\r\n"
        "for %%F in (\"%UPDATE_DIR%\*%EXE_NAME:~0,-4%*.exe\") do set NEW_FILE=%%~fF\r\n"
        "if not \"%NEW_FILE%\"==\"\" goto do_update\r\n"
        "REM 2) 本地无包则联机下载 latest/manifest.json 到 UPDATE_DIR\r\n"
        "powershell -NoProfile -Command \"$t=$env:IMAGE_CLASSIFIER_UPDATE_TOKEN; $url='%MANIFEST_URL%'; $h=@{}; if($t){$h[''PRIVATE-TOKEN'']=$t}; $m=(Invoke-WebRequest -UseBasicParsing -Headers $h -Uri $url).Content | ConvertFrom-Json; $d='%UPDATE_DIR%'; if(-not (Test-Path $d)){New-Item -ItemType Directory -Path $d|Out-Null}; $name= if($m.display_name){$m.display_name}else{[System.IO.Path]::GetFileName($m.url)}; $dest=Join-Path $d $name; Invoke-WebRequest -UseBasicParsing -Headers $h -Uri $m.url -OutFile $dest; $sha=$m.sha256; $hash=(Get-FileHash -Algorithm SHA256 $dest).Hash; if($hash -ne $sha){Write-Error 'HASH_MISMATCH'; exit 5}; Write-Output $dest\" > \"%UPDATE_DIR%download_path.tmp\"\r\n"
        "set /p NEW_FILE=<\"%UPDATE_DIR%download_path.tmp\"\r\n"
        "del /f /q \"%UPDATE_DIR%download_path.tmp\" >nul 2>&1\r\n"
        ":do_update\r\n"
        "if \"%NEW_FILE%\"==\"\" ( echo 未找到可用安装包 & exit /b 2 )\r\n"
        "for %%A in (\"%NEW_FILE%\") do set NEW_BASENAME=%%~nxA\r\n"
        "set FINAL=\"%TARGET_DIR%\\%NEW_BASENAME%\"\r\n"
        "REM 结束可能残留进程\r\n"
        "taskkill /IM \"%EXE_NAME%\" /T /F >nul 2>&1\r\n"
        "REM 原子式替换到最终新文件名 FINAL（保留新版本文件名）\r\n"
        "copy /y \"%NEW_FILE%\" \"%FINAL%.new\" >nul\r\n"
        "if errorlevel 1 ( ping -n 2 127.0.0.1 >nul & copy /y \"%NEW_FILE%\" \"%FINAL%.new\" >nul )\r\n"
        "attrib -r \"%FINAL%.new\" >nul 2>&1\r\n"
        "move /y \"%FINAL%.new\" \"%FINAL%\" >nul 2>&1\r\n"
        "if errorlevel 1 ( ren \"%FINAL%\" \"%NEW_BASENAME%.old\" >nul 2>&1 & move /y \"%FINAL%.new\" \"%FINAL%\" >nul 2>&1 & del /f /q \"%TARGET_DIR%\\%NEW_BASENAME%.old\" >nul 2>&1 )\r\n"
        "REM 如旧目标名与最终名不同，清理旧 EXE\r\n"
        "if /I not \"%FINAL%\"==\"%TARGET%\" del /f /q \"%TARGET%\" >nul 2>&1\r\n"
        "REM 清理安装包\r\n"
        "del /f /q \"%NEW_FILE%\" >nul 2>&1\r\n"
        "REM 等3秒再启动，设定工作目录为程序目录\r\n"
        "timeout /t 3 /nobreak >nul\r\n"
        "start \"\" /D \"%TARGET_DIR%\" \"%FINAL%\"\r\n"
        "echo Update done.\r\n"
    )

    batch_path.write_text(content, encoding="utf-8")
    return batch_path


def launch_self_update(target_exe: Path, new_file: Path) -> Path:
    """返回持久化更新脚本路径；脚本将接收新文件路径作为参数，由调用方启动。"""
    batch_path = ensure_persistent_updater(target_exe)
    return batch_path


