from __future__ import annotations

from models.operation import Operation, OperationStatus
from storage.sqlite import SQLiteStorage

from ._common import allocate_public_id, get_row_by_identifier


OPERATIONS_SCHEMA = """
CREATE TABLE IF NOT EXISTS operations (
    id TEXT PRIMARY KEY,
    public_id TEXT,
    title TEXT NOT NULL,
    objective TEXT NOT NULL,
    workspace TEXT NOT NULL,
    status TEXT NOT NULL,
    scope_policy_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    closed_at TEXT,
    last_error TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_operations_public_id ON operations(public_id);
CREATE INDEX IF NOT EXISTS idx_operations_status ON operations(status);
CREATE INDEX IF NOT EXISTS idx_operations_updated_at ON operations(updated_at DESC);
"""


class OperationRepository:
    def __init__(self, storage: SQLiteStorage) -> None:
        self.storage = storage
        self._ensure_schema()

    def create(self, operation: Operation) -> Operation:
        with self.storage.connect() as connection:
            self._create_with_connection(connection, operation)
            connection.commit()
        return operation

    def get(self, identifier: str) -> Operation | None:
        with self.storage.connect() as connection:
            row = get_row_by_identifier(
                connection,
                table_name="operations",
                identifier=identifier,
                order_column="updated_at",
            )
        return Operation.from_row(dict(row)) if row else None

    def list(
        self,
        *,
        status: OperationStatus | None = None,
        title_query: str | None = None,
        limit: int | None = 50,
    ) -> list[Operation]:
        query = "SELECT * FROM operations"
        params: list[object] = []
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
        return [Operation.from_row(dict(row)) for row in rows]

    def update(self, operation: Operation) -> Operation:
        with self.storage.connect() as connection:
            self._update_with_connection(connection, operation)
            connection.commit()
        return operation

    def _create_with_connection(self, connection, operation: Operation) -> Operation:
        operation.public_id = allocate_public_id(connection, table_name="operations", prefix="O")
        connection.execute(
            """
            INSERT INTO operations (
                id, public_id, title, objective, workspace, status, scope_policy_id,
                created_at, updated_at, closed_at, last_error
            ) VALUES (
                :id, :public_id, :title, :objective, :workspace, :status, :scope_policy_id,
                :created_at, :updated_at, :closed_at, :last_error
            )
            """,
            operation.to_row(),
        )
        return operation

    def _update_with_connection(self, connection, operation: Operation) -> Operation:
        connection.execute(
            """
            UPDATE operations
            SET
                public_id = :public_id,
                title = :title,
                objective = :objective,
                workspace = :workspace,
                status = :status,
                scope_policy_id = :scope_policy_id,
                created_at = :created_at,
                updated_at = :updated_at,
                closed_at = :closed_at,
                last_error = :last_error
            WHERE id = :id
            """,
            operation.to_row(),
        )
        return operation

    def _ensure_schema(self) -> None:
        with self.storage.connect() as connection:
            connection.executescript(OPERATIONS_SCHEMA)
            connection.commit()
