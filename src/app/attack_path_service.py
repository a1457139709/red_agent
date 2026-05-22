from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agent.settings import Settings, get_settings
from models.control_center import AttackPathNode, Event, Evidence, Finding, Flag, TargetSession
from storage.repositories.control_center import (
    AttackPathEvidenceLinkRepository,
    AttackPathNodeRepository,
    EventRepository,
    EvidenceRepository,
    FindingRepository,
    FlagRepository,
    ProjectRepository,
    TargetSessionRepository,
)
from storage.sqlite import SQLiteStorage

from .control_center_base import ControlCenterService


@dataclass(frozen=True, slots=True)
class AttackPathNodeDetail:
    node: AttackPathNode
    evidence: list[Evidence] = field(default_factory=list)


class AttackPathService(ControlCenterService):
    def __init__(self, *, settings: Settings) -> None:
        storage = SQLiteStorage(settings.sqlite_path)
        object.__setattr__(self, "settings", settings)
        object.__setattr__(self, "project_repository", ProjectRepository(storage))
        object.__setattr__(self, "session_repository", TargetSessionRepository(storage))
        object.__setattr__(self, "node_repository", AttackPathNodeRepository(storage))
        object.__setattr__(self, "evidence_repository", EvidenceRepository(storage))
        object.__setattr__(self, "finding_repository", FindingRepository(storage))
        object.__setattr__(self, "flag_repository", FlagRepository(storage))
        object.__setattr__(self, "link_repository", AttackPathEvidenceLinkRepository(storage))
        object.__setattr__(self, "event_repository", EventRepository(storage))

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "AttackPathService":
        return cls(settings=settings or get_settings())

    def list_attack_path(self, *, session_identifier: str, limit: int | None = None) -> list[AttackPathNodeDetail]:
        session = self.session_repository.require(session_identifier)
        nodes = self.node_repository.list(session_id=session.id, limit=limit)
        return [AttackPathNodeDetail(node=node, evidence=self._node_evidence(node)) for node in nodes]

    def create_attack_path_node(
        self,
        *,
        session_identifier: str,
        stage: str,
        title: str,
        status: str = "open",
        source_ref: str | None = None,
        next_action: str | None = None,
        evidence_ids: list[str] | None = None,
    ) -> AttackPathNodeDetail:
        session = self.session_repository.require(session_identifier)
        linked_evidence = self._resolve_evidence_refs(session_id=session.id, evidence_ids=evidence_ids or [])
        node = AttackPathNode.create(
            project_id=session.project_id,
            session_id=session.id,
            stage=stage,
            title=title,
            status=status,
            source_ref=source_ref,
            next_action=next_action,
        )
        storage = SQLiteStorage(self.settings.sqlite_path)
        with storage.connect() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                self.node_repository.create_in_connection(connection, node)
                for evidence in linked_evidence:
                    self.link_repository.link_in_connection(connection, node_id=node.id, evidence_id=evidence.id)
                self.event_repository.create_in_connection(
                    connection,
                    Event.create(
                        project_id=session.project_id,
                        session_id=session.id,
                        event_kind="attack_path.node_created",
                        level="info",
                        payload={"node_id": node.id, "public_id": node.public_id, "stage": node.stage, "title": node.title},
                    ),
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return AttackPathNodeDetail(node=node, evidence=self._node_evidence(node))

    def list_evidence(self, *, session_identifier: str, limit: int | None = None) -> list[Evidence]:
        session = self.session_repository.require(session_identifier)
        return self.evidence_repository.list(session_id=session.id, limit=limit)

    def create_evidence(
        self,
        *,
        session_identifier: str,
        evidence_type: str,
        title: str,
        summary: str | None = None,
        content_ref: str | None = None,
        payload: dict[str, Any] | None = None,
        source_task_id: str | None = None,
        attack_path_node_id: str | None = None,
    ) -> tuple[Evidence, AttackPathNodeDetail]:
        session = self.session_repository.require(session_identifier)
        node: AttackPathNode | None = None
        if attack_path_node_id:
            node = self.node_repository.get(attack_path_node_id)
            if node is None or node.session_id != session.id:
                raise ValueError(f"Attack path node not found in session: {attack_path_node_id}")

        evidence = Evidence.create(
            project_id=session.project_id,
            session_id=session.id,
            source_task_id=source_task_id,
            evidence_type=evidence_type,
            title=title,
            summary=summary,
            content_ref=content_ref,
            payload=dict(payload or {}),
        )
        created_node = False
        if node is None:
            node = AttackPathNode.create(
                project_id=session.project_id,
                session_id=session.id,
                stage="note",
                title=title,
                status="open",
                source_ref=evidence.id,
                next_action="Review and classify this manual note.",
            )
            created_node = True
        storage = SQLiteStorage(self.settings.sqlite_path)
        with storage.connect() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                self.evidence_repository.create_in_connection(connection, evidence)
                if created_node:
                    self.node_repository.create_in_connection(connection, node)
                self.link_repository.link_in_connection(connection, node_id=node.id, evidence_id=evidence.id)
                if created_node:
                    self.event_repository.create_in_connection(
                        connection,
                        Event.create(
                            project_id=session.project_id,
                            session_id=session.id,
                            event_kind="attack_path.node_created",
                            level="info",
                            payload={"node_id": node.id, "public_id": node.public_id, "stage": node.stage, "title": node.title},
                        ),
                    )
                self.event_repository.create_in_connection(
                    connection,
                    Event.create(
                        project_id=session.project_id,
                        session_id=session.id,
                        event_kind="evidence.created",
                        level="info",
                        payload={"evidence_id": evidence.id, "public_id": evidence.public_id, "evidence_type": evidence.evidence_type},
                    ),
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return evidence, AttackPathNodeDetail(node=node, evidence=self._node_evidence(node))

    def list_findings(self, *, session_identifier: str, limit: int | None = None) -> list[Finding]:
        session = self.session_repository.require(session_identifier)
        return self.finding_repository.list(session_id=session.id, limit=limit)

    def update_finding(
        self,
        *,
        finding_identifier: str,
        severity: str | None = None,
        status: str | None = None,
        title: str | None = None,
        description: str | None = None,
        evidence_refs: list[str] | None = None,
    ) -> Finding:
        finding = self.finding_repository.require(finding_identifier)
        if severity is not None:
            finding.severity = severity
        if status is not None:
            finding.status = status
        if title is not None:
            finding.title = title
        if description is not None:
            finding.description = description
        if evidence_refs is not None:
            session = self.session_repository.require(finding.session_id)
            normalized_refs: list[str] = []
            for evidence_id in evidence_refs:
                evidence = self.evidence_repository.get(evidence_id)
                if evidence is None or evidence.session_id != session.id:
                    raise ValueError(f"Evidence not found in session: {evidence_id}")
                normalized_refs.append(evidence.id)
            finding.evidence_refs = normalized_refs
        updated = self.finding_repository.update(finding)
        session = self.session_repository.require(updated.session_id)
        self._record_event(
            session,
            "finding.updated",
            {"finding_id": updated.id, "public_id": updated.public_id, "status": updated.status},
        )
        return updated

    def list_flags(self, *, session_identifier: str, limit: int | None = None) -> list[Flag]:
        session = self.session_repository.require(session_identifier)
        return self.flag_repository.list(session_id=session.id, limit=limit)

    def create_flag(
        self,
        *,
        session_identifier: str,
        flag_type: str,
        value: str,
        source_evidence_id: str | None = None,
    ) -> tuple[Flag, AttackPathNodeDetail]:
        session = self.session_repository.require(session_identifier)
        if source_evidence_id:
            evidence = self.evidence_repository.get(source_evidence_id)
            if evidence is None or evidence.session_id != session.id:
                raise ValueError(f"Evidence not found in session: {source_evidence_id}")
            source_evidence_id = evidence.id
        flag = Flag.create(
            project_id=session.project_id,
            session_id=session.id,
            flag_type=flag_type,
            value=value,
            source_evidence_id=source_evidence_id,
        )
        node = AttackPathNode.create(
            project_id=session.project_id,
            session_id=session.id,
            stage="flag",
            title=f"Captured {flag.flag_type} flag/loot",
            status="verified",
            source_ref=flag.id,
            next_action="Add this result to the writeup.",
        )
        storage = SQLiteStorage(self.settings.sqlite_path)
        with storage.connect() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                self.flag_repository.create_in_connection(connection, flag)
                node.source_ref = flag.id
                self.node_repository.create_in_connection(connection, node)
                if source_evidence_id:
                    self.link_repository.link_in_connection(connection, node_id=node.id, evidence_id=source_evidence_id)
                self.event_repository.create_in_connection(
                    connection,
                    Event.create(
                        project_id=session.project_id,
                        session_id=session.id,
                        event_kind="flag.created",
                        level="info",
                        payload={"flag_id": flag.id, "public_id": flag.public_id, "flag_type": flag.flag_type},
                    ),
                )
                self.event_repository.create_in_connection(
                    connection,
                    Event.create(
                        project_id=session.project_id,
                        session_id=session.id,
                        event_kind="attack_path.node_created",
                        level="info",
                        payload={"node_id": node.id, "public_id": node.public_id, "stage": node.stage, "title": node.title},
                    ),
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return flag, AttackPathNodeDetail(node=node, evidence=self._node_evidence(node))

    def _node_evidence(self, node: AttackPathNode) -> list[Evidence]:
        evidence: list[Evidence] = []
        for evidence_id in self.link_repository.list_evidence_ids(node_id=node.id):
            item = self.evidence_repository.get(evidence_id)
            if item is not None:
                evidence.append(item)
        if not evidence and node.source_ref:
            source = self.evidence_repository.get(node.source_ref)
            if source is not None and source.session_id == node.session_id:
                evidence.append(source)
        return evidence

    def _record_event(self, session: TargetSession, event_kind: str, payload: dict[str, Any]) -> Event:
        return self.event_repository.create(
            Event.create(
                project_id=session.project_id,
                session_id=session.id,
                event_kind=event_kind,
                level="info",
                payload=payload,
            )
        )

    def _resolve_evidence_refs(self, *, session_id: str, evidence_ids: list[str]) -> list[Evidence]:
        resolved: list[Evidence] = []
        for evidence_id in evidence_ids:
            evidence = self.evidence_repository.get(evidence_id)
            if evidence is None or evidence.session_id != session_id:
                raise ValueError(f"Evidence not found in session: {evidence_id}")
            resolved.append(evidence)
        return resolved
