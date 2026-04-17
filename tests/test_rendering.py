from __future__ import annotations

from alilog.models import SearchWindow
from alilog.rendering import render_context, render_search


def test_render_search_uses_message_when_content_missing() -> None:
    output = render_search(
        {
            "meta": {"count": 1},
            "data": [{"__time__": 1776352860, "message": "hello world"}],
        },
        SearchWindow(1776352800, 1776352860, "UTC"),
    )

    assert "hello world" in output
    assert "+00:00" in output


def test_render_context_uses_requested_timezone() -> None:
    output = render_context(
        {
            "data": {
                "logs": [
                    {"__index_number__": "1", "__time__": 1776352860,
                    "level": "INFO", "msg": "ok"}
                ]
            }
        },
        "next",
        "UTC",
    )

    assert "level=INFO msg=ok" in output
    assert "+00:00" in output
