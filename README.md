# alilog

[English](README.en.md) | 简体中文

`alilog` 是一个非官方的阿里云 SLS Console 命令行工具，用于查询日志，并基于某条日志继续获取上下文。

## 项目定位

这个项目只保留两条核心链路：

- `search`：查日志
- `context`：基于 `search` 结果继续查上下文

## 安全说明

- 这个工具依赖阿里云登录态。
- 认证基于浏览器 Cookie，只建议在本机和受信任环境使用。
- 如果启用自动登录，`~/.alilog/auth.json` 会保存 RAM 用户名、密码和 TOTP seed。请确保该文件只在受信任机器上使用，并保持默认的本机文件权限。

## 环境要求

- Python 3.10+
- 示例中的安装和开发命令使用 `uv`

## 安装

从 GitHub 安装成用户级命令：

```bash
uv tool install git+https://github.com/cp5670681/alilog.git
alilog --help
```

如果你就在本地仓库目录里，也可以直接安装当前工作区版本：

```bash
uv tool install .
alilog --help
```

升级命令：

- 本地仓库安装：`uv tool install . --reinstall`
- GitHub 安装：`uv tool upgrade alilog`

## 登录

### 登录并刷新认证

```bash
alilog auth login
```

如果已经通过 `auth save` 保存 RAM 用户名、密码和 TOTP seed，`auth login` 会直接使用无头浏览器自动登录并刷新 Cookie/csrf token。

如果没有完整的自动登录凭据，`auth login` 会降级为原来的手动浏览器登录流程。若自动探测不到 Chrome/Chromium/Edge，可以显式指定浏览器可执行文件：

```bash
alilog auth login \
  --browser '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
```

### 自动登录凭据

可以保存 RAM 用户名、密码和 TOTP seed。之后 `auth login` 会优先自动刷新认证；`search` 或 `context` 如果发现认证失效，也会自动登录获取新的 Cookie 和 csrf token，保存到 `~/.alilog/auth.json`，并重试当前请求一次。

```bash
alilog auth save \
  --username 'ram-user@example.onaliyun.com' \
  --password 'your-password' \
  --seed 'your-totp-seed'
```

也可以同时保存已有 Cookie：

```bash
alilog auth save \
  --cookie 'aliyun_lang=zh; ...' \
  --csrf-token 'xxxxxxxx' \
  --username 'ram-user@example.onaliyun.com' \
  --password 'your-password' \
  --seed 'your-totp-seed'
```

自动登录使用 Playwright，默认以无头模式运行。默认会尝试 Playwright 自带 Chromium；如果未安装，会回退到系统中的 Chrome/Chromium/Edge。需要安装 Playwright 自带浏览器时执行：

```bash
uv run playwright install chromium
```

### 手动保存 Cookie

也可以只手动保存 Cookie 和 csrf-token（可通过抓包获取）：

```bash
alilog auth save \
  --cookie 'aliyun_lang=zh; ...' \
  --csrf-token 'xxxxxxxx'
```

# 默认配置
认证配置保存在 `~/.alilog/auth.json`。

示例：

```json
{
  "cookie": "aliyun_lang=zh; ...",
  "csrf_token": "xxxxxxxx",
  "username": "ram-user@example.onaliyun.com",
  "password": "your-password",
  "seed": "your-totp-seed"
}
```

默认项目和默认日志库保存在 `~/.alilog/settings.json`。

```json
{
  "default_project": "k8s-log-c19af6eaf83e44c28a7eb544564eee247",
  "default_logstore": "research"
}
```

## 查日志

`search` 支持：

- Unix 时间戳（10 位秒级）
- ISO 时间
- `YYYY-MM-DD HH:MM[:SS]`
- 相对时间窗口 `--last`

如果 `~/.alilog/settings.json` 已经配置了 `default_project` 和 `default_logstore`，那么 `--project` 和 `--logstore` 可以省略：

```bash
alilog search \
  --from '2026-04-16 23:06:00' \
  --to '2026-04-16 23:21:00' \
  --query 'error'
```

如果需要，也可以继续显式覆盖：

```bash
alilog search \
  --project k8s-log-c19af6eaf83e44c28a7eb544564eee247 \
  --logstore research \
  --from '2026-04-16 23:06:00' \
  --to '2026-04-16 23:21:00' \
  --query 'error'
```

相对时间窗口示例：

```bash
alilog search \
  --project k8s-log-c19af6eaf83e44c28a7eb544564eee247 \
  --logstore research \
  --last 15m \
  --query 'error'
```

## 查上下文

`context` 直接使用 `search` 输出里的 `pack_id` 和 `pack_meta`，默认同时查前文和后文。

同理，如果 `~/.alilog/settings.json` 已经配置了 `default_project` 和 `default_logstore`，那么 `--project` 和 `--logstore` 也可以省略。下面先给出完整写法：

```bash
alilog context \
  --project k8s-log-c19af6eaf83e44c28a7eb544564eee247 \
  --logstore research \
  --pack-id EBA5D6B0CB95EA56-F3 \
  --pack-meta '1|MTc2ODA0MTQzNjk1MDUwNzQwMQ==|54|6'
```

## 开发

安装开发依赖：

```bash
uv sync --group dev
```

运行测试：

```bash
uv run pytest -q
```

运行 lint：

```bash
uv run ruff check .
```

运行类型检查：

```bash
uv run mypy
```

CI 会在 Python 3.10、3.11、3.12、3.13 上运行 Ruff、mypy 和测试。

## License

MIT，见 [LICENSE](LICENSE)。
