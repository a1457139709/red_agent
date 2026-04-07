from __future__ import annotations

from models.finding_evidence_link import FindingEvidenceLink
from storage.sqlite import SQLiteStorage


FINDING_EVIDENCE_LINKS_SCHEMA = """
CREATE TABLE IF NOT EXISTS finding_evidence_links (
    id TEXT PRIMARY KEY,
    operation_id TEXT NOT NULL,
    finding_id TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(operation_id) REFERENCES operations(id),
    FOREIGN KEY(finding_id) REFERENCES findings(id),
    FOREIGN KEY(evidence_id) REFERENCES evidence(id),
    UNIQUE(finding_id, evidence_id)
);

CREATE INDEX IF NOT EXISTS idx_finding_evidence_links_operation
ON finding_evidence_links(operation_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_finding_evidence_links_finding
ON finding_evidence_links(finding_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_finding_evidence_links_evidence
ON finding_evidence_links(evidence_id, created_at DESC);
"""


class FindingEvidenceLinkRepository:
    def __init__(self, storage: SQLiteStorage) -> None:
        self.storage = storage
        self._ensure_schema()

    def create(self, link: FindingEvidenceLink) -> FindingEvidenceLink:
        with self.storage.connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO finding_evidence_links (
                    id, operation_id, finding_id, evidence_id, created_at
                ) VALUES (
                    :id, :operation_id, :finding_id, :evidence_id, :created_at
                )
                """,
                link.to_row(),
            )
            connection.commit()
            row = connection.execute(
                """
                SELECT *
                FROM finding_evidence_links
                WHERE finding_id = ? AND evidence_id = ?
                """,
                (link.finding_id, link.evidence_id),
            ).fetchone()
        if row is None:
            raise ValueError("Failed to create finding-evidence link.")
        return FindingEvidenceLink.from_row(dict(row))

    def list(self, operation_id: str) -> list[FindingEvidenceLink]:
        with self.storage.connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM finding_evidence_links
                WHERE operation_id = ?
                ORDER BY created_at DESC
                """,
                (operation_id,),
            ).fetchall()
        return [FindingEvidenceLink.from_row(dict(row)) for row in rows]

    def list_for_finding(self, finding_id: str) -> list[FindingEvidenceLink]:
        with self.storage.connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM finding_evidence_links
                WHERE finding_id = ?
                ORDER BY created_at DESC
                """,
                (finding_id,),
            ).fetchall()
        return [FindingEvidenceLink.from_row(dict(row)) for row in rows]

    def list_for_evidence(self, evidence_id: str) -> list[FindingEvidenceLink]:
        with self.storage.connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM finding_evidence_links
                WHERE evidence_id = ?
                ORDER BY created_at DESC
                """,
                (evidence_id,),
            ).fetchall()
        return [FindingEvidenceLink.from_row(dict(row)) for row in rows]

    def _ensure_schema(self) -> None:
        with self.storage.connect() as connection:
            connection.executescript(FINDING_EVIDENCE_LINKS_SCHEMA)
            connection.commit()
