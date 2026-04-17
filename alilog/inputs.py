from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .models import AliLogError, ContextCoordinates, SearchWindow

DEFAULT_TIMEZONE = "Asia/Shanghai"


def parse_pack_meta(pack_meta: str) -> ContextCoordinates:
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
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise AliLogError(f"未知时区: {timezone_name}") from exc


def parse_duration(value: str) -> int:
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
    value = raw_value.strip()
    tz = get_timezone(timezone_name)
    if re.fullmatch(r"\d+", value):
        if len(value) not in (10, 13):
            raise AliLogError("纯数字时间戳仅支持 10 位秒级或 13 位毫秒级。")
        timestamp = int(value)
        if len(value) == 13:
            timestamp //= 1000
        return timestamp

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
