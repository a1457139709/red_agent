from __future__ import annotations

from pathlib import Path
import re

from models.skill import LoadedSkill, SkillLoadError, SkillManifest


_SCALAR_INT_PATTERN = re.compile(r"^-?\d+$")


def load_skill_from_file(skill_file: Path) -> LoadedSkill:
    if skill_file.name != "SKILL.md":
        raise SkillLoadError(f"Expected SKILL.md, got {skill_file.name}")
    if not skill_file.exists():
        raise SkillLoadError(f"Skill file not found: {skill_file}")

    text = skill_file.read_text(encoding="utf-8")
    frontmatter, body = parse_skill_markdown(text, source=str(skill_file))
    root_dir = skill_file.parent
    references_dir = root_dir / "references"
    scripts_dir = root_dir / "scripts"

    manifest = SkillManifest(
        name=_require_string(frontmatter, "name"),
        description=_require_string(frontmatter, "description"),
        license=_require_string(frontmatter, "license"),
        compatibility=_require_string(frontmatter, "compatibility"),
        allowed_tools=_require_string_list(frontmatter, "allowed-tools"),
        metadata=_require_string_keyed_map(frontmatter, "metadata", required=True),
        raw_frontmatter=dict(frontmatter),
        body=body.strip(),
        references=sorted(path for path in references_dir.iterdir()) if references_dir.exists() else [],
        scripts=sorted(path for path in scripts_dir.iterdir()) if scripts_dir.exists() else [],
        argument_hint=_optional_string(frontmatter, "argument-hint"),
        disable_model_invocation=_optional_bool(frontmatter, "disable-model-invocation"),
        user_invocable=_optional_bool(frontmatter, "user-invocable"),
        model=_optional_string(frontmatter, "model"),
        effort=_optional_string(frontmatter, "effort"),
        shell=_optional_string(frontmatter, "shell"),
        workflow_profile=_resolve_workflow_profile(frontmatter),
    )
    return LoadedSkill(manifest=manifest, root_dir=root_dir, skill_file=skill_file)


def parse_skill_markdown(text: str, *, source: str = "<memory>") -> tuple[dict[str, object], str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise SkillLoadError(f"{source}: SKILL.md must start with a frontmatter block")

    closing_index = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            closing_index = index
            break
    if closing_index is None:
        raise SkillLoadError(f"{source}: SKILL.md frontmatter is missing a closing ---")

    frontmatter_lines = lines[1:closing_index]
    body = "\n".join(lines[closing_index + 1 :]).strip()
    if not body:
        raise SkillLoadError(f"{source}: SKILL.md body is required")

    return _parse_frontmatter(frontmatter_lines, source=source), body


def _parse_frontmatter(lines: list[str], *, source: str) -> dict[str, object]:
    result: dict[str, object] = {}
    index = 0

    while index < len(lines):
        raw_line = lines[index]
        if not raw_line.strip():
            index += 1
            continue
        if raw_line.startswith(" "):
            raise SkillLoadError(f"{source}: Unexpected indentation in frontmatter line: {raw_line}")
        if ":" not in raw_line:
            raise SkillLoadError(f"{source}: Invalid frontmatter entry: {raw_line}")

        key, raw_value = raw_line.split(":", 1)
        key = key.strip()
        value_text = raw_value.strip()

        if not key:
            raise SkillLoadError(f"{source}: Empty frontmatter key")

        if value_text:
            result[key] = _parse_scalar(value_text, source=source, key=key)
            index += 1
            continue

        index += 1
        block_lines: list[str] = []
        while index < len(lines):
            block_line = lines[index]
            if not block_line.strip():
                index += 1
                continue
            if not block_line.startswith("  "):
                break
            block_lines.append(block_line)
            index += 1

        if not block_lines:
            raise SkillLoadError(f"{source}: Frontmatter key '{key}' is missing a value")
        result[key] = _parse_block_value(block_lines, source=source, key=key)

    return result


def _parse_block_value(block_lines: list[str], *, source: str, key: str) -> object:
    first = block_lines[0]
    stripped = first.strip()
    if stripped.startswith("- "):
        values: list[object] = []
        for line in block_lines:
            current = line.strip()
            if not current.startswith("- "):
                raise SkillLoadError(
                    f"{source}: Mixed collection types are not supported for frontmatter key '{key}'"
                )
            values.append(_parse_scalar(current[2:].strip(), source=source, key=key))
        return values

    mapping: dict[str, object] = {}
    for line in block_lines:
        current = line[2:]
        if current.startswith(" "):
            raise SkillLoadError(
                f"{source}: Nested frontmatter structures are not supported for key '{key}'"
            )
        if ":" not in current:
            raise SkillLoadError(f"{source}: Invalid mapping entry under '{key}': {current}")
        child_key, raw_value = current.split(":", 1)
        child_key = child_key.strip()
        value_text = raw_value.strip()
        if not child_key:
            raise SkillLoadError(f"{source}: Empty mapping key under '{key}'")
        if not value_text:
            raise SkillLoadError(
                f"{source}: Nested frontmatter structures are not supported for key '{key}'"
            )
        mapping[child_key] = _parse_scalar(value_text, source=source, key=f"{key}.{child_key}")
    return mapping


def _parse_scalar(value: str, *, source: str, key: str) -> object:
    if not value:
        return ""
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if _SCALAR_INT_PATTERN.match(value):
        return int(value)
    if value.startswith(("{", "[")):
        raise SkillLoadError(
            f"{source}: Unsupported inline structured value for frontmatter key '{key}'"
        )
    return value


def _require_string(frontmatter: dict[str, object], key: str) -> str:
    value = frontmatter.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SkillLoadError(f"Missing or invalid required field: {key}")
    return value.strip()


def _optional_string(frontmatter: dict[str, object], key: str) -> str | None:
    value = frontmatter.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise SkillLoadError(f"Field '{key}' must be a string when present")
    return value


def _optional_bool(frontmatter: dict[str, object], key: str) -> bool | None:
    value = frontmatter.get(key)
    if value is None:
        return None
    if not isinstance(value, bool):
        raise SkillLoadError(f"Field '{key}' must be a boolean when present")
    return value


def _resolve_workflow_profile(frontmatter: dict[str, object]) -> str | None:
    value = _optional_string(frontmatter, "workflow-profile")
    if value is not None:
        normalized = value.strip()
        return normalized or None
    metadata = frontmatter.get("metadata")
    if not isinstance(metadata, dict):
        return None
    for key in ("workflow_profile", "workflow-profile"):
        metadata_value = metadata.get(key)
        if metadata_value is None:
            continue
        if not isinstance(metadata_value, str):
            raise SkillLoadError(f"Field 'metadata.{key}' must be a string when present")
        normalized = metadata_value.strip()
        return normalized or None
    return None


def _require_string_list(frontmatter: dict[str, object], key: str) -> list[str]:
    value = frontmatter.get(key)
    if not isinstance(value, list) or not value:
        raise SkillLoadError(f"Missing or invalid required list field: {key}")
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise SkillLoadError(f"Field '{key}' must be a list of strings")
        normalized.append(item.strip())
    return normalized


def _require_string_keyed_map(
    frontmatter: dict[str, object],
    key: str,
    *,
    required: bool,
) -> dict[str, object]:
    value = frontmatter.get(key)
    if value is None:
        if required:
            raise SkillLoadError(f"Missing required mapping field: {key}")
        return {}
    if not isinstance(value, dict):
        raise SkillLoadError(f"Field '{key}' must be a map")
    normalized: dict[str, object] = {}
    for child_key, child_value in value.items():
        if not isinstance(child_key, str) or not child_key.strip():
            raise SkillLoadError(f"Field '{key}' contains an invalid key")
        normalized[child_key.strip()] = child_value
    return normalized
