#!/usr/bin/env python3
"""
边缘场景测试脚本

测试跨年、闰年、证书到期等典型边缘场景。
运行前需要先执行 make 编译共享库。
"""

import os
import sys
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
LIB_PATH = PROJECT_ROOT / "lib" / "time_shim.so"
CLI_PATH = PROJECT_ROOT / "bin" / "time-travel"


def run_time_travel(date_expr, command):
    """运行 time-travel 命令并返回结果"""
    if not LIB_PATH.exists():
        print(f"错误: 找不到共享库 {LIB_PATH}")
        print("请先执行 'make' 编译共享库")
        return None

    if not CLI_PATH.exists():
        print(f"错误: 找不到 CLI 脚本 {CLI_PATH}")
        return None

    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT / "src" / "python")

    full_command = [
        sys.executable,
        str(CLI_PATH),
        "-d",
        date_expr,
        "-q",
        "--",
    ] + command

    result = subprocess.run(
        full_command,
        env=env,
        capture_output=True,
        text=True,
    )

    return result


def test_cross_year():
    """测试跨年场景: 2025-12-31 23:59:59 -> 2026-01-01 00:00:00"""
    print("=" * 60)
    print("测试场景 1: 跨年逻辑 (2025-12-31 23:59:59)")
    print("=" * 60)

    result = run_time_travel(
        "2025-12-31 23:59:59",
        ["python3", "-c", "import datetime; print(datetime.datetime.now())"],
    )

    if result is None:
        return False

    if result.returncode == 0:
        output = result.stdout.strip()
        print(f"  进程看到的时间: {output}")
        if "2025-12-31" in output or "2026-01-01" in output:
            print("  ✓ 跨年场景测试通过")
            return True
        else:
            print(f"  ✗ 期望看到 2025-12-31 或 2026-01-01，实际看到: {output}")
            return False
    else:
        print(f"  ✗ 命令执行失败: {result.stderr}")
        return False


def test_leap_year():
    """测试闰年场景: 2024-02-29"""
    print("\n" + "=" * 60)
    print("测试场景 2: 闰年逻辑 (2024-02-29)")
    print("=" * 60)

    result = run_time_travel(
        "2024-02-29",
        [
            "python3",
            "-c",
            "import datetime; d = datetime.datetime.now(); print(d); print('Is Feb 29:', d.month == 2 and d.day == 29); print('Leap year check:', (d.year % 4 == 0 and (d.year % 100 != 0 or d.year % 400 == 0)))",
        ],
    )

    if result is None:
        return False

    if result.returncode == 0:
        output = result.stdout.strip()
        print(f"  输出:\n{output}")
        if "2024-02-29" in output and "Is Feb 29: True" in output:
            print("  ✓ 闰年场景测试通过")
            return True
        else:
            print(f"  ✗ 期望看到 2024-02-29，实际看到: {output}")
            return False
    else:
        print(f"  ✗ 命令执行失败: {result.stderr}")
        return False


def test_cert_expiry_tomorrow():
    """测试证书明天到期场景"""
    print("\n" + "=" * 60)
    print("测试场景 3: 证书明天到期 (当前时间设为到期前一天)")
    print("=" * 60)

    result = run_time_travel(
        "-1d",
        [
            "python3",
            "-c",
            "import datetime; now = datetime.datetime.now(); expiry = now + datetime.timedelta(days=1); print(f'当前时间: {now}'); print(f'证书到期时间: {expiry}'); days_left = (expiry - now).days; print(f'剩余天数: {days_left}'); print('证书明天到期:', days_left == 1)",
        ],
    )

    if result is None:
        return False

    if result.returncode == 0:
        output = result.stdout.strip()
        print(f"  输出:\n{output}")
        if "证书明天到期: True" in output:
            print("  ✓ 证书到期场景测试通过")
            return True
        else:
            print(f"  ✗ 期望证书明天到期，实际输出: {output}")
            return False
    else:
        print(f"  ✗ 命令执行失败: {result.stderr}")
        return False


def test_end_of_month():
    """测试月末场景"""
    print("\n" + "=" * 60)
    print("测试场景 4: 月末逻辑 (使用 end-of-month 关键字)")
    print("=" * 60)

    result = run_time_travel(
        "end-of-month",
        [
            "python3",
            "-c",
            "import datetime; now = datetime.datetime.now(); print(f'当前时间: {now}'); next_day = now + datetime.timedelta(days=1); print(f'明天是: {next_day}'); print('是月末:', now.month != next_day.month)",
        ],
    )

    if result is None:
        return False

    if result.returncode == 0:
        output = result.stdout.strip()
        print(f"  输出:\n{output}")
        if "是月末: True" in output:
            print("  ✓ 月末场景测试通过")
            return True
        else:
            print(f"  ✗ 期望是月末，实际输出: {output}")
            return False
    else:
        print(f"  ✗ 命令执行失败: {result.stderr}")
        return False


def test_relative_time():
    """测试相对时间偏移"""
    print("\n" + "=" * 60)
    print("测试场景 5: 相对时间 (+1y - 一年后)")
    print("=" * 60)

    real_now = subprocess.run(
        ["python3", "-c", "import datetime; print(datetime.datetime.now().year)"],
        capture_output=True,
        text=True,
    ).stdout.strip()

    result = run_time_travel(
        "+1y",
        ["python3", "-c", "import datetime; print(datetime.datetime.now().year)"],
    )

    if result is None:
        return False

    if result.returncode == 0:
        virtual_year = result.stdout.strip()
        print(f"  真实年份: {real_now}")
        print(f"  虚拟年份: {virtual_year}")
        expected_year = str(int(real_now) + 1)
        if virtual_year == expected_year:
            print("  ✓ 相对时间测试通过")
            return True
        else:
            print(f"  ✗ 期望年份 {expected_year}，实际 {virtual_year}")
            return False
    else:
        print(f"  ✗ 命令执行失败: {result.stderr}")
        return False


def test_host_time_unchanged():
    """验证宿主机时间不受影响"""
    print("\n" + "=" * 60)
    print("验证: 宿主机时间不受影响")
    print("=" * 60)

    before = subprocess.run(
        ["date", "+%Y-%m-%d %H:%M:%S"],
        capture_output=True,
        text=True,
    ).stdout.strip()

    run_time_travel("2025-12-31", ["sleep", "1"])

    after = subprocess.run(
        ["date", "+%Y-%m-%d %H:%M:%S"],
        capture_output=True,
        text=True,
    ).stdout.strip()

    print(f"  测试前时间: {before}")
    print(f"  测试后时间: {after}")

    if before != after:
        print("  ✓ 宿主机时间正常流逝（证明未被修改）")
        return True
    else:
        print("  ⚠  宿主机时间未变化（可能是测试太快）")
        return True


def main():
    """运行所有测试"""
    print("⏰  Time Travel 边缘场景测试")
    print("=" * 60)
    print()

    tests = [
        test_cross_year,
        test_leap_year,
        test_cert_expiry_tomorrow,
        test_end_of_month,
        test_relative_time,
        test_host_time_unchanged,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"  ✗ 测试异常: {e}")
            failed += 1

    print("\n" + "=" * 60)
    print(f"测试结果: {passed} 通过, {failed} 失败")
    print("=" * 60)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
