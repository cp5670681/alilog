"""自动登录阿里云 RAM 并提取 SLS Console 认证信息。"""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import quote

from mintotp import totp  # type: ignore[import-untyped]
from playwright.sync_api import (
    Browser,
    ViewportSize,
    sync_playwright,
)
from playwright.sync_api import (
    Error as PlaywrightError,
)
from playwright.sync_api import (
    TimeoutError as PlaywrightTimeoutError,
)

from .browser_auth import (
    CookieEntry,
    build_cookie_header,
    extract_csrf_token,
    resolve_browser_executable,
)
from .client import BASE_URL
from .models import AliLogError, AuthConfig

DEFAULT_CALLBACK_URL = f"{BASE_URL}/lognext/"
DEFAULT_VIEWPORT = ViewportSize(width=1440, height=900)
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def auto_login_with_password(
    *,
    username: str,
    password: str,
    seed: str,
    callback_url: str = DEFAULT_CALLBACK_URL,
    headless: bool = True,
) -> AuthConfig:
    """使用账号、密码和 TOTP seed 自动登录并返回认证配置。"""
    domain = extract_ram_domain(username)
    login_url = (
        f"https://signin.aliyun.com/{domain}/login.htm?"
        f"callback={quote(callback_url, safe=':/?=&')}"
    )

    try:
        with sync_playwright() as playwright:
            browser = launch_chromium(playwright, headless=headless)
            try:
                context = browser.new_context(
                    viewport=DEFAULT_VIEWPORT,
                    user_agent=DEFAULT_USER_AGENT,
                    locale="zh-CN",
                )
                page = context.new_page()
                page.goto(login_url, wait_until="networkidle")
                page.wait_for_timeout(3000)
                fill_first_visible(
                    page,
                    [
                        "input[placeholder*='用户名']",
                        "input[placeholder*='Username']",
                        "input[type='text']",
                        "input:not([type='password'])",
                        "#username",
                        "[name='username']",
                    ],
                    username,
                    "用户名输入框",
                )
                page.wait_for_timeout(500)
                click_first_visible(page, ["button:has-text('下一步')"], "下一步按钮")
                page.wait_for_timeout(2000)
                fill_first_visible(
                    page,
                    ["input[type='password']"],
                    password,
                    "密码输入框",
                    timeout=10_000,
                )
                page.wait_for_timeout(500)
                click_first_visible(page, ["button:has-text('登录')"], "登录按钮")
                page.wait_for_timeout(3000)
                complete_mfa_if_present(page, seed)
                wait_for_login_redirect(page)
                page_html = read_page_html_after_navigation(page)
                cookie_header = build_cookie_header(
                    [
                        CookieEntry(
                            name=str(cookie["name"]),
                            value=str(cookie["value"]),
                            domain=str(cookie["domain"]),
                            path=str(cookie.get("path") or "/"),
                        )
                        for cookie in context.cookies()
                    ],
                    "sls.console.aliyun.com",
                )
                if not cookie_header:
                    raise AliLogError(
                        "自动登录后未获取到可用于 SLS Console 的 Cookie。"
                    )
                csrf_token = extract_csrf_token(page_html)
                if not csrf_token:
                    raise AliLogError(
                        "自动登录后未从 ALIYUN_SLS_CONSOLE_CONFIG 提取到 csrf token。"
                    )
                return AuthConfig(cookie=cookie_header, csrf_token=csrf_token)
            finally:
                browser.close()
    except PlaywrightTimeoutError as exc:
        raise AliLogError("自动登录等待页面元素超时。") from exc
    except PlaywrightError as exc:
        raise AliLogError(f"自动登录失败: {exc}") from exc


def launch_chromium(playwright: Any, *, headless: bool) -> Browser:
    """启动 Playwright Chromium，不可用时回退到系统浏览器。"""
    launch_args = [
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
    ]
    try:
        return playwright.chromium.launch(headless=headless, args=launch_args)
    except PlaywrightError:
        executable = resolve_browser_executable(None)
        return playwright.chromium.launch(
            executable_path=executable,
            headless=headless,
            args=launch_args,
        )


def extract_ram_domain(username: str) -> str:
    """从 RAM 用户名中提取企业域名。"""
    if "@" not in username:
        raise AliLogError(
            "自动登录需要 username 包含 RAM 域名，例如 "
            "user@example.onaliyun.com。"
        )
    domain = username.rsplit("@", 1)[1].strip()
    if not domain:
        raise AliLogError("自动登录需要 username 包含 RAM 域名。")
    return domain


def fill_first_visible(
    page: Any,
    selectors: list[str],
    value: str,
    label: str,
    *,
    timeout: int = 1000,
) -> None:
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            if locator.is_visible(timeout=timeout):
                locator.fill(value)
                return
        except PlaywrightTimeoutError:
            continue
    raise AliLogError(f"自动登录未找到{label}。")


def click_first_visible(page: Any, selectors: list[str], label: str) -> None:
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            if locator.is_visible(timeout=5000):
                wait_until_enabled(page, locator, label)
                locator.click()
                return
        except PlaywrightTimeoutError:
            continue
        except PlaywrightError as exc:
            raise AliLogError(f"自动登录点击{label}失败。") from exc
    raise AliLogError(f"自动登录未找到{label}。")


def wait_until_enabled(
    page: Any,
    locator: Any,
    label: str,
    *,
    timeout: int = 30_000,
) -> None:
    """等待按钮从 disabled 变为可点击。"""
    deadline = time.monotonic() + timeout / 1000
    while time.monotonic() < deadline:
        if not hasattr(locator, "is_enabled") or locator.is_enabled(timeout=500):
            return
        page.wait_for_timeout(200)
    raise AliLogError(f"自动登录找到{label}，但按钮一直不可点击。")


def wait_for_login_redirect(page: Any) -> None:
    """等待登录后跳转，保持和参考脚本一致。"""
    try:
        page.wait_for_url("**/sls.console.aliyun.com/**", timeout=30_000)
    except PlaywrightTimeoutError:
        pass
    page.wait_for_timeout(3000)


def read_page_html_after_navigation(page: Any) -> str:
    """页面跳转稳定后读取 HTML，避开 navigating 时的 content 错误。"""
    last_error: PlaywrightError | None = None
    for _ in range(10):
        try:
            return page.content()
        except PlaywrightError as exc:
            last_error = exc
            page.wait_for_timeout(500)
    raise AliLogError("自动登录后读取页面 HTML 失败。") from last_error


def complete_mfa_if_present(page: Any, seed: str) -> None:
    mfa_input = page.locator(
        "input[placeholder*='验证码'], "
        "input[placeholder*='安全码'], "
        "input[maxlength='6']"
    ).first
    try:
        if not mfa_input.is_visible(timeout=5000):
            return
    except PlaywrightTimeoutError:
        return
    mfa_input.fill(totp(seed))
    page.wait_for_timeout(500)
    confirm_button = page.locator(
        "button:has-text('确定'), "
        "button:has-text('确认'), "
        "button:has-text('提交')"
    ).first
    try:
        if confirm_button.is_visible(timeout=5000):
            confirm_button.click()
    except PlaywrightTimeoutError:
        return
