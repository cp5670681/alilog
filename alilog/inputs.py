"""
输入解析模块。

本模块负责解析和处理用户输入的各种参数，包括：
- 时间解析：支持时间戳、ISO 时间、相对时间等多种格式
- pack_meta 解析：解析日志上下文查询所需的坐标信息
- 查询语句处理：自动追加 with_pack_meta 以获取日志元数据
"""

from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .models import AliLogError, ContextCoordinates, SearchWindow

DEFAULT_TIMEZONE = "Asia/Shanghai"


def parse_pack_meta(pack_meta: str) -> ContextCoordinates:
    """解析 pack_meta 字符串。

    pack_meta 是日志上下文查询的关键参数，格式为 'ShardId|Cursor|PackNum|Offset'。

    Args:
        pack_meta: 从 search 结果中的 __pack_meta__ 字段获取

    Returns:
        解析后的上下文坐标对象

    Raises:
        AliLogError: pack_meta 格式无效
    """
    parts = pack_meta.split("|")
    if len(parts) != 4 or not all(parts):
        raise AliLogError(
            "pack_meta 格式无效，预期为 'ShardId|Cursor|PackNum|Offset'。"
        )
    return ContextCoordinates(
        shard_id=parts[0],
        cursor=parts[1],
        pack_num=parts[2],
        offset=parts[3],
    )


def get_timezone(timezone_name: str) -> ZoneInfo:
    """获取时区对象。

    Args:
        timezone_name: IANA 时区名称，如 'Asia/Shanghai'

    Returns:
        对应的 ZoneInfo 对象

    Raises:
        AliLogError: 时区名称无效
    """
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise AliLogError(f"未知时区: {timezone_name}") from exc


def parse_duration(value: str) -> int:
    """解析相对时间持续时间。

    支持的格式：30s（秒）、15m（分钟）、2h（小时）、7d（天）、1w（周）。

    Args:
        value: 相对时间字符串

    Returns:
        持续时间（秒）

    Raises:
        AliLogError: 时间格式无效
    """
    match = re.fullmatch(r"(?i)\s*(\d+)\s*([smhdw])\s*", value)
    if not match:
        raise AliLogError(
            "相对时间格式无效，支持的格式例如: 30s, 15m, 2h, 7d, 1w"
        )
    amount = int(match.group(1))
    unit = match.group(2).lower()
    multiplier = {
        "s": 1,
        "m": 60,
        "h": 3600,
        "d": 86400,
        "w": 604800,
    }[unit]
    return amount * multiplier


def parse_time_value(raw_value: str, timezone_name: str) -> int:
    """解析时间值为 Unix 时间戳。

    支持的时间格式：
    - 10 位数字：秒级时间戳
    - 'now'：当前时间
    - ISO 8601 格式：如 '2024-01-01T00:00:00+08:00'
    - 常规格式：'YYYY-MM-DD HH:MM:SS'、'YYYY-MM-DD HH:MM'、'YYYY-MM-DD'

    Args:
        raw_value: 时间字符串
        timezone_name: 解析无时区时间时使用的时区

    Returns:
        Unix 时间戳（秒级）

    Raises:
        AliLogError: 时间格式无效
    """
    value = raw_value.strip()
    tz = get_timezone(timezone_name)
    if re.fullmatch(r"\d+", value):
        if len(value) != 10:
            raise AliLogError("纯数字时间戳仅支持 10 位秒级。")
        return int(value)

    if value.lower() == "now":
        return int(datetime.now(tz).timestamp())

    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        parsed = None

    if parsed is None:
        for pattern in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d",
        ):
            try:
                parsed = datetime.strptime(value, pattern)
                break
            except ValueError:
                continue

    if parsed is None:
        raise AliLogError(
            "时间格式无效，支持时间戳、ISO 时间、"
            "'YYYY-MM-DD HH:MM[:SS]'、'YYYY-MM-DD' 和 'now'。"
        )

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=tz)
    return int(parsed.timestamp())


def ensure_with_pack_meta(query: str) -> str:
    """确保查询语句包含 with_pack_meta。

    with_pack_meta 用于获取日志的元数据信息，是上下文查询的必要条件。

    Args:
        query: 原始查询语句

    Returns:
        包含 with_pack_meta 的查询语句
    """
    normalized_query = query.strip()
    if not normalized_query:
        return "with_pack_meta"
    segments = [segment.strip() for segment in normalized_query.split("|")]
    if "with_pack_meta" in segments:
        return normalized_query
    return f"{normalized_query} | with_pack_meta"


def resolve_search_window(
    *,
    start: str | None,
    end: str | None,
    last: str | None,
    timezone_name: str,
) -> SearchWindow:
    """解析日志查询时间窗口。

    支持两种模式：
    1. 绝对时间：通过 --from 和 --to 指定起止时间
    2. 相对时间：通过 --last 指定相对于当前时间的时间窗口

    Args:
        start: 起始时间字符串
        end: 结束时间字符串
        last: 相对时间窗口，如 '15m'、'2h'
        timezone_name: 时区名称

    Returns:
        解析后的时间窗口对象

    Raises:
        AliLogError: 参数冲突或时间范围无效
    """
    if last:
        if start is not None:
            raise AliLogError("--last 和 --from 不能同时使用。")
        duration_seconds = parse_duration(last)
        end_value = (
            parse_time_value(end, timezone_name)
            if end is not None
            else int(datetime.now(get_timezone(timezone_name)).timestamp())
        )
        start_value = end_value - duration_seconds
    else:
        if start is None or end is None:
            raise AliLogError("search 命令需要提供 --from/--to，或提供 --last。")
        start_value = parse_time_value(start, timezone_name)
        end_value = parse_time_value(end, timezone_name)

    if start_value >= end_value:
        raise AliLogError("时间范围无效: 起始时间必须早于结束时间。")
    return SearchWindow(
        start=start_value,
        end=end_value,
        timezone_name=timezone_name,
    )
