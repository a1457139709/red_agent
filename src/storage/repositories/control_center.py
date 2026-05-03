from __future__ import annotations

import sqlite3

from models.control_center import (
    AttackPathNode,
    CommandRun,
    Event,
    Evidence,
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

CREATE TABLE IF NOT EXISTS ctf_command_runs (
    id TEXT PRIMARY KEY,
    public_id TEXT UNIQUE,
    project_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    terminal_id TEXT NOT NULL,
    command TEXT NOT NULL,
    exit_code INTEGER,
    output_ref TEXT,
    tags_json TEXT NOT NULL DEFAULT '[]',
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
"""


class ControlCenterSchemaRepository:
    def __init__(self, storage: SQLiteStorage) -> None:
        self.storage = storage
        self.ensure_schema()

    def ensure_schema(self) -> None:
        with self.storage.connect() as connection:
            connection.executescript(CONTROL_CENTER_SCHEMA)
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
                    exit_code, output_ref, tags_json, created_at
                ) VALUES (
                    :id, :public_id, :project_id, :session_id, :terminal_id, :command,
                    :exit_code, :output_ref, :tags_json, :created_at
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
