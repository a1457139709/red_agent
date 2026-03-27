# Engineering Development Plan

## 1. Purpose

This document is the working engineering roadmap for the current repository state.

It should answer:

- what is already implemented
- what should change next
- which architectural assumptions are now considered wrong
- which direction should guide future implementation

## 2. Product Direction

The project is a local single-user coding agent with:

- interactive CLI usage as the primary interface
- support for medium and long-running tasks
- local-first persistence
- future expansion into safer cybersecurity-oriented skills

Non-goals remain:

- SaaS deployment
- multi-user collaboration
- heavy web-platform architecture
- distributed orchestration

Conclusion:

The project should keep evolving from the current codebase, but the next phase should correct two runtime design mismatches:

1. skills should be explicit and on-demand, not implicitly active by default
2. tasks should remain persisted, but CLI interaction must not depend on raw UUIDs

## 3. Current Baseline

Already implemented:

- local CLI shell
- persisted `Task`, `Run`, `Checkpoint`, and task logs
- resumable task runtime
- centralized `Settings`
- centralized `SessionState`
- controlled `ToolExecutor`
- standard `SKILL.md` parsing and built-in skill discovery
- runtime skill-aware prompt composition
- runtime skill-aware visible tool filtering
- built-in skills:
  - `development-default`
  - `security-audit`

However, the current behavior exposes two practical problems:

- the implicit default skill behaves too much like the base runtime, so skill boundaries are unclear
- UUID-only task identity is awkward for CLI workflows

These are now first-class roadmap items.

## 4. Stable Rules

### 4.1 Local-First

Prefer:

- local files
- SQLite
- built-in and future user-local skill directories

### 4.2 Small Core Runtime

Keep the core runtime focused on:

- prompt assembly
- task orchestration
- session state
- tool execution
- persistence
- safety policy

### 4.3 Unified Side-Effect Boundary

Skills may shape:

- prompt fragments
- visible tools
- future policy hints

Skills must not:

- bypass `ToolExecutor`
- create hidden execution paths
- weaken safety rules implicitly

### 4.4 Recoverable Task Runtime

Future work must preserve:

- pause/resume
- checkpoint restore
- task/run logs
- explicit failure tracking

## 5. Corrected Skill Direction

The previous “default skill always active” direction is no longer the preferred model.

The updated target model is:

### 5.1 Base Runtime Mode

Normal ad-hoc chat should run in a base agent mode:

- no skill prompt is loaded by default
- no skill-specific tool filtering is applied by default
- the base runtime uses the standard built-in tool set

### 5.2 Explicit Skill Activation

Skills should be loaded only when explicitly activated.

Target interaction model:

- `/skill list`
- `/skill show <name>`
- `/skill use <name>`
- `/skill clear`
- `/skill-name ...` style invocation or equivalent explicit shorthand

Activation modes to support:

- one-shot skill invocation
- session-bound active skill
- task-bound skill profile

### 5.3 Future Skill Sources

The current built-in `src/skills/` directory remains valid.

Future support should add:

- user-local skills under `.mini-claude-code/skills/`

### 5.4 Skill Runtime Goal

Skills should feel like on-demand capability packs, not a wrapper around the default runtime.

## 6. Corrected Task Direction

Tasks remain useful and should stay in the architecture.

The problem is not that tasks are “for web/UI only”.
The problem is that task identity is currently storage-friendly but CLI-hostile.

### 6.1 Internal vs CLI Identity

Tasks should use two identifiers:

- internal ID: UUID for persistence and relations
- public/display ID: short CLI-friendly identifier

Recommended examples:

- `T0001`
- `T0002`
- `T0003`

### 6.2 CLI Ergonomics Goal

Task commands should support the CLI-friendly ID directly:

- `/task show T0001`
- `/task resume T0001`
- `/task logs T0001`

The full UUID should remain available for debugging, but not be the primary interaction handle.

## 7. Updated Roadmap

### Phase 3: Skill Activation Redesign

This should now come before broader safety expansion.

Required work:

- remove implicit default-skill behavior from normal chat
- introduce explicit skill activation state
- support session-bound active skill
- support one-shot skill invocation
- keep task-bound skill profiles explicit
- prepare user-local skill discovery

Definition of done:

- ad-hoc chat works with no skill loaded
- skills are activated explicitly
- skill loading is clearly visible to the user
- task skill behavior remains explicit and predictable

### Phase 4: Task CLI Ergonomics

Required work:

- add CLI-friendly task public IDs
- support public ID lookup in all task commands
- keep UUID as internal storage key
- improve task listing and selection UX

Definition of done:

- no common CLI task flow requires typing a full UUID
- task output consistently shows public IDs first

### Phase 5: Execution Safety Hardening

After skill activation is corrected, strengthen runtime safety.

Required work:

- tool permission levels
- read/write/execute capability classes
- workspace allowlists
- stricter shell safety rules
- better audit logging for risky operations

Reason:

Security-oriented skills should not expand faster than execution controls.

### Phase 6: Persistence and Recovery Enhancements

Required work:

- persist active skill/session metadata where needed
- improve run-level metadata
- support richer recovery semantics
- prepare for user-local skills and explicit skill session state

### Phase 7: Observability

Required work:

- include `skill_name` where skill execution is active
- record tool-level execution traces
- track durations
- improve failure categorization

### Phase 8: Safe Cybersecurity Skill Expansion

Recommended order:

1. information gathering
2. local configuration audit
3. dependency and secret checks
4. semi-automated verification

Hard rule:

Do not introduce high-risk or offensive capabilities before the safety layer is stronger.

## 8. Immediate Next Development Entry Point

The best next implementation slice is:

1. redesign skill activation so skills are explicit and on-demand
2. introduce active-skill session state in the CLI
3. remove implicit default skill behavior from normal chat
4. add a CLI-friendly task public ID model

This slice will make the runtime match actual CLI usage expectations before further expansion.

## 9. Testing Priorities

Future regression coverage should focus on:

- explicit skill activation and clearing
- no-skill base runtime behavior
- one-shot skill invocation
- session-bound skill behavior
- task public ID generation and lookup
- backward-safe UUID lookup where still needed
- invalid skill activation handling
- explicit task-skill binding behavior

## 10. Documentation Policy

Rules:

1. do not leave completed phases described as “next”
2. do not describe implicit default skill behavior as the desired long-term model
3. keep CLI ergonomics concerns explicit in roadmap decisions
4. update task runtime docs whenever task identity or skill activation behavior changes
