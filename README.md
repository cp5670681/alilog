# alilog

阿里云 SLS Console 命令行查询工具，基于 `click` 实现。

当前支持两类能力：

- 查日志：对应 `getLogs.json`
- 查上下文：对应 `contextQueryLogs.json` 的前文、后文或两侧

## 安装

```bash
uv sync
```

开发态直接运行：

```bash
uv run alilog --help
```

如果希望当前 shell 里直接用 `alilog`：

```bash
source .venv/bin/activate
alilog --help
```

如果希望安装成用户级命令：

```bash
uv tool install .
alilog --help
```

## 认证

最少需要提供浏览器登录后的 Cookie。

项目默认配置文件是：

```text
~/.alilog.json
```

文件里会保存：

```json
{
  "cookie": "aliyun_lang=zh; ...",
  "csrf_token": "f11fea43"
}
```

建议仅当前用户可读写。

### 保存认证信息

```bash
uv run alilog auth save \
  --cookie 'aliyun_lang=zh; ...' \
  --csrf-token 'f11fea43'
```

保存后，后续 `search` 和 `context` 会自动读取 `~/.alilog.json`。

查看当前认证状态：

```bash
uv run alilog auth show
```

清除本地认证信息：

```bash
uv run alilog auth clear
```

认证读取优先级：

- 命令行参数 `--cookie`、`--csrf-token`
- 环境变量 `ALILOG_COOKIE`、`ALILOG_CSRF_TOKEN`
- 配置文件 `~/.alilog.json`

```bash
export ALILOG_COOKIE='aliyun_lang=zh; ...'
export ALILOG_CSRF_TOKEN='f11fea43'
```

也可以通过命令行传入：

```bash
uv run alilog --cookie 'aliyun_lang=zh; ...' --csrf-token 'f11fea43' ...
```

如果还需要补充浏览器里的其他请求头，可以重复传入 `--header`：

```bash
uv run alilog \
  --header 'bx-v: 2.5.36' \
  --header 'accept-language: zh-CN,zh;q=0.9' \
  ...
```

如果需要自定义配置文件位置：

```bash
uv run alilog --config /path/to/alilog.json auth show
```

## 查日志

现在 `search` 同时支持：

- Unix 时间戳
- ISO 时间
- `YYYY-MM-DD HH:MM[:SS]`
- 相对时间窗口 `--last`

### 用时间戳

```bash
uv run alilog search \
  --project k8s-log-c19af6eaf83e44c28a7eb544564eee247 \
  --logstore research \
  --from 1776351960 \
  --to 1776352860 \
  --query 'error | with_pack_meta'
```

### 用绝对时间

```bash
uv run alilog search \
  --project k8s-log-c19af6eaf83e44c28a7eb544564eee247 \
  --logstore research \
  --from '2026-04-16 23:06:00' \
  --to '2026-04-16 23:21:00' \
  --query 'error | with_pack_meta'
```

### 用相对时间

```bash
uv run alilog search \
  --project k8s-log-c19af6eaf83e44c28a7eb544564eee247 \
  --logstore research \
  --last 15m \
  --query 'error | with_pack_meta'
```

也可以把 `--last` 和 `--to` 组合使用：

```bash
uv run alilog search \
  --project k8s-log-c19af6eaf83e44c28a7eb544564eee247 \
  --logstore research \
  --to '2026-04-16 23:21:00' \
  --last 15m \
  --query 'error | with_pack_meta'
```

无时区的时间字符串默认按 `Asia/Shanghai` 解析；如果需要可以覆盖：

```bash
uv run alilog search ... --timezone UTC
```

默认输出适合终端阅读的摘要，包含：

- 最终解析后的时间范围
- 时间
- `__tag__:__pack_id__`
- `__pack_meta__`
- 日志正文

如果要看原始返回：

```bash
uv run alilog search ... --json
```

## 查上下文

上下文查询需要 `pack_id` 和 `pack_meta`。这两个字段可直接来自 `search` 结果。

```bash
uv run alilog context \
  --project k8s-log-c19af6eaf83e44c28a7eb544564eee247 \
  --logstore research \
  --pack-id EBA5D6B0CB95EA56-F3 \
  --pack-meta '1|MTc2ODA0MTQzNjk1MDUwNzQwMQ==|54|6'
```

默认会同时查前文和后文，也就是分别调用：

- `Reserve=false`
- `Reserve=true`

也可以只查一侧：

```bash
uv run alilog context ... --direction prev
uv run alilog context ... --direction next
```

如果不想传 `pack_meta`，也可以把它拆开：

```bash
uv run alilog context \
  --project k8s-log-c19af6eaf83e44c28a7eb544564eee247 \
  --logstore research \
  --pack-id EBA5D6B0CB95EA56-F3 \
  --shard-id 1 \
  --cursor 'MTc2ODA0MTQzNjk1MDUwNzQwMQ==' \
  --pack-num 54 \
  --offset 6
```

## 注意

- `--json` 会输出完整响应，日志正文里可能包含敏感字段，不要直接外发。
- 这个工具调用的是阿里云 Console 接口，依赖当前登录态，Cookie 过期后需要重新获取。
