# Architecture Review

## Snapshot

The current repository is beyond the demo stage. It already has a usable local-agent backbone:

- interactive CLI with Rich presentation
- explicit skill activation and one-shot skill invocation
- persisted tasks, runs, checkpoints, and task logs
- public task/run IDs
- capability-tier safety enforcement
- checkpoint blob storage plus SQLite metadata
- resumable task execution with detach and complete flows

The strongest part of the system is the main runtime spine:

`shell -> skill resolution -> tool executor -> task/run/checkpoint persistence`

That spine is coherent and already useful for local development workflows.

## What Is Working Well

### Clear layering

Responsibilities are split reasonably well across:

- `main.py` for shell routing
- `agent/` for prompt + model turn execution
- `app/` for service orchestration
- `runtime/task_runner.py` for persisted task execution
- `storage/` for SQLite persistence
- `tools/` for execution and safety boundaries

### Good local-first tradeoffs

The current stack is pragmatic for a single-user local agent:

- Python for iteration speed
- LangChain for tool-calling integration
- SQLite for structured runtime state
- filesystem blobs for checkpoint payloads
- Rich for readable CLI inspection

### Observability is already practical

The project does more than store final task state. It also keeps:

- run metadata
- failure kinds
- task logs
- safety audit events
- tool execution events

That makes debugging and runtime inspection much easier than in a typical early agent prototype.

## Main Gaps

The most important current gaps are not in the basic runtime loop. They are in product maturity and ecosystem depth.

### 1. Long-term memory and workspace rules

There is no durable project-level instruction layer comparable to a repository memory file or persistent workspace rules. The runtime can resume conversations through checkpoints, but it does not yet have a separate long-lived memory system.

### 2. External extensibility

The code supports `SKILL.md`, but not a broader external integration model such as plugins, MCP-style tools, or a stable third-party extension API.

### 3. Multi-agent and planning capabilities

The current runtime is single-agent and interactive. There is no sub-agent delegation, planner/executor split, or background orchestration model.

### 4. Codebase hygiene

A few mismatches still show up in the repository:

- some files still contain mojibake or garbled text
- naming is not fully unified (`red-code` vs `mini-claude-code`)
- a few source files exist but are not part of the actual runtime path
- documentation and implementation have needed periodic re-alignment

## Comparison With More Mature Coding Agents

Compared with mature coding-agent products, this repository already covers the minimum viable local core:

- shell UX
- file and command tools
- skill system
- resumable task persistence
- basic safety controls
- task/run observability

What it does not yet cover is the next maturity layer:

- project memory and rules
- permission modes and planning modes
- external tool protocols
- multi-agent delegation
- git-native review or PR automation
- background or remote workflows

So the project should be viewed as:

**a solid local coding-agent prototype with a real persisted runtime, not yet a fully mature agent platform**

## Suggested Next Priorities

Recommended priority order:

1. keep docs and runtime behavior aligned
2. clean up naming and mojibake in source and docs
3. add a project-memory or repository-rules layer
4. design an external integration boundary
5. explore sub-agent or planning workflows
6. expand security-oriented skills only after the platform stays observable and auditable
