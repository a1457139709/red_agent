from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
import re
import shlex
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from agent.provider import create_model
from agent.settings import Settings, get_settings
from models.control_center import CTFReport, Event, Project, ReportType, TargetSession
from storage.project_paths import project_reports_dir, project_session_reports_dir
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

PUBLIC_ID_PATTERN = re.compile(r"\b(?:P|T|TASK|EVID|FIND|AP|CMD|FLAG|RPT)\d{4}\b")
INLINE_CODE_PATTERN = re.compile(r"`([^`]+)`")
FACTUAL_SECTIONS = (
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
)


@dataclass(frozen=True, slots=True)
class WriteupResult:
    report: CTFReport
    material_markdown: str
    writeup_markdown: str


@dataclass(slots=True)
class SourceIndex:
    public_ids: set[str] = field(default_factory=set)
    commands: set[str] = field(default_factory=set)

    def merge(self, other: "SourceIndex") -> None:
        self.public_ids.update(other.public_ids)
        self.commands.update(other.commands)


@dataclass(frozen=True, slots=True)
class ValidationResult:
    errors: list[str]
    warnings: list[str]


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

    def list_project_reports(self, *, project_identifier: str, limit: int | None = 50) -> list[CTFReport]:
        project = self.project_repository.require(project_identifier)
        return self.report_repository.list_project_reports(project_id=project.id, limit=limit)

    def require_report(self, report_identifier: str) -> CTFReport:
        return self.report_repository.require(report_identifier)

    def read_report_markdown(self, report_identifier: str) -> str:
        report = self.require_report(report_identifier)
        return Path(report.artifact_path).read_text(encoding="utf-8")

    def generate_session_writeup(self, *, session_identifier: str) -> WriteupResult:
        session = self.session_repository.require(session_identifier)
        project = self.project_repository.require(session.project_id)
        context_markdown, source_index = self._build_session_context(project=project, session=session)
        return self._generate_writeup(
            project=project,
            session=session,
            report_type=ReportType.SESSION_WRITEUP,
            title=f"{session.name} writeup",
            scope_label="Session",
            context_markdown=context_markdown,
            source_index=source_index,
            base_reports_dir=project_session_reports_dir(self.settings, project_id=project.id, session_id=session.id),
            event_session_id=session.id,
        )

    def generate_project_writeup(self, *, project_identifier: str) -> WriteupResult:
        project = self.project_repository.require(project_identifier)
        sessions = self.session_repository.list(project_id=project.id, limit=None)
        context_markdown, source_index = self._build_project_context(project=project, sessions=sessions)
        return self._generate_writeup(
            project=project,
            session=None,
            report_type=ReportType.PROJECT_WRITEUP,
            title=f"{project.name} project writeup",
            scope_label="Project",
            context_markdown=context_markdown,
            source_index=source_index,
            base_reports_dir=project_reports_dir(self.settings, project.id),
            event_session_id=None,
        )

    def _generate_writeup(
        self,
        *,
        project: Project,
        session: TargetSession | None,
        report_type: ReportType,
        title: str,
        scope_label: str,
        context_markdown: str,
        source_index: SourceIndex,
        base_reports_dir: Path,
        event_session_id: str | None,
    ) -> WriteupResult:
        model = self.model_factory(self.settings)
        material_markdown = _message_text(
            model.invoke(
                [
                    SystemMessage(content=_material_system_prompt(scope_label)),
                    HumanMessage(content=context_markdown),
                ]
            )
        )
        if not material_markdown:
            material_markdown = context_markdown

        writeup_markdown = _message_text(
            model.invoke(
                [
                    SystemMessage(content=_writer_system_prompt(scope_label)),
                    HumanMessage(content=material_markdown),
                ]
            )
        )
        if not writeup_markdown:
            raise ValueError("Writeup Agent returned an empty report.")

        validation = validate_writeup(markdown=writeup_markdown, source_index=source_index)
        if validation.errors:
            raise ValueError("Writeup validation failed: " + "; ".join(validation.errors))
        final_markdown = _append_validation_notes(writeup_markdown, validation)

        report = self.report_repository.create(
            CTFReport.create(
                project_id=project.id,
                session_id=session.id if session else None,
                report_type=report_type,
                title=title,
                summary=_first_non_empty_line(final_markdown) or title,
                material_path=str(base_reports_dir / "_pending" / "report_material.md"),
                artifact_path=str(base_reports_dir / "_pending" / "writeup.md"),
                metadata={
                    "scope": "project" if session is None else "session",
                    "source_session_ids": [] if session is None else [session.id],
                    "sections": list(WRITEUP_SECTIONS),
                    "material_source": "llm_structured_summary",
                    "writer": "llm_writeup_agent",
                    "validation": {"errors": validation.errors, "warnings": validation.warnings},
                },
            )
        )

        report_dir = base_reports_dir / report.public_id
        report_dir.mkdir(parents=True, exist_ok=True)
        material_path = report_dir / "report_material.md"
        writeup_path = report_dir / "writeup.md"
        material_path.write_text(material_markdown, encoding="utf-8")
        writeup_path.write_text(final_markdown, encoding="utf-8")
        report.material_path = str(material_path)
        report.artifact_path = str(writeup_path)
        if session is None:
            report.metadata["source_session_ids"] = [item for item in sorted(source_index.public_ids) if item.startswith("T")]
        self.report_repository.update(report)

        self.event_repository.create(
            Event.create(
                project_id=project.id,
                session_id=event_session_id,
                event_kind="report.generated",
                level="info",
                payload={
                    "report_id": report.id,
                    "public_id": report.public_id,
                    "scope": report.metadata["scope"],
                    "artifact_path": report.artifact_path,
                    "summary": report.summary,
                    "validation": report.metadata["validation"],
                },
            )
        )
        return WriteupResult(report=report, material_markdown=material_markdown, writeup_markdown=final_markdown)

    def _build_project_context(self, *, project: Project, sessions: list[TargetSession]) -> tuple[str, SourceIndex]:
        index = SourceIndex(public_ids={_public(project)})
        lines = [
            "# Project Writeup Source Material",
            "",
            "## Project",
            f"- Project id: {_public(project)}",
            f"- Name: {project.name}",
            f"- Description: {project.description or 'TODO: not recorded'}",
            "",
            "## Sessions",
        ]
        if not sessions:
            lines.append("- TODO: no sessions recorded")
        for session in sessions:
            session_context, session_index = self._build_session_context(project=project, session=session)
            index.merge(session_index)
            lines.extend(["", f"## Session Material: {_public(session)}", session_context])
        lines.extend(_source_rules())
        return "\n".join(lines), index

    def _build_session_context(self, *, project: Project, session: TargetSession) -> tuple[str, SourceIndex]:
        tasks = self.task_repository.list(session_id=session.id, limit=None)
        evidence = self.evidence_repository.list(session_id=session.id, limit=None)
        findings = self.finding_repository.list(session_id=session.id, limit=None)
        nodes = self.attack_path_repository.list(session_id=session.id, limit=None)
        commands = self.command_repository.list(session_id=session.id, limit=None)
        flags = self.flag_repository.list(session_id=session.id, limit=None)
        evidence_public_by_id = {item.id: _public(item) for item in evidence}
        scanner_commands = _task_commands(tasks)
        index = SourceIndex(
            public_ids={
                _public(project),
                _public(session),
                *[_public(item) for item in tasks],
                *[_public(item) for item in evidence],
                *[_public(item) for item in findings],
                *[_public(item) for item in nodes],
                *[_public(item) for item in commands],
                *[_public(item) for item in flags],
            },
            commands={command.command for command in commands} | {item[1] for item in scanner_commands},
        )
        lines = [
            "# Session Writeup Source Material",
            "",
            "## Project",
            f"- Project id: {_public(project)}",
            f"- Name: {project.name}",
            f"- Description: {project.description or 'TODO: not recorded'}",
            "",
            "## Session",
            f"- Session id: {_public(session)}",
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
                f"- {_public(node)}: {node.stage} / {node.status} / {node.title}"
                + (f" / next: {node.next_action}" if node.next_action else "")
                for node in nodes
            ] or ["- TODO: no attack path nodes recorded"]),
            "",
            "## Findings",
            *([
                f"- {_public(finding)}: {finding.title} ({finding.severity}, {finding.status})"
                + _evidence_ref_text(finding.evidence_refs, evidence_public_by_id)
                + (f" - {finding.description}" if finding.description else "")
                for finding in findings
            ] or ["- TODO: no findings recorded"]),
            "",
            "## Evidence",
            *([
                f"- {_public(item)}: {item.evidence_type} / {item.title}"
                + (f" - {item.summary}" if item.summary else "")
                + (f" / ref={item.content_ref}" if item.content_ref else "")
                for item in evidence
            ] or ["- TODO: no evidence recorded"]),
            "",
            "## Command Log",
            *([
                f"- {_public(command)}: `{command.command}` exit={command.exit_code if command.exit_code is not None else 'unknown'}"
                + (f" cwd={command.working_directory}" if command.working_directory else "")
                + (f" summary={command.output_summary}" if command.output_summary else "")
                for command in commands
            ] or ["- TODO: no command runs recorded"]),
            "",
            "## Scanner Task Commands",
            *([
                f"- {_public(task)}: `{command}` status={task.status.value}"
                for task, command in scanner_commands
            ] or ["- TODO: no scanner task commands recorded"]),
            "",
            "## Flags and Loot",
            *([
                f"- {_public(flag)}: {flag.flag_type} `{flag.value}`"
                + (f" evidence={evidence_public_by_id.get(flag.source_evidence_id, flag.source_evidence_id)}" if flag.source_evidence_id else "")
                for flag in flags
            ] or ["- TODO: no flags recorded"]),
            "",
            *_source_rules(),
        ]
        return "\n".join(lines), index


def validate_writeup(*, markdown: str, source_index: SourceIndex) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    missing_sections = [section for section in WRITEUP_SECTIONS if f"## {section}" not in markdown]
    if missing_sections:
        errors.append("Missing required sections: " + ", ".join(missing_sections))
    unknown_ids = sorted(set(PUBLIC_ID_PATTERN.findall(markdown)) - source_index.public_ids)
    if unknown_ids:
        errors.append("Unknown public ids referenced: " + ", ".join(unknown_ids))
    for command in _command_log_inline_code(markdown):
        if command not in source_index.commands:
            errors.append(f"Unrecorded command in Command Log: {command}")
    uncited_lines = _uncited_factual_lines(markdown)
    if uncited_lines:
        errors.append("Factual lines without public id references: " + "; ".join(uncited_lines[:5]))
    if "TODO" not in markdown:
        warnings.append("No TODO markers were present; verify unfinished work is explicitly tracked.")
    return ValidationResult(errors=errors, warnings=warnings)


def _task_lines(tasks: list[Any]) -> list[str]:
    if not tasks:
        return ["- TODO: no tasks recorded"]
    return [
        f"- {_public(task)}: {task.task_type} via {task.executor} status={task.status.value}"
        + (f" summary={task.result_json.get('summary')}" if task.result_json.get("summary") else "")
        + (f" error={task.error}" if task.error else "")
        for task in tasks
    ]


def _task_commands(tasks: list[Any]) -> list[tuple[Any, str]]:
    commands: list[tuple[Any, str]] = []
    for task in tasks:
        argv = task.result_json.get("argv")
        if isinstance(argv, list) and all(isinstance(item, str) for item in argv) and argv:
            commands.append((task, shlex.join(argv)))
    return commands


def _open_port_lines(tasks: list[Any]) -> list[str]:
    lines: list[str] = []
    for task in tasks:
        structured = task.result_json.get("structured") if isinstance(task.result_json.get("structured"), dict) else {}
        for port in structured.get("open_ports") or []:
            if isinstance(port, dict):
                lines.append(
                    f"- {_public(task)}: {port.get('port')}/{port.get('protocol', 'tcp')} "
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
                        lines.append(f"- {_public(task)}: {target} {item}")
    return lines or ["- TODO: no web enumeration recorded"]


def _source_rules() -> list[str]:
    return [
        "",
        "## Rules",
        "- Do not invent commands, vulnerabilities, findings, flags, or exploitation steps.",
        "- Use TODO when a section has no recorded support.",
        "- Preserve public ids for evidence, findings, commands, tasks, and flags.",
        "- Every factual step should cite the relevant public id.",
    ]


def _material_system_prompt(scope_label: str) -> str:
    return (
        f"You are the primary red-code CTF Agent. Summarize the supplied structured {scope_label} records "
        "into Markdown source material for a writeup writer. Do not invent facts. Keep all public ids."
    )


def _writer_system_prompt(scope_label: str) -> str:
    sections = ", ".join(WRITEUP_SECTIONS)
    return (
        f"You are a report-writing assistant. Generate a concise Markdown CTF {scope_label} writeup from the supplied "
        f"source material. Include these sections exactly: {sections}. Do not invent missing steps; write TODO instead. "
        "Every factual bullet or paragraph in Recon, Open Ports, Web Enumeration, vulnerability, verification, exploit, "
        "privilege escalation, flags, command, and evidence sections must cite at least one public id. Every command in "
        "the Command Log must come from a CMD or TASK public id in the source material."
    )


def _append_validation_notes(markdown: str, validation: ValidationResult) -> str:
    if not validation.warnings:
        return markdown
    lines = [markdown.rstrip(), "", "## Validation Notes"]
    lines.extend(f"- {warning}" for warning in validation.warnings)
    return "\n".join(lines)


def _command_log_inline_code(markdown: str) -> list[str]:
    section = _section_body(markdown, "Command Log")
    commands: list[str] = []
    for line in section.splitlines():
        if "TODO" in line:
            continue
        commands.extend(INLINE_CODE_PATTERN.findall(line))
    return commands


def _uncited_factual_lines(markdown: str) -> list[str]:
    uncited: list[str] = []
    for section in FACTUAL_SECTIONS:
        body = _section_body(markdown, section)
        for line in body.splitlines():
            stripped = line.strip()
            if not _requires_public_id(stripped):
                continue
            if not PUBLIC_ID_PATTERN.search(stripped):
                uncited.append(f"{section}: {stripped[:120]}")
    return uncited


def _requires_public_id(line: str) -> bool:
    if not line or line.startswith("#") or "TODO" in line:
        return False
    normalized = line.lstrip("-*0123456789. )").strip()
    if not normalized:
        return False
    if normalized.startswith("|") or set(normalized) <= {"-", "|", " "}:
        return False
    return True


def _section_body(markdown: str, section: str) -> str:
    marker = f"## {section}"
    start = markdown.find(marker)
    if start == -1:
        return ""
    body_start = start + len(marker)
    next_section = markdown.find("\n## ", body_start)
    return markdown[body_start:] if next_section == -1 else markdown[body_start:next_section]


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


def _public(item: Any) -> str:
    return str(getattr(item, "public_id", "") or getattr(item, "id"))


def _evidence_ref_text(refs: Iterable[str], evidence_public_by_id: dict[str, str]) -> str:
    public_refs = [evidence_public_by_id.get(ref, ref) for ref in refs]
    return f" evidence={', '.join(public_refs)}" if public_refs else ""
