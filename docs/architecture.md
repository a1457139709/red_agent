# Current Architecture

## Summary

`mini-claude-code` is a local Python CLI agent with these active pillars:

- an interactive chat shell
- a persisted task runtime
- an explicit `SKILL.md` skill layer
- a capability-tier safety boundary
- metadata-plus-blob checkpoint storage

The system remains local-first and single-user focused.

## Top-Level Structure

```text
src/
  main.py               # CLI shell, slash commands, prompt routing, active skill state
  agent/                # prompt assembly, model loop, session state, context compression
  app/                  # task, run, checkpoint, and skill service layer
  runtime/              # task runner orchestration
  models/               # Task, Run, CheckpointRecord, CheckpointSummary, TaskLogEntry, SkillManifest
  skills/               # SKILL.md loader, registry, and built-in skills
  storage/              # SQLite repositories
  tools/                # tools, safety policy, and executor
  utils/                # path safety, command safety, confirmations, truncation helpers
```

## Runtime Layers

### 1. CLI Layer

`src/main.py` owns:

- the interactive shell
- slash command handling
- hierarchical help routing:
  - `/help`
  - `/help task`
  - `/help skill`
  - `/task help`
  - `/skill help`
- active task binding
- active session skill binding
- prompt routing
- `/task ...` commands, including search, recent-task shortcuts, and compact status views
- `/skill ...` commands
- `/skill reload`
- `/skill-name <prompt>` one-shot skill shorthand

The human-facing CLI output is rendered through the Rich presenter in `src/cli/ui.py`.
`src/main.py` no longer owns a separate plain-string render path for task/run/checkpoint/skill views.

### 2. Agent Runtime Layer

`src/agent/` owns:

- `loop.py`
  The LangChain tool-calling loop.
- `prompt.py`
  System prompt assembly with base prompt, optional skill prompt, and optional context summary.
- `provider.py`
  Model creation.
- `state.py`
  In-memory session state and checkpoint serialization.
- `context.py`
  Context compression and compressed-summary rendering.

This layer is responsible for one conversational turn at a time.

### 3. Application Layer

`src/app/` owns:

- `task_service.py`
  Task CRUD and task status updates.
- `run_service.py`
  Run lifecycle and task log operations.
- `checkpoint_service.py`
  Checkpoint save/load/list/delete/prune behavior across SQLite metadata and filesystem blobs.
- `skill_service.py`
  Skill discovery plus runtime config building for:
  - base mode
  - explicit skill mode
  - runtime safety policy derivation

### 4. Task Runtime Layer

`src/runtime/task_runner.py` owns:

- task resume rules
- one-prompt-to-one-run orchestration
- checkpoint creation after successful bound runs
- task status transitions for resume, detach, complete, and failure
- explicit task-skill resolution when `Task.skill_profile` is set
- base-mode execution when `Task.skill_profile` is unset
- task-scoped safety audit logging

### 5. Skill Layer

`src/skills/` contains:

- `loader.py`
  Minimal frontmatter parser for standard `SKILL.md`.
- `registry.py`
  Built-in plus user-local skill discovery and validation.
- `development-default/`
  A built-in development skill template.
- `security-audit/`
  A narrower read-heavy audit skill.

Skill sources currently supported:

- built-in: `src/skills/*/SKILL.md`
- local: `.mini-claude-code/skills/*/SKILL.md`

If a local skill and a built-in skill share the same name, the local skill wins.

### 6. Persistence Layer

`src/storage/` owns SQLite access:

- `sqlite.py`
  Database connection setup.
- `tasks.py`
  `tasks` table repository.
- `runs.py`
  `runs` and `task_logs` table repository.
- `checkpoints.py`
  `checkpoints` metadata repository and checkpoint schema validation.

The current source of truth for persisted runtime state is:

- `.mini-claude-code/agent.db`

Checkpoint blobs live under:

- `.mini-claude-code/checkpoints/`

### 7. Tool Layer

`src/tools/` contains the current built-in tools:

- `read_file`
- `write_file`
- `edit_file`
- `list_dir`
- `search`
- `bash`
- `delete_file`

`src/tools/policy.py` owns:

- capability classification
- runtime safety policy calculation
- safety audit event shape

`src/tools/executor.py` remains the execution policy boundary.

### 8. Safety Layer

The safety layer is split across:

- `src/tools/policy.py`
- `src/tools/executor.py`
- `src/utils/safety.py`

Current safety behavior includes:

- path restriction to the working directory
- capability tiers:
  - `read`
  - `write`
  - `execute`
  - `destructive`
- confirmation for sensitive writes
- confirmation for destructive tools
- shell danger classification
- task-scoped safety audit events for risky operations

Skills can tighten the effective safety policy by limiting visible tools, but they do not expand permissions beyond base mode.

## Execution Flow

### Ad-Hoc Chat in Base Mode

1. The user enters a normal prompt in `main.py`.
2. No skill is resolved.
3. `SkillService` builds a base runtime config.
4. The base prompt plus optional context summary is assembled.
5. The full built-in tool registry is visible to the model.
6. The base safety policy is attached to the executor.
7. `agent.loop.agent_loop(...)` runs the model-plus-tools turn.
8. The result is applied into `SessionState`.

### Ad-Hoc Chat with an Active Session Skill

1. The user activates a skill with `/skill use <name>`.
2. Normal prompts route through the selected skill.
3. The skill body is appended into prompt assembly.
4. The visible tool set is filtered by the skill's `allowed-tools`.
5. The safety policy is narrowed from the allowed tools.
6. The result is applied into `SessionState`.

### One-Shot Skill Invocation

1. The user enters `/skill-name <prompt>`.
2. The skill is resolved for that turn only.
3. The prompt executes with the skill's prompt body, filtered tools, and narrowed safety policy.
4. The shell does not keep that skill active afterward.

### Bound Task Prompt

1. The user resumes a task with `/task resume <id>`.
2. The latest checkpoint is restored into `SessionState`.
3. If the task has `skill_profile`, that skill is resolved.
4. If the task has no `skill_profile`, the task runs in base mode.
5. A `Run` is created.
6. The executor is wrapped with the effective safety policy and task-scoped audit logger.
7. `agent_loop(...)` executes one turn.
8. The updated `SessionState` is checkpointed through `CheckpointService`.
9. Task logs are written, including safety and tool events when relevant.
10. The task stays bound until detach, complete, reset, or exit.

## Current Data Model

### Task

The current `Task` entity stores:

- internal UUID
- public task ID
- title and goal
- workspace
- task status
- optional `skill_profile`
- last checkpoint ID
- last error

### Run

A `Run` represents one bound user prompt processed through the task runtime.

It stores:

- public run ID
- run status
- start and finish timestamps
- duration
- step count
- effective skill name
- effective visible tools
- failure kind
- last usage
- last error

### Checkpoint

Checkpoint persistence is split into:

- `CheckpointRecord`
  Internal checkpoint metadata used for restore and lifecycle operations.
- `CheckpointSummary`
  CLI-safe checkpoint metadata used for listing and inspection.

Checkpoint payloads are stored as gzip-compressed JSON blobs on disk, while SQLite stores only metadata.

### TaskLogEntry

A `TaskLogEntry` records task-level runtime events such as:

- task resumed
- run started
- checkpoint saved
- run completed
- run failed
- task detached
- task completed
- safety confirmation required
- safety operation blocked
- safety policy denied
- tool invoked/completed/failed

## Current Boundaries

The current architecture enforces these boundaries:

- `main.py` handles shell interaction
- `SkillService` builds base or skill runtime configs
- `TaskRunner` handles persisted task orchestration
- `CheckpointService` handles checkpoint storage and lifecycle
- `agent_loop` handles one model/tool loop
- `ToolExecutor` handles safety checks before tool execution
- repositories handle SQLite reads and writes

## What Is Not Implemented Yet

The following are still future work:

- better task ergonomics beyond public IDs
- richer task filtering and recent-task shortcuts
- more structured export-friendly diagnostics
- richer use of optional Claude-compatible skill extensions
- safe expansion of cybersecurity-oriented skills
