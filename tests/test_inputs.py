from __future__ import annotations

import pytest

from alilog.inputs import (
    ensure_with_pack_meta,
    parse_pack_meta,
    parse_time_value,
    resolve_search_window,
)
from alilog.models import AliLogError


def test_parse_pack_meta() -> None:
    coords = parse_pack_meta("1|cursor-value|54|6")

    assert coords.shard_id == "1"
    assert coords.cursor == "cursor-value"
    assert coords.pack_num == "54"
    assert coords.offset == "6"


def test_parse_pack_meta_rejects_invalid_value() -> None:
    with pytest.raises(AliLogError):
        parse_pack_meta("1|cursor-only")


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        ("1776352860", 1776352860),
        ("1776352860000", 1776352860),
        ("2026-04-16 23:21:00", 1776352860),
    ],
)
def test_parse_time_value_supported_formats(raw_value: str, expected: int) -> None:
    assert parse_time_value(raw_value, "Asia/Shanghai") == expected


@pytest.mark.parametrize("raw_value", ["17763528600", "177635286000"])
def test_parse_time_value_rejects_ambiguous_numeric_timestamp(raw_value: str) -> None:
    with pytest.raises(AliLogError):
        parse_time_value(raw_value, "Asia/Shanghai")


def test_resolve_search_window_supports_last() -> None:
    window = resolve_search_window(
        start=None,
        end="2026-04-16 23:21:00",
        last="15m",
        timezone_name="Asia/Shanghai",
    )

    assert window.start == 1776351960
    assert window.end == 1776352860
    assert window.timezone_name == "Asia/Shanghai"


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("error", "error | with_pack_meta"),
        ("error | with_pack_meta", "error | with_pack_meta"),
        ("", "with_pack_meta"),
    ],
)
def test_ensure_with_pack_meta(query: str, expected: str) -> None:
    assert ensure_with_pack_meta(query) == expected
