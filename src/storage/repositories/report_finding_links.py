from __future__ import annotations

from models.report_finding_link import ReportFindingLink
from storage.schema_guard import ensure_phase6_clean_runtime_reset
from storage.sqlite import SQLiteStorage

from .sessions import SessionRepository


REPORT_FINDING_LINKS_SCHEMA = """
CREATE TABLE IF NOT EXISTS report_finding_links (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    report_id TEXT NOT NULL,
    finding_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(session_id) REFERENCES sessions(id),
    FOREIGN KEY(report_id) REFERENCES reports(id),
    FOREIGN KEY(finding_id) REFERENCES findings(id),
    UNIQUE(report_id, finding_id)
);

CREATE INDEX IF NOT EXISTS idx_report_finding_links_session
ON report_finding_links(session_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_report_finding_links_report
ON report_finding_links(report_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_report_finding_links_finding
ON report_finding_links(finding_id, created_at DESC);
"""


class ReportFindingLinkRepository:
    def __init__(self, storage: SQLiteStorage) -> None:
        self.storage = storage
        self._ensure_schema()

    def create(self, link: ReportFindingLink) -> ReportFindingLink:
        with self.storage.connect() as connection:
            self._create_with_connection(connection, link)
            connection.commit()
            row = connection.execute(
                """
                SELECT *
                FROM report_finding_links
                WHERE report_id = ? AND finding_id = ?
                """,
                (link.report_id, link.finding_id),
            ).fetchone()
        if row is None:
            raise ValueError("Failed to create report-finding link.")
        return ReportFindingLink.from_row(dict(row))

    def _create_with_connection(self, connection, link: ReportFindingLink) -> ReportFindingLink:
        connection.execute(
            """
            INSERT OR IGNORE INTO report_finding_links (
                id, session_id, report_id, finding_id, created_at
            ) VALUES (
                :id, :session_id, :report_id, :finding_id, :created_at
            )
            """,
            link.to_row(),
        )
        return link

    def list_for_report(self, report_id: str) -> list[ReportFindingLink]:
        with self.storage.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM report_finding_links WHERE report_id = ? ORDER BY created_at DESC",
                (report_id,),
            ).fetchall()
        return [ReportFindingLink.from_row(dict(row)) for row in rows]

    def _ensure_schema(self) -> None:
        SessionRepository(self.storage)
        with self.storage.connect() as connection:
            ensure_phase6_clean_runtime_reset(connection, app_data_dir=self.storage.db_path.parent)
            connection.executescript(REPORT_FINDING_LINKS_SCHEMA)
            connection.commit()
