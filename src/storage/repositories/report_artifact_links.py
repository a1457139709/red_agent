from __future__ import annotations

from models.report_artifact_link import ReportArtifactLink
from storage.schema_guard import ensure_phase6_clean_runtime_reset
from storage.sqlite import SQLiteStorage

from .sessions import SessionRepository


REPORT_ARTIFACT_LINKS_SCHEMA = """
CREATE TABLE IF NOT EXISTS report_artifact_links (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    report_id TEXT NOT NULL,
    artifact_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(session_id) REFERENCES sessions(id),
    FOREIGN KEY(report_id) REFERENCES reports(id),
    FOREIGN KEY(artifact_id) REFERENCES artifacts(id),
    UNIQUE(report_id, artifact_id)
);

CREATE INDEX IF NOT EXISTS idx_report_artifact_links_session
ON report_artifact_links(session_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_report_artifact_links_report
ON report_artifact_links(report_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_report_artifact_links_artifact
ON report_artifact_links(artifact_id, created_at DESC);
"""


class ReportArtifactLinkRepository:
    def __init__(self, storage: SQLiteStorage) -> None:
        self.storage = storage
        self._ensure_schema()

    def create(self, link: ReportArtifactLink) -> ReportArtifactLink:
        with self.storage.connect() as connection:
            self._create_with_connection(connection, link)
            connection.commit()
            row = connection.execute(
                """
                SELECT *
                FROM report_artifact_links
                WHERE report_id = ? AND artifact_id = ?
                """,
                (link.report_id, link.artifact_id),
            ).fetchone()
        if row is None:
            raise ValueError("Failed to create report-artifact link.")
        return ReportArtifactLink.from_row(dict(row))

    def _create_with_connection(self, connection, link: ReportArtifactLink) -> ReportArtifactLink:
        connection.execute(
            """
            INSERT OR IGNORE INTO report_artifact_links (
                id, session_id, report_id, artifact_id, created_at
            ) VALUES (
                :id, :session_id, :report_id, :artifact_id, :created_at
            )
            """,
            link.to_row(),
        )
        return link

    def list_for_report(self, report_id: str) -> list[ReportArtifactLink]:
        with self.storage.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM report_artifact_links WHERE report_id = ? ORDER BY created_at DESC",
                (report_id,),
            ).fetchall()
        return [ReportArtifactLink.from_row(dict(row)) for row in rows]

    def _ensure_schema(self) -> None:
        SessionRepository(self.storage)
        with self.storage.connect() as connection:
            ensure_phase6_clean_runtime_reset(connection, app_data_dir=self.storage.db_path.parent)
            connection.executescript(REPORT_ARTIFACT_LINKS_SCHEMA)
            connection.commit()
