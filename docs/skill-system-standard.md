# Skill System Standard

## Summary

`red-code` uses the standard `SKILL.md` format as the skill artifact.

The compatibility strategy remains:

- baseline: Agent Skills open standard
- compatibility target: Claude Code style extensions
- runtime policy: parse standard fields first and ignore unsupported extensions safely

The current runtime direction is:

- skills are **on-demand**
- skills are **not** the default base runtime mode
- skills may be loaded from built-in and user-local directories

## Runtime Model

### Base Mode

Normal agent usage works without any skill loaded.

In base mode:

- no skill body is injected
- no skill-specific tool filtering is applied
- the base runtime uses the standard built-in tool set
- the base safety policy is used

### Activated Skill Mode

A skill is loaded only when explicitly activated by:

- a skill command
- a skill shorthand such as `/skill-name`
- a task with an explicit `skill_profile`

When activated, a skill may affect:

- prompt composition
- visible tools
- runtime safety narrowing

## Directory Layout

Built-in skill layout:

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

User-local layout:

```text
.red-code/skills/
  my-skill/
    SKILL.md
```

## Discovery and Precedence

Current discovery behavior:

- built-in skills are loaded from `src/skills/*/SKILL.md`
- local skills are loaded from `.red-code/skills/*/SKILL.md`
- only direct child directories containing `SKILL.md` are considered skills

Current precedence rule:

- built-in skills are loaded first
- local skills are loaded second
- if both define the same skill name, the local skill overrides the built-in one

Current reload behavior:

- `/skill reload` clears the in-memory skill registry cache
- the next skill lookup rescans disk
- if the current active shell skill disappears after reload, the shell clears it

## Required `SKILL.md` Fields

The current implementation requires:

- `name`
- `description`
- `license`
- `compatibility`
- `metadata`
- `allowed-tools`

Rules:

- `name` must match the directory name
- `description` should describe both what the skill does and when it should be used
- `allowed-tools` constrains visible tools while the skill is active

## Optional Claude-Compatible Fields

The runtime preserves these fields for compatibility when present:

- `argument-hint`
- `disable-model-invocation`
- `user-invocable`
- `model`
- `effort`
- `context`
- `agent`
- `hooks`
- `shell`

These fields are not all active yet.

## Body Requirements

The `SKILL.md` body is the prompt fragment for the skill.

It should define:

- what the skill is for
- when to use it
- workflow
- output expectations
- safety boundaries
- references to local `references/` or `scripts/`

## Current Internal Manifest Shape

The runtime normalizes a loaded skill into an internal manifest with at least:

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

And the loaded skill also carries:

- `root_dir`
- `skill_file`
- `source`

Supported `source` values currently include:

- `built-in`
- `local`

## Safety Rules

Current safety integration rules:

- skill tool visibility is constrained by `allowed-tools`
- the effective runtime safety policy is narrowed from the visible tools
- skills may tighten permissions relative to base mode
- skills do not expand permissions beyond base mode

This means a read-heavy skill such as `security-audit` can reduce available capabilities without bypassing the executor’s policy boundary.

## Activation Expectations

The current user-facing behavior is:

- no skill loaded by default
- explicit skill activation for ad-hoc CLI work
- explicit skill binding for tasks
- explicit reload of built-in plus local skill views

Supported interaction patterns:

- `/skill list`
- `/skill show <name>`
- `/skill use <name>`
- `/skill clear`
- `/skill current`
- `/skill reload`
- `/skill-name <prompt>`

## Runtime Integration Rules

When a skill is explicitly activated:

1. resolve the skill by name
2. load and normalize `SKILL.md`
3. append the body content into prompt assembly
4. filter the visible tool registry by `allowed-tools`
5. derive the narrowed safety policy from the visible tools
6. preserve unknown extension fields for future compatibility

When no skill is activated:

1. run the base runtime
2. do not inject a skill prompt
3. do not apply skill-specific tool filtering
4. use the base safety policy

## Testing Requirements

At minimum, tests should cover:

- valid `SKILL.md` parsing
- invalid frontmatter failure paths
- built-in skill discovery
- local skill discovery
- local override of built-in skills
- reload behavior
- `allowed-tools` filtering while a skill is active
- explicit skill activation behavior
- no-skill base runtime behavior
- missing skill handling
- prompt assembly with an activated skill
