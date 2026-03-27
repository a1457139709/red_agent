from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class SkillLoadError(ValueError):
    """Raised when a SKILL.md file cannot be parsed or normalized."""


@dataclass(slots=True)
class SkillManifest:
    name: str
    description: str
    license: str
    compatibility: str
    allowed_tools: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)
    raw_frontmatter: dict[str, Any] = field(default_factory=dict)
    body: str = ""
    references: list[Path] = field(default_factory=list)
    scripts: list[Path] = field(default_factory=list)
    argument_hint: str | None = None
    disable_model_invocation: bool | None = None
    user_invocable: bool | None = None
    model: str | None = None
    effort: str | None = None
    shell: str | None = None


@dataclass(slots=True)
class LoadedSkill:
    manifest: SkillManifest
    root_dir: Path
    skill_file: Path
