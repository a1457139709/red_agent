from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from uuid import uuid4

from domain.common import json_dumps, json_loads, utc_now_iso


class OperationStatus(StrEnum):
    DRAFT = "draft"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    BLOCKED = "blocked"
    FAILED = "failed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


@dataclass(slots=True)
class Operation:
    id: str
    public_id: str
    title: str
    objective: str
    workspace: str
    status: OperationStatus = OperationStatus.DRAFT
    planner_profile: str | None = None
    memory_profile_id: str | None = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    closed_at: str | None = None
    last_error_code: str | None = None
    last_error_message: str | None = None

    @classmethod
    def create(
        cls,
        *,
        title: str,
        objective: str,
        workspace: str,
        status: OperationStatus = OperationStatus.DRAFT,
        planner_profile: str | None = None,
        memory_profile_id: str | None = None,
    ) -> "Operation":
        return cls(
            id=str(uuid4()),
            public_id="",
            title=title,
            objective=objective,
            workspace=workspace,
            status=status,
            planner_profile=planner_profile,
            memory_profile_id=memory_profile_id,
        )

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "Operation":
        return cls(
            id=row["id"],
            public_id=row["public_id"],
            title=row["title"],
            objective=row["objective"],
            workspace=row["workspace"],
            status=OperationStatus(row["status"]),
            planner_profile=row["planner_profile"],
            memory_profile_id=row["memory_profile_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            closed_at=row["closed_at"],
            last_error_code=row["last_error_code"],
            last_error_message=row["last_error_message"],
        )

    def to_row(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "public_id": self.public_id,
            "title": self.title,
            "objective": self.objective,
            "workspace": self.workspace,
            "status": self.status.value,
            "planner_profile": self.planner_profile,
            "memory_profile_id": self.memory_profile_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "closed_at": self.closed_at,
            "last_error_code": self.last_error_code,
            "last_error_message": self.last_error_message,
        }


@dataclass(slots=True)
class ScopePolicy:
    id: str
    operation_id: str
    allowed_hostnames: list[str] = field(default_factory=list)
    allowed_ips: list[str] = field(default_factory=list)
    allowed_domains: list[str] = field(default_factory=list)
    allowed_cidrs: list[str] = field(default_factory=list)
    allowed_ports: list[int] = field(default_factory=list)
    allowed_protocols: list[str] = field(default_factory=list)
    denied_targets: list[str] = field(default_factory=list)
    allowed_tool_categories: list[str] = field(default_factory=list)
    max_concurrency: int = 1
    requests_per_minute: int | None = None
    packets_per_second: int | None = None
    requires_confirmation_for: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    @classmethod
    def create(
        cls,
        *,
        operation_id: str,
        allowed_hostnames: list[str] | None = None,
        allowed_ips: list[str] | None = None,
        allowed_domains: list[str] | None = None,
        allowed_cidrs: list[str] | None = None,
        allowed_ports: list[int] | None = None,
        allowed_protocols: list[str] | None = None,
        denied_targets: list[str] | None = None,
        allowed_tool_categories: list[str] | None = None,
        max_concurrency: int = 1,
        requests_per_minute: int | None = None,
        packets_per_second: int | None = None,
        requires_confirmation_for: list[str] | None = None,
    ) -> "ScopePolicy":
        return cls(
            id=str(uuid4()),
            operation_id=operation_id,
            allowed_hostnames=allowed_hostnames or [],
            allowed_ips=allowed_ips or [],
            allowed_domains=allowed_domains or [],
            allowed_cidrs=allowed_cidrs or [],
            allowed_ports=allowed_ports or [],
            allowed_protocols=allowed_protocols or [],
            denied_targets=denied_targets or [],
            allowed_tool_categories=allowed_tool_categories or [],
            max_concurrency=max_concurrency,
            requests_per_minute=requests_per_minute,
            packets_per_second=packets_per_second,
            requires_confirmation_for=requires_confirmation_for or [],
        )

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "ScopePolicy":
        return cls(
            id=row["id"],
            operation_id=row["operation_id"],
            allowed_hostnames=json_loads(row["allowed_hostnames_json"], []),
            allowed_ips=json_loads(row["allowed_ips_json"], []),
            allowed_domains=json_loads(row["allowed_domains_json"], []),
            allowed_cidrs=json_loads(row["allowed_cidrs_json"], []),
            allowed_ports=json_loads(row["allowed_ports_json"], []),
            allowed_protocols=json_loads(row["allowed_protocols_json"], []),
            denied_targets=json_loads(row["denied_targets_json"], []),
            allowed_tool_categories=json_loads(row["allowed_tool_categories_json"], []),
            max_concurrency=row["max_concurrency"],
            requests_per_minute=row["requests_per_minute"],
            packets_per_second=row["packets_per_second"],
            requires_confirmation_for=json_loads(row["requires_confirmation_for_json"], []),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def to_row(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "operation_id": self.operation_id,
            "allowed_hostnames_json": json_dumps(self.allowed_hostnames),
            "allowed_ips_json": json_dumps(self.allowed_ips),
            "allowed_domains_json": json_dumps(self.allowed_domains),
            "allowed_cidrs_json": json_dumps(self.allowed_cidrs),
            "allowed_ports_json": json_dumps(self.allowed_ports),
            "allowed_protocols_json": json_dumps(self.allowed_protocols),
            "denied_targets_json": json_dumps(self.denied_targets),
            "allowed_tool_categories_json": json_dumps(self.allowed_tool_categories),
            "max_concurrency": self.max_concurrency,
            "requests_per_minute": self.requests_per_minute,
            "packets_per_second": self.packets_per_second,
            "requires_confirmation_for_json": json_dumps(self.requires_confirmation_for),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
