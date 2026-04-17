from __future__ import annotations

import json
from pathlib import Path

from alilog.config import load_auth_config, save_auth_config
from alilog.models import AuthConfig


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
