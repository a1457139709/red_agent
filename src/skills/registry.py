from __future__ import annotations

from pathlib import Path

from models.skill import LoadedSkill, SkillLoadError
from .loader import load_skill_from_file


class SkillRegistry:
    def __init__(self, root_dir: Path, *, known_tool_names: set[str]) -> None:
        self.root_dir = root_dir
        self.known_tool_names = set(known_tool_names)
        self._cache: dict[str, LoadedSkill] | None = None

    @classmethod
    def built_in(cls, *, known_tool_names: set[str]) -> "SkillRegistry":
        return cls(Path(__file__).resolve().parent, known_tool_names=known_tool_names)

    def list_skills(self) -> list[LoadedSkill]:
        return list(self._load_all().values())

    def get_skill(self, name: str) -> LoadedSkill | None:
        return self._load_all().get(name)

    def require_skill(self, name: str) -> LoadedSkill:
        skill = self.get_skill(name)
        if skill is None:
            raise SkillLoadError(f"Skill not found: {name}")
        return skill

    def _load_all(self) -> dict[str, LoadedSkill]:
        if self._cache is not None:
            return self._cache

        skills: dict[str, LoadedSkill] = {}
        if not self.root_dir.exists():
            self._cache = {}
            return self._cache

        for entry in sorted(self.root_dir.iterdir()):
            if not entry.is_dir():
                continue
            skill_file = entry / "SKILL.md"
            if not skill_file.exists():
                continue

            loaded = load_skill_from_file(skill_file)
            if loaded.manifest.name != entry.name:
                raise SkillLoadError(
                    f"Skill name '{loaded.manifest.name}' does not match directory '{entry.name}'"
                )
            unknown_tools = sorted(
                tool_name
                for tool_name in loaded.manifest.allowed_tools
                if tool_name not in self.known_tool_names
            )
            if unknown_tools:
                raise SkillLoadError(
                    f"Skill '{loaded.manifest.name}' declares unknown tools: {', '.join(unknown_tools)}"
                )
            skills[loaded.manifest.name] = loaded

        self._cache = skills
        return self._cache
