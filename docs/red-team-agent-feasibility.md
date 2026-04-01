# Red Team Agent Feasibility

## Purpose

This document evaluates whether the current `red-code` codebase can evolve into a local red-team-oriented agent, and what technical work is required to make that direction practical, safe, and maintainable.

It focuses on these target capabilities:

1. extend a red-team toolbox through `SKILL.md` skills
2. support multiple tasks running in parallel, such as:
   - port scan + directory scan at the same time
   - multiple directory scans at the same time
   - coordinated multi-tool execution
3. support multi-window or multi-pane task presentation so parallel work remains inspectable

This document is not a product pitch. It is a technical feasibility and gap analysis grounded in the current repository state.

## Executive Summary

The current project is a strong local-agent foundation, but it is not yet a mature red-team agent.

What already fits the goal:

- explicit `SKILL.md` loading
- persisted `Task` / `Run` / checkpoint model
- local-first CLI workflow
- task-scoped observability
- capability-tier safety boundary
- structured tool execution boundary

What is still missing for a practical red-team agent:

- controlled network-capable red-team tools
- real concurrent task execution
- multi-window or multi-pane runtime views
- stronger permission and target-boundary controls
- richer long-running orchestration semantics
- safer domain-specific red-team workflows

Feasibility judgment:

- building a useful local red-team agent on top of this codebase is feasible
- building a safe and reliable one requires new execution, isolation, and UI layers
- the hardest problem is not prompt design; it is controlled concurrent execution plus trustworthy safety boundaries

## Current Foundation Relevant to the Goal

The current codebase already provides several pieces that are directly useful for a red-team direction.

### 1. Skill system

The current runtime already supports:

- built-in and local `SKILL.md` discovery
- explicit skill activation
- skill-scoped prompt overlay
- skill-scoped visible-tool filtering
- skill-aware runtime safety narrowing

This is a good base for red-team capability packaging because each domain skill can define:

- when it should be used
- what tools it may expose
- how it should guide the model
- what workflows and reporting style it should follow

### 2. Task / Run / Checkpoint model

The current persisted runtime supports:

- resumable tasks
- one-prompt-to-one-run execution
- run metadata
- tool and safety logs
- checkpoint restore

This is already aligned with offensive or audit-style work, because real security workflows are usually:

- iterative
- long-running
- interruption-prone
- evidence-heavy

### 3. Safety boundary

The current safety model is still generic, but it already establishes:

- a central `ToolExecutor`
- capability tiers:
  - `read`
  - `write`
  - `execute`
  - `destructive`
- shell danger checks
- task-scoped safety audit logs

That means the project already has the right shape for future red-team restrictions, even though the current policy model is not yet strong enough for network-heavy tooling.

### 4. CLI and observability

The current CLI already has:

- persisted task views
- run inspection
- checkpoint inspection
- Rich-based structured presentation

This is important because security work becomes unusable very quickly if users cannot see:

- what ran
- against what target
- with which tool
- with what result
- under which task

## Target Capability 1: Skill-Based Red-Team Toolbox

### What this means

The goal is to use skills as domain packages for red-team workflows, for example:

- `port-scan`
- `dir-scan`
- `http-enum`
- `cve-2021-41773-check`
- `wordpress-enum`
- `subdomain-recon`

Each skill would combine:

- instructions
- allowed tools
- output format
- workflow guidance
- possibly local helper scripts or wrappers

### What is already sufficient

The current skill architecture is already good enough for:

- loading skills from local disk
- validating tool names
- applying prompt overlays
- narrowing visible tools

This means the skill layer itself does not need to be redesigned before red-team work starts.

### What is still missing

The missing piece is not skill loading. The missing piece is the tool layer under the skill system.

Red-team-oriented skills will require tools that do not exist yet, such as:

- TCP/UDP port scanning
- HTTP probing
- directory or content discovery
- DNS resolution or subdomain enumeration
- CVE-specific check wrappers
- result normalization and evidence collection

Those tools should not be implemented as unrestricted raw shell habits alone. They need first-class wrappers so the runtime can:

- validate targets
- validate parameters
- log intent and outcome
- classify risk
- constrain execution

### Technical recommendation

Do not make red-team skills simply say "use bash and run nmap".

Instead, introduce a new layer of typed security tools, for example:

- `port_scan`
- `dir_scan`
- `http_probe`
- `dns_lookup`
- `cve_check`

Each of these should:

- accept structured arguments
- validate targets
- produce normalized output
- integrate with task logs
- remain auditable through `ToolExecutor`

### Difficulty

Medium to high.

The skill architecture is ready.
The tool architecture is only partially ready.

The bulk of the work is:

- security-tool design
- policy design
- wrapper quality
- evidence normalization

## Target Capability 2: Multiple Tasks Running in Parallel

### What this means

You want cases like:

- one task doing port scan while another does directory scan
- several directory scans running at the same time
- a parent security workflow coordinating multiple child operations

### Current limitation

The current architecture is fundamentally single-active-loop per shell.

Right now:

- one shell can bind one task at a time
- one prompt creates one run
- the agent loop is interactive and foreground-oriented
- task execution is resumable, but not concurrent

This is the biggest architecture gap between the current codebase and your target direction.

### Why this is hard

Parallel security workflows are not just "run more tools".

They require:

- concurrent execution model
- task scheduler or job runner
- process lifecycle management
- output capture
- cancellation handling
- timeout handling
- resource controls
- target and rate limits
- run isolation

Today, the runtime model is:

- user prompt
- one loop
- one run
- checkpoint

What you need is closer to:

- orchestration task
- many child jobs
- background execution
- partial result collection
- parent task aggregation

### Architectural options

#### Option A: keep current task model and add background jobs

Add a new persisted `Job` layer under `Task`.

Example:

- `Task`
  - represents the operator goal
- `Run`
  - represents one agent-driven planning/execution turn
- `Job`
  - represents one concrete background action such as a scan

This is the most practical next step.

#### Option B: treat each scan as a task

This is simpler at first, but it scales poorly because:

- parent-child coordination becomes awkward
- UI becomes noisy
- checkpoint semantics become confused

This can work for prototypes, but it is not the right long-term model.

### Technical recommendation

If the project wants true parallel red-team workflows, add:

- `Job` model
- `JobService`
- background runner process or worker pool
- task-to-job linking
- job logs
- job status model
- cancellation and timeout semantics

Without that layer, "parallel tasks" will remain mostly manual rather than real.

### Difficulty

High.

This is the single biggest technical step on the roadmap toward a mature red-team agent.

## Target Capability 3: Multi-Window or Multi-Pane Task Display

### What this means

If multiple scans or jobs are active, the operator needs to see:

- which jobs are running
- their latest result
- which target each is hitting
- whether something failed
- whether a job needs confirmation or intervention

### Current limitation

The current CLI is improved, but it is still fundamentally a single interactive terminal session.

You can inspect tasks and runs, but you do not yet have:

- multiple live panes
- split task dashboards
- background status boards
- streaming concurrent views

### What is actually needed

Strictly speaking, "multi-window" is a presentation problem only after the runtime supports real concurrency.

So the dependency order matters:

1. build concurrent execution first
2. define observable job state
3. then build multi-pane UI on top of that state

### Implementation options

#### Option A: terminal multiplexer style inside Rich

Build a dashboard view with:

- active jobs table
- selected job detail
- recent task logs
- current task summary

This is the easiest path inside the current CLI technology stack.

#### Option B: separate TUI application

Move from a command shell to a proper text UI with:

- panes
- focus
- refresh loop
- key-driven navigation

This is more powerful, but also a bigger product shift.

#### Option C: web UI

This is not necessary for the first red-team version.

The current project is local-first and CLI-first. A web UI can wait.

### Technical recommendation

Do not start with true multi-window support.

Start with:

- background jobs
- a live `/task monitor <id>` or `/jobs` dashboard
- Rich auto-refresh panels/tables

Once that works, a larger TUI can be considered.

### Difficulty

Medium by itself, high if attempted before background execution exists.

## Main Technical Challenges

## 1. Safe network-capable execution

The current safety model is file and shell oriented.

A red-team agent needs target-aware policy, for example:

- allowed CIDRs
- allowed hostnames
- allowed ports
- allowed protocols
- rate limits
- scope boundaries per task

Without that, the project risks becoming "prompted shell automation with audit logs", which is not enough.

## 2. Structured security tools

Security tasks produce messy outputs.

You need wrappers that normalize:

- command arguments
- evidence
- findings
- exit status
- partial success

If everything goes through generic shell output, the agent will be harder to trust and harder to inspect.

## 3. Concurrency and orchestration

Parallel scanning requires:

- queueing
- worker ownership
- cancellation
- resource limits
- aggregation

This is not solved by the current `TaskRunner`.

## 4. Scope control and ethics boundary

Even for a local red-team agent, safety needs to move beyond generic execution policy.

The runtime needs explicit scoping, such as:

- approved target list per task
- mandatory target declaration at task creation
- hard block outside declared scope
- skill restrictions that cannot be widened by prompt text

## 5. Evidence and reporting

Security work is not only about running tools.
It is about producing useful operator output:

- what was checked
- what was found
- confidence level
- evidence
- next step

That means findings need to become first-class structured outputs, not just free-form assistant text.

## Feasibility Analysis

## Overall feasibility

Feasible, but only if the project grows in the right order.

The current codebase is already good enough to support:

- skill-based specialization
- persisted task-oriented workflows
- richer security-tool wrappers
- auditable execution

It is not yet good enough to support:

- real parallel offensive workflows
- safe network-scoped automation
- multi-pane monitoring

## Feasibility by target

### 1. Skill-based red-team toolbox

Feasibility: high

Reason:

- the current skill system is already usable
- local skill loading already exists
- skill activation model already exists

Needed work:

- add structured security tools
- add stronger target policy
- add domain reporting conventions

### 2. Parallel red-team execution

Feasibility: medium

Reason:

- the persistence model is promising
- but the runtime is still single-loop and foreground-oriented

Needed work:

- new `Job` layer
- background workers
- orchestration semantics

### 3. Multi-window display

Feasibility: medium

Reason:

- Rich UI already exists
- but there is not yet real concurrent state to visualize

Needed work:

- active job registry
- refreshable dashboard
- eventually a fuller TUI

## What Is Necessary vs Optional

### Necessary for a real red-team agent

- typed security tools instead of relying mainly on raw shell calls
- target-aware safety policy
- parent task plus child job execution model
- background execution support
- structured findings and evidence summaries
- job-level observability

### Useful but not immediately necessary

- multi-pane TUI
- web UI
- remote orchestration
- distributed workers
- broad plugin marketplace

## Recommended Implementation Order

## Phase A: Safe security-tool foundation

Build first-class security tools, for example:

- `port_scan`
- `dir_scan`
- `http_probe`
- `dns_lookup`
- `cve_check`

Each should expose:

- structured arguments
- target validation
- normalized results
- audit-friendly summaries

## Phase B: Scope-aware policy model

Extend the safety system so tasks can declare allowed scope:

- hosts
- CIDRs
- protocols
- rate limits

The executor should hard-block out-of-scope actions.

## Phase C: Job model for concurrency

Add:

- `Job`
- `JobStatus`
- `JobService`
- worker runner
- parent task aggregation

This is the real turning point for parallel scanning.

## Phase D: Monitoring UI

Add CLI monitoring features such as:

- `/jobs`
- `/task monitor <id>`
- live dashboards
- selected job detail view

Only after this should a larger TUI or multi-window model be considered.

## Phase E: Domain reporting and findings model

Add first-class security findings:

- severity
- evidence
- affected target
- confidence
- remediation or next action

## Bottom-Line Assessment

The project is a credible foundation for a local red-team agent, but it is still a foundation.

Its strongest current advantages are:

- explicit skill architecture
- persistent task/run/checkpoint runtime
- auditable local execution model
- improving CLI ergonomics

Its biggest missing pieces for your stated goal are:

- structured red-team tools
- target-aware safety scope
- true concurrent execution
- UI for monitoring concurrent work

The most important design decision is this:

Do not treat "red-team agent" as only a prompt-and-skill problem.

It is mainly a runtime, safety, orchestration, and observability problem.

If the project grows in that order, the direction is feasible.
If it grows by only adding more skills and shell commands, it will become fragile quickly.
