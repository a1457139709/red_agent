from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING
import re

from domain.operations import OperationArtifacts

if TYPE_CHECKING:
    from tools.contracts import EvidenceItem


_SLUG_RE = re.compile(r"[^a-zA-Z0-9]+")


@dataclass(frozen=True, slots=True)
class MaterializedEvidence:
    evidence_type: str
    title: str
    artifact_path: str
    content_type: str
    byte_size: int


class EvidenceMaterializer:
    def __init__(self, app_data_dir: Path) -> None:
        self.app_data_dir = Path(app_data_dir)

    def materialize(self, operation_id: str, evidence_items: list["EvidenceItem"]) -> list[MaterializedEvidence]:
        artifacts = OperationArtifacts(self.app_data_dir, operation_id).ensure()
        materialized: list[MaterializedEvidence] = []
        for index, item in enumerate(evidence_items, start=1):
            slug = self._slugify(item.filename_hint or item.title or item.evidence_type)
            extension = self._extension_for_content_type(item.content_type)
            filename = f"{index:02d}_{slug}.{extension}"
            output_path = artifacts.evidence_dir / filename

            if isinstance(item.content, bytes):
                output_path.write_bytes(item.content)
                byte_size = len(item.content)
            else:
                output_path.write_text(item.content, encoding="utf-8")
                byte_size = len(item.content.encode("utf-8"))

            materialized.append(
                MaterializedEvidence(
                    evidence_type=item.evidence_type,
                    title=item.title,
                    artifact_path=str(output_path.relative_to(self.app_data_dir)),
                    content_type=item.content_type,
                    byte_size=byte_size,
                )
            )
        return materialized

    def _slugify(self, value: str) -> str:
        candidate = _SLUG_RE.sub("-", value.strip()).strip("-").lower()
        return candidate or "artifact"

    def _extension_for_content_type(self, content_type: str) -> str:
        mapping = {
            "text/plain": "txt",
            "application/json": "json",
        }
        return mapping.get(content_type, "bin")
