from __future__ import annotations

from pathlib import Path
from typing import Any

from domain.evidence import EvidenceMaterializer
from tools.contracts import ToolExecutionReport
from tools.redteam_registry import RedTeamToolRegistry


class RedTeamToolExecutor:
    def __init__(self, registry: RedTeamToolRegistry, *, app_data_dir: Path) -> None:
        self.registry = registry
        self.materializer = EvidenceMaterializer(app_data_dir)

    def execute(self, tool_name: str, request: Any) -> ToolExecutionReport:
        tool = self.registry.get(tool_name)
        result = tool.execute(request)
        materialized = self.materializer.materialize(request.operation_id, result.evidence_items)
        return ToolExecutionReport(result=result, materialized_evidence=materialized)
