"""
自定义异常类模块

定义了 Time Travel 工具可能抛出的所有异常类型，
保持异常层级清晰，便于上层捕获和处理。
"""


class TimeTravelError(Exception):
    """
    基础异常类，所有 Time Travel 相关异常的基类。
    """

    pass


class InvalidDateError(TimeTravelError):
    """
    当提供的日期格式无效或无法解析时抛出。

    示例场景:
    - 日期字符串格式错误
    - 日期不存在（如 2025-02-30）
    - 相对时间表达式无效
    """

    def __init__(self, date_str: str, message: str = None):
        self.date_str = date_str
        if message is None:
            message = f"无法解析日期: {date_str}"
        super().__init__(message)


class LibraryNotFoundError(TimeTravelError):
    """
    当找不到编译好的 time_shim 共享库时抛出。

    示例场景:
    - 未执行 make 编译
    - 编译的库路径不正确
    - 库文件被删除或移动
    """

    def __init__(self, library_path: str, message: str = None):
        self.library_path = library_path
        if message is None:
            message = (
                f"找不到时间劫持库: {library_path}\n"
                f"请先执行 'make' 命令编译共享库"
            )
        super().__init__(message)


class UnsupportedPlatformError(TimeTravelError):
    """
    当在不支持的操作系统上运行时抛出。

    目前仅支持 Linux 系统（因为需要 LD_PRELOAD 机制）。
    macOS 使用 DYLD_INSERT_LIBRARIES，可后续扩展支持。
    Windows 需要其他技术方案（如 Detours）。
    """

    def __init__(self, platform: str, message: str = None):
        self.platform = platform
        if message is None:
            message = (
                f"不支持的操作系统: {platform}\n"
                f"当前仅支持 Linux 系统（LD_PRELOAD 机制）"
            )
        super().__init__(message)


class CommandExecutionError(TimeTravelError):
    """
    当目标命令执行失败时抛出。

    示例场景:
    - 命令不存在
    - 命令执行异常退出
    - 没有执行权限
    """

    def __init__(self, command: str, return_code: int, message: str = None):
        self.command = command
        self.return_code = return_code
        if message is None:
            message = f"命令执行失败 (退出码 {return_code}): {command}"
        super().__init__(message)
