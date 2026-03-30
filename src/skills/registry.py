from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from models.skill import LoadedSkill, SkillLoadError
from .loader import load_skill_from_file


class SkillRegistry:
    def __init__(
        self,
        roots: list[tuple[str, Path]] | Path,
        *,
        known_tool_names: set[str],
    ) -> None:
        if isinstance(roots, Path):
            self.roots = [("custom", roots)]
        else:
            self.roots = list(roots)
        self.known_tool_names = set(known_tool_names)
        self._cache: dict[str, LoadedSkill] | None = None

    @classmethod
    def built_in(cls, *, known_tool_names: set[str]) -> "SkillRegistry":
        return cls(
            [("built-in", Path(__file__).resolve().parent)],
            known_tool_names=known_tool_names,
        )

    @classmethod
    def built_in_and_local(
        cls,
        *,
        known_tool_names: set[str],
        local_root: Path,
    ) -> "SkillRegistry":
        return cls(
            [
                ("built-in", Path(__file__).resolve().parent),
                ("local", local_root),
            ],
            known_tool_names=known_tool_names,
        )

    def reload(self) -> None:
        self._cache = None

    def list_skills(self) -> list[LoadedSkill]:
        return [self._load_all()[name] for name in sorted(self._load_all())]

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
        for source, root_dir in self.roots:
            if not root_dir.exists():
                continue

            for entry in sorted(root_dir.iterdir()):
                if not entry.is_dir():
                    continue
                skill_file = entry / "SKILL.md"
                if not skill_file.exists():
                    continue

                loaded = self._load_skill(entry, skill_file, source=source)
                skills[loaded.manifest.name] = loaded

        self._cache = skills
        return self._cache

    def _load_skill(self, entry: Path, skill_file: Path, *, source: str) -> LoadedSkill:
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
        return replace(loaded, source=source)
