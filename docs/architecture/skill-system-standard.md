# RETIRED DOCUMENT

# Skill System Standard

## Summary

`red-code` uses the standard `SKILL.md` format for legacy prompt-assist skill artifacts.
Phase 5 executable modules use `capability.json` instead of extending
`SKILL.md` frontmatter into the target module contract.

### Target Architecture Warning

This document describes the **current** skill runtime. It is not the target contract for the session-centric refactor.

The current `SKILL.md` design only partially matches the target architecture. It can inform low-level reuse, but Phase 5 must not continue by copying the current design directly.

Reusable ideas:

- local skill description files
- `allowed-tools` narrowing
- `references/` and `scripts/` directories

Do not treat these as the target Phase 5 design:

- slash-command-first skill activation
- task-bound skill profiles
- operation-id-based workflow skills
- prompt-body-only red-team module semantics
- `/skill plan <name> <operation_id>` and `/skill apply <name> <operation_id>` as the main red-team workflow

The target architecture now uses a unified `capability.json` skill/module contract with parameters, risk metadata, execution style, session integration, and execution-service routing.

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
  git-auto-commit/
    SKILL.md
    references/
    scripts/
  security-audit/
    SKILL.md
    references/
    scripts/
  weather-query-example/
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

The runtime currently parses and preserves these optional fields when present:

- `argument-hint`
- `disable-model-invocation`
- `user-invocable`
- `model`
- `effort`
- `shell`

These fields are part of the normalized manifest shape.
`model`, `effort`, `user-invocable`, `disable-model-invocation`, and `shell` now affect runtime behavior.
When a skill declares `shell`, the `bash` tool launches that shell explicitly instead of falling back to the host default command shell.

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

This means a read-heavy skill such as `security-audit` can reduce available capabilities without bypassing the executor鈥檚 policy boundary.

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

Phase 5 module interaction patterns:

- `/module list`
- `/module show <name>`
- `/module run <name> <target> [json_overrides]`

Current built-in prompt-assist skills include:

- `development-default`
- `git-auto-commit`
- `security-audit`
- `surface-recon`
- `web-enum`
- `weather-query-example`

`surface-recon` and `web-enum` also have Phase 5 module manifests under
`src/capabilities/`. Their legacy `SKILL.md` files are migration/debug prompt
bridges and should not be used as the target module runtime contract.

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

# RETIRED DOCUMENT

This document describes the removed `SKILL.md` runtime and is retained only for migration history.
The current runtime uses capability directories under `src/capabilities/` and `.red-code/capabilities/`,
with `capability.json` for metadata and `prompt.md` for prompt-assist skill bodies.

Do not use this document as the current runtime contract.
