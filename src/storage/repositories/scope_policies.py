from __future__ import annotations

from domain.operations import ScopePolicy
from storage.redteam import RedTeamStorage


class ScopePolicyRepository:
    def __init__(self, storage: RedTeamStorage) -> None:
        self.storage = storage

    def upsert(self, policy: ScopePolicy) -> ScopePolicy:
        with self.storage.connect() as connection:
            existing = connection.execute(
                "SELECT id, created_at FROM scope_policies WHERE operation_id = ?",
                (policy.operation_id,),
            ).fetchone()
            if existing is not None:
                policy.id = existing["id"]
                policy.created_at = existing["created_at"]
                connection.execute(
                    """
                    UPDATE scope_policies
                    SET
                        allowed_hostnames_json = :allowed_hostnames_json,
                        allowed_ips_json = :allowed_ips_json,
                        allowed_domains_json = :allowed_domains_json,
                        allowed_cidrs_json = :allowed_cidrs_json,
                        allowed_ports_json = :allowed_ports_json,
                        allowed_protocols_json = :allowed_protocols_json,
                        denied_targets_json = :denied_targets_json,
                        allowed_tool_categories_json = :allowed_tool_categories_json,
                        max_concurrency = :max_concurrency,
                        requests_per_minute = :requests_per_minute,
                        packets_per_second = :packets_per_second,
                        requires_confirmation_for_json = :requires_confirmation_for_json,
                        created_at = :created_at,
                        updated_at = :updated_at
                    WHERE operation_id = :operation_id
                    """,
                    policy.to_row(),
                )
            else:
                connection.execute(
                    """
                    INSERT INTO scope_policies (
                        id, operation_id, allowed_hostnames_json, allowed_ips_json, allowed_domains_json,
                        allowed_cidrs_json, allowed_ports_json, allowed_protocols_json,
                        denied_targets_json, allowed_tool_categories_json, max_concurrency,
                        requests_per_minute, packets_per_second, requires_confirmation_for_json,
                        created_at, updated_at
                    ) VALUES (
                        :id, :operation_id, :allowed_hostnames_json, :allowed_ips_json, :allowed_domains_json,
                        :allowed_cidrs_json, :allowed_ports_json, :allowed_protocols_json,
                        :denied_targets_json, :allowed_tool_categories_json, :max_concurrency,
                        :requests_per_minute, :packets_per_second, :requires_confirmation_for_json,
                        :created_at, :updated_at
                    )
                    """,
                    policy.to_row(),
                )
            connection.commit()
        return policy

    def get_by_operation_id(self, operation_id: str) -> ScopePolicy | None:
        with self.storage.connect() as connection:
            row = connection.execute(
                "SELECT * FROM scope_policies WHERE operation_id = ?",
                (operation_id,),
            ).fetchone()
        return ScopePolicy.from_row(dict(row)) if row else None

    def delete_by_operation_id(self, operation_id: str) -> None:
        with self.storage.connect() as connection:
            connection.execute(
                "DELETE FROM scope_policies WHERE operation_id = ?",
                (operation_id,),
            )
            connection.commit()
