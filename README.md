# mini-claude-code

`mini-claude-code` is a local Python CLI coding agent built around:

- a LangChain tool-calling loop
- a persisted task runtime
- a controlled local tool execution boundary

The project is intended for local single-user development work. It is not a SaaS agent platform or a multi-user service.

## Current Capabilities

- interactive local CLI
- built-in `SKILL.md` skill system
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
- `/skill list`
- `/skill show <name>`

## Current Architecture

Core source areas:

- `src/main.py`
- `src/agent/`
- `src/app/`
- `src/runtime/`
- `src/models/`
- `src/skills/`
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

## Built-In Skills

The current built-in skills are:

- `development-default`
- `security-audit`

These skills are loaded from `src/skills/*/SKILL.md` and currently affect:

- prompt composition
- visible tool availability
- task creation and task resume validation

## Tests

```bash
pytest
```
