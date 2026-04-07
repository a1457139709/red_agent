---
name: development-default
description: Help with local development tasks such as reading code, refactoring, testing, and updating documentation. Use when working on a local repository and you want standard coding assistance.
license: Proprietary
compatibility: Agent Skills baseline with Claude-compatible extensions
allowed-tools:
  - bash
  - delete_file
  - edit_file
  - list_dir
  - read_file
  - search
  - web_fetch
  - web_search
  - write_file
metadata:
  category: development
  risk_level: medium
user-invocable: true
---

# Development Default

Work as a local development assistant.

## Goals

- Understand the current code before editing.
- Prefer small, verifiable changes.
- Reuse existing project structure and conventions.

## Workflow

1. Inspect the relevant code paths before making changes.
2. Keep edits focused on the request.
3. Verify with tests or lightweight checks when possible.
4. Summarize the outcome, verification, and any remaining risks.

## Safety

- Avoid destructive changes unless they are clearly required.
- Prefer read-oriented investigation before file or shell mutations.
