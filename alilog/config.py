from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .models import AliLogError, AuthConfig

DEFAULT_CONFIG_NAME = ".alilog.json"


def resolve_config_path() -> Path:
    return Path.home() / DEFAULT_CONFIG_NAME


def load_auth_config(path: Path) -> AuthConfig:
    if not path.exists():
        return AuthConfig()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return AuthConfig()
    except OSError as exc:
        raise AliLogError(f"读取配置文件失败: {path}") from exc
    except ValueError as exc:
        raise AliLogError(f"配置文件不是合法 JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise AliLogError(f"配置文件格式无效: {path}")
    cookie = payload.get("cookie")
    csrf_token = payload.get("csrf_token")
    if cookie is not None and not isinstance(cookie, str):
        raise AliLogError(f"配置文件中的 cookie 必须是字符串: {path}")
    if csrf_token is not None and not isinstance(csrf_token, str):
        raise AliLogError(f"配置文件中的 csrf_token 必须是字符串: {path}")
    return AuthConfig(cookie=cookie, csrf_token=csrf_token)


def save_auth_config(path: Path, config: AuthConfig) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        key: value
        for key, value in {
            "cookie": config.cookie,
            "csrf_token": config.csrf_token,
        }.items()
        if value
    }
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.chmod(temp_name, 0o600)
        os.replace(temp_name, path)
    except OSError as exc:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise AliLogError(f"写入配置文件失败: {path}") from exc
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def clear_auth_config(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise AliLogError(f"删除配置文件失败: {path}") from exc
