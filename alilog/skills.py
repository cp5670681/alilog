"""
Claude Skill 安装模块。

本模块负责将 alilog 的 Claude skill 安装到 Claude 的 skills 目录，
使 Claude 能够使用 alilog 的功能进行日志查询。

Skill 文件位于 alilog/assets/claude-skill/SKILL.md。
"""

from __future__ import annotations

import os
from importlib.resources import files
from pathlib import Path

from .models import AliLogError

INSTALL_REPO_URL = "git+https://github.com/cp5670681/alilog.git"


def install_ai_skill() -> Path:
    """安装 Claude skill。

    将内置的 skill 模板复制到 Claude 的 skills 目录。

    Returns:
        安装的 skill 文件路径

    Raises:
        AliLogError: 写入文件失败时抛出
    """
    destination = skill_destination()
    content = skill_template()
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        destination.write_text(content, encoding="utf-8")
    except OSError as exc:
        raise AliLogError(f"写入 skill 失败: {destination}") from exc
    return destination


def skill_destination() -> Path:
    """获取 skill 安装目标路径。

    目标路径为 ~/.claude/skills/alilog/SKILL.md，
    可通过 CLAUDE_HOME 环境变量自定义 Claude 主目录。

    Returns:
        skill 文件的目标路径
    """
    claude_home = os.environ.get("CLAUDE_HOME")
    root = Path(claude_home).expanduser() if claude_home else Path.home() / ".claude"
    return root / "skills" / "alilog" / "SKILL.md"


def skill_template() -> str:
    """读取 skill 模板内容。

    从包资源中读取内置的 skill 模板文件。

    Returns:
        skill 模板的文本内容
    """
    return files("alilog").joinpath("assets/claude-skill/SKILL.md").read_text(
        encoding="utf-8"
    )
