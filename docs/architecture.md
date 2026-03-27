# Current Architecture

## Summary

`mini-claude-code` is a local Python CLI agent with four active pillars:

- an interactive chat shell
- a persisted task runtime
- a built-in `SKILL.md` skill layer
- a controlled tool execution boundary

The system remains intentionally local-first and single-user focused.

## Top-Level Structure

```text
src/
  main.py               # CLI shell, slash commands, and prompt routing
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
- prompt routing
- `/task ...` commands
- `/skill list` and `/skill show <name>`

`/task create` now also validates and stores a skill profile.

### 2. Agent Runtime Layer

`src/agent/` owns:

- `loop.py`
  The LangChain tool-calling loop.
- `prompt.py`
  System prompt assembly with base prompt, skill prompt, and context summary.
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
  Skill discovery, default resolution, prompt assembly, and allowed-tool selection.

### 4. Task Runtime Layer

`src/runtime/task_runner.py` owns:

- task resume rules
- one-prompt-to-one-run orchestration
- checkpoint creation after successful bound runs
- task status transitions for resume, detach, complete, and failure
- skill resolution for bound task execution

This is the bridge between the generic chat loop and persisted task execution.

### 5. Skill Layer

`src/skills/` now contains:

- `loader.py`
  Minimal frontmatter parser for standard `SKILL.md`.
- `registry.py`
  Built-in skill discovery and validation.
- `development-default/`
  The default coding skill.
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

`src/tools/__init__.py` is the explicit tool registry entry point. The visible tool set is now filtered per skill before each model turn.

### 8. Safety Layer

`src/tools/executor.py` and `src/utils/safety.py` together provide:

- path restriction to the working directory
- sensitive-path warnings
- command danger classification
- confirmation for risky shell commands

Tools do not own their own approval UI. The executor remains the execution policy boundary.

## Execution Flow

### Ad-Hoc Chat

1. The user enters a prompt in `main.py`.
2. `SkillService` resolves `development-default`.
3. The skill body is appended into system prompt assembly.
4. The visible tool registry is filtered by the skill.
5. `agent.loop.agent_loop(...)` runs the model-plus-tools turn.
6. The result is applied into `SessionState`.
7. Context compression may run if token usage crosses the threshold.
8. The shell waits for the next prompt.

### Bound Task Prompt

1. The user resumes a task with `/task resume <id>`.
2. The latest checkpoint is restored into `SessionState`.
3. The task skill is resolved from `Task.skill_profile`.
4. Normal prompts now route through `TaskRunner.run_prompt(...)`.
5. A `Run` is created.
6. `agent_loop(...)` executes one turn with the resolved skill prompt and filtered tools.
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
- `TaskRunner` handles persisted task orchestration
- `SkillService` handles skill resolution and prompt/tool shaping
- `agent_loop` handles one model/tool loop
- `ToolExecutor` handles safety checks before tool execution
- repositories handle SQLite reads and writes

## What Is Not Implemented Yet

The following are still future work:

- a user-local skill directory loader
- stronger permission levels per tool
- richer observability and metrics
- richer use of optional Claude-compatible skill extensions
