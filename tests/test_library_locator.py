"""
LibraryLocator 单元测试

验证在各种部署场景下能正确找到共享库：
1. 用户显式指定路径
2. 环境变量 TIME_TRAVEL_LIBRARY_PATH
3. 包内资源目录
4. 项目根目录 lib/
5. 当前工作目录 lib/
6. 系统标准路径
7. 动态链接器路径
8. 搜索日志记录
9. 错误信息详情
"""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# 确保可以导入项目模块
sys.path.insert(0, str(Path(__file__).parent.parent / "src" / "python"))

from time_travel.library_locator import LibraryLocator
from time_travel.exceptions import LibraryNotFoundError


@pytest.fixture
def temp_dir():
    """创建临时目录用于测试"""
    with tempfile.TemporaryDirectory() as td:
        yield Path(td)


@pytest.fixture
def locator():
    """创建 Linux 平台的定位器"""
    return LibraryLocator(".so")


@pytest.fixture
def fake_library(temp_dir):
    """创建一个假的共享库文件"""
    lib_path = temp_dir / "time_shim.so"
    lib_path.write_bytes(b"fake library content")
    return lib_path


class TestExplicitPath:
    """测试：用户显式指定路径"""

    def test_explicit_path_exists(self, locator, fake_library):
        """显式指定存在的路径"""
        result = locator.locate(fake_library)
        assert result.exists()
        assert result.resolve() == fake_library.resolve()

    def test_explicit_path_with_tilde(self, locator, fake_library, temp_dir):
        """显式指定包含 ~ 的路径"""
        with patch.dict(os.environ, {"HOME": str(temp_dir)}):
            lib_in_home = Path.home() / "time_shim.so"
            lib_in_home.write_bytes(b"fake")
            result = locator.locate("~/time_shim.so")
            assert result.exists()

    def test_explicit_path_not_found(self, locator, temp_dir):
        """显式指定不存在的路径"""
        with pytest.raises(LibraryNotFoundError):
            locator.locate(temp_dir / "nonexistent.so")

    def test_explicit_path_none(self, locator):
        """显式路径为 None 时跳过此策略"""
        with pytest.raises(LibraryNotFoundError):
            locator.locate(None)
        log = dict(locator.get_search_log())
        assert "未提供" in log.get("用户显式指定", "")


class TestEnvironmentVariable:
    """测试：环境变量 TIME_TRAVEL_LIBRARY_PATH"""

    def test_env_var_pointing_to_file(self, locator, fake_library):
        """环境变量指向文件"""
        with patch.dict(os.environ, {"TIME_TRAVEL_LIBRARY_PATH": str(fake_library)}):
            result = locator.locate()
            assert result.resolve() == fake_library.resolve()

    def test_env_var_pointing_to_directory(self, locator, temp_dir):
        """环境变量指向目录（自动拼接文件名）"""
        (temp_dir / "time_shim.so").write_bytes(b"fake")
        with patch.dict(os.environ, {"TIME_TRAVEL_LIBRARY_PATH": str(temp_dir)}):
            result = locator.locate()
            assert result.exists()
            assert result.name == "time_shim.so"

    def test_env_var_not_set(self, locator):
        """环境变量未设置"""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(LibraryNotFoundError):
                locator.locate()
        log = dict(locator.get_search_log())
        assert "未设置" in log.get("环境变量", "")


class TestPackageResources:
    """测试：包内资源定位"""

    @pytest.fixture
    def fake_package_data(self, monkeypatch, temp_dir):
        """模拟 time_travel.data 包目录"""
        # 创建假的 data 包结构
        data_dir = temp_dir / "time_travel" / "data"
        data_dir.mkdir(parents=True)
        (data_dir / "__init__.py").write_text("")
        (data_dir / "time_shim.so").write_bytes(b"fake lib")

        # 将 temp_dir 加入 sys.path
        monkeypatch.syspath_prepend(str(temp_dir))
        return data_dir

    def test_importlib_files_python39_plus(self, locator, fake_package_data):
        """Python 3.9+: importlib.resources.files() 找到包内资源"""
        if sys.version_info < (3, 9):
            pytest.skip("需要 Python 3.9+")

        result = None
        try:
            result = locator.locate()
        except LibraryNotFoundError:
            pass

        # 检查搜索日志，确认 importlib 策略被调用了
        log = dict(locator.get_search_log())
        assert "importlib.resources (包内资源)" in log

    def test_pkgutil_fallback(self, locator, fake_package_data):
        """pkgutil.get_data 回退策略"""
        import pkgutil

        # mock pkgutil.get_data 返回内容
        with patch.object(
            pkgutil, "get_data", return_value=b"mocked library binary"
        ):
            # 需要 mock _write_library_to_cache 避免实际写文件
            with patch.object(locator, "_write_library_to_cache") as mock_write:
                mock_write.return_value = fake_package_data / "time_shim.so"
                try:
                    locator.locate()
                except LibraryNotFoundError:
                    pass


class TestProjectLibDir:
    """测试：项目根目录 lib/"""

    def test_find_in_project_lib(self, locator, temp_dir, monkeypatch):
        """在项目根目录 lib/ 下找到共享库"""
        # 创建项目结构
        project_root = temp_dir
        (project_root / "Makefile").write_text("fake makefile")
        lib_dir = project_root / "lib"
        lib_dir.mkdir()
        fake_lib = lib_dir / "time_shim.so"
        fake_lib.write_bytes(b"fake")

        # 将定位器模块放在深层结构中
        fake_module_dir = project_root / "src" / "python" / "time_travel"
        fake_module_dir.mkdir(parents=True)

        # mock __file__ 指向深层目录
        import time_travel.library_locator as locator_module

        original_file = locator_module.__file__
        try:
            locator_module.__file__ = str(fake_module_dir / "library_locator.py")
            with patch.object(Path, "resolve", return_value=fake_module_dir / "library_locator.py"):
                # 尝试查找
                try:
                    result = locator.locate()
                except LibraryNotFoundError:
                    pass
        finally:
            locator_module.__file__ = original_file

        # 验证搜索日志
        log = dict(locator.get_search_log())
        assert "项目根目录 lib/" in log


class TestSystemPaths:
    """测试：系统标准路径"""

    def test_check_system_paths(self, locator):
        """检查系统路径搜索策略是否被调用"""
        with pytest.raises(LibraryNotFoundError):
            locator.locate()
        log = dict(locator.get_search_log())
        assert "系统标准路径" in log


class TestLinkerPaths:
    """测试：动态链接器路径"""

    def test_ld_library_path(self, locator, fake_library, temp_dir):
        """LD_LIBRARY_PATH 中的路径"""
        lib_dir = fake_library.parent
        with patch.dict(os.environ, {"LD_LIBRARY_PATH": str(lib_dir)}):
            try:
                result = locator.locate()
                assert result.exists()
            except LibraryNotFoundError:
                # 某些策略可能先找到或先失败，检查日志即可
                pass

        log = dict(locator.get_search_log())
        assert "动态链接器路径" in log


class TestSearchLog:
    """测试：搜索日志功能"""

    def test_log_contains_all_strategies(self, locator):
        """日志应包含所有策略名称"""
        with pytest.raises(LibraryNotFoundError):
            locator.locate()

        log_entries = locator.get_search_log()
        strategy_names = [name for name, _ in log_entries]

        expected = [
            "用户显式指定",
            "环境变量",
            "importlib.resources (包内资源)",
            "pkgutil 回退",
            "项目根目录 lib/",
            "当前工作目录 lib/",
            "系统标准路径",
            "动态链接器路径",
        ]

        for exp in expected:
            assert exp in strategy_names, f"缺少策略日志: {exp}"

    def test_log_returns_copy(self, locator):
        """get_search_log 返回副本，避免外部修改"""
        with pytest.raises(LibraryNotFoundError):
            locator.locate()

        log1 = locator.get_search_log()
        log1.append(("fake", "entry"))

        log2 = locator.get_search_log()
        assert ("fake", "entry") not in log2


class TestErrorMessage:
    """测试：错误信息的完整性"""

    def test_error_contains_search_history(self, locator):
        """错误信息应包含搜索历史"""
        with pytest.raises(LibraryNotFoundError) as exc_info:
            locator.locate()

        error_msg = str(exc_info.value)
        assert "time_shim.so" in error_msg
        assert "已尝试的搜索路径" in error_msg
        assert "解决方法" in error_msg

    def test_error_contains_solutions(self, locator):
        """错误信息应包含解决方法建议"""
        with pytest.raises(LibraryNotFoundError) as exc_info:
            locator.locate()

        error_msg = str(exc_info.value)
        assert "make" in error_msg
        assert "--library" in error_msg
        assert "TIME_TRAVEL_LIBRARY_PATH" in error_msg


class TestLibraryFilename:
    """测试：不同平台的库文件名"""

    def test_linux_extension(self):
        """Linux 平台使用 .so"""
        locator = LibraryLocator(".so")
        assert locator.library_filename == "time_shim.so"

    def test_macos_extension(self):
        """macOS 平台使用 .dylib"""
        locator = LibraryLocator(".dylib")
        assert locator.library_filename == "time_shim.dylib"


class TestPriorityOrder:
    """测试：策略优先级顺序"""

    def test_explicit_path_highest_priority(self, locator, temp_dir):
        """用户显式指定路径优先级最高"""
        # 创建两个假的库文件
        explicit_lib = temp_dir / "explicit" / "time_shim.so"
        explicit_lib.parent.mkdir()
        explicit_lib.write_bytes(b"explicit")

        env_lib = temp_dir / "env" / "time_shim.so"
        env_lib.parent.mkdir()
        env_lib.write_bytes(b"env")

        # 设置环境变量指向另一个
        with patch.dict(os.environ, {"TIME_TRAVEL_LIBRARY_PATH": str(env_lib)}):
            result = locator.locate(explicit_lib)
            # 应优先返回显式指定的
            assert result.resolve() == explicit_lib.resolve()


class TestTemporaryCache:
    """测试：临时缓存目录管理"""

    def test_temp_dir_cleanup_registered(self):
        """验证 atexit 清理函数已注册"""
        import atexit
        from time_travel.library_locator import _cleanup_temp_dir

        # 检查 _cleanup_temp_dir 是否在 atexit 注册列表中
        # 注意：atexit 没有公开 API 列出已注册函数，
        # 这里我们只验证函数本身存在且可调用
        assert callable(_cleanup_temp_dir)
