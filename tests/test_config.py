from __future__ import annotations

import json
from pathlib import Path

import pytest

from alilog.config import (
    find_project_config_path,
    load_auth_config,
    load_project_config,
    save_auth_config,
)
from alilog.models import AliLogError, AuthConfig, LogstoreRule


def test_save_and_load_auth_config(tmp_path: Path) -> None:
    path = tmp_path / ".alilog.json"

    save_auth_config(
        path,
        AuthConfig(cookie="cookie=value", csrf_token="csrf-token"),
    )

    loaded = load_auth_config(path)
    assert loaded.cookie == "cookie=value"
    assert loaded.csrf_token == "csrf-token"
    assert json.loads(path.read_text(encoding="utf-8"))["cookie"] == "cookie=value"


def test_find_project_config_path_walks_up_parents(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    nested = project_root / "src" / "pkg"
    nested.mkdir(parents=True)
    config_path = project_root / ".alilog.json"
    config_path.write_text("{}", encoding="utf-8")

    assert find_project_config_path(nested) == config_path


def test_load_project_config_reads_expected_fields(tmp_path: Path) -> None:
    path = tmp_path / ".alilog.json"
    path.write_text(
        json.dumps(
            {
                "project": "project-a",
                "default_logstore": "research",
                "logstore_rules": [
                    {
                        "logstore": "research",
                        "command": "bundle exec puma -C config/puma.rb",
                        "description": "Rails Web 服务",
                    },
                    {
                        "logstore": "nginx",
                        "command": "nginx -g daemon off;",
                        "description": "Nginx 入口流量",
                    },
                    {
                        "logstore": "app",
                        "command": "bundle exec sidekiq -C config/sidekiq.yml",
                        "description": "通用异步任务",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    config = load_project_config(path)

    assert config.project == "project-a"
    assert config.default_logstore == "research"
    assert config.logstore_rules == (
        LogstoreRule(
            logstore="research",
            command="bundle exec puma -C config/puma.rb",
            description="Rails Web 服务",
        ),
        LogstoreRule(
            logstore="nginx",
            command="nginx -g daemon off;",
            description="Nginx 入口流量",
        ),
        LogstoreRule(
            logstore="app",
            command="bundle exec sidekiq -C config/sidekiq.yml",
            description="通用异步任务",
        ),
    )


def test_load_project_config_rejects_default_logstore_not_in_logstore_rules(
    tmp_path: Path,
) -> None:
    path = tmp_path / ".alilog.json"
    path.write_text(
        json.dumps(
            {
                "project": "project-a",
                "default_logstore": "research",
                "logstore_rules": [
                    {
                        "logstore": "nginx",
                        "command": "nginx -g daemon off;",
                        "description": "Nginx 入口流量",
                    },
                    {
                        "logstore": "app",
                        "command": "bundle exec sidekiq -C config/sidekiq.yml",
                        "description": "通用异步任务",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(AliLogError):
        load_project_config(path)


def test_load_project_config_rejects_invalid_logstore_rule_shape(
    tmp_path: Path,
) -> None:
    path = tmp_path / ".alilog.json"
    path.write_text(
        json.dumps(
            {
                "project": "project-a",
                "logstore_rules": [
                    {
                        "logstore": "research",
                        "command": "bundle exec puma -C config/puma.rb",
                        "description": 123,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(AliLogError):
        load_project_config(path)
