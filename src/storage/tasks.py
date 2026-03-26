from __future__ import annotations

from models.task import Task, TaskStatus
from .sqlite import SQLiteStorage


TASKS_SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    goal TEXT NOT NULL,
    workspace TEXT NOT NULL,
    status TEXT NOT NULL,
    session_id TEXT,
    skill_profile TEXT,
    priority INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_checkpoint TEXT,
    last_error TEXT,
    metadata TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_updated_at ON tasks(updated_at DESC);
"""


class TaskRepository:
    def __init__(self, storage: SQLiteStorage) -> None:
        self.storage = storage
        self._ensure_schema()

    def create(self, task: Task) -> Task:
        row = task.to_row()
        with self.storage.connect() as connection:
            connection.execute(
                """
                INSERT INTO tasks (
                    id, title, goal, workspace, status, session_id, skill_profile,
                    priority, created_at, updated_at, last_checkpoint, last_error, metadata
                ) VALUES (
                    :id, :title, :goal, :workspace, :status, :session_id, :skill_profile,
                    :priority, :created_at, :updated_at, :last_checkpoint, :last_error, :metadata
                )
                """,
                row,
            )
            connection.commit()
        return task

    def get(self, task_id: str) -> Task | None:
        with self.storage.connect() as connection:
            row = connection.execute(
                "SELECT * FROM tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
        return Task.from_row(dict(row)) if row else None

    def list(self, *, status: TaskStatus | None = None, limit: int | None = None) -> list[Task]:
        query = "SELECT * FROM tasks"
        params: list = []

        if status is not None:
            query += " WHERE status = ?"
            params.append(status.value)

        query += " ORDER BY updated_at DESC"

        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)

        with self.storage.connect() as connection:
            rows = connection.execute(query, params).fetchall()

        return [Task.from_row(dict(row)) for row in rows]

    def update(self, task: Task) -> Task:
        row = task.to_row()
        with self.storage.connect() as connection:
            connection.execute(
                """
                UPDATE tasks
                SET
                    title = :title,
                    goal = :goal,
                    workspace = :workspace,
                    status = :status,
                    session_id = :session_id,
                    skill_profile = :skill_profile,
                    priority = :priority,
                    created_at = :created_at,
                    updated_at = :updated_at,
                    last_checkpoint = :last_checkpoint,
                    last_error = :last_error,
                    metadata = :metadata
                WHERE id = :id
                """,
                row,
            )
            connection.commit()
        return task

    def _ensure_schema(self) -> None:
        with self.storage.connect() as connection:
            connection.executescript(TASKS_SCHEMA)
            connection.commit()
