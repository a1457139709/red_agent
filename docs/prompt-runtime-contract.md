# Prompt Runtime Contract

## Summary

This document defines the maintained contract for the runtime prompt layer in `mini-claude-code`.

The runtime prompt is assembled in this order:

1. base prompt
2. skill prompt
3. context summary

The base prompt is stored in `src/SYSTEM_PROMPT.md`.

## Responsibilities

### Base Prompt Responsibilities

The base prompt is responsible for the stable runtime behavior that should apply even when no skill is active.

It should define:

- agent identity and role
- tool-use discipline
- safety and permission behavior
- task/run/checkpoint awareness
- response expectations
- editing discipline
- hard constraints

The base prompt should not contain domain-specific workflows that belong to a skill.

### Skill Prompt Responsibilities

A skill prompt is an explicit overlay that narrows or specializes behavior for a task or one-shot invocation.

A skill prompt should define:

- when that skill should be used
- domain-specific workflow
- output expectations for that domain
- any special safety boundaries or references relevant to that skill

Skills should not redefine the base runtime identity unless that is absolutely necessary.

### Context Summary Responsibilities

The context summary is runtime state, not a second base prompt.

It should carry:

- compressed prior context
- recovered working state
- recent relevant history when the live message history has been compressed

It should not redefine stable global behavior.

## What Belongs Where

Put content in the base prompt when it is:

- always true for the agent
- independent of skill choice
- about safety, truthfulness, tool discipline, or runtime behavior

Put content in a skill when it is:

- domain-specific
- workflow-specific
- tailored to a particular task family
- about narrowing visible tools or specialized references

Put content in the context summary when it is:

- task-local
- turn-local
- recovered from prior state

## Language Policy

The current prompt policy is:

- the base runtime prompt is written in English
- user-facing replies default to English
- code, paths, commands, tool names, and identifiers remain literal

This policy may be changed later, but it should be treated as part of the maintained prompt contract until intentionally revised.

## Why the Base Prompt Is Prescriptive

The base prompt is intentionally prescriptive because this agent:

- uses real local tools
- runs inside a safety-enforced executor
- supports persisted tasks and checkpoints
- can operate with or without explicit skills

The base prompt needs to anchor safe, stable behavior before any skill overlay is applied.

## Runtime Alignment Rules

The base prompt must stay aligned with the actual runtime:

- base mode may run with no skill
- skills are explicit overlays
- visible tools may be filtered by skill
- the executor enforces capability-based safety
- tasks, runs, checkpoints, and logs are real persisted concepts

Do not document or encode behavior in the base prompt that implies:

- multi-user collaboration
- SaaS deployment
- unsupported tools
- autonomous background execution
- implicit default skill loading
