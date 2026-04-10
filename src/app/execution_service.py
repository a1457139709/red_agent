from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from agent.settings import Settings, get_settings
from agent.state import SessionState
from app.session_service import SessionService
from app.skill_service import SkillService
from models.session import Session, SessionStatus
from runtime.execution_events import ExecutionOutcome, ExecutionProgressEvent
from runtime.foreground_runner import ForegroundRunner
from tools.executor import ToolExecutor


ProgressCallback = Callable[[ExecutionProgressEvent], None] | None
InfoCallback = Callable[[str], None] | None


@dataclass(slots=True)
class ExecutionService:
    session_service: SessionService
    foreground_runner: ForegroundRunner

    @classmethod
    def from_settings(
        cls,
        settings: Settings | None = None,
        *,
        session_service: SessionService | None = None,
        foreground_runner: ForegroundRunner | None = None,
    ) -> "ExecutionService":
        settings = settings or get_settings()
        return cls(
            session_service=session_service or SessionService.from_settings(settings),
            foreground_runner=foreground_runner or ForegroundRunner(),
        )

    async def execute_session(
        self,
        *,
        session_identifier: str,
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
        try:
            session = self.session_service.require_session(session_identifier)
        except Exception as exc:
            return self._failed_outcome(str(exc))

        try:
            session = self._mark_execution_started(session)
        except Exception as exc:
            return self._failed_outcome(str(exc))

        outcome = await self.foreground_runner.run(
            session=session,
            prompt_text=prompt_text,
            session_state=session_state,
            skill_service=skill_service,
            tool_executor=tool_executor,
            settings=settings,
            skill_name=skill_name,
            on_progress=on_progress,
            on_info=on_info,
            on_error=on_error,
        )

        try:
            if outcome.error:
                self.session_service.update_session_status(
                    session.id,
                    SessionStatus.ACTIVE,
                    last_error=outcome.error,
                )
            else:
                self.session_service.update_session_status(
                    session.id,
                    SessionStatus.ACTIVE,
                    last_error=None,
                )
        except Exception:
            # Execution result is still meaningful even if status persistence fails.
            pass

        return outcome

    def _mark_execution_started(self, session: Session) -> Session:
        return self.session_service.update_session_status(
            session.id,
            SessionStatus.ACTIVE,
            last_error=None,
        )

    def _failed_outcome(self, error: str) -> ExecutionOutcome:
        return ExecutionOutcome(
            status="failed",
            response=error,
            error=error,
            usage={},
            raw_result=None,
        )
