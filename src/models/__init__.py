from __future__ import annotations

from importlib import import_module

__all__ = [
    "CheckpointRecord",
    "CheckpointSummary",
    "Evidence",
    "Finding",
    "FindingEvidenceLink",
    "FindingStatus",
    "Job",
    "JobLogEntry",
    "JobLogLevel",
    "JobStatus",
    "MemoryEntry",
    "Operation",
    "OperationStatus",
    "OperationEvent",
    "OperationEventLevel",
    "OperationEventType",
    "RiskLevel",
    "ConfirmationMode",
    "ConfirmationDecisionStatus",
    "ActionRiskPolicy",
    "RiskPolicyLimits",
    "RiskPolicyConfig",
    "ConfirmationRequestPayload",
    "ConfirmationDecision",
    "Run",
    "RunStatus",
    "Session",
    "SessionMode",
    "SessionPersistenceMode",
    "SessionStatus",
    "SessionTarget",
    "SessionTargetKind",
    "ScopePolicy",
    "StoredCheckpoint",
    "Task",
    "TaskLogEntry",
    "TaskLogLevel",
    "TaskStatus",
]

_EXPORTS = {
    "CheckpointRecord": ".checkpoint",
    "CheckpointSummary": ".checkpoint",
    "StoredCheckpoint": ".checkpoint",
    "Evidence": ".evidence",
    "Finding": ".finding",
    "FindingStatus": ".finding",
    "FindingEvidenceLink": ".finding_evidence_link",
    "Job": ".job",
    "JobLogEntry": ".job",
    "JobLogLevel": ".job",
    "JobStatus": ".job",
    "MemoryEntry": ".memory",
    "Operation": ".operation",
    "OperationStatus": ".operation",
    "OperationEvent": ".operation_event",
    "OperationEventLevel": ".operation_event",
    "OperationEventType": ".operation_event",
    "RiskLevel": ".risk_policy",
    "ConfirmationMode": ".risk_policy",
    "ConfirmationDecisionStatus": ".risk_policy",
    "ActionRiskPolicy": ".risk_policy",
    "RiskPolicyLimits": ".risk_policy",
    "RiskPolicyConfig": ".risk_policy",
    "ConfirmationRequestPayload": ".risk_policy",
    "ConfirmationDecision": ".risk_policy",
    "Run": ".run",
    "RunStatus": ".run",
    "Session": ".session",
    "SessionMode": ".session",
    "SessionPersistenceMode": ".session",
    "SessionStatus": ".session",
    "SessionTarget": ".session",
    "SessionTargetKind": ".session",
    "ScopePolicy": ".scope_policy",
    "Task": ".task",
    "TaskLogEntry": ".run",
    "TaskLogLevel": ".run",
    "TaskStatus": ".task",
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
