from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from agent.provider import create_model
from agent.settings import Settings
from langchain.tools import StructuredTool
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from models.control_center import Event, Finding, TargetSession, TargetSource, Task
from pydantic import BaseModel, Field
from storage.repositories.control_center import (
    AttackPathNodeRepository,
    EventRepository,
    EvidenceRepository,
    FindingRepository,
    TargetSessionRepository,
    TaskRepository,
)
from storage.sqlite import SQLiteStorage

from .attack_path_service import AttackPathService
from .scanner_service import ScannerService
from .target_admission_service import TargetAdmissionService
from .writeup_service import WriteupService


ModelFactory = Callable[[Settings], Any]


@dataclass(frozen=True, slots=True)
class AgentToolResult:
    summary: str
    model_text: str
    data: dict[str, Any]


class StartPortScanInput(BaseModel):
    target_id: str | None = Field(default=None, description="Active target id or public id from the Target Pool.")
    reason: str | None = Field(default=None, description="Why a port scan is useful now.")


class StartDirScanInput(BaseModel):
    target_id: str | None = Field(default=None, description="Active URL target id or public id from the Target Pool.")
    base_url: str | None = Field(default=None, description="HTTP(S) URL to submit for target admission when target_id is not available.")
    wordlist: str | None = Field(default=None, description="Optional ffuf wordlist path.")
    reason: str | None = Field(default=None, description="Why directory enumeration is useful now.")


class StartPocScanInput(BaseModel):
    target_id: str | None = Field(default=None, description="Active URL target id or public id from the Target Pool.")
    target_url: str | None = Field(default=None, description="HTTP(S) URL to submit for target admission when target_id is not available.")
    templates: list[str] | None = Field(default=None, description="Optional nuclei template paths.")
    reason: str | None = Field(default=None, description="Why POC validation is useful now.")


class ProposeTargetInput(BaseModel):
    value: str = Field(description="Discovered host, IP, or URL to submit for scope admission.")
    source: str | None = Field(default="agent_discovered", description="Discovery source label.")
    evidence_id: str | None = Field(default=None, description="Optional evidence id or public id supporting the discovery.")


class SummarizeTaskResultInput(BaseModel):
    task_id: str = Field(description="Task id or public id to summarize.")


class CreateAttackPathNodeInput(BaseModel):
    stage: str = Field(description="Attack path stage, e.g. recon, web-enum, poc-verified.")
    title: str = Field(description="Short node title.")
    status: str = Field(default="open", description="Node status.")
    next_action: str | None = Field(default=None, description="Suggested next action.")
    evidence_ids: list[str] | None = Field(default=None, description="Evidence ids or public ids to link.")


class CreateFindingInput(BaseModel):
    severity: str = Field(default="info", description="Finding severity.")
    status: str = Field(default="candidate", description="Finding status.")
    title: str = Field(description="Finding title.")
    description: str | None = Field(default=None, description="Finding description.")
    evidence_refs: list[str] | None = Field(default=None, description="Evidence ids or public ids supporting the finding.")


class SuggestTerminalCommandInput(BaseModel):
    command: str = Field(description="Terminal command suggestion for the operator to review and run.")
    reason: str | None = Field(default=None, description="Why this command is suggested.")


class CreateWriteupDraftInput(BaseModel):
    title: str | None = Field(default=None, description="Optional writeup title.")


@dataclass(frozen=True, slots=True)
class AgentToolSpec:
    name: str
    description: str
    input_model: type[BaseModel]

    def build_langchain_tool(self) -> StructuredTool:
        def schema_only_tool(**_kwargs: Any) -> str:
            return "This schema-only tool is executed by AgentToolRouter."

        schema_only_tool.__name__ = self.name
        return StructuredTool.from_function(
            func=schema_only_tool,
            name=self.name,
            description=self.description,
            args_schema=self.input_model,
        )


class AgentToolRouter:
    def __init__(self, *, settings: Settings, scanner_service: ScannerService | None = None) -> None:
        storage = SQLiteStorage(settings.sqlite_path)
        self.settings = settings
        self.scanner_service = scanner_service or ScannerService.from_settings(settings)
        self.session_repository = TargetSessionRepository(storage)
        self.task_repository = TaskRepository(storage)
        self.event_repository = EventRepository(storage)
        self.evidence_repository = EvidenceRepository(storage)
        self.finding_repository = FindingRepository(storage)
        self.node_repository = AttackPathNodeRepository(storage)
        self.attack_path_service = AttackPathService.from_settings(settings)
        self.target_admission_service = TargetAdmissionService.from_settings(settings)
        self.writeup_service = WriteupService.from_settings(settings)
        self._specs = {
            spec.name: spec
            for spec in (
                AgentToolSpec("propose_target", "Submit a discovered target for scope admission.", ProposeTargetInput),
                AgentToolSpec("start_port_scan", "Start an in-scope nmap port scan for an active Target Pool target.", StartPortScanInput),
                AgentToolSpec("start_dir_scan", "Start an in-scope ffuf directory scan for an active URL target.", StartDirScanInput),
                AgentToolSpec("start_poc_scan", "Start an in-scope nuclei POC scan for an active URL target.", StartPocScanInput),
                AgentToolSpec("summarize_task_result", "Summarize a task result from the active Session.", SummarizeTaskResultInput),
                AgentToolSpec("create_attack_path_node", "Create an attack path node in the active Session.", CreateAttackPathNodeInput),
                AgentToolSpec("create_finding", "Create a structured finding in the active Session.", CreateFindingInput),
                AgentToolSpec("suggest_terminal_command", "Suggest a terminal command for the operator to run manually.", SuggestTerminalCommandInput),
                AgentToolSpec("create_writeup_draft", "Generate a persistent Markdown writeup report from current Session records.", CreateWriteupDraftInput),
            )
        }

    def langchain_tools(self) -> list[StructuredTool]:
        return [spec.build_langchain_tool() for spec in self._specs.values()]

    def execute(self, *, agent_task: Task, tool_name: str, arguments: dict[str, Any]) -> AgentToolResult:
        spec = self._specs.get(tool_name)
        self._record_event(
            agent_task,
            "agent.tool_call.started",
            level="info",
            payload={"tool": tool_name, "arguments": dict(arguments)},
        )
        if spec is None:
            return self._tool_error(agent_task, tool_name, f"Tool is not registered: {tool_name}")
        try:
            parsed = spec.input_model.model_validate(arguments).model_dump()
            result = self._dispatch(agent_task=agent_task, tool_name=tool_name, arguments=parsed)
        except Exception as exc:
            return self._tool_error(agent_task, tool_name, str(exc))
        self._record_event(
            agent_task,
            "agent.tool_call.completed",
            level="info",
            payload={"tool": tool_name, "status": "succeeded", "summary": result.summary, "data": result.data},
        )
        return result

    def _dispatch(self, *, agent_task: Task, tool_name: str, arguments: dict[str, Any]) -> AgentToolResult:
        session = self.session_repository.require(agent_task.session_id)
        if tool_name == "propose_target":
            result = self.target_admission_service.propose_target(
                project_identifier=session.project_id,
                value=str(arguments["value"]),
                source=TargetSource(str(arguments.get("source") or "agent_discovered")),
                evidence_id=arguments.get("evidence_id"),
                discovered_by="ctf_agent",
                discovered_from=agent_task.id,
            )
            text = f"Target {result.target.public_id} {result.status}: {result.reason}"
            return AgentToolResult(
                summary=text,
                model_text=text,
                data={"target_id": result.target.id, "public_id": result.target.public_id, "status": result.status},
            )
        if tool_name == "start_port_scan":
            task = self.scanner_service.create_scan_task(
                session_identifier=session.id,
                task_type="port_scan",
                input_data={"target_id": arguments.get("target_id")},
            )
            return _task_result(task, "Started port scan.")
        if tool_name == "start_dir_scan":
            wordlist = arguments.get("wordlist") or self.scanner_service.get_config().for_tool("ffuf").default_wordlist
            if not wordlist:
                raise ValueError("ffuf wordlist is not configured.")
            task = self.scanner_service.create_scan_task(
                session_identifier=session.id,
                task_type="dir_scan",
                input_data=self._input_with_target_id(
                    session=session,
                    input_data={
                        "target_id": arguments.get("target_id"),
                        "base_url": arguments.get("base_url"),
                        "wordlist": wordlist,
                        "filters": {},
                    },
                ),
            )
            return _task_result(task, "Started directory scan.")
        if tool_name == "start_poc_scan":
            templates = arguments.get("templates") or [self.scanner_service.get_config().for_tool("nuclei").templates_path]
            templates = [str(item) for item in templates if item]
            if not templates:
                raise ValueError("nuclei templates path is not configured.")
            task = self.scanner_service.create_scan_task(
                session_identifier=session.id,
                task_type="poc_scan",
                input_data=self._input_with_target_id(
                    session=session,
                    input_data={
                        "target_id": arguments.get("target_id"),
                        "target_url": arguments.get("target_url"),
                        "templates": templates,
                    },
                ),
            )
            return _task_result(task, "Started POC scan.")
        if tool_name == "summarize_task_result":
            task = self.task_repository.require(str(arguments["task_id"]))
            if task.session_id != session.id:
                raise ValueError("Task is not in the active Session.")
            summary = str(task.result_json.get("summary") or task.error or f"{task.task_type} {task.status.value}.")
            return AgentToolResult(summary=summary, model_text=summary, data={"task_id": task.id, "status": task.status.value})
        if tool_name == "create_attack_path_node":
            detail = self.attack_path_service.create_attack_path_node(
                session_identifier=session.id,
                stage=str(arguments["stage"]),
                title=str(arguments["title"]),
                status=str(arguments.get("status") or "open"),
                next_action=arguments.get("next_action"),
                evidence_ids=list(arguments.get("evidence_ids") or []),
            )
            node = detail.node
            return AgentToolResult(
                summary=f"Created attack path node {node.public_id}.",
                model_text=f"Created attack path node {node.public_id}: {node.title}",
                data={"node_id": node.id, "public_id": node.public_id},
            )

        if tool_name == "create_finding":
            evidence_refs = self._normalize_evidence_refs(session=session, refs=list(arguments.get("evidence_refs") or []))
            finding = self.finding_repository.create(
                Finding.create(
                    project_id=session.project_id,
                    session_id=session.id,
                    severity=str(arguments.get("severity") or "info"),
                    status=str(arguments.get("status") or "candidate"),
                    title=str(arguments["title"]),
                    description=arguments.get("description"),
                    evidence_refs=evidence_refs,
                )
            )
            self._record_event(
                agent_task,
                "finding.created",
                level="info",
                payload={"finding_id": finding.id, "public_id": finding.public_id, "severity": finding.severity},
            )
            return AgentToolResult(
                summary=f"Created finding {finding.public_id}.",
                model_text=f"Created finding {finding.public_id}: {finding.title}",
                data={"finding_id": finding.id, "public_id": finding.public_id},
            )
        if tool_name == "suggest_terminal_command":
            command = str(arguments["command"]).strip()
            if not command:
                raise ValueError("command must be non-empty.")
            self._record_event(
                agent_task,
                "agent.terminal_command.suggested",
                level="info",
                payload={"command": command, "reason": arguments.get("reason")},
            )
            return AgentToolResult(
                summary="Suggested terminal command.",
                model_text=f"Suggested terminal command for operator review: {command}",
                data={"command": command},
            )
        if tool_name == "create_writeup_draft":
            result = self.writeup_service.generate_session_writeup(session_identifier=session.id)
            report = result.report
            self._record_event(
                agent_task,
                "report.generated",
                level="info",
                payload={
                    "report_id": report.id,
                    "public_id": report.public_id,
                    "artifact_path": report.artifact_path,
                    "summary": report.summary,
                },
            )
            return AgentToolResult(
                summary=f"Generated writeup report {report.public_id}.",
                model_text=f"Generated writeup report {report.public_id}: {report.summary}",
                data={"report_id": report.id, "public_id": report.public_id, "artifact_path": report.artifact_path},
            )
        raise ValueError(f"Tool is not implemented: {tool_name}")

    def _input_with_target_id(self, *, session: TargetSession, input_data: dict[str, Any]) -> dict[str, Any]:
        if input_data.get("target_id"):
            return {key: value for key, value in input_data.items() if value is not None}
        value = input_data.get("base_url") or input_data.get("target_url") or input_data.get("target_host")
        if value:
            result = self.target_admission_service.propose_target(
                project_identifier=session.project_id,
                value=str(value),
                discovered_by="ctf_agent",
            )
            if result.target.status.value != "active":
                raise ValueError(f"Target {value} is not active: {result.reason}")
            normalized = {key: value for key, value in input_data.items() if value is not None}
            normalized["target_id"] = result.target.id
            return normalized
        raise ValueError("No active target_id is available for scanner task.")

    def _normalize_evidence_refs(self, *, session: TargetSession, refs: list[str]) -> list[str]:
        evidence_refs: list[str] = []
        for ref in refs:
            evidence = self.evidence_repository.get(ref)
            if evidence is None or evidence.session_id != session.id:
                raise ValueError(f"Evidence not found in active Session: {ref}")
            evidence_refs.append(evidence.id)
        return evidence_refs

    def _tool_error(self, agent_task: Task, tool_name: str, message: str) -> AgentToolResult:
        result = AgentToolResult(
            summary=message,
            model_text=f"Tool {tool_name} failed: {message}",
            data={"error": message},
        )
        self._record_event(
            agent_task,
            "agent.tool_call.completed",
            level="error",
            payload={"tool": tool_name, "status": "failed", "summary": message, "data": result.data},
        )
        return result

    def _record_event(self, task: Task, event_kind: str, *, level: str, payload: dict[str, Any]) -> Event:
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


class AgentOrchestrator:
    def __init__(
        self,
        *,
        settings: Settings,
        tool_router: AgentToolRouter,
        event_repository: EventRepository,
        model_factory: ModelFactory = create_model,
    ) -> None:
        self.settings = settings
        self.tool_router = tool_router
        self.event_repository = event_repository
        self.model_factory = model_factory

    def run_turn(self, *, task: Task, session: TargetSession, message: str) -> dict[str, Any]:
        model = self.model_factory(self.settings).bind_tools(self.tool_router.langchain_tools())
        messages: list[Any] = [
            SystemMessage(content=self._system_prompt()),
            HumanMessage(content=self._context_message(session)),
            HumanMessage(content=message),
        ]
        tool_calls: list[dict[str, Any]] = []
        last_response = ""
        max_steps = min(max(self.settings.max_agent_steps, 1), 8)
        for _ in range(max_steps):
            response: AIMessage = model.invoke(messages)
            response_text = _message_text(response.content)
            if not response.tool_calls:
                final_text = response_text or last_response or "Agent turn completed."
                self._record_event(task, "conversation.completed", level="info", payload={"content": final_text})
                return {"ok": True, "summary": final_text, "response": final_text, "tool_calls": tool_calls}
            if response_text:
                last_response = response_text
                self._record_event(task, "conversation.delta", level="info", payload={"content": response_text})
            messages.append(response)
            for tool_call in response.tool_calls:
                tool_name = str(tool_call.get("name") or "")
                args = tool_call.get("args") if isinstance(tool_call.get("args"), dict) else {}
                call_id = str(tool_call.get("id") or f"call_{len(tool_calls) + 1}")
                tool_calls.append({"name": tool_name, "args": dict(args), "id": call_id})
                result = self.tool_router.execute(agent_task=task, tool_name=tool_name, arguments=dict(args))
                messages.append(ToolMessage(content=result.model_text, tool_call_id=call_id))
        summary = f"Agent turn stopped after {max_steps} tool-calling steps."
        self._record_event(task, "conversation.completed", level="warning", payload={"content": summary})
        return {"ok": True, "recoverable": True, "summary": summary, "response": summary, "tool_calls": tool_calls}

    def _system_prompt(self) -> str:
        return (
            "You are red-code's local CTF Control Center Agent. "
            "Answer normal questions directly. For CTF work, use only the registered high-level tools. "
            "Never request raw bash execution or scan out-of-scope targets. "
            "Terminal commands must be suggestions for operator review."
        )

    def _context_message(self, session: TargetSession) -> str:
        targets = self.tool_router.target_admission_service.list_targets(
            project_identifier=session.project_id,
            limit=20,
        )
        active_targets = [target for target in targets if target.status.value == "active"]
        pending_targets = [target for target in targets if target.status.value == "pending"]
        active_lines = [
            f"- {target.public_id or target.id}: {target.target_type.value} {target.value}"
            for target in active_targets
        ]
        pending_lines = [
            f"- {target.public_id or target.id}: {target.target_type.value} {target.value}"
            for target in pending_targets
        ]
        return (
            f"Active Session: {session.name}\n"
            f"Session summary: {session.summary or '-'}\n"
            f"Active targets:\n{chr(10).join(active_lines) if active_lines else '-'}\n"
            f"Pending targets:\n{chr(10).join(pending_lines) if pending_lines else '-'}\n"
            "Scanner tools require an active Target Pool target_id. "
            "For a new host or URL, call propose_target first and scan only if it is accepted."
        )

    def _record_event(self, task: Task, event_kind: str, *, level: str, payload: dict[str, Any]) -> Event:
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


def _task_result(task: Task, prefix: str) -> AgentToolResult:
    summary = str(task.result_json.get("summary") or task.error or f"{task.task_type} {task.status.value}.")
    text = f"{prefix} {task.public_id} {task.status.value}: {summary}"
    return AgentToolResult(summary=text, model_text=text, data={"task_id": task.id, "public_id": task.public_id, "status": task.status.value})


def _message_text(content: Any) -> str:
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
