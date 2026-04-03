---
name: git-auto-commit
description: Summarize the current local git repository changes and create a focused commit. Use when a user asks to inspect the latest modified, staged, or untracked files in the current repository, explain the change set, and commit it.
license: Proprietary
compatibility: Agent Skills baseline with Claude-compatible extensions
allowed-tools:
  - bash
  - list_dir
  - read_file
  - search
metadata:
  category: development
  risk_level: medium
  mode: commit
argument-hint: summarize the current git changes and create a commit
user-invocable: true
shell: powershell
---

# Git Auto Commit

Work as a careful local git commit assistant.

## Goals

- Inspect the current working tree before committing.
- Summarize the change set in plain language.
- Create a focused commit message that matches the actual diff.
- Avoid committing obviously unrelated, generated, or sensitive files.

## Workflow

1. Confirm the current directory is inside a git repository with `git rev-parse --is-inside-work-tree`.
2. Inspect the worktree with:
   `git status --short`
   `git diff --stat`
   `git diff --cached --stat`
   `git diff --cached`
   `git diff`
3. If the diff is large, narrow inspection with `git diff -- <path>` and `read_file` for the most important changed files.
4. Separate staged and unstaged changes. Treat an already staged subset as an intentional boundary unless the user explicitly asks to restage everything.
5. Write a short summary of what changed before committing.
6. Choose a commit scope:
   - If files are already staged, prefer committing the staged set as-is.
   - If nothing is staged and the changes form one coherent unit, stage the relevant files with `git add <path>`.
   - If the changes appear unrelated, stop and ask whether to split or narrow the commit instead of creating a catch-all commit.
7. Create a concise commit message:
   - Prefer a one-line imperative subject.
   - Mention the primary behavior change, not implementation trivia.
   - Add a body only when it clarifies non-obvious context.
8. Run `git commit -m "<subject>"` or `git commit -m "<subject>" -m "<body>"`.
9. After committing, report the summary, the commit message, and the latest commit header with `git show --stat --oneline --no-patch HEAD`.

## Safety

- Do not commit when `git status --short` is empty.
- Do not use `git commit -a` or `git add -A` blindly when the repository contains unrelated or surprising changes.
- Exclude obvious noise such as `.pyc`, `__pycache__`, build artifacts, virtual environments, secrets, and local env files unless the user explicitly asks.
- Do not rewrite history, amend commits, or push unless the user asks.
- If git reports conflicts, unresolved merges, or hook failures, stop and explain the blocker.