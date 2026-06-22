"""
时间模拟器核心模块

负责计算时间偏移量，支持多种时间表达式格式，
并提供可扩展的时间计算接口。
"""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, Union

from .exceptions import InvalidDateError


@dataclass
class TimeOffset:
    """
    时间偏移量数据类

    存储目标时间与真实时间的差值，精确到纳秒。
    """

    seconds: int
    nanoseconds: int = 0

    def total_seconds(self) -> float:
        """返回总秒数（包含纳秒部分）"""
        return self.seconds + self.nanoseconds / 1e9

    def __str__(self) -> str:
        sign = "+" if self.seconds >= 0 else "-"
        abs_sec = abs(self.seconds)
        hours = abs_sec // 3600
        minutes = (abs_sec % 3600) // 60
        secs = abs_sec % 60
        return f"{sign}{hours:02d}:{minutes:02d}:{secs:02d}"


class TimeSimulator:
    """
    时间模拟器类

    核心功能:
    1. 解析各种格式的时间表达式
    2. 计算目标时间与真实时间的偏移量
    3. 验证时间表达式的有效性

    支持的时间格式:
    - 绝对日期: "2025-12-31", "2025/12/31", "2025-12-31 23:59:59"
    - ISO 格式: "2025-12-31T23:59:59", "2025-12-31T23:59:59.123456"
    - 相对时间: "+1d", "-2h", "+30m", "+1y", "+6mo"
    - 关键字: "now", "today", "tomorrow", "yesterday"
    - Unix 时间戳: "1735689599"

    设计要点:
    - 使用策略模式解析不同格式的时间表达式
    - 所有计算基于 UTC 时间，避免时区问题
    - 支持毫秒/微秒/纳秒级精度
    """

    DATE_FORMATS = [
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%Y/%m/%d %H:%M:%S.%f",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%Y/%m/%d",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y%m%d",
    ]

    RELATIVE_PATTERN = re.compile(
        r"^([+-]?\d+(?:\.\d+)?)\s*(y|mo|w|d|h|m|s|ms|us|ns)$"
    )

    KEYWORD_DATES = {
        "now": lambda now: now,
        "today": lambda now: now.replace(hour=0, minute=0, second=0, microsecond=0),
        "tomorrow": lambda now: (now + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        ),
        "yesterday": lambda now: (now - timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        ),
        "end-of-year": lambda now: datetime(now.year, 12, 31, 23, 59, 59, 999999, tzinfo=timezone.utc),
        "end-of-month": lambda now: (
            datetime(now.year, now.month + 1, 1, tzinfo=timezone.utc) - timedelta(microseconds=1)
            if now.month < 12
            else datetime(now.year, 12, 31, 23, 59, 59, 999999, tzinfo=timezone.utc)
        ),
        "leap-day": lambda now: (
            datetime(now.year, 2, 29, tzinfo=timezone.utc)
            if (now.year % 4 == 0 and (now.year % 100 != 0 or now.year % 400 == 0))
            else None
        ),
    }

    TIME_UNIT_MULTIPLIERS = {
        "y": 365.25 * 24 * 3600,
        "mo": 30.44 * 24 * 3600,
        "w": 7 * 24 * 3600,
        "d": 24 * 3600,
        "h": 3600,
        "m": 60,
        "s": 1,
        "ms": 1e-3,
        "us": 1e-6,
        "ns": 1e-9,
    }

    def __init__(self, target_time: Optional[datetime] = None):
        """
        初始化时间模拟器

        Args:
            target_time: 目标时间，如果为 None 则使用解析方法指定
        """
        self.target_time = target_time

    @classmethod
    def parse(cls, time_expr: str) -> "TimeSimulator":
        """
        解析时间表达式并创建 TimeSimulator 实例

        Args:
            time_expr: 时间表达式字符串

        Returns:
            TimeSimulator 实例

        Raises:
            InvalidDateError: 当时间表达式无法解析时
        """
        target = cls._parse_expression(time_expr)
        return cls(target_time=target)

    def calculate_offset(self, real_time: Optional[datetime] = None) -> TimeOffset:
        """
        计算目标时间与真实时间的偏移量

        Args:
            real_time: 真实时间，默认为当前 UTC 时间

        Returns:
            TimeOffset 偏移量对象

        Raises:
            ValueError: 当未设置目标时间时
        """
        if self.target_time is None:
            raise ValueError("未设置目标时间，请先调用 parse() 或在构造时指定")

        if real_time is None:
            real_time = datetime.now(timezone.utc)

        if self.target_time.tzinfo is None:
            self.target_time = self.target_time.replace(tzinfo=timezone.utc)
        if real_time.tzinfo is None:
            real_time = real_time.replace(tzinfo=timezone.utc)

        delta = self.target_time - real_time
        total_seconds = delta.total_seconds()

        seconds = int(total_seconds)
        nanoseconds = int((total_seconds - seconds) * 1e9)

        return TimeOffset(seconds=seconds, nanoseconds=nanoseconds)

    @classmethod
    def _parse_expression(cls, time_expr: str) -> datetime:
        """
        内部方法：解析时间表达式

        按照优先级尝试各种解析策略：
        1. 关键字解析
        2. 相对时间解析
        3. 日期格式解析（优先于时间戳，避免 20251231 被误判为时间戳）
        4. Unix 时间戳解析
        """
        time_expr = time_expr.strip().lower()

        target = cls._try_keyword(time_expr)
        if target is not None:
            return target

        target = cls._try_relative(time_expr)
        if target is not None:
            return target

        target = cls._try_date_formats(time_expr)
        if target is not None:
            return target

        target = cls._try_timestamp(time_expr)
        if target is not None:
            return target

        raise InvalidDateError(
            time_expr,
            f"无法解析时间表达式: '{time_expr}'\n"
            f"支持的格式:\n"
            f"  - 绝对日期: 2025-12-31, 2025-12-31 23:59:59\n"
            f"  - ISO 格式: 2025-12-31T23:59:59.123\n"
            f"  - 相对时间: +1d, -2h, +30m, +1y\n"
            f"  - 关键字: now, today, tomorrow, end-of-year\n"
            f"  - 时间戳: 1735689599",
        )

    @classmethod
    def _try_keyword(cls, time_expr: str) -> Optional[datetime]:
        """尝试解析关键字时间"""
        if time_expr in cls.KEYWORD_DATES:
            now = datetime.now(timezone.utc)
            result = cls.KEYWORD_DATES[time_expr](now)
            if result is None:
                raise InvalidDateError(
                    time_expr,
                    f"关键字 '{time_expr}' 不适用于当前年份（可能不是闰年）",
                )
            return result
        return None

    @classmethod
    def _try_relative(cls, time_expr: str) -> Optional[datetime]:
        """尝试解析相对时间表达式"""
        match = cls.RELATIVE_PATTERN.match(time_expr)
        if match:
            value = float(match.group(1))
            unit = match.group(2)
            multiplier = cls.TIME_UNIT_MULTIPLIERS[unit]
            total_seconds = value * multiplier
            now = datetime.now(timezone.utc)
            return now + timedelta(seconds=total_seconds)
        return None

    @classmethod
    def _try_timestamp(cls, time_expr: str) -> Optional[datetime]:
        """尝试解析 Unix 时间戳"""
        try:
            timestamp = float(time_expr)
            return datetime.fromtimestamp(timestamp, tz=timezone.utc)
        except (ValueError, OSError, OverflowError):
            return None

    @classmethod
    def _try_date_formats(cls, time_expr: str) -> Optional[datetime]:
        """尝试各种日期格式解析"""
        for fmt in cls.DATE_FORMATS:
            try:
                parsed = datetime.strptime(time_expr, fmt)
                return parsed.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        return None

    def format_target_time(self) -> str:
        """格式化目标时间为可读字符串"""
        if self.target_time is None:
            return "未设置"
        return self.target_time.strftime("%Y-%m-%d %H:%M:%S.%f %Z")
