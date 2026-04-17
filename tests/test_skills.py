from __future__ import annotations

from pathlib import Path

from alilog.skills import skill_destination, skill_template


def test_claude_skill_template_mentions_install_command() -> None:
    content = skill_template()

    assert "uv tool install git+https://github.com/cp5670681/alilog.git" in content
    assert "alilog context" in content
    assert "disable-model-invocation: true" in content


def test_skill_destination_uses_claude_home(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("CLAUDE_HOME", str(tmp_path / "custom-claude"))

    path = skill_destination()

    assert path == tmp_path / "custom-claude" / "skills" / "alilog" / "SKILL.md"
