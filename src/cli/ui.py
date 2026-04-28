from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from io import StringIO
import json
import os
from typing import Callable

from rich import box
from rich.console import Console, Group, RenderableType
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from app.dashboard_service import SessionDashboard
from models.artifact import Artifact
from models.checkpoint import CheckpointSummary
from models.capability import LoadedCapability
from models.evidence import Evidence
from models.finding import Finding
from models.job import Job
from models.planner import (
    OperationContextSummary,
    PlannerMemoryWritebackStatus,
    PlannerMemoryWritebackSummary,
    PlannerPlan,
    PlannerProposal,
    PlannerProposalKind,
)
from models.report import Report
from models.run import Run, SessionLogEntry
from models.skill import LoadedSkill
from runtime.execution_events import ExecutionEventType, ExecutionProgressEvent


SinkFn = Callable[[str], None]
NONE_LABEL = "none"
ASCII_BOX = box.ASCII
HELP_TOPIC_PURPOSES: tuple[tuple[str, str], ...] = (
    ("query", "Session-first record lookup and report commands"),
    ("finding", "Session-owned findings and artifact links"),
    ("artifact", "Inspect raw session artifacts"),
    ("report", "Inspect persisted session reports"),
    ("dashboard", "Session runtime summary"),
    ("planner", "Planner plan creation and application"),
    ("skill", "Skill activation, inspection, reload, and shorthand usage"),
    ("module", "Redteam module listing, inspection, and one-shot or session-bound runs"),
)


@dataclass(slots=True)
class _PresenterSinks:
    text: SinkFn | None = None
    info: SinkFn | None = None
    error: SinkFn | None = None
    success: SinkFn | None = None
    header: SinkFn | None = None
    final_answer: SinkFn | None = None


class CliPresenter:
    def __init__(self, console: Console | None = None, sinks: _PresenterSinks | None = None) -> None:
        self.console = console or Console(soft_wrap=True)
        self.sinks = sinks or _PresenterSinks()

    @classmethod
    def for_callbacks(
        cls,
        *,
        text_output: SinkFn | None = None,
        info_output: SinkFn | None = None,
        error_output: SinkFn | None = None,
        success_output: SinkFn | None = None,
        header_output: SinkFn | None = None,
        final_answer_output: SinkFn | None = None,
    ) -> "CliPresenter":
        # Use a deterministic plain-text console when the presenter is wired into
        # tests or callback hooks so output does not depend on terminal features.
        return cls(
            console=Console(width=120, soft_wrap=True, color_system=None, force_terminal=False),
            sinks=_PresenterSinks(
                text=text_output,
                info=info_output,
                error=error_output,
                success=success_output,
                header=header_output,
                final_answer=final_answer_output,
            ),
        )

    @classmethod
    def supported_help_topics(cls) -> tuple[str, ...]:
        return tuple(name for name, _purpose in HELP_TOPIC_PURPOSES)

    @classmethod
    def is_supported_help_topic(cls, topic: str) -> bool:
        return topic in cls.supported_help_topics()

    @classmethod
    def supported_help_topics_text(cls) -> str:
        return ", ".join(cls.supported_help_topics())

    @classmethod
    def help_usage(cls) -> str:
        return f"/help [{ '|'.join(cls.supported_help_topics()) }]"

    def _render_text(self, renderable: RenderableType) -> str:
        buffer = StringIO()
        console = Console(
            width=self.console.width,
            record=True,
            soft_wrap=True,
            color_system=None,
            force_terminal=False,
            file=buffer,
        )
        # Render through Rich even for callback sinks so every output path shares
        # the same table wrapping and panel layout rules.
        console.print(renderable)
        return console.export_text().rstrip()

    def _emit(self, renderable: RenderableType, *, kind: str = "text") -> None:
        sink = getattr(self.sinks, kind)
        if sink is None and kind != "text":
            sink = self.sinks.text
        if sink is not None:
            sink(self._render_text(renderable))
            return
        self.console.print(renderable)

    def _detail_table(self, rows: list[tuple[str, str]]) -> Table:
        table = Table.grid(padding=(0, 1), expand=True)
        table.add_column(style="bold cyan", ratio=2, overflow="fold")
        table.add_column(style="white", ratio=3, overflow="fold")
        for label, value in rows:
            normalized_label = label if label.endswith(":") else f"{label}:"
            table.add_row(normalized_label, value)
        return table

    def _command_panel(
        self,
        title: str,
        rows: list[tuple[str, str]],
        *,
        border_style: str,
    ) -> Panel:
        content = Text()
        for index, (command, description) in enumerate(rows):
            if index:
                content.append("\n")
            content.append(command, style="bold cyan")
            content.append("\n")
            content.append(f"  {description}", style="white")
        return Panel(content, title=title, border_style=border_style, box=ASCII_BOX)

    def _status_text(self, status: str) -> Text:
        style_map = {
            "draft": "bright_black",
            "pending": "yellow",
            "queued": "yellow",
            "ready": "blue",
            "running": "green",
            "succeeded": "bold green",
            "paused": "cyan",
            "blocked": "bold yellow",
            "failed": "bold red",
            "timed_out": "bold red",
            "completed": "bold green",
            "cancelled": "magenta",
            "open": "yellow",
            "confirmed": "bold green",
            "dismissed": "bright_black",
            "duplicate": "magenta",
            "fixed": "cyan",
        }
        return Text(status, style=style_map.get(status.lower(), "white"))

    def _level_text(self, level: str) -> Text:
        return Text(level, style="bold red" if level == "error" else "blue")

    def _format_timestamp_compact(self, raw: str) -> str:
        try:
            parsed = datetime.fromisoformat(raw)
            return parsed.strftime("%Y-%m-%d %H:%M")
        except ValueError:
            return raw

    def _format_duration_ms(self, duration_ms: int | None) -> str:
        if duration_ms is None:
            return "-"
        if duration_ms < 1000:
            return f"{duration_ms}ms"
        return f"{duration_ms / 1000:.2f}s"

    def _format_size_bytes(self, size_bytes: int) -> str:
        if size_bytes < 1024:
            return f"{size_bytes}B"
        if size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f}KB"
        return f"{size_bytes / (1024 * 1024):.1f}MB"

    def _format_tool_argument_value(self, value: object) -> str:
        try:
            return json.dumps(value, ensure_ascii=False)
        except TypeError:
            return str(value)

    def _render_skill_name(self, skill_name: str | None) -> str:
        return skill_name or NONE_LABEL

    def _summarize_log_payload(self, payload: dict | None) -> str:
        if not payload:
            return "-"
        preferred_keys = [
            "tool_name",
            "capability",
            "failure_kind",
            "skill_name",
            "args_summary",
            "result_summary",
            "error",
            "reason",
        ]
        parts: list[str] = []
        for key in preferred_keys:
            value = payload.get(key)
            if value in (None, "", []):
                continue
            text = str(value)
            if len(text) > 60:
                text = text[:57] + "..."
            parts.append(f"{key}={text}")
        return " | ".join(parts) if parts else "-"

    def _truncate_observation(self, text: str, *, truncate_lines: int, truncate_chars: int) -> str:
        limited = text
        was_truncated = False
        if len(limited) > truncate_chars:
            limited = limited[:truncate_chars].rstrip()
            was_truncated = True
        lines = limited.splitlines()
        if len(lines) > truncate_lines:
            limited = "\n".join(lines[:truncate_lines]).rstrip()
            was_truncated = True
        if was_truncated:
            limited += "\n\n[truncated for display]"
        return limited

    def _help_overview(self) -> Group:
        examples = Table(box=ASCII_BOX, expand=True, header_style="bold")
        examples.add_column("Example", style="bold green", no_wrap=True)
        examples.add_column("What Happens", style="white")
        examples.add_row("Summarize this repository structure", "Starts or reuses a normal session and runs the normal prompt flow.")
        examples.add_row("/redteam on", "Switches the next plain-language requests into redteam session mode.")
        examples.add_row("Scan example.com for open services", "Runs in the currently selected mode and reuses that mode's active session when possible.")
        examples.add_row("What did you already do?", "Looks up the current or requested session context.")

        topics = Table(box=ASCII_BOX, expand=True, header_style="bold")
        topics.add_column("Topic", style="bold cyan", no_wrap=True)
        topics.add_column("Purpose", style="white")
        for topic, purpose in HELP_TOPIC_PURPOSES:
            topics.add_row(topic, purpose)
        return Group(
            Text(
                "Describe what you want in plain language first. "
                "Slash commands are available for advanced and debug workflows.",
                style="dim",
            ),
            Rule(style="grey50", characters="-"),
            Panel(examples, title="Natural-Language First", border_style="green", box=ASCII_BOX),
            Panel(topics, title="Advanced Help Topics", border_style="bright_blue", box=ASCII_BOX),
            Text(
                "Use /help <topic> for command details. The table above lists all supported topics.",
                style="dim",
            ),
            Text("Session shortcuts: /redteam [on|off|toggle|current], /clear, /reset, /exit, /quit", style="dim"),
        )

    def _help_topic_page(
        self,
        *,
        heading: str,
        summary: str,
        panels: list[RenderableType],
        footer: str | None = None,
    ) -> Group:
        renderables: list[RenderableType] = [
            Text(f"{heading} help", style="dim"),
            Rule(style="grey50", characters="-"),
            Text(summary, style="dim"),
        ]
        renderables.extend(panels)
        if footer:
            renderables.append(Text(footer, style="dim"))
        return Group(*renderables)

    def _help_query(self) -> Group:
        return self._help_topic_page(
            heading="Query",
            summary=(
                "Inspect session-scoped history, execution steps, findings, artifacts, and reports. "
                "When scope is omitted, commands default to the active session."
            ),
            panels=[
                self._command_panel("Query Commands", [
                    ("/status [scope]", "Show the current session-focused history/status summary"),
                    ("/history [scope]", "Look up session history with current-session default scope"),
                    ("/steps [scope]", "Look up execution step history for a session"),
                    ("/artifacts [scope]", "Look up session artifacts"),
                    ("/findings [scope]", "Look up session findings"),
                    ("/reports [scope]", "Look up persisted session reports"),
                    ("/show <public_id> [scope]", "Resolve one session/artifact/finding/report public id in session scope"),
                    ("/why <finding_public_id> [scope]", "Explain a finding through the Phase 7 trace flow"),
                    (
                        "/report <session_summary|findings_summary|operator_report> [scope]",
                        "Request a session-scoped report flow",
                    ),
                ], border_style="bright_blue"),
            ],
            footer="Scope may be current, latest, or a session id like S0001. No scope means the active session.",
        )

    def _help_finding(self) -> Group:
        return self._help_topic_page(
            heading="Finding",
            summary=(
                "Inspect and update session findings, including linked artifact relationships and analyst review state."
            ),
            panels=[
                self._command_panel("Finding Commands", [
                    ("/finding list <session_id> [limit]", "List findings for a session"),
                    ("/finding show <finding_id>", "Show finding details and linked artifacts"),
                    ("/finding confirm <finding_id>", "Mark a finding as confirmed"),
                    ("/finding dismiss <finding_id>", "Dismiss a finding with an optional reason"),
                ], border_style="bright_blue"),
            ],
        )

    def _help_artifact(self) -> Group:
        return self._help_topic_page(
            heading="Artifact",
            summary="Inspect raw session artifacts and trace how they connect back to findings.",
            panels=[
                self._command_panel("Artifact Commands", [
                    ("/artifact list <session_id> [limit]", "List artifacts for a session"),
                    ("/artifact show <artifact_id>", "Show artifact details and linked findings"),
                ], border_style="bright_blue"),
            ],
        )

    def _help_report(self) -> Group:
        return self._help_topic_page(
            heading="Report",
            summary="Inspect persisted reports that summarize session outcomes, findings, and supporting evidence.",
            panels=[
                self._command_panel("Report Commands", [
                    ("/report list <session_id> [limit]", "List reports for a session"),
                    ("/report show <report_id>", "Show report details and linked artifacts/findings"),
                ], border_style="bright_blue"),
            ],
        )

    def _help_dashboard(self) -> Group:
        return self._help_topic_page(
            heading="Dashboard",
            summary="View a concise runtime summary for the most recent redteam session or one specific session.",
            panels=[
                self._command_panel("Dashboard Commands", [
                    ("/dashboard", "Show the most recently active redteam session dashboard"),
                    ("/dashboard <session_id>", "Show the dashboard for one session"),
                ], border_style="bright_blue"),
            ],
        )

    def _help_planner(self) -> Group:
        return self._help_topic_page(
            heading="Planner",
            summary="Create persisted planner plans and selectively apply generated proposals into executable jobs.",
            panels=[
                self._command_panel("Planner Commands", [
                    ("/planner plan <session_id>", "Create and preview a persisted planner plan"),
                    ("/planner apply <plan_id> [1,3,...]", "Create jobs from all or selected planner proposals"),
                ], border_style="bright_blue"),
            ],
        )

    def _help_skill(self) -> Group:
        return self._help_topic_page(
            heading="Skill",
            summary=(
                "Inspect and manage shell-scoped skills, or run a one-off skill prompt without changing the active shell."
            ),
            panels=[
                self._command_panel("Skill Commands", [
                    ("/skill list", "List built-in and local skills"),
                    ("/skill show <name>", "Show skill details"),
                    ("/skill use <name>", "Activate a skill for this shell"),
                    ("/skill reload", "Reload skills from disk"),
                    ("/skill clear", "Clear the active shell skill"),
                    ("/skill current", "Show the active shell skill"),
                ], border_style="bright_blue"),
                self._command_panel("Shorthand Invocation", [
                    ("/skill-name <prompt>", "Run one prompt with a skill without activating it"),
                ], border_style="bright_blue"),
            ],
            footer="Skills affect the current shell only. Use the shorthand form for one-shot execution.",
        )

    def _help_module(self) -> Group:
        return self._help_topic_page(
            heading="Module",
            summary=(
                "Modules use the Phase 5 capability manifest and execute through the shared session risk and scope gate."
            ),
            panels=[
                self._command_panel(
                    "Module Commands",
                    [
                        ("/module list", "List redteam modules from capability.json manifests"),
                        ("/module show <name>", "Show module manifest details"),
                        (
                            "/module run <name> <target> [json_overrides]",
                            "Run a module one-shot, or inside the active redteam session",
                        ),
                    ],
                    border_style="bright_blue",
                ),
            ],
        )

    def show_help(self, topic: str | None = None) -> None:
        if topic is None:
            body = self._help_overview()
            title = "red-code"
        else:
            topic_builders: dict[str, Callable[[], Group]] = {
                "query": self._help_query,
                "finding": self._help_finding,
                "artifact": self._help_artifact,
                "report": self._help_report,
                "dashboard": self._help_dashboard,
                "planner": self._help_planner,
                "skill": self._help_skill,
                "module": self._help_module,
            }
            builder = topic_builders.get(topic)
            if builder is None:
                raise ValueError(f"Unsupported help topic: {topic}")
            body = builder()
            title = f"Help: {topic}"
        self._emit(Panel(body, title=title, border_style="bright_blue", box=ASCII_BOX))

    def clear_screen(self) -> None:
        if any(
            value is not None
            for value in (
                self.sinks.text,
                self.sinks.info,
                self.sinks.error,
                self.sinks.success,
                self.sinks.header,
                self.sinks.final_answer,
            )
        ):
            # Callback presenters usually feed tests or logs, where clearing the
            # screen would erase useful output instead of helping the operator.
            return
        file = self.console.file
        is_tty = callable(getattr(file, "isatty", None)) and bool(file.isatty())
        if os.name == "nt" and is_tty:
            # `cls` remains the most reliable option for classic Windows terminals.
            if os.system("cls") == 0:
                return
        self.console.clear(home=True)

    def show_operation_context_summary(self, summary: OperationContextSummary) -> None:
        self._emit(
            Panel(
                self._detail_table([
                    ("Session", summary.operation_id),
                    ("Summary", summary.summary),
                    ("Scope", summary.scope_summary),
                    ("Findings", summary.findings_summary),
                    ("Artifacts", summary.evidence_summary),
                    ("Memory", summary.memory_summary),
                    ("Suggested Next Step", summary.next_step_hint),
                ]),
                title="Session Context Summary",
                border_style="bright_blue",
                box=ASCII_BOX,
            )
        )

    def show_job_list(self, jobs: list[Job], *, operation_label: str | None = None) -> None:
        if not jobs:
            self._emit(Panel(Text("No jobs found.", style="dim"), title="Jobs", border_style="yellow", box=ASCII_BOX))
            return
        title = f"Jobs for {operation_label}" if operation_label else "Jobs"
        table = Table(title=title, box=ASCII_BOX, expand=True, header_style="bold")
        table.add_column("Job", style="cyan", no_wrap=True)
        table.add_column("Status", no_wrap=True)
        table.add_column("Type", no_wrap=True)
        table.add_column("Target", overflow="fold")
        table.add_column("Updated", style="dim", no_wrap=True)
        for job in jobs:
            table.add_row(
                job.public_id,
                self._status_text(job.status.value),
                job.job_type,
                job.target_ref,
                self._format_timestamp_compact(job.updated_at),
            )
        self._emit(table)

    def show_job_detail(self, job: Job) -> None:
        self._emit(
            Panel(
                self._detail_table([
                    ("Job ID", job.public_id),
                    ("Internal ID", job.id),
                    ("Session ID", job.operation_id),
                    ("Type", job.job_type),
                    ("Target", job.target_ref),
                    ("Status", job.status.value),
                    ("Arguments", str(job.arguments or {})),
                    ("Dependencies", ", ".join(job.dependency_job_ids) or "-"),
                    ("Timeout Seconds", str(job.timeout_seconds) if job.timeout_seconds is not None else "-"),
                    ("Retry Limit", str(job.retry_limit)),
                    ("Retry Count", str(job.retry_count)),
                    ("Queued At", job.queued_at or "-"),
                    ("Started At", job.started_at or "-"),
                    ("Finished At", job.finished_at or "-"),
                    ("Created At", job.created_at),
                    ("Updated At", job.updated_at),
                    ("Lease Owner", job.lease_owner or "-"),
                    ("Lease Expires At", job.lease_expires_at or "-"),
                    ("Last Heartbeat At", job.last_heartbeat_at or "-"),
                    ("Cancel Requested At", job.cancel_requested_at or "-"),
                    ("Cancel Reason", job.cancel_reason or "-"),
                    ("Last Error", job.last_error or "-"),
                ]),
                title="Job",
                border_style="magenta",
                box=ASCII_BOX,
            )
        )

    def show_finding_list(self, findings: list[Finding], *, operation_label: str | None = None) -> None:
        if not findings:
            self._emit(
                Panel(Text("No findings found.", style="dim"), title="Findings", border_style="yellow", box=ASCII_BOX)
            )
            return
        title = f"Findings for {operation_label}" if operation_label else "Findings"
        table = Table(title=title, box=ASCII_BOX, expand=True, header_style="bold")
        table.add_column("Finding", style="cyan", no_wrap=True)
        table.add_column("Status", no_wrap=True)
        table.add_column("Severity", no_wrap=True)
        table.add_column("Confidence", no_wrap=True)
        table.add_column("Target", overflow="fold")
        table.add_column("Title", overflow="fold")
        for finding in findings:
            table.add_row(
                finding.public_id,
                self._status_text(finding.status.value),
                finding.severity,
                finding.confidence,
                finding.target_ref,
                finding.title,
            )
        self._emit(table)

    def show_finding_detail(self, finding: Finding, *, linked_evidence_ids: list[str]) -> None:
        self._emit(
            Panel(
                self._detail_table([
                    ("Finding ID", finding.public_id),
                    ("Internal ID", finding.id),
                    ("Session ID", finding.operation_id),
                    ("Source Job ID", finding.source_job_id or "-"),
                    ("Type", finding.finding_type),
                    ("Title", finding.title),
                    ("Target", finding.target_ref),
                    ("Severity", finding.severity),
                    ("Confidence", finding.confidence),
                    ("Status", finding.status.value),
                    ("Summary", finding.summary or "-"),
                    ("Impact", finding.impact or "-"),
                    ("Reproduction Notes", finding.reproduction_notes or "-"),
                    ("Next Action", finding.next_action or "-"),
                    ("Linked Artifact IDs", ", ".join(linked_evidence_ids) or "-"),
                    ("Created At", finding.created_at),
                    ("Updated At", finding.updated_at),
                ]),
                title="Finding",
                border_style="yellow",
                box=ASCII_BOX,
            )
        )

    def show_evidence_list(self, evidence_items: list[Evidence], *, operation_label: str | None = None) -> None:
        artifacts = [
            Artifact(
                id=evidence.id,
                public_id=evidence.public_id,
                session_id=evidence.operation_id,
                source_job_id=evidence.job_id,
                artifact_type=evidence.evidence_type,
                target_ref=evidence.target_ref,
                title=evidence.title,
                summary=evidence.summary,
                artifact_path=evidence.artifact_path,
                content_type=evidence.content_type,
                hash_digest=evidence.hash_digest,
                captured_at=evidence.captured_at,
                metadata={},
            )
            for evidence in evidence_items
        ]
        self.show_artifact_list(artifacts, session_label=operation_label)

    def show_evidence_detail(self, evidence: Evidence, *, linked_finding_ids: list[str]) -> None:
        artifact = Artifact(
            id=evidence.id,
            public_id=evidence.public_id,
            session_id=evidence.operation_id,
            source_job_id=evidence.job_id,
            artifact_type=evidence.evidence_type,
            target_ref=evidence.target_ref,
            title=evidence.title,
            summary=evidence.summary,
            artifact_path=evidence.artifact_path,
            content_type=evidence.content_type,
            hash_digest=evidence.hash_digest,
            captured_at=evidence.captured_at,
            metadata={},
        )
        self.show_artifact_detail(artifact, linked_finding_ids=linked_finding_ids)

    def show_artifact_list(self, artifacts: list[Artifact], *, session_label: str | None = None) -> None:
        if not artifacts:
            self._emit(
                Panel(Text("No artifacts found.", style="dim"), title="Artifacts", border_style="yellow", box=ASCII_BOX)
            )
            return
        title = f"Artifacts for {session_label}" if session_label else "Artifacts"
        table = Table(title=title, box=ASCII_BOX, expand=True, header_style="bold")
        table.add_column("Artifact", style="cyan", no_wrap=True)
        table.add_column("Type", no_wrap=True)
        table.add_column("Target", overflow="fold")
        table.add_column("Captured", style="dim", no_wrap=True)
        table.add_column("Title", overflow="fold")
        for artifact in artifacts:
            table.add_row(
                artifact.public_id,
                artifact.artifact_type,
                artifact.target_ref,
                self._format_timestamp_compact(artifact.captured_at),
                artifact.title,
            )
        self._emit(table)

    def show_artifact_detail(self, artifact: Artifact, *, linked_finding_ids: list[str]) -> None:
        self._emit(
            Panel(
                self._detail_table([
                    ("Artifact ID", artifact.public_id),
                    ("Internal ID", artifact.id),
                    ("Session ID", artifact.operation_id),
                    ("Job ID", artifact.job_id or "-"),
                    ("Type", artifact.artifact_type),
                    ("Target", artifact.target_ref),
                    ("Title", artifact.title),
                    ("Summary", artifact.summary),
                    ("Artifact Path", artifact.artifact_path or "-"),
                    ("Content Type", artifact.content_type or "-"),
                    ("Hash Digest", artifact.hash_digest or "-"),
                    ("Linked Finding IDs", ", ".join(linked_finding_ids) or "-"),
                    ("Captured At", artifact.captured_at),
                ]),
                title="Artifact",
                border_style="green",
                box=ASCII_BOX,
            )
        )

    def show_report_list(self, reports: list[Report], *, session_label: str | None = None) -> None:
        if not reports:
            self._emit(
                Panel(Text("No reports found.", style="dim"), title="Reports", border_style="yellow", box=ASCII_BOX)
            )
            return
        title = f"Reports for {session_label}" if session_label else "Reports"
        table = Table(title=title, box=ASCII_BOX, expand=True, header_style="bold")
        table.add_column("Report", style="cyan", no_wrap=True)
        table.add_column("Type", no_wrap=True)
        table.add_column("Created", style="dim", no_wrap=True)
        table.add_column("Title", overflow="fold")
        for report in reports:
            table.add_row(
                report.public_id,
                report.report_type,
                self._format_timestamp_compact(report.created_at),
                report.title,
            )
        self._emit(table)

    def show_report_detail(
        self,
        report: Report,
        *,
        linked_artifact_ids: list[str],
        linked_finding_ids: list[str],
    ) -> None:
        self._emit(
            Panel(
                self._detail_table([
                    ("Report ID", report.public_id),
                    ("Internal ID", report.id),
                    ("Session ID", report.session_id),
                    ("Type", report.report_type),
                    ("Title", report.title),
                    ("Summary", report.summary),
                    ("Output Path", report.artifact_path or "-"),
                    ("Linked Artifact IDs", ", ".join(linked_artifact_ids) or "-"),
                    ("Linked Finding IDs", ", ".join(linked_finding_ids) or "-"),
                    ("Created At", report.created_at),
                ]),
                title="Report",
                border_style="bright_blue",
                box=ASCII_BOX,
            )
        )

    def show_dashboard(self, dashboard: SessionDashboard) -> None:
        summary = Panel(
            self._detail_table([
                ("Session ID", dashboard.session.public_id),
                ("Title", dashboard.session.title),
                ("Goal", dashboard.session.goal),
                ("Mode", dashboard.session.mode.value),
                ("Status", dashboard.session.status.value),
                ("Workspace", dashboard.session.workspace),
                ("Target Summary", dashboard.session.target_summary or "-"),
                ("Allowed Hosts", ", ".join(dashboard.policy.allowed_hosts) or "-"),
                ("Allowed Domains", ", ".join(dashboard.policy.allowed_domains) or "-"),
                ("Allowed Ports", ", ".join(str(port) for port in dashboard.policy.allowed_ports) or "-"),
                ("Allowed Protocols", ", ".join(dashboard.policy.allowed_protocols) or "-"),
                ("Artifact Total", str(dashboard.artifact_count)),
                ("Report Total", str(dashboard.report_count)),
                ("Admission Denied Events", str(dashboard.event_counts.get("admission_denied", 0))),
                ("Confirmation Denied Events", str(dashboard.event_counts.get("confirmation_denied", 0))),
                ("Execution Failed Events", str(dashboard.event_counts.get("execution_failed", 0))),
            ]),
            title="Dashboard Summary",
            border_style="bright_blue",
            box=ASCII_BOX,
        )

        job_counts = Table(title="Job Status Counts", box=ASCII_BOX, expand=True, header_style="bold")
        job_counts.add_column("Status", style="cyan", no_wrap=True)
        job_counts.add_column("Count", justify="right", no_wrap=True)
        for status, count in sorted(dashboard.job_counts.items()):
            job_counts.add_row(self._status_text(status), str(count))

        finding_counts = Table(title="Finding Status Counts", box=ASCII_BOX, expand=True, header_style="bold")
        finding_counts.add_column("Status", style="cyan", no_wrap=True)
        finding_counts.add_column("Count", justify="right", no_wrap=True)
        for status, count in sorted(dashboard.finding_counts.items()):
            finding_counts.add_row(self._status_text(status), str(count))

        flagged_jobs: RenderableType
        if dashboard.flagged_jobs:
            flagged_jobs = Table(title="Recent Failed / Timed-Out / Blocked Jobs", box=ASCII_BOX, expand=True, header_style="bold")
            flagged_jobs.add_column("Job", style="cyan", no_wrap=True)
            flagged_jobs.add_column("Status", no_wrap=True)
            flagged_jobs.add_column("Type", no_wrap=True)
            flagged_jobs.add_column("Target", overflow="fold")
            flagged_jobs.add_column("Last Error", overflow="fold")
            for job in dashboard.flagged_jobs:
                flagged_jobs.add_row(
                    job.public_id,
                    self._status_text(job.status.value),
                    job.job_type,
                    job.target_ref,
                    job.last_error or "-",
                )
        else:
            flagged_jobs = Panel(
                Text("No failed, timed-out, or blocked jobs.", style="dim"),
                title="Recent Failed / Timed-Out / Blocked Jobs",
                border_style="green",
                box=ASCII_BOX,
            )

        recent_findings: RenderableType
        if dashboard.recent_findings:
            recent_findings = Table(title="Recent Findings", box=ASCII_BOX, expand=True, header_style="bold")
            recent_findings.add_column("Finding", style="cyan", no_wrap=True)
            recent_findings.add_column("Status", no_wrap=True)
            recent_findings.add_column("Severity", no_wrap=True)
            recent_findings.add_column("Target", overflow="fold")
            recent_findings.add_column("Title", overflow="fold")
            for finding in dashboard.recent_findings:
                recent_findings.add_row(
                    finding.public_id,
                    self._status_text(finding.status.value),
                    finding.severity,
                    finding.target_ref,
                    finding.title,
                )
        else:
            recent_findings = Panel(
                Text("No findings found.", style="dim"),
                title="Recent Findings",
                border_style="yellow",
                box=ASCII_BOX,
            )

        recent_artifacts: RenderableType
        if dashboard.recent_artifacts:
            recent_artifacts = Table(title=f"Recent Artifacts ({dashboard.artifact_count} total)", box=ASCII_BOX, expand=True, header_style="bold")
            recent_artifacts.add_column("Artifact", style="cyan", no_wrap=True)
            recent_artifacts.add_column("Type", no_wrap=True)
            recent_artifacts.add_column("Target", overflow="fold")
            recent_artifacts.add_column("Captured", style="dim", no_wrap=True)
            for artifact in dashboard.recent_artifacts:
                recent_artifacts.add_row(
                    artifact.public_id,
                    artifact.artifact_type,
                    artifact.target_ref,
                    self._format_timestamp_compact(artifact.captured_at),
                )
        else:
            recent_artifacts = Panel(
                Text("No artifacts found.", style="dim"),
                title=f"Recent Artifacts ({dashboard.artifact_count} total)",
                border_style="yellow",
                box=ASCII_BOX,
            )

        recent_events: RenderableType
        if dashboard.recent_events:
            recent_events = Table(title="Recent Session Events", box=ASCII_BOX, expand=True, header_style="bold")
            recent_events.add_column("Created", style="dim", no_wrap=True)
            recent_events.add_column("Event", no_wrap=True)
            recent_events.add_column("Target", overflow="fold")
            recent_events.add_column("Message", overflow="fold")
            for event in dashboard.recent_events:
                event_label = event.event_type.value
                if event.event_type.value in dashboard.event_counts and dashboard.event_counts[event.event_type.value] > 0:
                    event_label = f"{event_label} ({dashboard.event_counts[event.event_type.value]})"
                recent_events.add_row(
                    self._format_timestamp_compact(event.created_at),
                    event_label,
                    event.target_ref,
                    event.message,
                )
        else:
            recent_events = Panel(
                Text("No session events found.", style="dim"),
                title="Recent Session Events",
                border_style="yellow",
                box=ASCII_BOX,
            )

        self._emit(Group(summary, job_counts, finding_counts, flagged_jobs, recent_findings, recent_artifacts, recent_events))

    def show_planner_plan(
        self,
        *,
        plan: PlannerPlan,
        operation_label: str,
        proposals: list[PlannerProposal],
        memory_writeback: PlannerMemoryWritebackSummary | None = None,
    ) -> None:
        memory_writeback_label = "-"
        if memory_writeback is not None:
            if memory_writeback.status == PlannerMemoryWritebackStatus.SUCCEEDED:
                memory_writeback_label = (
                    f"created {memory_writeback.created_count}, skipped {memory_writeback.skipped_count}"
                )
            else:
                memory_writeback_label = f"failed: {memory_writeback.error_message or 'unknown error'}"
        summary = Panel(
            self._detail_table([
                ("Plan ID", plan.public_id),
                ("Session", operation_label),
                ("Status", plan.status.value),
                ("Planning Mode", plan.planning_mode),
                ("Planner Source", plan.planner_source.value),
                ("Model", plan.model_name or "-"),
                ("Memory Write-back", memory_writeback_label),
                ("Summary", plan.summary),
                ("Rationale", plan.rationale),
            ]),
            title="Planner Plan",
            border_style="bright_blue",
            box=ASCII_BOX,
        )
        proposed = [proposal for proposal in proposals if proposal.proposal_kind == PlannerProposalKind.PROPOSED]
        blocked_or_skipped = [
            proposal
            for proposal in proposals
            if proposal.proposal_kind != PlannerProposalKind.PROPOSED
        ]

        if proposed:
            proposed_table: RenderableType = Table(
                title="Planner Proposals",
                box=ASCII_BOX,
                expand=True,
                header_style="bold",
            )
            proposed_table.add_column("#", style="cyan", no_wrap=True)
            proposed_table.add_column("Type", no_wrap=True)
            proposed_table.add_column("Target", overflow="fold")
            proposed_table.add_column("Summary", overflow="fold")
            proposed_table.add_column("Rationale", overflow="fold")
            for proposal in proposed:
                proposed_table.add_row(
                    str(proposal.proposal_index),
                    proposal.job_type,
                    proposal.target_ref,
                    proposal.summary or "-",
                    proposal.rationale or "-",
                )
        else:
            proposed_table = Panel(
                Text("No runnable planner proposals were produced.", style="dim"),
                title="Planner Proposals",
                border_style="yellow",
                box=ASCII_BOX,
            )

        if blocked_or_skipped:
            blocked_table: RenderableType = Table(
                title="Skipped / Blocked Proposals",
                box=ASCII_BOX,
                expand=True,
                header_style="bold",
            )
            blocked_table.add_column("Kind", style="cyan", no_wrap=True)
            blocked_table.add_column("Type", no_wrap=True)
            blocked_table.add_column("Target", overflow="fold")
            blocked_table.add_column("Reason", overflow="fold")
            for proposal in blocked_or_skipped:
                blocked_table.add_row(
                    proposal.proposal_kind.value,
                    proposal.job_type,
                    proposal.target_ref,
                    proposal.skip_reason or "-",
                )
        else:
            blocked_table = Panel(
                Text("No skipped or blocked planner proposals.", style="dim"),
                title="Skipped / Blocked Proposals",
                border_style="green",
                box=ASCII_BOX,
            )
        self._emit(Group(summary, proposed_table, blocked_table))

    def show_run_list(self, runs: list[Run], session_label: str | None = None) -> None:
        if not runs:
            self._emit(Panel(Text("No runs found.", style="dim"), title="Runs", border_style="yellow", box=ASCII_BOX))
            return
        title = f"Runs for {session_label}" if session_label is not None else "Runs"
        table = Table(title=title, box=ASCII_BOX, expand=True, header_style="bold")
        table.add_column("Run", style="cyan", no_wrap=True)
        table.add_column("Status", no_wrap=True)
        table.add_column("Started", style="dim", no_wrap=True)
        table.add_column("Duration", no_wrap=True)
        table.add_column("Skill", style="magenta")
        table.add_column("Failure", overflow="fold")
        for run in runs:
            table.add_row(
                run.public_id,
                self._status_text(run.status.value),
                self._format_timestamp_compact(run.started_at),
                self._format_duration_ms(run.duration_ms),
                self._render_skill_name(run.effective_skill_name),
                run.failure_kind or "-",
            )
        self._emit(table)

    def show_run_detail(self, run: Run, session_label: str, entries: list[SessionLogEntry]) -> None:
        summary = Panel(
            self._detail_table([
                ("Run ID", run.public_id),
                ("Internal ID", run.id),
                ("Session", session_label),
                ("Session Internal ID", run.session_id),
                ("Status", run.status.value),
                ("Started At", run.started_at),
                ("Finished At", run.finished_at or "-"),
                ("Duration", self._format_duration_ms(run.duration_ms)),
                ("Skill", self._render_skill_name(run.effective_skill_name)),
                ("Tools", ", ".join(run.effective_tools) if run.effective_tools else "-"),
                ("Step Count", str(run.step_count)),
                ("Failure Kind", run.failure_kind or "-"),
                ("Last Error", run.last_error or "-"),
                ("Usage", str(run.last_usage or {})),
            ]),
            title="Run Detail",
            border_style="magenta",
            box=ASCII_BOX,
        )
        self._emit(Group(summary, self._session_log_table(entries, {run.id: run.public_id}, title="Recent Run Logs")))

    def show_checkpoint_list(
        self,
        summaries: list[CheckpointSummary],
        session_label: str,
        run_labels: dict[str, str],
    ) -> None:
        if not summaries:
            self._emit(
                Panel(
                    Text(f"No checkpoints found for session {session_label}.", style="dim"),
                    title="Checkpoints",
                    border_style="yellow",
                    box=ASCII_BOX,
                )
            )
            return
        table = Table(title=f"Checkpoints for {session_label}", box=ASCII_BOX, expand=True, header_style="bold")
        table.add_column("Checkpoint", style="cyan")
        table.add_column("Created", style="dim", no_wrap=True)
        table.add_column("Storage", no_wrap=True)
        table.add_column("Size", no_wrap=True)
        table.add_column("Msgs", justify="right", no_wrap=True)
        table.add_column("Summary", no_wrap=True)
        table.add_column("Run", no_wrap=True)
        for summary in summaries:
            table.add_row(
                summary.id,
                self._format_timestamp_compact(summary.created_at),
                summary.storage_kind,
                self._format_size_bytes(summary.payload_size_bytes),
                str(summary.history_message_count),
                "yes" if summary.has_compressed_summary else "no",
                run_labels.get(summary.run_id or "", "-") if summary.run_id else "-",
            )
        self._emit(table)

    def show_checkpoint_detail(
        self,
        summary: CheckpointSummary,
        session_label: str,
        run_label: str | None = None,
    ) -> None:
        self._emit(
            Panel(
                self._detail_table([
                    ("Checkpoint ID", summary.id),
                    ("Session", session_label),
                    ("Session Internal ID", summary.session_id),
                    ("Run", run_label or "-"),
                    ("Run Internal ID", summary.run_id or "-"),
                    ("Created At", summary.created_at),
                    ("Storage", summary.storage_kind),
                    ("Payload Size", self._format_size_bytes(summary.payload_size_bytes)),
                    ("History Message Count", str(summary.history_message_count)),
                    ("History Text Bytes", str(summary.history_text_bytes)),
                    ("Compressed Summary", "yes" if summary.has_compressed_summary else "no"),
                ]),
                title="Checkpoint Detail",
                border_style="green",
                box=ASCII_BOX,
            )
        )

    def show_session_logs(self, entries: list[SessionLogEntry], run_labels: dict[str, str] | None = None) -> None:
        self._emit(self._session_log_table(entries, run_labels or {}, title="Session Logs"))

    def _session_log_table(self, entries: list[SessionLogEntry], run_labels: dict[str, str], *, title: str) -> RenderableType:
        if not entries:
            return Panel(Text("No session logs found.", style="dim"), title=title, border_style="yellow", box=ASCII_BOX)
        table = Table(title=title, box=ASCII_BOX, expand=True, header_style="bold")
        table.add_column("Created", style="dim", no_wrap=True)
        table.add_column("Level", no_wrap=True)
        table.add_column("Run", no_wrap=True)
        table.add_column("Event", no_wrap=True)
        table.add_column("Details", overflow="fold")
        for entry in entries:
            run_part = "-"
            if entry.run_id:
                run_part = run_labels.get(entry.run_id, entry.run_id[:8])
            table.add_row(
                self._format_timestamp_compact(entry.created_at),
                self._level_text(entry.level.value),
                run_part,
                entry.message,
                self._summarize_log_payload(entry.payload),
            )
        return table

    def show_skill_list(self, skills: list[LoadedSkill]) -> None:
        if not skills:
            self._emit(Panel(Text("No skills found.", style="dim"), title="Skills", border_style="yellow", box=ASCII_BOX))
            return
        table = Table(title="Skills", box=ASCII_BOX, expand=True, header_style="bold")
        table.add_column("Name", style="cyan", no_wrap=True)
        table.add_column("Source", no_wrap=True)
        table.add_column("Description", overflow="fold")
        for skill in skills:
            table.add_row(skill.manifest.name, skill.source, skill.manifest.description)
        self._emit(table)

    def show_skill_detail(self, skill: LoadedSkill) -> None:
        metadata = skill.manifest.metadata or {}
        metadata_text = "\n".join(
            f"{key}: {value}" for key, value in sorted(metadata.items())
        ) if metadata else "-"
        invocation_mode = "workflow-only" if skill.manifest.disable_model_invocation else "prompt"
        summary = Panel(
            self._detail_table([
                ("Name", skill.manifest.name),
                ("Description", skill.manifest.description),
                ("License", skill.manifest.license),
                ("Compatibility", skill.manifest.compatibility),
                ("Source", skill.source),
                ("Invocation Mode", invocation_mode),
                ("User Invocable", "yes" if skill.manifest.is_user_invocable else "no"),
                ("Direct Model Invocation", "yes" if skill.manifest.allows_model_invocation else "no"),
                ("Shell", skill.manifest.shell or "-"),
                ("Model", skill.manifest.model or "-"),
                ("Reasoning Effort", skill.manifest.effort or "-"),
                ("Workflow Profile", skill.manifest.workflow_profile or "-"),
                ("Argument Hint", skill.manifest.argument_hint or "-"),
                ("Allowed Tools", ", ".join(skill.manifest.allowed_tools)),
                ("Path", str(skill.skill_file)),
            ]),
            title="Skill Detail",
            border_style="green",
            box=ASCII_BOX,
        )
        metadata_panel = Panel(Text(metadata_text), title="Metadata", border_style="blue", box=ASCII_BOX)
        self._emit(Group(summary, metadata_panel))

    def show_capability_list(
        self,
        capabilities: list[LoadedCapability],
        *,
        title: str = "Capabilities",
    ) -> None:
        if not capabilities:
            self._emit(
                Panel(
                    Text("No capabilities found.", style="dim"),
                    title=title,
                    border_style="yellow",
                    box=ASCII_BOX,
                )
            )
            return
        table = Table(title=title, box=ASCII_BOX, expand=True, header_style="bold")
        table.add_column("Name", style="cyan", no_wrap=True)
        table.add_column("Kind", no_wrap=True)
        table.add_column("Source", no_wrap=True)
        table.add_column("Execution", no_wrap=True)
        table.add_column("Description", overflow="fold")
        for capability in capabilities:
            table.add_row(
                capability.manifest.name,
                capability.manifest.kind.value,
                capability.source,
                capability.manifest.execution.style.value,
                capability.manifest.description,
            )
        self._emit(table)

    def show_capability_detail(self, capability: LoadedCapability) -> None:
        manifest = capability.manifest
        parameters = "\n".join(
            (
                f"{parameter.name} "
                f"({parameter.type.value}, {'required' if parameter.required else 'optional'}): "
                f"{parameter.description}"
            )
            for parameter in manifest.parameters
        ) or "-"
        summary = Panel(
            self._detail_table([
                ("Name", manifest.name),
                ("Display Name", manifest.display_name),
                ("Kind", manifest.kind.value),
                ("Description", manifest.description),
                ("Source", capability.source),
                ("Modes", ", ".join(mode.value for mode in manifest.modes)),
                ("Execution Style", manifest.execution.style.value),
                ("Execution Profile", manifest.execution.profile),
                ("Allowed Tools", ", ".join(manifest.tools.allowed)),
                ("Risk Default", manifest.risk.default.value),
                ("Risk Actions", ", ".join(manifest.risk.actions) or "-"),
                ("One Shot", "yes" if manifest.session.supports_one_shot else "no"),
                ("Persistent", "yes" if manifest.session.supports_persistent else "no"),
                ("Result Layers", ", ".join(manifest.session.result_layers) or "-"),
                ("Path", str(capability.manifest_file)),
            ]),
            title="Capability Detail",
            border_style="green",
            box=ASCII_BOX,
        )
        self._emit(
            Group(
                summary,
                Panel(
                    Text(parameters),
                    title="Parameters",
                    border_style="blue",
                    box=ASCII_BOX,
                ),
            )
        )

    def show_skill_workflow_plan(
        self,
        *,
        skill_name: str,
        workflow_profile: str,
        session_label: str,
        primary_target: str,
        planned_rows: list[dict[str, str]],
        skipped_rows: list[dict[str, str]],
    ) -> None:
        summary = Panel(
            self._detail_table([
                ("Skill", skill_name),
                ("Workflow Profile", workflow_profile),
                ("Session", session_label),
                ("Primary Target", primary_target),
                ("Planned Jobs", str(len(planned_rows))),
                ("Skipped Jobs", str(len(skipped_rows))),
            ]),
            title="Skill Workflow Plan",
            border_style="green",
            box=ASCII_BOX,
        )
        planned_table = Table(title="Planned Jobs", box=ASCII_BOX, expand=True, header_style="bold")
        planned_table.add_column("Type", style="cyan", no_wrap=True)
        planned_table.add_column("Target", overflow="fold")
        planned_table.add_column("Arguments", overflow="fold")
        planned_table.add_column("Timeout", no_wrap=True)
        planned_table.add_column("Retry", no_wrap=True)
        planned_table.add_column("Notes", overflow="fold")
        for row in planned_rows:
            planned_table.add_row(
                row["type"],
                row["target"],
                row["arguments"],
                row["timeout"],
                row["retry"],
                row["notes"],
            )

        renderables: list[RenderableType] = [summary, planned_table]
        if skipped_rows:
            skipped_table = Table(title="Skipped Jobs", box=ASCII_BOX, expand=True, header_style="bold")
            skipped_table.add_column("Type", style="yellow", no_wrap=True)
            skipped_table.add_column("Target", overflow="fold")
            skipped_table.add_column("Reason", overflow="fold")
            skipped_table.add_column("Summary", overflow="fold")
            for row in skipped_rows:
                skipped_table.add_row(
                    row["type"],
                    row["target"],
                    row["reason"],
                    row["summary"],
                )
            renderables.append(skipped_table)
        self._emit(Group(*renderables))

    def show_execution_progress(self, event: ExecutionProgressEvent) -> None:
        if event.event_type == ExecutionEventType.CONFIRMATION_REQUIRED:
            details = [
                f"Session: {event.session_public_id}",
                f"Action: {event.action_name or event.step_label or '-'}",
                f"Risk: {event.risk_level or '-'}",
                f"Target: {event.target_summary or '-'}",
                f"Reason: {event.reason or event.message or '-'}",
            ]
            self._emit(
                Panel(
                    Text("\n".join(details)),
                    title="Confirmation Required",
                    border_style="yellow",
                    box=ASCII_BOX,
                ),
                kind="info",
            )
            return

        if event.event_type in {
            ExecutionEventType.CONFIRMATION_APPROVED,
            ExecutionEventType.CONFIRMATION_DENIED,
        }:
            approved = event.event_type == ExecutionEventType.CONFIRMATION_APPROVED
            self._emit(
                Panel(
                    Text(
                        "\n".join(
                            [
                                f"Session: {event.session_public_id}",
                                f"Action: {event.action_name or event.step_label or '-'}",
                                f"Risk: {event.risk_level or '-'}",
                                f"Decision: {'approved' if approved else 'denied'}",
                            ]
                        )
                    ),
                    title="Confirmation Decision",
                    border_style="green" if approved else "red",
                    box=ASCII_BOX,
                ),
                kind="success" if approved else "error",
            )
            return

        if event.event_type == ExecutionEventType.STEP_STARTED:
            label = event.step_label or "step"
            self._emit(
                Rule(
                    f" session {event.session_public_id} | {label} started ",
                    style="cyan",
                    characters="-",
                ),
                kind="info",
            )
            return

        if event.event_type == ExecutionEventType.STEP_COMPLETED:
            label = event.step_label or "step"
            message = event.message or "completed"
            self._emit(
                Panel(
                    Text(f"{label}: {message}"),
                    title=f"Step Completed ({event.session_public_id})",
                    border_style="green",
                    box=ASCII_BOX,
                ),
                kind="success",
            )
            return

        if event.event_type == ExecutionEventType.STEP_FAILED:
            label = event.step_label or "step"
            message = event.message or "failed"
            self._emit(
                Panel(
                    Text(f"{label}: {message}"),
                    title=f"Step Failed ({event.session_public_id})",
                    border_style="red",
                    box=ASCII_BOX,
                ),
                kind="error",
            )
            return

        title_style = {
            ExecutionEventType.EXECUTION_STARTED: ("Execution Started", "blue", "info"),
            ExecutionEventType.EXECUTION_PAUSED: ("Execution Paused", "yellow", "info"),
            ExecutionEventType.EXECUTION_COMPLETED: ("Execution Completed", "green", "success"),
            ExecutionEventType.EXECUTION_FAILED: ("Execution Failed", "red", "error"),
        }.get(event.event_type, ("Execution Event", "blue", "info"))
        title, border_style, sink_kind = title_style
        details = [
            f"Session: {event.session_public_id}",
            f"Event: {event.event_type.value}",
        ]
        if event.target_summary:
            details.append(f"Target: {event.target_summary}")
        if event.message:
            details.append(f"Message: {event.message}")
        details.append(f"At: {self._format_timestamp_compact(event.timestamp)}")
        self._emit(
            Panel(
                Text("\n".join(details)),
                title=title,
                border_style=border_style,
                box=ASCII_BOX,
            ),
            kind=sink_kind,
        )

    def show_info(self, message: str) -> None:
        self._emit(Panel(Text(message), title="Info", border_style="blue", box=ASCII_BOX), kind="info")

    def show_success(self, message: str) -> None:
        self._emit(Panel(Text(message), title="Success", border_style="green", box=ASCII_BOX), kind="success")

    def show_error(self, message: str) -> None:
        self._emit(Panel(Text(message), title="Error", border_style="red", box=ASCII_BOX), kind="error")

    def show_header(self, title: str) -> None:
        self._emit(Rule(f" {title} ", style="bright_blue", characters="-"), kind="header")

    def show_final_answer(self, text: str) -> None:
        self._emit(Panel(Text(text), title="Final Answer", border_style="green", box=ASCII_BOX), kind="final_answer")

    def show_step_start(self, step_num: int, total_steps: int | None = None) -> None:
        label = f"Step {step_num}/{total_steps}" if total_steps is not None else f"Step {step_num}"
        self._emit(Rule(f" {label} ", style="cyan", characters="-"))

    def show_thinking(self, text: str) -> None:
        self._emit(Panel(Text(text, style="dim"), title="Thinking", border_style="grey50", box=ASCII_BOX))

    def show_tool_call(self, tool_name: str, args: dict) -> None:
        table = Table(box=ASCII_BOX, expand=True)
        table.add_column("Argument", style="cyan", no_wrap=True)
        table.add_column("Value", overflow="fold")
        for key, value in args.items():
            table.add_row(str(key), self._format_tool_argument_value(value))
        self._emit(Panel(table, title=f"Tool: {tool_name}", border_style="yellow", box=ASCII_BOX))

    def show_observation(self, text: str, *, truncate_lines: int = 12, truncate_chars: int = 600) -> None:
        truncated = self._truncate_observation(text, truncate_lines=truncate_lines, truncate_chars=truncate_chars)
        self._emit(Panel(Text(truncated, style="dim"), title="Observation", border_style="grey50", box=ASCII_BOX))


_default_presenter: CliPresenter | None = None


def get_presenter() -> CliPresenter:
    global _default_presenter
    if _default_presenter is None:
        _default_presenter = CliPresenter()
    return _default_presenter


def set_presenter(presenter: CliPresenter | None) -> None:
    global _default_presenter
    _default_presenter = presenter
