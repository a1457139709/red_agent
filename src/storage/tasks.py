from __future__ import annotations

from models.task import Task, TaskStatus
from .sqlite import SQLiteStorage


TASKS_SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    public_id TEXT,
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

CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_public_id ON tasks(public_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_updated_at ON tasks(updated_at DESC);
"""


class TaskRepository:
    def __init__(self, storage: SQLiteStorage) -> None:
        self.storage = storage
        self._ensure_schema()

    def create(self, task: Task) -> Task:
        with self.storage.connect() as connection:
            public_id = self._allocate_public_id(connection)
            task.public_id = public_id
            row = task.to_row()
            connection.execute(
                """
                INSERT INTO tasks (
                    id, public_id, title, goal, workspace, status, session_id, skill_profile,
                    priority, created_at, updated_at, last_checkpoint, last_error, metadata
                ) VALUES (
                    :id, :public_id, :title, :goal, :workspace, :status, :session_id, :skill_profile,
                    :priority, :created_at, :updated_at, :last_checkpoint, :last_error, :metadata
                )
                """,
                row,
            )
            connection.commit()
        return task

    def get(self, task_id: str) -> Task | None:
        with self.storage.connect() as connection:
            row = self._get_row_by_identifier(connection, task_id)
        return Task.from_row(dict(row)) if row else None

    def list(
        self,
        *,
        status: TaskStatus | None = None,
        title_query: str | None = None,
        limit: int | None = None,
    ) -> list[Task]:
        query = "SELECT * FROM tasks"
        params: list = []
        conditions: list[str] = []

        if status is not None:
            conditions.append("status = ?")
            params.append(status.value)

        if title_query:
            conditions.append("LOWER(title) LIKE ?")
            params.append(f"%{title_query.lower()}%")

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

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
                    public_id = :public_id,
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
            self._ensure_public_id_column(connection)
            self._backfill_public_ids(connection)
            connection.commit()

    def _ensure_public_id_column(self, connection) -> None:
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(tasks)").fetchall()
        }
        if "public_id" not in columns:
            connection.execute("ALTER TABLE tasks ADD COLUMN public_id TEXT")
            connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_public_id ON tasks(public_id)")

    def _get_row_by_identifier(self, connection, identifier: str):
        row = connection.execute(
            "SELECT * FROM tasks WHERE public_id = ?",
            (identifier,),
        ).fetchone()
        if row is not None:
            return row

        row = connection.execute(
            "SELECT * FROM tasks WHERE id = ?",
            (identifier,),
        ).fetchone()
        if row is not None:
            return row

        prefix_rows = connection.execute(
            "SELECT * FROM tasks WHERE id LIKE ? ORDER BY updated_at DESC LIMIT 2",
            (f"{identifier}%",),
        ).fetchall()
        if len(prefix_rows) == 1:
            return prefix_rows[0]
        return None

    def _allocate_public_id(self, connection) -> str:
        row = connection.execute(
            """
            SELECT public_id
            FROM tasks
            WHERE public_id LIKE 'T%'
            ORDER BY CAST(SUBSTR(public_id, 2) AS INTEGER) DESC
            LIMIT 1
            """
        ).fetchone()
        next_number = 1
        if row is not None and row["public_id"]:
            try:
                next_number = int(str(row["public_id"])[1:]) + 1
            except ValueError:
                next_number = 1
        return f"T{next_number:04d}"

    def _backfill_public_ids(self, connection) -> None:
        rows = connection.execute(
            "SELECT id FROM tasks WHERE public_id IS NULL OR public_id = '' ORDER BY created_at ASC, id ASC"
        ).fetchall()
        for row in rows:
            connection.execute(
                "UPDATE tasks SET public_id = ? WHERE id = ?",
                (self._allocate_public_id(connection), row["id"]),
            )
