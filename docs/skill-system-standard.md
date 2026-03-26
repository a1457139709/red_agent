# Skill System Standard

## Summary

`mini-claude-code` will build its skill system around the standard `SKILL.md` format.

The project will follow this compatibility strategy:

- baseline: Agent Skills open standard
- compatibility target: Claude Code style extensions
- runtime policy: parse standard fields first, ignore unknown extensions safely

This gives the project a portable skill format without locking the runtime into a vendor-specific schema.

## Directory Layout

Recommended built-in skill layout:

```text
src/skills/
  development-default/
    SKILL.md
    references/
    scripts/
  security-audit/
    SKILL.md
    references/
    scripts/
```

Optional future user-local layout:

```text
.mini-claude-code/skills/
  development-default/
    SKILL.md
```

## Required `SKILL.md` Fields

The first implementation stage must support these frontmatter fields:

- `name`
- `description`
- `license`
- `compatibility`
- `metadata`
- `allowed-tools`

Rules:

- `name` must match or map stably to the directory name
- `description` must describe both what the skill does and when to use it
- `allowed-tools` constrains the visible tool set for that skill

## Optional Claude-Compatible Fields

The runtime may accept these fields for compatibility:

- `argument-hint`
- `disable-model-invocation`
- `user-invocable`
- `model`
- `effort`
- `context`
- `agent`
- `hooks`
- `shell`

These fields are not all required to be active in the first implementation. Unknown or unsupported extensions must not break loading.

## Body Requirements

The `SKILL.md` body is treated as the main prompt fragment for the skill.

It should define:

- when the skill should be used
- goals
- workflow
- output expectations
- safety boundaries
- references to local `references/` or `scripts/`

## Recommended Internal Manifest Shape

The runtime should normalize a loaded skill into an internal manifest with at least:

- `name`
- `description`
- `license`
- `compatibility`
- `allowed_tools`
- `metadata`
- `raw_frontmatter`
- `body`
- `references`
- `scripts`

Recommended compatibility fields to preserve:

- `argument_hint`
- `user_invocable`
- `disable_model_invocation`
- `model`
- `effort`
- `shell`

## Recommended First Built-In Skills

The first built-in templates should be:

1. `development-default`
2. `security-audit`

These should serve as both real runtime skills and scaffolding templates for future skills.

## Example Template

```md
---
name: development-default
description: Help with local development tasks such as reading code, refactoring, and test updates. Use when working on a local repository and you want standard coding assistance.
license: Proprietary
compatibility: Agent Skills baseline with Claude-compatible extensions
allowed-tools:
  - read_file
  - write_file
  - edit_file
  - list_dir
  - search
  - bash
metadata:
  risk_level: low
  category: development
---

# Development Default

## When to use
Use this skill for normal local development work, code reading, refactoring, and test-oriented changes.

## Workflow
1. Read the existing code before editing.
2. Reuse current project patterns.
3. Keep edits minimal and verifiable.
4. Summarize what changed and how it was verified.

## Output
- concise implementation-focused answers
- clear verification notes
- explicit mention of risks or assumptions
```

## Runtime Integration Rules

When a task has `skill_profile` set:

1. resolve the skill by name
2. load and normalize `SKILL.md`
3. append the body content into prompt assembly
4. filter the visible tool registry by `allowed-tools`
5. preserve unknown extension fields for future compatibility

## Testing Requirements

At minimum, tests must cover:

- valid `SKILL.md` parsing
- invalid frontmatter failure paths
- `allowed-tools` filtering
- missing skill fallback behavior
- prompt assembly with a loaded skill
