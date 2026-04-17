# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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