from __future__ import annotations

from datetime import datetime
from typing import Any

from .inputs import get_timezone
from .models import SearchWindow

LOG_TEXT_FIELDS = ("content", "message", "__raw__")


def format_timestamp(value: Any, timezone_name: str | None = None) -> str:
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
    return " ".join(value.split())


def render_log_text(log: dict[str, Any]) -> str:
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
