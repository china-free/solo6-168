"""
时间模拟器单元测试
"""

import unittest
from datetime import datetime, timedelta, timezone

from time_travel.time_simulator import TimeSimulator, TimeOffset
from time_travel.exceptions import InvalidDateError


class TestTimeOffset(unittest.TestCase):
    """测试 TimeOffset 数据类"""

    def test_total_seconds(self):
        offset = TimeOffset(seconds=3600, nanoseconds=500000000)
        self.assertAlmostEqual(offset.total_seconds(), 3600.5, places=6)

    def test_str_positive(self):
        offset = TimeOffset(seconds=3661)
        self.assertEqual(str(offset), "+01:01:01")

    def test_str_negative(self):
        offset = TimeOffset(seconds=-3661)
        self.assertEqual(str(offset), "-01:01:01")

    def test_str_zero(self):
        offset = TimeOffset(seconds=0)
        self.assertEqual(str(offset), "+00:00:00")


class TestTimeSimulator(unittest.TestCase):
    """测试 TimeSimulator 类"""

    def test_parse_absolute_date(self):
        """测试解析绝对日期"""
        simulator = TimeSimulator.parse("2025-12-31")
        self.assertEqual(simulator.target_time.year, 2025)
        self.assertEqual(simulator.target_time.month, 12)
        self.assertEqual(simulator.target_time.day, 31)

    def test_parse_absolute_datetime(self):
        """测试解析绝对日期时间"""
        simulator = TimeSimulator.parse("2025-12-31 23:59:59")
        self.assertEqual(simulator.target_time.hour, 23)
        self.assertEqual(simulator.target_time.minute, 59)
        self.assertEqual(simulator.target_time.second, 59)

    def test_parse_iso_format(self):
        """测试解析 ISO 格式"""
        simulator = TimeSimulator.parse("2025-12-31T23:59:59.123456")
        self.assertEqual(simulator.target_time.microsecond, 123456)

    def test_parse_slash_format(self):
        """测试解析斜杠分隔格式"""
        simulator = TimeSimulator.parse("2025/12/31")
        self.assertEqual(simulator.target_time.year, 2025)
        self.assertEqual(simulator.target_time.month, 12)
        self.assertEqual(simulator.target_time.day, 31)

    def test_parse_compact_format(self):
        """测试解析紧凑格式"""
        simulator = TimeSimulator.parse("20251231")
        self.assertEqual(simulator.target_time.year, 2025)
        self.assertEqual(simulator.target_time.month, 12)
        self.assertEqual(simulator.target_time.day, 31)

    def test_parse_relative_days(self):
        """测试解析相对天数"""
        simulator = TimeSimulator.parse("+1d")
        real_now = datetime.now(timezone.utc)
        expected = (real_now + timedelta(days=1)).replace(tzinfo=timezone.utc)
        self.assertAlmostEqual(
            simulator.target_time.timestamp(),
            expected.timestamp(),
            delta=1,
        )

    def test_parse_relative_hours(self):
        """测试解析相对小时"""
        simulator = TimeSimulator.parse("-2h")
        real_now = datetime.now(timezone.utc)
        expected = (real_now - timedelta(hours=2)).replace(tzinfo=timezone.utc)
        self.assertAlmostEqual(
            simulator.target_time.timestamp(),
            expected.timestamp(),
            delta=1,
        )

    def test_parse_relative_minutes(self):
        """测试解析相对分钟"""
        simulator = TimeSimulator.parse("+30m")
        real_now = datetime.now(timezone.utc)
        expected = (real_now + timedelta(minutes=30)).replace(tzinfo=timezone.utc)
        self.assertAlmostEqual(
            simulator.target_time.timestamp(),
            expected.timestamp(),
            delta=1,
        )

    def test_parse_relative_seconds(self):
        """测试解析相对秒"""
        simulator = TimeSimulator.parse("+10s")
        real_now = datetime.now(timezone.utc)
        expected = (real_now + timedelta(seconds=10)).replace(tzinfo=timezone.utc)
        self.assertAlmostEqual(
            simulator.target_time.timestamp(),
            expected.timestamp(),
            delta=1,
        )

    def test_parse_keyword_now(self):
        """测试解析关键字 now"""
        simulator = TimeSimulator.parse("now")
        real_now = datetime.now(timezone.utc)
        self.assertAlmostEqual(
            simulator.target_time.timestamp(),
            real_now.timestamp(),
            delta=1,
        )

    def test_parse_keyword_today(self):
        """测试解析关键字 today"""
        simulator = TimeSimulator.parse("today")
        real_now = datetime.now(timezone.utc)
        expected = real_now.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
        self.assertEqual(simulator.target_time, expected)

    def test_parse_keyword_tomorrow(self):
        """测试解析关键字 tomorrow"""
        simulator = TimeSimulator.parse("tomorrow")
        real_now = datetime.now(timezone.utc)
        expected = (real_now + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc
        )
        self.assertEqual(simulator.target_time, expected)

    def test_parse_keyword_yesterday(self):
        """测试解析关键字 yesterday"""
        simulator = TimeSimulator.parse("yesterday")
        real_now = datetime.now(timezone.utc)
        expected = (real_now - timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc
        )
        self.assertEqual(simulator.target_time, expected)

    def test_parse_keyword_end_of_year(self):
        """测试解析关键字 end-of-year"""
        simulator = TimeSimulator.parse("end-of-year")
        real_now = datetime.now(timezone.utc)
        expected = datetime(real_now.year, 12, 31, 23, 59, 59, 999999, tzinfo=timezone.utc)
        self.assertEqual(simulator.target_time, expected)

    def test_parse_timestamp(self):
        """测试解析 Unix 时间戳"""
        timestamp = 1735689599.0
        simulator = TimeSimulator.parse(str(timestamp))
        expected = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        self.assertEqual(simulator.target_time, expected)

    def test_parse_invalid_date(self):
        """测试解析无效日期"""
        with self.assertRaises(InvalidDateError):
            TimeSimulator.parse("invalid-date")

    def test_parse_invalid_relative(self):
        """测试解析无效相对时间"""
        with self.assertRaises(InvalidDateError):
            TimeSimulator.parse("+1x")

    def test_calculate_offset_future(self):
        """测试计算未来时间偏移"""
        now = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        target = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        simulator = TimeSimulator(target_time=target)
        offset = simulator.calculate_offset(real_time=now)
        expected_seconds = 366 * 24 * 3600  # 2024 是闰年
        self.assertEqual(offset.seconds, expected_seconds)
        self.assertEqual(offset.nanoseconds, 0)

    def test_calculate_offset_past(self):
        """测试计算过去时间偏移"""
        now = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        target = datetime(2023, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        simulator = TimeSimulator(target_time=target)
        offset = simulator.calculate_offset(real_time=now)
        expected_seconds = -365 * 24 * 3600
        self.assertEqual(offset.seconds, expected_seconds)

    def test_calculate_offset_with_nanoseconds(self):
        """测试计算带纳秒的偏移"""
        now = datetime(2024, 1, 1, 0, 0, 0, 0, tzinfo=timezone.utc)
        target = datetime(2024, 1, 1, 0, 0, 0, 123456, tzinfo=timezone.utc)
        simulator = TimeSimulator(target_time=target)
        offset = simulator.calculate_offset(real_time=now)
        self.assertEqual(offset.seconds, 0)
        self.assertEqual(offset.nanoseconds, 123456000)

    def test_format_target_time(self):
        """测试格式化目标时间"""
        target = datetime(2025, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
        simulator = TimeSimulator(target_time=target)
        formatted = simulator.format_target_time()
        self.assertIn("2025-12-31", formatted)
        self.assertIn("23:59:59", formatted)
        self.assertIn("UTC", formatted)

    def test_calculate_offset_without_target(self):
        """测试未设置目标时间时计算偏移"""
        simulator = TimeSimulator()
        with self.assertRaises(ValueError):
            simulator.calculate_offset()


if __name__ == "__main__":
    unittest.main()
