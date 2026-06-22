# ⏰ Time Travel - 进程级时间穿梭模拟器

> 再也不用改系统时间测试跨年/闰年/证书到期逻辑了！

## 简介

Time Travel 是一个进程级别的时间穿梭工具，利用 `LD_PRELOAD` 技术劫持系统调用（`gettimeofday`、`time`、`clock_gettime` 等），让目标进程及其子进程"看到"自定义的时间，而宿主机的真实时间纹丝不动。

**核心特性：**
- 🚀 **零侵入**：不需要修改任何业务代码
- 🎯 **进程级隔离**：仅影响目标进程，不影响其他服务
- ⏱️ **高精度**：支持纳秒级时间偏移
- 🌍 **跨语言**：支持 C/C++/Go/Python/Java 等所有语言
- 📦 **即开即用**：简单的 CLI 界面，无需复杂配置
- 🔧 **可扩展**：模块化设计，易于扩展新功能

## 适用场景

| 场景 | 示例命令 |
|------|---------|
| **跨年逻辑测试** | `time-travel --date "2025-12-31 23:59:59" -- ./my-server` |
| **闰年逻辑测试** | `time-travel --date "2024-02-29" -- ./leap-year-test` |
| **证书到期测试** | `time-travel --date "tomorrow" -- ./cert-check` |
| **月末结账测试** | `time-travel --date "end-of-month" -- ./monthly-billing` |
| **相对时间测试** | `time-travel --date "+1y" -- ./license-expiry` |
| **过去时间复现** | `time-travel --date "2023-01-01" -- ./bug-reproduce` |

## 快速开始

### 1. 编译

```bash
# 克隆项目后，在根目录执行
make
```

这将编译 C 劫持共享库并创建可执行脚本。

### 2. 验证安装

```bash
# 查看帮助
./bin/time-travel --help

# 简单测试（让 date 命令看到 2025 年）
./bin/time-travel --date "2025-01-01" -- date
```

### 3. 实际使用

```bash
# 测试跨年逻辑
./bin/time-travel --date "2025-12-31 23:59:59" -- ./my-server

# 测试闰年逻辑
./bin/time-travel --date "2024-02-29" -- python test_leap_year.py

# 测试证书明天到期
./bin/time-travel --date "tomorrow" -- ./check-cert-expiry

# 相对时间偏移（1小时后）
./bin/time-travel --date "+1h" -- ./timeout-test
```

## 支持的时间表达式

### 绝对日期时间
```
2025-12-31
2025-12-31 23:59:59
2025-12-31T23:59:59.123456
2025/12/31
20251231
```

### 相对时间
```
+1d      # 1天后
-2h      # 2小时前
+30m     # 30分钟后
+1y      # 1年后
+6mo     # 6个月后
+100ms   # 100毫秒后
+500us   # 500微秒后
+1000ns  # 1000纳秒后
```

### 关键字
```
now              # 当前时间
today            # 今天 00:00:00
tomorrow         # 明天 00:00:00
yesterday        # 昨天 00:00:00
end-of-year      # 今年最后一天 23:59:59.999999
end-of-month     # 本月最后一天 23:59:59.999999
leap-day         # 本年2月29日（非闰年抛出错误）
```

### Unix 时间戳
```
1735689599
1735689599.123
```

## 工作原理

### 技术架构

```
┌─────────────────────────────────────────────────────────────┐
│                     用户 CLI 调用                            │
│  time-travel --date "2025-12-31" -- ./my-server              │
└────────────────────────────┬────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────┐
│                  Python CLI 入口层                           │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  cli.py - 参数解析、用户交互、错误处理                │  │
│  └──────────────────────────────────────────────────────┘  │
└────────────────────────────┬────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────┐
│                  业务逻辑层                                 │
│  ┌──────────────────┐  ┌──────────────────────────┐        │
│  │ time_simulator.py│  │   process_launcher.py     │        │
│  │  - 时间表达式解析 │  │   - LD_PRELOAD 环境设置   │        │
│  │  - 偏移量计算    │  │   - 子进程启动/管理        │        │
│  └──────────────────┘  └──────────────────────────┘        │
└────────────────────────────┬────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────┐
│                  系统调用劫持层 (C 语言)                    │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  time_shim.c - 劫持以下系统调用:                      │  │
│  │  • gettimeofday()                                    │  │
│  │  • time()                                            │  │
│  │  • clock_gettime()                                   │  │
│  └──────────────────────────────────────────────────────┘  │
└────────────────────────────┬────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────┐
│                  目标进程 (./my-server)                     │
│  所有时间相关系统调用都会被劫持，返回偏移后的时间             │
│  对应用程序完全透明，无需修改任何代码                        │
└─────────────────────────────────────────────────────────────┘
```

### 核心原理

1. **LD_PRELOAD 机制**：Linux 动态链接器允许在程序启动前预加载指定的共享库，优先使用其中的符号。

2. **系统调用劫持**：我们的共享库 `time_shim.so` 实现了与系统库同名的函数：
   - `gettimeofday()`
   - `time()`
   - `clock_gettime()`

3. **真实函数调用**：使用 `dlsym(RTLD_NEXT, "函数名")` 获取原始系统函数的指针。

4. **时间偏移**：从环境变量读取偏移量，在调用真实函数后，将返回值加上偏移量再返回。

5. **环境变量传递**：
   - `TIME_TRAVEL_ENABLED=1` - 启用标记
   - `TIME_TRAVEL_OFFSET_SEC` - 秒级偏移
   - `TIME_TRAVEL_OFFSET_NSEC` - 纳秒级偏移

## 命令行参数

```bash
time-travel [选项] -- <命令> [命令参数...]

选项:
  -d, --date TIME_EXPR    目标时间表达式（必需）
  -t, --time HH:MM:SS     设置具体时间（可选）
      --library PATH      指定共享库路径
      --cwd DIR           指定工作目录
      --no-env            不继承当前环境变量
      --dry-run           仅显示命令，不执行
  -q, --quiet             静默模式
  -v, --verbose           详细调试信息
```

## 目录结构

```
time-travel/
├── src/
│   ├── c/
│   │   └── time_shim.c              # C 语言劫持库（核心）
│   └── python/
│       ├── bin/
│       │   └── time-travel          # 可执行入口脚本
│       └── time_travel/             # Python 包
│           ├── __init__.py          # 包初始化
│           ├── __main__.py          # 模块入口
│           ├── cli.py               # CLI 接口
│           ├── time_simulator.py    # 时间模拟核心
│           ├── process_launcher.py  # 进程启动器
│           └── exceptions.py        # 自定义异常
├── tests/
│   ├── test_time_simulator.py       # 单元测试
│   └── test_edge_cases.py           # 边缘场景测试
├── Makefile                         # 编译构建
├── setup.py                         # Python 包配置
├── requirements.txt                 # 依赖清单
└── README.md                        # 本文档
```

## 运行测试

### 单元测试

```bash
# 运行 Python 单元测试
cd tests && python3 -m pytest test_time_simulator.py -v

# 或者使用 Makefile
make test
```

### 边缘场景测试

```bash
# 先编译
make

# 运行边缘场景测试（需要 Linux 环境）
python3 tests/test_edge_cases.py
```

### 手动测试

```bash
# 测试 1: 让 date 看到过去的时间
./bin/time-travel --date "2020-01-01" -- date

# 测试 2: 让 Python 看到未来的时间
./bin/time-travel --date "+1y" -- python3 -c "import datetime; print(datetime.datetime.now())"

# 测试 3: 验证宿主机时间不变
date && ./bin/time-travel --date "2025-01-01" -- date && date
```

## 代码质量检查

```bash
# 检查 Python 代码
make lint

# 检查 C 代码语法
gcc -Wall -Wextra -fsyntax-only src/c/time_shim.c
```

## 安装到系统（可选）

```bash
# 安装到 /usr/local
sudo make install

# 卸载
sudo make uninstall
```

安装后可以直接使用 `time-travel` 命令。

## 设计亮点

### 1. 策略模式 (Strategy Pattern)

在 `process_launcher.py` 中，使用策略模式支持不同操作系统的库注入机制：

```python
class LibraryLoaderStrategy(ABC):
    @abstractmethod
    def get_environment_variable_name(self) -> str: ...

class LinuxLibraryLoader(LibraryLoaderStrategy):
    def get_environment_variable_name(self) -> str:
        return "LD_PRELOAD"

class MacOSLibraryLoader(LibraryLoaderStrategy):
    def get_environment_variable_name(self) -> str:
        return "DYLD_INSERT_LIBRARIES"
```

### 2. 工厂模式 (Factory Pattern)

```python
class LibraryLoaderFactory:
    @staticmethod
    def get_strategy() -> LibraryLoaderStrategy:
        system = platform.system().lower()
        strategies = {"linux": LinuxLibraryLoader, "darwin": MacOSLibraryLoader}
        return strategies[system]()
```

### 3. 清晰的异常层级

```python
class TimeTravelError(Exception): pass
class InvalidDateError(TimeTravelError): pass
class LibraryNotFoundError(TimeTravelError): pass
class UnsupportedPlatformError(TimeTravelError): pass
class CommandExecutionError(TimeTravelError): pass
```

### 4. 可扩展的时间解析

`TimeSimulator` 类使用优先级解析策略，易于添加新的时间格式：

```python
def _parse_expression(cls, time_expr: str) -> datetime:
    # 1. 关键字解析
    # 2. 相对时间解析
    # 3. Unix 时间戳解析
    # 4. 日期格式解析
```

## 常见问题

### Q: 为什么在 Windows 上不能用？
A: Windows 没有 LD_PRELOAD 机制，需要使用 Detours 等其他技术。目前仅支持 Linux 和 macOS（实验性）。

### Q: 会影响所有子进程吗？
A: 是的！因为环境变量会被子进程继承，所以所有通过 `fork()`/`exec()` 创建的子进程都会看到偏移后的时间。

### Q: 对静态编译的程序有效吗？
A: 无效。LD_PRELOAD 仅对动态链接的程序有效。静态编译的程序直接将系统调用编译进二进制。

### Q: 对 Go 程序有效吗？
A: Go 1.16+ 默认使用系统调用而不是 libc，可能需要特殊处理。可以尝试设置 `CGO_ENABLED=1` 重新编译。

### Q: 会影响宿主机时间吗？
A: 绝对不会！我们只是劫持目标进程的系统调用返回值，没有修改任何系统设置。

### Q: 能劫持 `sleep()` 吗？
A: 目前不支持。`sleep()` 基于单调时钟（CLOCK_MONOTONIC），我们只劫持真实时间相关的调用。如果需要可以自行扩展。

## 扩展开发

### 添加新的时间格式

在 `time_simulator.py` 中添加新的解析方法：

```python
@classmethod
def _try_my_format(cls, time_expr: str) -> Optional[datetime]:
    # 实现你的解析逻辑
    pass
```

然后在 `_parse_expression` 中添加调用。

### 添加新的系统调用劫持

在 `time_shim.c` 中添加新的函数：

```c
typedef int (*my_syscall_t)(...);
static my_syscall_t real_my_syscall = NULL;

int my_syscall(...) {
    time_shim_init();
    int ret = real_my_syscall(...);
    // 修改返回值...
    return ret;
}
```

### 添加新平台支持

在 `process_launcher.py` 中添加新的策略类：

```python
class WindowsLibraryLoader(LibraryLoaderStrategy):
    def get_environment_variable_name(self) -> str:
        return "..."  # Windows 机制

    def get_library_extension(self) -> str:
        return ".dll"

    def get_supported_platforms(self) -> List[str]:
        return ["windows"]
```

## 性能考虑

- **初始化开销**：仅在第一次调用时间函数时有一次 `pthread_mutex` 锁开销
- **运行时开销**：每次调用增加一次环境变量读取（已缓存）和简单的算术运算
- **内存开销**：约 100 字节的静态变量

对于绝大多数应用，性能影响可以忽略不计。

## 安全注意事项

1. **不要在生产环境使用**：这是一个开发/测试工具，不应该在生产环境使用
2. **Setuid 程序**：LD_PRELOAD 对 setuid 程序无效（安全机制）
3. **敏感程序**：不要用这个工具运行不信任的程序

## 相关项目

- [libfaketime](https://github.com/wolfcw/libfaketime) - 类似功能的 C 语言实现
- [timecop](https://github.com/travisjeffery/timecop) - Ruby 的时间旅行库
- [freezegun](https://github.com/spulec/freezegun) - Python 的时间模拟库

## License

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request！

---

**享受无痛的时间敏感逻辑测试吧！** 🎉
