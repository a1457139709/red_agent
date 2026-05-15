from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from agent.settings import Settings, get_settings
from models.control_center import AttackPathNode, CommandRun, Event, Evidence, TargetSession
from models.run import utc_now_iso
from storage.project_paths import project_session_root
from storage.repositories.control_center import (
    AttackPathEvidenceLinkRepository,
    AttackPathNodeRepository,
    CommandRunRepository,
    EventRepository,
    EvidenceRepository,
    ProjectRepository,
    TargetSessionRepository,
)
from storage.sqlite import SQLiteStorage
from terminal.command_log import TerminalCommandLogger
from terminal.pty_manager import PtyManager, PtyTerminal

from .control_center_base import ControlCenterService


@dataclass(frozen=True, slots=True)
class TerminalDescriptor:
    terminal_id: str
    project_id: str
    session_id: str
    working_directory: str
    status: str
    created_at: str


@dataclass(frozen=True, slots=True)
class TerminalContext:
    project_id: str
    session_id: str
    working_directory: str


class TerminalService(ControlCenterService):
    def __init__(self, *, settings: Settings, pty_manager: PtyManager | None = None) -> None:
        storage = SQLiteStorage(settings.sqlite_path)
        object.__setattr__(self, "settings", settings)
        object.__setattr__(self, "pty_manager", pty_manager or PtyManager())
        object.__setattr__(self, "project_repository", ProjectRepository(storage))
        object.__setattr__(self, "session_repository", TargetSessionRepository(storage))
        object.__setattr__(self, "event_repository", EventRepository(storage))
        object.__setattr__(self, "command_repository", CommandRunRepository(storage))
        object.__setattr__(self, "evidence_repository", EvidenceRepository(storage))
        object.__setattr__(self, "node_repository", AttackPathNodeRepository(storage))
        object.__setattr__(self, "link_repository", AttackPathEvidenceLinkRepository(storage))
        object.__setattr__(
            self,
            "command_logger",
            TerminalCommandLogger(settings=settings, repository=CommandRunRepository(storage)),
        )
        object.__setattr__(self, "_terminal_contexts", {})
        object.__setattr__(self, "_terminal_created_at", {})

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "TerminalService":
        return cls(settings=settings or get_settings())

    def open_terminal(self, *, session_identifier: str, rows: int = 24, cols: int = 80) -> TerminalDescriptor:
        session = self.session_repository.require(session_identifier)
        self.project_repository.require(session.project_id)
        working_directory = project_session_root(
            self.settings,
            project_id=session.project_id,
            session_id=session.id,
        )
        working_directory.mkdir(parents=True, exist_ok=True)
        terminal_id = f"term-{uuid4()}"

        def on_output(chunk: str) -> None:
            self._handle_terminal_output(terminal_id=terminal_id, chunk=chunk)

        def on_exit(exit_code: int | None) -> None:
            self._handle_terminal_exit(terminal_id=terminal_id, exit_code=exit_code)

        terminal: PtyTerminal = self.pty_manager.open(
            cwd=working_directory,
            terminal_id=terminal_id,
            rows=rows,
            cols=cols,
            on_output=on_output,
            on_exit=on_exit,
        )
        created_at = utc_now_iso()
        self._terminal_contexts[terminal.terminal_id] = TerminalContext(
            project_id=session.project_id,
            session_id=session.id,
            working_directory=str(working_directory),
        )
        self._terminal_created_at[terminal.terminal_id] = created_at
        descriptor = TerminalDescriptor(
            terminal_id=terminal.terminal_id,
            project_id=session.project_id,
            session_id=session.id,
            working_directory=str(working_directory),
            status="open",
            created_at=created_at,
        )
        self._record_event(
            context=self._terminal_contexts[terminal.terminal_id],
            event_kind="terminal.opened",
            payload=_terminal_payload(descriptor),
        )
        return descriptor

    def handle_input(self, *, terminal_id: str, data: str) -> CommandRun | None:
        context = self._require_context(terminal_id)
        command = self.command_logger.observe_input(
            terminal_id=terminal_id,
            project_id=context.project_id,
            session_id=context.session_id,
            working_directory=context.working_directory,
            data=data,
        )
        self.pty_manager.write(terminal_id, data)
        return command

    def resize_terminal(self, *, terminal_id: str, rows: int, cols: int) -> None:
        self._require_context(terminal_id)
        self.pty_manager.resize(terminal_id, rows=rows, cols=cols)

    def close_terminal(self, *, terminal_id: str) -> None:
        self._require_context(terminal_id)
        self.pty_manager.close(terminal_id)

    def list_commands(self, *, terminal_identifier: str, limit: int | None = None) -> list[CommandRun]:
        return self.command_repository.list_by_terminal(terminal_id=terminal_identifier, limit=limit)

    def list_session_commands(self, *, session_identifier: str, limit: int | None = None) -> list[CommandRun]:
        session = self.session_repository.require(session_identifier)
        return self.command_repository.list(session_id=session.id, limit=limit)

    def create_evidence_from_command(
        self,
        *,
        command_identifier: str,
        title: str,
        selected_text: str,
        summary: str | None = None,
        attack_path_node_id: str | None = None,
        tags: list[str] | None = None,
    ) -> Evidence:
        command = self.command_repository.get(command_identifier)
        if command is None:
            raise ValueError(f"Command run not found: {command_identifier}")
        selected = selected_text.strip()
        if not selected:
            raise ValueError("selected_text must be non-empty.")
        evidence = self.evidence_repository.create(
            Evidence.create(
                project_id=command.project_id,
                session_id=command.session_id,
                evidence_type="terminal_output",
                title=title,
                summary=summary or _selected_summary(selected),
                content_ref=command.output_ref,
                payload={
                    "command_run_id": command.id,
                    "terminal_id": command.terminal_id,
                    "command": command.command,
                    "selected_text": selected,
                    "tags": list(tags or []),
                },
            )
        )
        if attack_path_node_id:
            node = self.node_repository.get(attack_path_node_id)
            if node is None or node.session_id != command.session_id:
                raise ValueError(f"Attack path node not found in command session: {attack_path_node_id}")
            self.link_repository.link(node_id=node.id, evidence_id=evidence.id)
        else:
            node = self.node_repository.create(
                AttackPathNode.create(
                    project_id=command.project_id,
                    session_id=command.session_id,
                    stage="terminal-evidence",
                    title=title,
                    status="open",
                    source_ref=evidence.id,
                    next_action="Review terminal output and decide whether it supports an attack-path step.",
                )
            )
            self.link_repository.link(node_id=node.id, evidence_id=evidence.id)
        if tags:
            command.tags = _merge_tags(command.tags, tags)
            self.command_repository.update(command)
        self._record_event(
            context=TerminalContext(
                project_id=command.project_id,
                session_id=command.session_id,
                working_directory=command.working_directory or "",
            ),
            event_kind="evidence.created",
            payload={
                "evidence_id": evidence.id,
                "public_id": evidence.public_id,
                "evidence_type": evidence.evidence_type,
                "source": "terminal",
            },
        )
        return evidence

    def shutdown(self) -> None:
        self.pty_manager.shutdown()

    def _handle_terminal_output(self, *, terminal_id: str, chunk: str) -> None:
        context = self._terminal_contexts.get(terminal_id)
        if context is None:
            return
        self.command_logger.observe_output(terminal_id=terminal_id, data=chunk)
        self._record_event(
            context=context,
            event_kind="terminal.output",
            payload={"terminal_id": terminal_id, "chunk": chunk},
        )

    def _handle_terminal_exit(self, *, terminal_id: str, exit_code: int | None) -> None:
        context = self._terminal_contexts.pop(terminal_id, None)
        self._terminal_created_at.pop(terminal_id, None)
        if context is None:
            return
        finalized = self.command_logger.finalize_active(terminal_id=terminal_id, exit_code=exit_code)
        payload: dict[str, Any] = {"terminal_id": terminal_id, "exit_code": exit_code}
        if finalized is not None:
            payload["command_run_id"] = finalized.id
        self._record_event(context=context, event_kind="terminal.exited", payload=payload)

    def _require_context(self, terminal_id: str) -> TerminalContext:
        context = self._terminal_contexts.get(terminal_id)
        if context is None:
            raise ValueError(f"Terminal not found: {terminal_id}")
        return context

    def _record_event(self, *, context: TerminalContext, event_kind: str, payload: dict[str, Any]) -> Event:
        return self.event_repository.create(
            Event.create(
                project_id=context.project_id,
                session_id=context.session_id,
                event_kind=event_kind,
                level="info",
                payload=payload,
            )
        )


def _terminal_payload(descriptor: TerminalDescriptor) -> dict[str, Any]:
    return {
        "terminal_id": descriptor.terminal_id,
        "project_id": descriptor.project_id,
        "session_id": descriptor.session_id,
        "working_directory": descriptor.working_directory,
        "status": descriptor.status,
        "created_at": descriptor.created_at,
    }


def _selected_summary(selected_text: str) -> str:
    return selected_text.replace("\r", "").replace("\n", " ")[:200]


def _merge_tags(existing: list[str], incoming: list[str]) -> list[str]:
    merged: list[str] = []
    for tag in [*existing, *incoming]:
        normalized = tag.strip()
        if normalized and normalized not in merged:
            merged.append(normalized)
    return merged
