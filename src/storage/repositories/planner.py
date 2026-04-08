from __future__ import annotations

import sqlite3

from models.planner import PlannerPlan, PlannerProposal
from storage.sqlite import SQLiteStorage

from ._common import allocate_public_id, get_row_by_identifier


PLANNER_SCHEMA = """
CREATE TABLE IF NOT EXISTS planner_plans (
    id TEXT PRIMARY KEY,
    public_id TEXT,
    operation_id TEXT NOT NULL,
    status TEXT NOT NULL,
    planning_mode TEXT NOT NULL,
    context_hash TEXT NOT NULL,
    summary TEXT NOT NULL,
    rationale TEXT NOT NULL,
    planner_source TEXT NOT NULL,
    model_name TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    applied_at TEXT,
    FOREIGN KEY(operation_id) REFERENCES operations(id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_planner_plans_public_id ON planner_plans(public_id);
CREATE INDEX IF NOT EXISTS idx_planner_plans_operation_updated_at
    ON planner_plans(operation_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS planner_proposals (
    id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL,
    proposal_index INTEGER NOT NULL,
    proposal_kind TEXT NOT NULL,
    apply_status TEXT NOT NULL,
    job_type TEXT NOT NULL,
    target_ref TEXT NOT NULL,
    arguments TEXT NOT NULL DEFAULT '{}',
    timeout_seconds INTEGER,
    retry_limit INTEGER NOT NULL DEFAULT 0,
    summary TEXT NOT NULL DEFAULT '',
    rationale TEXT NOT NULL DEFAULT '',
    skip_reason TEXT,
    created_job_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(plan_id) REFERENCES planner_plans(id)
);

CREATE INDEX IF NOT EXISTS idx_planner_proposals_plan_kind
    ON planner_proposals(plan_id, proposal_kind, proposal_index ASC, created_at ASC);
"""


class PlannerRepository:
    def __init__(self, storage: SQLiteStorage) -> None:
        self.storage = storage
        self._ensure_schema()

    def create_plan(self, plan: PlannerPlan, proposals: list[PlannerProposal]) -> PlannerPlan:
        with self.storage.connect() as connection:
            self._create_plan_with_connection(connection, plan)
            for proposal in proposals:
                self._create_proposal_with_connection(connection, proposal)
            connection.commit()
        return plan

    def get_plan(self, identifier: str) -> PlannerPlan | None:
        with self.storage.connect() as connection:
            row = get_row_by_identifier(
                connection,
                table_name="planner_plans",
                identifier=identifier,
                order_column="updated_at",
            )
        return PlannerPlan.from_row(dict(row)) if row else None

    def list_plan_proposals(self, plan_identifier: str) -> list[PlannerProposal]:
        plan = self.get_plan(plan_identifier)
        if plan is None:
            return []
        with self.storage.connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM planner_proposals
                WHERE plan_id = ?
                ORDER BY proposal_kind = 'proposed' DESC, proposal_index ASC, created_at ASC, id ASC
                """,
                (plan.id,),
            ).fetchall()
        return [PlannerProposal.from_row(dict(row)) for row in rows]

    def update_plan(self, plan: PlannerPlan) -> PlannerPlan:
        with self.storage.connect() as connection:
            connection.execute(
                """
                UPDATE planner_plans
                SET
                    operation_id = :operation_id,
                    status = :status,
                    planning_mode = :planning_mode,
                    context_hash = :context_hash,
                    summary = :summary,
                    rationale = :rationale,
                    planner_source = :planner_source,
                    model_name = :model_name,
                    created_at = :created_at,
                    updated_at = :updated_at,
                    applied_at = :applied_at
                WHERE id = :id
                """,
                plan.to_row(),
            )
            connection.commit()
        return plan

    def update_proposal(self, proposal: PlannerProposal) -> PlannerProposal:
        with self.storage.connect() as connection:
            connection.execute(
                """
                UPDATE planner_proposals
                SET
                    plan_id = :plan_id,
                    proposal_index = :proposal_index,
                    proposal_kind = :proposal_kind,
                    apply_status = :apply_status,
                    job_type = :job_type,
                    target_ref = :target_ref,
                    arguments = :arguments,
                    timeout_seconds = :timeout_seconds,
                    retry_limit = :retry_limit,
                    summary = :summary,
                    rationale = :rationale,
                    skip_reason = :skip_reason,
                    created_job_id = :created_job_id,
                    created_at = :created_at,
                    updated_at = :updated_at
                WHERE id = :id
                """,
                proposal.to_row(),
            )
            connection.commit()
        return proposal

    def _create_plan_with_connection(self, connection: sqlite3.Connection, plan: PlannerPlan) -> None:
        plan.public_id = allocate_public_id(connection, table_name="planner_plans", prefix="PLN")
        connection.execute(
            """
            INSERT INTO planner_plans (
                id, public_id, operation_id, status, planning_mode, context_hash,
                summary, rationale, planner_source, model_name, created_at, updated_at, applied_at
            ) VALUES (
                :id, :public_id, :operation_id, :status, :planning_mode, :context_hash,
                :summary, :rationale, :planner_source, :model_name, :created_at, :updated_at, :applied_at
            )
            """,
            plan.to_row(),
        )

    def _create_proposal_with_connection(self, connection: sqlite3.Connection, proposal: PlannerProposal) -> None:
        connection.execute(
            """
            INSERT INTO planner_proposals (
                id, plan_id, proposal_index, proposal_kind, apply_status, job_type,
                target_ref, arguments, timeout_seconds, retry_limit, summary, rationale,
                skip_reason, created_job_id, created_at, updated_at
            ) VALUES (
                :id, :plan_id, :proposal_index, :proposal_kind, :apply_status, :job_type,
                :target_ref, :arguments, :timeout_seconds, :retry_limit, :summary, :rationale,
                :skip_reason, :created_job_id, :created_at, :updated_at
            )
            """,
            proposal.to_row(),
        )

    def _ensure_schema(self) -> None:
        with self.storage.connect() as connection:
            connection.executescript(PLANNER_SCHEMA)
            connection.commit()
