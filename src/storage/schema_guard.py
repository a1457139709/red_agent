from __future__ import annotations

from pathlib import Path
import sqlite3


LEGACY_RUNTIME_TABLES = (
    "runs",
    "task_logs",
    "checkpoints",
    "jobs",
    "job_logs",
    "operation_events",
    "memory_entries",
    "evidence",
    "finding_evidence_links",
)

LEGACY_SCHEMA_TABLE_COLUMNS = {
    "findings": "operation_id",
    "scope_policies": "operation_id",
    "planner_plans": "operation_id",
}

LEGACY_SCHEMA_SHAPES = {
    "checkpoints": {"task_id", "payload"},
}


def ensure_phase6_clean_runtime_reset(connection: sqlite3.Connection, *, app_data_dir: Path) -> None:
    blocking_sources: list[str] = []
    for table_name in LEGACY_RUNTIME_TABLES:
        exists = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table_name,),
        ).fetchone()
        if exists is None:
            continue
        has_rows = connection.execute(
            f"SELECT 1 FROM {table_name} LIMIT 1"
        ).fetchone()
        if has_rows is not None:
            blocking_sources.append(f"table:{table_name}")

    for table_name, legacy_column in LEGACY_SCHEMA_TABLE_COLUMNS.items():
        exists = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table_name,),
        ).fetchone()
        if exists is None:
            continue
        columns = {
            row["name"]
            for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        }
        if legacy_column not in columns:
            continue
        has_rows = connection.execute(f"SELECT 1 FROM {table_name} LIMIT 1").fetchone()
        if has_rows is not None:
            blocking_sources.append(f"legacy-schema:{table_name}")

    for table_name, legacy_columns in LEGACY_SCHEMA_SHAPES.items():
        exists = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table_name,),
        ).fetchone()
        if exists is None:
            continue
        columns = {
            row["name"]
            for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        }
        if legacy_columns.issubset(columns):
            singular_name = table_name[:-1] if table_name.endswith("s") else table_name
            blocking_sources.append(f"older {singular_name} schema")

    legacy_operations_dir = app_data_dir / "operations"
    if legacy_operations_dir.exists() and any(legacy_operations_dir.iterdir()):
        blocking_sources.append(f"path:{legacy_operations_dir}")

    if not blocking_sources:
        return

    sources = ", ".join(blocking_sources)
    raise ValueError(
        "Legacy runtime storage detected for the pre-Phase 6 layout "
        f"({sources}). This local database is test-only and can be recreated. "
        "Delete `.red-code/agent.db` and `.red-code/operations/` before starting "
        "the Phase 6 runtime."
    )
