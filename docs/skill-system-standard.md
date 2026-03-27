# Skill System Standard

## Summary

`mini-claude-code` uses the standard `SKILL.md` format as the skill artifact.

The compatibility strategy remains:

- baseline: Agent Skills open standard
- compatibility target: Claude Code style extensions
- runtime policy: parse standard fields first and ignore unsupported extensions safely

However, the runtime direction is now explicitly:

- skills are **on-demand**
- skills are **not** the default base runtime mode

## Runtime Model

The intended runtime model is:

### Base Mode

Normal agent usage should work without any skill loaded.

In base mode:

- no skill body is injected
- no skill-specific tool filtering is applied
- the base runtime uses the standard default tool set

### Activated Skill Mode

A skill should be loaded only when explicitly activated by:

- a skill command
- a skill shorthand such as `/skill-name`
- a task with an explicit `skill_profile`

When activated, a skill may affect:

- prompt composition
- visible tools
- future policy hints

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

Planned future user-local layout:

```text
.mini-claude-code/skills/
  my-skill/
    SKILL.md
```

## Required `SKILL.md` Fields

The current implementation requires:

- `name`
- `description`
- `license`
- `compatibility`
- `metadata`
- `allowed-tools`

Rules:

- `name` must match or map stably to the directory name
- `description` should describe both what the skill does and when it should be used
- `allowed-tools` constrains tool visibility while the skill is active

## Optional Claude-Compatible Fields

The runtime may preserve these fields for compatibility:

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

## Activation Expectations

The desired user-facing behavior is:

- no skill loaded by default
- explicit skill activation for ad-hoc CLI work
- explicit skill binding for tasks

This means skill loading should feel temporary and visible, not implicit.

## Recommended Built-In Skills

Current built-in templates:

1. `development-default`
2. `security-audit`

Note:

`development-default` is still useful as a reusable skill template, but it should not define the long-term default runtime model by itself.

## Runtime Integration Rules

When a skill is explicitly activated:

1. resolve the skill by name
2. load and normalize `SKILL.md`
3. append the body content into prompt assembly
4. filter the visible tool registry by `allowed-tools`
5. preserve unknown extension fields for future compatibility

When no skill is activated:

1. run the base runtime
2. do not inject a skill prompt
3. do not apply skill-specific tool filtering

## Testing Requirements

At minimum, tests should cover:

- valid `SKILL.md` parsing
- invalid frontmatter failure paths
- `allowed-tools` filtering while a skill is active
- explicit skill activation behavior
- no-skill base runtime behavior
- missing skill handling
- prompt assembly with an activated skill
