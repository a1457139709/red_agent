from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from agent.provider import create_model
from agent.settings import Settings, get_settings
from models.control_center import CTFReport, Event, Project, TargetSession
from storage.project_paths import project_session_reports_dir
from storage.repositories.control_center import (
    AttackPathNodeRepository,
    CTFReportRepository,
    CommandRunRepository,
    EventRepository,
    EvidenceRepository,
    FindingRepository,
    FlagRepository,
    ProjectRepository,
    TargetSessionRepository,
    TaskRepository,
)
from storage.sqlite import SQLiteStorage


ModelFactory = Callable[[Settings], Any]

WRITEUP_SECTIONS = (
    "Overview",
    "Target",
    "Recon",
    "Open Ports",
    "Web Enumeration",
    "Vulnerability Hypotheses",
    "Verification",
    "Exploit Notes",
    "Privilege Escalation Notes",
    "Flags and Loot",
    "Command Log",
    "Evidence Index",
    "TODO",
)


@dataclass(frozen=True, slots=True)
class WriteupResult:
    report: CTFReport
    material_markdown: str
    writeup_markdown: str


class WriteupService:
    def __init__(
        self,
        *,
        settings: Settings,
        model_factory: ModelFactory = create_model,
    ) -> None:
        storage = SQLiteStorage(settings.sqlite_path)
        self.settings = settings
        self.model_factory = model_factory
        self.project_repository = ProjectRepository(storage)
        self.session_repository = TargetSessionRepository(storage)
        self.task_repository = TaskRepository(storage)
        self.evidence_repository = EvidenceRepository(storage)
        self.finding_repository = FindingRepository(storage)
        self.attack_path_repository = AttackPathNodeRepository(storage)
        self.command_repository = CommandRunRepository(storage)
        self.flag_repository = FlagRepository(storage)
        self.report_repository = CTFReportRepository(storage)
        self.event_repository = EventRepository(storage)

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "WriteupService":
        return cls(settings=settings or get_settings())

    def list_reports(self, *, session_identifier: str, limit: int | None = 50) -> list[CTFReport]:
        session = self.session_repository.require(session_identifier)
        return self.report_repository.list(session_id=session.id, limit=limit)

    def require_report(self, report_identifier: str) -> CTFReport:
        return self.report_repository.require(report_identifier)

    def read_report_markdown(self, report_identifier: str) -> str:
        report = self.require_report(report_identifier)
        return Path(report.artifact_path).read_text(encoding="utf-8")

    def generate_session_writeup(self, *, session_identifier: str) -> WriteupResult:
        session = self.session_repository.require(session_identifier)
        project = self.project_repository.require(session.project_id)
        context_markdown = self._build_context_markdown(project=project, session=session)
        model = self.model_factory(self.settings)
        material_markdown = _message_text(
            model.invoke(
                [
                    SystemMessage(content=_material_system_prompt()),
                    HumanMessage(content=context_markdown),
                ]
            )
        )
        if not material_markdown:
            material_markdown = context_markdown

        writeup_markdown = _message_text(
            model.invoke(
                [
                    SystemMessage(content=_writer_system_prompt()),
                    HumanMessage(content=material_markdown),
                ]
            )
        )
        if not writeup_markdown:
            raise ValueError("Writeup Agent returned an empty report.")

        reports_dir = project_session_reports_dir(
            self.settings,
            project_id=project.id,
            session_id=session.id,
        )
        reports_dir.mkdir(parents=True, exist_ok=True)
        material_path = reports_dir / "report_material.md"
        writeup_path = reports_dir / "writeup.md"
        material_path.write_text(material_markdown, encoding="utf-8")
        writeup_path.write_text(writeup_markdown, encoding="utf-8")

        report = self.report_repository.create(
            CTFReport.create(
                project_id=project.id,
                session_id=session.id,
                title=f"{session.name} writeup",
                summary=_first_non_empty_line(writeup_markdown) or f"Session writeup for {session.name}.",
                material_path=str(material_path),
                artifact_path=str(writeup_path),
                metadata={
                    "sections": list(WRITEUP_SECTIONS),
                    "material_source": "llm_structured_summary",
                    "writer": "llm_writeup_agent",
                },
            )
        )
        self.event_repository.create(
            Event.create(
                project_id=project.id,
                session_id=session.id,
                event_kind="report.generated",
                level="info",
                payload={
                    "report_id": report.id,
                    "public_id": report.public_id,
                    "artifact_path": report.artifact_path,
                    "summary": report.summary,
                },
            )
        )
        return WriteupResult(report=report, material_markdown=material_markdown, writeup_markdown=writeup_markdown)

    def _build_context_markdown(self, *, project: Project, session: TargetSession) -> str:
        tasks = self.task_repository.list(session_id=session.id, limit=None)
        evidence = self.evidence_repository.list(session_id=session.id, limit=None)
        findings = self.finding_repository.list(session_id=session.id, limit=None)
        nodes = self.attack_path_repository.list(session_id=session.id, limit=None)
        commands = self.command_repository.list(session_id=session.id, limit=None)
        flags = self.flag_repository.list(session_id=session.id, limit=None)
        lines = [
            "# Session Writeup Source Material",
            "",
            "## Project",
            f"- Project id: {project.public_id or project.id}",
            f"- Name: {project.name}",
            f"- Description: {project.description or 'TODO: not recorded'}",
            "",
            "## Session",
            f"- Session id: {session.public_id or session.id}",
            f"- Name: {session.name}",
            f"- Target: {session.target_type.value} {session.target_value}",
            f"- Summary: {session.summary or 'TODO: not recorded'}",
            "",
            "## Required Writeup Sections",
            *[f"- {section}" for section in WRITEUP_SECTIONS],
            "",
            "## Tasks",
            *_task_lines(tasks),
            "",
            "## Open Ports",
            *_open_port_lines(tasks),
            "",
            "## Web Enumeration",
            *_web_enum_lines(tasks),
            "",
            "## Attack Path",
            *([
                f"- {node.public_id}: {node.stage} / {node.status} / {node.title}"
                + (f" / next: {node.next_action}" if node.next_action else "")
                for node in nodes
            ] or ["- TODO: no attack path nodes recorded"]),
            "",
            "## Findings",
            *([
                f"- {finding.public_id}: {finding.title} ({finding.severity}, {finding.status})"
                + (f" evidence={', '.join(finding.evidence_refs)}" if finding.evidence_refs else "")
                + (f" - {finding.description}" if finding.description else "")
                for finding in findings
            ] or ["- TODO: no findings recorded"]),
            "",
            "## Evidence",
            *([
                f"- {item.public_id}: {item.evidence_type} / {item.title}"
                + (f" - {item.summary}" if item.summary else "")
                + (f" / ref={item.content_ref}" if item.content_ref else "")
                for item in evidence
            ] or ["- TODO: no evidence recorded"]),
            "",
            "## Command Log",
            *([
                f"- {command.public_id}: `{command.command}` exit={command.exit_code if command.exit_code is not None else 'unknown'}"
                + (f" cwd={command.working_directory}" if command.working_directory else "")
                + (f" summary={command.output_summary}" if command.output_summary else "")
                for command in commands
            ] or ["- TODO: no command runs recorded"]),
            "",
            "## Flags and Loot",
            *([
                f"- {flag.public_id}: {flag.flag_type} `{flag.value}`"
                + (f" evidence={flag.source_evidence_id}" if flag.source_evidence_id else "")
                for flag in flags
            ] or ["- TODO: no flags recorded"]),
            "",
            "## Rules",
            "- Do not invent commands, vulnerabilities, findings, flags, or exploitation steps.",
            "- Use TODO when a section has no recorded support.",
            "- Preserve public ids for evidence, findings, commands, tasks, and flags.",
        ]
        return "\n".join(lines)


def _task_lines(tasks: list[Any]) -> list[str]:
    if not tasks:
        return ["- TODO: no tasks recorded"]
    return [
        f"- {task.public_id}: {task.task_type} via {task.executor} status={task.status.value}"
        + (f" summary={task.result_json.get('summary')}" if task.result_json.get("summary") else "")
        + (f" error={task.error}" if task.error else "")
        for task in tasks
    ]


def _open_port_lines(tasks: list[Any]) -> list[str]:
    lines: list[str] = []
    for task in tasks:
        structured = task.result_json.get("structured") if isinstance(task.result_json.get("structured"), dict) else {}
        for port in structured.get("open_ports") or []:
            if isinstance(port, dict):
                lines.append(
                    f"- {task.public_id}: {port.get('port')}/{port.get('protocol', 'tcp')} "
                    f"{port.get('service') or 'unknown'} {port.get('product') or ''} {port.get('version') or ''}".strip()
                )
    return lines or ["- TODO: no open ports recorded"]


def _web_enum_lines(tasks: list[Any]) -> list[str]:
    lines: list[str] = []
    for task in tasks:
        structured = task.result_json.get("structured") if isinstance(task.result_json.get("structured"), dict) else {}
        for key in ("directories", "entries", "results", "hits"):
            for item in structured.get(key) or []:
                if isinstance(item, dict):
                    target = item.get("url") or item.get("path") or item.get("matched_at") or item.get("matched-at")
                    if target:
                        lines.append(f"- {task.public_id}: {target} {item}")
    return lines or ["- TODO: no web enumeration recorded"]


def _material_system_prompt() -> str:
    return (
        "You are the primary red-code CTF Agent. Summarize the supplied structured session records "
        "into Markdown source material for a writeup writer. Do not invent facts. Keep all public ids."
    )


def _writer_system_prompt() -> str:
    sections = ", ".join(WRITEUP_SECTIONS)
    return (
        "You are a report-writing assistant. Generate a concise Markdown CTF Session writeup from the supplied "
        f"source material. Include these sections exactly: {sections}. Do not invent missing steps; write TODO instead."
    )


def _message_text(message: Any) -> str:
    content = message.content if isinstance(message, AIMessage) else getattr(message, "content", message)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "\n".join(part.strip() for part in parts if part.strip())
    return str(content).strip() if content else ""


def _first_non_empty_line(markdown: str) -> str | None:
    for line in markdown.splitlines():
        normalized = line.strip().lstrip("#").strip()
        if normalized:
            return normalized
    return None
