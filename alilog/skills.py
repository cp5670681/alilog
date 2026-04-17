from __future__ import annotations

import os
from importlib.resources import files
from pathlib import Path

from .models import AliLogError

INSTALL_REPO_URL = "git+https://github.com/cp5670681/alilog.git"


def install_ai_skill() -> Path:
    destination = skill_destination()
    content = skill_template()
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        destination.write_text(content, encoding="utf-8")
    except OSError as exc:
        raise AliLogError(f"写入 skill 失败: {destination}") from exc
    return destination


def skill_destination() -> Path:
    claude_home = os.environ.get("CLAUDE_HOME")
    root = Path(claude_home).expanduser() if claude_home else Path.home() / ".claude"
    return root / "skills" / "alilog" / "SKILL.md"


def skill_template() -> str:
    return files("alilog").joinpath("assets/claude-skill/SKILL.md").read_text(
        encoding="utf-8"
    )
