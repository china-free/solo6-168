"""
共享库定位器模块

负责在各种部署场景下可靠地找到 time_shim 共享库。
支持以下场景（按优先级排序）：

1. 用户显式指定路径
2. 环境变量 TIME_TRAVEL_LIBRARY_PATH
3. 包内资源 (via importlib.resources，兼容 Python 3.8+)
   - 开发模式: src/python/time_travel/data/
   - pip install: site-packages/time_travel/data/
   - zipapp/zipimport: 临时解压到缓存目录
4. 项目根目录 lib/ (开发模式，兼容旧行为)
5. 系统标准路径: /usr/local/lib, /usr/lib
6. LD_LIBRARY_PATH / DYLD_LIBRARY_PATH 中的路径

设计原则:
- 职责链模式：每一种定位策略封装为独立方法，逐一尝试
- 路径绝对化：所有返回路径都经过 resolve()，确保是绝对路径
- 可观测性：记录每一步搜索路径，便于调试
- 向后兼容：保留对旧目录结构的支持
"""

import abc
import os
import sys
import tempfile
import atexit
import shutil
from pathlib import Path
from typing import List, Optional, Tuple, Union

from .exceptions import LibraryNotFoundError


# 全局缓存：已提取的临时文件路径，进程退出时自动清理
_extracted_temp_dir: Optional[Path] = None


def _cleanup_temp_dir() -> None:
    """进程退出时清理临时解压目录"""
    global _extracted_temp_dir
    if _extracted_temp_dir and _extracted_temp_dir.exists():
        shutil.rmtree(_extracted_temp_dir, ignore_errors=True)
        _extracted_temp_dir = None


atexit.register(_cleanup_temp_dir)


class LibraryLocator:
    """
    共享库定位器

    使用策略链模式依次尝试各种定位方式。
    每个 _try_* 方法返回 Optional[Path]，成功返回绝对路径，失败返回 None。
    """

    LIBRARY_NAME = "time_shim"
    ENV_VAR_NAME = "TIME_TRAVEL_LIBRARY_PATH"

    def __init__(self, library_extension: str):
        """
        Args:
            library_extension: 共享库扩展名，如 ".so" 或 ".dylib"
        """
        self.library_extension = library_extension
        self.library_filename = f"{self.LIBRARY_NAME}{library_extension}"
        self._search_log: List[Tuple[str, str]] = []

    def locate(self, explicit_path: Optional[Union[str, Path]] = None) -> Path:
        """
        查找共享库

        Args:
            explicit_path: 用户显式指定的路径，可选

        Returns:
            共享库的绝对路径

        Raises:
            LibraryNotFoundError: 所有策略都失败时抛出
        """
        self._search_log.clear()

        strategies = [
            ("用户显式指定", lambda: self._try_explicit_path(explicit_path)),
            ("环境变量", self._try_environment_variable),
            ("importlib.resources (包内资源)", self._try_package_resources),
            ("pkgutil 回退", self._try_pkgutil_fallback),
            ("项目根目录 lib/", self._try_project_lib_dir),
            ("当前工作目录 lib/", self._try_cwd_lib_dir),
            ("系统标准路径", self._try_system_paths),
            ("动态链接器路径", self._try_linker_paths),
        ]

        for strategy_name, strategy_fn in strategies:
            try:
                result = strategy_fn()
            except Exception as e:
                self._log_search(strategy_name, f"异常: {e}")
                continue

            if result is None:
                # result is None 表示该策略主动跳过（如无环境变量、无显式路径等）
                # 各策略内部已记录日志
                continue

            if result.exists():
                resolved = result.resolve()
                # 如果结果是目录（环境变量策略），需要拼接文件名
                if resolved.is_dir():
                    candidate = resolved / self.library_filename
                    if candidate.exists():
                        resolved = candidate.resolve()
                        self._log_search(strategy_name, f"✓ 找到: {resolved}")
                        return resolved
                    self._log_search(strategy_name, f"目录中未找到: {resolved}")
                    continue
                self._log_search(strategy_name, f"✓ 找到: {resolved}")
                return resolved
            else:
                self._log_search(strategy_name, f"路径不存在: {result}")

        raise LibraryNotFoundError(
            self.library_filename,
            self._build_error_message(),
        )

    def get_search_log(self) -> List[Tuple[str, str]]:
        """返回搜索日志，用于调试"""
        return list(self._search_log)

    # =========================================================================
    # 定位策略实现
    # =========================================================================

    def _try_explicit_path(
        self, explicit_path: Optional[Union[str, Path]]
    ) -> Optional[Path]:
        """策略 1: 用户显式指定路径"""
        if explicit_path is None:
            self._log_search("用户显式指定", "未提供")
            return None

        path = Path(explicit_path).expanduser()
        self._log_search("用户显式指定", f"检查: {path}")
        return path

    def _try_environment_variable(self) -> Optional[Path]:
        """策略 2: 环境变量 TIME_TRAVEL_LIBRARY_PATH"""
        env_path = os.environ.get(self.ENV_VAR_NAME)
        if not env_path:
            self._log_search("环境变量", "未设置")
            return None

        path = Path(env_path).expanduser()
        self._log_search("环境变量", f"检查: {path}")
        if path.exists() and path.is_file():
            return path

        # 如果环境变量是目录，尝试拼接文件名
        if path.is_dir():
            candidate = path / self.library_filename
            self._log_search("环境变量", f"检查目录内: {candidate}")
            if candidate.exists():
                return candidate

        return path

    def _try_package_resources(self) -> Optional[Path]:
        """
        策略 3: 使用 importlib.resources 访问包内资源

        支持三种情况:
        a) 普通文件系统安装 (pip install, pip install -e)
        b) zipapp / PyInstaller 打包 (需要临时解压)
        c) Python 3.8 / 3.9 / 3.10+ API 差异
        """
        # 先检查是否可以作为普通文件路径访问（开发/安装模式）
        data_dir = Path(__file__).resolve().parent / "data"
        direct_path = data_dir / self.library_filename
        self._log_search("importlib.resources (包内资源)", f"直接检查: {direct_path}")
        if direct_path.exists():
            return direct_path

        try:
            if sys.version_info >= (3, 9):
                result = self._try_importlib_resources_modern()
                if result is not None:
                    return result
            else:
                result = self._try_importlib_resources_legacy()
                if result is not None:
                    return result
        except Exception as e:
            self._log_search(
                "importlib.resources (包内资源)",
                f"失败: {type(e).__name__}: {e}",
            )

        # 返回直接检查的路径作为参考
        return direct_path

    def _try_importlib_resources_modern(self) -> Optional[Path]:
        """Python 3.9+: 使用 importlib.resources.files() API"""
        from importlib import resources

        try:
            data_dir = resources.files("time_travel.data")
        except (ModuleNotFoundError, TypeError):
            self._log_search("importlib.resources (包内资源)", "time_travel.data 包不可用")
            return None

        try:
            resource = data_dir.joinpath(self.library_filename)
        except Exception:
            self._log_search("importlib.resources (包内资源)", "无法拼接路径")
            return None

        # 情况 A: 资源是真实文件 (普通安装/开发模式)
        try:
            from importlib.resources import as_file

            with as_file(resource) as path:
                # as_file 返回的是上下文管理器，对于真实文件直接返回 Path
                # 对于 zip 资源会临时解压到磁盘
                resolved = Path(path).resolve()
                self._log_search(
                    "importlib.resources (包内资源)",
                    f"as_file 返回: {resolved}",
                )

                # 如果是临时解压的文件，需要复制到持久缓存目录
                # 因为 as_file 的上下文退出后临时文件可能被删除
                if not self._is_on_permanent_filesystem(resolved):
                    return self._persist_temporary_library(resolved)

                return resolved

        except Exception as e:
            self._log_search(
                "importlib.resources (包内资源)",
                f"as_file 失败: {type(e).__name__}: {e}",
            )
            return None

    def _try_importlib_resources_legacy(self) -> Optional[Path]:
        """Python 3.8: 使用旧版 importlib.resources API"""
        try:
            from importlib import resources
        except ImportError:
            import importlib_resources as resources  # type: ignore

        try:
            if resources.is_resource("time_travel.data", self.library_filename):
                # 读取二进制内容并写入临时文件
                data = resources.read_binary("time_travel.data", self.library_filename)
                return self._write_library_to_cache(data)
        except Exception as e:
            self._log_search(
                "importlib.resources (包内资源)",
                f"legacy API 失败: {type(e).__name__}: {e}",
            )

        return None

    def _try_pkgutil_fallback(self) -> Optional[Path]:
        """
        策略 4: pkgutil.get_data 回退

        当 importlib.resources 不可用时（罕见情况），
        使用更兼容的 pkgutil API。
        """
        try:
            import pkgutil

            data = pkgutil.get_data("time_travel", f"data/{self.library_filename}")
            if data is not None:
                self._log_search("pkgutil 回退", f"成功读取 {len(data)} 字节")
                return self._write_library_to_cache(data)
            else:
                self._log_search("pkgutil 回退", "未找到资源")
                return None
        except Exception as e:
            self._log_search("pkgutil 回退", f"失败: {type(e).__name__}: {e}")
            return None

    def _try_project_lib_dir(self) -> Optional[Path]:
        """
        策略 5: 项目根目录 lib/

        兼容开发模式：用户在项目根目录执行 make 后，
        库会出现在项目根目录的 lib/ 下。
        """
        found = None
        # 向上追溯，寻找包含 Makefile 的目录作为项目根
        current = Path(__file__).resolve().parent
        for _ in range(5):  # 最多向上追溯 5 层
            candidate = current / "lib" / self.library_filename
            self._log_search("项目根目录 lib/", f"检查: {candidate}")
            if candidate.exists():
                return candidate

            found = candidate  # 记录最后一次检查的路径

            parent = current.parent
            if parent == current:
                break
            current = parent

        return found

    def _try_cwd_lib_dir(self) -> Optional[Path]:
        """策略 6: 当前工作目录 lib/"""
        candidate = Path.cwd() / "lib" / self.library_filename
        self._log_search("当前工作目录 lib/", f"检查: {candidate}")
        if candidate.exists():
            return candidate
        return candidate

    def _try_system_paths(self) -> Optional[Path]:
        """策略 7: 系统标准路径"""
        system_paths = [
            Path("/usr/local/lib"),
            Path("/usr/lib"),
            Path("/opt/local/lib"),
            Path.home() / ".local" / "lib",
        ]

        last_checked = None
        for base in system_paths:
            candidate = base / self.library_filename
            self._log_search("系统标准路径", f"检查: {candidate}")
            if candidate.exists():
                return candidate
            last_checked = candidate

        return last_checked

    def _try_linker_paths(self) -> Optional[Path]:
        """
        策略 8: 动态链接器路径

        检查 LD_LIBRARY_PATH (Linux) 或 DYLD_LIBRARY_PATH (macOS)
        """
        env_vars = ["LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH", "DYLD_FALLBACK_LIBRARY_PATH"]

        any_checked = False
        last_candidate = None
        for env_var in env_vars:
            paths_str = os.environ.get(env_var)
            if not paths_str:
                continue

            for base in paths_str.split(os.pathsep):
                if not base:
                    continue
                any_checked = True
                candidate = Path(base) / self.library_filename
                self._log_search("动态链接器路径", f"检查: {candidate}")
                if candidate.exists():
                    return candidate
                last_candidate = candidate

        if not any_checked:
            self._log_search("动态链接器路径", "未设置 LD_LIBRARY_PATH/DYLD_LIBRARY_PATH")
            return None

        return last_candidate

    # =========================================================================
    # 辅助方法
    # =========================================================================

    def _log_search(self, strategy: str, message: str) -> None:
        """记录搜索日志"""
        self._search_log.append((strategy, message))

    def _is_on_permanent_filesystem(self, path: Path) -> bool:
        """
        判断路径是否在永久文件系统上

        如果是在 /tmp 或系统临时目录，则认为是临时文件。
        """
        temp_dirs = [
            Path(tempfile.gettempdir()).resolve(),
            Path("/tmp").resolve() if Path("/tmp").exists() else None,
            Path("/var/tmp").resolve() if Path("/var/tmp").exists() else None,
        ]
        temp_dirs = [d for d in temp_dirs if d is not None]

        resolved = path.resolve()
        for temp_dir in temp_dirs:
            try:
                resolved.relative_to(temp_dir)
                return False
            except ValueError:
                continue
        return True

    def _persist_temporary_library(self, temp_path: Path) -> Optional[Path]:
        """
        将临时解压的共享库复制到进程持久缓存目录

        importlib.resources.as_file 在处理 zip 中的资源时，
        会解压到临时目录，上下文退出后可能被删除。
        我们需要将其复制到一个进程生命周期内稳定的位置。
        """
        global _extracted_temp_dir

        if _extracted_temp_dir is None:
            _extracted_temp_dir = Path(
                tempfile.mkdtemp(prefix="time_travel_libs_")
            )

        dest = _extracted_temp_dir / self.library_filename
        if not dest.exists():
            self._log_search(
                "importlib.resources (包内资源)",
                f"持久化临时库到: {dest}",
            )
            shutil.copy2(temp_path, dest)
            # 确保可执行权限
            try:
                dest.chmod(dest.stat().st_mode | 0o755)
            except OSError:
                pass

        return dest

    def _write_library_to_cache(self, data: bytes) -> Optional[Path]:
        """将二进制数据写入持久缓存目录"""
        global _extracted_temp_dir

        if _extracted_temp_dir is None:
            _extracted_temp_dir = Path(
                tempfile.mkdtemp(prefix="time_travel_libs_")
            )

        dest = _extracted_temp_dir / self.library_filename
        if not dest.exists():
            self._log_search(
                "pkgutil/legacy 资源",
                f"写入缓存: {dest} ({len(data)} 字节)",
            )
            dest.write_bytes(data)
            try:
                dest.chmod(dest.stat().st_mode | 0o755)
            except OSError:
                pass

        return dest

    def _build_error_message(self) -> str:
        """构建详细的错误信息，包含所有搜索路径"""
        lines = [
            f"找不到时间劫持共享库: {self.library_filename}",
            "",
            "已尝试的搜索路径:",
        ]

        for strategy, message in self._search_log:
            lines.append(f"  [{strategy}] {message}")

        lines.extend(
            [
                "",
                "解决方法:",
                "  1. 在项目根目录执行 'make' 编译共享库",
                "  2. 使用 --library 参数显式指定路径",
                f"  3. 设置环境变量 {self.ENV_VAR_NAME}=/path/to/{self.library_filename}",
                "  4. 将共享库复制到 time_travel/data/ 目录后重新安装",
                "  5. 执行 'sudo make install' 安装到 /usr/local/lib",
            ]
        )

        return "\n".join(lines)
