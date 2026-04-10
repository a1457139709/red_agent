from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from agent.loop import agent_loop
from agent.settings import Settings
from agent.state import SessionState
from app.skill_service import SkillService
from models.session import Session
from runtime.task_runner import apply_result_to_session
from tools.executor import ToolExecutionError, ToolExecutionEvent, ToolExecutor

from .execution_events import ExecutionEventType, ExecutionOutcome, ExecutionProgressEvent


ProgressCallback = Callable[[ExecutionProgressEvent], None] | None
InfoCallback = Callable[[str], None] | None
AgentLoopFn = Callable[..., Awaitable[dict]]
ApplyResultFn = Callable[..., Awaitable[None]]


@dataclass(slots=True)
class ForegroundRunner:
    agent_loop_fn: AgentLoopFn = agent_loop
    apply_result_to_session_fn: ApplyResultFn = apply_result_to_session

    async def run(
        self,
        *,
        session: Session,
        prompt_text: str,
        session_state: SessionState,
        skill_service: SkillService,
        tool_executor: ToolExecutor,
        settings: Settings,
        skill_name: str | None = None,
        on_progress: ProgressCallback = None,
        on_info: InfoCallback = None,
        on_error: InfoCallback = None,
    ) -> ExecutionOutcome:
        self._emit_event(
            on_progress=on_progress,
            event_type=ExecutionEventType.EXECUTION_STARTED,
            session=session,
            message="Foreground execution started.",
        )

        try:
            if skill_name is None:
                runtime_config = await skill_service.build_base_runtime_config(
                    context_summary=session_state.context_summary,
                )
            else:
                runtime_config = await skill_service.build_skill_runtime_config(
                    skill_name=skill_name,
                    context_summary=session_state.context_summary,
                )
        except asyncio.CancelledError:
            return self._interrupted_outcome(session=session, on_progress=on_progress)
        except Exception as exc:
            return self._failed_outcome(
                session=session,
                on_progress=on_progress,
                error=str(exc),
            )

        try:
            visible_executor = tool_executor.restricted_to(runtime_config.allowed_tools)
        except ValueError:
            if tool_executor.tool_names.isdisjoint(runtime_config.allowed_tools):
                visible_executor = tool_executor
            else:
                return self._failed_outcome(
                    session=session,
                    on_progress=on_progress,
                    error="Visible tool selection failed.",
                )

        runtime_executor = visible_executor.with_shell_preference(
            runtime_config.preferred_shell
        ).with_safety_policy(
            runtime_config.safety_policy,
            on_tool_event=self._build_tool_event_callback(
                session=session,
                on_progress=on_progress,
            ),
        )
        effective_settings = runtime_config.with_settings(settings)

        try:
            result = await self.agent_loop_fn(
                prompt_text,
                session_state,
                runtime_executor,
                effective_settings,
                system_prompt=runtime_config.system_prompt,
                tools=runtime_executor.get_tools(),
            )
        except asyncio.CancelledError:
            return self._interrupted_outcome(session=session, on_progress=on_progress)
        except TypeError as exc:
            if "unexpected keyword argument 'system_prompt'" not in str(exc):
                return self._failed_outcome(
                    session=session,
                    on_progress=on_progress,
                    error=str(exc),
                )
            try:
                result = await self.agent_loop_fn(
                    prompt_text,
                    session_state,
                    runtime_executor,
                    effective_settings,
                )
            except asyncio.CancelledError:
                return self._interrupted_outcome(session=session, on_progress=on_progress)
            except ToolExecutionError as inner_exc:
                return self._failed_outcome(
                    session=session,
                    on_progress=on_progress,
                    error=inner_exc.error,
                )
            except Exception as inner_exc:
                return self._failed_outcome(
                    session=session,
                    on_progress=on_progress,
                    error=str(inner_exc),
                )
        except ToolExecutionError as exc:
            return self._failed_outcome(
                session=session,
                on_progress=on_progress,
                error=exc.error,
            )
        except Exception as exc:
            return self._failed_outcome(
                session=session,
                on_progress=on_progress,
                error=str(exc),
            )

        try:
            await self.apply_result_to_session_fn(
                question=prompt_text,
                result=result,
                session_state=session_state,
                settings=settings,
                on_info=on_info,
                on_error=on_error,
            )
        except asyncio.CancelledError:
            return self._interrupted_outcome(session=session, on_progress=on_progress)
        except Exception as exc:
            return self._failed_outcome(
                session=session,
                on_progress=on_progress,
                error=str(exc),
            )

        status = str(result.get("status", "completed"))
        response = str(result.get("response", ""))
        usage = dict(result.get("usage") or {})
        if status == "completed":
            self._emit_event(
                on_progress=on_progress,
                event_type=ExecutionEventType.EXECUTION_COMPLETED,
                session=session,
                message="Foreground execution completed.",
            )
            return ExecutionOutcome(
                status=status,
                response=response,
                usage=usage,
                raw_result=result,
            )

        error = response or f"Execution ended with status: {status}"
        self._emit_event(
            on_progress=on_progress,
            event_type=ExecutionEventType.EXECUTION_FAILED,
            session=session,
            message=error,
        )
        return ExecutionOutcome(
            status=status,
            response=response,
            error=error,
            usage=usage,
            raw_result=result,
        )

    def _failed_outcome(
        self,
        *,
        session: Session,
        on_progress: ProgressCallback,
        error: str,
    ) -> ExecutionOutcome:
        self._emit_event(
            on_progress=on_progress,
            event_type=ExecutionEventType.EXECUTION_FAILED,
            session=session,
            message=error,
        )
        return ExecutionOutcome(
            status="failed",
            response=error,
            error=error,
            usage={},
            raw_result=None,
        )

    def _interrupted_outcome(
        self,
        *,
        session: Session,
        on_progress: ProgressCallback,
    ) -> ExecutionOutcome:
        message = "Foreground execution was interrupted before completion."
        self._emit_event(
            on_progress=on_progress,
            event_type=ExecutionEventType.EXECUTION_PAUSED,
            session=session,
            message=message,
        )
        return ExecutionOutcome(
            status="paused",
            response=message,
            error=message,
            usage={},
            raw_result=None,
        )

    def _build_tool_event_callback(
        self,
        *,
        session: Session,
        on_progress: ProgressCallback,
    ) -> Callable[[ToolExecutionEvent], None]:
        def emit_tool_event(event: ToolExecutionEvent) -> None:
            if on_progress is None:
                return
            mapped = {
                "tool_invoked": ExecutionEventType.STEP_STARTED,
                "tool_completed": ExecutionEventType.STEP_COMPLETED,
                "tool_failed": ExecutionEventType.STEP_FAILED,
            }.get(event.event_type)
            if mapped is None:
                return
            message = event.error or event.result_summary or event.args_summary
            on_progress(
                ExecutionProgressEvent(
                    event_type=mapped,
                    session_id=session.id,
                    session_public_id=session.public_id,
                    step_type="tool",
                    step_label=event.tool_name,
                    target_summary=session.target_summary,
                    message=message,
                )
            )

        return emit_tool_event

    def _emit_event(
        self,
        *,
        on_progress: ProgressCallback,
        event_type: ExecutionEventType,
        session: Session,
        message: str | None = None,
    ) -> None:
        if on_progress is None:
            return
        on_progress(
            ExecutionProgressEvent(
                event_type=event_type,
                session_id=session.id,
                session_public_id=session.public_id,
                step_type=None,
                step_label=None,
                target_summary=session.target_summary,
                message=message,
            )
        )
