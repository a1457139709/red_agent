# Task Runtime

## Summary

The current codebase supports a minimal persisted task workflow on top of the local CLI.

The shell can run in two modes:

- unbound chat mode
- bound task mode

In bound task mode, prompts are attached to a persisted task and each prompt produces a persisted run plus a new checkpoint.

## CLI Commands

### General Commands

- `/help`
- `/reset`
- `/exit`
- `/quit`

### Task Commands

- `/task create`
  Prompt for a title and goal, then create a task in `pending`.
- `/task list`
  List recent tasks by `updated_at DESC`.
- `/task show <task_id>`
  Show task details.
- `/task logs <task_id> [limit]`
  Show recent task log entries. Default limit: `20`.
- `/task resume <task_id>`
  Restore the latest checkpoint and bind the task to the current shell.
- `/task detach`
  Save a checkpoint, mark the task `paused`, and detach it from the shell.
- `/task complete`
  Save a checkpoint, mark the task `completed`, and detach it from the shell.

## Shell Binding Model

Only one task can be bound to one interactive shell session at a time.

When a task is bound:

- the prompt changes to `task:<short_id> >`
- normal user prompts are executed through the task runtime
- `/reset`, `/exit`, and `/quit` pause and detach the task before leaving the current session

## Task States

The current task states are:

- `pending`
- `running`
- `paused`
- `failed`
- `completed`
- `cancelled`

Current behavior:

- a new task starts as `pending`
- `/task resume` moves a resumable task to `running`
- `/task detach` moves the active task to `paused`
- `/task complete` moves the active task to `completed`
- runtime exceptions during a bound run move the task to `failed`
- `completed` and `cancelled` tasks cannot be resumed

## Runtime Flow for a Bound Prompt

When the user sends a normal prompt while a task is bound:

1. `TaskRunner` verifies the task can run.
2. `RunService` creates a `Run` row with status `running`.
3. A `run_started` task log entry is written.
4. `agent.loop.agent_loop(...)` executes one model/tool loop.
5. The returned messages are applied to `SessionState`.
6. Context compression may run if token usage is high enough.
7. `RunService` saves a new checkpoint from the updated `SessionState`.
8. The task is updated with the new checkpoint ID.
9. The run is marked `completed` or `failed`.
10. Task log entries are written for checkpoint and run outcome.

## Persisted Entities

### Task

Stored in the `tasks` table.

Used for:

- task identity
- goal and metadata
- current status
- current checkpoint pointer
- last error

### Run

Stored in the `runs` table.

Used for:

- one bound prompt execution
- start and finish timestamps
- step count
- last usage
- last error

### Checkpoint

Stored in the `checkpoints` table.

Used for:

- serialized `SessionState` snapshots
- restore of conversation context on `/task resume`

### TaskLogEntry

Stored in the `task_logs` table.

Used for:

- task lifecycle events
- run lifecycle events
- checkpoint-related events
- failure diagnostics

## Checkpoint Contents

The current checkpoint payload serializes `SessionState`:

- `history`
- `compressed_summary`
- `last_usage`

Supported message types in checkpoint serialization:

- `HumanMessage`
- `AIMessage`
- `ToolMessage`
- `SystemMessage`

## Code Entry Points

- `src/main.py`
  CLI shell, task command handling, and active task binding.
- `src/runtime/task_runner.py`
  Task lifecycle orchestration and checkpoint behavior.
- `src/app/task_service.py`
  Task persistence API.
- `src/app/run_service.py`
  Run, checkpoint, and task log persistence API.
- `src/storage/tasks.py`
  SQLite repository for `tasks`.
- `src/storage/runs.py`
  SQLite repository for `runs`, `checkpoints`, and `task_logs`.

## Current Limitations

- tasks are still manually completed with `/task complete`
- there is no autonomous background runner yet
- `skill_profile` exists on `Task` but is not active in runtime behavior yet
- logs are event-oriented, not yet a full replay/debug trace

## Next Step

The next development step is to integrate a standardized `SKILL.md`-based skill system into this task runtime so that:

- a task can bind a real skill profile
- the skill can affect prompt composition
- the skill can filter the available tool set
