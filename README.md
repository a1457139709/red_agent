# mini-claude-code

`mini-claude-code` is a local Python CLI coding agent built around:

- a LangChain tool-calling loop
- a persisted task runtime
- an explicit `SKILL.md` skill system
- a controlled local execution boundary

The project is intended for local single-user development work. It is not a SaaS agent platform or a multi-user service.

## Current Capabilities

- interactive local CLI
- built-in and user-local `SKILL.md` skills
- explicit skill activation and one-shot skill invocation
- file tools: read, write, edit, list, search, delete
- shell command execution with safety checks
- capability-tier tool safety
- session state and context compression
- persisted tasks, runs, checkpoints, and task logs
- task-scoped safety audit logging

## Run

```bash
pip install -r requirements.txt
python src/main.py
```

## Current CLI Commands

- `/task create`
- `/task list`
- `/task show <task_id>`
- `/task runs <task_id> [limit]`
- `/task run <run_id>`
- `/task logs <task_id> [limit]`
- `/task resume <task_id>`
- `/task detach`
- `/task complete`
- `/skill list`
- `/skill show <name>`
- `/skill use <name>`
- `/skill reload`
- `/skill clear`
- `/skill current`
- `/skill-name <prompt>`

## Skill Locations

Built-in skills live under:

- `src/skills/`

User-local skills live under:

- `.mini-claude-code/skills/`

Example:

```text
.mini-claude-code/
  skills/
    my-skill/
      SKILL.md
```

If a local skill has the same name as a built-in skill, the local skill overrides it after `/skill reload`.

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

Current docs:

- `docs/architecture.md`
- `docs/task-runtime.md`
- `docs/engineering-development-plan.en.md`
- `docs/skill-system-standard.md`

The docs index is at `docs/README.md`.

## Built-In Skills

The current built-in skills are:

- `development-default`
- `security-audit`

## Tests

```bash
pytest
```
