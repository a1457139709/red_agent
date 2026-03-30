# Engineering Development Plan

## Purpose

This document is the working roadmap for the current repository state.

It should stay aligned with the actual Python codebase and answer:

- what is already implemented
- what architectural rules now hold
- what the next development phase should be

## Current Product Direction

`mini-claude-code` is a local single-user coding agent focused on:

- interactive CLI usage
- resumable local task execution
- explicit on-demand skills
- local-first persistence
- controlled local tool execution

It is still not aiming for:

- SaaS deployment
- multi-user collaboration
- distributed orchestration
- heavy web-platform architecture

## Current Baseline

Already implemented:

- local interactive CLI shell
- persisted `Task`, `Run`, `Checkpoint`, and task logs
- resumable task runtime with public task IDs
- explicit skill activation
- one-shot skill shorthand such as `/security-audit ...`
- built-in and user-local `SKILL.md` loading
- local skill reload from disk
- runtime skill-aware prompt composition
- runtime skill-aware visible tool filtering
- capability-tier execution safety:
  - `read`
  - `write`
  - `execute`
  - `destructive`
- risk-focused safety audit logging for task runs

Built-in skills currently include:

- `development-default`
- `security-audit`

User-local skills are now supported under:

- `.mini-claude-code/skills/<skill-name>/SKILL.md`

## Stable Architectural Rules

### 1. Base Runtime First

Normal ad-hoc chat runs in base mode:

- no implicit skill prompt
- no implicit skill-specific tool filtering
- full built-in tool set

Skills are explicit overlays, not the default runtime identity.

### 2. Skills May Tighten, Not Bypass

Skills may influence:

- prompt composition
- visible tools
- runtime safety narrowing

Skills must not:

- bypass `ToolExecutor`
- create hidden execution paths
- expand permissions beyond base runtime

### 3. Local-First Persistence

Prefer:

- SQLite for structured runtime state
- local files for skills and prompts
- CLI-first workflows

### 4. Recoverable Task Runtime

Future work must preserve:

- pause/resume
- checkpoint restore
- task/run logs
- explicit failure tracking

## Phase Status

### Completed

#### Phase 1: Minimal Long-Running Task Support

Completed:

- task persistence
- run persistence
- checkpoints
- task logs
- resume/detach/complete flow

#### Phase 2: Skill System Foundation

Completed:

- standard `SKILL.md` parsing
- built-in skill discovery
- explicit skill activation
- task-bound optional skills
- base runtime with no implicit skill

#### Phase 3: Execution Safety Hardening

Completed:

- capability-tier tool model
- runtime safety policies
- skill-driven policy tightening
- shell danger checks integrated into unified executor flow
- task-scoped safety audit logs

## Next Phase

### Phase 4: Observability and Richer Diagnostics

This should be the next implementation focus.

Required work:

- record run duration
- record effective skill used for each run
- record effective visible tools for each run
- add structured failure classification
- add higher-signal tool invocation events
- improve task/run inspection commands

Recommended CLI additions:

- `/task runs <task_id>`
- `/task run <run_id>`
- richer `/task logs`

Definition of done:

- a user can inspect what happened in a task without reading SQLite directly
- failed runs are easier to diagnose
- future skill expansion remains debuggable

Status:

- implemented for task-bound runs
- public run IDs, richer run metadata, tool event logs, and run inspection commands are now available

## Later Phases

### Phase 5: Better Task Ergonomics Beyond Identity

Potential work:

- title or recent-task shortcuts
- better task filtering
- compact status views

### Phase 6: Safer Cybersecurity Skill Expansion

Recommended order:

1. information gathering
2. local configuration audit
3. dependency and secret checks
4. semi-automated verification

Hard rule:

Do not add high-risk or offensive capabilities before observability and safety remain easy to audit.

## Testing Priorities

Future regression coverage should focus on:

- local skill override and reload behavior
- capability-tier enforcement
- safety audit logging
- run inspection and diagnostics
- failure classification
- richer task/run CLI inspection

## Documentation Policy

Rules:

1. do not leave completed phases described as “next”
2. keep skill behavior documented as explicit and on-demand
3. update docs whenever task/run inspection or safety logging changes
4. prefer rewriting stale docs over accumulating historical notes
