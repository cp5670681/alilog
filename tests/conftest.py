from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from alilog import cli
from alilog.config import save_auth_config
from alilog.models import AuthConfig


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    return tmp_path / ".alilog.json"


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    path = tmp_path / "project"
    path.mkdir()
    return path


@pytest.fixture
def invoke_cli(
    runner: CliRunner,
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[[list[str]], Result]:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(project_root)

    def _invoke(args: list[str]) -> Result:
        return runner.invoke(cli.cli, args)

    return _invoke


@pytest.fixture
def save_auth(config_path: Path) -> Callable[[str | None, str | None], None]:
    def _save(
        cookie: str | None = "cookie=value",
        csrf_token: str | None = "csrf-token",
    ) -> None:
        save_auth_config(
            config_path,
            AuthConfig(cookie=cookie, csrf_token=csrf_token),
        )

    return _save


@pytest.fixture
def save_project_config(project_root: Path) -> Callable[[str], Path]:
    def _save(content: str) -> Path:
        path = project_root / ".alilog.json"
        path.write_text(content, encoding="utf-8")
        return path

    return _save
