# mini-claude-code

`mini-claude-code` is a local Python CLI coding agent built around:

- a LangChain tool-calling loop
- a persisted task runtime
- a controlled local tool execution boundary

The project is intended for local single-user development work. It is not a SaaS agent platform or a multi-user service.

## Current Capabilities

- interactive local CLI
- file tools: read, write, edit, list, search, delete
- shell command execution with safety checks
- session state and context compression
- persisted tasks, runs, checkpoints, and task logs

## Run

```bash
pip install -r requirements.txt
python src/main.py
```

## Task Commands

The CLI currently supports:

- `/task create`
- `/task list`
- `/task show <task_id>`
- `/task logs <task_id> [limit]`
- `/task resume <task_id>`
- `/task detach`
- `/task complete`

## Current Architecture

Core source areas:

- `src/main.py`
- `src/agent/`
- `src/app/`
- `src/runtime/`
- `src/models/`
- `src/storage/`
- `src/tools/`
- `src/utils/`

## Documentation

The `docs/` folder was cleaned up to keep only current documents:

- `docs/architecture.md`
- `docs/task-runtime.md`
- `docs/engineering-development-plan.en.md`
- `docs/skill-system-standard.md`

The docs index is at `docs/README.md`.

## Next Direction

The next major engineering phase is a standardized `SKILL.md`-based skill system:

- parse and load standard `SKILL.md` files
- bind `Task.skill_profile` to runtime behavior
- let skills affect prompt composition
- let skills filter the visible tool set

## Tests

```bash
pytest
```
