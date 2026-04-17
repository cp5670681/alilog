# alilog

English | [简体中文](README.zh-CN.md)

`alilog` is an unofficial command-line tool for querying Alibaba Cloud SLS console logs and retrieving log context around a selected record.

Status: experimental

## Why This Project Exists

This project keeps a narrow CLI surface for two common workflows:

- `search`: query logs from an SLS project/logstore
- `context`: fetch previous and next logs from a `search` result

## Safety Notes

- This tool depends on an Alibaba Cloud Console login session.
- Authentication is based on browser cookies, so it is intended for local, trusted machines only.
- The project is not affiliated with Alibaba Cloud.
- Console APIs may change without notice.

## Requirements

- Python 3.10+
- `uv` for local development and installation in the examples below

## Install

Run directly from the repository:

```bash
uv sync
uv run alilog --help
```

Install as a user-level command from a local checkout:

```bash
uv tool install .
alilog --help
```

## Authentication

The CLI reads credentials from:

```text
~/.alilog.json
```

The repository-level defaults are read from the nearest project-root `.alilog.json` found by walking upward from the current working directory. This file is intended for non-secret defaults such as:

```json
{
  "project": "k8s-log-c19af6eaf83e44c28a7eb544564eee247",
  "default_logstore": "research",
  "logstores": ["research", "research-sidekiq-default"]
}
```

Save a browser cookie:

```bash
uv run alilog auth save \
  --cookie 'aliyun_lang=zh; ...'
```

If you also captured `x-csrf-token`, save it together with the cookie:

```bash
uv run alilog auth save \
  --cookie 'aliyun_lang=zh; ...' \
  --csrf-token 'f11fea43'
```

Clear the local auth file:

```bash
uv run alilog auth clear
```

## Search Logs

`search` accepts:

- Unix timestamps in 10-digit seconds or 13-digit milliseconds
- ISO timestamps
- `YYYY-MM-DD HH:MM[:SS]`
- relative windows via `--last`

The query automatically appends `with_pack_meta`, so the output can be passed into `context`.

If the current project already has `.alilog.json`, `--project` and `--logstore` are optional:

```bash
uv run alilog search \
  --from '2026-04-16 23:06:00' \
  --to '2026-04-16 23:21:00' \
  --query 'error'
```

You can still override them explicitly when needed:

```bash
uv run alilog search \
  --project k8s-log-c19af6eaf83e44c28a7eb544564eee247 \
  --logstore research \
  --from '2026-04-16 23:06:00' \
  --to '2026-04-16 23:21:00' \
  --query 'error'
```

Relative window example:

```bash
uv run alilog search \
  --project k8s-log-c19af6eaf83e44c28a7eb544564eee247 \
  --logstore research \
  --to '2026-04-16 23:21:00' \
  --last 15m \
  --query 'error'
```

## Fetch Context

`context` uses `pack_id` and `pack_meta` from `search` output and fetches both previous and next logs by default.

If your project root already has `.alilog.json`, `--project` and `--logstore` can be omitted. The fully explicit form is:

```bash
uv run alilog context \
  --project k8s-log-c19af6eaf83e44c28a7eb544564eee247 \
  --logstore research \
  --pack-id EBA5D6B0CB95EA56-F3 \
  --pack-meta '1|MTc2ODA0MTQzNjk1MDUwNzQwMQ==|54|6'
```

## Development

Install dependencies:

```bash
uv sync --group dev
```

Run tests:

```bash
uv run pytest -q
```

Run lint:

```bash
uv run ruff check .
```

Run type checks:

```bash
uv run mypy
```

CI runs Ruff, mypy, and the test suite on Python 3.10, 3.11, 3.12, and 3.13.

## AI Skill Setup

This project supports Claude Code skills.

After installing `alilog`, install the Claude skill with:

```bash
alilog install-skill
```

If you want a single setup flow from GitHub on a new machine:

```bash
uv tool install git+https://github.com/cp5670681/alilog.git
alilog install-skill
```

This writes the skill to `~/.claude/skills/alilog/SKILL.md`, which matches the Claude Code skills layout described in the official docs.

Manual copy is also supported:

- Copy `alilog/assets/claude-skill/SKILL.md` to `~/.claude/skills/alilog/SKILL.md`

The skill file itself includes instructions for installing `alilog` if the CLI is missing.

## License

MIT. See [LICENSE](LICENSE).
