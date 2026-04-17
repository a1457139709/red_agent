from __future__ import annotations

from models.finding_artifact_link import FindingArtifactLink
from storage.schema_guard import ensure_phase6_clean_runtime_reset
from storage.sqlite import SQLiteStorage

from .sessions import SessionRepository


FINDING_ARTIFACT_LINKS_SCHEMA = """
CREATE TABLE IF NOT EXISTS finding_artifact_links (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    finding_id TEXT NOT NULL,
    artifact_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(session_id) REFERENCES sessions(id),
    FOREIGN KEY(finding_id) REFERENCES findings(id),
    FOREIGN KEY(artifact_id) REFERENCES artifacts(id),
    UNIQUE(finding_id, artifact_id)
);

CREATE INDEX IF NOT EXISTS idx_finding_artifact_links_session
ON finding_artifact_links(session_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_finding_artifact_links_finding
ON finding_artifact_links(finding_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_finding_artifact_links_artifact
ON finding_artifact_links(artifact_id, created_at DESC);
"""


class FindingArtifactLinkRepository:
    def __init__(self, storage: SQLiteStorage) -> None:
        self.storage = storage
        self._ensure_schema()

    def create(self, link: FindingArtifactLink) -> FindingArtifactLink:
        with self.storage.connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO finding_artifact_links (
                    id, session_id, finding_id, artifact_id, created_at
                ) VALUES (
                    :id, :session_id, :finding_id, :artifact_id, :created_at
                )
                """,
                link.to_row(),
            )
            connection.commit()
            row = connection.execute(
                """
                SELECT *
                FROM finding_artifact_links
                WHERE finding_id = ? AND artifact_id = ?
                """,
                (link.finding_id, link.artifact_id),
            ).fetchone()
        if row is None:
            raise ValueError("Failed to create finding-artifact link.")
        return FindingArtifactLink.from_row(dict(row))

    def list(self, session_id: str) -> list[FindingArtifactLink]:
        with self.storage.connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM finding_artifact_links
                WHERE session_id = ?
                ORDER BY created_at DESC
                """,
                (session_id,),
            ).fetchall()
        return [FindingArtifactLink.from_row(dict(row)) for row in rows]

    def list_for_finding(self, finding_id: str) -> list[FindingArtifactLink]:
        with self.storage.connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM finding_artifact_links
                WHERE finding_id = ?
                ORDER BY created_at DESC
                """,
                (finding_id,),
            ).fetchall()
        return [FindingArtifactLink.from_row(dict(row)) for row in rows]

    def list_for_artifact(self, artifact_id: str) -> list[FindingArtifactLink]:
        with self.storage.connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM finding_artifact_links
                WHERE artifact_id = ?
                ORDER BY created_at DESC
                """,
                (artifact_id,),
            ).fetchall()
        return [FindingArtifactLink.from_row(dict(row)) for row in rows]

    def _ensure_schema(self) -> None:
        SessionRepository(self.storage)
        with self.storage.connect() as connection:
            ensure_phase6_clean_runtime_reset(connection, app_data_dir=self.storage.db_path.parent)
            connection.executescript(FINDING_ARTIFACT_LINKS_SCHEMA)
            connection.commit()
