from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil


@dataclass(frozen=True, slots=True)
class OperationArtifacts:
    app_data_dir: Path
    operation_id: str

    @property
    def operations_root(self) -> Path:
        return self.app_data_dir / "operations"

    @property
    def operation_dir(self) -> Path:
        return self.operations_root / self.operation_id

    @property
    def evidence_dir(self) -> Path:
        return self.operation_dir / "evidence"

    @property
    def planner_dir(self) -> Path:
        return self.operation_dir / "planner"

    @property
    def exports_dir(self) -> Path:
        return self.operation_dir / "exports"

    def ensure(self) -> "OperationArtifacts":
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        self.planner_dir.mkdir(parents=True, exist_ok=True)
        self.exports_dir.mkdir(parents=True, exist_ok=True)
        return self

    def delete(self) -> None:
        if self.operation_dir.exists():
            shutil.rmtree(self.operation_dir)
