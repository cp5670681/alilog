from __future__ import annotations

import json
from pathlib import Path

import pytest

from alilog.config import (
    load_auth_config,
    load_project_config,
    resolve_auth_config_path,
    resolve_project_config_path,
    save_auth_config,
)
from alilog.models import AliLogError, AuthConfig


def test_save_and_load_auth_config(tmp_path: Path) -> None:
    path = tmp_path / ".alilog" / "auth.json"

    save_auth_config(
        path,
        AuthConfig(cookie="cookie=value", csrf_token="csrf-token"),
    )

    loaded = load_auth_config(path)
    assert loaded.cookie == "cookie=value"
    assert loaded.csrf_token == "csrf-token"
    assert json.loads(path.read_text(encoding="utf-8"))["cookie"] == "cookie=value"


def test_resolve_config_paths_use_home_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    assert resolve_auth_config_path() == tmp_path / ".alilog" / "auth.json"
    assert resolve_project_config_path() == tmp_path / ".alilog" / "settings.json"


def test_load_project_config_reads_expected_fields(tmp_path: Path) -> None:
    path = tmp_path / ".alilog" / "settings.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "default_project": "project-a",
                "default_logstore": "research",
            }
        ),
        encoding="utf-8",
    )

    config = load_project_config(path)

    assert config.default_project == "project-a"
    assert config.default_logstore == "research"


def test_load_project_config_rejects_invalid_default_project_type(
    tmp_path: Path,
) -> None:
    path = tmp_path / ".alilog" / "settings.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "default_project": ["project-a"],
                "default_logstore": "research",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(AliLogError):
        load_project_config(path)


def test_load_project_config_rejects_invalid_default_logstore_type(
    tmp_path: Path,
) -> None:
    path = tmp_path / ".alilog" / "settings.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "default_project": "project-a",
                "default_logstore": 123,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(AliLogError):
        load_project_config(path)
