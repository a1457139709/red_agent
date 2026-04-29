from __future__ import annotations

from pathlib import Path
import sqlite3


LEGACY_RUNTIME_TABLES = (
    "runs",
    "task_logs",
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

LEGACY_INCOMPATIBLE_TABLES = {
    "checkpoints": "older checkpoint schema",
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

    for table_name, reason in LEGACY_INCOMPATIBLE_TABLES.items():
        exists = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table_name,),
        ).fetchone()
        if exists is None:
            continue
        blocking_sources.append(reason)

    legacy_operations_dir = app_data_dir / "operations"
    if legacy_operations_dir.exists() and any(legacy_operations_dir.iterdir()):
        blocking_sources.append(f"path:{legacy_operations_dir}")

    if not blocking_sources:
        return

    sources = ", ".join(blocking_sources)
    raise ValueError(
        "Legacy runtime storage detected for the retired pre-session layout "
        f"({sources}). This local database is test-only and can be recreated. "
        "Delete `.red-code/agent.db` and the legacy `.red-code/operations/` directory "
        "before starting the current runtime."
    )
