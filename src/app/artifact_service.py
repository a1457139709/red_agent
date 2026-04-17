from __future__ import annotations

from agent.settings import Settings, get_settings
from models.artifact import Artifact
from storage.repositories.artifacts import ArtifactRepository
from storage.repositories.jobs import JobRepository
from storage.repositories.operations import OperationRepository
from storage.sqlite import SQLiteStorage

from .session_scope import resolve_session_identifier
from .session_service import SessionService


class ArtifactService:
    def __init__(
        self,
        repository: ArtifactRepository,
        session_service: SessionService,
        operation_repository: OperationRepository,
        job_repository: JobRepository,
        settings: Settings,
    ) -> None:
        self.repository = repository
        self.session_service = session_service
        self.operation_repository = operation_repository
        self.job_repository = job_repository
        self.settings = settings

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "ArtifactService":
        settings = settings or get_settings()
        storage = SQLiteStorage(settings.sqlite_path)
        return cls(
            ArtifactRepository(storage),
            SessionService.from_settings(settings),
            OperationRepository(storage),
            JobRepository(storage),
            settings,
        )

    def create_artifact(
        self,
        *,
        session_identifier: str | None = None,
        operation_identifier: str | None = None,
        artifact_type: str,
        target_ref: str,
        title: str,
        summary: str,
        source_job_identifier: str | None = None,
        artifact_path: str | None = None,
        content_type: str | None = None,
        hash_digest: str | None = None,
        captured_at: str | None = None,
        metadata: dict | None = None,
    ) -> Artifact:
        session_id = self._resolve_session_id(session_identifier or operation_identifier)
        source_job_id: str | None = None
        if source_job_identifier is not None:
            job = self.job_repository.get(source_job_identifier)
            if job is None:
                raise ValueError(f"Job not found: {source_job_identifier}")
            if job.session_id != session_id:
                raise ValueError("Artifact source job must belong to the same session.")
            source_job_id = job.id

        artifact = Artifact.create(
            session_id=session_id,
            source_job_id=source_job_id,
            artifact_type=artifact_type,
            target_ref=target_ref,
            title=title,
            summary=summary,
            artifact_path=artifact_path,
            content_type=content_type,
            hash_digest=hash_digest,
            captured_at=captured_at,
            metadata=metadata,
        )
        return self.repository.create(artifact)

    def get_artifact(self, identifier: str) -> Artifact | None:
        return self.repository.get(identifier)

    def require_artifact(self, identifier: str) -> Artifact:
        artifact = self.get_artifact(identifier)
        if artifact is None:
            raise ValueError(f"Artifact not found: {identifier}")
        return artifact

    def list_artifacts(self, session_identifier: str, *, limit: int | None = 50) -> list[Artifact]:
        return self.repository.list(self._resolve_session_id(session_identifier), limit=limit)

    def save_artifact(self, artifact: Artifact) -> Artifact:
        return self.repository.update(artifact)

    def _resolve_session_id(self, identifier: str | None) -> str:
        if not identifier:
            raise ValueError("session_identifier is required.")
        return resolve_session_identifier(
            self.session_service,
            identifier,
            operation_repository=self.operation_repository,
        )
