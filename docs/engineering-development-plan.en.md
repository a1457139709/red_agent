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
- Rich presenter-backed CLI output
- hierarchical help with compact `/help` plus `/help task` and `/help skill`
- persisted `Task`, `Run`, checkpoints, and task logs
- public task IDs and public run IDs
- resumable task runtime with detach and complete flow
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
- richer run metadata and run inspection commands
- blob-backed checkpoint storage with SQLite metadata and filesystem snapshots
- checkpoint inspection commands
- checkpoint deletion and pruning APIs

Built-in skills currently include:

- `development-default`
- `security-audit`

User-local skills are supported under:

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
- local files for prompts, skills, and checkpoint blobs
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
- checkpoint creation and restore
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

#### Phase 4: Observability and Richer Diagnostics

Completed:

- run duration
- effective skill and effective tools persisted per run
- structured failure classification
- tool invocation events for task-bound runs
- richer `/task runs`, `/task run`, and `/task logs`

#### Checkpoint Storage Redesign

Completed:

- `CheckpointService`
- SQLite metadata plus filesystem blob storage
- blob integrity validation
- fail-fast rejection of legacy inline checkpoint schema
- `/task checkpoints <task_id>`
- `/task checkpoint <checkpoint_id>`
- `delete_checkpoint(...)`
- `prune_checkpoints(...)`

## Next Phase

### Phase 5: Better Task Ergonomics Beyond Identity

Completed:

- status-aware `/task list [status] [limit]`
- `/task recent [limit]` shortcuts
- `/task find <query> [limit]` title search
- compact `/task status <id>` views
- `latest` / `last` aliases for task-facing commands

### Phase 5A: CLI Presentation and Help Redesign

Completed:

- Rich-based CLI presenter as the human-facing output path
- table/panel-based task, run, checkpoint, and skill views
- hierarchical help:
  - `/help`
  - `/help task`
  - `/help skill`
  - `/task help`
  - `/skill help`
- removal of the old plain-string CLI rendering path from `src/main.py`

### Phase 6: Safer Cybersecurity Skill Expansion

This is now the next implementation focus.

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
- checkpoint inspection, pruning, and deletion behavior
- richer task/run/task-selection CLI inspection

## Documentation Policy

Rules:

1. do not leave completed phases described as "next"
2. keep skill behavior documented as explicit and on-demand
3. update docs whenever task/run/checkpoint inspection changes
4. prefer rewriting stale docs over accumulating historical notes
