from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from io import StringIO
import os
from typing import Callable

from rich import box
from rich.console import Console, Group, RenderableType
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from app.dashboard_service import OperationDashboard
from models.checkpoint import CheckpointSummary
from models.evidence import Evidence
from models.finding import Finding
from models.job import Job
from models.operation import Operation
from models.operation_event import OperationEvent
from models.planner import (
    OperationContextSummary,
    PlannerMemoryWritebackStatus,
    PlannerMemoryWritebackSummary,
    PlannerPlan,
    PlannerProposal,
    PlannerProposalKind,
)
from models.run import Run, TaskLogEntry
from models.skill import LoadedSkill
from models.scope_policy import ScopePolicy
from models.task import Task


SinkFn = Callable[[str], None]
NONE_LABEL = "none"
ASCII_BOX = box.ASCII


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
        topics = Table(box=ASCII_BOX, expand=True, header_style="bold")
        topics.add_column("Topic", style="bold cyan", no_wrap=True)
        topics.add_column("Purpose", style="white")
        topics.add_row("operation", "Red-team operations and scope policy inspection")
        topics.add_row("job", "Operation jobs and execution details")
        topics.add_row("finding", "Finding review and triage")
        topics.add_row("evidence", "Evidence inspection and traceability")
        topics.add_row("dashboard", "Operation summary, failures, and recent events")
        topics.add_row("planner", "Structured next-step planning for v2 operations")
        topics.add_row("task", "Task lifecycle, runs, checkpoints, and logs")
        topics.add_row("skill", "Skill activation, inspection, reload, and shorthand usage")
        return Group(
            Text("Base mode uses the default prompt and full built-in tool set.", style="dim"),
            Rule(style="grey50", characters="-"),
            Panel(topics, title="Help Topics", border_style="bright_blue", box=ASCII_BOX),
            Text(
                "Drill down with /help operation, /help job, /help finding, /help evidence.",
                style="dim",
            ),
            Text(
                "Also available: /help dashboard, /help planner, /help task, /help skill.",
                style="dim",
            ),
            Text("Session shortcuts: /clear, /reset, /exit, /quit", style="dim"),
        )

    def _help_operation(self) -> Group:
        return Group(
            Text("Operation help", style="dim"),
            Rule(style="grey50", characters="-"),
            self._command_panel("Operation Commands", [
                ("/operation create", "Create an operation and its scope policy"),
                ("/operation list [status] [limit]", "List recent operations"),
                ("/operation show <id>", "Show operation details and scope policy"),
                ("/operation pause <id>", "Pause an operation so new jobs stop being scheduled"),
                ("/operation resume <id>", "Resume a draft, paused, or blocked operation into ready"),
            ], border_style="cyan"),
        )

    def _help_job(self) -> Group:
        return Group(
            Text("Job help", style="dim"),
            Rule(style="grey50", characters="-"),
            self._command_panel("Job Commands", [
                ("/job create <operation_id>", "Create a job inside an operation"),
                ("/job list <operation_id> [status] [limit]", "List jobs for an operation"),
                ("/job show <job_id>", "Show job details"),
                ("/job cancel <job_id>", "Request cancellation for a queued or running job"),
            ], border_style="magenta"),
        )

    def _help_finding(self) -> Group:
        return Group(
            Text("Finding help", style="dim"),
            Rule(style="grey50", characters="-"),
            self._command_panel("Finding Commands", [
                ("/finding list <operation_id> [limit]", "List findings for an operation"),
                ("/finding show <finding_id>", "Show finding details and linked evidence"),
                ("/finding confirm <finding_id>", "Mark a finding as confirmed"),
                ("/finding dismiss <finding_id>", "Dismiss a finding with an optional reason"),
            ], border_style="yellow"),
        )

    def _help_evidence(self) -> Group:
        return Group(
            Text("Evidence help", style="dim"),
            Rule(style="grey50", characters="-"),
            self._command_panel("Evidence Commands", [
                ("/evidence list <operation_id> [limit]", "List evidence for an operation"),
                ("/evidence show <evidence_id>", "Show evidence details and linked findings"),
            ], border_style="green"),
        )

    def _help_dashboard(self) -> Group:
        return Group(
            Text("Dashboard help", style="dim"),
            Rule(style="grey50", characters="-"),
            self._command_panel("Dashboard Commands", [
                ("/dashboard", "Show the most recently updated operation dashboard"),
                ("/dashboard <operation_id>", "Show the dashboard for one operation"),
            ], border_style="bright_blue"),
        )

    def _help_planner(self) -> Group:
        return Group(
            Text("Planner help", style="dim"),
            Rule(style="grey50", characters="-"),
            self._command_panel("Planner Commands", [
                ("/planner plan <operation_id>", "Create and preview a persisted planner plan"),
                ("/planner apply <plan_id> [1,3,...]", "Create jobs from all or selected planner proposals"),
            ], border_style="bright_blue"),
            Text(
                "Tip: /operation resume now shows a context summary and points you to /planner plan.",
                style="dim",
            ),
        )

    def _help_task(self) -> Group:
        return Group(
            Text("Task help", style="dim"),
            Rule(style="grey50", characters="-"),
            self._command_panel("Task Commands", [
                ("/task create", "Create a persisted task"),
                ("/task list [status] [limit]", "List recent tasks"),
                ("/task recent [limit]", "Show recent tasks"),
                ("/task find <query> [limit]", "Search tasks by title"),
                ("/task show <id>", "Show task details"),
                ("/task status <id>", "Show compact task status"),
                ("/task resume <id>", "Resume and bind a task"),
                ("/task detach", "Pause and detach the active task"),
                ("/task complete", "Mark the active task as completed"),
            ], border_style="cyan"),
            self._command_panel("Runs and Checkpoints", [
                ("/task runs <id> [limit]", "Show recent runs for a task"),
                ("/task run <id>", "Show one run in detail"),
                ("/task checkpoints <id> [limit]", "Show recent checkpoints"),
                ("/task checkpoint <id>", "Show one checkpoint in detail"),
                ("/task logs <id> [limit]", "Show recent task logs"),
            ], border_style="magenta"),
            Text("Tip: use 'latest' or 'last' in task-facing commands to target the most recent task.", style="dim"),
        )

    def _help_skill(self) -> Group:
        return Group(
            Text("Skill help", style="dim"),
            Rule(style="grey50", characters="-"),
            self._command_panel("Skill Commands", [
                ("/skill list", "List built-in and local skills"),
                ("/skill show <name>", "Show skill details"),
                ("/skill use <name>", "Activate a skill for this shell"),
                ("/skill plan <name> <operation_id>", "Preview bounded workflow jobs for an operation"),
                ("/skill apply <name> <operation_id>", "Create bounded workflow jobs for an operation"),
                ("/skill reload", "Reload skills from disk"),
                ("/skill clear", "Clear the active shell skill"),
                ("/skill current", "Show the active shell skill"),
            ], border_style="green"),
            self._command_panel("Shorthand Invocation", [
                ("/skill-name <prompt>", "Run one prompt with a skill without activating it"),
            ], border_style="bright_blue"),
        )

    def show_help(self, topic: str | None = None) -> None:
        if topic is None:
            body = self._help_overview()
            title = "red-code"
        elif topic == "operation":
            body = self._help_operation()
            title = "Help: operation"
        elif topic == "job":
            body = self._help_job()
            title = "Help: job"
        elif topic == "finding":
            body = self._help_finding()
            title = "Help: finding"
        elif topic == "evidence":
            body = self._help_evidence()
            title = "Help: evidence"
        elif topic == "dashboard":
            body = self._help_dashboard()
            title = "Help: dashboard"
        elif topic == "planner":
            body = self._help_planner()
            title = "Help: planner"
        elif topic == "task":
            body = self._help_task()
            title = "Help: task"
        elif topic == "skill":
            body = self._help_skill()
            title = "Help: skill"
        else:
            raise ValueError(f"Unsupported help topic: {topic}")
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
            return
        file = self.console.file
        is_tty = callable(getattr(file, "isatty", None)) and bool(file.isatty())
        if os.name == "nt" and is_tty:
            # `cls` remains the most reliable option for classic Windows terminals.
            if os.system("cls") == 0:
                return
        self.console.clear(home=True)

    def show_task_list(self, tasks: list[Task], *, filter_label: str | None = None) -> None:
        if not tasks:
            self._emit(Panel(Text("No tasks found.", style="dim"), title="Tasks", border_style="yellow", box=ASCII_BOX))
            return
        table = Table(title=filter_label or "Tasks", box=ASCII_BOX, expand=True, header_style="bold")
        table.add_column("Task", style="cyan", no_wrap=True)
        table.add_column("Status", no_wrap=True)
        table.add_column("Updated", style="dim", no_wrap=True)
        table.add_column("Skill", style="magenta")
        table.add_column("Title", overflow="fold")
        for task in tasks:
            table.add_row(
                task.public_id,
                self._status_text(task.status.value),
                self._format_timestamp_compact(task.updated_at),
                self._render_skill_name(task.skill_profile),
                task.title,
            )
        self._emit(table)

    def show_operation_list(self, operations: list[Operation], *, filter_label: str | None = None) -> None:
        if not operations:
            self._emit(
                Panel(Text("No operations found.", style="dim"), title="Operations", border_style="yellow", box=ASCII_BOX)
            )
            return
        table = Table(title=filter_label or "Operations", box=ASCII_BOX, expand=True, header_style="bold")
        table.add_column("Operation", style="cyan", no_wrap=True)
        table.add_column("Status", no_wrap=True)
        table.add_column("Updated", style="dim", no_wrap=True)
        table.add_column("Title", overflow="fold")
        table.add_column("Objective", overflow="fold")
        for operation in operations:
            table.add_row(
                operation.public_id,
                self._status_text(operation.status.value),
                self._format_timestamp_compact(operation.updated_at),
                operation.title,
                operation.objective,
            )
        self._emit(table)

    def show_operation_detail(self, operation: Operation, policy: ScopePolicy) -> None:
        summary = Panel(
            self._detail_table([
                ("Operation ID", operation.public_id),
                ("Internal ID", operation.id),
                ("Title", operation.title),
                ("Objective", operation.objective),
                ("Status", operation.status.value),
                ("Workspace", operation.workspace),
                ("Scope Policy ID", policy.id),
                ("Created At", operation.created_at),
                ("Updated At", operation.updated_at),
                ("Closed At", operation.closed_at or "-"),
                ("Last Error", operation.last_error or "-"),
            ]),
            title="Operation",
            border_style="cyan",
            box=ASCII_BOX,
        )
        policy_panel = Panel(
            self._detail_table([
                ("Allowed Hosts", ", ".join(policy.allowed_hosts) or "-"),
                ("Allowed Domains", ", ".join(policy.allowed_domains) or "-"),
                ("Allowed CIDRs", ", ".join(policy.allowed_cidrs) or "-"),
                ("Allowed Ports", ", ".join(str(port) for port in policy.allowed_ports) or "-"),
                ("Allowed Protocols", ", ".join(policy.allowed_protocols) or "-"),
                ("Denied Targets", ", ".join(policy.denied_targets) or "-"),
                ("Tool Categories", ", ".join(policy.allowed_tool_categories) or "-"),
                ("Max Concurrency", str(policy.max_concurrency)),
                ("Rate Limit", str(policy.rate_limit_per_minute) if policy.rate_limit_per_minute is not None else "-"),
                ("Confirmation Actions", ", ".join(policy.confirmation_required_actions) or "-"),
            ]),
            title="Scope Policy",
            border_style="magenta",
            box=ASCII_BOX,
        )
        self._emit(Group(summary, policy_panel))

    def show_operation_context_summary(self, summary: OperationContextSummary) -> None:
        self._emit(
            Panel(
                self._detail_table([
                    ("Operation", summary.operation_id),
                    ("Summary", summary.summary),
                    ("Scope", summary.scope_summary),
                    ("Findings", summary.findings_summary),
                    ("Evidence", summary.evidence_summary),
                    ("Memory", summary.memory_summary),
                    ("Suggested Next Step", summary.next_step_hint),
                ]),
                title="Operation Context Summary",
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
                    ("Operation ID", job.operation_id),
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
                    ("Operation ID", finding.operation_id),
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
                    ("Linked Evidence IDs", ", ".join(linked_evidence_ids) or "-"),
                    ("Created At", finding.created_at),
                    ("Updated At", finding.updated_at),
                ]),
                title="Finding",
                border_style="yellow",
                box=ASCII_BOX,
            )
        )

    def show_evidence_list(self, evidence_items: list[Evidence], *, operation_label: str | None = None) -> None:
        if not evidence_items:
            self._emit(
                Panel(Text("No evidence found.", style="dim"), title="Evidence", border_style="yellow", box=ASCII_BOX)
            )
            return
        title = f"Evidence for {operation_label}" if operation_label else "Evidence"
        table = Table(title=title, box=ASCII_BOX, expand=True, header_style="bold")
        table.add_column("Evidence", style="cyan", no_wrap=True)
        table.add_column("Type", no_wrap=True)
        table.add_column("Target", overflow="fold")
        table.add_column("Captured", style="dim", no_wrap=True)
        table.add_column("Title", overflow="fold")
        for evidence in evidence_items:
            table.add_row(
                evidence.public_id,
                evidence.evidence_type,
                evidence.target_ref,
                self._format_timestamp_compact(evidence.captured_at),
                evidence.title,
            )
        self._emit(table)

    def show_evidence_detail(self, evidence: Evidence, *, linked_finding_ids: list[str]) -> None:
        self._emit(
            Panel(
                self._detail_table([
                    ("Evidence ID", evidence.public_id),
                    ("Internal ID", evidence.id),
                    ("Operation ID", evidence.operation_id),
                    ("Job ID", evidence.job_id or "-"),
                    ("Type", evidence.evidence_type),
                    ("Target", evidence.target_ref),
                    ("Title", evidence.title),
                    ("Summary", evidence.summary),
                    ("Artifact Path", evidence.artifact_path or "-"),
                    ("Content Type", evidence.content_type or "-"),
                    ("Hash Digest", evidence.hash_digest or "-"),
                    ("Linked Finding IDs", ", ".join(linked_finding_ids) or "-"),
                    ("Captured At", evidence.captured_at),
                ]),
                title="Evidence",
                border_style="green",
                box=ASCII_BOX,
            )
        )

    def show_dashboard(self, dashboard: OperationDashboard) -> None:
        summary = Panel(
            self._detail_table([
                ("Operation ID", dashboard.operation.public_id),
                ("Title", dashboard.operation.title),
                ("Objective", dashboard.operation.objective),
                ("Status", dashboard.operation.status.value),
                ("Workspace", dashboard.operation.workspace),
                ("Allowed Hosts", ", ".join(dashboard.policy.allowed_hosts) or "-"),
                ("Allowed Domains", ", ".join(dashboard.policy.allowed_domains) or "-"),
                ("Allowed Ports", ", ".join(str(port) for port in dashboard.policy.allowed_ports) or "-"),
                ("Allowed Protocols", ", ".join(dashboard.policy.allowed_protocols) or "-"),
                ("Evidence Total", str(dashboard.evidence_count)),
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

        recent_evidence: RenderableType
        if dashboard.recent_evidence:
            recent_evidence = Table(title=f"Recent Evidence ({dashboard.evidence_count} total)", box=ASCII_BOX, expand=True, header_style="bold")
            recent_evidence.add_column("Evidence", style="cyan", no_wrap=True)
            recent_evidence.add_column("Type", no_wrap=True)
            recent_evidence.add_column("Target", overflow="fold")
            recent_evidence.add_column("Captured", style="dim", no_wrap=True)
            for evidence in dashboard.recent_evidence:
                recent_evidence.add_row(
                    evidence.public_id,
                    evidence.evidence_type,
                    evidence.target_ref,
                    self._format_timestamp_compact(evidence.captured_at),
                )
        else:
            recent_evidence = Panel(
                Text("No evidence found.", style="dim"),
                title=f"Recent Evidence ({dashboard.evidence_count} total)",
                border_style="yellow",
                box=ASCII_BOX,
            )

        recent_events: RenderableType
        if dashboard.recent_events:
            recent_events = Table(title="Recent Operation Events", box=ASCII_BOX, expand=True, header_style="bold")
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
                Text("No operation events found.", style="dim"),
                title="Recent Operation Events",
                border_style="yellow",
                box=ASCII_BOX,
            )

        self._emit(Group(summary, job_counts, finding_counts, flagged_jobs, recent_findings, recent_evidence, recent_events))

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
                ("Operation", operation_label),
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

    def show_task_detail(self, task: Task) -> None:
        identity = Panel(
            self._detail_table([
                ("Task ID", task.public_id),
                ("Internal ID", task.id),
                ("Title", task.title),
                ("Goal", task.goal),
                ("Status", task.status.value),
                ("Skill", self._render_skill_name(task.skill_profile)),
                ("Workspace", task.workspace),
            ]),
            title="Task",
            border_style="cyan",
            box=ASCII_BOX,
        )
        execution = Panel(
            self._detail_table([
                ("Created At", task.created_at),
                ("Updated At", task.updated_at),
                ("Last Checkpoint", task.last_checkpoint or "-"),
                ("Last Error", task.last_error or "-"),
            ]),
            title="Execution and Recovery",
            border_style="magenta",
            box=ASCII_BOX,
        )
        self._emit(Group(identity, execution))

    def show_task_status(self, task: Task) -> None:
        self._emit(
            Panel(
                self._detail_table([
                    ("Task", task.public_id),
                    ("Title", task.title),
                    ("Status", task.status.value),
                    ("Skill", self._render_skill_name(task.skill_profile)),
                    ("Updated At", task.updated_at),
                    ("Last Checkpoint", task.last_checkpoint or "-"),
                    ("Last Error", task.last_error or "-"),
                ]),
                title="Task Status",
                border_style="cyan",
                box=ASCII_BOX,
            )
        )

    def show_run_list(self, runs: list[Run], task: Task | None = None) -> None:
        if not runs:
            self._emit(Panel(Text("No runs found.", style="dim"), title="Runs", border_style="yellow", box=ASCII_BOX))
            return
        title = f"Runs for {task.public_id}" if task is not None else "Runs"
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

    def show_run_detail(self, run: Run, task: Task, entries: list[TaskLogEntry]) -> None:
        summary = Panel(
            self._detail_table([
                ("Run ID", run.public_id),
                ("Internal ID", run.id),
                ("Task", task.public_id or task.id),
                ("Task Internal ID", task.id),
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
        self._emit(Group(summary, self._task_log_table(entries, {run.id: run.public_id}, title="Recent Run Logs")))

    def show_checkpoint_list(self, summaries: list[CheckpointSummary], task: Task, run_labels: dict[str, str]) -> None:
        if not summaries:
            self._emit(Panel(Text(f"No checkpoints found for task {task.public_id}.", style="dim"), title="Checkpoints", border_style="yellow", box=ASCII_BOX))
            return
        table = Table(title=f"Checkpoints for {task.public_id}", box=ASCII_BOX, expand=True, header_style="bold")
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

    def show_checkpoint_detail(self, summary: CheckpointSummary, task: Task, run_label: str | None = None) -> None:
        self._emit(
            Panel(
                self._detail_table([
                    ("Checkpoint ID", summary.id),
                    ("Task", task.public_id),
                    ("Task Internal ID", task.id),
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

    def show_task_logs(self, entries: list[TaskLogEntry], run_labels: dict[str, str] | None = None) -> None:
        self._emit(self._task_log_table(entries, run_labels or {}, title="Task Logs"))

    def _task_log_table(self, entries: list[TaskLogEntry], run_labels: dict[str, str], *, title: str) -> RenderableType:
        if not entries:
            return Panel(Text("No task logs found.", style="dim"), title=title, border_style="yellow", box=ASCII_BOX)
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

    def show_skill_workflow_plan(
        self,
        *,
        skill_name: str,
        workflow_profile: str,
        operation_label: str,
        primary_target: str,
        planned_rows: list[dict[str, str]],
        skipped_rows: list[dict[str, str]],
    ) -> None:
        summary = Panel(
            self._detail_table([
                ("Skill", skill_name),
                ("Workflow Profile", workflow_profile),
                ("Operation", operation_label),
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
            table.add_row(str(key), str(value))
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
