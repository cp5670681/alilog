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

```bash
alilog auth login
```

如果自动探测不到 Chrome/Chromium/Edge，可以显式指定浏览器可执行文件：

```bash
alilog auth login \
  --browser '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
```

或者手动保存cookie和csrf-token(可通过抓包获取):

```bash
alilog auth save \
  --cookie 'aliyun_lang=zh; ...' \
  --csrf-token 'xxxxxxxx'
```

# 项目级配置
项目级配置默认会从当前工作目录向上查找最近的项目根目录的 `.alilog.json`。

```json
{
  "project": "k8s-log-c19af6eaf83e44c28a7eb544564eee247",
  "default_logstore": "research",
  "logstore_rules": [
    {
      "logstore": "research",
      "command": "./bin/start-web --config ./config/web.yaml",
      "description": "主 Web 服务"
    },
    {
      "logstore": "research-worker-default",
      "command": "./bin/start-worker --config ./config/worker-default.yaml",
      "description": "默认队列后台任务"
    }
  ]
}
```

`default_logstore` 仍用于命令行默认值；`logstore_rules` 用来描述“哪个启动入口/代码职责会把日志打到哪个 logstore”。

## 查日志

`search` 支持：

- Unix 时间戳（10 位秒级）
- ISO 时间
- `YYYY-MM-DD HH:MM[:SS]`
- 相对时间窗口 `--last`

如果当前项目已经有 `.alilog.json`，那么 `--project` 和 `--logstore` 可以省略：

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

同理，如果项目根目录已经有 `.alilog.json`，那么 `--project` 和 `--logstore` 也可以省略。下面先给出完整写法：

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
