# Current Architecture

## Summary

`mini-claude-code` is a local Python CLI agent with four active pillars:

- an interactive chat shell
- a persisted task runtime
- an explicit `SKILL.md` skill layer
- a controlled tool execution boundary

The system remains local-first and single-user focused.

## Top-Level Structure

```text
src/
  main.py               # CLI shell, slash commands, prompt routing, active skill state
  agent/                # prompt assembly, model loop, session state, context compression
  app/                  # task, run, and skill service layer
  runtime/              # task runner orchestration
  models/               # Task, Run, Checkpoint, TaskLogEntry, SkillManifest
  skills/               # SKILL.md loader, registry, and built-in skills
  storage/              # SQLite repositories
  tools/                # tool implementations and tool registry
  utils/                # path safety, command safety, confirmations, truncation helpers
```

## Runtime Layers

### 1. CLI Layer

`src/main.py` owns:

- the interactive shell
- slash command handling
- active task binding
- active session skill binding
- prompt routing
- `/task ...` commands
- `/skill ...` commands
- `/skill-name <prompt>` one-shot skill shorthand

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
  Run lifecycle, checkpoints, and task log operations.
- `skill_service.py`
  Skill discovery plus runtime config building for:
  - base mode
  - explicit skill mode

### 4. Task Runtime Layer

`src/runtime/task_runner.py` owns:

- task resume rules
- one-prompt-to-one-run orchestration
- checkpoint creation after successful bound runs
- task status transitions for resume, detach, complete, and failure
- explicit task-skill resolution when `Task.skill_profile` is set
- base-mode execution when `Task.skill_profile` is unset

This is the bridge between the generic chat loop and persisted task execution.

### 5. Skill Layer

`src/skills/` contains:

- `loader.py`
  Minimal frontmatter parser for standard `SKILL.md`.
- `registry.py`
  Built-in skill discovery and validation.
- `development-default/`
  A built-in development skill template.
- `security-audit/`
  A narrower read-heavy audit skill.

Built-in skills are currently loaded only from `src/skills/*/SKILL.md`.

### 6. Persistence Layer

`src/storage/` owns SQLite access:

- `sqlite.py`
  Database connection setup.
- `tasks.py`
  `tasks` table repository.
- `runs.py`
  `runs`, `checkpoints`, and `task_logs` table repository.

The current source of truth for local persisted runtime state is `.mini-claude-code/agent.db`.

### 7. Tool Layer

`src/tools/` contains the current built-in tools:

- `read_file`
- `write_file`
- `edit_file`
- `list_dir`
- `search`
- `bash`
- `delete_file`

`src/tools/__init__.py` is the explicit tool registry entry point.

### 8. Safety Layer

`src/tools/executor.py` and `src/utils/safety.py` provide:

- path restriction to the working directory
- sensitive-path warnings
- command danger classification
- confirmation for risky shell commands

Tools do not own their own approval UI. The executor remains the execution policy boundary.

## Execution Flow

### Ad-Hoc Chat in Base Mode

1. The user enters a normal prompt in `main.py`.
2. No skill is resolved.
3. `SkillService` builds a base runtime config.
4. The base prompt plus optional context summary is assembled.
5. The full built-in tool registry is visible to the model.
6. `agent.loop.agent_loop(...)` runs the model-plus-tools turn.
7. The result is applied into `SessionState`.

### Ad-Hoc Chat with an Active Session Skill

1. The user activates a skill with `/skill use <name>`.
2. Normal prompts now route through the selected skill.
3. The skill body is appended into prompt assembly.
4. The visible tool set is filtered by the skill’s `allowed-tools`.
5. The result is applied into `SessionState`.

### One-Shot Skill Invocation

1. The user enters `/skill-name <prompt>`.
2. The skill is resolved for that turn only.
3. The prompt executes with the skill’s prompt body and filtered tools.
4. The shell does not keep that skill active afterward.

### Bound Task Prompt

1. The user resumes a task with `/task resume <id>`.
2. The latest checkpoint is restored into `SessionState`.
3. If the task has `skill_profile`, that skill is resolved.
4. If the task has no `skill_profile`, the task runs in base mode.
5. A `Run` is created.
6. `agent_loop(...)` executes one turn.
7. The updated `SessionState` is checkpointed.
8. Task logs are written.
9. The task stays bound until detach, complete, reset, or exit.

## Current Data Model

### Task

The current `Task` entity stores:

- identity and metadata
- title and goal
- workspace
- task status
- optional `skill_profile`
- last checkpoint ID
- last error

### Run

A `Run` represents one bound user prompt processed through the task runtime.

It stores:

- run status
- start and finish timestamps
- step count
- last usage
- last error

### Checkpoint

A `Checkpoint` stores a serialized `SessionState` snapshot for a task, optionally linked to a run.

### TaskLogEntry

A `TaskLogEntry` records task-level runtime events such as:

- task resumed
- run started
- checkpoint saved
- run completed
- run failed
- task detached
- task completed

## Current Boundaries

The current architecture enforces these boundaries:

- `main.py` handles shell interaction
- `SkillService` builds base or skill runtime configs
- `TaskRunner` handles persisted task orchestration
- `agent_loop` handles one model/tool loop
- `ToolExecutor` handles safety checks before tool execution
- repositories handle SQLite reads and writes

## What Is Not Implemented Yet

The following are still future work:

- user-local skill directory loading
- CLI-friendly public task IDs
- stronger permission levels per tool
- richer observability and metrics
- richer use of optional Claude-compatible skill extensions
