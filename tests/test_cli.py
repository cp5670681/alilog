from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import alilog.usecases as usecases


def test_auth_save_writes_config_file(
    invoke_cli,
    config_path: Path,
) -> None:
    result = invoke_cli(
        ["auth", "save", "--cookie", "cookie=value", "--csrf-token", "csrf-token"]
    )

    assert result.exit_code == 0, result.output
    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["cookie"] == "cookie=value"
    assert saved["csrf_token"] == "csrf-token"
    assert str(config_path.parent) in result.output


def test_auth_save_requires_cookie(invoke_cli) -> None:
    result = invoke_cli(["auth", "save", "--csrf-token", "csrf-token"])

    assert result.exit_code != 0
    assert "Cookie 为必填" in result.output


def test_auth_save_clears_stale_csrf_when_only_cookie_is_updated(
    invoke_cli,
    config_path: Path,
) -> None:
    config_path.write_text(
        '{"cookie":"old-cookie","csrf_token":"old-csrf"}',
        encoding="utf-8",
    )

    result = invoke_cli(["auth", "save", "--cookie", "new-cookie"])

    assert result.exit_code == 0, result.output
    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved == {"cookie": "new-cookie"}


def test_auth_clear_removes_config_file(
    invoke_cli,
    config_path: Path,
) -> None:
    config_path.write_text('{"cookie":"cookie=value"}', encoding="utf-8")

    result = invoke_cli(["auth", "clear"])

    assert result.exit_code == 0, result.output
    assert not config_path.exists()


def test_auth_save_ignores_invalid_project_config(
    invoke_cli,
    project_root: Path,
) -> None:
    (project_root / ".alilog.json").write_text("{bad json", encoding="utf-8")

    result = invoke_cli(["auth", "save", "--cookie", "cookie=value"])

    assert result.exit_code == 0, result.output


def test_context_always_calls_prev_and_next(
    invoke_cli,
    monkeypatch: pytest.MonkeyPatch,
    save_auth,
    save_project_config,
) -> None:
    fake_client = MagicMock()
    fake_client.context_logs.side_effect = [
        {
            "data": {
                "packId": "PACK-ID",
                "prePackId": "PREV-PACK",
                "packMeta": "1|cursor|54|6",
                "prePackMeta": "0|cursor-prev|24|0",
                "logs": [
                    {"__index_number__": "-1", "__time__": 1776352587,
                     "content": "prev log"}
                ],
            }
        },
        {
            "data": {
                "packId": "PACK-ID",
                "prePackId": "PACK-ID",
                "packMeta": "1|cursor|54|36",
                "prePackMeta": "1|cursor|54|6",
                "logs": [
                    {"__index_number__": "+1", "__time__": 1776352588,
                     "content": "next log"}
                ],
            }
        },
    ]
    save_auth()
    save_project_config(
        '{"project":"project-a","default_logstore":"research","logstores":["research","nginx","app"]}'
    )
    monkeypatch.setattr(usecases, "get_client", lambda runtime: fake_client)

    result = invoke_cli(
        [
            "context",
            "--pack-meta",
            "1|cursor|54|6",
            "--pack-id",
            "PACK-ID",
        ]
    )

    assert result.exit_code == 0, result.output
    assert fake_client.context_logs.call_count == 2
    assert "[prev]" in result.output
    assert "[next]" in result.output


def test_search_uses_auth_from_default_config(
    invoke_cli,
    monkeypatch: pytest.MonkeyPatch,
    save_auth,
    save_project_config,
) -> None:
    fake_client = MagicMock()
    fake_client.search_logs.return_value = {
        "meta": {"count": 1, "progress": "Complete"},
        "data": [{"__time__": 1776352860, "content": "hello"}],
    }
    save_auth()
    save_project_config(
        '{"project":"project-a","default_logstore":"research","logstores":["research","nginx","app"]}'
    )
    monkeypatch.setattr(usecases, "get_client", lambda runtime: fake_client)

    result = invoke_cli(
        [
            "search",
            "--from",
            "2026-04-16 23:06:00",
            "--to",
            "2026-04-16 23:21:00",
            "--query",
            "error",
        ]
    )

    assert result.exit_code == 0, result.output
    assert "count=1" in result.output
    _, kwargs = fake_client.search_logs.call_args
    assert kwargs["query"] == "error | with_pack_meta"


def test_search_accepts_last_with_empty_query(
    invoke_cli,
    monkeypatch: pytest.MonkeyPatch,
    save_auth,
    save_project_config,
) -> None:
    fake_client = MagicMock()
    fake_client.search_logs.return_value = {"meta": {"count": 0}, "data": []}
    save_auth()
    save_project_config(
        '{"project":"project-a","default_logstore":"research","logstores":["research","nginx","app"]}'
    )
    monkeypatch.setattr(usecases, "get_client", lambda runtime: fake_client)

    result = invoke_cli(
        [
            "search",
            "--to",
            "2026-04-16 23:21:00",
            "--last",
            "15m",
            "--query",
            "",
        ]
    )

    assert result.exit_code == 0, result.output
    _, kwargs = fake_client.search_logs.call_args
    assert kwargs["start"] == 1776351960
    assert kwargs["end"] == 1776352860
    assert kwargs["query"] == "with_pack_meta"


def test_explicit_project_and_logstore_override_project_config(
    invoke_cli,
    monkeypatch: pytest.MonkeyPatch,
    save_auth,
    save_project_config,
) -> None:
    fake_client = MagicMock()
    fake_client.search_logs.return_value = {"meta": {"count": 0}, "data": []}
    save_auth()
    save_project_config(
        '{"project":"project-a","default_logstore":"research","logstores":["research","nginx","app"]}'
    )
    monkeypatch.setattr(usecases, "get_client", lambda runtime: fake_client)

    result = invoke_cli(
        [
            "search",
            "--project",
            "project-b",
            "--logstore",
            "nginx",
            "--from",
            "2026-04-16 23:06:00",
            "--to",
            "2026-04-16 23:21:00",
            "--query",
            "error",
        ]
    )

    assert result.exit_code == 0, result.output
    _, kwargs = fake_client.search_logs.call_args
    assert kwargs["project"] == "project-b"
    assert kwargs["logstore"] == "nginx"


def test_search_with_explicit_project_and_logstore_ignores_invalid_project_config(
    invoke_cli,
    monkeypatch: pytest.MonkeyPatch,
    project_root: Path,
    save_auth,
) -> None:
    fake_client = MagicMock()
    fake_client.search_logs.return_value = {"meta": {"count": 0}, "data": []}
    save_auth()
    (project_root / ".alilog.json").write_text("{bad json", encoding="utf-8")
    monkeypatch.setattr(usecases, "get_client", lambda runtime: fake_client)

    result = invoke_cli(
        [
            "search",
            "--project",
            "project-b",
            "--logstore",
            "nginx",
            "--from",
            "2026-04-16 23:06:00",
            "--to",
            "2026-04-16 23:21:00",
            "--query",
            "error",
        ]
    )

    assert result.exit_code == 0, result.output
    _, kwargs = fake_client.search_logs.call_args
    assert kwargs["project"] == "project-b"
    assert kwargs["logstore"] == "nginx"


def test_search_requires_project_when_project_config_missing(
    invoke_cli,
    monkeypatch: pytest.MonkeyPatch,
    save_auth,
) -> None:
    fake_client = MagicMock()
    save_auth()
    monkeypatch.setattr(usecases, "get_client", lambda runtime: fake_client)

    result = invoke_cli(
        [
            "search",
            "--from",
            "2026-04-16 23:06:00",
            "--to",
            "2026-04-16 23:21:00",
            "--query",
            "error",
        ]
    )

    assert result.exit_code != 0
    assert "缺少 ProjectName" in result.output


def test_search_requires_logstore_when_project_config_missing_default_logstore(
    invoke_cli,
    monkeypatch: pytest.MonkeyPatch,
    save_auth,
    save_project_config,
) -> None:
    fake_client = MagicMock()
    save_auth()
    save_project_config('{"project":"project-a","logstores":["research","nginx","app"]}')
    monkeypatch.setattr(usecases, "get_client", lambda runtime: fake_client)

    result = invoke_cli(
        [
            "search",
            "--from",
            "2026-04-16 23:06:00",
            "--to",
            "2026-04-16 23:21:00",
            "--query",
            "error",
        ]
    )

    assert result.exit_code != 0
    assert "缺少 LogStoreName" in result.output


@pytest.mark.parametrize("option", ["--page", "--size"])
def test_search_rejects_non_positive_pagination_values(
    invoke_cli,
    option: str,
    save_project_config,
) -> None:
    save_project_config(
        '{"project":"project-a","default_logstore":"research","logstores":["research","nginx","app"]}'
    )
    result = invoke_cli(
        [
            "search",
            "--from",
            "2026-04-16 23:06:00",
            "--to",
            "2026-04-16 23:21:00",
            "--query",
            "error",
            option,
            "0",
        ]
    )

    assert result.exit_code != 0
    assert "x>=1" in result.output


def test_context_rejects_non_positive_size(invoke_cli, save_project_config) -> None:
    save_project_config(
        '{"project":"project-a","default_logstore":"research","logstores":["research","nginx","app"]}'
    )
    result = invoke_cli(
        [
            "context",
            "--pack-meta",
            "1|cursor|54|6",
            "--pack-id",
            "PACK-ID",
            "--size",
            "0",
        ]
    )

    assert result.exit_code != 0
    assert "x>=1" in result.output


def test_install_skill_writes_claude_skill(
    invoke_cli,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLAUDE_HOME", str(tmp_path / "claude-home"))

    result = invoke_cli(["install-skill"])

    assert result.exit_code == 0, result.output
    assert "已安装 Claude skill" in result.output
    assert (tmp_path / "claude-home" / "skills" / "alilog" / "SKILL.md").exists()
