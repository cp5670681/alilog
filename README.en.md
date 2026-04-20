# alilog

English | [简体中文](README.md)

`alilog` is an unofficial command-line tool for querying Alibaba Cloud SLS console logs and retrieving log context around a selected record.

## Why This Project Exists

This project keeps a narrow CLI surface for two common workflows:

- `search`: query logs from an SLS project/logstore
- `context`: fetch previous and next logs from a `search` result

## Safety Notes

- This tool depends on an Alibaba Cloud Console login session.
- Authentication is based on browser cookies, so it is intended for local, trusted machines only.

## Requirements

- Python 3.10+
- `uv` for local development and installation in the examples below

## Install

Install as a user-level command from GitHub:

```bash
uv tool install git+https://github.com/cp5670681/alilog.git
alilog --help
```

## Login

```bash
alilog auth login
```

If auto-detection cannot find Chrome/Chromium/Edge, provide the browser executable path explicitly:

```bash
alilog auth login \
  --browser '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
```

Or manually save the cookie and csrf-token (can be obtained via packet capture):

```bash
alilog auth save \
  --cookie 'aliyun_lang=zh; ...' \
  --csrf-token 'xxxxxxxx'
```

# Project-level Configuration

Project-level configuration is read from the nearest project-root `.alilog.json` found by walking upward from the current working directory.

```json
{
  "project": "k8s-log-c19af6eaf83e44c28a7eb544564eee247",
  "default_logstore": "research",
  "logstore_rules": [
    {
      "logstore": "research",
      "command": "./bin/start-web --config ./config/web.yaml",
      "description": "Primary web service"
    },
    {
      "logstore": "research-worker-default",
      "command": "./bin/start-worker --config ./config/worker-default.yaml",
      "description": "Default background jobs"
    }
  ]
}
```

`default_logstore` is still used as the CLI fallback. `logstore_rules` documents which runtime entrypoint or code path maps to which logstore.

## Search Logs

`search` accepts:

- Unix timestamps (10-digit seconds)
- ISO timestamps
- `YYYY-MM-DD HH:MM[:SS]`
- relative windows via `--last`

If the current project already has `.alilog.json`, `--project` and `--logstore` are optional:

```bash
alilog search \
  --from '2026-04-16 23:06:00' \
  --to '2026-04-16 23:21:00' \
  --query 'error'
```

You can still override them explicitly when needed:

```bash
alilog search \
  --project k8s-log-c19af6eaf83e44c28a7eb544564eee247 \
  --logstore research \
  --from '2026-04-16 23:06:00' \
  --to '2026-04-16 23:21:00' \
  --query 'error'
```

Relative window example:

```bash
alilog search \
  --project k8s-log-c19af6eaf83e44c28a7eb544564eee247 \
  --logstore research \
  --last 15m \
  --query 'error'
```

## Fetch Context

`context` uses `pack_id` and `pack_meta` from `search` output and fetches both previous and next logs by default.

Similarly, if your project root already has `.alilog.json`, `--project` and `--logstore` can be omitted. The full form is:

```bash
alilog context \
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

This writes the skill to `~/.claude/skills/alilog/SKILL.md`.

Manual copy is also supported:

- Copy `alilog/assets/claude-skill/SKILL.md` to `~/.claude/skills/alilog/SKILL.md`

The skill file itself includes instructions for installing `alilog` if the CLI is missing.

## License

MIT. See [LICENSE](LICENSE).
