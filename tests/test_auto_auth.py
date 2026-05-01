from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import alilog.auto_login as auto_login
import alilog.usecases as usecases
from alilog.models import AliLogError, AuthConfig, RuntimeOptions


def test_run_search_reauthenticates_and_retries_once(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runtime = RuntimeOptions(
        cookie="stale-cookie",
        csrf_token="stale-csrf",
        username="ram-user@example.onaliyun.com",
        password="password",
        seed="seed",
        config_path=tmp_path / ".alilog" / "auth.json",
        project_config_path=tmp_path / ".alilog" / "settings.json",
    )
    clients = [MagicMock(), MagicMock()]
    clients[0].search_logs.side_effect = AliLogError("日志查询失败: HTTP 401")
    clients[1].search_logs.return_value = {"meta": {"count": 1}, "data": []}
    refreshed = AuthConfig(cookie="fresh-cookie", csrf_token="fresh-csrf")
    saved: list[AuthConfig] = []

    monkeypatch.setattr(usecases, "get_client", lambda runtime: clients.pop(0))
    monkeypatch.setattr(usecases, "auto_login_auth", lambda runtime: refreshed)
    monkeypatch.setattr(
        usecases,
        "save_auth_config",
        lambda path, config: saved.append(config),
    )

    _, response = usecases.run_search(
        runtime=runtime,
        project="project-a",
        logstore="logstore-a",
        start="2026-04-16 23:06:00",
        end="2026-04-16 23:21:00",
        last=None,
        timezone_name="Asia/Shanghai",
        query="error",
        page=1,
        size=20,
    )

    assert response == {"meta": {"count": 1}, "data": []}
    assert saved == [
        AuthConfig(
            cookie="fresh-cookie",
            csrf_token="fresh-csrf",
            username="ram-user@example.onaliyun.com",
            password="password",
            seed="seed",
        )
    ]
    captured = capsys.readouterr()
    assert "认证已失效，正在自动登录" in captured.err
    assert "自动登录成功，已刷新认证信息" in captured.err


def test_run_search_auto_logs_in_when_cookie_is_missing(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runtime = RuntimeOptions(
        cookie=None,
        csrf_token=None,
        username="ram-user@example.onaliyun.com",
        password="password",
        seed="seed",
        config_path=tmp_path / ".alilog" / "auth.json",
        project_config_path=tmp_path / ".alilog" / "settings.json",
    )
    client = MagicMock()
    client.search_logs.return_value = {"meta": {"count": 1}, "data": []}
    refreshed = AuthConfig(cookie="fresh-cookie", csrf_token="fresh-csrf")
    saved: list[AuthConfig] = []

    monkeypatch.setattr(usecases, "get_client", lambda runtime: client)
    monkeypatch.setattr(usecases, "auto_login_auth", lambda runtime: refreshed)
    monkeypatch.setattr(
        usecases,
        "save_auth_config",
        lambda path, config: saved.append(config),
    )

    _, response = usecases.run_search(
        runtime=runtime,
        project="project-a",
        logstore="logstore-a",
        start="2026-04-16 23:06:00",
        end="2026-04-16 23:21:00",
        last=None,
        timezone_name="Asia/Shanghai",
        query="error",
        page=1,
        size=20,
    )

    assert response == {"meta": {"count": 1}, "data": []}
    assert saved == [
        AuthConfig(
            cookie="fresh-cookie",
            csrf_token="fresh-csrf",
            username="ram-user@example.onaliyun.com",
            password="password",
            seed="seed",
        )
    ]
    captured = capsys.readouterr()
    assert "正在自动登录" in captured.err
    assert "自动登录成功，已刷新认证信息" in captured.err


def test_auto_login_requires_username_password_and_seed(tmp_path) -> None:
    runtime = RuntimeOptions(
        cookie="stale-cookie",
        csrf_token="stale-csrf",
        username="ram-user@example.onaliyun.com",
        password=None,
        seed="seed",
        config_path=tmp_path / ".alilog" / "auth.json",
        project_config_path=tmp_path / ".alilog" / "settings.json",
    )

    with pytest.raises(AliLogError, match="username/password/seed"):
        usecases.auto_login_auth(runtime)


def test_auto_login_defaults_to_headless_browser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class StubBrowser:
        def new_context(self, **kwargs):
            raise RuntimeError("stop after launch")

        def close(self) -> None:
            captured["closed"] = True

    class StubChromium:
        def launch(self, **kwargs):
            captured["launch"] = kwargs
            return StubBrowser()

    class StubPlaywright:
        chromium = StubChromium()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    monkeypatch.setattr(auto_login, "sync_playwright", lambda: StubPlaywright())

    with pytest.raises(RuntimeError, match="stop after launch"):
        auto_login.auto_login_with_password(
            username="ram-user@example.onaliyun.com",
            password="password",
            seed="seed",
        )

    assert captured["launch"]["headless"] is True


def test_auto_login_fills_full_username(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    filled: list[str] = []

    class StubLocator:
        def __init__(self, selector: str) -> None:
            self.selector = selector
            self.first = self

        def is_visible(self, timeout: int = 1000) -> bool:
            return self.selector in {
                "input[placeholder*='用户名']",
                "button:has-text('下一步')",
                "input[type='password']",
                "button:has-text('登录')",
            }

        def fill(self, value: str) -> None:
            filled.append(value)

        def click(self) -> None:
            return None

    class StubPage:
        def goto(self, *args, **kwargs) -> None:
            return None

        def locator(self, selector: str) -> StubLocator:
            return StubLocator(selector)

        def wait_for_load_state(self, *args, **kwargs) -> None:
            return None

        def wait_for_url(self, *args, **kwargs) -> None:
            return None

        def wait_for_timeout(self, timeout: int) -> None:
            return None

        def content(self) -> str:
            return (
                "<script>var ALIYUN_SLS_CONSOLE_CONFIG = "
                '{SEC_TOKEN: "csrf-token"};</script>'
            )

    class StubContext:
        def new_page(self) -> StubPage:
            return StubPage()

        def cookies(self) -> list[dict[str, str]]:
            return [
                {
                    "name": "session",
                    "value": "value",
                    "domain": ".aliyun.com",
                    "path": "/",
                }
            ]

    class StubBrowser:
        def new_context(self, **kwargs) -> StubContext:
            return StubContext()

        def close(self) -> None:
            return None

    class StubPlaywright:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    monkeypatch.setattr(auto_login, "sync_playwright", lambda: StubPlaywright())
    monkeypatch.setattr(
        auto_login,
        "launch_chromium",
        lambda playwright, headless: StubBrowser(),
    )

    auto_login.auto_login_with_password(
        username="projects-internal-line@rccchina.onaliyun.com",
        password="password",
        seed="seed",
    )

    assert filled[0] == "projects-internal-line@rccchina.onaliyun.com"


def test_auto_login_waits_like_reference_flow_before_and_after_username(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []

    class StubLocator:
        def __init__(self, selector: str) -> None:
            self.selector = selector
            self.first = self

        def is_visible(self, timeout: int = 1000) -> bool:
            return self.selector in {
                "input[placeholder*='用户名']",
                "button:has-text('下一步')",
                "input[type='password']",
                "button:has-text('登录')",
            }

        def fill(self, value: str) -> None:
            events.append(f"fill:{value}")

        def click(self) -> None:
            events.append(f"click:{self.selector}")

    class StubPage:
        def goto(self, *args, **kwargs) -> None:
            events.append("goto")

        def locator(self, selector: str) -> StubLocator:
            return StubLocator(selector)

        def wait_for_load_state(self, *args, **kwargs) -> None:
            events.append("load-state")

        def wait_for_url(self, *args, **kwargs) -> None:
            events.append("wait-url")

        def wait_for_timeout(self, timeout: int) -> None:
            events.append(f"wait:{timeout}")

        def content(self) -> str:
            return (
                "<script>var ALIYUN_SLS_CONSOLE_CONFIG = "
                '{SEC_TOKEN: "csrf-token"};</script>'
            )

    class StubContext:
        def new_page(self) -> StubPage:
            return StubPage()

        def cookies(self) -> list[dict[str, str]]:
            return [
                {
                    "name": "session",
                    "value": "value",
                    "domain": ".aliyun.com",
                    "path": "/",
                }
            ]

    class StubBrowser:
        def new_context(self, **kwargs) -> StubContext:
            return StubContext()

        def close(self) -> None:
            return None

    class StubPlaywright:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    monkeypatch.setattr(auto_login, "sync_playwright", lambda: StubPlaywright())
    monkeypatch.setattr(
        auto_login,
        "launch_chromium",
        lambda playwright, headless: StubBrowser(),
    )

    auto_login.auto_login_with_password(
        username="projects-internal-line@rccchina.onaliyun.com",
        password="password",
        seed="seed",
    )

    assert events[:4] == [
        "goto",
        "wait:3000",
        "fill:projects-internal-line@rccchina.onaliyun.com",
        "wait:500",
    ]


def test_click_first_visible_waits_until_button_enabled() -> None:
    events: list[str] = []

    class StubLocator:
        first = None

        def __init__(self) -> None:
            self.first = self
            self.enabled_checks = 0

        def is_visible(self, timeout: int = 5000) -> bool:
            return True

        def is_enabled(self, timeout: int = 500) -> bool:
            self.enabled_checks += 1
            return self.enabled_checks >= 3

        def click(self) -> None:
            events.append("click")

    locator = StubLocator()

    class StubPage:
        def locator(self, selector: str) -> StubLocator:
            return locator

        def wait_for_timeout(self, timeout: int) -> None:
            events.append(f"wait:{timeout}")

    auto_login.click_first_visible(StubPage(), ["button"], "下一步按钮")

    assert events == ["wait:200", "wait:200", "click"]


def test_read_page_html_after_navigation_retries_content_errors() -> None:
    events: list[str] = []

    class StubPage:
        def __init__(self) -> None:
            self.calls = 0

        def content(self) -> str:
            self.calls += 1
            if self.calls < 3:
                raise auto_login.PlaywrightError("navigating")
            return (
                "<script>var ALIYUN_SLS_CONSOLE_CONFIG = "
                '{SEC_TOKEN: "csrf-token"};</script>'
            )

        def wait_for_timeout(self, timeout: int) -> None:
            events.append(f"wait:{timeout}")

    html = auto_login.read_page_html_after_navigation(StubPage())

    assert "csrf-token" in html
    assert events == ["wait:500", "wait:500"]
