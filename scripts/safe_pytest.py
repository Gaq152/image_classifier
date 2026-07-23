"""在内存和时间限制内运行 pytest，并确保清理整个进程树。"""

from __future__ import annotations

import argparse
import ctypes
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import psutil


DEFAULT_MAX_MEMORY_MB = 2048
DEFAULT_TIMEOUT_SECONDS = 600
MEMORY_LIMIT_EXIT_CODE = 137
TIMEOUT_EXIT_CODE = 124
INTERRUPTED_EXIT_CODE = 130


@dataclass(frozen=True)
class RunResult:
    """受限子进程的运行结果。"""

    exit_code: int
    peak_memory_mb: float
    stop_reason: str | None = None
    hard_memory_limit: bool = False


class WindowsJobMemoryLimit:
    """使用 Windows Job Object 为整个子进程树设置硬内存上限。"""

    JOB_OBJECT_LIMIT_JOB_MEMORY = 0x00000200
    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
    JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS = 9

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_uint64),
            ("WriteOperationCount", ctypes.c_uint64),
            ("OtherOperationCount", ctypes.c_uint64),
            ("ReadTransferCount", ctypes.c_uint64),
            ("WriteTransferCount", ctypes.c_uint64),
            ("OtherTransferCount", ctypes.c_uint64),
        ]

    class BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", ctypes.c_uint32),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", ctypes.c_uint32),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", ctypes.c_uint32),
            ("SchedulingClass", ctypes.c_uint32),
        ]

    class EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        pass

    EXTENDED_LIMIT_INFORMATION._fields_ = [
        ("BasicLimitInformation", BASIC_LIMIT_INFORMATION),
        ("IoInfo", IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]

    def __init__(self, max_memory_bytes: int):
        if os.name != "nt":
            raise OSError("Windows Job Object 仅在 Windows 上可用")

        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._configure_api()
        self._handle = self._kernel32.CreateJobObjectW(None, None)
        if not self._handle:
            raise ctypes.WinError(ctypes.get_last_error())

        information = self.EXTENDED_LIMIT_INFORMATION()
        information.BasicLimitInformation.LimitFlags = (
            self.JOB_OBJECT_LIMIT_JOB_MEMORY
            | self.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        )
        information.JobMemoryLimit = max_memory_bytes
        success = self._kernel32.SetInformationJobObject(
            self._handle,
            self.JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS,
            ctypes.byref(information),
            ctypes.sizeof(information),
        )
        if not success:
            error = ctypes.WinError(ctypes.get_last_error())
            self.close()
            raise error

    def _configure_api(self) -> None:
        """声明 Win32 API 参数类型，避免 64 位句柄被截断。"""
        from ctypes import wintypes

        self._kernel32.CreateJobObjectW.argtypes = [
            ctypes.c_void_p,
            wintypes.LPCWSTR,
        ]
        self._kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        self._kernel32.SetInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        self._kernel32.SetInformationJobObject.restype = wintypes.BOOL
        self._kernel32.AssignProcessToJobObject.argtypes = [
            wintypes.HANDLE,
            wintypes.HANDLE,
        ]
        self._kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
        self._kernel32.QueryInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.c_void_p,
        ]
        self._kernel32.QueryInformationJobObject.restype = wintypes.BOOL
        self._kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        self._kernel32.CloseHandle.restype = wintypes.BOOL

    def assign(self, child: subprocess.Popen) -> None:
        """将 pytest 根进程加入受限 Job，后续子进程会继承限制。"""
        from ctypes import wintypes

        process_handle = wintypes.HANDLE(int(child._handle))
        if not self._kernel32.AssignProcessToJobObject(self._handle, process_handle):
            raise ctypes.WinError(ctypes.get_last_error())

    def peak_memory_bytes(self) -> int:
        """读取 Job Object 记录的峰值提交内存。"""
        information = self.EXTENDED_LIMIT_INFORMATION()
        success = self._kernel32.QueryInformationJobObject(
            self._handle,
            self.JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS,
            ctypes.byref(information),
            ctypes.sizeof(information),
            None,
        )
        if not success:
            return 0
        return int(information.PeakJobMemoryUsed)

    def close(self) -> None:
        """关闭 Job；仍存活的进程会因 KILL_ON_JOB_CLOSE 被清理。"""
        if getattr(self, "_handle", None):
            self._kernel32.CloseHandle(self._handle)
            self._handle = None


def _collect_process_tree(
    root_process: psutil.Process,
    known_processes: dict[int, psutil.Process],
) -> list[psutil.Process]:
    """收集根进程及其子进程，并记录已发现的进程。"""
    processes = [root_process]
    try:
        processes.extend(root_process.children(recursive=True))
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass

    for process in processes:
        known_processes[process.pid] = process
    return processes


def _processes_memory_bytes(processes: Iterable[psutil.Process]) -> int:
    """返回仍在运行的进程总工作集。"""
    total = 0
    for process in processes:
        try:
            total += process.memory_info().rss
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return total


def _terminate_processes(processes: Iterable[psutil.Process]) -> None:
    """先终止、后强杀所有仍存活的进程。"""
    alive = []
    for process in reversed(list(processes)):
        try:
            if process.is_running():
                process.terminate()
                alive.append(process)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    _, alive = psutil.wait_procs(alive, timeout=3)
    for process in alive:
        try:
            process.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    psutil.wait_procs(alive, timeout=3)


def run_with_limits(
    command: Sequence[str],
    *,
    cwd: Path,
    env: dict[str, str],
    max_memory_mb: int,
    timeout_seconds: int,
    poll_interval: float = 0.1,
) -> RunResult:
    """运行命令并限制进程树的总内存和执行时间。"""
    creation_flags = 0
    if os.name == "nt":
        creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP

    child = subprocess.Popen(
        list(command),
        cwd=cwd,
        env=env,
        creationflags=creation_flags,
    )
    job_limit = None
    hard_memory_limit = False
    if os.name == "nt":
        try:
            job_limit = WindowsJobMemoryLimit(max_memory_mb * 1024 * 1024)
            job_limit.assign(child)
            hard_memory_limit = True
        except OSError as e:
            if job_limit is not None:
                job_limit.close()
                job_limit = None
            print(
                f"[安全测试] 警告：Windows 硬内存限制启用失败，将使用软限制: {e}",
                file=sys.stderr,
                flush=True,
            )

    root_process = psutil.Process(child.pid)
    known_processes: dict[int, psutil.Process] = {child.pid: root_process}
    memory_limit_bytes = max_memory_mb * 1024 * 1024
    started_at = time.monotonic()
    peak_memory_bytes = 0
    stop_reason = None

    try:
        while child.poll() is None:
            processes = _collect_process_tree(root_process, known_processes)
            current_memory_bytes = _processes_memory_bytes(processes)
            peak_memory_bytes = max(peak_memory_bytes, current_memory_bytes)

            if current_memory_bytes > memory_limit_bytes:
                stop_reason = "memory"
                print(
                    f"\n[安全测试] 内存达到 {current_memory_bytes / 1024 / 1024:.1f} MB，"
                    f"超过上限 {max_memory_mb} MB，正在终止测试进程树。",
                    file=sys.stderr,
                    flush=True,
                )
                break

            elapsed = time.monotonic() - started_at
            if elapsed > timeout_seconds:
                stop_reason = "timeout"
                print(
                    f"\n[安全测试] 运行超过 {timeout_seconds} 秒，正在终止测试进程树。",
                    file=sys.stderr,
                    flush=True,
                )
                break

            time.sleep(poll_interval)
    except KeyboardInterrupt:
        stop_reason = "interrupted"
        print("\n[安全测试] 收到中断，正在清理测试进程树。", file=sys.stderr)
    finally:
        if stop_reason is not None or child.poll() is None:
            _terminate_processes(known_processes.values())

    job_peak_memory_bytes = 0
    if job_limit is not None:
        job_peak_memory_bytes = job_limit.peak_memory_bytes()
        job_limit.close()

    if (
        stop_reason is None
        and hard_memory_limit
        and child.returncode not in (None, 0)
        and job_peak_memory_bytes >= int(memory_limit_bytes * 0.95)
    ):
        stop_reason = "memory"
        print(
            "\n[安全测试] Windows 硬内存上限已阻止继续分配，测试进程已终止。",
            file=sys.stderr,
            flush=True,
        )

    if stop_reason == "memory":
        exit_code = MEMORY_LIMIT_EXIT_CODE
    elif stop_reason == "timeout":
        exit_code = TIMEOUT_EXIT_CODE
    elif stop_reason == "interrupted":
        exit_code = INTERRUPTED_EXIT_CODE
    else:
        exit_code = child.wait()

    return RunResult(
        exit_code=exit_code,
        peak_memory_mb=peak_memory_bytes / 1024 / 1024,
        stop_reason=stop_reason,
        hard_memory_limit=hard_memory_limit,
    )


def build_pytest_command(pytest_args: Sequence[str]) -> list[str]:
    """构造仅加载项目所需插件的 pytest 命令。"""
    return [
        sys.executable,
        "-m",
        "pytest",
        "-p",
        "pytestqt.plugin",
        *pytest_args,
    ]


def parse_args(argv: Sequence[str] | None = None) -> tuple[argparse.Namespace, list[str]]:
    """解析运行器参数，并保留其余参数传给 pytest。"""
    parser = argparse.ArgumentParser(description="在资源限制内安全运行 pytest")
    parser.add_argument(
        "--max-memory-mb",
        type=int,
        default=DEFAULT_MAX_MEMORY_MB,
        help=f"pytest 进程树内存上限，默认 {DEFAULT_MAX_MEMORY_MB} MB",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"总超时秒数，默认 {DEFAULT_TIMEOUT_SECONDS} 秒",
    )
    args, pytest_args = parser.parse_known_args(argv)
    if pytest_args[:1] == ["--"]:
        pytest_args = pytest_args[1:]
    if args.max_memory_mb <= 0:
        parser.error("--max-memory-mb 必须大于 0")
    if args.timeout_seconds <= 0:
        parser.error("--timeout-seconds 必须大于 0")
    return args, pytest_args


def main(argv: Sequence[str] | None = None) -> int:
    """运行受限 pytest。"""
    args, pytest_args = parse_args(argv)
    if not pytest_args:
        pytest_args = ["tests", "-q"]

    project_root = Path(__file__).resolve().parent.parent
    env = os.environ.copy()
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    env.setdefault("QT_QPA_PLATFORM", "offscreen")

    command = build_pytest_command(pytest_args)
    print(
        f"[安全测试] 内存上限: {args.max_memory_mb} MB；"
        f"总超时: {args.timeout_seconds} 秒",
        flush=True,
    )
    print(f"[安全测试] 命令: {' '.join(command)}", flush=True)

    result = run_with_limits(
        command,
        cwd=project_root,
        env=env,
        max_memory_mb=args.max_memory_mb,
        timeout_seconds=args.timeout_seconds,
    )
    protection = "硬限制 + 进程树监控" if result.hard_memory_limit else "进程树监控"
    print(f"[安全测试] 内存保护: {protection}", flush=True)
    print(f"[安全测试] 峰值内存: {result.peak_memory_mb:.1f} MB", flush=True)
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
