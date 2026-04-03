from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4
import json

from .run import utc_now_iso


@dataclass(slots=True)
class ScopePolicy:
    id: str
    operation_id: str
    allowed_hosts: list[str] = field(default_factory=list)
    allowed_domains: list[str] = field(default_factory=list)
    allowed_cidrs: list[str] = field(default_factory=list)
    allowed_ports: list[int] = field(default_factory=list)
    allowed_protocols: list[str] = field(default_factory=list)
    denied_targets: list[str] = field(default_factory=list)
    allowed_tool_categories: list[str] = field(default_factory=list)
    max_concurrency: int = 1
    rate_limit_per_minute: int | None = None
    confirmation_required_actions: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    @classmethod
    def create(
        cls,
        *,
        operation_id: str,
        allowed_hosts: list[str] | None = None,
        allowed_domains: list[str] | None = None,
        allowed_cidrs: list[str] | None = None,
        allowed_ports: list[int] | None = None,
        allowed_protocols: list[str] | None = None,
        denied_targets: list[str] | None = None,
        allowed_tool_categories: list[str] | None = None,
        max_concurrency: int = 1,
        rate_limit_per_minute: int | None = None,
        confirmation_required_actions: list[str] | None = None,
    ) -> "ScopePolicy":
        return cls(
            id=str(uuid4()),
            operation_id=operation_id,
            allowed_hosts=list(allowed_hosts or []),
            allowed_domains=list(allowed_domains or []),
            allowed_cidrs=list(allowed_cidrs or []),
            allowed_ports=list(allowed_ports or []),
            allowed_protocols=list(allowed_protocols or []),
            denied_targets=list(denied_targets or []),
            allowed_tool_categories=list(allowed_tool_categories or []),
            max_concurrency=max_concurrency,
            rate_limit_per_minute=rate_limit_per_minute,
            confirmation_required_actions=list(confirmation_required_actions or []),
        )

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "ScopePolicy":
        return cls(
            id=row["id"],
            operation_id=row["operation_id"],
            allowed_hosts=json.loads(row["allowed_hosts"]) if row.get("allowed_hosts") else [],
            allowed_domains=json.loads(row["allowed_domains"]) if row.get("allowed_domains") else [],
            allowed_cidrs=json.loads(row["allowed_cidrs"]) if row.get("allowed_cidrs") else [],
            allowed_ports=json.loads(row["allowed_ports"]) if row.get("allowed_ports") else [],
            allowed_protocols=json.loads(row["allowed_protocols"]) if row.get("allowed_protocols") else [],
            denied_targets=json.loads(row["denied_targets"]) if row.get("denied_targets") else [],
            allowed_tool_categories=json.loads(row["allowed_tool_categories"])
            if row.get("allowed_tool_categories")
            else [],
            max_concurrency=row["max_concurrency"],
            rate_limit_per_minute=row["rate_limit_per_minute"],
            confirmation_required_actions=json.loads(row["confirmation_required_actions"])
            if row.get("confirmation_required_actions")
            else [],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def to_row(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "operation_id": self.operation_id,
            "allowed_hosts": json.dumps(self.allowed_hosts, ensure_ascii=False),
            "allowed_domains": json.dumps(self.allowed_domains, ensure_ascii=False),
            "allowed_cidrs": json.dumps(self.allowed_cidrs, ensure_ascii=False),
            "allowed_ports": json.dumps(self.allowed_ports, ensure_ascii=False),
            "allowed_protocols": json.dumps(self.allowed_protocols, ensure_ascii=False),
            "denied_targets": json.dumps(self.denied_targets, ensure_ascii=False),
            "allowed_tool_categories": json.dumps(self.allowed_tool_categories, ensure_ascii=False),
            "max_concurrency": self.max_concurrency,
            "rate_limit_per_minute": self.rate_limit_per_minute,
            "confirmation_required_actions": json.dumps(
                self.confirmation_required_actions,
                ensure_ascii=False,
            ),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
