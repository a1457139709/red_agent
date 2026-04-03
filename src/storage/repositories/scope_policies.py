from __future__ import annotations

from models.scope_policy import ScopePolicy
from storage.sqlite import SQLiteStorage


SCOPE_POLICIES_SCHEMA = """
CREATE TABLE IF NOT EXISTS scope_policies (
    id TEXT PRIMARY KEY,
    operation_id TEXT NOT NULL UNIQUE,
    allowed_hosts TEXT NOT NULL DEFAULT '[]',
    allowed_domains TEXT NOT NULL DEFAULT '[]',
    allowed_cidrs TEXT NOT NULL DEFAULT '[]',
    allowed_ports TEXT NOT NULL DEFAULT '[]',
    allowed_protocols TEXT NOT NULL DEFAULT '[]',
    denied_targets TEXT NOT NULL DEFAULT '[]',
    allowed_tool_categories TEXT NOT NULL DEFAULT '[]',
    max_concurrency INTEGER NOT NULL DEFAULT 1,
    rate_limit_per_minute INTEGER,
    confirmation_required_actions TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(operation_id) REFERENCES operations(id)
);

CREATE INDEX IF NOT EXISTS idx_scope_policies_operation_id ON scope_policies(operation_id);
"""


class ScopePolicyRepository:
    def __init__(self, storage: SQLiteStorage) -> None:
        self.storage = storage
        self._ensure_schema()

    def create(self, policy: ScopePolicy) -> ScopePolicy:
        with self.storage.connect() as connection:
            self._create_with_connection(connection, policy)
            connection.commit()
        return policy

    def get(self, policy_id: str) -> ScopePolicy | None:
        with self.storage.connect() as connection:
            row = connection.execute(
                "SELECT * FROM scope_policies WHERE id = ?",
                (policy_id,),
            ).fetchone()
        return ScopePolicy.from_row(dict(row)) if row else None

    def get_by_operation_id(self, operation_id: str) -> ScopePolicy | None:
        with self.storage.connect() as connection:
            row = connection.execute(
                "SELECT * FROM scope_policies WHERE operation_id = ?",
                (operation_id,),
            ).fetchone()
        return ScopePolicy.from_row(dict(row)) if row else None

    def list(self, *, limit: int | None = 50) -> list[ScopePolicy]:
        query = "SELECT * FROM scope_policies ORDER BY updated_at DESC"
        params: list[object] = []
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        with self.storage.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [ScopePolicy.from_row(dict(row)) for row in rows]

    def update(self, policy: ScopePolicy) -> ScopePolicy:
        with self.storage.connect() as connection:
            self._update_with_connection(connection, policy)
            connection.commit()
        return policy

    def _create_with_connection(self, connection, policy: ScopePolicy) -> ScopePolicy:
        connection.execute(
            """
            INSERT INTO scope_policies (
                id, operation_id, allowed_hosts, allowed_domains, allowed_cidrs, allowed_ports,
                allowed_protocols, denied_targets, allowed_tool_categories, max_concurrency,
                rate_limit_per_minute, confirmation_required_actions, created_at, updated_at
            ) VALUES (
                :id, :operation_id, :allowed_hosts, :allowed_domains, :allowed_cidrs, :allowed_ports,
                :allowed_protocols, :denied_targets, :allowed_tool_categories, :max_concurrency,
                :rate_limit_per_minute, :confirmation_required_actions, :created_at, :updated_at
            )
            """,
            policy.to_row(),
        )
        return policy

    def _update_with_connection(self, connection, policy: ScopePolicy) -> ScopePolicy:
        connection.execute(
            """
            UPDATE scope_policies
            SET
                operation_id = :operation_id,
                allowed_hosts = :allowed_hosts,
                allowed_domains = :allowed_domains,
                allowed_cidrs = :allowed_cidrs,
                allowed_ports = :allowed_ports,
                allowed_protocols = :allowed_protocols,
                denied_targets = :denied_targets,
                allowed_tool_categories = :allowed_tool_categories,
                max_concurrency = :max_concurrency,
                rate_limit_per_minute = :rate_limit_per_minute,
                confirmation_required_actions = :confirmation_required_actions,
                created_at = :created_at,
                updated_at = :updated_at
            WHERE id = :id
            """,
            policy.to_row(),
        )
        return policy

    def _ensure_schema(self) -> None:
        with self.storage.connect() as connection:
            connection.executescript(SCOPE_POLICIES_SCHEMA)
            connection.commit()
