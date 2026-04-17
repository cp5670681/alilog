from __future__ import annotations

from functools import wraps
from typing import Any

import click
import httpx

from .inputs import DEFAULT_TIMEZONE
from .models import AliLogError
from .rendering import render_context, render_search
from .usecases import clear_auth, load_runtime, run_context, run_search, save_auth


def fail_as_click(exc: Exception) -> Exception:
    return click.ClickException(str(exc))


def as_click_command(func: Any) -> Any:
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
@click.option("--project", required=True, help="ProjectName")
@click.option("--logstore", required=True, help="LogStoreName")
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
@click.option("--project", required=True, help="ProjectName")
@click.option("--logstore", required=True, help="LogStoreName")
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
    runtime = load_runtime()
    save_auth(runtime, cookie, csrf_token)
    click.echo(f"已保存认证配置到: {runtime.config_path}")


@auth_group.command("clear")
@as_click_command
def auth_clear() -> None:
    runtime = load_runtime()
    clear_auth(runtime)
    click.echo(f"已删除配置文件: {runtime.config_path}")


def main() -> None:
    cli(standalone_mode=True)
