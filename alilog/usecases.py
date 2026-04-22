"""
业务用例模块。

本模块封装了核心业务逻辑，作为 CLI 和底层模块之间的桥梁。
提供以下用例：
- load_runtime: 加载运行时配置
- run_search: 执行日志查询
- run_context: 执行上下文查询
- save_auth: 保存认证配置
- login_auth: 通过浏览器登录并保存认证
"""

from __future__ import annotations

from collections.abc import Callable

from .browser_auth import DEFAULT_LOGIN_URL, capture_auth_via_cdp
from .client import AliyunSLSClient
from .config import (
    load_auth_config,
    load_project_config,
    resolve_auth_config_path,
    resolve_project_config_path,
    save_auth_config,
)
from .inputs import ensure_with_pack_meta, parse_pack_meta, resolve_search_window
from .models import AliLogError, AuthConfig, RuntimeOptions, SearchWindow


def load_runtime() -> RuntimeOptions:
    """加载运行时配置。

    从配置文件加载认证信息和项目配置，聚合为运行时选项。

    Returns:
        包含所有运行时配置的 RuntimeOptions 对象
    """
    config_path = resolve_auth_config_path()
    stored_auth = load_auth_config(config_path)
    project_config_path = resolve_project_config_path()
    return RuntimeOptions(
        cookie=stored_auth.cookie,
        csrf_token=stored_auth.csrf_token,
        config_path=config_path,
        project_config_path=project_config_path,
    )


def get_client(runtime: RuntimeOptions) -> AliyunSLSClient:
    """创建 SLS 客户端实例。

    Args:
        runtime: 运行时选项

    Returns:
        配置好的 AliyunSLSClient 实例
    """
    return AliyunSLSClient(
        cookie=runtime.cookie or "",
        csrf_token=runtime.csrf_token,
    )


def run_search(
    *,
    runtime: RuntimeOptions,
    project: str | None,
    logstore: str | None,
    start: str | None,
    end: str | None,
    last: str | None,
    timezone_name: str,
    query: str,
    page: int,
    size: int,
) -> tuple[SearchWindow, dict]:
    """执行日志查询。

    解析参数并调用 SLS API 执行日志查询。

    Args:
        runtime: 运行时选项
        project: 项目名称，为 None 时从项目配置读取
        logstore: 日志库名称，为 None 时从项目配置读取
        start: 起始时间字符串
        end: 结束时间字符串
        last: 相对时间窗口
        timezone_name: 时区名称
        query: 查询语句
        page: 页码
        size: 每页条数

    Returns:
        元组 (时间窗口, API 响应)
    """
    resolved_project = resolve_project_name(runtime, project)
    resolved_logstore = resolve_logstore_name(runtime, logstore)
    window = resolve_search_window(
        start=start,
        end=end,
        last=last,
        timezone_name=timezone_name,
    )
    response = get_client(runtime).search_logs(
        project=resolved_project,
        logstore=resolved_logstore,
        start=window.start,
        end=window.end,
        query=ensure_with_pack_meta(query),
        page=page,
        size=size,
    )
    return window, response


def run_context(
    *,
    runtime: RuntimeOptions,
    project: str | None,
    logstore: str | None,
    pack_meta: str,
    pack_id: str,
    size: int,
) -> dict[str, dict]:
    """执行上下文查询。

    查询指定日志位置的前后上下文日志。

    Args:
        runtime: 运行时选项
        project: 项目名称
        logstore: 日志库名称
        pack_meta: pack_meta 字符串
        pack_id: 日志包 ID
        size: 返回的日志条数

    Returns:
        字典 {'prev': 前向查询结果, 'next': 后向查询结果}
    """
    client = get_client(runtime)
    coords = parse_pack_meta(pack_meta)
    resolved_project = resolve_project_name(runtime, project)
    resolved_logstore = resolve_logstore_name(runtime, logstore)
    return {
        label: client.context_logs(
            project=resolved_project,
            logstore=resolved_logstore,
            coords=coords,
            pack_id=pack_id,
            size=size,
            reserve=reserve,
        )
        for label, reserve in (("prev", False), ("next", True))
    }


def save_auth(
    runtime: RuntimeOptions,
    cookie: str | None,
    csrf_token: str | None,
) -> None:
    """保存认证配置。

    合并现有配置和新提供的认证信息，保存到配置文件。

    Args:
        runtime: 运行时选项
        cookie: 新的 Cookie，为 None 时保留现有值
        csrf_token: 新的 CSRF Token

    Raises:
        AliLogError: Cookie 为空时抛出
    """
    final_cookie = runtime.cookie if cookie is None else cookie
    if not final_cookie:
        raise AliLogError("Cookie 为必填，请通过 --cookie 提供，或先从已有配置读取。")
    if cookie is None:
        final_csrf_token = (
            runtime.csrf_token if csrf_token is None
            else (csrf_token or None)
        )
    else:
        final_csrf_token = csrf_token or None
    save_auth_config(
        runtime.config_path,
        AuthConfig(cookie=final_cookie, csrf_token=final_csrf_token),
    )


def login_auth(
    runtime: RuntimeOptions,
    *,
    browser: str | None,
    login_url: str = DEFAULT_LOGIN_URL,
    confirm: Callable[[], object] | None = None,
) -> AuthConfig:
    """通过浏览器登录并保存认证。

    启动浏览器，等待用户完成登录，提取认证信息并保存。

    Args:
        runtime: 运行时选项
        browser: 浏览器可执行文件路径
        login_url: 登录页面 URL
        confirm: 确认回调函数

    Returns:
        保存认证配置
    """
    config = capture_auth_via_cdp(
        browser=browser,
        login_url=login_url,
        confirm=confirm,
    )
    save_auth_config(runtime.config_path, config)
    return config


def resolve_project_name(runtime: RuntimeOptions, project: str | None) -> str:
    """解析项目名称。

    如果未提供项目名称，尝试从项目配置中读取。

    Args:
        runtime: 运行时选项
        project: 命令行提供的项目名称

    Returns:
        解析后的项目名称

    Raises:
        AliLogError: 无法确定项目名称时抛出
    """
    if project:
        return project
    project_config = load_project_config(runtime.project_config_path)
    if project_config.default_project:
        return project_config.default_project
    raise AliLogError(
        "缺少 ProjectName，请通过 --project 提供，"
        "或在 ~/.alilog/settings.json 中配置 default_project。"
    )


def resolve_logstore_name(runtime: RuntimeOptions, logstore: str | None) -> str:
    """解析日志库名称。

    如果未提供日志库名称，尝试从项目配置中读取默认值。

    Args:
        runtime: 运行时选项
        logstore: 命令行提供的日志库名称

    Returns:
        解析后的日志库名称

    Raises:
        AliLogError: 无法确定日志库名称时抛出
    """
    if logstore:
        return logstore
    project_config = load_project_config(runtime.project_config_path)
    if project_config.default_logstore:
        return project_config.default_logstore
    raise AliLogError(
        "缺少 LogStoreName，请通过 --logstore 提供，"
        "或在 ~/.alilog/settings.json 中配置 default_logstore。"
    )
