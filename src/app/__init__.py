from __future__ import annotations

from importlib import import_module

__all__ = [
    "ArtifactService",
    "AttackPathService",
    "CheckpointService",
    "ConfirmationPolicyService",
    "DashboardService",
    "EventStreamService",
    "ExecutionService",
    "InteractionPort",
    "FindingService",
    "JobService",
    "MemoryService",
    "ProjectService",
    "RedteamSessionService",
    "RunService",
    "ScannerService",
    "SessionEventService",
    "SessionInteractionService",
    "SessionRecordLocator",
    "SessionService",
    "ScopePolicyService",
    "TargetSessionService",
    "TerminalService",
    "ToolAccessPolicyService",
    "WriteupService",
]

_EXPORTS = {
    "ArtifactService": ".artifact_service",
    "AttackPathService": ".attack_path_service",
    "CheckpointService": ".checkpoint_service",
    "ConfirmationPolicyService": ".confirmation_policy_service",
    "DashboardService": ".dashboard_service",
    "EventStreamService": ".event_stream_service",
    "ExecutionService": ".execution_service",
    "InteractionPort": ".interaction_port",
    "FindingService": ".finding_service",
    "JobService": ".job_service",
    "MemoryService": ".memory_service",
    "ProjectService": ".project_service",
    "RedteamSessionService": ".redteam_session_service",
    "RunService": ".run_service",
    "ScannerService": ".scanner_service",
    "SessionEventService": ".session_event_service",
    "SessionInteractionService": ".session_interaction_service",
    "SessionRecordLocator": ".session_record_locator",
    "SessionService": ".session_service",
    "ScopePolicyService": ".scope_policy_service",
    "TargetSessionService": ".target_session_service",
    "TerminalService": ".terminal_service",
    "ToolAccessPolicyService": ".tool_access_policy_service",
    "WriteupService": ".writeup_service",
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
