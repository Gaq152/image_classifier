"""安全 pytest 运行器测试。"""

import sys

import pytest

from scripts.safe_pytest import (
    DEFAULT_MAX_MEMORY_MB,
    DEFAULT_TIMEOUT_SECONDS,
    build_pytest_command,
    parse_args,
)


def test_build_pytest_command_only_loads_required_plugin():
    """运行器应显式加载 Qt 插件并透传 pytest 参数。"""
    command = build_pytest_command(["tests/unit", "-q"])

    assert command == [
        sys.executable,
        "-m",
        "pytest",
        "-p",
        "pytestqt.plugin",
        "tests/unit",
        "-q",
    ]


def test_parse_args_uses_safe_defaults():
    """没有显式配置时应使用安全默认限制。"""
    args, pytest_args = parse_args(["--", "tests/unit", "-q"])

    assert args.max_memory_mb == DEFAULT_MAX_MEMORY_MB
    assert args.timeout_seconds == DEFAULT_TIMEOUT_SECONDS
    assert pytest_args == ["tests/unit", "-q"]


@pytest.mark.parametrize(
    "option",
    ["--max-memory-mb", "--timeout-seconds"],
)
def test_parse_args_rejects_non_positive_limits(option):
    """资源限制必须是正数，避免误关闭保护。"""
    with pytest.raises(SystemExit):
        parse_args([option, "0"])
