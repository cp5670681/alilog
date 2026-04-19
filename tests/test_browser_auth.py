from __future__ import annotations

from pathlib import Path

import pytest

from alilog.browser_auth import (
    CDPWebSocket,
    CookieEntry,
    ManagedBrowser,
    build_cookie_header,
    capture_auth_from_page_target,
    extract_csrf_token,
    resolve_browser_executable,
)
from alilog.models import AliLogError, AuthConfig


class StubWebSocket:
    def __init__(
        self,
        responses: list[object] | None = None,
        *,
        recv_error: Exception | None = None,
    ) -> None:
        self.responses = list(responses or [])
        self.recv_error = recv_error
        self.sent: list[tuple[object, int]] = []
        self.closed = False

    def send(self, payload: object, opcode: int = 1) -> int:
        self.sent.append((payload, opcode))
        return len(str(payload))

    def recv(self) -> object:
        if self.recv_error is not None:
            raise self.recv_error
        return self.responses.pop(0)

    def close(self, status: int = 1000, reason: bytes = b"", timeout: int = 3) -> None:
        self.closed = True


def test_cdp_websocket_command_skips_non_matching_messages() -> None:
    websocket = CDPWebSocket("ws://127.0.0.1:9222/devtools/page/1")
    websocket._socket = StubWebSocket(
        responses=[
            '{"method":"Page.loadEventFired","params":{}}',
            '{"id":1,"result":{"cookies":[]}}',
        ]
    )

    result = websocket.command("Network.getAllCookies")

    assert result == {"cookies": []}
    assert websocket._socket.sent == [
        ('{"id": 1, "method": "Network.getAllCookies", "params": {}}', 1)
    ]


def test_cdp_websocket_connect_bypasses_proxy_for_localhost(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_create_connection(url: str, timeout: float = 30.0, **kwargs):
        captured["url"] = url
        captured["timeout"] = timeout
        captured["kwargs"] = kwargs
        return StubWebSocket()

    monkeypatch.setattr("alilog.browser_auth.create_connection", fake_create_connection)

    websocket = CDPWebSocket("ws://127.0.0.1:9222/devtools/page/1")
    websocket.connect()

    assert captured["url"] == "ws://127.0.0.1:9222/devtools/page/1"
    assert captured["timeout"] == 30.0
    assert captured["kwargs"] == {
        "http_no_proxy": ["127.0.0.1"],
        "suppress_origin": True,
    }
    assert websocket._socket is not None


def test_managed_browser_starts_with_remote_allow_origins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []

    class StubProcess:
        def poll(self) -> int | None:
            return 0

        def wait(self, timeout: int | float | None = None) -> int:
            return 0

    monkeypatch.setattr(
        "alilog.browser_auth.resolve_browser_executable",
        lambda browser: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    )
    monkeypatch.setattr(
        "alilog.browser_auth.subprocess.Popen",
        lambda command, stdout, stderr: commands.append(command) or StubProcess(),
    )
    monkeypatch.setattr(
        "alilog.browser_auth.wait_for_debugger",
        lambda *args, **kwargs: None,
    )

    managed_browser = ManagedBrowser(browser=None, login_url="https://example.com")
    managed_browser.start()

    assert commands == [
        [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            f"--remote-debugging-port={managed_browser.cdp_port}",
            f"--remote-allow-origins=http://127.0.0.1:{managed_browser.cdp_port}",
            f"--user-data-dir={managed_browser._profile_dir.name}",
            "--new-window",
            "--no-first-run",
            "--no-default-browser-check",
            "https://example.com",
        ]
    ]


def test_cdp_websocket_recv_maps_closed_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection_closed = type(
        "WebSocketConnectionClosedException",
        (RuntimeError,),
        {},
    )
    websocket = CDPWebSocket("ws://127.0.0.1:9222/devtools/page/1")
    websocket._socket = StubWebSocket(recv_error=connection_closed("boom"))
    monkeypatch.setattr(
        "alilog.browser_auth.WebSocketConnectionClosedException",
        connection_closed,
    )
    monkeypatch.setattr("alilog.browser_auth.WebSocketException", RuntimeError)

    with pytest.raises(AliLogError, match="CDP 连接已关闭"):
        websocket.recv_json()


def test_cdp_websocket_recv_maps_library_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    websocket = CDPWebSocket("ws://127.0.0.1:9222/devtools/page/1")
    websocket._socket = StubWebSocket(recv_error=RuntimeError("boom"))
    connection_closed = type(
        "WebSocketConnectionClosedException",
        (Exception,),
        {},
    )
    monkeypatch.setattr(
        "alilog.browser_auth.WebSocketConnectionClosedException",
        connection_closed,
    )
    monkeypatch.setattr("alilog.browser_auth.WebSocketException", RuntimeError)

    with pytest.raises(AliLogError, match="读取 CDP 消息失败"):
        websocket.recv_json()


def test_build_cookie_header_keeps_only_console_applicable_cookies() -> None:
    cookies = [
        CookieEntry(name="root", value="1", domain=".aliyun.com", path="/"),
        CookieEntry(
            name="console",
            value="2",
            domain="sls.console.aliyun.com",
            path="/console",
        ),
        CookieEntry(name="other", value="3", domain=".example.com", path="/"),
    ]

    header = build_cookie_header(cookies, "sls.console.aliyun.com")

    assert header == "console=2; root=1"


def test_extract_csrf_token_from_html_extracts_sec_token() -> None:
    page_html = """
    <html>
      <script>
        var ALIYUN_SLS_CONSOLE_CONFIG = {
          loginLink: "https://account.aliyun.com",
          SEC_TOKEN: "98862ee0",
        };
      </script>
    </html>
    """

    assert extract_csrf_token(page_html) == "98862ee0"


def test_extract_csrf_token_from_html_returns_none_without_sec_token() -> None:
    page_html = """
    <html>
      <script>
        var ALIYUN_SLS_CONSOLE_CONFIG = {
          loginLink: "https://account.aliyun.com",
        };
      </script>
    </html>
    """

    assert extract_csrf_token(page_html) is None


def test_capture_auth_from_page_target_retries_stale_websocket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    targets = [
        {"webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/page/stale"},
        {"webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/page/fresh"},
    ]
    calls: list[str] = []

    class StubCDPWebSocket:
        def __init__(self, url: str, *, timeout: float = 30.0) -> None:
            self.url = url

        def __enter__(self):
            calls.append(self.url)
            if self.url.endswith("/stale"):
                raise AliLogError(f"连接 CDP WebSocket 失败: {self.url}")
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def command(self, method: str, params=None):
            if method == "Network.getAllCookies":
                return {
                    "cookies": [
                        {
                            "name": "session",
                            "value": "abc",
                            "domain": ".aliyun.com",
                            "path": "/",
                        }
                    ]
                }
            return {}

    monkeypatch.setattr(
        "alilog.browser_auth.wait_for_page_target",
        lambda *args, **kwargs: targets.pop(0),
    )
    monkeypatch.setattr("alilog.browser_auth.CDPWebSocket", StubCDPWebSocket)
    monkeypatch.setattr(
        "alilog.browser_auth.read_current_page_html",
        lambda websocket: (
            '<script>var ALIYUN_SLS_CONSOLE_CONFIG = '
            '{SEC_TOKEN: "t"};</script>'
        ),
    )
    monkeypatch.setattr("alilog.browser_auth.time.sleep", lambda _: None)

    config = capture_auth_from_page_target(
        "http://127.0.0.1:9222",
        "https://sls.console.aliyun.com/lognext/",
    )

    assert config == AuthConfig(cookie="session=abc", csrf_token="t")
    assert calls == [
        "ws://127.0.0.1:9222/devtools/page/stale",
        "ws://127.0.0.1:9222/devtools/page/fresh",
    ]


def test_resolve_browser_executable_accepts_existing_path(tmp_path: Path) -> None:
    browser = tmp_path / "Chromium"
    browser.write_text("", encoding="utf-8")

    assert resolve_browser_executable(str(browser)) == str(browser)


def test_resolve_browser_executable_rejects_missing_browser() -> None:
    with pytest.raises(AliLogError):
        resolve_browser_executable("/missing/browser")
