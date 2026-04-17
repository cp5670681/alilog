from __future__ import annotations

from typing import Any

import httpx

from .models import AliLogError, ContextCoordinates

BASE_URL = "https://sls.console.aliyun.com"
DEFAULT_TIMEOUT = 30
DEFAULT_USER_AGENT = "alilog/0.1"


class AliyunSLSClient:
    def __init__(
        self,
        *,
        cookie: str,
        csrf_token: str | None = None,
        base_url: str = BASE_URL,
        timeout: int = DEFAULT_TIMEOUT,
        extra_headers: dict[str, str] | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        if not cookie:
            raise AliLogError("缺少 Cookie，请先在配置文件中保存认证信息。")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.client = client or httpx.Client()
        self.client.headers.update(
            {
                "Accept-Language": "zh-CN,zh;q=0.9",
                "Origin": self.base_url,
                "User-Agent": DEFAULT_USER_AGENT,
            }
        )
        self.client.headers["Cookie"] = cookie
        if csrf_token:
            self.client.headers["x-csrf-token"] = csrf_token
        if extra_headers:
            self.client.headers.update(extra_headers)

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
        response = self.client.post(
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
        response = self.client.get(
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
                "Size": str(size),
                "TotalOffset": str(total_offset),
                "Reserve": str(reserve).lower(),
            },
            timeout=self.timeout,
        )
        return self._decode_json(response, "上下文查询")

    @staticmethod
    def _decode_json(response: httpx.Response, action: str) -> dict[str, Any]:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = response.text.strip()
            if detail:
                raise AliLogError(
                    f"{action}失败: HTTP {response.status_code} - {detail}"
                ) from exc
            raise AliLogError(f"{action}失败: HTTP {response.status_code}") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise AliLogError(f"{action}失败: 返回不是合法 JSON。") from exc

        if isinstance(payload, dict) and payload.get("success") is False:
            message = payload.get("message") or payload.get("code") or "unknown error"
            raise AliLogError(f"{action}失败: {message}")
        return payload