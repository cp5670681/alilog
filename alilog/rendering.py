"""
输出渲染模块。

本模块负责将 API 响应数据格式化为用户可读的文本输出，包括：
- 日志查询结果渲染（render_search）：显示查询统计和日志列表
- 上下文查询结果渲染（render_context）：显示上下文日志列表
- 时间戳格式化（format_timestamp）：将时间戳转换为可读时间
- 日志文本提取（render_log_text）：从日志对象中提取主要文本内容
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .inputs import get_timezone
from .models import SearchWindow

LOG_TEXT_FIELDS = ("content", "message", "__raw__")


def format_timestamp(value: Any, timezone_name: str | None = None) -> str:
    """格式化时间戳为可读字符串。

    将 Unix 时间戳转换为 ISO 8601 格式的本地时间字符串。

    Args:
        value: 时间戳值（秒级），可以是任意类型，无效值返回 '-'
        timezone_name: 时区名称，用于转换时区

    Returns:
        格式化后的时间字符串，如 '2024-01-01T12:00:00+08:00'
    """
    if value is None:
        return "-"
    try:
        timezone = get_timezone(timezone_name) if timezone_name else None
        return datetime.fromtimestamp(int(value)).astimezone(timezone).isoformat(
            timespec="seconds"
        )
    except (TypeError, ValueError, OSError):
        return str(value)


def compact_text(value: str) -> str:
    """压缩文本中的空白字符。

    将连续的空白字符替换为单个空格，并去除首尾空白。

    Args:
        value: 原始文本

    Returns:
        压缩后的文本
    """
    return " ".join(value.split())


def render_log_text(log: dict[str, Any]) -> str:
    """渲染日志文本内容。

    从日志对象中提取主要文本内容，优先使用 content、message、__raw__ 字段。
    如果这些字段不存在，则拼接所有非元数据字段。

    Args:
        log: 日志对象

    Returns:
        格式化后的日志文本
    """
    for field in LOG_TEXT_FIELDS:
        value = log.get(field)
        if value not in (None, ""):
            return compact_text(str(value))

    parts = [
        f"{key}={value}"
        for key, value in log.items()
        if not key.startswith("__") and value not in (None, "")
    ]
    return compact_text(" ".join(parts))


def render_search(response: dict[str, Any], window: SearchWindow | None = None) -> str:
    """渲染日志查询结果。

    将 API 响应格式化为多行文本输出，包含查询统计信息和日志列表。

    Args:
        response: API 响应数据，包含 meta 和 data 字段
        window: 时间窗口信息，用于显示时间范围

    Returns:
        格式化后的查询结果文本
    """
    meta = response.get("meta", {})
    logs = response.get("data", [])
    lines = [
        f"count={meta.get('count', len(logs))} "
        f"progress={meta.get('progress', '-')} "
        f"elapsed={meta.get('elapsedMillisecond', '-')}ms "
        f"accurate={meta.get('isAccurate', '-')}"
    ]
    if window is not None:
        lines.append(
            f"range={format_timestamp(window.start, window.timezone_name)} -> "
            f"{format_timestamp(window.end, window.timezone_name)} "
            f"timezone={window.timezone_name} from={window.start} to={window.end}"
        )
    for index, log in enumerate(logs, start=1):
        tz_name = window.timezone_name if window else None
        lines.append(
            f"[{index}] "
            f"time={format_timestamp(log.get('__time__'), tz_name)} "
            f"pack_id={log.get('__tag__:__pack_id__', '-')}"
        )
        if "__pack_meta__" in log:
            lines.append(f"    pack_meta={log['__pack_meta__']}")
        source = log.get("__source__") or log.get("__tag__:_pod_name_") or "-"
        lines.append(f"    source={source}")
        lines.append(f"    {render_log_text(log)}")
    return "\n".join(lines)


def render_context(
    response: dict[str, Any],
    label: str,
    timezone_name: str | None = None,
) -> str:
    """渲染上下文查询结果。

    将上下文查询 API 响应格式化为多行文本输出。

    Args:
        response: API 响应数据
        label: 标签，通常为 'prev' 或 'next'
        timezone_name: 时区名称，用于时间格式化

    Returns:
        格式化后的上下文查询结果文本
    """
    data = response.get("data", {})
    logs = data.get("logs", [])
    lines = [
        f"[{label}] total={data.get('total', len(logs))} "
        f"pack_id={data.get('packId', '-')}"
    ]
    if data.get("prePackId"):
        lines.append(f"pre_pack_id={data.get('prePackId')}")
    if data.get("packMeta"):
        lines.append(f"pack_meta={data.get('packMeta')}")
    if data.get("prePackMeta"):
        lines.append(f"pre_pack_meta={data.get('prePackMeta')}")
    for log in logs:
        lines.append(
            f"{log.get('__index_number__', '?'):>4} "
            f"{format_timestamp(log.get('__time__'), timezone_name)} "
            f"{render_log_text(log)}"
        )
    return "\n".join(lines)
