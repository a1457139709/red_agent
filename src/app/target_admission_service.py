from __future__ import annotations

from dataclasses import dataclass
from ipaddress import ip_address
from urllib.parse import urlsplit

from agent.settings import Settings, get_settings
from models.control_center import CampaignTarget, Event, TargetPoolStatus, TargetSource, TargetType
from models.run import utc_now_iso
from models.scope_policy import ScopePolicy
from orchestration.scope_validator import AdmissionOutcome, AdmissionRequest, ScopeValidator, TargetDescriptor
from storage.repositories.control_center import (
    CampaignTargetRepository,
    EventRepository,
    ProjectRepository,
    ProjectScopePolicyRepository,
)
from storage.sqlite import SQLiteStorage


@dataclass(frozen=True, slots=True)
class TargetAdmissionResult:
    status: str
    target: CampaignTarget
    reason: str


class TargetAdmissionService:
    def __init__(
        self,
        *,
        target_repository: CampaignTargetRepository,
        project_repository: ProjectRepository,
        scope_repository: ProjectScopePolicyRepository,
        event_repository: EventRepository,
        settings: Settings,
        scope_validator: ScopeValidator | None = None,
    ) -> None:
        self.target_repository = target_repository
        self.project_repository = project_repository
        self.scope_repository = scope_repository
        self.event_repository = event_repository
        self.settings = settings
        self.scope_validator = scope_validator or ScopeValidator()

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "TargetAdmissionService":
        settings = settings or get_settings()
        storage = SQLiteStorage(settings.sqlite_path)
        return cls(
            target_repository=CampaignTargetRepository(storage),
            project_repository=ProjectRepository(storage),
            scope_repository=ProjectScopePolicyRepository(storage),
            event_repository=EventRepository(storage),
            settings=settings,
        )

    def require_scope_policy(self, project_identifier: str) -> ScopePolicy:
        project = self.project_repository.require(project_identifier)
        policy = self.scope_repository.get_by_project_id(project.id)
        if policy is not None:
            return policy
        policy = ScopePolicy.create(session_id=project.id)
        return self.scope_repository.create(policy)

    def save_scope_policy(self, project_identifier: str, policy: ScopePolicy) -> ScopePolicy:
        project = self.project_repository.require(project_identifier)
        policy.session_id = project.id
        policy.updated_at = utc_now_iso()
        current = self.scope_repository.get_by_project_id(project.id)
        if current is None:
            return self.scope_repository.create(policy)
        policy.id = current.id
        policy.created_at = current.created_at
        return self.scope_repository.update(policy)

    def list_targets(
        self,
        *,
        project_identifier: str,
        status: TargetPoolStatus | None = None,
        limit: int | None = 50,
    ) -> list[CampaignTarget]:
        project = self.project_repository.require(project_identifier)
        return self.target_repository.list(project_id=project.id, status=status, limit=limit)

    def create_initial_target(
        self,
        *,
        project_identifier: str,
        value: str,
        target_type: TargetType,
        source: TargetSource = TargetSource.USER_ADDED,
    ) -> CampaignTarget:
        project = self.project_repository.require(project_identifier)
        descriptor = self._describe(value)
        existing = self.target_repository.find_by_value(project_id=project.id, value=value.strip())
        if existing is not None:
            return existing
        target = CampaignTarget.create(
            project_id=project.id,
            value=value,
            target_type=TargetType(target_type),
            normalized_host=descriptor.host,
            source=source,
            status=TargetPoolStatus.ACTIVE,
            scope_reason="initial target added by operator",
            rejection_key=_rejection_key(descriptor),
        )
        created = self.target_repository.create(target)
        policy = self.require_scope_policy(project.id)
        self._add_target_to_policy(policy, created)
        self.scope_repository.update(policy)
        return created

    def propose_target(
        self,
        *,
        project_identifier: str,
        value: str,
        source: TargetSource = TargetSource.AGENT_DISCOVERED,
        evidence_id: str | None = None,
        discovered_by: str | None = None,
        discovered_from: str | None = None,
    ) -> TargetAdmissionResult:
        project = self.project_repository.require(project_identifier)
        descriptor = self._describe(value)
        key = _rejection_key(descriptor)
        existing = self.target_repository.find_by_value(project_id=project.id, value=value.strip())
        if existing is not None:
            return TargetAdmissionResult(status=existing.status.value, target=existing, reason=existing.scope_reason or "target already exists")

        rejected = self.target_repository.find_rejected_by_key(project_id=project.id, rejection_key=key)
        if rejected is not None:
            target = self._create_target(
                project_id=project.id,
                value=value,
                descriptor=descriptor,
                source=source,
                status=TargetPoolStatus.REJECTED,
                scope_reason=f"matched previous rejected scope key {key}",
                rejection_key=key,
                evidence_id=evidence_id,
                discovered_by=discovered_by,
                discovered_from=discovered_from,
            )
            self._record_event(project_id=project.id, event_kind="target.rejected", target=target, reason=target.scope_reason)
            return TargetAdmissionResult(status="rejected", target=target, reason=target.scope_reason or "target rejected")

        policy = self.require_scope_policy(project.id)
        decision = self.scope_validator.evaluate(
            policy,
            AdmissionRequest(
                session_id=project.id,
                job_id=None,
                tool_name="target_admission",
                tool_category="recon",
                raw_target=value,
                protocol=descriptor.protocol,
                port=descriptor.port,
                skip_confirmation=True,
            ),
        )
        if decision.outcome == AdmissionOutcome.ALLOWED:
            target = self._create_target(
                project_id=project.id,
                value=value,
                descriptor=descriptor,
                source=source,
                status=TargetPoolStatus.ACTIVE,
                scope_reason=decision.message,
                rejection_key=key,
                evidence_id=evidence_id,
                discovered_by=discovered_by,
                discovered_from=discovered_from,
            )
            self._record_event(project_id=project.id, event_kind="target.accepted", target=target, reason=decision.message)
            return TargetAdmissionResult(status="accepted", target=target, reason=decision.message)

        if decision.reason_code == "target_denied":
            target = self._create_target(
                project_id=project.id,
                value=value,
                descriptor=descriptor,
                source=source,
                status=TargetPoolStatus.REJECTED,
                scope_reason=decision.message,
                rejection_key=key,
                evidence_id=evidence_id,
                discovered_by=discovered_by,
                discovered_from=discovered_from,
            )
            self._record_event(project_id=project.id, event_kind="target.rejected", target=target, reason=decision.message)
            return TargetAdmissionResult(status="rejected", target=target, reason=decision.message)

        target = self._create_target(
            project_id=project.id,
            value=value,
            descriptor=descriptor,
            source=source,
            status=TargetPoolStatus.PENDING,
            scope_reason=decision.message,
            rejection_key=key,
            evidence_id=evidence_id,
            discovered_by=discovered_by,
            discovered_from=discovered_from,
        )
        self._record_event(project_id=project.id, event_kind="target.review_required", target=target, reason=decision.message)
        return TargetAdmissionResult(status="pending_review", target=target, reason=decision.message)

    def approve_target(self, target_identifier: str) -> TargetAdmissionResult:
        target = self.target_repository.require(target_identifier)
        if target.status == TargetPoolStatus.ARCHIVED:
            raise ValueError("Archived targets cannot be approved.")
        policy = self.require_scope_policy(target.project_id)
        self._add_target_to_policy(policy, target)
        self.scope_repository.update(policy)
        target.status = TargetPoolStatus.ACTIVE
        target.scope_reason = "approved by operator and added to project scope"
        target.updated_at = utc_now_iso()
        updated = self.target_repository.update(target)
        self._record_event(project_id=updated.project_id, event_kind="target.approved", target=updated, reason=updated.scope_reason)
        return TargetAdmissionResult(status="accepted", target=updated, reason=updated.scope_reason)

    def reject_target(self, target_identifier: str) -> TargetAdmissionResult:
        target = self.target_repository.require(target_identifier)
        if target.status == TargetPoolStatus.ARCHIVED:
            raise ValueError("Archived targets cannot be rejected.")
        target.status = TargetPoolStatus.REJECTED
        target.scope_reason = "rejected by operator"
        target.rejection_key = target.rejection_key or _rejection_key(self._describe(target.value))
        target.updated_at = utc_now_iso()
        updated = self.target_repository.update(target)
        policy = self.require_scope_policy(updated.project_id)
        if updated.value not in policy.denied_targets:
            policy.denied_targets.append(updated.value)
            policy.updated_at = utc_now_iso()
            self.scope_repository.update(policy)
        self._record_event(project_id=updated.project_id, event_kind="target.rejected", target=updated, reason=updated.scope_reason)
        return TargetAdmissionResult(status="rejected", target=updated, reason=updated.scope_reason)

    def _create_target(
        self,
        *,
        project_id: str,
        value: str,
        descriptor: TargetDescriptor,
        source: TargetSource,
        status: TargetPoolStatus,
        scope_reason: str,
        rejection_key: str,
        evidence_id: str | None,
        discovered_by: str | None,
        discovered_from: str | None,
    ) -> CampaignTarget:
        target = CampaignTarget.create(
            project_id=project_id,
            value=value,
            target_type=_target_type_for_descriptor(descriptor),
            normalized_host=descriptor.host,
            source=source,
            status=status,
            discovered_by=discovered_by,
            discovered_from=discovered_from,
            scope_reason=scope_reason,
            rejection_key=rejection_key,
            metadata={"evidence_id": evidence_id} if evidence_id else {},
        )
        return self.target_repository.create(target)

    def _describe(self, value: str) -> TargetDescriptor:
        return self.scope_validator.describe_target(
            AdmissionRequest(
                session_id="target-admission",
                job_id=None,
                tool_name="target_admission",
                tool_category="recon",
                raw_target=value,
            )
        )

    def _add_target_to_policy(self, policy: ScopePolicy, target: CampaignTarget) -> None:
        value = target.normalized_host or target.value
        if target.target_type == TargetType.DOMAIN:
            _append_unique(policy.allowed_domains, value)
            return
        _append_unique(policy.allowed_hosts, value)

    def _record_event(self, *, project_id: str, event_kind: str, target: CampaignTarget, reason: str | None) -> None:
        self.event_repository.create(
            Event.create(
                project_id=project_id,
                event_kind=event_kind,
                level="info" if target.status != TargetPoolStatus.REJECTED else "warning",
                payload={
                    "target_id": target.id,
                    "target_public_id": target.public_id,
                    "value": target.value,
                    "status": target.status.value,
                    "reason": reason,
                    "rejection_key": target.rejection_key,
                },
            )
        )


def _target_type_for_descriptor(descriptor: TargetDescriptor) -> TargetType:
    if descriptor.kind == "url":
        return TargetType.URL
    if descriptor.ip is not None:
        return TargetType.IP
    host = descriptor.host or descriptor.normalized_target
    return TargetType.DOMAIN if "." in host else TargetType.HOST


def _append_unique(values: list[str], value: str) -> None:
    normalized = value.strip().lower()
    if not normalized:
        return
    if normalized not in {item.strip().lower() for item in values}:
        values.append(value.strip())


def _rejection_key(descriptor: TargetDescriptor) -> str:
    host = descriptor.host or descriptor.normalized_target
    host = host.strip().lower().strip("[]").rstrip(".")
    try:
        return str(ip_address(host))
    except ValueError:
        pass
    if "://" in host:
        parsed = urlsplit(host)
        host = (parsed.hostname or host).strip().lower().rstrip(".")
    labels = [label for label in host.split(".") if label]
    if len(labels) >= 2:
        return ".".join(labels[-2:])
    return host
