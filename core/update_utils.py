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

import base64
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from utils.paths import get_update_dir

# Public GitHub Releases 默认无需令牌，保留可选令牌能力用于私有源
BUILTIN_UPDATE_TOKEN = ""
READY_UPDATE_METADATA = "update_ready.json"


class DownloadCancelled(RuntimeError):
    """用户主动取消更新下载。"""


def resolve_token(preferred: Optional[str] = None) -> Optional[str]:
    if preferred:
        return preferred
    env_val = os.getenv('IMAGE_CLASSIFIER_UPDATE_TOKEN')
    if env_val:
        return env_val
    return BUILTIN_UPDATE_TOKEN or None


def sha256_file(
    file_path: Path,
    chunk_size: int = 1024 * 1024,
    cancel_cb: Optional[Callable[[], bool]] = None,
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> str:
    """计算文件 SHA256，并支持取消和进度回调。"""
    hasher = hashlib.sha256()
    processed = 0
    total = file_path.stat().st_size
    with open(file_path, 'rb') as f:
        while True:
            if cancel_cb and cancel_cb():
                raise DownloadCancelled("更新下载已取消")
            chunk = f.read(chunk_size)
            if not chunk:
                break
            hasher.update(chunk)
            processed += len(chunk)
            if progress_cb:
                progress_cb(processed, total)
    return hasher.hexdigest()


def _build_request(url: str, token: Optional[str]) -> Request:
    req = Request(url)
    # 鉴权策略（兼容多种后端）：
    # - 若 token 形如 "user:token" 或以 "Basic " 开头，则使用 Basic Auth
    # - 若 token 以 "Bearer " 开头，则使用 Bearer Token
    # - 其他情况，默认使用 Authorization 头
    # - GitHub Public Releases 默认无需 token
    if token:
        token = token.strip()
        try:
            if token.lower().startswith('basic '):
                # 直接传入完整的 Basic 头
                req.add_header('Authorization', token)
            elif ':' in token:
                # user:token -> Basic
                b64 = base64.b64encode(token.encode('utf-8')).decode('ascii')
                req.add_header('Authorization', f'Basic {b64}')
            elif token.lower().startswith('bearer '):
                req.add_header('Authorization', token)
            else:
                req.add_header('Authorization', f'Bearer {token}')
        except Exception:
            # 兜底：按 Bearer 处理
            req.add_header('Authorization', f'Bearer {token}')
    # 避免被缓存
    req.add_header('Cache-Control', 'no-cache')
    req.add_header('Pragma', 'no-cache')
    return req


def fetch_manifest(url: str, token: Optional[str] = None, timeout: int = 8, retries: int = 3) -> Dict:
    """拉取 manifest.json，支持自动重试机制

    Args:
        url: manifest URL
        token: 访问令牌
        timeout: 超时时间（秒）
        retries: 最大重试次数，默认3次

    Returns:
        解析后的 manifest 字典

    Raises:
        RuntimeError: 拉取或解析失败
    """
    token = resolve_token(token)
    req = _build_request(url, token)

    last_error = None
    for attempt in range(retries + 1):
        try:
            with urlopen(req, timeout=timeout) as resp:
                data = resp.read()
                return json.loads(data.decode('utf-8'))
        except HTTPError as e:
            # 对于临时性错误（502, 503, 504）进行重试
            if e.code in (502, 503, 504) and attempt < retries:
                wait_time = 0.5 * (2 ** attempt)  # 指数退避: 0.5s, 1s, 2s
                time.sleep(wait_time)
                last_error = f"HTTP {e.code}"
                continue
            # 永久性错误或重试耗尽，直接抛出
            raise RuntimeError(f"拉取manifest失败: HTTP {e.code}")
        except URLError as e:
            # 网络错误也重试
            if attempt < retries:
                wait_time = 0.5 * (2 ** attempt)
                time.sleep(wait_time)
                last_error = str(e)
                continue
            raise RuntimeError(f"网络错误: {e}")
        except json.JSONDecodeError as e:
            # JSON 解析错误不重试
            raise RuntimeError(f"manifest解析失败: {e}")

    # 理论上不会到这里，但为了安全
    raise RuntimeError(f"拉取manifest失败: {last_error}")


def download_with_progress(url: str, dest: Path, token: Optional[str] = None,
                           progress_cb: Optional[Callable[[int, Optional[int]], None]] = None,
                           timeout: int = 20, chunk_size: int = 1024 * 256,
                           cancel_cb: Optional[Callable[[], bool]] = None,
                           response_cb: Optional[Callable[[Any], None]] = None) -> None:
    """下载到指定路径，支持协作式取消及由调用方关闭网络响应。"""
    token = resolve_token(token)
    req = _build_request(url, token)
    response = None
    try:
        response = urlopen(req, timeout=timeout)
        if response_cb:
            response_cb(response)
        with response, open(dest, 'wb') as f:
            total_header = response.headers.get('Content-Length')
            total = int(total_header) if total_header else None
            downloaded = 0
            while True:
                if cancel_cb and cancel_cb():
                    raise DownloadCancelled("更新下载已取消")
                chunk = response.read(chunk_size)
                if not chunk:
                    break
                if cancel_cb and cancel_cb():
                    raise DownloadCancelled("更新下载已取消")
                f.write(chunk)
                downloaded += len(chunk)
                if progress_cb:
                    progress_cb(downloaded, total)
    finally:
        if response_cb:
            response_cb(None)


def _ready_metadata_path(update_dir: Optional[Path] = None) -> Path:
    return (update_dir or get_update_dir()) / READY_UPDATE_METADATA


def save_ready_update(
    package_path: Path,
    version: str,
    sha256: str,
    size_bytes: Optional[int] = None,
) -> Dict[str, Any]:
    """原子写入已完成更新包标记；只有带此标记的包才允许安装。"""
    package_path = package_path.resolve()
    update_dir = package_path.parent
    actual_size = package_path.stat().st_size
    metadata = {
        "completed": True,
        "version": str(version),
        "filename": package_path.name,
        "sha256": str(sha256).lower(),
        "size_bytes": int(size_bytes or actual_size),
        "actual_size_bytes": actual_size,
        "completed_at": int(time.time()),
    }
    metadata_path = _ready_metadata_path(update_dir)
    temp_path = metadata_path.with_suffix(metadata_path.suffix + ".tmp")
    temp_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(temp_path, metadata_path)
    return metadata


def load_ready_update(
    update_dir: Optional[Path] = None,
    verify_hash: bool = False,
) -> Optional[Dict[str, Any]]:
    """读取并验证已完成更新包标记，忽略下载中的临时文件。"""
    update_dir = (update_dir or get_update_dir()).resolve()
    metadata_path = _ready_metadata_path(update_dir)
    if not metadata_path.is_file():
        return None
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        filename = str(metadata.get("filename", ""))
        if not metadata.get("completed") or not filename:
            return None
        if Path(filename).name != filename or not filename.lower().endswith(".exe"):
            return None
        package_path = (update_dir / filename).resolve()
        if package_path.parent != update_dir or not package_path.is_file():
            return None
        actual_size = package_path.stat().st_size
        expected_size = int(metadata.get("actual_size_bytes", 0) or 0)
        if expected_size <= 0 or actual_size != expected_size:
            return None
        expected_hash = str(metadata.get("sha256", "")).lower()
        if verify_hash and expected_hash:
            if sha256_file(package_path).lower() != expected_hash:
                return None
        result = dict(metadata)
        result["path"] = package_path
        return result
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None


def discard_ready_update(
    update_dir: Optional[Path] = None,
    remove_package: bool = True,
) -> None:
    """删除完成标记，并按需删除其对应的更新包。"""
    update_dir = (update_dir or get_update_dir()).resolve()
    ready = load_ready_update(update_dir)
    if remove_package and ready:
        try:
            ready["path"].unlink(missing_ok=True)
        except OSError:
            pass
    _ready_metadata_path(update_dir).unlink(missing_ok=True)
    _ready_metadata_path(update_dir).with_suffix(".json.tmp").unlink(missing_ok=True)


def cleanup_incomplete_updates(update_dir: Optional[Path] = None) -> None:
    """清理中断下载和没有完成标记的安装包。"""
    update_dir = (update_dir or get_update_dir()).resolve()
    if not update_dir.exists():
        return
    for partial in update_dir.glob("*.part"):
        try:
            partial.unlink(missing_ok=True)
        except OSError:
            pass

    ready = load_ready_update(update_dir)
    ready_path = ready.get("path") if ready else None
    for package in update_dir.glob("ImageClassifier_v*.exe"):
        if ready_path is None or package.resolve() != ready_path:
            try:
                package.unlink(missing_ok=True)
            except OSError:
                pass
    if ready is None:
        _ready_metadata_path(update_dir).unlink(missing_ok=True)


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
        ":: 延迟删除自己并关闭窗口",
        '(goto) 2>nul & del /f /q "%~f0" & exit',
    ]
    return "\r\n".join(lines) + "\r\n"


def _escape_win_path(path: str) -> str:
    return path.replace('"', '""')


def ensure_persistent_updater(target_exe: Path) -> Path:
    """在用户目录下创建/覆盖通用更新脚本 update/update.bat，并返回其路径。

    统一一个脚本：
    - 无参数：联机下载到 .part，校验成功后再改为 .exe 并安装
    - 有参数：使用传入的新包路径进行安装（程序内调用），完成后删除该包
    """
    exe_path = target_exe.resolve()
    exe_dir = exe_path.parent
    # 使用统一的用户目录下的 update 目录
    update_dir = get_update_dir()
    update_dir.mkdir(parents=True, exist_ok=True)
    batch_path = update_dir / "update.bat"

    manifest_url = (
        "https://github.com/Gaq152/image_classifier/releases/latest/download/manifest.json"
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
        "REM 1) 程序内调用会传入已完成校验的新包\r\n"
        "set NEW_FILE=%~1\r\n"
        "if not \"%NEW_FILE%\"==\"\" goto do_update\r\n"
        "REM 2) 手动运行脚本时，只使用 .part 下载，校验后原子改名\r\n"
        "powershell -NoProfile -Command \"$t=$env:IMAGE_CLASSIFIER_UPDATE_TOKEN; $url='%MANIFEST_URL%'; $h=@{}; if($t){if($t.StartsWith('Bearer ')){$h['Authorization']=$t}else{$h['Authorization']='Bearer '+$t}}; $m=(Invoke-WebRequest -UseBasicParsing -Headers $h -Uri $url).Content | ConvertFrom-Json; $d='%UPDATE_DIR%'; if(-not (Test-Path $d)){New-Item -ItemType Directory -Path $d|Out-Null}; $name=if($m.display_name){$m.display_name}else{[System.IO.Path]::GetFileName($m.url)}; $dest=Join-Path $d $name; $partial=$dest+'.part'; Remove-Item -LiteralPath $partial -Force -ErrorAction SilentlyContinue; Invoke-WebRequest -UseBasicParsing -Headers $h -Uri $m.url -OutFile $partial; $sha=$m.sha256; $hash=(Get-FileHash -Algorithm SHA256 $partial).Hash; if($hash -ne $sha){Remove-Item -LiteralPath $partial -Force -ErrorAction SilentlyContinue; Write-Error 'HASH_MISMATCH'; exit 5}; Move-Item -LiteralPath $partial -Destination $dest -Force; Write-Output $dest\" > \"%UPDATE_DIR%download_path.tmp\"\r\n"
        "if errorlevel 1 ( del /f /q \"%UPDATE_DIR%download_path.tmp\" >nul 2>&1 & exit /b 5 )\r\n"
        "set /p NEW_FILE=<\"%UPDATE_DIR%download_path.tmp\"\r\n"
        "del /f /q \"%UPDATE_DIR%download_path.tmp\" >nul 2>&1\r\n"
        ":do_update\r\n"
        "if \"%NEW_FILE%\"==\"\" ( echo 未找到可用安装包 & exit /b 2 )\r\n"
        "if not exist \"%NEW_FILE%\" ( echo 更新包不存在 & exit /b 3 )\r\n"
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
        "del /f /q \"%UPDATE_DIR%update_ready.json\" >nul 2>&1\r\n"
        "REM 等3秒再启动，设定工作目录为程序目录\r\n"
        "timeout /t 3 /nobreak >nul\r\n"
        "start \"\" /D \"%TARGET_DIR%\" \"%FINAL%\"\r\n"
        "echo Update done.\r\n"
        "REM 延迟删除自己并关闭窗口\r\n"
        "(goto) 2>nul & del /f /q \"%~f0\" & exit\r\n"
    )

    batch_path.write_text(content, encoding="utf-8")
    return batch_path


def launch_self_update(target_exe: Path, new_file: Path) -> Path:
    """返回持久化更新脚本路径；脚本将接收新文件路径作为参数，由调用方启动。"""
    batch_path = ensure_persistent_updater(target_exe)
    return batch_path


