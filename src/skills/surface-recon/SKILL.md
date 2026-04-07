---
name: surface-recon
description: Generate a bounded reconnaissance job plan for a hostname or URL using the v2 security runtime. Use when you want deterministic DNS, HTTP, and TLS discovery jobs inside an operation scope.
license: Proprietary
compatibility: Agent Skills baseline with Claude-compatible extensions
allowed-tools:
  - bash
  - list_dir
  - read_file
metadata:
  category: security
  risk_level: medium
  mode: workflow
user-invocable: true
disable-model-invocation: true
shell: powershell
workflow-profile: surface-recon
---

# Surface Recon

Work as a bounded red-team workflow skill.

## Goals

- Turn a hostname or URL into a deterministic reconnaissance plan.
- Keep scope control in runtime code rather than prompt instructions.
- Preview the jobs before creating them.

## Workflow

1. Use `/skill plan surface-recon <operation_id>` to preview the generated jobs.
2. Use `/skill apply surface-recon <operation_id>` to create the approved jobs.
3. Provide a primary target and optional JSON overrides when prompted.

## Outputs

- `dns_lookup` for hostnames when enabled
- derived `http_probe` jobs
- an optional `tls_inspect` job

## Safety

- This skill is workflow-only and does not support freeform model invocation.
- Scope, protocol, port, and confirmation enforcement stay in the v2 runtime.
