from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .models import AliLogError, AuthConfig, ProjectConfig

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


def find_project_config_path(start: Path | None = None) -> Path | None:
    current = (start or Path.cwd()).resolve()
    home = Path.home().resolve()
    for directory in (current, *current.parents):
        if directory == home:
            continue
        candidate = directory / DEFAULT_CONFIG_NAME
        if candidate.exists():
            return candidate
    return None


def load_project_config(path: Path | None) -> ProjectConfig:
    if path is None or not path.exists():
        return ProjectConfig()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return ProjectConfig()
    except OSError as exc:
        raise AliLogError(f"读取项目配置文件失败: {path}") from exc
    except ValueError as exc:
        raise AliLogError(f"项目配置文件不是合法 JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise AliLogError(f"项目配置文件格式无效: {path}")

    project = payload.get("project")
    default_logstore = payload.get("default_logstore")
    logstores = payload.get("logstores", [])

    if project is not None and not isinstance(project, str):
        raise AliLogError(f"项目配置中的 project 必须是字符串: {path}")
    if default_logstore is not None and not isinstance(default_logstore, str):
        raise AliLogError(f"项目配置中的 default_logstore 必须是字符串: {path}")
    if not isinstance(logstores, list) or any(
        not isinstance(item, str) for item in logstores
    ):
        raise AliLogError(f"项目配置中的 logstores 必须是字符串数组: {path}")
    if default_logstore and logstores and default_logstore not in logstores:
        raise AliLogError(
            f"项目配置中的 default_logstore 必须存在于 logstores 中: {path}"
        )

    return ProjectConfig(
        project=project,
        default_logstore=default_logstore,
        logstores=tuple(logstores),
    )


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
