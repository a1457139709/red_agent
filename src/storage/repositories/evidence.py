from __future__ import annotations

from models.evidence import Evidence
from storage.sqlite import SQLiteStorage

from ._common import allocate_public_id, get_row_by_identifier


EVIDENCE_SCHEMA = """
CREATE TABLE IF NOT EXISTS evidence (
    id TEXT PRIMARY KEY,
    public_id TEXT,
    operation_id TEXT NOT NULL,
    job_id TEXT,
    evidence_type TEXT NOT NULL,
    target_ref TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    artifact_path TEXT,
    content_type TEXT,
    hash_digest TEXT,
    captured_at TEXT NOT NULL,
    FOREIGN KEY(operation_id) REFERENCES operations(id),
    FOREIGN KEY(job_id) REFERENCES jobs(id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_evidence_public_id ON evidence(public_id);
CREATE INDEX IF NOT EXISTS idx_evidence_operation_captured_at ON evidence(operation_id, captured_at DESC);
"""


class EvidenceRepository:
    def __init__(self, storage: SQLiteStorage) -> None:
        self.storage = storage
        self._ensure_schema()

    def create(self, evidence: Evidence) -> Evidence:
        with self.storage.connect() as connection:
            evidence.public_id = allocate_public_id(connection, table_name="evidence", prefix="E")
            connection.execute(
                """
                INSERT INTO evidence (
                    id, public_id, operation_id, job_id, evidence_type, target_ref, title,
                    summary, artifact_path, content_type, hash_digest, captured_at
                ) VALUES (
                    :id, :public_id, :operation_id, :job_id, :evidence_type, :target_ref, :title,
                    :summary, :artifact_path, :content_type, :hash_digest, :captured_at
                )
                """,
                evidence.to_row(),
            )
            connection.commit()
        return evidence

    def get(self, identifier: str) -> Evidence | None:
        with self.storage.connect() as connection:
            row = get_row_by_identifier(
                connection,
                table_name="evidence",
                identifier=identifier,
                order_column="captured_at",
            )
        return Evidence.from_row(dict(row)) if row else None

    def list(self, operation_id: str, *, limit: int | None = 50) -> list[Evidence]:
        query = "SELECT * FROM evidence WHERE operation_id = ? ORDER BY captured_at DESC"
        params: list[object] = [operation_id]
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        with self.storage.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [Evidence.from_row(dict(row)) for row in rows]

    def update(self, evidence: Evidence) -> Evidence:
        with self.storage.connect() as connection:
            connection.execute(
                """
                UPDATE evidence
                SET
                    public_id = :public_id,
                    operation_id = :operation_id,
                    job_id = :job_id,
                    evidence_type = :evidence_type,
                    target_ref = :target_ref,
                    title = :title,
                    summary = :summary,
                    artifact_path = :artifact_path,
                    content_type = :content_type,
                    hash_digest = :hash_digest,
                    captured_at = :captured_at
                WHERE id = :id
                """,
                evidence.to_row(),
            )
            connection.commit()
        return evidence

    def _ensure_schema(self) -> None:
        with self.storage.connect() as connection:
            connection.executescript(EVIDENCE_SCHEMA)
            connection.commit()
