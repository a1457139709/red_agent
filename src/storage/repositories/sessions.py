from __future__ import annotations

from models.session import Session, SessionMode, SessionStatus
from storage.sqlite import SQLiteStorage

from ._common import allocate_public_id, get_row_by_identifier


SESSIONS_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    public_id TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    goal TEXT NOT NULL,
    mode TEXT NOT NULL,
    persistence_mode TEXT NOT NULL,
    workspace TEXT NOT NULL,
    status TEXT NOT NULL,
    target_summary TEXT,
    authorization_note TEXT,
    targets_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    closed_at TEXT,
    last_error TEXT,
    metadata TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_sessions_updated_at ON sessions(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_mode ON sessions(mode);
CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status);
"""


class SessionRepository:
    def __init__(self, storage: SQLiteStorage) -> None:
        self.storage = storage
        self._ensure_schema()

    def create(self, session: Session) -> Session:
        with self.storage.connect() as connection:
            if not session.public_id:
                session.public_id = allocate_public_id(
                    connection,
                    table_name="sessions",
                    prefix="S",
                )
            connection.execute(
                """
                INSERT INTO sessions (
                    id, public_id, title, goal, mode, persistence_mode, workspace, status,
                    target_summary, authorization_note, targets_json, created_at, updated_at,
                    closed_at, last_error, metadata
                ) VALUES (
                    :id, :public_id, :title, :goal, :mode, :persistence_mode, :workspace, :status,
                    :target_summary, :authorization_note, :targets_json, :created_at, :updated_at,
                    :closed_at, :last_error, :metadata
                )
                """,
                session.to_row(),
            )
            connection.commit()
        return session

    def get(self, identifier: str) -> Session | None:
        with self.storage.connect() as connection:
            row = get_row_by_identifier(
                connection,
                table_name="sessions",
                identifier=identifier,
                order_column="updated_at",
            )
        return Session.from_row(dict(row)) if row else None

    def require(self, identifier: str) -> Session:
        session = self.get(identifier)
        if session is None:
            raise ValueError(f"Session not found: {identifier}")
        return session

    def list(
        self,
        *,
        mode: SessionMode | None = None,
        status: SessionStatus | None = None,
        title_query: str | None = None,
        limit: int | None = 50,
    ) -> list[Session]:
        query = "SELECT * FROM sessions"
        params: list[object] = []
        conditions: list[str] = []

        if mode is not None:
            conditions.append("mode = ?")
            params.append(SessionMode(mode).value)
        if status is not None:
            conditions.append("status = ?")
            params.append(SessionStatus(status).value)
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
        return [Session.from_row(dict(row)) for row in rows]

    def update(self, session: Session) -> Session:
        with self.storage.connect() as connection:
            connection.execute(
                """
                UPDATE sessions
                SET
                    public_id = :public_id,
                    title = :title,
                    goal = :goal,
                    mode = :mode,
                    persistence_mode = :persistence_mode,
                    workspace = :workspace,
                    status = :status,
                    target_summary = :target_summary,
                    authorization_note = :authorization_note,
                    targets_json = :targets_json,
                    created_at = :created_at,
                    updated_at = :updated_at,
                    closed_at = :closed_at,
                    last_error = :last_error,
                    metadata = :metadata
                WHERE id = :id
                """,
                session.to_row(),
            )
            connection.commit()
        return session

    def _ensure_schema(self) -> None:
        with self.storage.connect() as connection:
            connection.executescript(SESSIONS_SCHEMA)
            connection.commit()
