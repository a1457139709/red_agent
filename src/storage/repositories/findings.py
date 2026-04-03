from __future__ import annotations

from models.finding import Finding
from storage.sqlite import SQLiteStorage

from ._common import allocate_public_id, get_row_by_identifier


FINDINGS_SCHEMA = """
CREATE TABLE IF NOT EXISTS findings (
    id TEXT PRIMARY KEY,
    public_id TEXT,
    operation_id TEXT NOT NULL,
    source_job_id TEXT,
    finding_type TEXT NOT NULL,
    title TEXT NOT NULL,
    target_ref TEXT NOT NULL,
    severity TEXT NOT NULL,
    confidence TEXT NOT NULL,
    status TEXT NOT NULL,
    summary TEXT NOT NULL,
    impact TEXT NOT NULL,
    reproduction_notes TEXT NOT NULL,
    next_action TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(operation_id) REFERENCES operations(id),
    FOREIGN KEY(source_job_id) REFERENCES jobs(id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_findings_public_id ON findings(public_id);
CREATE INDEX IF NOT EXISTS idx_findings_operation_updated_at ON findings(operation_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_findings_status ON findings(status);
"""


class FindingRepository:
    def __init__(self, storage: SQLiteStorage) -> None:
        self.storage = storage
        self._ensure_schema()

    def create(self, finding: Finding) -> Finding:
        with self.storage.connect() as connection:
            finding.public_id = allocate_public_id(connection, table_name="findings", prefix="F")
            connection.execute(
                """
                INSERT INTO findings (
                    id, public_id, operation_id, source_job_id, finding_type, title, target_ref,
                    severity, confidence, status, summary, impact, reproduction_notes, next_action,
                    created_at, updated_at
                ) VALUES (
                    :id, :public_id, :operation_id, :source_job_id, :finding_type, :title, :target_ref,
                    :severity, :confidence, :status, :summary, :impact, :reproduction_notes, :next_action,
                    :created_at, :updated_at
                )
                """,
                finding.to_row(),
            )
            connection.commit()
        return finding

    def get(self, identifier: str) -> Finding | None:
        with self.storage.connect() as connection:
            row = get_row_by_identifier(
                connection,
                table_name="findings",
                identifier=identifier,
                order_column="updated_at",
            )
        return Finding.from_row(dict(row)) if row else None

    def list(self, operation_id: str, *, limit: int | None = 50) -> list[Finding]:
        query = "SELECT * FROM findings WHERE operation_id = ? ORDER BY updated_at DESC"
        params: list[object] = [operation_id]
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        with self.storage.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [Finding.from_row(dict(row)) for row in rows]

    def update(self, finding: Finding) -> Finding:
        with self.storage.connect() as connection:
            connection.execute(
                """
                UPDATE findings
                SET
                    public_id = :public_id,
                    operation_id = :operation_id,
                    source_job_id = :source_job_id,
                    finding_type = :finding_type,
                    title = :title,
                    target_ref = :target_ref,
                    severity = :severity,
                    confidence = :confidence,
                    status = :status,
                    summary = :summary,
                    impact = :impact,
                    reproduction_notes = :reproduction_notes,
                    next_action = :next_action,
                    created_at = :created_at,
                    updated_at = :updated_at
                WHERE id = :id
                """,
                finding.to_row(),
            )
            connection.commit()
        return finding

    def _ensure_schema(self) -> None:
        with self.storage.connect() as connection:
            connection.executescript(FINDINGS_SCHEMA)
            connection.commit()
