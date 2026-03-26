# Current Architecture

## Summary

`mini-claude-code` is a local Python CLI agent with three active pillars:

- an interactive chat shell
- a persisted task runtime
- a controlled tool execution boundary

It is not yet a plugin-driven or service-oriented system. The current runtime is intentionally small and local-first.

## Top-Level Structure

```text
src/
  main.py               # CLI shell and task commands
  agent/                # prompt assembly, model loop, session state, context compression
  app/                  # task and run service layer
  runtime/              # task runner orchestration
  models/               # Task, Run, Checkpoint, TaskLogEntry
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
- prompt routing
- display of task details and task logs

This is the user-facing entry point for both ad-hoc chat and task-oriented work.

### 2. Agent Runtime Layer

`src/agent/` owns:

- `loop.py`
  The LangChain tool-calling loop.
- `prompt.py`
  System prompt assembly.
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

These services are thin wrappers over storage and hold the app-level persistence API used by the CLI and runtime.

### 4. Task Runtime Layer

`src/runtime/task_runner.py` owns:

- task resume rules
- one-prompt-to-one-run orchestration
- checkpoint creation after successful bound runs
- task status transitions for resume, detach, complete, and failure

This is the bridge between the generic chat loop and persisted task execution.

### 5. Persistence Layer

`src/storage/` owns SQLite access:

- `sqlite.py`
  Database connection setup.
- `tasks.py`
  `tasks` table repository.
- `runs.py`
  `runs`, `checkpoints`, and `task_logs` table repository.

The current source of truth for local persisted runtime state is `.mini-claude-code/agent.db`.

### 6. Tool Layer

`src/tools/` contains the current built-in tools:

- `read_file`
- `write_file`
- `edit_file`
- `list_dir`
- `search`
- `bash`
- `delete_file`

`src/tools/__init__.py` is the explicit tool registry entry point.

### 7. Safety Layer

`src/tools/executor.py` and `src/utils/safety.py` together provide:

- path restriction to the working directory
- sensitive-path warnings
- command danger classification
- confirmation for risky shell commands

Tools do not own their own approval UI. The executor is the current policy boundary.

## Execution Flow

### Ad-Hoc Chat

1. The user enters a prompt in `main.py`.
2. `agent.loop.agent_loop(...)` runs a normal model-plus-tools turn.
3. The result is applied into `SessionState`.
4. Context compression may run if token usage crosses the threshold.
5. The shell waits for the next prompt.

### Bound Task Prompt

1. The user resumes a task with `/task resume <id>`.
2. The latest checkpoint is restored into `SessionState`.
3. Normal prompts now route through `TaskRunner.run_prompt(...)`.
4. A `Run` is created.
5. `agent_loop(...)` executes one turn.
6. The updated `SessionState` is checkpointed.
7. Task logs are written.
8. The task stays bound until detach, complete, reset, or exit.

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

The current architecture already enforces these boundaries:

- `main.py` handles shell interaction
- `TaskRunner` handles persisted task orchestration
- `agent_loop` handles one model/tool loop
- `ToolExecutor` handles safety checks before tool execution
- repositories handle SQLite reads and writes

## What Is Not Implemented Yet

The following are still future work:

- the `SKILL.md`-based skill system
- skill-aware prompt composition
- skill-aware tool filtering
- stronger permission levels per tool
- richer observability and metrics
- a user-local skill directory loader

## Recommended Next Direction

The next major architecture step is not more tools. It is the standardized skill layer:

- `models/skill.py`
- `skills/loader.py`
- `skills/registry.py`
- `app/skill_service.py`

That will allow future development and security capabilities to extend the runtime without bloating the core loop.
