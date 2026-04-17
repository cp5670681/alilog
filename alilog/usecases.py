from __future__ import annotations

from .client import AliyunSLSClient
from .config import (
    clear_auth_config,
    find_project_config_path,
    load_auth_config,
    load_project_config,
    resolve_config_path,
    save_auth_config,
)
from .inputs import ensure_with_pack_meta, parse_pack_meta, resolve_search_window
from .models import AliLogError, AuthConfig, RuntimeOptions, SearchWindow
from .skills import install_ai_skill


def load_runtime() -> RuntimeOptions:
    config_path = resolve_config_path()
    stored_auth = load_auth_config(config_path)
    project_config_path = find_project_config_path()
    return RuntimeOptions(
        cookie=stored_auth.cookie,
        csrf_token=stored_auth.csrf_token,
        config_path=config_path,
        project_config_path=project_config_path,
    )


def get_client(runtime: RuntimeOptions) -> AliyunSLSClient:
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


def install_skill() -> str:
    return str(install_ai_skill())


def resolve_project_name(runtime: RuntimeOptions, project: str | None) -> str:
    if project:
        return project
    project_config = load_project_config(runtime.project_config_path)
    if project_config.project:
        return project_config.project
    raise AliLogError(
        "缺少 ProjectName，请通过 --project 提供，"
        "或在项目根目录的 .alilog.json 中配置 project。"
    )


def resolve_logstore_name(runtime: RuntimeOptions, logstore: str | None) -> str:
    if logstore:
        return logstore
    project_config = load_project_config(runtime.project_config_path)
    if project_config.default_logstore:
        return project_config.default_logstore
    raise AliLogError(
        "缺少 LogStoreName，请通过 --logstore 提供，"
        "或在项目根目录的 .alilog.json 中配置 default_logstore。"
    )
