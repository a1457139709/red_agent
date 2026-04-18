from __future__ import annotations

from models.report import Report
from storage.schema_guard import ensure_phase6_clean_runtime_reset
from storage.sqlite import SQLiteStorage

from ._common import allocate_public_id, get_row_by_identifier
from .sessions import SessionRepository


REPORTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS reports (
    id TEXT PRIMARY KEY,
    public_id TEXT,
    session_id TEXT NOT NULL,
    report_type TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    artifact_path TEXT,
    created_at TEXT NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(session_id) REFERENCES sessions(id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_reports_public_id ON reports(public_id);
CREATE INDEX IF NOT EXISTS idx_reports_session_created_at ON reports(session_id, created_at DESC);
"""


class ReportRepository:
    def __init__(self, storage: SQLiteStorage) -> None:
        self.storage = storage
        self._ensure_schema()

    def create(self, report: Report) -> Report:
        with self.storage.connect() as connection:
            self._create_with_connection(connection, report)
            connection.commit()
        return report

    def get(self, identifier: str) -> Report | None:
        with self.storage.connect() as connection:
            row = get_row_by_identifier(
                connection,
                table_name="reports",
                identifier=identifier,
                order_column="created_at",
            )
        return Report.from_row(dict(row)) if row else None

    def list(self, session_id: str, *, limit: int | None = 50) -> list[Report]:
        query = "SELECT * FROM reports WHERE session_id = ? ORDER BY created_at DESC"
        params: list[object] = [session_id]
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        with self.storage.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [Report.from_row(dict(row)) for row in rows]

    def count(self, session_id: str) -> int:
        with self.storage.connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM reports WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return int(row["count"]) if row is not None else 0

    def update(self, report: Report) -> Report:
        with self.storage.connect() as connection:
            self._update_with_connection(connection, report)
            connection.commit()
        return report

    def _create_with_connection(self, connection, report: Report) -> Report:
        report.public_id = allocate_public_id(connection, table_name="reports", prefix="RP")
        connection.execute(
            """
            INSERT INTO reports (
                id, public_id, session_id, report_type, title, summary, artifact_path, created_at, metadata
            ) VALUES (
                :id, :public_id, :session_id, :report_type, :title, :summary, :artifact_path, :created_at, :metadata
            )
            """,
            report.to_row(),
        )
        return report

    def _update_with_connection(self, connection, report: Report) -> Report:
        connection.execute(
            """
            UPDATE reports
            SET
                public_id = :public_id,
                session_id = :session_id,
                report_type = :report_type,
                title = :title,
                summary = :summary,
                artifact_path = :artifact_path,
                created_at = :created_at,
                metadata = :metadata
            WHERE id = :id
            """,
            report.to_row(),
        )
        return report

    def _ensure_schema(self) -> None:
        SessionRepository(self.storage)
        with self.storage.connect() as connection:
            ensure_phase6_clean_runtime_reset(connection, app_data_dir=self.storage.db_path.parent)
            connection.executescript(REPORTS_SCHEMA)
            connection.commit()
