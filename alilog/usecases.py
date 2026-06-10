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

import sys
from collections.abc import Callable

from .auto_login import auto_login_with_password
from .browser_auth import DEFAULT_LOGIN_URL, capture_auth_via_cdp
from .client import AliyunSLSClient
from .config import (
    load_auth_config,
    resolve_auth_config_path,
    save_auth_config,
)
from .inputs import ensure_with_pack_meta, parse_pack_meta, resolve_search_window
from .models import AliLogError, AuthConfig, RuntimeOptions, SearchWindow


def load_runtime() -> RuntimeOptions:
    """加载运行时配置。

    从配置文件加载认证信息，聚合为运行时选项。

    Returns:
        包含所有运行时配置的 RuntimeOptions 对象
    """
    config_path = resolve_auth_config_path()
    stored_auth = load_auth_config(config_path)
    return RuntimeOptions(
        cookie=stored_auth.cookie,
        csrf_token=stored_auth.csrf_token,
        username=stored_auth.username,
        password=stored_auth.password,
        seed=stored_auth.seed,
        config_path=config_path,
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
    project: str,
    logstore: str,
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
        project: 项目名称
        logstore: 日志库名称
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
    window = resolve_search_window(
        start=start,
        end=end,
        last=last,
        timezone_name=timezone_name,
    )
    resolved_query = ensure_with_pack_meta(query)

    def search_with_runtime(active_runtime: RuntimeOptions) -> dict:
        return get_client(active_runtime).search_logs(
            project=project,
            logstore=logstore,
            start=window.start,
            end=window.end,
            query=resolved_query,
            page=page,
            size=size,
        )

    response = call_with_auto_reauth(
        runtime,
        search_with_runtime,
    )
    return window, response


def run_context(
    *,
    runtime: RuntimeOptions,
    project: str,
    logstore: str,
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
    coords = parse_pack_meta(pack_meta)
    results: dict[str, dict] = {}
    for label, reserve in (("prev", False), ("next", True)):
        def context_with_runtime(
            active_runtime: RuntimeOptions,
            *,
            reserve: bool = reserve,
        ) -> dict:
            return get_client(active_runtime).context_logs(
                project=project,
                logstore=logstore,
                coords=coords,
                pack_id=pack_id,
                size=size,
                reserve=reserve,
            )

        results[label] = call_with_auto_reauth(
            runtime,
            context_with_runtime,
        )
    return results


def save_auth(
    runtime: RuntimeOptions,
    cookie: str | None,
    csrf_token: str | None,
    username: str | None = None,
    password: str | None = None,
    seed: str | None = None,
) -> None:
    """保存认证配置。

    合并现有配置和新提供的认证信息，保存到配置文件。

    Args:
        runtime: 运行时选项
        cookie: 新的 Cookie，为 None 时保留现有值
        csrf_token: 新的 CSRF Token
        username: 新的 RAM 用户名，为 None 时保留现有值
        password: 新的 RAM 用户密码，为 None 时保留现有值
        seed: 新的 TOTP seed，为 None 时保留现有值

    Raises:
        AliLogError: Cookie 为空时抛出
    """
    final_cookie = runtime.cookie if cookie is None else cookie
    if cookie is None:
        final_csrf_token = (
            runtime.csrf_token if csrf_token is None
            else (csrf_token or None)
        )
    else:
        final_csrf_token = csrf_token or None
    final_username = runtime.username if username is None else (username or None)
    final_password = runtime.password if password is None else (password or None)
    final_seed = runtime.seed if seed is None else (seed or None)
    if not final_cookie and not all((final_username, final_password, final_seed)):
        raise AliLogError(
            "Cookie 为必填，请通过 --cookie 提供，或提供完整的 "
            "username/password/seed。"
        )
    save_auth_config(
        runtime.config_path,
        AuthConfig(
            cookie=final_cookie,
            csrf_token=final_csrf_token,
            username=final_username,
            password=final_password,
            seed=final_seed,
        ),
    )


def login_auth(
    runtime: RuntimeOptions,
    *,
    browser: str | None,
    login_url: str = DEFAULT_LOGIN_URL,
    headless: bool = True,
    confirm: Callable[[], object] | None = None,
) -> AuthConfig:
    """登录并保存认证。

    有自动登录凭据时使用账号密码登录；否则启动浏览器等待用户手动登录，
    提取认证信息并保存。

    Args:
        runtime: 运行时选项
        browser: 浏览器可执行文件路径
        login_url: 登录页面 URL
        headless: 是否使用无头模式
        confirm: 确认回调函数

    Returns:
        保存认证配置
    """
    if has_auto_login_credentials(runtime):
        return save_refreshed_auth(runtime, auto_login_auth(runtime, headless=headless))
    config = capture_auth_via_cdp(
        browser=browser,
        login_url=login_url,
        confirm=confirm,
    )
    return save_refreshed_auth(runtime, config)


def auto_login_auth(runtime: RuntimeOptions, *, headless: bool = True) -> AuthConfig:
    """使用 auth.json 中的账号、密码和 seed 自动登录。"""
    if not runtime.username or not runtime.password or not runtime.seed:
        raise AliLogError(
            "认证已失效，且 ~/.alilog/auth.json 缺少 username/password/seed，"
            "无法自动登录。"
        )
    return auto_login_with_password(
        username=runtime.username,
        password=runtime.password,
        seed=runtime.seed,
        headless=headless,
    )


def call_with_auto_reauth(
    runtime: RuntimeOptions,
    call: Callable[[RuntimeOptions], dict],
) -> dict:
    """调用接口；认证失效时自动登录并重试一次。"""
    if not runtime.cookie and has_auto_login_credentials(runtime):
        refreshed = refresh_auth_with_notice(runtime)
        return call(runtime_with_auth(runtime, refreshed))
    try:
        return call(runtime)
    except AliLogError as exc:
        if not is_auth_expired_error(exc):
            raise
        if not has_auto_login_credentials(runtime):
            raise manual_login_required_error() from exc
    refreshed = refresh_auth_with_notice(runtime)
    return call(runtime_with_auth(runtime, refreshed))


def refresh_auth_with_notice(runtime: RuntimeOptions) -> AuthConfig:
    """自动登录刷新认证，并向控制台输出进度提示。"""
    print("认证已失效，正在自动登录并刷新 Cookie...", file=sys.stderr)
    refreshed = save_refreshed_auth(runtime, auto_login_auth(runtime))
    print("自动登录成功，已刷新认证信息。", file=sys.stderr)
    return refreshed


def has_auto_login_credentials(runtime: RuntimeOptions) -> bool:
    """判断运行时是否具备自动登录所需凭据。"""
    return bool(runtime.username and runtime.password and runtime.seed)


def manual_login_required_error() -> AliLogError:
    """构造需要手动刷新认证的错误。"""
    return AliLogError(
        "认证已失效。请先运行 `alilog auth login` 手动登录并刷新 Cookie，"
        "然后重试当前命令。"
    )


def runtime_with_auth(runtime: RuntimeOptions, auth: AuthConfig) -> RuntimeOptions:
    """用刷新后的认证信息构造新的运行时。"""
    return RuntimeOptions(
        cookie=auth.cookie,
        csrf_token=auth.csrf_token,
        username=auth.username,
        password=auth.password,
        seed=auth.seed,
        config_path=runtime.config_path,
    )


def is_auth_expired_error(exc: AliLogError) -> bool:
    """判断错误是否表示认证失效。"""
    message = str(exc).lower()
    return any(
        marker in message
        for marker in (
            "http 401",
            "http 403",
            "unauthorized",
            "forbidden",
            "csrf",
            "login",
            "not login",
            "未登录",
            "登录",
            "认证",
        )
    )


def save_refreshed_auth(
    runtime: RuntimeOptions,
    config: AuthConfig,
) -> AuthConfig:
    """保存新 cookie/csrf，同时保留自动登录凭据。"""
    refreshed = AuthConfig(
        cookie=config.cookie,
        csrf_token=config.csrf_token,
        username=runtime.username,
        password=runtime.password,
        seed=runtime.seed,
    )
    save_auth_config(runtime.config_path, refreshed)
    return refreshed
