"""
命令行接口模块。

本模块定义了 alilog 的命令行接口，使用 Click 框架实现。
提供以下命令：
- search: 日志查询
- context: 上下文查询
- auth save: 保存认证配置
- auth login: 通过浏览器登录
- install-skill: 安装 Claude skill
"""

from __future__ import annotations

from functools import wraps
from typing import Any

import click
import httpx

from .inputs import DEFAULT_TIMEZONE
from .models import AliLogError
from .rendering import render_context, render_search
from .skills import INSTALL_REPO_URL
from .usecases import (
    install_skill,
    load_runtime,
    login_auth,
    run_context,
    run_search,
    save_auth,
)


def fail_as_click(exc: Exception) -> Exception:
    """将异常转换为 Click 异常。

    Args:
        exc: 原始异常

    Returns:
        Click 异常
    """
    return click.ClickException(str(exc))


def as_click_command(func: Any) -> Any:
    """装饰器：捕获异常并转换为 Click 异常。

    Args:
        func: 要装饰的函数

    Returns:
        装饰后的函数
    """
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except (AliLogError, httpx.HTTPError) as exc:
            raise fail_as_click(exc) from exc

    return wrapper


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
def cli() -> None:
    """阿里云 SLS Console 日志查询 CLI。"""


@cli.command("search")
@click.option(
    "--project",
    help="ProjectName。未提供时尝试从项目根目录的 .alilog.json 读取。",
)
@click.option(
    "--logstore",
    help="LogStoreName。未提供时尝试从项目根目录的 .alilog.json 读取。",
)
@click.option(
    "--from",
    "start",
    help="起始时间，支持时间戳、ISO 时间、'YYYY-MM-DD HH:MM[:SS]'。",
)
@click.option(
    "--to",
    "end",
    help="结束时间，支持时间戳、ISO 时间、'YYYY-MM-DD HH:MM[:SS]' 或 now。",
)
@click.option("--last", help="相对时间窗口，例如 15m、2h、1d。与 --from 互斥。")
@click.option(
    "--timezone",
    default=DEFAULT_TIMEZONE,
    show_default=True,
    help="解析无时区时间字符串时使用的时区。",
)
@click.option("--query", required=True, help="查询语句。会自动追加 with_pack_meta。")
@click.option(
    "--page",
    default=1,
    show_default=True,
    type=click.IntRange(min=1),
    help="页码",
)
@click.option(
    "--size",
    default=20,
    show_default=True,
    type=click.IntRange(min=1),
    help="每页条数",
)
@as_click_command
def search_command(
    project: str,
    logstore: str,
    start: str | None,
    end: str | None,
    last: str | None,
    timezone: str,
    query: str,
    page: int,
    size: int,
) -> None:
    """执行日志查询。

    查询指定项目和日志库的日志，支持多种时间格式和分页。
    """
    window, response = run_search(
        runtime=load_runtime(),
        project=project,
        logstore=logstore,
        start=start,
        end=end,
        last=last,
        timezone_name=timezone,
        query=query,
        page=page,
        size=size,
    )
    click.echo(render_search(response, window))


@cli.command("context")
@click.option(
    "--project",
    help="ProjectName。未提供时尝试从项目根目录的 .alilog.json 读取。",
)
@click.option(
    "--logstore",
    help="LogStoreName。未提供时尝试从项目根目录的 .alilog.json 读取。",
)
@click.option(
    "--pack-meta",
    required=True,
    help="从 search 结果中的 __pack_meta__ 直接传入。",
)
@click.option("--pack-id", required=True, help="PackId")
@click.option(
    "--size",
    default=30,
    show_default=True,
    type=click.IntRange(min=1),
    help="上下文条数",
)
@click.option(
    "--timezone",
    default=DEFAULT_TIMEZONE,
    show_default=True,
    help="显示时间时使用的时区。",
)
@as_click_command
def context_command(
    project: str,
    logstore: str,
    pack_meta: str,
    pack_id: str,
    size: int,
    timezone: str,
) -> None:
    """执行上下文查询。

    查询指定日志位置前后的上下文日志。
    """
    responses = run_context(
        runtime=load_runtime(),
        project=project,
        logstore=logstore,
        pack_meta=pack_meta,
        pack_id=pack_id,
        size=size,
    )
    click.echo(render_context(responses["prev"], "prev", timezone))
    click.echo()
    click.echo(render_context(responses["next"], "next", timezone))


@cli.group("auth")
def auth_group() -> None:
    """保存或清除本地认证配置。"""


@auth_group.command("save")
@click.option("--cookie", help="要保存的 Cookie。")
@click.option("--csrf-token", help="要保存的 csrf token。")
@as_click_command
def auth_save(cookie: str | None, csrf_token: str | None) -> None:
    """保存认证配置。

    将 Cookie 和 CSRF Token 保存到 ~/.alilog.json 文件。
    """
    runtime = load_runtime()
    save_auth(runtime, cookie, csrf_token)
    click.echo(f"已保存认证配置到: {runtime.config_path}")


@auth_group.command("login")
@click.option(
    "--browser",
    help="Chromium 浏览器可执行文件路径。未提供时自动探测 Chrome/Chromium/Edge。",
)
@click.option(
    "--url",
    "login_url",
    default="https://sls.console.aliyun.com/lognext/",
    show_default=True,
    help="打开的登录页地址。",
)
@as_click_command
def auth_login(browser: str | None, login_url: str) -> None:
    """通过浏览器登录。

    启动浏览器，等待用户完成阿里云登录，自动提取并保存认证信息。
    """
    runtime = load_runtime()
    click.echo("正在启动浏览器并连接 CDP...")
    click.echo("请在打开的页面里完成阿里云登录。")
    config = login_auth(
        runtime,
        browser=browser,
        login_url=login_url,
        confirm=lambda: click.prompt(
            "登录完成后回到终端按回车继续",
            default="",
            show_default=False,
        ),
    )
    click.echo(f"已保存认证配置到: {runtime.config_path}")
    if config.csrf_token:
        click.echo("已同时提取 csrf token。")


@cli.command("install-skill")
@as_click_command
def install_skill_command() -> None:
    """安装 Claude skill。

    将 alilog skill 安装到 Claude 的 skills 目录，以便在 Claude 中使用。
    """
    path = install_skill()
    click.echo(f"已安装 Claude skill: {path}")
    click.echo("如果当前机器还没有安装 alilog CLI，可执行:")
    click.echo(f"  uv tool install {INSTALL_REPO_URL}")


def main() -> None:
    """CLI 入口点。"""
    cli(standalone_mode=True)
