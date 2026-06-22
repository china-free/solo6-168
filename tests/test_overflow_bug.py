#!/usr/bin/env python3
"""
测试微秒/纳秒溢出 Bug

问题描述:
1. Python 端 calculate_offset 使用 int() 截断取整，导致负数时 nanoseconds 可能为负
2. C 端 gettimeofday/clock_gettime 使用单次 if-else 处理进位/借位，
   无法处理超过 1 秒的溢出，导致返回非法的 timeval/timespec 结构体
"""

import unittest
import math
from datetime import datetime, timezone, timedelta

import sys
sys.path.insert(0, '../src/python')

from time_travel.time_simulator import TimeSimulator, TimeOffset


class TestOverflowBug(unittest.TestCase):
    """测试溢出 Bug"""

    def test_negative_offset_calculation_python_bug(self):
        """
        测试 Python 端负数偏移量计算问题
        
        问题: int(-1.5) = -1 (截断)，而不是 -2 (向下取整)
        导致 nanoseconds 可能为负数
        """
        now = datetime(2026, 6, 22, 12, 0, 0, tzinfo=timezone.utc)
        
        # 模拟穿越回 1.5 秒前
        target = now - timedelta(seconds=1, microseconds=500000)
        simulator = TimeSimulator(target_time=target)
        offset = simulator.calculate_offset(real_time=now)
        
        print(f"\n测试 1: 负数偏移量计算")
        print(f"  真实时间: {now}")
        print(f"  目标时间: {target}")
        print(f"  差值: -1.5 秒")
        print(f"  计算结果: seconds={offset.seconds}, nanoseconds={offset.nanoseconds}")
        
        # 期望: seconds=-2, nanoseconds=500000000 (向下取整)
        # 或者至少: nanoseconds 应该在 [0, 1e9) 范围内
        self.assertGreaterEqual(offset.nanoseconds, 0, 
            f"Bug 复现! nanoseconds={offset.nanoseconds} 为负数")
        self.assertLess(offset.nanoseconds, 1e9,
            f"nanoseconds={offset.nanoseconds} 超出范围")
        
        # 验证总偏移量正确
        total = offset.seconds + offset.nanoseconds / 1e9
        self.assertAlmostEqual(total, -1.5, places=6,
            msg=f"总偏移量错误: {total} != -1.5")

    def test_large_negative_offset(self):
        """
        测试大的负数偏移量（穿越回5年前）
        
        这会导致 C 端的 tv_usec 大幅溢出，单次 if-else 无法处理
        """
        now = datetime(2026, 6, 22, 12, 0, 0, 123456, tzinfo=timezone.utc)
        
        # 穿越回 5 年 + 0.5 秒前
        target = now - timedelta(days=365*5, microseconds=500000)
        simulator = TimeSimulator(target_time=target)
        offset = simulator.calculate_offset(real_time=now)
        
        print(f"\n测试 2: 大负数偏移量（5年前）")
        print(f"  真实时间: {now}")
        print(f"  目标时间: {target}")
        print(f"  计算结果: seconds={offset.seconds}, nanoseconds={offset.nanoseconds}")
        
        # nanoseconds 必须在合法范围
        self.assertGreaterEqual(offset.nanoseconds, 0,
            f"Bug 复现! nanoseconds={offset.nanoseconds} 为负数")
        self.assertLess(offset.nanoseconds, 1e9)

    def test_large_positive_offset(self):
        """
        测试大的正数偏移量（穿越到10年后）
        """
        now = datetime(2026, 6, 22, 12, 0, 0, 123456, tzinfo=timezone.utc)
        
        # 穿越到 10 年 + 0.9 秒后
        target = now + timedelta(days=365*10, microseconds=900000)
        simulator = TimeSimulator(target_time=target)
        offset = simulator.calculate_offset(real_time=now)
        
        print(f"\n测试 3: 大正数偏移量（10年后）")
        print(f"  真实时间: {now}")
        print(f"  目标时间: {target}")
        print(f"  计算结果: seconds={offset.seconds}, nanoseconds={offset.nanoseconds}")
        
        # nanoseconds 必须在合法范围
        self.assertGreaterEqual(offset.nanoseconds, 0)
        self.assertLess(offset.nanoseconds, 1e9)

    def test_boundary_negative_0_5(self):
        """
        测试边界: -0.5 秒偏移
        """
        now = datetime(2026, 6, 22, 12, 0, 0, tzinfo=timezone.utc)
        target = now - timedelta(microseconds=500000)
        simulator = TimeSimulator(target_time=target)
        offset = simulator.calculate_offset(real_time=now)
        
        print(f"\n测试 4: 边界 -0.5 秒")
        print(f"  计算结果: seconds={offset.seconds}, nanoseconds={offset.nanoseconds}")
        
        # 正确的结果应该是 seconds=-1, nanoseconds=500000000
        # 而不是 seconds=0, nanoseconds=-500000000
        self.assertEqual(offset.seconds, -1,
            f"Bug 复现! seconds={offset.seconds}, 期望 -1")
        self.assertEqual(offset.nanoseconds, 500000000,
            f"Bug 复现! nanoseconds={offset.nanoseconds}, 期望 500000000")

    def test_boundary_negative_0_999999999(self):
        """
        测试边界: -0.999999999 秒偏移
        """
        now = datetime(2026, 6, 22, 12, 0, 0, tzinfo=timezone.utc)
        target = now - timedelta(microseconds=999999)
        simulator = TimeSimulator(target_time=target)
        offset = simulator.calculate_offset(real_time=now)
        
        print(f"\n测试 5: 边界 -0.999999 秒")
        print(f"  计算结果: seconds={offset.seconds}, nanoseconds={offset.nanoseconds}")
        
        self.assertEqual(offset.seconds, -1)
        self.assertEqual(offset.nanoseconds, 1000)  # 1000 纳秒

    def test_c_side_overflow_simulation(self):
        """
        模拟 C 端的溢出问题
        
        假设 offset_nsec = -3500000000 (-3.5秒，由于 Python 端 Bug 导致)
        那么 offset_nsec / 1000 = -3500000 微秒
        如果 tv->tv_usec 原本是 500000，那么变成 -3000000
        单次 if-else 只能借位一次，变成 -2000000，仍然不合法！
        """
        print(f"\n测试 6: 模拟 C 端溢出问题")
        
        # 模拟 Python 端 Bug 产生的非法偏移
        # 故意使用一个会导致多次溢出的偏移量
        buggy_offset_sec = -1
        buggy_offset_nsec = -3500000000  # -3.5 秒，非法！应该分成 -4秒 + 500000000纳秒
        
        # 模拟真实的 gettimeofday 返回值
        tv_sec = 1000
        tv_usec = 500000  # 0.5 秒
        
        print(f"  原始时间: {tv_sec}.{tv_usec:06d}")
        print(f"  Buggy 偏移: sec={buggy_offset_sec}, nsec={buggy_offset_nsec}")
        
        # 应用偏移 (模拟 C 端代码)
        # C 语言中负数除法是截断取整(向零)，而非向下取整
        c_div = lambda a, b: int(a / b)  # 模拟 C 语言截断取整
        tv_sec += buggy_offset_sec
        tv_usec += c_div(buggy_offset_nsec, 1000)
        
        print(f"  偏移后未修正: {tv_sec}.{tv_usec}")
        self.assertEqual(tv_usec, -3000000, "偏移后应该是 -3000000")
        
        # 单次 if-else 修正 (原始 Bug 代码)
        if tv_usec >= 1000000:
            tv_sec += 1
            tv_usec -= 1000000
        elif tv_usec < 0:
            tv_sec -= 1
            tv_usec += 1000000
        
        print(f"  单次修正后: {tv_sec}.{tv_usec}")
        print(f"  tv_usec 合法吗? {0 <= tv_usec < 1000000}")
        
        # 这里 tv_usec 应该还是 -2000000，不合法！
        self.assertEqual(tv_usec, -2000000, "单次修正后应该还是 -2000000")
        self.assertFalse(0 <= tv_usec < 1000000,
            "Bug 存在！单次 if-else 无法处理多次溢出")

    def test_c_side_overflow_fix_simulation(self):
        """
        模拟修复后的 C 端代码
        使用 while 循环确保完全修正
        """
        print(f"\n测试 7: 模拟修复后的 C 端代码")
        
        # 同样的非法偏移（会导致多次溢出）
        buggy_offset_sec = -1
        buggy_offset_nsec = -3500000000
        
        tv_sec = 1000
        tv_usec = 500000
        
        print(f"  原始时间: {tv_sec}.{tv_usec:06d}")
        
        # 模拟 C 语言截断取整
        c_div = lambda a, b: int(a / b)
        tv_sec += buggy_offset_sec
        tv_usec += c_div(buggy_offset_nsec, 1000)
        
        print(f"  偏移后未修正: {tv_sec}.{tv_usec}")
        self.assertEqual(tv_usec, -3000000, "偏移后应该是 -3000000")
        
        # 使用 while 循环修正
        while tv_usec >= 1000000:
            tv_sec += 1
            tv_usec -= 1000000
        while tv_usec < 0:
            tv_sec -= 1
            tv_usec += 1000000
        
        print(f"  循环修正后: {tv_sec}.{tv_usec:06d}")
        print(f"  tv_usec 合法吗? {0 <= tv_usec < 1000000}")
        
        # 验证修正后的值正确
        # 原始: 1000.500000
        # 加上偏移: -1秒 + (-3500000000纳秒/1000) = -1秒 -3500000微秒
        # 总共: 999.500000 - 3.500000 = 996.000000
        self.assertEqual(tv_sec, 996, "修正后秒数应该是 996")
        self.assertEqual(tv_usec, 0, "修正后微秒应该是 0")
        self.assertTrue(0 <= tv_usec < 1000000,
            "修复后应该合法")

    def test_math_floor_vs_int(self):
        """
        演示 math.floor 和 int 的区别
        """
        print(f"\n测试 8: math.floor vs int")
        
        test_values = [1.5, 0.5, -0.5, -1.5, -0.999999999]
        
        for val in test_values:
            int_val = int(val)
            floor_val = math.floor(val)
            print(f"  {val:12.9f}: int()={int_val:4d}, math.floor()={floor_val:4d}")
            
            if val < 0:
                # 对于负数，int 截断（向零），floor 向下取整（更小）
                self.assertLessEqual(floor_val, int_val,
                    f"负数时 floor 应该小于等于 int: {val}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
