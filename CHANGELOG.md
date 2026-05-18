# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.6.0] - 2026-05-18

### Removed

- settings.json 配置文件支持
- 默认 project 和 logstore 配置回退
- --project 和 --logstore 现为必需参数

## [0.5.1] - 2026-05-01

### Changed

- `auth login` now refreshes authentication with saved RAM credentials before falling back to the manual browser login flow

## [0.5.0] - 2026-05-01

### Added

- RAM password credential refresh using Playwright and TOTP seed
- Credential-based re-authentication and one retry for `search` and `context` when a session expires
- `auth save` options for storing RAM login credentials
- Tests covering credential refresh, re-authentication, and credential persistence

### Changed

- Moved runtime configuration into `~/.alilog/`
- Renamed the auth file from `~/.alilog.json` to `~/.alilog/auth.json`
- Replaced project-root `.alilog.json` discovery with `~/.alilog/settings.json`
- Simplified the default project config shape to `default_project` and `default_logstore`
- Documented local credential storage risks in both README files
- Added `mintotp` and `playwright` runtime dependencies

### Removed

- `install-skill` command and `skills` module (skill is now managed separately)
- Claude Code skill asset at `alilog/assets/claude-skill/SKILL.md`
- AI Skill setup documentation from README files

## [0.3.1] - 2026-04-20

### Added

- Project-level `logstore_rules` metadata for describing which runtime entrypoint maps to which logstore

### Changed

- Project config parsing now reads structured `logstore_rules` entries alongside `default_logstore`
- Claude skill guidance now tells AI agents to prefer project-level `logstore_rules` when choosing a logstore and falls back to `default_logstore` only when no stronger runtime clue is available
- README examples now show the `logstore_rules` structure in both English and Chinese documentation

## [0.3.0] - 2026-04-19

### Added

- `auth login` command for browser authentication via Chrome DevTools Protocol (CDP)
  - Extracts cookies and CSRF token from an already logged-in browser
  - Supports Chrome, Edge, and other Chromium-based browsers
  - Interactive confirmation before saving credentials
- `websocket-client` dependency for CDP communication

### Changed

- Time parsing now supports 13-digit millisecond timestamps (e.g., `1776352860000`)
- README restructured with separate English (`README.en.md`) and Chinese (`README.md`) versions

## [0.2.0] - 2026-04-17

### Added

- Claude Code skill template at `alilog/assets/claude-skill/SKILL.md`
- `install-skill` command for installing the bundled Claude Code skill into `~/.claude/skills/alilog/SKILL.md`
- Packaged skill asset distribution via `setuptools` package data
- Project-level `.alilog.json` defaults for `project`, `default_logstore`, and `logstores`
- Documentation for skill installation and project-level defaults in both English and Chinese READMEs
- Tests covering skill installation and project config driven CLI behavior

### Fixed

- Explicit `--project` and `--logstore` arguments now bypass invalid project config files instead of failing early
- `auth save` and `auth clear` no longer depend on project config parsing
- `context` README examples now show a safe explicit invocation and document when defaults may be omitted

## [0.1.0] - 2026-04-17

### Added

- `search` command for querying logs from Alibaba Cloud SLS
  - Support for multiple time formats: Unix timestamp, ISO, `YYYY-MM-DD HH:MM[:SS]`, `now`
  - Relative time window via `--last` option (e.g., `15m`, `2h`, `1d`)
  - Automatic `with_pack_meta` append for context compatibility
  - Pagination via `--page` and `--size` options
- `context` command for fetching log context around a selected record
  - Fetches both previous and next logs by default
  - Uses `pack_id` and `pack_meta` from search output
- `auth save` subcommand for storing browser cookies
  - Optional CSRF token storage
  - Atomic file write with secure permissions (`0600`)
- `auth clear` subcommand for removing stored credentials
- Dual-language documentation (English and Chinese)
- CI pipeline with Ruff, mypy, and pytest on Python 3.10-3.13
