"""
进程启动器模块

负责设置环境变量并启动目标进程，使其加载时间劫持库。
支持灵活的环境变量配置和子进程管理。
"""

import os
import platform
import subprocess
import sys
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Optional, Union

from .exceptions import (
    LibraryNotFoundError,
    UnsupportedPlatformError,
    CommandExecutionError,
)
from .library_locator import LibraryLocator
from .time_simulator import TimeOffset


class LibraryLoaderStrategy(ABC):
    """
    共享库加载策略抽象基类

    不同操作系统有不同的库注入机制，使用策略模式便于扩展：
    - Linux: LD_PRELOAD
    - macOS: DYLD_INSERT_LIBRARIES (需要额外的签名配置)
    - Windows: 需要使用 Detours 等其他技术
    """

    @abstractmethod
    def get_environment_variable_name(self) -> str:
        """返回环境变量名称"""
        pass

    @abstractmethod
    def get_library_extension(self) -> str:
        """返回共享库文件扩展名"""
        pass

    def validate_platform(self) -> None:
        """验证当前平台是否支持"""
        current_platform = platform.system().lower()
        if current_platform not in self.get_supported_platforms():
            raise UnsupportedPlatformError(current_platform)

    @abstractmethod
    def get_supported_platforms(self) -> List[str]:
        """返回支持的平台列表"""
        pass


class LinuxLibraryLoader(LibraryLoaderStrategy):
    """Linux 平台的库加载策略"""

    def get_environment_variable_name(self) -> str:
        return "LD_PRELOAD"

    def get_library_extension(self) -> str:
        return ".so"

    def get_supported_platforms(self) -> List[str]:
        return ["linux"]


class MacOSLibraryLoader(LibraryLoaderStrategy):
    """macOS 平台的库加载策略"""

    def get_environment_variable_name(self) -> str:
        return "DYLD_INSERT_LIBRARIES"

    def get_library_extension(self) -> str:
        return ".dylib"

    def get_supported_platforms(self) -> List[str]:
        return ["darwin"]


class LibraryLoaderFactory:
    """
    库加载策略工厂

    根据当前操作系统自动选择合适的加载策略。
    """

    @staticmethod
    def get_strategy() -> LibraryLoaderStrategy:
        """
        获取当前平台的库加载策略

        Returns:
            LibraryLoaderStrategy 实例

        Raises:
            UnsupportedPlatformError: 当平台不支持时
        """
        system = platform.system().lower()
        strategies = {
            "linux": LinuxLibraryLoader,
            "darwin": MacOSLibraryLoader,
        }

        if system not in strategies:
            raise UnsupportedPlatformError(system)

        return strategies[system]()


class ProcessLauncher:
    """
    进程启动器类

    核心职责:
    1. 查找并验证时间劫持共享库
    2. 构造注入用的环境变量
    3. 启动目标进程并传递偏移量
    4. 管理子进程的生命周期

    设计要点:
    - 使用策略模式支持多平台
    - 环境变量传递支持子进程继承
    - 提供同步和异步两种执行模式
    """

    def __init__(
        self,
        library_path: Optional[Union[str, Path]] = None,
        extra_env: Optional[Dict[str, str]] = None,
    ):
        """
        初始化进程启动器

        Args:
            library_path: 共享库路径，默认在项目 lib 目录下查找
            extra_env: 额外传递给子进程的环境变量
        """
        self.strategy = LibraryLoaderFactory.get_strategy()
        self.strategy.validate_platform()

        self.library_path = self._resolve_library_path(library_path)
        self.extra_env = extra_env or {}

    def launch(
        self,
        command: List[str],
        time_offset: TimeOffset,
        working_dir: Optional[Union[str, Path]] = None,
        inherit_env: bool = True,
        capture_output: bool = False,
        interactive: bool = True,
    ) -> int:
        """
        启动目标进程

        Args:
            command: 要执行的命令及其参数列表
            time_offset: 时间偏移量
            working_dir: 工作目录
            inherit_env: 是否继承当前进程的环境变量
            capture_output: 是否捕获标准输出和标准错误
            interactive: 是否使用交互模式（继承标准输入输出）

        Returns:
            子进程的退出码

        Raises:
            CommandExecutionError: 当命令执行失败时
        """
        env = self._build_environment(time_offset, inherit_env)

        try:
            if not interactive or capture_output:
                result = subprocess.run(
                    command,
                    env=env,
                    cwd=working_dir,
                    capture_output=capture_output,
                    text=True,
                )
                return result.returncode
            else:
                result = subprocess.run(
                    command,
                    env=env,
                    cwd=working_dir,
                    stdin=sys.stdin,
                    stdout=sys.stdout,
                    stderr=sys.stderr,
                )
                return result.returncode
        except FileNotFoundError:
            raise CommandExecutionError(
                " ".join(command),
                -1,
                f"找不到命令: {command[0]}",
            )
        except PermissionError:
            raise CommandExecutionError(
                " ".join(command),
                -1,
                f"没有执行权限: {command[0]}",
            )

    def launch_async(
        self,
        command: List[str],
        time_offset: TimeOffset,
        working_dir: Optional[Union[str, Path]] = None,
        inherit_env: bool = True,
        capture_output: bool = False,
    ) -> subprocess.Popen:
        """
        异步启动目标进程（不等待结束）

        Args:
            command: 要执行的命令及其参数列表
            time_offset: 时间偏移量
            working_dir: 工作目录
            inherit_env: 是否继承当前进程的环境变量
            capture_output: 是否捕获标准输出和标准错误

        Returns:
            subprocess.Popen 对象，可用于后续管理
        """
        env = self._build_environment(time_offset, inherit_env)

        stdout = subprocess.PIPE if capture_output else sys.stdout
        stderr = subprocess.PIPE if capture_output else sys.stderr
        stdin = sys.stdin

        return subprocess.Popen(
            command,
            env=env,
            cwd=working_dir,
            stdin=stdin,
            stdout=stdout,
            stderr=stderr,
            text=True,
        )

    def _build_environment(
        self,
        time_offset: TimeOffset,
        inherit_env: bool,
    ) -> Dict[str, str]:
        """
        构建子进程环境变量

        核心环境变量:
        - LD_PRELOAD (或 DYLD_INSERT_LIBRARIES): 时间劫持库路径
        - TIME_TRAVEL_ENABLED: 启用标记
        - TIME_TRAVEL_OFFSET_SEC: 秒级偏移量
        - TIME_TRAVEL_OFFSET_NSEC: 纳秒级偏移量
        """
        env = dict(os.environ) if inherit_env else {}

        env.update(self.extra_env)

        env[self.strategy.get_environment_variable_name()] = str(self.library_path)
        env["TIME_TRAVEL_ENABLED"] = "1"
        env["TIME_TRAVEL_OFFSET_SEC"] = str(time_offset.seconds)
        env["TIME_TRAVEL_OFFSET_NSEC"] = str(time_offset.nanoseconds)

        return env

    def _resolve_library_path(
        self, library_path: Optional[Union[str, Path]]
    ) -> Path:
        """
        解析并验证共享库路径

        使用 LibraryLocator 支持多种部署场景：
        - 用户显式指定路径
        - 环境变量 TIME_TRAVEL_LIBRARY_PATH
        - 包内资源 (importlib.resources)
        - 项目根目录 lib/ (开发模式)
        - 系统标准路径 (/usr/local/lib 等)
        - 动态链接器路径
        """
        locator = LibraryLocator(self.strategy.get_library_extension())
        return locator.locate(library_path)
