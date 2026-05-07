from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

from agent.settings import Settings, get_settings
from models.control_center import AttackPathNode, Event, TargetSession, Task, TaskStatus, TargetType
from models.run import utc_now_iso
from storage.repositories.control_center import (
    AttackPathNodeRepository,
    EventRepository,
    ProjectRepository,
    TargetSessionRepository,
    TaskRepository,
)
from storage.sqlite import SQLiteStorage

from .control_center_base import ControlCenterService
from .scanner_service import ScannerService


@dataclass(frozen=True, slots=True)
class PlannedScan:
    tool_name: str
    task_type: str
    input_data: dict[str, Any]
    reason: str


@dataclass(frozen=True, slots=True)
class EnumerationPlan:
    dir_scans: list[PlannedScan] = field(default_factory=list)
    poc_scans: list[PlannedScan] = field(default_factory=list)
    terminal_suggestions: list[str] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ScanSummary:
    task_id: str
    task_type: str
    status: str
    summary: str
    structured: dict[str, Any]
    error: str | None = None


class EnumerationPlanner:
    def plan_after_port_scan(
        self,
        *,
        session: TargetSession,
        port_scan: Task,
        default_wordlist: str | None,
        nuclei_templates_path: str | None,
    ) -> EnumerationPlan:
        web_targets = self.web_targets_from_port_scan(session=session, port_scan=port_scan)
        dir_scans: list[PlannedScan] = []
        poc_scans: list[PlannedScan] = []
        terminal_suggestions: list[str] = []
        next_actions: list[str] = []

        if web_targets and default_wordlist:
            dir_scans = [
                PlannedScan(
                    tool_name="ffuf",
                    task_type="dir_scan",
                    input_data={"base_url": target, "wordlist": default_wordlist, "filters": {}},
                    reason=f"HTTP service discovered at {target}.",
                )
                for target in web_targets
            ]
        elif web_targets:
            next_actions.append("Configure a default ffuf wordlist to enable automatic directory enumeration.")

        for target in web_targets:
            terminal_suggestions.append(f"curl -I {target}")

        if web_targets and nuclei_templates_path:
            poc_scans = [
                PlannedScan(
                    tool_name="nuclei",
                    task_type="poc_scan",
                    input_data={"target_url": target, "templates": [nuclei_templates_path]},
                    reason=f"HTTP candidate target is available at {target}.",
                )
                for target in web_targets
            ]
        elif web_targets:
            next_actions.append("Configure a nuclei templates path before automatic POC validation.")

        if not web_targets:
            next_actions.append("No HTTP/HTTPS services were identified; continue manual service enumeration.")

        return EnumerationPlan(
            dir_scans=dir_scans,
            poc_scans=poc_scans,
            terminal_suggestions=terminal_suggestions,
            next_actions=next_actions,
        )

    def web_targets_from_port_scan(self, *, session: TargetSession, port_scan: Task) -> list[str]:
        if session.target_type == TargetType.URL:
            return [session.target_value]
        structured = port_scan.result_json.get("structured")
        if not isinstance(structured, dict):
            return []
        open_ports = structured.get("open_ports")
        if not isinstance(open_ports, list):
            return []
        targets: list[str] = []
        for port_data in open_ports:
            if not isinstance(port_data, dict):
                continue
            target = _web_target_from_port(session.target_value, port_data)
            if target is not None and target not in targets:
                targets.append(target)
        return targets


class EnumerationResultReducer:
    def summarize_scan_result(self, task: Task) -> ScanSummary:
        result = task.result_json
        structured = result.get("structured") if isinstance(result.get("structured"), dict) else {}
        summary = result.get("summary") if isinstance(result.get("summary"), str) else _fallback_summary(task)
        return ScanSummary(
            task_id=task.id,
            task_type=task.task_type,
            status=task.status.value,
            summary=summary,
            structured=dict(structured),
            error=task.error,
        )

    def summarize_workflow(self, *, summaries: list[ScanSummary], next_actions: list[str]) -> str:
        parts = [item.summary for item in summaries if item.summary]
        if next_actions:
            parts.append(f"{len(next_actions)} next action(s) suggested.")
        return " ".join(parts) if parts else "Enumeration workflow completed."


class CTFAgentService(ControlCenterService):
    def __init__(
        self,
        *,
        settings: Settings,
        planner: EnumerationPlanner | None = None,
        reducer: EnumerationResultReducer | None = None,
        scanner_service: ScannerService | None = None,
    ) -> None:
        storage = SQLiteStorage(settings.sqlite_path)
        object.__setattr__(self, "settings", settings)
        object.__setattr__(self, "planner", planner or EnumerationPlanner())
        object.__setattr__(self, "reducer", reducer or EnumerationResultReducer())
        object.__setattr__(self, "scanner_service", scanner_service or ScannerService.from_settings(settings))
        object.__setattr__(self, "project_repository", ProjectRepository(storage))
        object.__setattr__(self, "session_repository", TargetSessionRepository(storage))
        object.__setattr__(self, "task_repository", TaskRepository(storage))
        object.__setattr__(self, "event_repository", EventRepository(storage))
        object.__setattr__(self, "attack_path_repository", AttackPathNodeRepository(storage))

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "CTFAgentService":
        return cls(settings=settings or get_settings())

    def create_agent_task(self, *, session_identifier: str, message: str) -> Task:
        session = self.session_repository.require(session_identifier)
        project = self.project_repository.require(session.project_id)
        normalized_message = message.strip()
        if not normalized_message:
            raise ValueError("agent message must be non-empty.")
        task = Task.create(
            project_id=project.id,
            session_id=session.id,
            task_type="agent_analysis",
            executor="ctf_agent",
            input_json={
                "message": normalized_message,
                "intent": _classify_agent_intent(normalized_message),
                "workflow_id": str(uuid4()),
            },
        )
        created = self.task_repository.create(task)
        self._record_agent_event(
            created,
            "agent.message.received",
            level="info",
            payload={"message": normalized_message, "intent": created.input_json["intent"]},
        )
        self._record_agent_event(
            created,
            "agent.workflow.queued",
            level="info",
            payload={"workflow_id": created.input_json["workflow_id"]},
        )
        return created

    def run_agent_task(self, task_identifier: str) -> Task:
        task = self.task_repository.require(task_identifier)
        if task.task_type != "agent_analysis":
            raise ValueError(f"Task is not an agent analysis task: {task_identifier}")
        if task.status == TaskStatus.CANCELLED:
            return task
        task.status = TaskStatus.RUNNING
        task.started_at = utc_now_iso()
        self.task_repository.update(task)
        self._record_agent_event(task, "agent.workflow.started", level="info", payload={"workflow_id": task.input_json.get("workflow_id")})

        try:
            if task.input_json.get("intent") != "enumerate_target":
                result = self._unsupported_message_result(task)
            else:
                result = self._run_enumeration(task)
        except Exception as exc:
            result = {"ok": False, "summary": "Agent enumeration failed.", "error": str(exc), "recoverable": True}

        task.ended_at = utc_now_iso()
        task.status = TaskStatus.SUCCEEDED if result.get("recoverable", False) or result.get("ok", False) else TaskStatus.FAILED
        task.error = result.get("error") if task.status == TaskStatus.FAILED else None
        task.result_json = result
        updated = self.task_repository.update(task)
        self._record_agent_event(
            updated,
            "agent.summary",
            level="info" if updated.status == TaskStatus.SUCCEEDED else "error",
            payload={
                "summary": result.get("summary"),
                "recoverable": result.get("recoverable", False),
                "error": result.get("error"),
            },
        )
        self._record_agent_event(
            updated,
            "agent.workflow.completed" if updated.status == TaskStatus.SUCCEEDED else "agent.workflow.failed",
            level="info" if updated.status == TaskStatus.SUCCEEDED else "error",
            payload={"workflow_id": updated.input_json.get("workflow_id"), "status": updated.status.value},
        )
        return updated

    def start_port_scan(self, *, session: TargetSession, agent_task: Task) -> Task:
        self._record_agent_event(agent_task, "agent.tool.started", level="info", payload={"tool": "start_port_scan"})
        task = self.scanner_service.create_scan_task(
            session_identifier=session.id,
            task_type="port_scan",
            input_data={"target_host": _scanner_host_for_session(session)},
        )
        self._record_agent_event(
            agent_task,
            "agent.tool.completed",
            level="info" if task.status == TaskStatus.SUCCEEDED else "error",
            payload={"tool": "start_port_scan", "task_id": task.id, "status": task.status.value},
        )
        return task

    def start_dir_scan(self, *, session: TargetSession, agent_task: Task, plan: PlannedScan) -> Task:
        self._record_agent_event(agent_task, "agent.tool.started", level="info", payload={"tool": "start_dir_scan", "reason": plan.reason})
        task = self.scanner_service.create_scan_task(
            session_identifier=session.id,
            task_type=plan.task_type,
            input_data=plan.input_data,
        )
        self._record_agent_event(
            agent_task,
            "agent.tool.completed",
            level="info" if task.status == TaskStatus.SUCCEEDED else "error",
            payload={"tool": "start_dir_scan", "task_id": task.id, "status": task.status.value},
        )
        return task

    def start_poc_scan(self, *, session: TargetSession, agent_task: Task, plan: PlannedScan) -> Task:
        self._record_agent_event(agent_task, "agent.tool.started", level="info", payload={"tool": "start_poc_scan", "reason": plan.reason})
        task = self.scanner_service.create_scan_task(
            session_identifier=session.id,
            task_type=plan.task_type,
            input_data=plan.input_data,
        )
        self._record_agent_event(
            agent_task,
            "agent.tool.completed",
            level="info" if task.status == TaskStatus.SUCCEEDED else "error",
            payload={"tool": "start_poc_scan", "task_id": task.id, "status": task.status.value},
        )
        return task

    def summarize_scan_result(self, task: Task) -> ScanSummary:
        return self.reducer.summarize_scan_result(task)

    def create_attack_path_node(self, *, session: TargetSession, title: str, next_action: str, source_ref: str | None = None) -> AttackPathNode:
        return self.attack_path_repository.create(
            AttackPathNode.create(
                project_id=session.project_id,
                session_id=session.id,
                stage="agent-analysis",
                title=title,
                status="open",
                source_ref=source_ref,
                next_action=next_action,
            )
        )

    def suggest_terminal_command(self, *, agent_task: Task, command: str) -> None:
        self._record_agent_event(
            agent_task,
            "agent.terminal_command.suggested",
            level="info",
            payload={"command": command},
        )

    def _run_enumeration(self, agent_task: Task) -> dict[str, Any]:
        session = self.session_repository.require(agent_task.session_id)
        summaries: list[ScanSummary] = []
        task_ids: list[str] = []
        next_actions: list[str] = []

        port_task = self.start_port_scan(session=session, agent_task=agent_task)
        task_ids.append(port_task.id)
        port_summary = self.summarize_scan_result(port_task)
        summaries.append(port_summary)
        self._record_agent_event(agent_task, "agent.scan_summary", level="info", payload=asdict(port_summary))

        if port_task.status != TaskStatus.SUCCEEDED:
            summary = f"Port scan failed recoverably: {port_task.error or port_summary.summary}"
            return {
                "ok": True,
                "recoverable": True,
                "summary": summary,
                "task_ids": task_ids,
                "next_actions": ["Fix scanner configuration or target reachability, then rerun enumeration."],
            }

        config = self.scanner_service.get_config()
        plan = self.planner.plan_after_port_scan(
            session=session,
            port_scan=port_task,
            default_wordlist=config.for_tool("ffuf").default_wordlist,
            nuclei_templates_path=config.for_tool("nuclei").templates_path,
        )
        self._record_agent_event(
            agent_task,
            "agent.plan.created",
            level="info",
            payload={
                "dir_scan_count": len(plan.dir_scans),
                "poc_scan_count": len(plan.poc_scans),
                "next_actions": list(plan.next_actions),
            },
        )

        for planned in plan.dir_scans:
            task = self.start_dir_scan(session=session, agent_task=agent_task, plan=planned)
            task_ids.append(task.id)
            scan_summary = self.summarize_scan_result(task)
            summaries.append(scan_summary)
            self._record_agent_event(agent_task, "agent.scan_summary", level="info", payload=asdict(scan_summary))

        for planned in plan.poc_scans:
            task = self.start_poc_scan(session=session, agent_task=agent_task, plan=planned)
            task_ids.append(task.id)
            scan_summary = self.summarize_scan_result(task)
            summaries.append(scan_summary)
            self._record_agent_event(agent_task, "agent.scan_summary", level="info", payload=asdict(scan_summary))

        for command in plan.terminal_suggestions:
            self.suggest_terminal_command(agent_task=agent_task, command=command)

        for action in plan.next_actions:
            next_actions.append(action)
            self.create_attack_path_node(
                session=session,
                title="Agent next action",
                next_action=action,
                source_ref=agent_task.id,
            )
            self._record_agent_event(agent_task, "agent.next_action.suggested", level="info", payload={"message": action})

        return {
            "ok": True,
            "recoverable": False,
            "summary": self.reducer.summarize_workflow(summaries=summaries, next_actions=next_actions),
            "task_ids": task_ids,
            "next_actions": next_actions,
        }

    def _unsupported_message_result(self, task: Task) -> dict[str, Any]:
        message = "Select a target Session and ask for enumeration to start the Phase 4 workflow."
        self._record_agent_event(task, "agent.next_action.suggested", level="info", payload={"message": message})
        return {"ok": True, "recoverable": True, "summary": message, "task_ids": [], "next_actions": [message]}

    def _record_agent_event(
        self,
        task: Task,
        event_kind: str,
        *,
        level: str,
        payload: dict[str, Any],
    ) -> Event:
        return self.event_repository.create(
            Event.create(
                project_id=task.project_id,
                session_id=task.session_id,
                task_id=task.id,
                event_kind=event_kind,
                level=level,
                payload=payload,
            )
        )


def _classify_agent_intent(message: str) -> str:
    normalized = message.lower()
    if "枚举" in message or "enumerate" in normalized or "recon" in normalized or "scan" in normalized:
        return "enumerate_target"
    return "unknown"


def _scanner_host_for_session(session: TargetSession) -> str:
    if session.target_type == TargetType.URL:
        parsed = urlsplit(session.target_value)
        return parsed.hostname or session.target_value
    return session.target_value


def _web_target_from_port(host: str, port_data: dict[str, Any]) -> str | None:
    port = port_data.get("port")
    if not isinstance(port, int):
        return None
    service = str(port_data.get("service") or "").lower()
    scheme: str | None = None
    if "https" in service or port in {443, 8443, 9443}:
        scheme = "https"
    elif "http" in service or port in {80, 8000, 8080, 8888}:
        scheme = "http"
    if scheme is None:
        return None
    default_port = 443 if scheme == "https" else 80
    netloc = host if port == default_port else f"{host}:{port}"
    return f"{scheme}://{netloc}"


def _fallback_summary(task: Task) -> str:
    if task.status == TaskStatus.FAILED:
        return task.error or f"{task.task_type} failed."
    return f"{task.task_type} {task.status.value}."
