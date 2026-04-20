"""
配置文件管理模块。

本模块负责管理 alilog 的配置文件，包括：
- 全局认证配置（~/.alilog.json）：存储 Cookie 和 CSRF Token
- 项目配置（项目根目录的 .alilog.json）：存储项目名称和日志库规则配置

配置文件采用 JSON 格式，支持原子写入以确保配置安全。
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .models import AliLogError, AuthConfig, LogstoreRule, ProjectConfig

DEFAULT_CONFIG_NAME = ".alilog.json"


def resolve_config_path() -> Path:
    """解析全局配置文件路径。

    Returns:
        全局配置文件的完整路径，位于用户主目录下。
    """
    return Path.home() / DEFAULT_CONFIG_NAME


def load_auth_config(path: Path) -> AuthConfig:
    """加载认证配置。

    从指定路径读取 JSON 配置文件并解析为 AuthConfig 对象。

    Args:
        path: 配置文件路径

    Returns:
        解析后的认证配置对象

    Raises:
        AliLogError: 配置文件读取失败、JSON 格式错误或字段类型错误
    """
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
    """查找项目配置文件路径。

    从指定目录开始向上搜索，直到找到 .alilog.json 文件或到达用户主目录。

    Args:
        start: 搜索起始目录，默认为当前工作目录

    Returns:
        找到的配置文件路径，未找到则返回 None
    """
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
    """加载项目配置。

    从指定路径读取 JSON 配置文件并解析为 ProjectConfig 对象。

    Args:
        path: 配置文件路径，可以为 None

    Returns:
        解析后的项目配置对象，路径为 None 时返回空配置

    Raises:
        AliLogError: 配置文件读取失败、JSON 格式错误或字段类型错误
    """
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
    logstore_rules = payload.get("logstore_rules", [])

    if project is not None and not isinstance(project, str):
        raise AliLogError(f"项目配置中的 project 必须是字符串: {path}")
    if default_logstore is not None and not isinstance(default_logstore, str):
        raise AliLogError(f"项目配置中的 default_logstore 必须是字符串: {path}")
    if not isinstance(logstore_rules, list):
        raise AliLogError(f"项目配置中的 logstore_rules 必须是对象数组: {path}")

    parsed_rules: list[LogstoreRule] = []
    for index, item in enumerate(logstore_rules, start=1):
        if not isinstance(item, dict):
            raise AliLogError(
                f"项目配置中的 logstore_rules 第 {index} 项必须是对象: {path}"
            )
        logstore = item.get("logstore")
        command = item.get("command")
        description = item.get("description")
        if not isinstance(logstore, str):
            raise AliLogError(
                "项目配置中的 logstore_rules 第 "
                f"{index} 项 logstore 必须是字符串: {path}"
            )
        if not isinstance(command, str):
            raise AliLogError(
                "项目配置中的 logstore_rules 第 "
                f"{index} 项 command 必须是字符串: {path}"
            )
        if not isinstance(description, str):
            raise AliLogError(
                "项目配置中的 logstore_rules 第 "
                f"{index} 项 description 必须是字符串: {path}"
            )
        parsed_rules.append(
            LogstoreRule(
                logstore=logstore,
                command=command,
                description=description,
            )
        )

    if default_logstore and parsed_rules and default_logstore not in {
        rule.logstore for rule in parsed_rules
    }:
        raise AliLogError(
            f"项目配置中的 default_logstore 必须存在于 logstore_rules 中: {path}"
        )

    return ProjectConfig(
        project=project,
        default_logstore=default_logstore,
        logstore_rules=tuple(parsed_rules),
    )


def save_auth_config(path: Path, config: AuthConfig) -> None:
    """保存认证配置。

    将认证配置以 JSON 格式原子写入指定路径。使用临时文件和原子替换
    确保写入安全，并设置文件权限为 600 以保护敏感信息。

    Args:
        path: 配置文件保存路径
        config: 要保存的认证配置对象

    Raises:
        AliLogError: 写入配置文件失败
    """
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
