from __future__ import annotations

from importlib import import_module

__all__ = [
    "ArtifactRepository",
    "AttackPathNodeRepository",
    "CommandRunRepository",
    "ControlCenterSchemaRepository",
    "EventRepository",
    "EvidenceRepository",
    "FlagRepository",
    "FindingRepository",
    "FindingArtifactLinkRepository",
    "JobRepository",
    "MemoryRepository",
    "ReportArtifactLinkRepository",
    "ReportFindingLinkRepository",
    "ReportRepository",
    "SessionRepository",
    "SessionEventRepository",
    "ScopePolicyRepository",
    "ProjectRepository",
    "TargetSessionRepository",
    "TaskRepository",
]

_EXPORTS = {
    "ArtifactRepository": ".artifacts",
    "AttackPathNodeRepository": ".control_center",
    "CommandRunRepository": ".control_center",
    "ControlCenterSchemaRepository": ".control_center",
    "EventRepository": ".control_center",
    "EvidenceRepository": ".control_center",
    "FlagRepository": ".control_center",
    "FindingRepository": ".findings",
    "FindingArtifactLinkRepository": ".finding_artifact_links",
    "JobRepository": ".jobs",
    "MemoryRepository": ".memory",
    "ReportArtifactLinkRepository": ".report_artifact_links",
    "ReportFindingLinkRepository": ".report_finding_links",
    "ReportRepository": ".reports",
    "SessionRepository": ".sessions",
    "SessionEventRepository": ".session_events",
    "ScopePolicyRepository": ".scope_policies",
    "ProjectRepository": ".control_center",
    "TargetSessionRepository": ".control_center",
    "TaskRepository": ".control_center",
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
