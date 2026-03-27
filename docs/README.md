# Documentation Index

This folder now contains only the current, maintained documentation for the Python codebase.

## Keep Reading These First

1. `architecture.md`
   Current runtime architecture, module boundaries, and execution flow.
2. `task-runtime.md`
   Persisted task model, run lifecycle, checkpoints, CLI task commands, and current skill-aware execution flow.
3. `engineering-development-plan.en.md`
   Current development roadmap after the first `SKILL.md` runtime slice.
4. `skill-system-standard.md`
   Current `SKILL.md`-based skill standard and compatibility rules.

## Maintenance Rules

- `docs/` should describe the current Python implementation, not historical experiments.
- If a document becomes stale, rewrite it or remove it.
- Do not keep imported design notes from other projects unless they are clearly marked as historical and still useful.
- When code and docs disagree, update the docs immediately after confirming the code path.

## Removed Legacy Docs

The previous topic docs that described old TypeScript-era or otherwise stale designs were removed on purpose. Their responsibilities are now covered by:

- `architecture.md`
- `task-runtime.md`
- `engineering-development-plan.en.md`
- `skill-system-standard.md`
