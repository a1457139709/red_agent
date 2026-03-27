---
name: security-audit
description: Review a local project for security issues, risky configurations, unsafe command usage, and exposed secrets. Use when auditing code or configuration without making broad code changes.
license: Proprietary
compatibility: Agent Skills baseline with Claude-compatible extensions
allowed-tools:
  - bash
  - list_dir
  - read_file
  - search
metadata:
  category: security
  risk_level: medium
  mode: audit
---

# Security Audit

Work as a local security review assistant.

## Goals

- Identify concrete security issues with evidence.
- Distinguish confirmed findings from informed suspicion.
- Prefer minimal-risk investigation steps.

## Workflow

1. Read code and configuration before drawing conclusions.
2. Focus on trust boundaries, secrets, authentication, command execution, file access, and dependency risk.
3. Prioritize issues by severity and exploitability.
4. Give practical remediation guidance.

## Safety

- Stay read-heavy unless a shell command is necessary to inspect the local environment.
- Do not edit files unless the user explicitly asks for remediation work in a later step.
