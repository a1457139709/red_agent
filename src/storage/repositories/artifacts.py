from __future__ import annotations

import re

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
            artifact.public_id = allocate_public_id(connection, table_name="artifacts", prefix="A")
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

    def count(self, session_id: str) -> int:
        with self.storage.connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM artifacts WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return int(row["count"]) if row is not None else 0

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
            self._migrate_legacy_public_ids(connection)
            connection.commit()

    def _migrate_legacy_public_ids(self, connection) -> None:
        legacy_rows = connection.execute(
            """
            SELECT id, public_id, captured_at
            FROM artifacts
            WHERE public_id LIKE 'E%'
            """
        ).fetchall()
        if not legacy_rows:
            return

        rows = connection.execute(
            """
            SELECT id, public_id, captured_at
            FROM artifacts
            """
        ).fetchall()
        ordered_rows = sorted(
            rows,
            key=lambda row: (
                self._public_id_sort_key(row["public_id"]),
                row["captured_at"],
                row["id"],
            ),
        )

        connection.execute("UPDATE artifacts SET public_id = NULL")
        for index, row in enumerate(ordered_rows, start=1):
            connection.execute(
                "UPDATE artifacts SET public_id = ? WHERE id = ?",
                (f"A{index:04d}", row["id"]),
            )

    def _public_id_sort_key(self, public_id: str | None) -> tuple[int, int, str]:
        if not public_id:
            return (1, 0, "")
        match = re.fullmatch(r"[AE](\d+)", str(public_id))
        if match is None:
            return (1, 0, str(public_id))
        return (0, int(match.group(1)), str(public_id))
