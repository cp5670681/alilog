"""
浏览器认证模块。

本模块通过 Chrome DevTools Protocol (CDP) 实现浏览器自动化认证，
用于从浏览器中捕获阿里云 SLS Console 的认证信息（Cookie 和 CSRF Token）。

主要功能：
- 启动带有远程调试端口的 Chromium 浏览器
- 通过 CDP WebSocket 连接浏览器
- 从浏览器页面中提取 Cookie 和 CSRF Token
- 支持自动探测系统中的 Chrome/Chromium/Edge 浏览器
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import socket
import subprocess
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Any
from urllib.parse import urlparse

import httpx
from websocket import (
    WebSocket,
    WebSocketConnectionClosedException,
    WebSocketException,
    WebSocketTimeoutException,
    create_connection,
)

from .client import BASE_URL
from .models import AliLogError, AuthConfig

logger = logging.getLogger(__name__)

DEFAULT_CDP_HOST = "127.0.0.1"
DEFAULT_CDP_STARTUP_TIMEOUT = 15
DEFAULT_PAGE_TARGET_TIMEOUT = 15
DEFAULT_LOGIN_URL = f"{BASE_URL}/lognext/"
DEFAULT_BROWSER_CANDIDATES = (
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
    "microsoft-edge",
    "msedge",
)
DEFAULT_BROWSER_PATH_CANDIDATES = (
    Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
    Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
    Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
    Path("/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"),
    Path("/Applications/Arc.app/Contents/MacOS/Arc"),
)
SEC_TOKEN_PATTERN = re.compile(
    r"ALIYUN_SLS_CONSOLE_CONFIG\s*=\s*\{.*?\bSEC_TOKEN\s*:\s*['\"]([^'\"]+)['\"]",
    re.DOTALL,
)


@dataclass(frozen=True)
class CookieEntry:
    """Cookie 条目。

    表示从浏览器中提取的单个 Cookie 信息。

    Attributes:
        name: Cookie 名称
        value: Cookie 值
        domain: Cookie 所属域名
        path: Cookie 路径
    """

    name: str
    value: str
    domain: str
    path: str = "/"


class CDPWebSocket:
    """CDP WebSocket 连接封装。

    封装 Chrome DevTools Protocol 的 WebSocket 连接，提供命令发送和响应接收功能。

    Attributes:
        url: WebSocket 连接 URL
        timeout: 连接和操作超时时间（秒）
    """

    def __init__(self, url: str, *, timeout: float = 30.0) -> None:
        """初始化 WebSocket 连接。

        Args:
            url: WebSocket 连接 URL，从 CDP 的 webSocketDebuggerUrl 获取
            timeout: 连接和操作超时时间（秒）
        """
        self.url = url
        self.timeout = timeout
        self._socket: WebSocket | None = None
        self._message_id = 0

    def __enter__(self) -> CDPWebSocket:
        self.connect()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def connect(self) -> None:
        """建立 WebSocket 连接。

        Raises:
            AliLogError: 连接失败时抛出
        """
        parsed = urlparse(self.url)
        if parsed.scheme != "ws":
            raise AliLogError(f"暂不支持非 ws:// 的 CDP 地址: {self.url}")
        if not parsed.hostname or parsed.port is None:
            raise AliLogError(f"CDP 地址无效: {self.url}")
        logger.debug("正在连接 CDP WebSocket: %s", self.url)
        try:
            self._socket = create_connection(
                self.url,
                timeout=self.timeout,
                http_no_proxy=[parsed.hostname],
                suppress_origin=True,
            )
        except (OSError, WebSocketException) as exc:
            raise AliLogError(
                f"连接 CDP WebSocket 失败: {self.url} ({exc})"
            ) from exc
        logger.debug("CDP WebSocket 连接成功")

    def close(self) -> None:
        """关闭 WebSocket 连接。"""
        if self._socket is None:
            return
        try:
            self._socket.close()
        except WebSocketException:
            pass
        finally:
            self._socket = None

    def command(
        self,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """发送 CDP 命令并等待响应。

        Args:
            method: CDP 方法名，如 'Network.getAllCookies'
            params: 命令参数

        Returns:
            CDP 响应的 result 字段

        Raises:
            AliLogError: 命令执行失败时抛出
        """
        self._message_id += 1
        expected_id = self._message_id
        self.send_json({"id": expected_id, "method": method, "params": params or {}})
        while True:
            message = self.recv_json()
            if message.get("id") != expected_id:
                continue
            error = message.get("error")
            if isinstance(error, dict):
                details = error.get("message") or "unknown error"
                raise AliLogError(f"CDP 调用失败 {method}: {details}")
            result = message.get("result")
            if not isinstance(result, dict):
                return {}
            return result

    def send_json(self, payload: dict[str, Any]) -> None:
        """发送 JSON 消息。

        Args:
            payload: 要发送的 JSON 对象

        Raises:
            AliLogError: 发送失败时抛出
        """
        if self._socket is None:
            raise AliLogError("CDP WebSocket 尚未连接。")
        try:
            self._socket.send(json.dumps(payload, ensure_ascii=False))
        except (OSError, WebSocketException) as exc:
            raise AliLogError("发送 CDP 消息失败。") from exc

    def recv_json(self) -> dict[str, Any]:
        """接收并解析 JSON 消息。

        Returns:
            解析后的 JSON 对象

        Raises:
            AliLogError: 接收或解析失败时抛出
        """
        payload = self._recv_message()
        try:
            text = payload.decode("utf-8") if isinstance(payload, bytes) else payload
            data = json.loads(text)
        except ValueError as exc:
            raise AliLogError("CDP 返回了非法 JSON 消息。") from exc
        if isinstance(data, dict):
            return data
        raise AliLogError("CDP 返回了非法 JSON 消息。")

    def _recv_message(self) -> str | bytes:
        """接收原始 WebSocket 消息。

        Returns:
            接收到的消息内容

        Raises:
            AliLogError: 接收失败时抛出
        """
        if self._socket is None:
            raise AliLogError("CDP WebSocket 尚未连接。")
        while True:
            try:
                payload = self._socket.recv()
            except WebSocketTimeoutException as exc:
                raise AliLogError("等待 CDP 消息超时。") from exc
            except WebSocketConnectionClosedException as exc:
                raise AliLogError("CDP 连接已关闭。") from exc
            except (OSError, WebSocketException) as exc:
                raise AliLogError("读取 CDP 消息失败。") from exc
            if isinstance(payload, (str, bytes)):
                return payload


class ManagedBrowser:
    """托管浏览器实例。

    启动并管理一个带有远程调试端口的 Chromium 浏览器实例，
    支持上下文管理器协议自动清理资源。

    Attributes:
        browser: 浏览器可执行文件路径
        login_url: 登录页面 URL
        cdp_host: CDP 监听主机
        cdp_port: CDP 监听端口
        startup_timeout: 浏览器启动超时时间（秒）
    """

    def __init__(
        self,
        *,
        browser: str | None,
        login_url: str,
        cdp_host: str = DEFAULT_CDP_HOST,
        cdp_port: int | None = None,
        startup_timeout: int = DEFAULT_CDP_STARTUP_TIMEOUT,
    ) -> None:
        """初始化托管浏览器。

        Args:
            browser: 浏览器可执行文件路径，为 None 时自动探测
            login_url: 登录页面 URL
            cdp_host: CDP 监听主机
            cdp_port: CDP 监听端口，为 None 时自动选择空闲端口
            startup_timeout: 浏览器启动超时时间（秒）
        """
        self.browser = browser
        self.login_url = login_url
        self.cdp_host = cdp_host
        self.cdp_port = cdp_port or pick_free_tcp_port()
        self.startup_timeout = startup_timeout
        self._profile_dir: tempfile.TemporaryDirectory[str] | None = None
        self._process: subprocess.Popen[bytes] | None = None

    def __enter__(self) -> ManagedBrowser:
        self.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    @property
    def debugger_url(self) -> str:
        """CDP 调试器 HTTP URL。"""
        return f"http://{self.cdp_host}:{self.cdp_port}"

    @property
    def debugger_origin(self) -> str:
        """CDP 调试器 Origin。"""
        return f"http://{self.cdp_host}:{self.cdp_port}"

    def start(self) -> None:
        """启动浏览器实例。

        Raises:
            AliLogError: 启动失败或超时时抛出
        """
        executable = resolve_browser_executable(self.browser)
        logger.info("正在启动浏览器: %s", executable)
        self._profile_dir = tempfile.TemporaryDirectory(prefix="alilog-cdp-profile-")
        command = [
            executable,
            f"--remote-debugging-port={self.cdp_port}",
            f"--remote-allow-origins={self.debugger_origin}",
            f"--user-data-dir={self._profile_dir.name}",
            "--new-window",
            "--no-first-run",
            "--no-default-browser-check",
            self.login_url,
        ]
        try:
            self._process = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as exc:
            self._cleanup_profile_dir()
            raise AliLogError(f"启动浏览器失败: {executable}") from exc
        logger.debug("浏览器进程已启动，等待 CDP 端口就绪...")
        wait_for_debugger(
            self.debugger_url,
            timeout=self.startup_timeout,
        )
        logger.info("浏览器已成功启动，CDP 端口: %d", self.cdp_port)

    def close(self) -> None:
        """关闭浏览器实例并清理资源。"""
        if self._process is not None and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
        self._process = None
        self._cleanup_profile_dir()

    def capture_auth(self) -> AuthConfig:
        """从浏览器页面捕获认证信息。

        Returns:
            包含 Cookie 和 CSRF Token 的认证配置

        Raises:
            AliLogError: 捕获失败时抛出
        """
        return capture_auth_from_page_target(
            self.debugger_url,
            self.login_url,
        )

    def _cleanup_profile_dir(self) -> None:
        """清理浏览器用户数据目录。"""
        if self._profile_dir is not None:
            self._profile_dir.cleanup()
            self._profile_dir = None


def capture_auth_via_cdp(
    *,
    browser: str | None = None,
    login_url: str = DEFAULT_LOGIN_URL,
    confirm: Callable[[], object] | None = None,
) -> AuthConfig:
    """通过 CDP 捕获认证信息。

    启动浏览器，等待用户完成登录，然后从浏览器中提取认证信息。

    Args:
        browser: 浏览器可执行文件路径，为 None 时自动探测
        login_url: 登录页面 URL
        confirm: 确认回调函数，用于等待用户完成登录

    Returns:
        包含 Cookie 和 CSRF Token 的认证配置
    """
    wait_for_login = confirm or (lambda: input("完成登录后按回车继续..."))
    with ManagedBrowser(
        browser=browser,
        login_url=login_url,
    ) as managed_browser:
        wait_for_login()
        return managed_browser.capture_auth()


def resolve_browser_executable(browser: str | None) -> str:
    """解析浏览器可执行文件路径。

    按以下顺序查找浏览器：
    1. 用户指定的路径
    2. 系统 PATH 中的 Chrome/Chromium/Edge
    3. macOS 应用程序目录中的浏览器

    Args:
        browser: 用户指定的浏览器路径或名称

    Returns:
        浏览器可执行文件的绝对路径

    Raises:
        AliLogError: 找不到浏览器时抛出
    """
    if browser:
        candidate = Path(browser).expanduser()
        if candidate.exists():
            return str(candidate)
        if resolved := shutil.which(browser):
            return resolved
        raise AliLogError(f"找不到浏览器可执行文件: {browser}")
    for name in DEFAULT_BROWSER_CANDIDATES:
        if resolved := shutil.which(name):
            return resolved
    for path in DEFAULT_BROWSER_PATH_CANDIDATES:
        if path.exists():
            return str(path)
    raise AliLogError(
        "未找到支持 CDP 的 Chromium 浏览器。"
        "请通过 --browser 指定 Chrome/Chromium/Edge 的可执行文件路径。"
    )


def wait_for_debugger(
    debugger_url: str,
    *,
    timeout: int,
) -> None:
    """等待浏览器 CDP 端口就绪。

    轮询 CDP 的 /json/version 端点，直到浏览器准备好接受连接。

    Args:
        debugger_url: CDP 调试器 HTTP URL
        timeout: 超时时间（秒）

    Raises:
        AliLogError: 超时时抛出
    """
    deadline = time.monotonic() + timeout
    version_url = f"{debugger_url}/json/version"
    while time.monotonic() < deadline:
        try:
            response = httpx.get(version_url, timeout=1.0)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            time.sleep(0.2)
            continue
        if isinstance(payload, dict) and payload.get("webSocketDebuggerUrl"):
            return
        time.sleep(0.2)
    raise AliLogError(f"等待浏览器 CDP 端口超时: {version_url}")


def wait_for_page_target(
    debugger_url: str,
    target_url: str,
    *,
    timeout: int = DEFAULT_PAGE_TARGET_TIMEOUT,
) -> dict[str, Any]:
    """等待并获取页面目标。

    轮询 CDP 的 /json/list 端点，查找匹配目标 URL 的页面。

    Args:
        debugger_url: CDP 调试器 HTTP URL
        target_url: 目标页面 URL
        timeout: 超时时间（秒）

    Returns:
        页面目标信息，包含 webSocketDebuggerUrl

    Raises:
        AliLogError: 超时时抛出
    """
    target_host = urlparse(target_url).hostname
    deadline = time.monotonic() + timeout
    list_url = f"{debugger_url}/json/list"
    while time.monotonic() < deadline:
        try:
            response = httpx.get(list_url, timeout=1.0)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            time.sleep(0.2)
            continue
        if not isinstance(payload, list):
            time.sleep(0.2)
            continue
        pages = [item for item in payload if isinstance(item, dict)]
        preferred = next(
            (
                item
                for item in pages
                if item.get("type") == "page"
                and isinstance(item.get("url"), str)
                and target_host
                and target_host in item["url"]
                and item.get("webSocketDebuggerUrl")
            ),
            None,
        )
        if preferred:
            return preferred
        fallback = next(
            (
                item
                for item in pages
                if item.get("type") == "page" and item.get("webSocketDebuggerUrl")
            ),
            None,
        )
        if fallback:
            return fallback
        time.sleep(0.2)
    raise AliLogError("未找到可连接的浏览器页面。")


def capture_auth_from_page_target(
    debugger_url: str,
    target_url: str,
) -> AuthConfig:
    """从页面目标捕获认证信息。

    连接到浏览器页面，提取 Cookie 和 CSRF Token。

    Args:
        debugger_url: CDP 调试器 HTTP URL
        target_url: 目标页面 URL

    Returns:
        包含 Cookie 和 CSRF Token 的认证配置

    Raises:
        AliLogError: 捕获失败时抛出
    """
    last_error: AliLogError | None = None
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        target = wait_for_page_target(debugger_url, target_url)
        websocket_url = target.get("webSocketDebuggerUrl")
        if not isinstance(websocket_url, str) or not websocket_url:
            time.sleep(0.2)
            continue
        try:
            with CDPWebSocket(websocket_url) as websocket:
                websocket.command("Page.bringToFront")
                websocket.command("Network.enable")
                logger.debug("正在从浏览器提取 Cookie...")
                cookies_payload = websocket.command("Network.getAllCookies")
                cookies = parse_cookie_entries(cookies_payload.get("cookies"))
                cookie_header = build_cookie_header(
                    cookies,
                    urlparse(BASE_URL).hostname or "",
                )
                if not cookie_header:
                    raise AliLogError(
                        "没有从浏览器里读到可用于 SLS Console 的 Cookie，"
                        "请确认已经完成登录。"
                    )
                logger.info("成功提取 Cookie (%d 字节)", len(cookie_header))
                page_html = read_current_page_html(websocket)
                csrf_token = extract_csrf_token(page_html)
                if csrf_token:
                    logger.info("成功提取 CSRF Token (%d 字节)", len(csrf_token))
                else:
                    logger.warning("未能提取 CSRF Token，可能页面结构已变化")
                return AuthConfig(cookie=cookie_header, csrf_token=csrf_token)
        except AliLogError as exc:
            last_error = exc
            if "连接 CDP WebSocket 失败" not in str(exc):
                raise
            time.sleep(0.2)
    if last_error is not None:
        raise last_error
    raise AliLogError("未找到可连接的浏览器页面。")


def parse_cookie_entries(payload: Any) -> list[CookieEntry]:
    """解析 Cookie 列表。

    将 CDP 返回的 Cookie 数组转换为 CookieEntry 列表。

    Args:
        payload: CDP 返回的 cookies 数组

    Returns:
        CookieEntry 列表
    """
    if not isinstance(payload, list):
        return []
    cookies = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        value = item.get("value")
        domain = item.get("domain")
        path = item.get("path", "/")
        if (
            isinstance(name, str)
            and isinstance(value, str)
            and isinstance(domain, str)
            and isinstance(path, str)
        ):
            cookies.append(
                CookieEntry(name=name, value=value, domain=domain, path=path)
            )
    return cookies


def build_cookie_header(cookies: list[CookieEntry], target_host: str) -> str:
    """构建 Cookie 请求头。

    筛选匹配目标主机的 Cookie，并按路径长度和名称排序。

    Args:
        cookies: Cookie 列表
        target_host: 目标主机名

    Returns:
        Cookie 请求头字符串
    """
    matching = [
        cookie for cookie in cookies if cookie_matches_host(cookie, target_host)
    ]
    ordered = sorted(
        matching,
        key=lambda cookie: (-len(cookie.path), cookie.name),
    )
    return "; ".join(f"{cookie.name}={cookie.value}" for cookie in ordered)


def cookie_matches_host(cookie: CookieEntry, target_host: str) -> bool:
    """检查 Cookie 是否匹配目标主机。

    支持域名通配符匹配（如 .aliyun.com 匹配 sls.console.aliyun.com）。

    Args:
        cookie: Cookie 条目
        target_host: 目标主机名

    Returns:
        是否匹配
    """
    domain = cookie.domain.lstrip(".").lower()
    host = target_host.lower()
    return bool(domain) and (host == domain or host.endswith(f".{domain}"))


def read_current_page_html(websocket: CDPWebSocket) -> str | None:
    """读取当前页面的 HTML 内容。

    通过 CDP 的 Runtime.evaluate 执行 JavaScript 获取页面 HTML。

    Args:
        websocket: CDP WebSocket 连接

    Returns:
        页面 HTML 内容，失败时返回 None
    """
    try:
        payload = websocket.command(
            "Runtime.evaluate",
            {
                "expression": (
                    "(document.documentElement && "
                    "document.documentElement.outerHTML) || ''"
                ),
                "returnByValue": True,
            },
        )
    except AliLogError:
        return None
    result = payload.get("result")
    if isinstance(result, dict):
        value = result.get("value")
        if isinstance(value, str) and value:
            return value
    return None


def extract_csrf_token(page_html: str | None) -> str | None:
    """从页面 HTML 中提取 CSRF Token。

    通过正则表达式匹配 ALIYUN_SLS_CONSOLE_CONFIG 中的 SEC_TOKEN。

    Args:
        page_html: 页面 HTML 内容

    Returns:
        CSRF Token，未找到时返回 None
    """
    if not page_html:
        logger.debug("页面 HTML 为空，跳过 CSRF Token 提取")
        return None
    
    logger.debug("正在从页面 HTML (%d 字节) 中提取 CSRF Token", len(page_html))
    
    try:
        match = SEC_TOKEN_PATTERN.search(page_html)
        if match is None:
            logger.debug("未在页面中找到 ALIYUN_SLS_CONSOLE_CONFIG.SEC_TOKEN")
            return None
        token = match.group(1).strip()
        if not token:
            logger.debug("SEC_TOKEN 匹配到空字符串")
            return None
        logger.debug("成功提取 CSRF Token: %s...", token[:20])
        return token
    except (re.error, AttributeError, IndexError) as exc:
        logger.warning("提取 CSRF Token 时发生错误: %s", exc)
        return None


def pick_free_tcp_port() -> int:
    """选择一个空闲的 TCP 端口。

    通过绑定端口 0 让操作系统自动分配空闲端口。

    Returns:
        空闲端口号
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((DEFAULT_CDP_HOST, 0))
        sock.listen(1)
        port = sock.getsockname()[1]
    return int(port)
