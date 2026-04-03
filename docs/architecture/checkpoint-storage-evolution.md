# Checkpoint Storage Redesign

## 1. Purpose

This document defines the next checkpoint storage architecture for the local agent runtime.

It replaces the current inline SQLite checkpoint approach with a cleaner model:

- SQLite stores only checkpoint metadata
- filesystem stores checkpoint blobs
- CLI consumes only checkpoint summaries
- no legacy compatibility layer is required

This is an intentional breaking change. The goal is to keep the future architecture clean instead of preserving an early-stage storage shape indefinitely.

## 2. Why We Are Changing It

The current checkpoint model stores the full serialized `SessionState` directly in SQLite.

That works as an early implementation, but it becomes a poor fit once tasks grow longer:

- `history` keeps expanding and duplicates across checkpoints
- the database becomes a large text snapshot store
- small state changes rewrite large JSON payloads
- checkpoint inspection and retention are harder to manage cleanly
- CLI behavior becomes coupled to storage internals

For a local single-user agent, SQLite is still the right persistence backbone, but it should act as the metadata index, not the blob store for large session snapshots.

## 3. Design Decision

Adopt a new checkpoint architecture with these rules:

1. SQLite stores only structured metadata for checkpoints.
2. Full `SessionState` snapshots are written to the filesystem as compressed blobs.
3. The runtime restores checkpoints by reading metadata first, then loading the blob.
4. CLI commands never read raw checkpoint payloads directly.
5. Old inline checkpoint rows are not supported by the new design.

This is a deliberate reset, not a hybrid migration.

## 4. Target Architecture

### 4.1 Metadata Layer

SQLite remains the system of record for:

- tasks
- runs
- task logs
- checkpoint metadata
- checkpoint-to-task/run relationships

### 4.2 Blob Layer

Filesystem becomes the storage backend for full checkpoint payloads.

Recommended layout:

```text
.red-code/
  agent.db
  checkpoints/
    2026/
      03/
        chk_<checkpoint_id>.json.gz
```

### 4.3 Service Layer

A dedicated `CheckpointService` owns:

- saving checkpoint blobs
- reading checkpoint blobs
- writing metadata
- loading `SessionState`
- exposing CLI-safe summaries
- deleting checkpoints
- pruning older checkpoints

The rest of the application should not know whether checkpoints are stored inline, in files, or in a future blob backend.

## 5. Data Model

### 5.1 SQLite `checkpoints` Table

The new `checkpoints` table should contain metadata only.

Required fields:

- `id`
- `task_id`
- `run_id`
- `created_at`
- `storage_kind`
- `blob_path`
- `blob_encoding`
- `payload_size_bytes`
- `payload_digest`
- `history_message_count`
- `history_text_bytes`
- `has_compressed_summary`

Field guidance:

- `storage_kind`
  - initial value: `file_blob`
- `blob_path`
  - path relative to `.red-code/`
- `blob_encoding`
  - initial value: `json+gzip`
- `payload_digest`
  - checksum used for blob integrity validation
- `history_message_count`
  - number of messages in `SessionState.history`
- `history_text_bytes`
  - approximate text size of serialized message content
- `has_compressed_summary`
  - whether `compressed_summary` is present

### 5.2 Blob Format

Each checkpoint blob stores a versioned payload:

```json
{
  "version": 2,
  "session_state": {
    "history": [],
    "compressed_summary": null,
    "last_usage": null
  }
}
```

Rules:

- only `version = 2` is supported in this redesign
- blobs are stored as UTF-8 JSON with `json+gzip` encoding
- the runtime must validate blob existence and digest before restore

Implementation note:

- checkpoint payloads must be serialized with `ensure_ascii=False` and encoded as UTF-8 before gzip compression so multilingual content restores losslessly
- user-visible shell output should be decoded with a UTF-8-first strategy plus Windows fallback encodings to avoid mojibake in CLI-visible tool responses

## 6. Runtime Boundaries

### 6.1 `CheckpointSummary`

This type is for CLI rendering and lightweight inspection.

Recommended fields:

- `id`
- `task_id`
- `run_id`
- `created_at`
- `storage_kind`
- `payload_size_bytes`
- `history_message_count`
- `history_text_bytes`
- `has_compressed_summary`

The CLI should depend only on this summary shape.

### 6.2 `CheckpointRecord`

This type is for internal loading and integrity checks.

Recommended fields:

- `id`
- `task_id`
- `run_id`
- `created_at`
- `blob_path`
- `blob_encoding`
- `payload_digest`

### 6.3 `CheckpointService`

Recommended interface:

- `save_checkpoint(task_id, session_state, run_id=None) -> CheckpointRecord`
- `load_checkpoint_state(checkpoint_id) -> SessionState`
- `get_checkpoint_summary(checkpoint_id) -> CheckpointSummary`
- `list_checkpoints(task_id, limit=20) -> list[CheckpointSummary]`
- `delete_checkpoint(checkpoint_id) -> None`
- `prune_checkpoints(task_id, keep_last=...) -> int`

Design rule:

- `TaskRunner` decides when to save or restore
- `CheckpointService` decides how checkpoint persistence works

## 7. CLI Contract

Future CLI checkpoint commands should expose metadata only.

Recommended commands:

- `/task checkpoints <task_id>`
- `/task checkpoint <checkpoint_id>`

The CLI may show:

- checkpoint ID
- created time
- storage kind
- payload size
- history message count
- compressed summary presence

The CLI must not:

- dump raw checkpoint JSON
- assume payloads live in SQLite
- read blob files directly

This keeps CLI behavior stable even if the storage backend changes later.

## 8. Breaking Change Policy

This redesign explicitly rejects automatic compatibility for the old inline checkpoint format.

Required policy:

1. add an `app_metadata` table with `schema_version`
2. define the new checkpoint architecture as `schema_version = 2`
3. if an old schema is detected, fail fast with a clear error
4. do not silently read legacy inline checkpoint rows
5. do not implement an automatic hybrid fallback

Recommended startup message:

> This workspace uses an older checkpoint schema. Delete or migrate `.red-code/agent.db` before running the new runtime.

This project is still in a rapid local-development phase. Clean architecture is more valuable than preserving every historical storage format.

## 9. Safety and Integrity Requirements

### 9.1 Atomic Write Strategy

Checkpoint writes should be durable and crash-resistant.

Recommended write order:

1. serialize session payload
2. compress payload
3. write to a temporary blob file
4. fsync if needed
5. atomically rename to final blob path
6. write SQLite metadata row

If metadata write fails after blob creation, the system may leave orphaned blobs. That is acceptable as long as periodic cleanup is supported.

### 9.2 Path Safety

Blob files must always live under:

```text
.red-code/checkpoints/
```

No caller-supplied absolute path should be accepted.

### 9.3 Integrity Validation

On restore, the runtime should validate:

- checkpoint row exists
- blob file exists
- blob digest matches
- payload version is supported

If any validation fails, restore should fail clearly and should not produce a partially restored `SessionState`.

## 10. Implementation Order

Recommended rollout order:

### Phase A

Introduce the new abstractions:

- `CheckpointSummary`
- `CheckpointRecord`
- `CheckpointService`

Move checkpoint responsibility out of `RunService`.

### Phase B

Create the new schema and blob writer/reader:

- metadata-only `checkpoints` table
- filesystem blob storage
- `json+gzip` encoding
- integrity digest support

### Phase C

Rewire task runtime:

- `TaskRunner.run_prompt()`
- `TaskRunner.resume_task()`
- `TaskRunner.detach_task()`
- `TaskRunner.complete_task()`

All checkpoint operations should go through `CheckpointService`.

### Phase D

Add CLI checkpoint inspection commands based on summary data only.

Status:

- implemented
- `/task checkpoints <task_id>`
- `/task checkpoint <checkpoint_id>`
- checkpoint deletion and pruning service APIs are also implemented

## 11. Non-Goals

This redesign does not include:

- backward compatibility with inline SQLite payload checkpoints
- automatic migration of old checkpoint rows
- diff-based checkpoints
- remote blob storage
- checkpoint content search
- automatic protection against deleting a task's currently referenced `last_checkpoint`

Those may be considered later, but they should not shape the new foundation.

## 12. Final Recommendation

The project should stop treating SQLite as a large snapshot warehouse.

The correct long-term architecture is:

- SQLite for metadata and indexing
- filesystem for full checkpoint blobs
- service boundaries for save/load/summary
- CLI based only on metadata

This is the cleanest path forward for a local, long-running, single-user agent runtime.