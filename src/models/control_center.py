from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from uuid import uuid4
import json

from .run import utc_now_iso


class ProjectStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class TargetSessionStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class TargetType(StrEnum):
    IP = "ip"
    DOMAIN = "domain"
    URL = "url"
    HOST = "host"
    NOTE = "note"


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


def _normalize_required_text(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be non-empty.")
    return normalized


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


@dataclass(slots=True)
class Project:
    id: str
    public_id: str
    name: str
    description: str | None
    root_path: str
    status: ProjectStatus = ProjectStatus.ACTIVE
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.name = _normalize_required_text(self.name, field_name="project name")
        self.description = _normalize_optional_text(self.description)
        self.root_path = _normalize_required_text(self.root_path, field_name="root path")
        self.status = ProjectStatus(self.status)
        self.metadata = dict(self.metadata)

    @classmethod
    def create(
        cls,
        *,
        name: str,
        description: str | None,
        root_path: str,
        metadata: dict[str, Any] | None = None,
    ) -> "Project":
        return cls(
            id=str(uuid4()),
            public_id="",
            name=name,
            description=description,
            root_path=root_path,
            metadata=dict(metadata or {}),
        )

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "Project":
        raw_metadata = row.get("metadata")
        return cls(
            id=row["id"],
            public_id=row.get("public_id") or "",
            name=row["name"],
            description=row.get("description"),
            root_path=row["root_path"],
            status=ProjectStatus(row["status"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            metadata=json.loads(raw_metadata) if raw_metadata else {},
        )

    def to_row(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "public_id": self.public_id,
            "name": self.name,
            "description": self.description,
            "root_path": self.root_path,
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": json.dumps(self.metadata, ensure_ascii=False),
        }


@dataclass(slots=True)
class TargetSession:
    id: str
    public_id: str
    project_id: str
    name: str
    target_value: str
    target_type: TargetType
    status: TargetSessionStatus = TargetSessionStatus.ACTIVE
    summary: str | None = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.project_id = _normalize_required_text(self.project_id, field_name="project id")
        self.name = _normalize_required_text(self.name, field_name="session name")
        self.target_value = _normalize_required_text(self.target_value, field_name="target value")
        self.target_type = TargetType(self.target_type)
        self.status = TargetSessionStatus(self.status)
        self.summary = _normalize_optional_text(self.summary)
        self.metadata = dict(self.metadata)

    @classmethod
    def create(
        cls,
        *,
        project_id: str,
        name: str,
        target_value: str,
        target_type: TargetType,
        summary: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "TargetSession":
        return cls(
            id=str(uuid4()),
            public_id="",
            project_id=project_id,
            name=name,
            target_value=target_value,
            target_type=target_type,
            summary=summary,
            metadata=dict(metadata or {}),
        )

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "TargetSession":
        raw_metadata = row.get("metadata")
        return cls(
            id=row["id"],
            public_id=row.get("public_id") or "",
            project_id=row["project_id"],
            name=row["name"],
            target_value=row["target_value"],
            target_type=TargetType(row["target_type"]),
            status=TargetSessionStatus(row["status"]),
            summary=row.get("summary"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            metadata=json.loads(raw_metadata) if raw_metadata else {},
        )

    def to_row(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "public_id": self.public_id,
            "project_id": self.project_id,
            "name": self.name,
            "target_value": self.target_value,
            "target_type": self.target_type.value,
            "status": self.status.value,
            "summary": self.summary,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": json.dumps(self.metadata, ensure_ascii=False),
        }


@dataclass(frozen=True, slots=True)
class SessionDashboard:
    project: Project
    session: TargetSession
    task_counts: dict[str, int] = field(default_factory=dict)
    finding_counts: dict[str, int] = field(default_factory=dict)
    evidence_count: int = 0
    flag_count: int = 0
    open_ports: list[dict[str, Any]] = field(default_factory=list)
    web_entries: list[dict[str, Any]] = field(default_factory=list)
    directory_findings: list[dict[str, Any]] = field(default_factory=list)
    poc_hits: list[dict[str, Any]] = field(default_factory=list)
    attack_path: list[dict[str, Any]] = field(default_factory=list)
    recent_commands: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    flags: list[dict[str, Any]] = field(default_factory=list)
    next_actions: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class Task:
    id: str
    public_id: str
    project_id: str
    session_id: str
    task_type: str
    executor: str
    status: TaskStatus = TaskStatus.PENDING
    input_json: dict[str, Any] = field(default_factory=dict)
    result_json: dict[str, Any] = field(default_factory=dict)
    started_at: str | None = None
    ended_at: str | None = None
    error: str | None = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def __post_init__(self) -> None:
        self.project_id = _normalize_required_text(self.project_id, field_name="project id")
        self.session_id = _normalize_required_text(self.session_id, field_name="session id")
        self.task_type = _normalize_required_text(self.task_type, field_name="task type")
        self.executor = _normalize_required_text(self.executor, field_name="executor")
        self.status = TaskStatus(self.status)
        self.input_json = dict(self.input_json)
        self.result_json = dict(self.result_json)

    @classmethod
    def create(
        cls,
        *,
        project_id: str,
        session_id: str,
        task_type: str,
        executor: str,
        status: TaskStatus = TaskStatus.PENDING,
        input_json: dict[str, Any] | None = None,
        result_json: dict[str, Any] | None = None,
    ) -> "Task":
        return cls(
            id=str(uuid4()),
            public_id="",
            project_id=project_id,
            session_id=session_id,
            task_type=task_type,
            executor=executor,
            status=status,
            input_json=dict(input_json or {}),
            result_json=dict(result_json or {}),
        )

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "Task":
        return cls(
            id=row["id"],
            public_id=row.get("public_id") or "",
            project_id=row["project_id"],
            session_id=row["session_id"],
            task_type=row["task_type"],
            executor=row["executor"],
            status=TaskStatus(row["status"]),
            input_json=json.loads(row.get("input_json") or "{}"),
            result_json=json.loads(row.get("result_json") or "{}"),
            started_at=row.get("started_at"),
            ended_at=row.get("ended_at"),
            error=row.get("error"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def to_row(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "public_id": self.public_id,
            "project_id": self.project_id,
            "session_id": self.session_id,
            "task_type": self.task_type,
            "executor": self.executor,
            "status": self.status.value,
            "input_json": json.dumps(self.input_json, ensure_ascii=False),
            "result_json": json.dumps(self.result_json, ensure_ascii=False),
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(slots=True)
class Event:
    id: str
    project_id: str | None
    session_id: str | None
    task_id: str | None
    event_kind: str
    level: str
    payload: dict[str, Any]
    sequence: int
    created_at: str = field(default_factory=utc_now_iso)

    def __post_init__(self) -> None:
        self.event_kind = _normalize_required_text(self.event_kind, field_name="event kind")
        self.level = _normalize_required_text(self.level, field_name="event level")
        self.payload = dict(self.payload)

    @classmethod
    def create(
        cls,
        *,
        event_kind: str,
        level: str,
        payload: dict[str, Any] | None = None,
        project_id: str | None = None,
        session_id: str | None = None,
        task_id: str | None = None,
        sequence: int = 0,
    ) -> "Event":
        return cls(
            id=str(uuid4()),
            project_id=project_id,
            session_id=session_id,
            task_id=task_id,
            event_kind=event_kind,
            level=level,
            payload=dict(payload or {}),
            sequence=sequence,
        )

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "Event":
        return cls(
            id=row["id"],
            project_id=row.get("project_id"),
            session_id=row.get("session_id"),
            task_id=row.get("task_id"),
            event_kind=row["event_kind"],
            level=row["level"],
            payload=json.loads(row.get("payload_json") or "{}"),
            sequence=int(row["sequence"]),
            created_at=row["created_at"],
        )

    def to_row(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "session_id": self.session_id,
            "task_id": self.task_id,
            "event_kind": self.event_kind,
            "level": self.level,
            "payload_json": json.dumps(self.payload, ensure_ascii=False),
            "sequence": self.sequence,
            "created_at": self.created_at,
        }


@dataclass(slots=True)
class Evidence:
    id: str
    public_id: str
    project_id: str
    session_id: str
    evidence_type: str
    title: str
    source_task_id: str | None = None
    summary: str | None = None
    content_ref: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)

    def __post_init__(self) -> None:
        self.project_id = _normalize_required_text(self.project_id, field_name="project id")
        self.session_id = _normalize_required_text(self.session_id, field_name="session id")
        self.evidence_type = _normalize_required_text(self.evidence_type, field_name="evidence type")
        self.title = _normalize_required_text(self.title, field_name="evidence title")
        self.summary = _normalize_optional_text(self.summary)
        self.content_ref = _normalize_optional_text(self.content_ref)
        self.payload = dict(self.payload)

    @classmethod
    def create(
        cls,
        *,
        project_id: str,
        session_id: str,
        evidence_type: str,
        title: str,
        source_task_id: str | None = None,
        summary: str | None = None,
        content_ref: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> "Evidence":
        return cls(
            id=str(uuid4()),
            public_id="",
            project_id=project_id,
            session_id=session_id,
            evidence_type=evidence_type,
            title=title,
            source_task_id=source_task_id,
            summary=summary,
            content_ref=content_ref,
            payload=dict(payload or {}),
        )

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "Evidence":
        return cls(
            id=row["id"],
            public_id=row.get("public_id") or "",
            project_id=row["project_id"],
            session_id=row["session_id"],
            source_task_id=row.get("source_task_id"),
            evidence_type=row["evidence_type"],
            title=row["title"],
            summary=row.get("summary"),
            content_ref=row.get("content_ref"),
            payload=json.loads(row.get("payload_json") or "{}"),
            created_at=row["created_at"],
        )

    def to_row(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "public_id": self.public_id,
            "project_id": self.project_id,
            "session_id": self.session_id,
            "source_task_id": self.source_task_id,
            "evidence_type": self.evidence_type,
            "title": self.title,
            "summary": self.summary,
            "content_ref": self.content_ref,
            "payload_json": json.dumps(self.payload, ensure_ascii=False),
            "created_at": self.created_at,
        }


@dataclass(slots=True)
class Finding:
    id: str
    public_id: str
    project_id: str
    session_id: str
    severity: str
    status: str
    title: str
    description: str | None = None
    evidence_refs: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def __post_init__(self) -> None:
        self.project_id = _normalize_required_text(self.project_id, field_name="project id")
        self.session_id = _normalize_required_text(self.session_id, field_name="session id")
        self.severity = _normalize_required_text(self.severity, field_name="finding severity")
        self.status = _normalize_required_text(self.status, field_name="finding status")
        self.title = _normalize_required_text(self.title, field_name="finding title")
        self.description = _normalize_optional_text(self.description)
        self.evidence_refs = [ref.strip() for ref in self.evidence_refs if ref.strip()]

    @classmethod
    def create(
        cls,
        *,
        project_id: str,
        session_id: str,
        severity: str,
        status: str,
        title: str,
        description: str | None = None,
        evidence_refs: list[str] | None = None,
    ) -> "Finding":
        return cls(
            id=str(uuid4()),
            public_id="",
            project_id=project_id,
            session_id=session_id,
            severity=severity,
            status=status,
            title=title,
            description=description,
            evidence_refs=list(evidence_refs or []),
        )

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "Finding":
        return cls(
            id=row["id"],
            public_id=row.get("public_id") or "",
            project_id=row["project_id"],
            session_id=row["session_id"],
            severity=row["severity"],
            status=row["status"],
            title=row["title"],
            description=row.get("description"),
            evidence_refs=json.loads(row.get("evidence_refs_json") or "[]"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def to_row(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "public_id": self.public_id,
            "project_id": self.project_id,
            "session_id": self.session_id,
            "severity": self.severity,
            "status": self.status,
            "title": self.title,
            "description": self.description,
            "evidence_refs_json": json.dumps(self.evidence_refs, ensure_ascii=False),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(slots=True)
class AttackPathNode:
    id: str
    public_id: str
    project_id: str
    session_id: str
    stage: str
    title: str
    status: str
    source_ref: str | None = None
    next_action: str | None = None
    created_at: str = field(default_factory=utc_now_iso)

    def __post_init__(self) -> None:
        self.project_id = _normalize_required_text(self.project_id, field_name="project id")
        self.session_id = _normalize_required_text(self.session_id, field_name="session id")
        self.stage = _normalize_required_text(self.stage, field_name="attack path stage")
        self.title = _normalize_required_text(self.title, field_name="attack path title")
        self.status = _normalize_required_text(self.status, field_name="attack path status")
        self.source_ref = _normalize_optional_text(self.source_ref)
        self.next_action = _normalize_optional_text(self.next_action)

    @classmethod
    def create(
        cls,
        *,
        project_id: str,
        session_id: str,
        stage: str,
        title: str,
        status: str,
        source_ref: str | None = None,
        next_action: str | None = None,
    ) -> "AttackPathNode":
        return cls(
            id=str(uuid4()),
            public_id="",
            project_id=project_id,
            session_id=session_id,
            stage=stage,
            title=title,
            status=status,
            source_ref=source_ref,
            next_action=next_action,
        )

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "AttackPathNode":
        return cls(
            id=row["id"],
            public_id=row.get("public_id") or "",
            project_id=row["project_id"],
            session_id=row["session_id"],
            stage=row["stage"],
            title=row["title"],
            status=row["status"],
            source_ref=row.get("source_ref"),
            next_action=row.get("next_action"),
            created_at=row["created_at"],
        )

    def to_row(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "public_id": self.public_id,
            "project_id": self.project_id,
            "session_id": self.session_id,
            "stage": self.stage,
            "title": self.title,
            "status": self.status,
            "source_ref": self.source_ref,
            "next_action": self.next_action,
            "created_at": self.created_at,
        }


@dataclass(slots=True)
class CommandRun:
    id: str
    public_id: str
    project_id: str
    session_id: str
    terminal_id: str
    command: str
    exit_code: int | None = None
    output_ref: str | None = None
    tags: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now_iso)

    def __post_init__(self) -> None:
        self.project_id = _normalize_required_text(self.project_id, field_name="project id")
        self.session_id = _normalize_required_text(self.session_id, field_name="session id")
        self.terminal_id = _normalize_required_text(self.terminal_id, field_name="terminal id")
        self.command = _normalize_required_text(self.command, field_name="command")
        self.output_ref = _normalize_optional_text(self.output_ref)
        self.tags = [tag.strip() for tag in self.tags if tag.strip()]

    @classmethod
    def create(
        cls,
        *,
        project_id: str,
        session_id: str,
        terminal_id: str,
        command: str,
        exit_code: int | None = None,
        output_ref: str | None = None,
        tags: list[str] | None = None,
    ) -> "CommandRun":
        return cls(
            id=str(uuid4()),
            public_id="",
            project_id=project_id,
            session_id=session_id,
            terminal_id=terminal_id,
            command=command,
            exit_code=exit_code,
            output_ref=output_ref,
            tags=list(tags or []),
        )

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "CommandRun":
        return cls(
            id=row["id"],
            public_id=row.get("public_id") or "",
            project_id=row["project_id"],
            session_id=row["session_id"],
            terminal_id=row["terminal_id"],
            command=row["command"],
            exit_code=row.get("exit_code"),
            output_ref=row.get("output_ref"),
            tags=json.loads(row.get("tags_json") or "[]"),
            created_at=row["created_at"],
        )

    def to_row(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "public_id": self.public_id,
            "project_id": self.project_id,
            "session_id": self.session_id,
            "terminal_id": self.terminal_id,
            "command": self.command,
            "exit_code": self.exit_code,
            "output_ref": self.output_ref,
            "tags_json": json.dumps(self.tags, ensure_ascii=False),
            "created_at": self.created_at,
        }


@dataclass(slots=True)
class Flag:
    id: str
    public_id: str
    project_id: str
    session_id: str
    flag_type: str
    value: str
    source_evidence_id: str | None = None
    created_at: str = field(default_factory=utc_now_iso)

    def __post_init__(self) -> None:
        self.project_id = _normalize_required_text(self.project_id, field_name="project id")
        self.session_id = _normalize_required_text(self.session_id, field_name="session id")
        self.flag_type = _normalize_required_text(self.flag_type, field_name="flag type")
        self.value = _normalize_required_text(self.value, field_name="flag value")

    @classmethod
    def create(
        cls,
        *,
        project_id: str,
        session_id: str,
        flag_type: str,
        value: str,
        source_evidence_id: str | None = None,
    ) -> "Flag":
        return cls(
            id=str(uuid4()),
            public_id="",
            project_id=project_id,
            session_id=session_id,
            flag_type=flag_type,
            value=value,
            source_evidence_id=source_evidence_id,
        )

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "Flag":
        return cls(
            id=row["id"],
            public_id=row.get("public_id") or "",
            project_id=row["project_id"],
            session_id=row["session_id"],
            flag_type=row["flag_type"],
            value=row["value"],
            source_evidence_id=row.get("source_evidence_id"),
            created_at=row["created_at"],
        )

    def to_row(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "public_id": self.public_id,
            "project_id": self.project_id,
            "session_id": self.session_id,
            "flag_type": self.flag_type,
            "value": self.value,
            "source_evidence_id": self.source_evidence_id,
            "created_at": self.created_at,
        }
