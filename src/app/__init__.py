from __future__ import annotations

from importlib import import_module

__all__ = [
    "ArtifactService",
    "CheckpointService",
    "ConfirmationPolicyService",
    "DashboardService",
    "ExecutionService",
    "EvidenceService",
    "FindingService",
    "JobService",
    "MemoryService",
    "OperationService",
    "OperationEventService",
    "ReportService",
    "RunService",
    "SessionEventService",
    "SessionRecordLocator",
    "SessionService",
    "ScopePolicyService",
    "TaskService",
    "ToolAccessPolicyService",
]

_EXPORTS = {
    "ArtifactService": ".artifact_service",
    "CheckpointService": ".checkpoint_service",
    "ConfirmationPolicyService": ".confirmation_policy_service",
    "DashboardService": ".dashboard_service",
    "ExecutionService": ".execution_service",
    "EvidenceService": ".evidence_service",
    "FindingService": ".finding_service",
    "JobService": ".job_service",
    "MemoryService": ".memory_service",
    "OperationService": ".operation_service",
    "OperationEventService": ".operation_event_service",
    "ReportService": ".report_service",
    "RunService": ".run_service",
    "SessionEventService": ".session_event_service",
    "SessionRecordLocator": ".session_record_locator",
    "SessionService": ".session_service",
    "ScopePolicyService": ".scope_policy_service",
    "TaskService": ".task_service",
    "ToolAccessPolicyService": ".tool_access_policy_service",
}


def __getattr__(name: str) -> object:
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(module_name, __name__)
    value = getattr(module, name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
