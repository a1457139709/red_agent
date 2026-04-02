from __future__ import annotations

from domain.operations import Operation, OperationStatus
from storage.redteam import RedTeamStorage


class OperationRepository:
    def __init__(self, storage: RedTeamStorage) -> None:
        self.storage = storage

    def create(self, operation: Operation) -> Operation:
        with self.storage.connect() as connection:
            operation.public_id = self._allocate_public_id(connection)
            connection.execute(
                """
                INSERT INTO operations (
                    id, public_id, title, objective, workspace, status, planner_profile,
                    memory_profile_id, created_at, updated_at, closed_at,
                    last_error_code, last_error_message
                ) VALUES (
                    :id, :public_id, :title, :objective, :workspace, :status, :planner_profile,
                    :memory_profile_id, :created_at, :updated_at, :closed_at,
                    :last_error_code, :last_error_message
                )
                """,
                operation.to_row(),
            )
            connection.commit()
        return operation

    def get(self, identifier: str) -> Operation | None:
        with self.storage.connect() as connection:
            row = connection.execute(
                "SELECT * FROM operations WHERE public_id = ? OR id = ?",
                (identifier, identifier),
            ).fetchone()
        return Operation.from_row(dict(row)) if row else None

    def list(
        self,
        *,
        status: OperationStatus | None = None,
        limit: int | None = None,
    ) -> list[Operation]:
        query = "SELECT * FROM operations"
        params: list[object] = []
        if status is not None:
            query += " WHERE status = ?"
            params.append(status.value)
        query += " ORDER BY updated_at DESC"
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        with self.storage.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [Operation.from_row(dict(row)) for row in rows]

    def update(self, operation: Operation) -> Operation:
        with self.storage.connect() as connection:
            connection.execute(
                """
                UPDATE operations
                SET
                    public_id = :public_id,
                    title = :title,
                    objective = :objective,
                    workspace = :workspace,
                    status = :status,
                    planner_profile = :planner_profile,
                    memory_profile_id = :memory_profile_id,
                    created_at = :created_at,
                    updated_at = :updated_at,
                    closed_at = :closed_at,
                    last_error_code = :last_error_code,
                    last_error_message = :last_error_message
                WHERE id = :id
                """,
                operation.to_row(),
            )
            connection.commit()
        return operation

    def delete(self, operation_id: str) -> None:
        with self.storage.connect() as connection:
            connection.execute("DELETE FROM operations WHERE id = ?", (operation_id,))
            connection.commit()

    def _allocate_public_id(self, connection) -> str:
        row = connection.execute(
            """
            SELECT public_id
            FROM operations
            WHERE public_id LIKE 'O%'
            ORDER BY CAST(SUBSTR(public_id, 2) AS INTEGER) DESC
            LIMIT 1
            """
        ).fetchone()
        next_number = 1
        if row is not None and row["public_id"]:
            next_number = int(str(row["public_id"])[1:]) + 1
        return f"O{next_number:04d}"
