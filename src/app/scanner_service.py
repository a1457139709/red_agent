from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json

from agent.settings import Settings, get_settings
from models.control_center import AttackPathNode, Evidence, Task, TaskStatus
from models.run import utc_now_iso
from scanners.contracts import ScanExecutionResult, ScannerArtifact, ScannerAdapter, ToolConfig, ToolStatus
from scanners.process_runner import ProcessRunner, read_version, resolve_binary
from scanners.registry import ScannerRegistry, build_scanner_registry
from storage.project_paths import project_session_artifacts_dir
from storage.repositories.control_center import (
    AttackPathNodeRepository,
    EvidenceRepository,
    ProjectRepository,
    TargetSessionRepository,
    TaskRepository,
)
from storage.sqlite import SQLiteStorage

from .control_center_base import ControlCenterService


TOOL_NAMES = ("nmap", "ffuf", "nuclei")
TOOL_TASK_TYPES = {"nmap": "port_scan", "ffuf": "dir_scan", "nuclei": "poc_scan"}


@dataclass(frozen=True, slots=True)
class ScannerToolConfig:
    tools: dict[str, ToolConfig]

    def for_tool(self, tool_name: str) -> ToolConfig:
        return self.tools.get(tool_name, ToolConfig(name=tool_name))

    def to_dict(self) -> dict[str, Any]:
        return {
            "tools": {
                name: {
                    "binary_path": config.binary_path,
                    "timeout_seconds": config.timeout_seconds,
                    "templates_path": config.templates_path,
                    "default_wordlist": config.default_wordlist,
                    "extra_args": list(config.extra_args),
                }
                for name, config in self.tools.items()
            }
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None = None) -> "ScannerToolConfig":
        payload = payload or {}
        raw_tools = payload.get("tools") if isinstance(payload.get("tools"), dict) else {}
        tools: dict[str, ToolConfig] = {}
        for name in TOOL_NAMES:
            raw = raw_tools.get(name) if isinstance(raw_tools.get(name), dict) else {}
            tools[name] = ToolConfig(
                name=name,
                binary_path=_optional_text(raw.get("binary_path")),
                timeout_seconds=_positive_int(raw.get("timeout_seconds"), default=300),
                templates_path=_optional_text(raw.get("templates_path")),
                default_wordlist=_optional_text(raw.get("default_wordlist")),
                extra_args=_string_list(raw.get("extra_args")),
            )
        return cls(tools=tools)


class ScannerService(ControlCenterService):
    def __init__(
        self,
        *,
        settings: Settings,
        registry: ScannerRegistry | None = None,
        runner: ProcessRunner | None = None,
    ) -> None:
        storage = SQLiteStorage(settings.sqlite_path)
        object.__setattr__(self, "settings", settings)
        object.__setattr__(self, "registry", registry or build_scanner_registry())
        object.__setattr__(self, "runner", runner or ProcessRunner())
        object.__setattr__(self, "project_repository", ProjectRepository(storage))
        object.__setattr__(self, "session_repository", TargetSessionRepository(storage))
        object.__setattr__(self, "task_repository", TaskRepository(storage))
        object.__setattr__(self, "evidence_repository", EvidenceRepository(storage))
        object.__setattr__(self, "attack_path_repository", AttackPathNodeRepository(storage))

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "ScannerService":
        return cls(settings=settings or get_settings())

    @property
    def config_path(self) -> Path:
        return self.settings.config_dir / "scanner-tools.json"

    def get_config(self) -> ScannerToolConfig:
        if not self.config_path.exists():
            return ScannerToolConfig.from_dict()
        return ScannerToolConfig.from_dict(json.loads(self.config_path.read_text(encoding="utf-8")))

    def update_config(self, patch: dict[str, Any]) -> ScannerToolConfig:
        current = self.get_config().to_dict()
        raw_tools = patch.get("tools")
        if not isinstance(raw_tools, dict):
            raise ValueError("tools config patch must include a tools object.")
        current_tools = current.setdefault("tools", {})
        for name, values in raw_tools.items():
            if name not in TOOL_NAMES:
                raise ValueError(f"Unknown scanner tool: {name}")
            if not isinstance(values, dict):
                raise ValueError("tool config values must be objects.")
            tool_config = dict(current_tools.get(name) or {})
            tool_config.update(values)
            current_tools[name] = tool_config
        config = ScannerToolConfig.from_dict(current)
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(json.dumps(config.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return config

    def get_tool_status(self) -> list[ToolStatus]:
        config = self.get_config()
        statuses: list[ToolStatus] = []
        for tool_name in TOOL_NAMES:
            tool_config = config.for_tool(tool_name)
            binary_path = resolve_binary(tool_name, tool_config.binary_path)
            if binary_path is None:
                statuses.append(
                    ToolStatus(
                        name=tool_name,
                        available=False,
                        path=tool_config.binary_path,
                        error=f"{tool_name} binary was not found.",
                    )
                )
                continue
            statuses.append(
                ToolStatus(
                    name=tool_name,
                    available=True,
                    path=binary_path,
                    version=read_version(binary_path),
                )
            )
        return statuses

    def create_scan_task(self, *, session_identifier: str, task_type: str, input_data: dict[str, Any]) -> Task:
        session = self.session_repository.require(session_identifier)
        project = self.project_repository.require(session.project_id)
        adapter = self.registry.require_by_task_type(task_type)
        normalized_input = adapter.validate_input(input_data)
        task = Task.create(
            project_id=project.id,
            session_id=session.id,
            task_type=adapter.task_type,
            executor=adapter.name,
            input_json=normalized_input,
        )
        created = self.task_repository.create(task)
        return self._execute_task(created, adapter=adapter)

    def list_tasks(self, *, session_identifier: str, limit: int | None = 50) -> list[Task]:
        session = self.session_repository.require(session_identifier)
        return self.task_repository.list(session_id=session.id, limit=limit)

    def get_task(self, task_identifier: str) -> Task:
        return self.task_repository.require(task_identifier)

    def cancel_task(self, task_identifier: str) -> Task:
        task = self.task_repository.require(task_identifier)
        if task.status in {TaskStatus.PENDING, TaskStatus.RUNNING}:
            task.status = TaskStatus.CANCELLED
            task.ended_at = utc_now_iso()
            task.error = "Task cancelled."
            task.result_json = {"ok": False, "summary": "Task cancelled.", "error": task.error}
            return self.task_repository.update(task)
        raise ValueError(f"Task cannot be cancelled from status {task.status.value}.")

    def rerun_task(self, task_identifier: str) -> Task:
        task = self.task_repository.require(task_identifier)
        adapter = self.registry.require_by_task_type(task.task_type)
        return self.create_scan_task(
            session_identifier=task.session_id,
            task_type=task.task_type,
            input_data=task.input_json,
        )

    def _execute_task(self, task: Task, *, adapter: ScannerAdapter) -> Task:
        task.status = TaskStatus.RUNNING
        task.started_at = utc_now_iso()
        self.task_repository.update(task)

        try:
            result = self._run_adapter(task, adapter=adapter)
        except Exception as exc:
            result = ScanExecutionResult(
                ok=False,
                argv=[],
                return_code=None,
                stdout_path=None,
                stderr_path=None,
                output_path=None,
                summary=f"{adapter.name} scan failed before execution.",
                structured={},
                error=str(exc),
            )

        task.ended_at = utc_now_iso()
        task.status = TaskStatus.SUCCEEDED if result.ok else TaskStatus.FAILED
        task.error = result.error
        task.result_json = result.to_task_result()
        updated = self.task_repository.update(task)
        if result.ok:
            self._persist_candidates(updated, result)
        return updated

    def _run_adapter(self, task: Task, *, adapter: ScannerAdapter) -> ScanExecutionResult:
        config = self.get_config().for_tool(adapter.name)
        binary_path = resolve_binary(adapter.name, config.binary_path)
        if binary_path is None:
            return ScanExecutionResult(
                ok=False,
                argv=[],
                return_code=None,
                stdout_path=None,
                stderr_path=None,
                output_path=None,
                summary=f"{adapter.name} binary was not found.",
                structured={},
                error=f"{adapter.name} binary was not found. Configure its path in tool settings.",
            )

        work_dir = self._task_work_dir(task)
        stdout_path = work_dir / "stdout.txt"
        stderr_path = work_dir / "stderr.txt"
        output_path = work_dir / adapter.output_filename
        argv = adapter.build_argv(binary_path=binary_path, input_data=task.input_json, output_path=output_path)
        process = self.runner.run(argv=argv, cwd=work_dir, timeout_seconds=config.timeout_seconds)
        stdout_path.write_text(process.stdout, encoding="utf-8")
        stderr_path.write_text(process.stderr, encoding="utf-8")

        if process.return_code != 0:
            return ScanExecutionResult(
                ok=False,
                argv=process.argv,
                return_code=process.return_code,
                stdout_path=str(stdout_path),
                stderr_path=str(stderr_path),
                output_path=str(output_path) if output_path.exists() else None,
                summary=f"{adapter.name} exited with a non-zero status.",
                structured={},
                artifacts=_artifacts(stdout_path, stderr_path, output_path, adapter.output_content_type),
                error=process.stderr.strip() or f"{adapter.name} exited with {process.return_code}.",
            )

        output_text = output_path.read_text(encoding="utf-8") if output_path.exists() else process.stdout
        if not output_path.exists():
            output_path.write_text(output_text, encoding="utf-8")
        structured = adapter.parse_output(output_text)
        evidence, attack_path = adapter.build_evidence(
            input_data=task.input_json,
            structured=structured,
            output_path=output_path,
        )
        return ScanExecutionResult(
            ok=True,
            argv=process.argv,
            return_code=process.return_code,
            stdout_path=str(stdout_path),
            stderr_path=str(stderr_path),
            output_path=str(output_path),
            summary=_summary(adapter.name, structured),
            structured=structured,
            evidence=evidence,
            attack_path=attack_path,
            artifacts=_artifacts(stdout_path, stderr_path, output_path, adapter.output_content_type),
        )

    def _task_work_dir(self, task: Task) -> Path:
        path = project_session_artifacts_dir(
            self.settings,
            project_id=task.project_id,
            session_id=task.session_id,
        ) / "tasks" / task.id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _persist_candidates(self, task: Task, result: ScanExecutionResult) -> None:
        for candidate in result.evidence:
            self.evidence_repository.create(
                Evidence.create(
                    project_id=task.project_id,
                    session_id=task.session_id,
                    source_task_id=task.id,
                    evidence_type=candidate.evidence_type,
                    title=candidate.title,
                    summary=candidate.summary,
                    content_ref=candidate.content_ref,
                    payload=candidate.payload,
                )
            )
        for candidate in result.attack_path:
            self.attack_path_repository.create(
                AttackPathNode.create(
                    project_id=task.project_id,
                    session_id=task.session_id,
                    stage=candidate.stage,
                    title=candidate.title,
                    status=candidate.status,
                    source_ref=candidate.source_ref,
                    next_action=candidate.next_action,
                )
            )


def _artifacts(
    stdout_path: Path,
    stderr_path: Path,
    output_path: Path,
    output_content_type: str,
) -> list[ScannerArtifact]:
    artifacts = [
        ScannerArtifact(kind="stdout", path=str(stdout_path), content_type="text/plain"),
        ScannerArtifact(kind="stderr", path=str(stderr_path), content_type="text/plain"),
    ]
    if output_path.exists():
        artifacts.append(ScannerArtifact(kind="structured_output", path=str(output_path), content_type=output_content_type))
    return artifacts


def _summary(tool_name: str, structured: dict[str, Any]) -> str:
    if tool_name == "nmap":
        return f"nmap found {len(structured.get('open_ports', []))} open port(s)."
    if tool_name == "ffuf":
        return f"ffuf found {len(structured.get('results', []))} path(s)."
    if tool_name == "nuclei":
        return f"nuclei found {len(structured.get('matches', []))} match(es)."
    return f"{tool_name} scan completed."


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _positive_int(value: object, *, default: int) -> int:
    if value in (None, ""):
        return default
    number = int(value)
    if number <= 0:
        raise ValueError("timeout_seconds must be greater than 0.")
    return number


def _string_list(value: object) -> list[str]:
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise ValueError("extra_args must be a list.")
    return [str(item) for item in value if str(item).strip()]
