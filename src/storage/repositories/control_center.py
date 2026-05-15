from __future__ import annotations

import sqlite3

from models.control_center import (
    AttackPathNode,
    CTFReport,
    CommandRun,
    Event,
    Evidence,
    Finding,
    Flag,
    Project,
    ProjectStatus,
    TargetSession,
    TargetSessionStatus,
    Task,
    TaskStatus,
)
from models.run import utc_now_iso
from storage.sqlite import SQLiteStorage

from ._common import allocate_public_id, get_row_by_identifier


CONTROL_CENTER_SCHEMA = """
CREATE TABLE IF NOT EXISTS ctf_projects (
    id TEXT PRIMARY KEY,
    public_id TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT,
    root_path TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_ctf_projects_updated_at ON ctf_projects(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_ctf_projects_status ON ctf_projects(status);

CREATE TABLE IF NOT EXISTS ctf_target_sessions (
    id TEXT PRIMARY KEY,
    public_id TEXT NOT NULL UNIQUE,
    project_id TEXT NOT NULL,
    name TEXT NOT NULL,
    target_value TEXT NOT NULL,
    target_type TEXT NOT NULL,
    status TEXT NOT NULL,
    summary TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(project_id) REFERENCES ctf_projects(id)
);

CREATE INDEX IF NOT EXISTS idx_ctf_target_sessions_project_updated_at
    ON ctf_target_sessions(project_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_ctf_target_sessions_status ON ctf_target_sessions(status);

CREATE TABLE IF NOT EXISTS ctf_tasks (
    id TEXT PRIMARY KEY,
    public_id TEXT UNIQUE,
    project_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    task_type TEXT NOT NULL,
    executor TEXT NOT NULL,
    status TEXT NOT NULL,
    input_json TEXT NOT NULL DEFAULT '{}',
    result_json TEXT NOT NULL DEFAULT '{}',
    started_at TEXT,
    ended_at TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(project_id) REFERENCES ctf_projects(id),
    FOREIGN KEY(session_id) REFERENCES ctf_target_sessions(id)
);

CREATE INDEX IF NOT EXISTS idx_ctf_tasks_session_updated_at ON ctf_tasks(session_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_ctf_tasks_status ON ctf_tasks(status);

CREATE TABLE IF NOT EXISTS ctf_events (
    id TEXT PRIMARY KEY,
    project_id TEXT,
    session_id TEXT,
    task_id TEXT,
    event_kind TEXT NOT NULL,
    level TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    sequence INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(project_id) REFERENCES ctf_projects(id),
    FOREIGN KEY(session_id) REFERENCES ctf_target_sessions(id),
    FOREIGN KEY(task_id) REFERENCES ctf_tasks(id)
);

CREATE INDEX IF NOT EXISTS idx_ctf_events_session_sequence ON ctf_events(session_id, sequence);
CREATE INDEX IF NOT EXISTS idx_ctf_events_project_sequence ON ctf_events(project_id, sequence);
CREATE INDEX IF NOT EXISTS idx_ctf_events_created_at ON ctf_events(created_at DESC);

CREATE TABLE IF NOT EXISTS ctf_evidence (
    id TEXT PRIMARY KEY,
    public_id TEXT UNIQUE,
    project_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    source_task_id TEXT,
    evidence_type TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT,
    content_ref TEXT,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY(project_id) REFERENCES ctf_projects(id),
    FOREIGN KEY(session_id) REFERENCES ctf_target_sessions(id),
    FOREIGN KEY(source_task_id) REFERENCES ctf_tasks(id)
);

CREATE INDEX IF NOT EXISTS idx_ctf_evidence_session_created_at ON ctf_evidence(session_id, created_at DESC);

CREATE TABLE IF NOT EXISTS ctf_findings (
    id TEXT PRIMARY KEY,
    public_id TEXT UNIQUE,
    project_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    severity TEXT NOT NULL,
    status TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(project_id) REFERENCES ctf_projects(id),
    FOREIGN KEY(session_id) REFERENCES ctf_target_sessions(id)
);

CREATE INDEX IF NOT EXISTS idx_ctf_findings_session_created_at
    ON ctf_findings(session_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ctf_findings_status ON ctf_findings(status);

CREATE TABLE IF NOT EXISTS ctf_attack_path_nodes (
    id TEXT PRIMARY KEY,
    public_id TEXT UNIQUE,
    project_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    stage TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    source_ref TEXT,
    next_action TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(project_id) REFERENCES ctf_projects(id),
    FOREIGN KEY(session_id) REFERENCES ctf_target_sessions(id)
);

CREATE INDEX IF NOT EXISTS idx_ctf_attack_path_nodes_session_created_at
    ON ctf_attack_path_nodes(session_id, created_at DESC);

CREATE TABLE IF NOT EXISTS ctf_attack_path_evidence_links (
    node_id TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(node_id, evidence_id),
    FOREIGN KEY(node_id) REFERENCES ctf_attack_path_nodes(id),
    FOREIGN KEY(evidence_id) REFERENCES ctf_evidence(id)
);

CREATE INDEX IF NOT EXISTS idx_ctf_attack_path_evidence_links_evidence
    ON ctf_attack_path_evidence_links(evidence_id);

CREATE TABLE IF NOT EXISTS ctf_command_runs (
    id TEXT PRIMARY KEY,
    public_id TEXT UNIQUE,
    project_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    terminal_id TEXT NOT NULL,
    command TEXT NOT NULL,
    exit_code INTEGER,
    output_ref TEXT,
    output_summary TEXT,
    working_directory TEXT,
    tags_json TEXT NOT NULL DEFAULT '[]',
    started_at TEXT,
    ended_at TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(project_id) REFERENCES ctf_projects(id),
    FOREIGN KEY(session_id) REFERENCES ctf_target_sessions(id)
);

CREATE INDEX IF NOT EXISTS idx_ctf_command_runs_session_created_at
    ON ctf_command_runs(session_id, created_at DESC);

CREATE TABLE IF NOT EXISTS ctf_flags (
    id TEXT PRIMARY KEY,
    public_id TEXT UNIQUE,
    project_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    flag_type TEXT NOT NULL,
    value TEXT NOT NULL,
    source_evidence_id TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(project_id) REFERENCES ctf_projects(id),
    FOREIGN KEY(session_id) REFERENCES ctf_target_sessions(id),
    FOREIGN KEY(source_evidence_id) REFERENCES ctf_evidence(id)
);

CREATE INDEX IF NOT EXISTS idx_ctf_flags_session_created_at ON ctf_flags(session_id, created_at DESC);

CREATE TABLE IF NOT EXISTS ctf_reports (
    id TEXT PRIMARY KEY,
    public_id TEXT NOT NULL UNIQUE,
    project_id TEXT NOT NULL,
    session_id TEXT,
    report_type TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    material_path TEXT NOT NULL,
    artifact_path TEXT NOT NULL,
    created_at TEXT NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(project_id) REFERENCES ctf_projects(id),
    FOREIGN KEY(session_id) REFERENCES ctf_target_sessions(id)
);

CREATE INDEX IF NOT EXISTS idx_ctf_reports_session_created_at
    ON ctf_reports(session_id, created_at DESC);
"""


class ControlCenterSchemaRepository:
    def __init__(self, storage: SQLiteStorage) -> None:
        self.storage = storage
        self.ensure_schema()

    def ensure_schema(self) -> None:
        with self.storage.connect() as connection:
            connection.executescript(CONTROL_CENTER_SCHEMA)
            connection.executescript(
                """
                DROP TABLE IF EXISTS report_artifact_links;
                DROP TABLE IF EXISTS report_finding_links;
                DROP TABLE IF EXISTS reports;
                """
            )
            self._ensure_column(connection, "ctf_command_runs", "output_summary", "TEXT")
            self._ensure_column(connection, "ctf_command_runs", "working_directory", "TEXT")
            self._ensure_column(connection, "ctf_command_runs", "started_at", "TEXT")
            self._ensure_column(connection, "ctf_command_runs", "ended_at", "TEXT")
            self._ensure_nullable_report_session_id(connection)
            self._normalize_event_sequences(connection)
            connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_ctf_events_sequence_unique
                ON ctf_events(sequence)
                """
            )
            connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_ctf_events_session_sequence_unique
                ON ctf_events(session_id, sequence)
                """
            )
            connection.commit()

    def _ensure_column(
        self,
        connection: sqlite3.Connection,
        table_name: str,
        column_name: str,
        column_type: str,
    ) -> None:
        rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        if column_name in {row["name"] for row in rows}:
            return
        connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")

    def _normalize_event_sequences(self, connection: sqlite3.Connection) -> None:
        rows = connection.execute(
            """
            SELECT id
            FROM ctf_events
            ORDER BY sequence ASC, created_at ASC, id ASC
            """
        ).fetchall()
        for index, row in enumerate(rows, start=1):
            connection.execute(
                "UPDATE ctf_events SET sequence = ? WHERE id = ?",
                (index, row["id"]),
            )

    def _ensure_nullable_report_session_id(self, connection: sqlite3.Connection) -> None:
        rows = connection.execute("PRAGMA table_info(ctf_reports)").fetchall()
        session_column = next((row for row in rows if row["name"] == "session_id"), None)
        if session_column is None or int(session_column["notnull"]) == 0:
            return
        connection.executescript(
            """
            ALTER TABLE ctf_reports RENAME TO ctf_reports_old;
            CREATE TABLE ctf_reports (
                id TEXT PRIMARY KEY,
                public_id TEXT NOT NULL UNIQUE,
                project_id TEXT NOT NULL,
                session_id TEXT,
                report_type TEXT NOT NULL,
                title TEXT NOT NULL,
                summary TEXT NOT NULL,
                material_path TEXT NOT NULL,
                artifact_path TEXT NOT NULL,
                created_at TEXT NOT NULL,
                metadata TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY(project_id) REFERENCES ctf_projects(id),
                FOREIGN KEY(session_id) REFERENCES ctf_target_sessions(id)
            );
            INSERT INTO ctf_reports (
                id, public_id, project_id, session_id, report_type, title,
                summary, material_path, artifact_path, created_at, metadata
            )
            SELECT
                id, public_id, project_id, session_id, report_type, title,
                summary, material_path, artifact_path, created_at, metadata
            FROM ctf_reports_old;
            DROP TABLE ctf_reports_old;
            CREATE INDEX IF NOT EXISTS idx_ctf_reports_session_created_at
                ON ctf_reports(session_id, created_at DESC);
            """
        )


class ProjectRepository:
    def __init__(self, storage: SQLiteStorage) -> None:
        self.storage = storage
        ControlCenterSchemaRepository(storage)

    def create(self, project: Project) -> Project:
        with self.storage.connect() as connection:
            self.create_in_connection(connection, project)
            connection.commit()
        return project

    def create_in_connection(self, connection: sqlite3.Connection, project: Project) -> Project:
        if not project.public_id:
            project.public_id = allocate_public_id(connection, table_name="ctf_projects", prefix="P")
        connection.execute(
            """
            INSERT INTO ctf_projects (
                id, public_id, name, description, root_path, status,
                created_at, updated_at, metadata
            ) VALUES (
                :id, :public_id, :name, :description, :root_path, :status,
                :created_at, :updated_at, :metadata
            )
            """,
            project.to_row(),
        )
        return project

    def get(self, identifier: str) -> Project | None:
        with self.storage.connect() as connection:
            row = get_row_by_identifier(
                connection,
                table_name="ctf_projects",
                identifier=identifier,
                order_column="updated_at",
            )
        return Project.from_row(dict(row)) if row else None

    def require(self, identifier: str) -> Project:
        project = self.get(identifier)
        if project is None:
            raise ValueError(f"Project not found: {identifier}")
        return project

    def list(
        self,
        *,
        status: ProjectStatus | None = None,
        limit: int | None = 50,
    ) -> list[Project]:
        query = "SELECT * FROM ctf_projects"
        params: list[object] = []
        if status is not None:
            query += " WHERE status = ?"
            params.append(ProjectStatus(status).value)
        query += " ORDER BY updated_at DESC"
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        with self.storage.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [Project.from_row(dict(row)) for row in rows]

    def update(self, project: Project) -> Project:
        with self.storage.connect() as connection:
            connection.execute(
                """
                UPDATE ctf_projects
                SET
                    public_id = :public_id,
                    name = :name,
                    description = :description,
                    root_path = :root_path,
                    status = :status,
                    created_at = :created_at,
                    updated_at = :updated_at,
                    metadata = :metadata
                WHERE id = :id
                """,
                project.to_row(),
            )
            connection.commit()
        return project


class TargetSessionRepository:
    def __init__(self, storage: SQLiteStorage) -> None:
        self.storage = storage
        ControlCenterSchemaRepository(storage)

    def create(self, session: TargetSession) -> TargetSession:
        with self.storage.connect() as connection:
            self.create_in_connection(connection, session)
            connection.commit()
        return session

    def create_in_connection(self, connection: sqlite3.Connection, session: TargetSession) -> TargetSession:
        if not session.public_id:
            session.public_id = allocate_public_id(
                connection,
                table_name="ctf_target_sessions",
                prefix="T",
            )
        connection.execute(
            """
            INSERT INTO ctf_target_sessions (
                id, public_id, project_id, name, target_value, target_type, status,
                summary, created_at, updated_at, metadata
            ) VALUES (
                :id, :public_id, :project_id, :name, :target_value, :target_type, :status,
                :summary, :created_at, :updated_at, :metadata
            )
            """,
            session.to_row(),
        )
        return session

    def get(self, identifier: str) -> TargetSession | None:
        with self.storage.connect() as connection:
            row = get_row_by_identifier(
                connection,
                table_name="ctf_target_sessions",
                identifier=identifier,
                order_column="updated_at",
            )
        return TargetSession.from_row(dict(row)) if row else None

    def require(self, identifier: str) -> TargetSession:
        session = self.get(identifier)
        if session is None:
            raise ValueError(f"Target session not found: {identifier}")
        return session

    def list(
        self,
        *,
        project_id: str,
        status: TargetSessionStatus | None = None,
        limit: int | None = 50,
    ) -> list[TargetSession]:
        query = "SELECT * FROM ctf_target_sessions WHERE project_id = ?"
        params: list[object] = [project_id]
        if status is not None:
            query += " AND status = ?"
            params.append(TargetSessionStatus(status).value)
        query += " ORDER BY updated_at DESC"
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        with self.storage.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [TargetSession.from_row(dict(row)) for row in rows]

    def update(self, session: TargetSession) -> TargetSession:
        with self.storage.connect() as connection:
            connection.execute(
                """
                UPDATE ctf_target_sessions
                SET
                    public_id = :public_id,
                    project_id = :project_id,
                    name = :name,
                    target_value = :target_value,
                    target_type = :target_type,
                    status = :status,
                    summary = :summary,
                    created_at = :created_at,
                    updated_at = :updated_at,
                    metadata = :metadata
                WHERE id = :id
                """,
                session.to_row(),
            )
            connection.commit()
        return session


class TaskRepository:
    def __init__(self, storage: SQLiteStorage) -> None:
        self.storage = storage
        ControlCenterSchemaRepository(storage)

    def create(self, task: Task) -> Task:
        with self.storage.connect() as connection:
            if not task.public_id:
                task.public_id = allocate_public_id(connection, table_name="ctf_tasks", prefix="TASK")
            connection.execute(
                """
                INSERT INTO ctf_tasks (
                    id, public_id, project_id, session_id, task_type, executor, status,
                    input_json, result_json, started_at, ended_at, error, created_at, updated_at
                ) VALUES (
                    :id, :public_id, :project_id, :session_id, :task_type, :executor, :status,
                    :input_json, :result_json, :started_at, :ended_at, :error, :created_at, :updated_at
                )
                """,
                task.to_row(),
            )
            connection.commit()
        return task

    def get(self, identifier: str) -> Task | None:
        with self.storage.connect() as connection:
            row = get_row_by_identifier(
                connection,
                table_name="ctf_tasks",
                identifier=identifier,
                order_column="updated_at",
            )
        return Task.from_row(dict(row)) if row else None

    def require(self, identifier: str) -> Task:
        task = self.get(identifier)
        if task is None:
            raise ValueError(f"Task not found: {identifier}")
        return task

    def list(
        self,
        *,
        session_id: str,
        status: TaskStatus | None = None,
        limit: int | None = 50,
    ) -> list[Task]:
        query = "SELECT * FROM ctf_tasks WHERE session_id = ?"
        params: list[object] = [session_id]
        if status is not None:
            query += " AND status = ?"
            params.append(TaskStatus(status).value)
        query += " ORDER BY updated_at DESC"
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        with self.storage.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [Task.from_row(dict(row)) for row in rows]

    def update(self, task: Task) -> Task:
        task.updated_at = utc_now_iso()
        with self.storage.connect() as connection:
            connection.execute(
                """
                UPDATE ctf_tasks
                SET
                    public_id = :public_id,
                    project_id = :project_id,
                    session_id = :session_id,
                    task_type = :task_type,
                    executor = :executor,
                    status = :status,
                    input_json = :input_json,
                    result_json = :result_json,
                    started_at = :started_at,
                    ended_at = :ended_at,
                    error = :error,
                    created_at = :created_at,
                    updated_at = :updated_at
                WHERE id = :id
                """,
                task.to_row(),
            )
            connection.commit()
        return task


class EventRepository:
    def __init__(self, storage: SQLiteStorage) -> None:
        self.storage = storage
        ControlCenterSchemaRepository(storage)

    def create(self, event: Event) -> Event:
        with self.storage.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if event.sequence <= 0:
                event.sequence = self._next_sequence(connection)
            connection.execute(
                """
                INSERT INTO ctf_events (
                    id, project_id, session_id, task_id, event_kind, level,
                    payload_json, sequence, created_at
                ) VALUES (
                    :id, :project_id, :session_id, :task_id, :event_kind, :level,
                    :payload_json, :sequence, :created_at
                )
                """,
                event.to_row(),
            )
            connection.commit()
        return event

    def get(self, event_id: str) -> Event | None:
        with self.storage.connect() as connection:
            row = connection.execute("SELECT * FROM ctf_events WHERE id = ?", (event_id,)).fetchone()
        return Event.from_row(dict(row)) if row else None

    def require(self, event_id: str) -> Event:
        event = self.get(event_id)
        if event is None:
            raise ValueError(f"Event not found: {event_id}")
        return event

    def list(
        self,
        *,
        session_id: str | None = None,
        project_id: str | None = None,
        since_sequence: int | None = None,
        limit: int | None = 50,
        descending: bool = True,
    ) -> list[Event]:
        filters: list[str] = []
        params: list[object] = []
        if session_id is not None:
            filters.append("session_id = ?")
            params.append(session_id)
        if project_id is not None:
            filters.append("project_id = ?")
            params.append(project_id)
        if since_sequence is not None:
            filters.append("sequence > ?")
            params.append(since_sequence)
        query = "SELECT * FROM ctf_events"
        if filters:
            query += " WHERE " + " AND ".join(filters)
        direction = "DESC" if descending else "ASC"
        query += f" ORDER BY sequence {direction}, created_at {direction}, id {direction}"
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        with self.storage.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [Event.from_row(dict(row)) for row in rows]

    def _next_sequence(self, connection: sqlite3.Connection) -> int:
        row = connection.execute("SELECT COALESCE(MAX(sequence), 0) AS sequence FROM ctf_events").fetchone()
        return int(row["sequence"]) + 1


class EvidenceRepository:
    def __init__(self, storage: SQLiteStorage) -> None:
        self.storage = storage
        ControlCenterSchemaRepository(storage)

    def create(self, evidence: Evidence) -> Evidence:
        with self.storage.connect() as connection:
            if not evidence.public_id:
                evidence.public_id = allocate_public_id(connection, table_name="ctf_evidence", prefix="EVID")
            connection.execute(
                """
                INSERT INTO ctf_evidence (
                    id, public_id, project_id, session_id, source_task_id, evidence_type,
                    title, summary, content_ref, payload_json, created_at
                ) VALUES (
                    :id, :public_id, :project_id, :session_id, :source_task_id, :evidence_type,
                    :title, :summary, :content_ref, :payload_json, :created_at
                )
                """,
                evidence.to_row(),
            )
            connection.commit()
        return evidence

    def get(self, identifier: str) -> Evidence | None:
        with self.storage.connect() as connection:
            row = get_row_by_identifier(
                connection,
                table_name="ctf_evidence",
                identifier=identifier,
                order_column="created_at",
            )
        return Evidence.from_row(dict(row)) if row else None

    def list(self, *, session_id: str, limit: int | None = 50) -> list[Evidence]:
        return _list_session_entities(
            self.storage,
            table_name="ctf_evidence",
            model_cls=Evidence,
            session_id=session_id,
            limit=limit,
        )


class FindingRepository:
    def __init__(self, storage: SQLiteStorage) -> None:
        self.storage = storage
        ControlCenterSchemaRepository(storage)

    def create(self, finding: Finding) -> Finding:
        with self.storage.connect() as connection:
            if not finding.public_id:
                finding.public_id = allocate_public_id(connection, table_name="ctf_findings", prefix="FIND")
            connection.execute(
                """
                INSERT INTO ctf_findings (
                    id, public_id, project_id, session_id, severity, status,
                    title, description, evidence_refs_json, created_at, updated_at
                ) VALUES (
                    :id, :public_id, :project_id, :session_id, :severity, :status,
                    :title, :description, :evidence_refs_json, :created_at, :updated_at
                )
                """,
                finding.to_row(),
            )
            connection.commit()
        return finding

    def get(self, identifier: str) -> Finding | None:
        with self.storage.connect() as connection:
            row = get_row_by_identifier(
                connection,
                table_name="ctf_findings",
                identifier=identifier,
                order_column="created_at",
            )
        return Finding.from_row(dict(row)) if row else None

    def require(self, identifier: str) -> Finding:
        finding = self.get(identifier)
        if finding is None:
            raise ValueError(f"Finding not found: {identifier}")
        return finding

    def list(self, *, session_id: str, limit: int | None = 50) -> list[Finding]:
        return _list_session_entities(
            self.storage,
            table_name="ctf_findings",
            model_cls=Finding,
            session_id=session_id,
            limit=limit,
        )

    def update(self, finding: Finding) -> Finding:
        finding.updated_at = utc_now_iso()
        with self.storage.connect() as connection:
            connection.execute(
                """
                UPDATE ctf_findings
                SET
                    public_id = :public_id,
                    project_id = :project_id,
                    session_id = :session_id,
                    severity = :severity,
                    status = :status,
                    title = :title,
                    description = :description,
                    evidence_refs_json = :evidence_refs_json,
                    created_at = :created_at,
                    updated_at = :updated_at
                WHERE id = :id
                """,
                finding.to_row(),
            )
            connection.commit()
        return finding


class AttackPathNodeRepository:
    def __init__(self, storage: SQLiteStorage) -> None:
        self.storage = storage
        ControlCenterSchemaRepository(storage)

    def create(self, node: AttackPathNode) -> AttackPathNode:
        with self.storage.connect() as connection:
            if not node.public_id:
                node.public_id = allocate_public_id(
                    connection,
                    table_name="ctf_attack_path_nodes",
                    prefix="AP",
                )
            connection.execute(
                """
                INSERT INTO ctf_attack_path_nodes (
                    id, public_id, project_id, session_id, stage, title, status,
                    source_ref, next_action, created_at
                ) VALUES (
                    :id, :public_id, :project_id, :session_id, :stage, :title, :status,
                    :source_ref, :next_action, :created_at
                )
                """,
                node.to_row(),
            )
            connection.commit()
        return node

    def get(self, identifier: str) -> AttackPathNode | None:
        with self.storage.connect() as connection:
            row = get_row_by_identifier(
                connection,
                table_name="ctf_attack_path_nodes",
                identifier=identifier,
                order_column="created_at",
            )
        return AttackPathNode.from_row(dict(row)) if row else None

    def list(self, *, session_id: str, limit: int | None = 50) -> list[AttackPathNode]:
        return _list_session_entities(
            self.storage,
            table_name="ctf_attack_path_nodes",
            model_cls=AttackPathNode,
            session_id=session_id,
            limit=limit,
        )


class AttackPathEvidenceLinkRepository:
    def __init__(self, storage: SQLiteStorage) -> None:
        self.storage = storage
        ControlCenterSchemaRepository(storage)

    def link(self, *, node_id: str, evidence_id: str) -> None:
        with self.storage.connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO ctf_attack_path_evidence_links (
                    node_id, evidence_id, created_at
                ) VALUES (?, ?, ?)
                """,
                (node_id, evidence_id, utc_now_iso()),
            )
            connection.commit()

    def list_evidence_ids(self, *, node_id: str) -> list[str]:
        with self.storage.connect() as connection:
            rows = connection.execute(
                """
                SELECT evidence_id
                FROM ctf_attack_path_evidence_links
                WHERE node_id = ?
                ORDER BY created_at ASC
                """,
                (node_id,),
            ).fetchall()
        return [row["evidence_id"] for row in rows]

    def list_node_ids(self, *, evidence_id: str) -> list[str]:
        with self.storage.connect() as connection:
            rows = connection.execute(
                """
                SELECT node_id
                FROM ctf_attack_path_evidence_links
                WHERE evidence_id = ?
                ORDER BY created_at ASC
                """,
                (evidence_id,),
            ).fetchall()
        return [row["node_id"] for row in rows]


class CommandRunRepository:
    def __init__(self, storage: SQLiteStorage) -> None:
        self.storage = storage
        ControlCenterSchemaRepository(storage)

    def create(self, command: CommandRun) -> CommandRun:
        with self.storage.connect() as connection:
            if not command.public_id:
                command.public_id = allocate_public_id(
                    connection,
                    table_name="ctf_command_runs",
                    prefix="CMD",
                )
            connection.execute(
                """
                INSERT INTO ctf_command_runs (
                    id, public_id, project_id, session_id, terminal_id, command,
                    exit_code, output_ref, output_summary, working_directory,
                    tags_json, started_at, ended_at, created_at
                ) VALUES (
                    :id, :public_id, :project_id, :session_id, :terminal_id, :command,
                    :exit_code, :output_ref, :output_summary, :working_directory,
                    :tags_json, :started_at, :ended_at, :created_at
                )
                """,
                command.to_row(),
            )
            connection.commit()
        return command

    def get(self, identifier: str) -> CommandRun | None:
        with self.storage.connect() as connection:
            row = get_row_by_identifier(
                connection,
                table_name="ctf_command_runs",
                identifier=identifier,
                order_column="created_at",
            )
        return CommandRun.from_row(dict(row)) if row else None

    def list(self, *, session_id: str, limit: int | None = 50) -> list[CommandRun]:
        return _list_session_entities(
            self.storage,
            table_name="ctf_command_runs",
            model_cls=CommandRun,
            session_id=session_id,
            limit=limit,
        )

    def list_by_terminal(self, *, terminal_id: str, limit: int | None = 50) -> list[CommandRun]:
        query = "SELECT * FROM ctf_command_runs WHERE terminal_id = ? ORDER BY created_at DESC"
        params: list[object] = [terminal_id]
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        with self.storage.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [CommandRun.from_row(dict(row)) for row in rows]

    def update(self, command: CommandRun) -> CommandRun:
        with self.storage.connect() as connection:
            connection.execute(
                """
                UPDATE ctf_command_runs
                SET
                    public_id = :public_id,
                    project_id = :project_id,
                    session_id = :session_id,
                    terminal_id = :terminal_id,
                    command = :command,
                    exit_code = :exit_code,
                    output_ref = :output_ref,
                    output_summary = :output_summary,
                    working_directory = :working_directory,
                    tags_json = :tags_json,
                    started_at = :started_at,
                    ended_at = :ended_at,
                    created_at = :created_at
                WHERE id = :id
                """,
                command.to_row(),
            )
            connection.commit()
        return command


class FlagRepository:
    def __init__(self, storage: SQLiteStorage) -> None:
        self.storage = storage
        ControlCenterSchemaRepository(storage)

    def create(self, flag: Flag) -> Flag:
        with self.storage.connect() as connection:
            if not flag.public_id:
                flag.public_id = allocate_public_id(connection, table_name="ctf_flags", prefix="FLAG")
            connection.execute(
                """
                INSERT INTO ctf_flags (
                    id, public_id, project_id, session_id, flag_type, value,
                    source_evidence_id, created_at
                ) VALUES (
                    :id, :public_id, :project_id, :session_id, :flag_type, :value,
                    :source_evidence_id, :created_at
                )
                """,
                flag.to_row(),
            )
            connection.commit()
        return flag

    def get(self, identifier: str) -> Flag | None:
        with self.storage.connect() as connection:
            row = get_row_by_identifier(
                connection,
                table_name="ctf_flags",
                identifier=identifier,
                order_column="created_at",
            )
        return Flag.from_row(dict(row)) if row else None

    def list(self, *, session_id: str, limit: int | None = 50) -> list[Flag]:
        return _list_session_entities(
            self.storage,
            table_name="ctf_flags",
            model_cls=Flag,
            session_id=session_id,
            limit=limit,
        )


class CTFReportRepository:
    def __init__(self, storage: SQLiteStorage) -> None:
        self.storage = storage
        ControlCenterSchemaRepository(storage)

    def create(self, report: CTFReport) -> CTFReport:
        with self.storage.connect() as connection:
            if not report.public_id:
                report.public_id = allocate_public_id(connection, table_name="ctf_reports", prefix="RPT")
            connection.execute(
                """
                INSERT INTO ctf_reports (
                    id, public_id, project_id, session_id, report_type, title,
                    summary, material_path, artifact_path, created_at, metadata
                ) VALUES (
                    :id, :public_id, :project_id, :session_id, :report_type, :title,
                    :summary, :material_path, :artifact_path, :created_at, :metadata
                )
                """,
                report.to_row(),
            )
            connection.commit()
        return report

    def update(self, report: CTFReport) -> CTFReport:
        with self.storage.connect() as connection:
            connection.execute(
                """
                UPDATE ctf_reports
                SET
                    public_id = :public_id,
                    project_id = :project_id,
                    session_id = :session_id,
                    report_type = :report_type,
                    title = :title,
                    summary = :summary,
                    material_path = :material_path,
                    artifact_path = :artifact_path,
                    created_at = :created_at,
                    metadata = :metadata
                WHERE id = :id
                """,
                report.to_row(),
            )
            connection.commit()
        return report

    def get(self, identifier: str) -> CTFReport | None:
        with self.storage.connect() as connection:
            row = get_row_by_identifier(
                connection,
                table_name="ctf_reports",
                identifier=identifier,
                order_column="created_at",
            )
        return CTFReport.from_row(dict(row)) if row else None

    def require(self, identifier: str) -> CTFReport:
        report = self.get(identifier)
        if report is None:
            raise ValueError(f"Report not found: {identifier}")
        return report

    def list(self, *, session_id: str, limit: int | None = 50) -> list[CTFReport]:
        return _list_session_entities(
            self.storage,
            table_name="ctf_reports",
            model_cls=CTFReport,
            session_id=session_id,
            limit=limit,
        )

    def list_project_reports(self, *, project_id: str, limit: int | None = 50) -> list[CTFReport]:
        query = "SELECT * FROM ctf_reports WHERE project_id = ? AND session_id IS NULL ORDER BY created_at DESC"
        params: list[object] = [project_id]
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        with self.storage.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [CTFReport.from_row(dict(row)) for row in rows]


def _list_session_entities(
    storage: SQLiteStorage,
    *,
    table_name: str,
    model_cls,
    session_id: str,
    limit: int | None,
):
    query = f"SELECT * FROM {table_name} WHERE session_id = ? ORDER BY created_at DESC"
    params: list[object] = [session_id]
    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)
    with storage.connect() as connection:
        rows = connection.execute(query, params).fetchall()
    return [model_cls.from_row(dict(row)) for row in rows]
