# Engineering Development Plan

## 1. Purpose

This document is the internal engineering blueprint for the continued development of `mini-claude-code`.

Its goal is not to explain what the project is at a high level, but to define:

- what the project should evolve toward
- which capabilities should be built first
- how the codebase should be structured over time
- what each delivery phase must achieve
- which architectural boundaries must remain intact during development

This document is written for future implementation work in this repository.

## 2. Product Scope and Constraints

### 2.1 Current Target

This project is not intended to become a team platform or a SaaS agent service.

The current target is:

- local single-user usage
- development assistance as the primary use case
- support for medium and long-running tasks
- gradual introduction of a skill system
- future addition of cybersecurity-oriented skills
- strong emphasis on local control, safety, and maintainability

### 2.2 Non-Goals

The following are not current goals:

- multi-tenancy
- web control panel
- user accounts
- organization-level permission models
- distributed scheduling
- complex cloud deployment

Conclusion:

The project should continue evolving from the current codebase rather than being rewritten from scratch, but future work must be done as structured engineering improvements instead of ad hoc feature accumulation.

## 3. Current Foundation

The current codebase already has enough structure to support continued growth:

- a working CLI interaction loop
- `Settings` for centralized configuration
- `SessionState` for centralized session state
- `ToolExecutor` for controlled tool execution
- explicit tool assembly
- baseline tests and packaging metadata

Because of this, the next stage is not about replacing the core loop. It is about adding four major capabilities:

1. long-running task support
2. skill / plugin support
3. stronger local execution safety
4. maintainable engineering infrastructure

## 4. Guiding Principles

All future development should follow these principles.

### 4.1 Local-First

Every design decision should optimize for local single-machine usage.

This means:

- prefer local files and SQLite for persistence
- prefer local task execution over external brokers
- prefer readable file-based configuration over service-heavy infrastructure

### 4.2 Keep the Core Runtime Small

The runtime core should remain stable and focused.

The core should own:

- session state
- task state
- prompt assembly
- tool execution
- task orchestration
- safety policy

Complex domain behavior should be introduced through explicit skills, not by overloading the main loop.

### 4.3 All Side Effects Must Go Through a Controlled Layer

Any capability that changes files, executes commands, or touches the network must go through a unified execution boundary.

This implies:

- tools must not handle user interaction directly
- tools must not define their own permission model
- tools must not bypass unified logging or audit logic

### 4.4 Long-Running Tasks Must Be Recoverable

Future long-running task support must prioritize:

- resumability after interruption
- retryability after failure
- step-level execution history
- visibility into current task state

### 4.5 Safety Must Be Enforced by Code, Not Only by Prompts

When cybersecurity skills are introduced later, safety must not rely only on prompt instructions.

It must be enforced through:

- tool-level permissions
- command classification
- workspace restrictions
- allowlists / denylists
- audit trails

## 5. Target Architecture Direction

The codebase should gradually move toward the following shape:

```text
src/
├── main.py                     # local CLI entry point
├── app/
│   ├── session_service.py      # session management
│   ├── task_service.py         # task management
│   ├── run_service.py          # single-run orchestration
│   └── skill_service.py        # skill loading and resolution
├── agent/
│   ├── loop.py
│   ├── context.py
│   ├── prompt.py
│   ├── provider.py
│   ├── settings.py
│   └── state.py
├── runtime/
│   ├── task_runner.py          # long-running task executor
│   ├── checkpoint.py           # save / restore checkpoints
│   ├── event_bus.py            # runtime events
│   └── policies.py             # runtime policies
├── skills/
│   ├── registry.py             # skill registry
│   ├── base.py                 # skill interface
│   ├── development/
│   └── security/
├── tools/
│   ├── __init__.py
│   ├── executor.py
│   ├── policies.py             # tool permission rules
│   └── ...
├── storage/
│   ├── sqlite.py               # SQLite access layer
│   ├── tasks.py
│   ├── sessions.py
│   └── runs.py
├── models/
│   ├── task.py
│   ├── skill.py
│   ├── run.py
│   └── events.py
└── utils/
```

Notes:

- this is a direction, not an immediate rewrite target
- new work should be added in a way that converges toward this shape

## 6. Capability Roadmap

## Phase 1: Minimal Long-Running Task Support

### Goal

Move the agent from pure request-response interaction toward explicit task execution.

### Required Work

1. define a `Task` model
2. define a task state machine
3. bind one execution run to one task
4. store task logs
5. support interruption and resume

### Suggested Task Fields

- `id`
- `title`
- `goal`
- `status`
- `created_at`
- `updated_at`
- `workspace`
- `last_checkpoint`
- `last_error`

Suggested states:

- `pending`
- `running`
- `paused`
- `failed`
- `completed`
- `cancelled`

### Definition of Done

- tasks can be created and persisted locally
- interrupted tasks can be resumed
- current task state can be inspected
- recent task logs can be viewed

## Phase 2: Skill / Plugin System

### Goal

Represent development, security, and future domain behaviors as skills rather than embedding them directly into the core loop.

### Minimal Skill Structure

Each skill should define:

- `manifest`
- prompt fragments
- required tools
- execution hooks
- safety constraints
- examples

### Initial Skill Families

Start with two families:

1. `development`
   - code reading
   - refactoring
   - test generation
   - project structure analysis

2. `security`
   - asset enumeration
   - vulnerability triage
   - web security inspection
   - local security analysis

### Definition of Done

- skills can be explicitly enabled or disabled
- skills can affect prompt composition and available tools
- a task can bind to a default skill profile
- each skill can declare required tools and permission needs

## Phase 3: Stronger Execution Safety

### Goal

Build a real local execution boundary before adding more powerful security capabilities.

### Required Work

1. tool permission levels
2. workspace allowlist support
3. command allowlist / denylist
4. stronger confirmation policy for risky operations
5. audit logging for critical actions

### Suggested Permission Levels

- `read_only`
- `workspace_write`
- `system_command_safe`
- `system_command_sensitive`
- `network_access`

### Important Constraint

Security-oriented skills are likely to request more powerful commands later, so execution safety must be strengthened before expanding those tools.

### Definition of Done

- every tool has an explicit permission level
- every execution can be traced to a task and run
- risky commands still go through the unified executor even in single-user local mode

## Phase 4: Local Persistence and Recovery

### Goal

Allow the agent to survive process exits and continue unfinished work.

### Recommended Approach

Use SQLite first.

Why:

- enough for single-machine usage
- easy to query
- no extra service dependency
- good fit for tasks, sessions, runs, and event history

### Suggested Persisted Entities

- Sessions
- Tasks
- Runs
- RunEvents
- SkillConfigs
- Checkpoints

### Definition of Done

- historical tasks can be listed after restart
- unfinished tasks can be resumed
- execution history can be inspected

## Phase 5: Observability and Debugging

### Goal

Make it possible to understand what the agent did, why it failed, and where the bottleneck is.

### Required Work

1. structured logs
2. event stream recording
3. task-level log files
4. tool timing metrics
5. error classification

### Suggested Log Fields

- `task_id`
- `session_id`
- `run_id`
- `step_index`
- `tool_name`
- `tool_args`
- `duration_ms`
- `status`
- `error_type`

### Definition of Done

- failed tasks can be replayed from logs
- failures can be categorized as model, tool, permission, or runtime issues

## Phase 6: Cybersecurity Skill Introduction

### Goal

Add security-oriented skills on top of an already controlled local runtime.

### Recommended Order

Add lower-risk capabilities first, then stronger ones.

1. information gathering
   - fingerprinting
   - basic HTTP probing
   - local file audit

2. inspection
   - common misconfiguration checks
   - dependency risk analysis
   - route / exposure analysis

3. semi-automated verification
   - only on explicitly controlled local targets
   - explicit target confirmation required
   - clear risk confirmation required

### Hard Rule

Do not add high-risk scanning or offensive command execution before permission control and audit logging are significantly stronger.

## 7. Directory Evolution Plan

## 7.1 Directories to Keep

These parts of the current codebase should remain and evolve:

- `src/agent/*`
- `src/tools/*`
- `src/utils/*`
- `src/main.py`

## 7.2 New Directories to Introduce First

Recommended order:

1. `src/models/`
2. `src/storage/`
3. `src/app/`
4. `src/runtime/`
5. `src/skills/`

## 7.3 Existing Legacy Areas

- `test/` remains a sandbox / experimental scripts area
- real regression tests should continue to live under `tests/`

## 8. Suggested Data Models

The following models should become stable first.

### 8.1 Session

Suggested fields:

- `id`
- `created_at`
- `updated_at`
- `workspace`
- `compressed_summary`
- `metadata`

### 8.2 Task

Suggested fields:

- `id`
- `session_id`
- `title`
- `goal`
- `status`
- `priority`
- `workspace`
- `skill_profile`
- `created_at`
- `updated_at`

### 8.3 Run

Suggested fields:

- `id`
- `task_id`
- `status`
- `started_at`
- `finished_at`
- `step_count`
- `last_usage`
- `last_error`

### 8.4 SkillManifest

Suggested fields:

- `name`
- `version`
- `description`
- `default_prompt_fragments`
- `required_tools`
- `forbidden_tools`
- `risk_level`

## 9. Testing Strategy

Testing must stay layered as the system grows.

### 9.1 Unit Tests

Cover:

- state objects
- config parsing
- safety rules
- tool executor
- compression summary parsing

### 9.2 Runtime Tests

Cover:

- main loop behavior
- multi-tool calls
- max-step handling
- interruption and resume
- skill switching

### 9.3 Tool Tests

Cover:

- file tools
- search behavior
- command execution boundaries
- permission enforcement

### 9.4 Regression Rule

Each new phase should ship with tests that protect the new behavior. No major refactor should be accepted without matching regression coverage.

## 10. Documentation Policy

The project must not fall back into a state where the code evolves but the docs still describe an old architecture.

Rules:

1. update `docs/` whenever architecture changes
2. update `README.md` when module structure changes
3. update this document when a new phase begins or completes
4. explicitly mark documents that are historical rather than current

## 11. Delivery Priority

Recommended next implementation order:

### Priority 1

- local task system
- SQLite persistence
- task logs and checkpoints

### Priority 2

- skill registry
- skill manifest
- skill-to-tool permission binding

### Priority 3

- stronger local execution safety
- tool permission levels
- minimal cybersecurity skill set

### Priority 4

- stronger observability
- richer examples and documentation

## 12. Definition of Done for Any Phase

Every future phase should satisfy at least the following:

1. a clear code entry point exists
2. regression tests are included
3. documentation is updated
4. failure paths are handled explicitly
5. the current CLI development workflow is not broken

## 13. Immediate Next Development Entry Point

The most practical next implementation step is:

1. create `src/models/task.py`
2. create `src/storage/sqlite.py`
3. create `src/storage/tasks.py`
4. create `src/app/task_service.py`
5. implement the minimal create / load / resume task loop

Why this is next:

- it directly supports the long-running task goal
- it avoids introducing skill-system complexity too early
- it creates the stable task substrate needed before security skills are added
