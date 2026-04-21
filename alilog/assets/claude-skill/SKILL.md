---
name: alilog
description: 当你想查询阿里云 SLS Console 日志、获取某条日志的上下文，或通过 alilog CLI 管理本地认证信息时，使用这个 skill。
argument-hint: search|context|auth，后面跟正常参数或任务描述
allowed-tools: Bash(alilog:*), Bash(which alilog), Bash(uv tool install:*), Bash(pwd), Bash(rg:*), Bash(cat:*), Bash(sed:*), Bash(ls:*)
---

# alilog

使用本地 `alilog` CLI 处理阿里云 SLS Console 日志相关操作。

这个 skill 适合显式调用，比如 `/alilog search ...` 或 `/alilog context ...`。

## 适用场景

当用户想做下面这些事情时，优先使用这个 skill：

- 查询某个时间范围内的日志
- 基于某条日志继续抓取上下文
- 保存本地认证信息
- 没有明确给出 `logstore`，但任务里带有代码、启动命令、任务入口或部署线索，需要你自主判断应该使用哪个 logstore
- 不确定命令怎么写，需要先通过 `--help` 自查

你的职责只有两件事：

1. 把用户需求翻译成正确的 `alilog` CLI 命令并执行。
2. 当缺少 `logstore` 时，优先根据项目级 `.alilog.json` 的 `logstore_rules` 选择最合适的 logstore。

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

## 执行前检查

开始执行前，按这个顺序判断：

1. 先确认 `alilog` 是否可用：`which alilog`
2. 如果命令不存在，先提示用户安装
3. 如果用户没有明确给 `project` 或 `logstore`，默认假设当前项目根目录有 `.alilog.json`
4. 如果你不确定参数名、命令格式或支持的选项，先运行帮助命令自查
5. 如果任务里隐含了代码入口、进程职责或运行命令，但没有显式给 `logstore`，先走“选择 logstore”流程，不要直接回落到 `default_logstore`

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

`logstore` 选择不是单独的 CLI 子命令，而是执行 `search` / `context` 之前的一步判断。

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

`alilog` 会从当前工作目录向上查找最近的项目根目录 `.alilog.json`。

这里有两层用途：

- `project` / `default_logstore`：用于补全 CLI 默认值
- `logstore_rules`：用于描述“哪个运行入口或职责”对应“哪个 logstore”，用于在缺少 `--logstore` 时做自主选择

典型格式：

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

## 操作流程

1. 把用户请求翻译成对应的 `alilog` 子命令。
2. 如果用户已经给了 `project`、`logstore`、`query`、时间范围，就原样保留。
3. 如果用户没给 `project`，优先依赖项目根目录 `.alilog.json`。
4. 如果用户没给 `logstore`，先进入“选择 Logstore”流程。
5. 如果命令格式拿不准，先运行 `alilog ... --help` 自查。
6. 只有在必填参数无法安全推断时，才向用户补问。
7. 执行完成后，清晰总结结果，不要输出无意义的噪音。

## 选择 Logstore

当 `search` 或 `context` 缺少 `logstore` 时，按下面的优先级处理：

1. 如果用户明确给了 `--logstore`，直接使用用户指定值。
2. 如果任务里带有可归因线索，优先用 `logstore_rules` 选择 logstore。
3. 如果没有足够线索，但项目配置里有 `default_logstore`，使用它作为兜底默认值。
4. 如果以上都做不到，再补问用户。

可归因线索包括：

- 代码文件路径
- 类名、方法名、worker 名
- 服务启动配置文件
- worker 配置文件
- 任务名
- deployment / 容器启动命令
- queue 名
- 进程职责描述

当需要用 `logstore_rules` 做选择时，按这个顺序做：

1. 找当前项目根目录最近的 `.alilog.json`。
2. 读取 `logstore_rules`，把它视为项目内“运行入口 -> logstore”的主映射表。
3. 提取任务中的线索。
4. 如果拿到的是代码文件或业务类，不要直接猜 logstore。先在仓库里继续找它归属的运行入口，例如：
   - 被哪个 worker / queue 使用
   - 被哪个任务入口调用
   - 被哪个 Web 请求入口调用
   - 被哪个部署命令启动的进程承载
5. 用找到的运行入口去匹配 `logstore_rules` 的 `command` 和 `description`。
6. 如果可以唯一命中，直接把该 logstore 用到后续 `alilog search` / `alilog context`。
7. 如果规则无法唯一命中，才给出多个候选 logstore，并说明各自依据。
8. 如果没有足够证据，不要硬猜；明确说“当前只能缩小到这些候选”，并指出还缺什么线索。

判断优先级：

- 最强证据：和 `logstore_rules.command` 直接对应的启动命令
- 次强证据：明确对应某个 worker 配置 / 任务入口 / 服务启动配置
- 辅助证据：部署文件、进程名、日志说明、业务职责
- 最弱证据：只凭文件名或模块名的主观猜测

## 常见任务映射

### 1. 查日志

查询语句约束：

- 不要在 `--query` 里直接包含 `/`。
- 如果用户输入里有类似 `api/create/999` 这种路径式关键词，需要拆成多个词并用 `and` 连接，例如：`api and create and 999`
- 如果用户要做“或”查询，用 `or` 连接多个词，例如：`api or create or 999`

如果任务没有提供额外代码线索，且项目配置里已经有默认 `project` 和 `default_logstore`，优先使用简写：

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

### 5. 根据项目配置自主选择 logstore

如果任务里带有启动命令、服务配置或任务入口，先对照 `.alilog.json`：

- `./bin/start-web --config ./config/web.yaml` -> 匹配 `logstore_rules[*].command`
- `./bin/start-worker --config ./config/worker-default.yaml` -> 找到对应的 `research-worker-default`
- `./bin/start-consumer --topic orders` -> 找到对应的消费类 logstore

如果任务里带的是代码路径，例如某个 service / worker / handler：

1. 先用代码搜索确认它被哪个运行入口调用。
2. 再把运行入口映射到 `logstore_rules`。
3. 用匹配到的 logstore 去执行后续 `alilog` 命令。
4. 输出时说明推断链路，而不是只报一个结论。

如果本次是 AI 自主选择了 logstore，输出至少包含：

- 结论：本次使用的 logstore 是 `...`
- 依据：对应的启动命令是 `...`
- 配置匹配：`.alilog.json` 中 `logstore_rules` 的 `...`
- 备注：如果存在多个候选，列出候选和差异

## 何时需要补问用户

只有在下面这些情况才补问：

- 当前目录及其上级没有项目级 `.alilog.json`，且用户也没给 `project`
- 项目配置里既没有 `logstore_rules` 可用于归因，也没有 `default_logstore` 可用于兜底，且用户也没给 `logstore`
- 代码或任务能定位到多个运行入口，且现有线索无法区分
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
