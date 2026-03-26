# Engineering Development Plan

## 1. Purpose

This document is the internal engineering blueprint for the continued development of `mini-claude-code`.

It is not a high-level project introduction. Its purpose is to define:

- what the project should evolve toward
- which capabilities should be built next
- which skill standard the project should adopt
- which architectural boundaries must remain intact
- what the next implementation entry point should be

This document is written for future implementation work in this repository.

## 2. Product Scope and Constraints

### 2.1 Current Target

The current target is:

- local single-user usage
- development assistance as the primary use case
- support for medium and long-running tasks
- gradual introduction of a skill system
- future addition of cybersecurity-oriented skills
- strong emphasis on local control, safety, and maintainability

### 2.2 Non-Goals

The following are not current goals:

- multi-tenancy
- SaaS deployment
- web control panels
- organization-level permission models
- distributed scheduling
- complex cloud infrastructure

Conclusion:

The project should continue evolving from the current codebase rather than being rewritten from scratch. However, future work must be done as structured engineering work, not as ad hoc feature accumulation.

## 3. Current Foundation

The current codebase already has enough structure to support continued growth:

- a working local CLI interaction loop
- centralized `Settings`
- centralized `SessionState`
- a controlled `ToolExecutor`
- explicit tool assembly
- persisted `Task`, `Run`, `Checkpoint`, and task logs
- baseline regression tests

Because of this, the next stage is no longer “build a minimal agent prototype.” The next stage is “standardize the skill system and integrate it into the existing task runtime.”

## 4. Guiding Principles

### 4.1 Local-First

Every design decision should optimize for local single-machine usage.

This means:

- prefer local files and SQLite
- prefer local directory conventions over service-heavy infrastructure
- prefer local skill discovery over remote registries

### 4.2 Keep the Core Runtime Small

The runtime core should remain stable and focused.

The core should own:

- session state
- task state
- prompt assembly
- tool execution
- task orchestration
- safety policy

Complex domain behavior should be introduced through skills, not by overloading `agent_loop`.

### 4.3 All Side Effects Must Go Through a Controlled Layer

Any capability that changes files, executes commands, or touches the network must go through a unified execution boundary.

This implies:

- skills must not bypass `ToolExecutor`
- skills must not define an independent permission model
- skills may influence tool availability and prompt composition, but not break the runtime boundary

### 4.4 Long-Running Tasks Must Remain Recoverable

The existing task runtime already supports resumability. Skills must not break:

- interruption recovery
- retry after failure
- checkpoint restore
- task/run log traceability

### 4.5 Skill Standard Before Private Format

The project should not invent a private skill format first and migrate later.

The project will standardize on:

- `SKILL.md` as the primary skill artifact
- the Agent Skills open standard as the baseline
- Claude Code extensions as optional compatibility fields
- forward-compatible parsing that ignores unknown extensions

## 5. Standardized Skill Strategy

### 5.1 Adopted Standard

The project will use a `SKILL.md`-based skill system.

The design direction is informed by:

- the Agent Skills open standard
- the Claude Code skills ecosystem

Engineering decisions:

1. `SKILL.md` is the only required entry file
2. a skill directory may also contain `scripts/`, `references/`, and `assets/`
3. the runtime first parses standard fields, then optional compatibility extensions
4. skill definitions must not be hard-coded as Python-only manifests

### 5.2 Standard Directory Shape

Recommended built-in skill structure:

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

The runtime should also be able to support a future user-local skill directory such as:

```text
.mini-claude-code/skills/
  development-default/
    SKILL.md
```

### 5.3 Required Standard Fields

The first implementation stage must support at least:

- `name`
- `description`
- `license`
- `compatibility`
- `metadata`
- `allowed-tools`

Rules:

- `name` must match or map stably to the skill directory name
- `description` must explain both what the skill does and when it should be used
- `allowed-tools` constrains tool visibility for that skill

### 5.4 Claude Code Compatibility Extensions

The runtime should allow, but not require, the following fields:

- `argument-hint`
- `disable-model-invocation`
- `user-invocable`
- `model`
- `effort`
- `context`
- `agent`
- `hooks`
- `shell`

Strategy:

- keep parsing support
- only consume the fields actually needed in the first runtime slice
- retain unhandled fields in raw metadata or a compatibility layer

### 5.5 Role of the `SKILL.md` Body

The body of `SKILL.md` is not decorative documentation. It is the primary prompt fragment source for the skill.

The body should describe:

- when to use the skill
- goals
- workflow
- output expectations
- safety boundaries
- references to `references/` and `scripts/`

## 6. Target Architecture Direction

The codebase should gradually move toward this shape:

```text
src/
  main.py
  app/
    task_service.py
    run_service.py
    skill_service.py
  agent/
    loop.py
    context.py
    prompt.py
    provider.py
    settings.py
    state.py
  runtime/
    task_runner.py
    policies.py
  skills/
    loader.py
    registry.py
    manifest.py
    development-default/
      SKILL.md
    security-audit/
      SKILL.md
  storage/
    sqlite.py
    tasks.py
    runs.py
  models/
    task.py
    run.py
    skill.py
  tools/
    executor.py
  utils/
```

Notes:

- `src/skills/` will contain both runtime support code and built-in skills
- the runtime should support both built-in and user-local skill sources

## 7. Capability Roadmap

### Phase 1: Minimal Long-Running Task Support

This phase is now largely in place:

- `Task`
- `Run`
- `Checkpoint`
- task logs
- `/task create|list|show|logs|resume|detach|complete`

Only incremental refinement remains here.

### Phase 2: Standardized Skill System

#### Goal

Represent development, security, and future domain behaviors as standard `SKILL.md` skills instead of private prompt packs or hard-coded manifests.

#### Required Work

1. define an internal `SkillManifest` model
2. implement `SKILL.md` frontmatter parsing
3. implement skill directory discovery and registration
4. make `Task.skill_profile` actually drive skill loading
5. let skills affect prompt composition
6. let skills affect the available tool set
7. ship at least two built-in templates:
   - `development-default`
   - `security-audit`

#### Not Required in the First Slice

- complex hook execution
- multi-agent skill collaboration
- online skill marketplaces
- remote dependency resolution

#### Definition of Done

- skills can be loaded from standard directories
- standard frontmatter fields are supported
- `Task.skill_profile` can bind a skill
- different skills affect prompt assembly and tool visibility
- unknown extension fields do not break loading
- built-in templates serve as scaffolding for future skills

### Phase 3: Stronger Execution Safety

Required work:

- tool permission levels
- workspace allowlists
- command allowlists and denylists
- stronger confirmation policies for risky operations
- task/run-level audit logging

Rule:

Security skills must not expand faster than execution controls.

### Phase 4: Persistence and Recovery Enhancements

Suggested persisted entities:

- Tasks
- Runs
- Checkpoints
- Task logs
- skill selection metadata
- skill resolution snapshots

The skill source of truth should still remain file-based whenever possible.

### Phase 5: Observability and Debugging

At minimum, logs should include:

- `task_id`
- `run_id`
- `skill_name`
- `tool_name`
- `duration_ms`
- `status`
- `error_type`

### Phase 6: Cybersecurity Skill Introduction

Recommended order:

1. information gathering
2. local config and dependency audit
3. semi-automated verification

Hard rule:

Do not add high-risk scanning or offensive behavior before stronger permissions and audit controls exist.

## 8. Skill Data Model Guidance

The internal `SkillManifest` should stabilize around at least:

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

Recommended compatibility fields to retain:

- `argument_hint`
- `user_invocable`
- `disable_model_invocation`
- `model`
- `effort`
- `shell`

## 9. Testing Strategy

### 9.1 Skill Loader Tests

Cover:

- valid `SKILL.md` parsing
- failure for missing `name` or `description`
- `allowed-tools` parsing
- compatibility with unknown extension fields
- discovery of `references/` and `scripts/`

### 9.2 Runtime Tests

Cover:

- prompt assembly with a bound skill
- tool filtering with a bound skill
- fallback behavior for missing skills
- failure handling for malformed or hostile skill files

### 9.3 Regression Rule

Every new skill-related capability must ship with loader and runtime regression coverage.

## 10. Documentation Policy

Rules:

1. update `docs/` whenever skill structure changes
2. update the documentation index when built-in skills are added
3. update this plan whenever the skill standard or compatibility strategy changes
4. explicitly distinguish current standard behavior from future optional extensions

## 11. Delivery Priority

### Priority 1

- standard `SKILL.md` loader
- skill registry
- runtime integration for `Task.skill_profile`
- prompt and tool filtering via skills

### Priority 2

- built-in `development-default` template
- built-in `security-audit` template
- compatibility extension handling

### Priority 3

- stronger tool permissions and safety policies
- minimal safe cybersecurity skill set

### Priority 4

- stronger observability
- skill import and installation workflows

## 12. Definition of Done for Any Phase

Every phase must satisfy at least:

1. a clear code entry point exists
2. regression tests are included
3. documentation is updated
4. failure paths are handled explicitly
5. the current CLI development workflow is not broken

## 13. Immediate Next Development Entry Point

The most practical next implementation step is:

1. create `src/models/skill.py`
2. create `src/skills/loader.py`
3. create `src/skills/registry.py`
4. create `src/app/skill_service.py`
5. integrate `Task.skill_profile` into `TaskRunner`, prompt assembly, and tool filtering
6. add two built-in standard skills:
   - `src/skills/development-default/SKILL.md`
   - `src/skills/security-audit/SKILL.md`

Why this is next:

- the Phase 1 task substrate already exists
- the skill system is the clean extension point for future development and security capabilities
- adopting standard `SKILL.md` now avoids lock-in to a private format
- it creates a durable base for future cybersecurity skills and external skill import
