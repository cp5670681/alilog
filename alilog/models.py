from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class AliLogError(RuntimeError):
    """Raised when the Aliyun log console API returns an unexpected result."""


@dataclass(frozen=True)
class ContextCoordinates:
    shard_id: str
    cursor: str
    pack_num: str
    offset: str


@dataclass(frozen=True)
class AuthConfig:
    cookie: str | None = None
    csrf_token: str | None = None


@dataclass(frozen=True)
class ProjectConfig:
    project: str | None = None
    default_logstore: str | None = None
    logstores: tuple[str, ...] = ()


@dataclass(frozen=True)
class SearchWindow:
    start: int
    end: int
    timezone_name: str


@dataclass(frozen=True)
class RuntimeOptions:
    cookie: str | None
    csrf_token: str | None
    config_path: Path
    project_config_path: Path | None
