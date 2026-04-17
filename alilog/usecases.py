from __future__ import annotations

from .client import AliyunSLSClient
from .config import (
    clear_auth_config,
    load_auth_config,
    resolve_config_path,
    save_auth_config,
)
from .inputs import ensure_with_pack_meta, parse_pack_meta, resolve_search_window
from .models import AliLogError, AuthConfig, RuntimeOptions, SearchWindow


def load_runtime() -> RuntimeOptions:
    config_path = resolve_config_path()
    stored_auth = load_auth_config(config_path)
    return RuntimeOptions(
        cookie=stored_auth.cookie,
        csrf_token=stored_auth.csrf_token,
        config_path=config_path,
    )


def get_client(runtime: RuntimeOptions) -> AliyunSLSClient:
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
    window = resolve_search_window(
        start=start,
        end=end,
        last=last,
        timezone_name=timezone_name,
    )
    response = get_client(runtime).search_logs(
        project=project,
        logstore=logstore,
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
    project: str,
    logstore: str,
    pack_meta: str,
    pack_id: str,
    size: int,
) -> dict[str, dict]:
    client = get_client(runtime)
    coords = parse_pack_meta(pack_meta)
    return {
        label: client.context_logs(
            project=project,
            logstore=logstore,
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


def clear_auth(runtime: RuntimeOptions) -> None:
    clear_auth_config(runtime.config_path)
