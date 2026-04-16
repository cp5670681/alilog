from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import click
import requests

BASE_URL = "https://sls.console.aliyun.com"
DEFAULT_TIMEOUT = 30
DEFAULT_USER_AGENT = "alilog/0.1"
DEFAULT_CONFIG_PATH = Path.home() / ".alilog.json"
DEFAULT_TIMEZONE = "Asia/Shanghai"


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
class SearchWindow:
    start: int
    end: int
    timezone_name: str


@dataclass(frozen=True)
class RuntimeOptions:
    cookie: str | None
    csrf_token: str | None
    config_path: Path
    base_url: str
    timeout: int
    headers: dict[str, str]


def parse_pack_meta(pack_meta: str) -> ContextCoordinates:
    parts = pack_meta.split("|")
    if len(parts) != 4 or not all(parts):
        raise AliLogError(
            "pack_meta 格式无效，预期为 'ShardId|Cursor|PackNum|Offset'。"
        )
    return ContextCoordinates(
        shard_id=parts[0],
        cursor=parts[1],
        pack_num=parts[2],
        offset=parts[3],
    )


def build_extra_headers(values: tuple[str, ...]) -> dict[str, str]:
    headers: dict[str, str] = {}
    for value in values:
        name, separator, header_value = value.partition(":")
        if not separator:
            raise AliLogError(f"自定义请求头格式无效: {value!r}")
        headers[name.strip()] = header_value.strip()
    return headers


def format_timestamp(value: Any) -> str:
    if value is None:
        return "-"
    try:
        return datetime.fromtimestamp(int(value)).astimezone().isoformat(timespec="seconds")
    except (TypeError, ValueError, OSError):
        return str(value)


def compact_text(value: str) -> str:
    return " ".join(value.split())


def get_timezone(timezone_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise AliLogError(f"未知时区: {timezone_name}") from exc


def parse_duration(value: str) -> int:
    match = re.fullmatch(r"(?i)\s*(\d+)\s*([smhdw])\s*", value)
    if not match:
        raise AliLogError(
            "相对时间格式无效，支持的格式例如: 30s, 15m, 2h, 7d, 1w"
        )
    amount = int(match.group(1))
    unit = match.group(2).lower()
    multiplier = {
        "s": 1,
        "m": 60,
        "h": 3600,
        "d": 86400,
        "w": 604800,
    }[unit]
    return amount * multiplier


def parse_time_value(raw_value: str, timezone_name: str) -> int:
    value = raw_value.strip()
    tz = get_timezone(timezone_name)
    if re.fullmatch(r"\d{10,13}", value):
        timestamp = int(value)
        if len(value) == 13:
            timestamp //= 1000
        return timestamp

    if value.lower() == "now":
        return int(datetime.now(tz).timestamp())

    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        parsed = None

    if parsed is None:
        for pattern in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d",
        ):
            try:
                parsed = datetime.strptime(value, pattern)
                break
            except ValueError:
                continue

    if parsed is None:
        raise AliLogError(
            "时间格式无效，支持时间戳、ISO 时间、'YYYY-MM-DD HH:MM[:SS]'、'YYYY-MM-DD' 和 'now'。"
        )

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=tz)
    return int(parsed.timestamp())


def resolve_search_window(
    *,
    start: str | None,
    end: str | None,
    last: str | None,
    timezone_name: str,
) -> SearchWindow:
    if last:
        if start is not None:
            raise AliLogError("--last 和 --from 不能同时使用。")
        duration_seconds = parse_duration(last)
        end_value = (
            parse_time_value(end, timezone_name)
            if end is not None
            else int(datetime.now(get_timezone(timezone_name)).timestamp())
        )
        start_value = end_value - duration_seconds
    else:
        if start is None or end is None:
            raise AliLogError("search 命令需要提供 --from/--to，或提供 --last。")
        start_value = parse_time_value(start, timezone_name)
        end_value = parse_time_value(end, timezone_name)

    if start_value >= end_value:
        raise AliLogError("时间范围无效: 起始时间必须早于结束时间。")
    return SearchWindow(
        start=start_value,
        end=end_value,
        timezone_name=timezone_name,
    )


def resolve_config_path(raw_path: str | None) -> Path:
    return Path(raw_path or DEFAULT_CONFIG_PATH).expanduser()


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


def resolve_auth(cli_cookie: str | None, cli_csrf_token: str | None, stored_auth: AuthConfig) -> AuthConfig:
    cookie = cli_cookie or os.getenv("ALILOG_COOKIE") or stored_auth.cookie
    csrf_token = (
        cli_csrf_token or os.getenv("ALILOG_CSRF_TOKEN") or stored_auth.csrf_token
    )
    return AuthConfig(cookie=cookie, csrf_token=csrf_token)


class AliyunSLSClient:
    def __init__(
        self,
        *,
        cookie: str,
        csrf_token: str | None = None,
        base_url: str = BASE_URL,
        timeout: int = DEFAULT_TIMEOUT,
        extra_headers: dict[str, str] | None = None,
        session: requests.Session | None = None,
    ) -> None:
        if not cookie:
            raise AliLogError(
                "缺少 Cookie，请通过 --cookie、ALILOG_COOKIE 或 ~/.alilog.json 提供。"
            )
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "Accept-Language": "zh-CN,zh;q=0.9",
                "Origin": self.base_url,
                "User-Agent": DEFAULT_USER_AGENT,
            }
        )
        self.session.headers["Cookie"] = cookie
        if csrf_token:
            self.session.headers["x-csrf-token"] = csrf_token
        if extra_headers:
            self.session.headers.update(extra_headers)

    def search_logs(
        self,
        *,
        project: str,
        logstore: str,
        start: int,
        end: int,
        query: str,
        page: int = 1,
        size: int = 20,
        reverse: bool = True,
        psql: bool = False,
        full_complete: bool = False,
        schema_free: bool = False,
        need_highlight: bool = True,
    ) -> dict[str, Any]:
        response = self.session.post(
            f"{self.base_url}/console/logs/getLogs.json",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": (
                    f"{self.base_url}/lognext/project/{project}/logsearch/{logstore}"
                ),
            },
            data={
                "ProjectName": project,
                "LogStoreName": logstore,
                "from": start,
                "query": query,
                "to": end,
                "Page": page,
                "Size": size,
                "Reverse": str(reverse).lower(),
                "pSql": str(psql).lower(),
                "fullComplete": str(full_complete).lower(),
                "schemaFree": str(schema_free).lower(),
                "needHighlight": str(need_highlight).lower(),
            },
            timeout=self.timeout,
        )
        return self._decode_json(response, "日志查询")

    def context_logs(
        self,
        *,
        project: str,
        logstore: str,
        coords: ContextCoordinates,
        pack_id: str,
        size: int = 30,
        total_offset: int = 0,
        reserve: bool,
    ) -> dict[str, Any]:
        response = self.session.get(
            f"{self.base_url}/console/logstore/contextQueryLogs.json",
            headers={
                "Accept": "*/*",
                "Referer": (
                    f"{self.base_url}/lognext/project/{project}/logsearch/{logstore}"
                ),
            },
            params={
                "LogStoreName": logstore,
                "ProjectName": project,
                "ShardId": coords.shard_id,
                "Cursor": coords.cursor,
                "PackNum": coords.pack_num,
                "Offset": coords.offset,
                "PackId": pack_id,
                "Size": size,
                "TotalOffset": total_offset,
                "Reserve": str(reserve).lower(),
            },
            timeout=self.timeout,
        )
        return self._decode_json(response, "上下文查询")

    @staticmethod
    def _decode_json(response: requests.Response, action: str) -> dict[str, Any]:
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            detail = response.text.strip()
            if detail:
                raise AliLogError(f"{action}失败: HTTP {response.status_code} - {detail}") from exc
            raise AliLogError(f"{action}失败: HTTP {response.status_code}") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise AliLogError(f"{action}失败: 返回不是合法 JSON。") from exc

        if isinstance(payload, dict) and payload.get("success") is False:
            message = payload.get("message") or payload.get("code") or "unknown error"
            raise AliLogError(f"{action}失败: {message}")
        return payload


def render_search(response: dict[str, Any], window: SearchWindow | None = None) -> str:
    meta = response.get("meta", {})
    logs = response.get("data", [])
    lines = [
        f"count={meta.get('count', len(logs))} progress={meta.get('progress', '-')}"
        f" elapsed={meta.get('elapsedMillisecond', '-')}ms accurate={meta.get('isAccurate', '-')}"
    ]
    if window is not None:
        lines.append(
            f"range={format_timestamp(window.start)} -> {format_timestamp(window.end)} "
            f"timezone={window.timezone_name} from={window.start} to={window.end}"
        )
    for index, log in enumerate(logs, start=1):
        lines.append(
            f"[{index}] time={format_timestamp(log.get('__time__'))} "
            f"pack_id={log.get('__tag__:__pack_id__', '-')}"
        )
        if "__pack_meta__" in log:
            lines.append(f"    pack_meta={log['__pack_meta__']}")
        source = log.get("__source__") or log.get("__tag__:_pod_name_") or "-"
        lines.append(f"    source={source}")
        lines.append(f"    {compact_text(str(log.get('content', '')))}")
    return "\n".join(lines)


def render_context(response: dict[str, Any], label: str) -> str:
    data = response.get("data", {})
    logs = data.get("logs", [])
    lines = [
        f"[{label}] total={data.get('total', len(logs))} "
        f"pack_id={data.get('packId', '-')}"
    ]
    if data.get("prePackId"):
        lines.append(f"pre_pack_id={data.get('prePackId')}")
    if data.get("packMeta"):
        lines.append(f"pack_meta={data.get('packMeta')}")
    if data.get("prePackMeta"):
        lines.append(f"pre_pack_meta={data.get('prePackMeta')}")
    for log in logs:
        lines.append(
            f"{log.get('__index_number__', '?'):>4} "
            f"{format_timestamp(log.get('__time__'))} "
            f"{compact_text(str(log.get('content', '')))}"
        )
    return "\n".join(lines)


def resolve_context_coordinates(
    pack_meta: str | None,
    shard_id: str | None,
    cursor: str | None,
    pack_num: str | None,
    offset: str | None,
) -> ContextCoordinates:
    if pack_meta:
        return parse_pack_meta(pack_meta)

    values = [shard_id, cursor, pack_num, offset]
    if all(values):
        return ContextCoordinates(
            shard_id=shard_id or "",
            cursor=cursor or "",
            pack_num=pack_num or "",
            offset=offset or "",
        )
    raise AliLogError(
        "context 命令需要提供 --pack-meta，或同时提供 --shard-id/--cursor/--pack-num/--offset。"
    )


def get_runtime(ctx: click.Context) -> RuntimeOptions:
    runtime = ctx.obj
    if not isinstance(runtime, RuntimeOptions):
        raise AliLogError("运行时配置未初始化。")
    return runtime


def get_client(runtime: RuntimeOptions) -> AliyunSLSClient:
    return AliyunSLSClient(
        cookie=runtime.cookie or "",
        csrf_token=runtime.csrf_token,
        base_url=runtime.base_url,
        timeout=runtime.timeout,
        extra_headers=runtime.headers,
    )


def fail_as_click(exc: Exception) -> Exception:
    return click.ClickException(str(exc))


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.option("--cookie", help="浏览器登录后的 Cookie。优先级高于环境变量和 ~/.alilog.json。")
@click.option("--csrf-token", help="x-csrf-token。优先级高于环境变量和 ~/.alilog.json。")
@click.option(
    "--config",
    default=lambda: os.getenv("ALILOG_CONFIG"),
    show_default="~/.alilog.json",
    help="配置文件路径，默认 ~/.alilog.json。也可通过 ALILOG_CONFIG 指定。",
)
@click.option(
    "--header",
    multiple=True,
    help="附加请求头，格式为 'Name: Value'。可重复传入。",
)
@click.option("--timeout", default=DEFAULT_TIMEOUT, show_default=True, type=int, help="请求超时秒数。")
@click.option("--base-url", default=BASE_URL, show_default=True, help="接口根地址。")
@click.pass_context
def cli(
    ctx: click.Context,
    cookie: str | None,
    csrf_token: str | None,
    config: str | None,
    header: tuple[str, ...],
    timeout: int,
    base_url: str,
) -> None:
    """阿里云 SLS Console 日志查询 CLI。"""
    try:
        config_path = resolve_config_path(config)
        stored_auth = load_auth_config(config_path)
        resolved_auth = resolve_auth(cookie, csrf_token, stored_auth)
        ctx.obj = RuntimeOptions(
            cookie=resolved_auth.cookie,
            csrf_token=resolved_auth.csrf_token,
            config_path=config_path,
            base_url=base_url,
            timeout=timeout,
            headers=build_extra_headers(header),
        )
    except (AliLogError, requests.RequestException) as exc:
        raise fail_as_click(exc) from exc


@cli.command("search")
@click.option("--project", required=True, help="ProjectName")
@click.option("--logstore", required=True, help="LogStoreName")
@click.option("--from", "start", help="起始时间，支持时间戳、ISO 时间、'YYYY-MM-DD HH:MM[:SS]'。")
@click.option("--to", "end", help="结束时间，支持时间戳、ISO 时间、'YYYY-MM-DD HH:MM[:SS]'，也支持 now。")
@click.option("--last", help="相对时间窗口，例如 15m、2h、1d。与 --from 互斥。")
@click.option("--timezone", default=DEFAULT_TIMEZONE, show_default=True, help="解析无时区时间字符串时使用的时区。")
@click.option("--query", required=True, help="查询语句")
@click.option("--page", default=1, show_default=True, type=int, help="页码")
@click.option("--size", default=20, show_default=True, type=int, help="每页条数")
@click.option("--reverse/--no-reverse", default=True, show_default=True, help="是否倒序。")
@click.option("--json", "json_output", is_flag=True, help="输出原始 JSON。")
@click.pass_context
def search_command(
    ctx: click.Context,
    project: str,
    logstore: str,
    start: str | None,
    end: str | None,
    last: str | None,
    timezone: str,
    query: str,
    page: int,
    size: int,
    reverse: bool,
    json_output: bool,
) -> None:
    try:
        runtime = get_runtime(ctx)
        window = resolve_search_window(
            start=start,
            end=end,
            last=last,
            timezone_name=timezone,
        )
        response = get_client(runtime).search_logs(
            project=project,
            logstore=logstore,
            start=window.start,
            end=window.end,
            query=query,
            page=page,
            size=size,
            reverse=reverse,
        )
        if json_output:
            click.echo(
                json.dumps(
                    {
                        "window": {
                            "from": window.start,
                            "to": window.end,
                            "from_iso": format_timestamp(window.start),
                            "to_iso": format_timestamp(window.end),
                            "timezone": window.timezone_name,
                        },
                        "response": response,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return
        click.echo(render_search(response, window))
    except (AliLogError, requests.RequestException) as exc:
        raise fail_as_click(exc) from exc


@cli.command("context")
@click.option("--project", required=True, help="ProjectName")
@click.option("--logstore", required=True, help="LogStoreName")
@click.option("--pack-meta", help="从 search 结果中的 __pack_meta__ 直接传入。")
@click.option("--shard-id", help="ShardId")
@click.option("--cursor", help="Cursor")
@click.option("--pack-num", help="PackNum")
@click.option("--offset", help="Offset")
@click.option("--pack-id", required=True, help="PackId")
@click.option("--size", default=30, show_default=True, type=int, help="Size")
@click.option("--total-offset", default=0, show_default=True, type=int, help="TotalOffset")
@click.option(
    "--direction",
    type=click.Choice(["prev", "next", "both"], case_sensitive=False),
    default="both",
    show_default=True,
    help="查询前文、后文或两侧。",
)
@click.option("--json", "json_output", is_flag=True, help="输出原始 JSON。")
@click.pass_context
def context_command(
    ctx: click.Context,
    project: str,
    logstore: str,
    pack_meta: str | None,
    shard_id: str | None,
    cursor: str | None,
    pack_num: str | None,
    offset: str | None,
    pack_id: str,
    size: int,
    total_offset: int,
    direction: str,
    json_output: bool,
) -> None:
    try:
        runtime = get_runtime(ctx)
        client = get_client(runtime)
        coords = resolve_context_coordinates(
            pack_meta=pack_meta,
            shard_id=shard_id,
            cursor=cursor,
            pack_num=pack_num,
            offset=offset,
        )

        if direction == "prev":
            response = client.context_logs(
                project=project,
                logstore=logstore,
                coords=coords,
                pack_id=pack_id,
                size=size,
                total_offset=total_offset,
                reserve=False,
            )
            click.echo(json.dumps(response, ensure_ascii=False, indent=2) if json_output else render_context(response, "prev"))
            return

        if direction == "next":
            response = client.context_logs(
                project=project,
                logstore=logstore,
                coords=coords,
                pack_id=pack_id,
                size=size,
                total_offset=total_offset,
                reserve=True,
            )
            click.echo(json.dumps(response, ensure_ascii=False, indent=2) if json_output else render_context(response, "next"))
            return

        prev_response = client.context_logs(
            project=project,
            logstore=logstore,
            coords=coords,
            pack_id=pack_id,
            size=size,
            total_offset=total_offset,
            reserve=False,
        )
        next_response = client.context_logs(
            project=project,
            logstore=logstore,
            coords=coords,
            pack_id=pack_id,
            size=size,
            total_offset=total_offset,
            reserve=True,
        )
        if json_output:
            click.echo(
                json.dumps(
                    {"prev": prev_response, "next": next_response},
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return
        click.echo(render_context(prev_response, "prev"))
        click.echo()
        click.echo(render_context(next_response, "next"))
    except (AliLogError, requests.RequestException) as exc:
        raise fail_as_click(exc) from exc


@cli.group("auth")
def auth_group() -> None:
    """保存或清除本地认证配置。"""


@auth_group.command("save")
@click.option("--cookie", help="要保存的 Cookie。")
@click.option("--csrf-token", help="要保存的 csrf token。")
@click.pass_context
def auth_save(
    ctx: click.Context,
    cookie: str | None,
    csrf_token: str | None,
) -> None:
    try:
        runtime = get_runtime(ctx)
        final_cookie = cookie or runtime.cookie
        final_csrf_token = csrf_token or runtime.csrf_token
        if not final_cookie and not final_csrf_token:
            raise AliLogError(
                "没有可保存的认证信息，请通过 --cookie/--csrf-token 或环境变量提供。"
            )
        save_auth_config(
            runtime.config_path,
            AuthConfig(cookie=final_cookie, csrf_token=final_csrf_token),
        )
        click.echo(f"已保存认证配置到: {runtime.config_path}")
    except AliLogError as exc:
        raise fail_as_click(exc) from exc


@auth_group.command("show")
@click.pass_context
def auth_show(ctx: click.Context) -> None:
    try:
        runtime = get_runtime(ctx)
        click.echo(
            json.dumps(
                {
                    "path": str(runtime.config_path),
                    "exists": runtime.config_path.exists(),
                    "has_cookie": bool(runtime.cookie),
                    "has_csrf_token": bool(runtime.csrf_token),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    except AliLogError as exc:
        raise fail_as_click(exc) from exc


@auth_group.command("clear")
@click.pass_context
def auth_clear(ctx: click.Context) -> None:
    try:
        runtime = get_runtime(ctx)
        clear_auth_config(runtime.config_path)
        click.echo(f"已删除配置文件: {runtime.config_path}")
    except AliLogError as exc:
        raise fail_as_click(exc) from exc


def main() -> None:
    cli(standalone_mode=True)
