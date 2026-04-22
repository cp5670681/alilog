"""
数据模型定义模块。

本模块定义了 alilog 项目中使用的核心数据结构，包括：
- 异常类型
- 配置数据结构
- 查询参数数据结构
- 运行时选项
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class AliLogError(RuntimeError):
    """阿里云日志服务操作异常。

    当 API 返回意外结果、配置错误或操作失败时抛出此异常。
    """


@dataclass(frozen=True)
class ContextCoordinates:
    """上下文查询坐标信息。

    用于定位日志上下文查询的起始位置，从 __pack_meta__ 字段解析得到。

    Attributes:
        shard_id: 分片 ID
        cursor: 游标位置
        pack_num: 包编号
        offset: 偏移量
    """

    shard_id: str
    cursor: str
    pack_num: str
    offset: str


@dataclass(frozen=True)
class AuthConfig:
    """认证配置信息。

    存储用于访问阿里云 SLS Console 的认证凭据。

    Attributes:
        cookie: HTTP Cookie 字符串，用于身份验证
        csrf_token: CSRF 令牌，用于防止跨站请求伪造
    """

    cookie: str | None = None
    csrf_token: str | None = None


@dataclass(frozen=True)
class ProjectConfig:
    """项目配置信息。

    存储项目默认日志服务配置，通常从 ~/.alilog/settings.json 文件加载。

    Attributes:
        default_project: 默认的阿里云 SLS 项目名称
        default_logstore: 默认的日志库名称
    """

    default_project: str | None = None
    default_logstore: str | None = None


@dataclass(frozen=True)
class SearchWindow:
    """日志查询时间窗口。

    定义日志查询的时间范围。

    Attributes:
        start: 起始时间戳（秒级）
        end: 结束时间戳（秒级）
        timezone_name: 时区名称，如 'Asia/Shanghai'
    """

    start: int
    end: int
    timezone_name: str


@dataclass(frozen=True)
class RuntimeOptions:
    """运行时选项。

    聚合了运行时需要的所有配置信息。

    Attributes:
        cookie: 认证 Cookie
        csrf_token: CSRF 令牌
        config_path: 全局认证配置文件路径（~/.alilog/auth.json）
        project_config_path: 默认项目配置文件路径（~/.alilog/settings.json）
    """

    cookie: str | None
    csrf_token: str | None
    config_path: Path
    project_config_path: Path
