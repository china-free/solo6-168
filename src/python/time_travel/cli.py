"""
命令行接口模块

提供友好的 CLI 界面，支持各种参数解析和命令执行。
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from .exceptions import TimeTravelError
from .time_simulator import TimeSimulator
from .process_launcher import ProcessLauncher


def build_parser() -> argparse.ArgumentParser:
    """
    构建命令行参数解析器

    Returns:
        配置好的 argparse.ArgumentParser 实例
    """
    parser = argparse.ArgumentParser(
        prog="time-travel",
        description="进程级时间穿梭模拟器 - 让目标进程看到自定义的时间",
        epilog="""
示例用法:
  time-travel --date "2025-12-31" -- ./my-server
  time-travel --date "+1d" -- date
  time-travel --date "end-of-year" -- python -c "import datetime; print(datetime.datetime.now())"
  time-travel --date "2025-02-29" -- ./leap-year-test
  time-travel --date "tomorrow" -- ./cert-expiry-test
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "-d",
        "--date",
        type=str,
        required=True,
        help="目标时间表达式（绝对日期、相对时间或关键字）",
        metavar="TIME_EXPR",
    )

    parser.add_argument(
        "-t",
        "--time",
        type=str,
        help="设置具体时间（时分秒，可选），例如 23:59:59）",
        metavar="HH:MM:SS",
    )

    parser.add_argument(
        "--library",
        type=str,
        help="指定时间劫持共享库路径",
        metavar="PATH",
    )

    parser.add_argument(
        "--cwd",
        type=str,
        help="指定工作目录",
        metavar="DIR",
    )

    parser.add_argument(
        "--no-env",
        action="store_true",
        help="不继承当前环境变量",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅显示将要执行的命令，不实际执行",
    )

    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="静默模式，不输出时间穿梭信息",
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="输出详细调试信息",
    )

    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="要执行的命令及其参数（使用 -- 分隔可选参数与命令）",
    )

    return parser


def print_banner(
    simulator: TimeSimulator,
    offset,
    command: List[str],
    library_path: Optional[Path],
) -> None:
    """
    打印时间穿梭启动信息横幅

    Args:
        simulator: 时间模拟器实例
        offset: 时间偏移量
        command: 要执行的命令
        library_path: 共享库路径
    """
    real_now = datetime.now(timezone.utc)
    target_time = simulator.target_time

    print("=" * 60)
    print("  ⏰  时光机已启动")
    print("=" * 60)
    print(f"  真实时间: {real_now.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"  虚拟时间: {target_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"  时间偏移: {offset}")
    print(f"  劫持库:   {library_path}")
    print(f"  目标进程: {' '.join(command)}")
    print("=" * 60)
    print()


def main(argv: Optional[List[str]] = None) -> int:
    """
    主函数

    Args:
        argv: 命令行参数列表，默认为 sys.argv[1:]

    Returns:
        进程退出码
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        time_expr = args.date
        if args.time:
            time_expr = f"{time_expr} {args.time}"

        simulator = TimeSimulator.parse(time_expr)
        offset = simulator.calculate_offset()

        if not args.command or (len(args.command) == 1 and args.command[0] == "--"):
            parser.error("请提供要执行的命令（使用 -- 分隔）")
            return 2

        command = args.command
        if command[0] == "--":
            command = command[1:]

        launcher = ProcessLauncher(
            library_path=args.library,
        )

        if not args.quiet:
            print_banner(simulator, offset, command, launcher.library_path)

        if args.dry_run:
            env = launcher._build_environment(offset, not args.no_env)
            print("将要设置的环境变量:")
            for key in [
                launcher.strategy.get_environment_variable_name(),
                "TIME_TRAVEL_ENABLED",
                "TIME_TRAVEL_OFFSET_SEC",
                "TIME_TRAVEL_OFFSET_NSEC",
            ]:
                print(f"  {key}={env.get(key, '(未设置)')}")
            print(f"\n将要执行的命令: {' '.join(command)}")
            return 0

        if args.verbose:
            print(f"[DEBUG] 时间偏移量: {offset.seconds}s + {offset.nanoseconds}ns")
            print(f"[DEBUG] 目标时间: {simulator.format_target_time()}")
            print()

        return_code = launcher.launch(
            command=command,
            time_offset=offset,
            working_dir=args.cwd,
            inherit_env=not args.no_env,
            capture_output=False,
            interactive=True,
        )

        return return_code

    except TimeTravelError as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1

    except KeyboardInterrupt:
        print("\n操作已中断", file=sys.stderr)
        return 130

    except Exception as e:
        print(f"意外错误: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
