from __future__ import annotations

from collections.abc import Callable

from agent.context import build_compressed_context, compress_context, should_compress
from agent.loop import agent_loop
from agent.settings import Settings
from agent.state import SessionState
from app.run_service import RunService
from app.skill_service import SkillService
from app.task_service import TaskService
from models.run import TaskLogLevel
from models.task import Task, TaskStatus
from skills.registry import SkillRegistry
from tools import build_tool_registry
from tools.executor import ToolExecutor


InfoCallback = Callable[[str], None] | None


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
    ) -> None:
        self.task_service = task_service
        self.run_service = run_service
        self.skill_service = skill_service or SkillService(
            SkillRegistry.built_in(known_tool_names=set(build_tool_registry().keys()))
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
        self.run_service.write_log(
            task_id=task.id,
            run_id=run.id,
            level=TaskLogLevel.INFO,
            message="run_started",
            payload={"question": question},
        )
        self.task_service.update_task_status(task.id, TaskStatus.RUNNING, last_error=None)

        try:
            runtime_config = await self.skill_service.build_runtime_config(
                skill_name=task.skill_profile,
                context_summary=session_state.context_summary,
            )
            try:
                visible_executor = tool_executor.restricted_to(runtime_config.allowed_tools)
            except ValueError:
                if tool_executor.tool_names.isdisjoint(runtime_config.allowed_tools):
                    visible_executor = tool_executor
                else:
                    raise
            try:
                result = await agent_loop(
                    question,
                    session_state,
                    visible_executor,
                    settings,
                    system_prompt=runtime_config.system_prompt,
                    tools=visible_executor.get_tools(),
                )
            except TypeError as exc:
                if "unexpected keyword argument 'system_prompt'" not in str(exc):
                    raise
                result = await agent_loop(
                    question,
                    session_state,
                    visible_executor,
                    settings,
                )

            await apply_result_to_session(
                question=question,
                result=result,
                session_state=session_state,
                settings=settings,
                on_info=on_info,
                on_error=on_error,
            )

            checkpoint = self.run_service.save_checkpoint(
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
            self.run_service.complete_run(
                run.id,
                step_count=len(result.get("messages", [])),
                last_usage=result.get("usage") or {},
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
                    "step_count": len(result.get("messages", [])),
                    "status": result.get("status", "completed"),
                    "skill_name": runtime_config.skill.manifest.name,
                },
            )
            return result
        except Exception as exc:
            error = str(exc)
            self.run_service.fail_run(run.id, error=error)
            self.task_service.update_task_status(
                task.id,
                TaskStatus.FAILED,
                last_checkpoint=task.last_checkpoint,
                last_error=error,
            )
            self.run_service.write_log(
                task_id=task.id,
                run_id=run.id,
                level=TaskLogLevel.ERROR,
                message="run_failed",
                payload={"error": error},
            )
            raise

    def resume_task(self, task_id: str) -> tuple[Task, SessionState]:
        task = self.task_service.require_task(task_id)
        if task.status in {TaskStatus.COMPLETED, TaskStatus.CANCELLED}:
            raise ValueError(f"Task {task.id} cannot be resumed from status {task.status.value}")
        if task.status not in {TaskStatus.PENDING, TaskStatus.PAUSED, TaskStatus.FAILED}:
            raise ValueError(f"Task {task.id} cannot be resumed from status {task.status.value}")

        self.skill_service.resolve_skill(task.skill_profile)

        if task.last_checkpoint:
            session_state = self.run_service.load_checkpoint_state(task.last_checkpoint)
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
        checkpoint = self.run_service.save_checkpoint(
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
        checkpoint = self.run_service.save_checkpoint(
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
