from __future__ import annotations

from models.artifact import Artifact
from storage.schema_guard import ensure_phase6_clean_runtime_reset
from storage.sqlite import SQLiteStorage

from ._common import allocate_public_id, get_row_by_identifier
from .sessions import SessionRepository


ARTIFACTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS artifacts (
    id TEXT PRIMARY KEY,
    public_id TEXT,
    session_id TEXT NOT NULL,
    source_job_id TEXT,
    artifact_type TEXT NOT NULL,
    target_ref TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    artifact_path TEXT,
    content_type TEXT,
    hash_digest TEXT,
    captured_at TEXT NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(session_id) REFERENCES sessions(id),
    FOREIGN KEY(source_job_id) REFERENCES session_jobs(id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_artifacts_public_id ON artifacts(public_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_session_captured_at ON artifacts(session_id, captured_at DESC);
"""


class ArtifactRepository:
    def __init__(self, storage: SQLiteStorage) -> None:
        self.storage = storage
        self._ensure_schema()

    def create(self, artifact: Artifact) -> Artifact:
        with self.storage.connect() as connection:
            artifact.public_id = allocate_public_id(connection, table_name="artifacts", prefix="E")
            connection.execute(
                """
                INSERT INTO artifacts (
                    id, public_id, session_id, source_job_id, artifact_type, target_ref, title,
                    summary, artifact_path, content_type, hash_digest, captured_at, metadata
                ) VALUES (
                    :id, :public_id, :session_id, :source_job_id, :artifact_type, :target_ref, :title,
                    :summary, :artifact_path, :content_type, :hash_digest, :captured_at, :metadata
                )
                """,
                artifact.to_row(),
            )
            connection.commit()
        return artifact

    def get(self, identifier: str) -> Artifact | None:
        with self.storage.connect() as connection:
            row = get_row_by_identifier(
                connection,
                table_name="artifacts",
                identifier=identifier,
                order_column="captured_at",
            )
        return Artifact.from_row(dict(row)) if row else None

    def list(self, session_id: str, *, limit: int | None = 50) -> list[Artifact]:
        query = "SELECT * FROM artifacts WHERE session_id = ? ORDER BY captured_at DESC"
        params: list[object] = [session_id]
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        with self.storage.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [Artifact.from_row(dict(row)) for row in rows]

    def update(self, artifact: Artifact) -> Artifact:
        with self.storage.connect() as connection:
            connection.execute(
                """
                UPDATE artifacts
                SET
                    public_id = :public_id,
                    session_id = :session_id,
                    source_job_id = :source_job_id,
                    artifact_type = :artifact_type,
                    target_ref = :target_ref,
                    title = :title,
                    summary = :summary,
                    artifact_path = :artifact_path,
                    content_type = :content_type,
                    hash_digest = :hash_digest,
                    captured_at = :captured_at,
                    metadata = :metadata
                WHERE id = :id
                """,
                artifact.to_row(),
            )
            connection.commit()
        return artifact

    def _ensure_schema(self) -> None:
        SessionRepository(self.storage)
        with self.storage.connect() as connection:
            ensure_phase6_clean_runtime_reset(connection, app_data_dir=self.storage.db_path.parent)
            connection.executescript(ARTIFACTS_SCHEMA)
            connection.commit()
