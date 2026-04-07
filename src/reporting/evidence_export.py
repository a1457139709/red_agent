from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re

from agent.settings import Settings, get_settings
from app.evidence_service import EvidenceService
from app.finding_service import FindingService
from app.job_service import JobService
from app.operation_service import OperationService
from models.run import utc_now_iso

from .findings_summary import (
    build_evidence_index_export,
    build_findings_export,
    build_operation_summary,
)


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "export"


@dataclass(frozen=True, slots=True)
class OperationExportResult:
    operation_id: str
    operation_public_id: str
    export_dir: Path
    files: list[Path]


class EvidenceExportService:
    def __init__(
        self,
        *,
        operation_service: OperationService,
        job_service: JobService,
        evidence_service: EvidenceService,
        finding_service: FindingService,
        settings: Settings,
    ) -> None:
        self.operation_service = operation_service
        self.job_service = job_service
        self.evidence_service = evidence_service
        self.finding_service = finding_service
        self.settings = settings

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "EvidenceExportService":
        settings = settings or get_settings()
        return cls(
            operation_service=OperationService.from_settings(settings),
            job_service=JobService.from_settings(settings),
            evidence_service=EvidenceService.from_settings(settings),
            finding_service=FindingService.from_settings(settings),
            settings=settings,
        )

    def generate_operation_export(
        self,
        operation_identifier: str,
        export_name: str | None = None,
    ) -> OperationExportResult:
        operation = self.operation_service.require_operation(operation_identifier)
        policy = self.operation_service.require_scope_policy(operation.id)
        jobs = self.job_service.list_jobs(operation.id, limit=None)
        evidence = self.evidence_service.list_evidence(operation.id, limit=None)
        findings = self.finding_service.list_findings(operation.id, limit=None)
        links = self.finding_service.list_links(operation.id)

        export_label = _slugify(export_name or utc_now_iso().replace(":", "-"))
        export_dir = (
            self.settings.app_data_dir
            / "operations"
            / operation.public_id
            / "exports"
            / export_label
        )
        export_dir.mkdir(parents=True, exist_ok=True)

        evidence_by_id = {item.id: item for item in evidence}
        findings_by_id = {item.id: item for item in findings}

        files = [
            self._write_json(
                export_dir / "operation-summary.json",
                build_operation_summary(
                    operation=operation,
                    policy=policy,
                    jobs=jobs,
                    evidence=evidence,
                    findings=findings,
                ),
            ),
            self._write_json(
                export_dir / "findings.json",
                build_findings_export(
                    findings=findings,
                    links=links,
                    evidence_by_id=evidence_by_id,
                ),
            ),
            self._write_json(
                export_dir / "evidence-index.json",
                build_evidence_index_export(
                    evidence=evidence,
                    links=links,
                    findings_by_id=findings_by_id,
                ),
            ),
        ]

        return OperationExportResult(
            operation_id=operation.id,
            operation_public_id=operation.public_id,
            export_dir=export_dir,
            files=files,
        )

    def _write_json(self, path: Path, payload: object) -> Path:
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return path
