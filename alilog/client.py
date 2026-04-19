"""
阿里云 SLS Console API 客户端模块。

本模块提供与阿里云日志服务 Console 交互的 HTTP 客户端，支持：
- 日志查询（search_logs）：执行日志搜索查询
- 上下文查询（context_logs）：获取指定日志前后的上下文日志

客户端使用 Cookie 进行身份验证，支持自定义请求头和超时设置。
"""

from __future__ import annotations

from typing import Any

import httpx

from .models import AliLogError, ContextCoordinates

BASE_URL = "https://sls.console.aliyun.com"
DEFAULT_TIMEOUT = 30
DEFAULT_USER_AGENT = "alilog/0.1"


class AliyunSLSClient:
    """阿里云 SLS Console API 客户端。

    通过 HTTP 请求与阿里云日志服务 Console API 交互，支持日志查询和上下文查询。

    Attributes:
        base_url: API 基础 URL
        timeout: 请求超时时间（秒）
        client: HTTP 客户端实例
    """

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
        """初始化客户端。

        Args:
            cookie: 认证 Cookie 字符串
            csrf_token: CSRF 令牌（可选）
            base_url: API 基础 URL
            timeout: 请求超时时间（秒）
            extra_headers: 额外的请求头
            client: 自定义 HTTP 客户端（可选）

        Raises:
            AliLogError: Cookie 为空时抛出
        """
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
        """执行日志查询。

        向 SLS Console API 发送日志查询请求，返回匹配的日志列表。

        Args:
            project: 项目名称
            logstore: 日志库名称
            start: 起始时间戳（秒级）
            end: 结束时间戳（秒级）
            query: 查询语句
            page: 页码，从 1 开始
            size: 每页条数
            reverse: 是否按时间倒序排列
            psql: 是否使用 SQL 查询
            full_complete: 是否等待查询完全完成
            schema_free: 是否使用 schema-free 模式
            need_highlight: 是否需要高亮

        Returns:
            API 响应数据，包含 meta（元信息）和 data（日志列表）

        Raises:
            AliLogError: 查询失败时抛出
        """
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
        """执行上下文查询。

        获取指定日志位置前后的上下文日志，用于日志上下文浏览。

        Args:
            project: 项目名称
            logstore: 日志库名称
            coords: 上下文坐标信息（从 pack_meta 解析）
            pack_id: 日志包 ID
            size: 返回的日志条数
            total_offset: 总偏移量
            reserve: 查询方向，True 为向后（next），False 为向前（prev）

        Returns:
            API 响应数据，包含上下文日志列表和分页信息

        Raises:
            AliLogError: 查询失败时抛出
        """
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
        """解码 HTTP 响应为 JSON。

        处理 HTTP 错误和 API 返回的错误信息。

        Args:
            response: HTTP 响应对象
            action: 操作名称，用于错误消息

        Returns:
            解析后的 JSON 数据

        Raises:
            AliLogError: HTTP 错误或 API 返回错误时抛出
        """
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
