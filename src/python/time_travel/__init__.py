"""
Time Travel - 进程级时间穿梭模拟器

利用 LD_PRELOAD 技术劫持系统调用，让目标进程及其子进程
看到自定义的时间，而不影响宿主机的真实时间。
"""

from .exceptions import (
    TimeTravelError,
    InvalidDateError,
    LibraryNotFoundError,
    UnsupportedPlatformError,
)
from .time_simulator import TimeSimulator
from .process_launcher import ProcessLauncher
from .cli import main

__version__ = "1.0.0"
__all__ = [
    "TimeTravelError",
    "InvalidDateError",
    "LibraryNotFoundError",
    "UnsupportedPlatformError",
    "TimeSimulator",
    "ProcessLauncher",
    "main",
]
