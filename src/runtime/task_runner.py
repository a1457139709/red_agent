from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from agent.context import build_compressed_context, compress_context, should_compress
from agent.loop import agent_loop
from agent.settings import Settings
from agent.state import SessionState
from app.checkpoint_service import CheckpointService
from app.run_service import RunService
from app.skill_service import SkillService
from app.task_service import TaskService
from models.run import RunFailureKind, TaskLogLevel
from models.task import Task, TaskStatus
from skills.registry import SkillRegistry
from tools import build_tool_registry
from tools.executor import ToolExecutionError, ToolExecutionEvent, ToolExecutor
from tools.policy import SafetyAuditEvent


InfoCallback = Callable[[str], None] | None


@dataclass(slots=True)
class RunObservabilityState:
    effective_skill_name: str | None = None
    effective_tools: list[str] = field(default_factory=list)
    saw_policy_denied: bool = False


async def apply_result_to_session(
    *,
    question: str,
    result: dict,
    session_state: SessionState,
    settings: Settings,
    on_info: InfoCallback = None,
    on_error: InfoCallback = None,
) -> None:
    usage = result.get("usage") or {}

    session_state.append_user_message(question)
    session_state.append_messages(result["messages"])
    session_state.set_usage(usage)

    total_tokens = usage.get("total_tokens")
    if total_tokens is None or not should_compress(total_tokens, settings):
        return

    if on_info is not None:
        on_info("Context window is getting full, compressing session state...")

    try:
        summary = await compress_context(session_state.history, settings)
        hint = build_compressed_context(summary)
        session_state.apply_compressed_summary(hint)
        if on_info is not None:
            on_info("Context compressed. Future prompts will continue from the summary.")
    except Exception as exc:
        if on_error is not None:
            on_error(str(exc))


class TaskRunner:
    def __init__(
        self,
        task_service: TaskService,
        run_service: RunService,
        skill_service: SkillService | None = None,
        checkpoint_service: CheckpointService | None = None,
    ) -> None:
        self.task_service = task_service
        self.run_service = run_service
        self.checkpoint_service = checkpoint_service or CheckpointService.from_settings(run_service.settings)
        self.skill_service = skill_service or SkillService(
            SkillRegistry.built_in(known_tool_names=set(build_tool_registry().keys())),
            base_tool_names=list(build_tool_registry().keys()),
        )

    async def run_prompt(
        self,
        *,
        task_id: str,
        question: str,
        session_state: SessionState,
        tool_executor: ToolExecutor,
        settings: Settings,
        on_info: InfoCallback = None,
        on_error: InfoCallback = None,
    ) -> dict:
        task = self._require_runnable_task(task_id)
        run = self.run_service.start_run(task.id)
        observability = RunObservabilityState()
        self.run_service.write_log(
            task_id=task.id,
            run_id=run.id,
            level=TaskLogLevel.INFO,
            message="run_started",
            payload={"question": question, "run_public_id": run.public_id},
        )
        self.task_service.update_task_status(task.id, TaskStatus.RUNNING, last_error=None)

        runtime_config = None
        try:
            try:
                if task.skill_profile is None:
                    runtime_config = await self.skill_service.build_base_runtime_config(
                        context_summary=session_state.context_summary,
                    )
                else:
                    runtime_config = await self.skill_service.build_skill_runtime_config(
                        skill_name=task.skill_profile,
                        context_summary=session_state.context_summary,
                    )
            except Exception as exc:
                await self._fail_run_and_task(
                    task=task,
                    run_id=run.id,
                    error=str(exc),
                    failure_kind=RunFailureKind.SKILL_RESOLUTION_ERROR,
                    effective_skill_name=task.skill_profile,
                    effective_tools=[],
                )
                raise

            try:
                visible_executor = tool_executor.restricted_to(runtime_config.allowed_tools)
            except ValueError:
                if tool_executor.tool_names.isdisjoint(runtime_config.allowed_tools):
                    visible_executor = tool_executor
                else:
                    await self._fail_run_and_task(
                        task=task,
                        run_id=run.id,
                        error="Visible tool selection failed.",
                        failure_kind=RunFailureKind.RUNTIME_ERROR,
                        effective_skill_name=runtime_config.skill.manifest.name if runtime_config.skill else None,
                        effective_tools=list(runtime_config.allowed_tools),
                    )
                    raise

            observability.effective_skill_name = (
                runtime_config.skill.manifest.name if runtime_config.skill else None
            )
            observability.effective_tools = [tool.name for tool in visible_executor.get_tools()]
            effective_settings = runtime_config.with_settings(settings)
            runtime_executor = visible_executor.with_safety_policy(
                runtime_config.safety_policy,
                on_audit=self._build_safety_audit_logger(task.id, run.id, observability),
                on_tool_event=self._build_tool_event_logger(task.id, run.id),
            )

            try:
                result = await agent_loop(
                    question,
                    session_state,
                    runtime_executor,
                    effective_settings,
                    system_prompt=runtime_config.system_prompt,
                    tools=runtime_executor.get_tools(),
                )
            except TypeError as exc:
                if "unexpected keyword argument 'system_prompt'" not in str(exc):
                    await self._fail_run_and_task(
                        task=task,
                        run_id=run.id,
                        error=str(exc),
                        failure_kind=RunFailureKind.MODEL_ERROR,
                        effective_skill_name=observability.effective_skill_name,
                        effective_tools=observability.effective_tools,
                    )
                    raise
                try:
                    result = await agent_loop(
                        question,
                        session_state,
                        runtime_executor,
                        effective_settings,
                    )
                except ToolExecutionError as exc:
                    await self._fail_run_and_task(
                        task=task,
                        run_id=run.id,
                        error=exc.error,
                        failure_kind=RunFailureKind.TOOL_ERROR,
                        effective_skill_name=observability.effective_skill_name,
                        effective_tools=observability.effective_tools,
                    )
                    raise
                except Exception as inner_exc:
                    await self._fail_run_and_task(
                        task=task,
                        run_id=run.id,
                        error=str(inner_exc),
                        failure_kind=RunFailureKind.MODEL_ERROR,
                        effective_skill_name=observability.effective_skill_name,
                        effective_tools=observability.effective_tools,
                    )
                    raise
            except ToolExecutionError as exc:
                await self._fail_run_and_task(
                    task=task,
                    run_id=run.id,
                    error=exc.error,
                    failure_kind=RunFailureKind.TOOL_ERROR,
                    effective_skill_name=observability.effective_skill_name,
                    effective_tools=observability.effective_tools,
                )
                raise
            except Exception as exc:
                failure_kind = (
                    RunFailureKind.POLICY_DENIED
                    if observability.saw_policy_denied
                    else RunFailureKind.MODEL_ERROR
                )
                await self._fail_run_and_task(
                    task=task,
                    run_id=run.id,
                    error=str(exc),
                    failure_kind=failure_kind,
                    effective_skill_name=observability.effective_skill_name,
                    effective_tools=observability.effective_tools,
                )
                raise

            try:
                await apply_result_to_session(
                    question=question,
                    result=result,
                    session_state=session_state,
                    settings=settings,
                    on_info=on_info,
                    on_error=on_error,
                )

                checkpoint = self.checkpoint_service.save_checkpoint(
                    task_id=task.id,
                    run_id=run.id,
                    session_state=session_state,
                )
                self.task_service.update_task_status(
                    task.id,
                    TaskStatus.RUNNING,
                    last_checkpoint=checkpoint.id,
                    last_error=None,
                )
                failure_kind = (
                    RunFailureKind.MAX_STEPS_EXCEEDED
                    if result.get("status") == "max_steps_exceeded"
                    else None
                )
                self.run_service.complete_run(
                    run.id,
                    step_count=len(result.get("messages", [])),
                    last_usage=result.get("usage") or {},
                    effective_skill_name=observability.effective_skill_name,
                    effective_tools=observability.effective_tools,
                    failure_kind=failure_kind,
                )
                self.run_service.write_log(
                    task_id=task.id,
                    run_id=run.id,
                    level=TaskLogLevel.INFO,
                    message="checkpoint_saved",
                    payload={"checkpoint_id": checkpoint.id, "reason": "run_completed"},
                )
                self.run_service.write_log(
                    task_id=task.id,
                    run_id=run.id,
                    level=TaskLogLevel.INFO,
                    message="run_completed",
                    payload={
                        "run_public_id": run.public_id,
                        "step_count": len(result.get("messages", [])),
                        "status": result.get("status", "completed"),
                        "skill_name": observability.effective_skill_name,
                        "effective_tools": observability.effective_tools,
                        "failure_kind": failure_kind.value if failure_kind else None,
                    },
                )
                return result
            except Exception as exc:
                await self._fail_run_and_task(
                    task=task,
                    run_id=run.id,
                    error=str(exc),
                    failure_kind=RunFailureKind.RUNTIME_ERROR,
                    effective_skill_name=observability.effective_skill_name,
                    effective_tools=observability.effective_tools,
                )
                raise
        except Exception:
            raise

    def resume_task(self, task_id: str) -> tuple[Task, SessionState]:
        task = self.task_service.require_task(task_id)
        if task.status in {TaskStatus.COMPLETED, TaskStatus.CANCELLED}:
            raise ValueError(f"Task {task.id} cannot be resumed from status {task.status.value}")
        if task.status not in {TaskStatus.PENDING, TaskStatus.PAUSED, TaskStatus.FAILED}:
            raise ValueError(f"Task {task.id} cannot be resumed from status {task.status.value}")

        if task.skill_profile is not None:
            self.skill_service.resolve_skill(task.skill_profile)

        if task.last_checkpoint:
            session_state = self.checkpoint_service.load_checkpoint_state(task.last_checkpoint)
        else:
            session_state = SessionState()

        updated = self.task_service.update_task_status(
            task.id,
            TaskStatus.RUNNING,
            last_checkpoint=task.last_checkpoint,
            last_error=None,
        )
        self.run_service.write_log(
            task_id=task.id,
            level=TaskLogLevel.INFO,
            message="task_resumed",
            payload={"from_status": task.status.value},
        )
        return updated, session_state

    def detach_task(self, task_id: str, session_state: SessionState) -> Task:
        task = self.task_service.require_task(task_id)
        checkpoint = self.checkpoint_service.save_checkpoint(
            task_id=task.id,
            session_state=session_state,
        )
        updated = self.task_service.update_task_status(
            task.id,
            TaskStatus.PAUSED,
            last_checkpoint=checkpoint.id,
            last_error=None,
        )
        self.run_service.write_log(
            task_id=task.id,
            level=TaskLogLevel.INFO,
            message="checkpoint_saved",
            payload={"checkpoint_id": checkpoint.id, "reason": "task_detached"},
        )
        self.run_service.write_log(
            task_id=task.id,
            level=TaskLogLevel.INFO,
            message="task_detached",
        )
        return updated

    def complete_task(self, task_id: str, session_state: SessionState) -> Task:
        task = self.task_service.require_task(task_id)
        checkpoint = self.checkpoint_service.save_checkpoint(
            task_id=task.id,
            session_state=session_state,
        )
        updated = self.task_service.update_task_status(
            task.id,
            TaskStatus.COMPLETED,
            last_checkpoint=checkpoint.id,
            last_error=None,
        )
        self.run_service.write_log(
            task_id=task.id,
            level=TaskLogLevel.INFO,
            message="checkpoint_saved",
            payload={"checkpoint_id": checkpoint.id, "reason": "task_completed"},
        )
        self.run_service.write_log(
            task_id=task.id,
            level=TaskLogLevel.INFO,
            message="task_completed",
        )
        return updated

    def _require_runnable_task(self, task_id: str) -> Task:
        task = self.task_service.require_task(task_id)
        if task.status in {TaskStatus.COMPLETED, TaskStatus.CANCELLED}:
            raise ValueError(f"Task {task.id} cannot run in status {task.status.value}")
        return task

    async def _fail_run_and_task(
        self,
        *,
        task: Task,
        run_id: str,
        error: str,
        failure_kind: RunFailureKind,
        effective_skill_name: str | None,
        effective_tools: list[str],
    ) -> None:
        self.run_service.fail_run(
            run_id,
            error=error,
            effective_skill_name=effective_skill_name,
            effective_tools=effective_tools,
            failure_kind=failure_kind,
        )
        self.task_service.update_task_status(
            task.id,
            TaskStatus.FAILED,
            last_checkpoint=task.last_checkpoint,
            last_error=error,
        )
        self.run_service.write_log(
            task_id=task.id,
            run_id=run_id,
            level=TaskLogLevel.ERROR,
            message="run_failed",
            payload={
                "error": error,
                "failure_kind": failure_kind.value,
                "effective_skill_name": effective_skill_name,
                "effective_tools": effective_tools,
            },
        )

    def _build_safety_audit_logger(
        self,
        task_id: str,
        run_id: str,
        observability: RunObservabilityState,
    ):
        def log_event(event: SafetyAuditEvent) -> None:
            if event.event_type == "policy_denied":
                observability.saw_policy_denied = True
            level = (
                TaskLogLevel.ERROR
                if event.event_type in {"operation_blocked", "policy_denied", "operation_failed"}
                else TaskLogLevel.INFO
            )
            self.run_service.write_log(
                task_id=task_id,
                run_id=run_id,
                level=level,
                message=f"safety_{event.event_type}",
                payload=event.to_payload(),
            )

        return log_event

    def _build_tool_event_logger(self, task_id: str, run_id: str):
        def log_event(event: ToolExecutionEvent) -> None:
            level = TaskLogLevel.ERROR if event.event_type == "tool_failed" else TaskLogLevel.INFO
            self.run_service.write_log(
                task_id=task_id,
                run_id=run_id,
                level=level,
                message=event.event_type,
                payload=event.to_payload(),
            )

        return log_event
