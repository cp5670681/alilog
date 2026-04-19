---
name: alilog
description: 当你想查询阿里云 SLS Console 日志、获取某条日志的上下文，或通过 alilog CLI 管理本地认证信息时，使用这个 skill。
disable-model-invocation: true
argument-hint: search|context|auth，后面跟正常的 alilog 参数
allowed-tools: Bash(alilog:*), Bash(which alilog), Bash(uv tool install:*), Bash(pwd)
---

# alilog

使用本地 `alilog` CLI 处理阿里云 SLS Console 日志相关操作。

这个 skill 适合显式调用，比如 `/alilog search ...` 或 `/alilog context ...`。

## 工作目标

当用户想做下面这些事情时，优先使用这个 skill：

- 查询某个时间范围内的日志
- 基于某条日志继续抓取上下文
- 保存本地认证信息
- 不确定命令怎么写时，先通过 `--help` 自查再执行

你的目标不是解释 `alilog` 的源码，而是把用户需求翻译成正确的 CLI 命令并给出结果摘要。

## 先安装 alilog

如果当前机器上还没有 `alilog` 命令，请先安装：

```bash
uv tool install git+https://github.com/cp5670681/alilog.git
```

如果你是在本地仓库里使用，而不是从 GitHub 安装，可以在仓库根目录执行：

```bash
uv tool install .
```

安装后，如果用户需要升级：

- 本地仓库安装：`uv tool install . --reinstall`
- GitHub 安装：`uv tool upgrade alilog`

## 先做的检查

开始执行前，按这个顺序判断：

1. 先确认 `alilog` 是否可用：`which alilog`
2. 如果命令不存在，先提示用户安装
3. 如果用户没有明确给 `project` 或 `logstore`，默认假设当前项目根目录有 `.alilog.json`
4. 如果你不确定参数名、命令格式或支持的选项，先运行帮助命令自查

可用的帮助命令：

```bash
alilog --help
alilog search --help
alilog context --help
alilog auth --help
alilog auth save --help
```

## 支持的操作

- `search`: `alilog search --project ... --logstore ... --from ... --to ... --query ...`
- `context`: `alilog context --project ... --logstore ... --pack-id ... --pack-meta ...`
- `auth save`: `alilog auth save --cookie ... [--csrf-token ...]`

## 配置约定

### 用户级认证文件

`alilog` 默认从下面的文件读取认证信息：

```text
~/.alilog.json
```

这里通常存：

- `cookie`
- `csrf_token`

### 项目级默认配置

`alilog` 会从当前工作目录向上查找最近的项目根目录 `.alilog.json`，用于补全默认的 `project` 和 `logstore`。

典型格式：

```json
{
  "project": "k8s-log-c19af6eaf83e44c28a7eb544564eee247",
  "default_logstore": "research",
  "logstores": ["research", "research-sidekiq"]
}
```

如果用户没有提供 `--project` 或 `--logstore`，优先使用这里的默认值。

## 操作流程

1. 把用户请求翻译成对应的 `alilog` 子命令。
2. 如果用户已经给了 `project`、`logstore`、`query`、时间范围，就原样保留。
3. 如果用户没给 `project` 或 `logstore`，优先依赖项目根目录 `.alilog.json`。
4. 如果命令格式拿不准，先运行 `alilog ... --help` 自查。
5. 只有在必填参数无法安全推断时，才向用户补问。
6. 执行完成后，清晰总结结果，不要输出无意义的噪音。

## 常见任务映射

### 1. 查日志

如果项目配置里已经有默认 `project` 和 `default_logstore`，优先使用简写：

```bash
alilog search --from '2026-04-16 23:06:00' --to '2026-04-16 23:21:00' --query 'error'
```

如果用户明确指定了项目或 logstore，就显式传参：

```bash
alilog search \
  --project k8s-log-c19af6eaf83e44c28a7eb544564eee247 \
  --logstore research \
  --from '2026-04-16 23:06:00' \
  --to '2026-04-16 23:21:00' \
  --query 'error'
```

### 2. 用相对时间窗口查日志

```bash
alilog search --to '2026-04-16 23:21:00' --last 15m --query 'error'
```

### 3. 查上下文

```bash
alilog context \
  --pack-id EBA5D6B0CB95EA56-F3 \
  --pack-meta '1|MTc2ODA0MTQzNjk1MDUwNzQwMQ==|54|6'
```

### 4. 保存认证信息

```bash
alilog auth save --cookie 'aliyun_lang=zh; ...' --csrf-token 'xxxxxxxx'
```

## 何时需要补问用户

只有在下面这些情况才补问：

- 当前目录及其上级没有项目级 `.alilog.json`，且用户也没给 `project`
- 项目配置里没有 `default_logstore`，且用户也没给 `logstore`
- `context` 缺少 `pack_id` 或 `pack_meta`
- 用户给的需求不足以构造时间范围或查询语句

如果可以从项目配置、用户上下文或上一步输出中拿到值，就不要重复问。

## 输出要求

- 优先总结重点结果，例如命中数量、时间范围、关键日志片段
- 如果执行的是 `context`，说明这是前文还是后文
- 如果执行失败，给出简短可操作的下一步，而不是只贴错误
- 不要把完整 cookie、csrf token 原样展示给用户

## 安全要求

- 除非用户明确要求，否则不要回显完整的 cookie 值。
- 把 `~/.alilog.json` 视为敏感的本地凭证文件。
- 需要提醒用户：这个工具依赖阿里云 Console cookie 和非官方 Console API。
