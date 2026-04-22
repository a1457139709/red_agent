from __future__ import annotations

from dataclasses import dataclass

from agent.settings import Settings
from agent.state import SessionState
from app.execution_service import ExecutionService
from app.interaction_port import InteractionOutcome, InteractionPort
from app.skill_service import SkillService
from controller import (
    AgentController,
    ControllerRequest,
    ControllerResultStatus,
    ExecutionBridgeKind,
    parse_record_query_command,
)
from models.conversation_context import ConversationContext
from tools.executor import ToolExecutor


def build_controller_request_from_context(
    *,
    question: str,
    conversation_context: ConversationContext,
) -> ControllerRequest:
    record_query = parse_record_query_command(question)
    return ControllerRequest(
        raw_input=question,
        record_query=record_query,
        active_skill_name=conversation_context.active_skill_name,
        active_session_id=conversation_context.active_session_id,
        active_session_public_id=conversation_context.active_session_public_id,
        active_session_mode=conversation_context.active_session_mode,
        active_session_title=conversation_context.active_session_title,
        active_session_target_summary=conversation_context.active_session_target_summary,
        pending_clarification=conversation_context.pending_clarification,
    )


@dataclass(slots=True)
class SessionInteractionService:
    controller: AgentController
    execution_service: ExecutionService

    @classmethod
    def from_services(
        cls,
        *,
        controller: AgentController,
        execution_service: ExecutionService,
    ) -> "SessionInteractionService":
        return cls(
            controller=controller,
            execution_service=execution_service,
        )

    def build_controller_request(
        self,
        *,
        question: str,
        conversation_context: ConversationContext,
    ) -> ControllerRequest:
        return build_controller_request_from_context(
            question=question,
            conversation_context=conversation_context,
        )

    async def handle_message(
        self,
        *,
        question: str,
        conversation_context: ConversationContext,
        session_state: SessionState,
        skill_service: SkillService,
        tool_executor: ToolExecutor,
        settings: Settings,
        interaction_port: InteractionPort,
    ) -> InteractionOutcome:
        controller_result = self.controller.handle(
            self.build_controller_request(
                question=question,
                conversation_context=conversation_context,
            )
        )

        if controller_result.status == ControllerResultStatus.DELEGATED_TO_ADVANCED_COMMAND:
            conversation_context.clear_pending_clarification()
            return InteractionOutcome(
                conversation_context=conversation_context,
                controller_result=controller_result,
                advanced_command_delegated=True,
            )

        if controller_result.status == ControllerResultStatus.CLARIFICATION_REQUIRED:
            conversation_context.pending_clarification = controller_result.clarification_request
        else:
            conversation_context.clear_pending_clarification()

        if controller_result.bind_session and controller_result.session_summary is not None:
            conversation_context.bind_session(controller_result.session_summary)

        await interaction_port.emit_controller_result(controller_result, conversation_context)

        final_text: str | None = None
        if controller_result.execution_bridge is not None:
            session_identifier = (
                controller_result.session_summary.id
                if controller_result.session_summary is not None
                else conversation_context.active_session_id
            )
            if session_identifier is None:
                message = "Execution bridge is missing an active session binding."
                await interaction_port.emit_interaction_error(message, conversation_context)
                return InteractionOutcome(
                    conversation_context=conversation_context,
                    controller_result=controller_result,
                    error_message=message,
                )

            skill_name = (
                conversation_context.active_skill_name
                if controller_result.execution_bridge.kind == ExecutionBridgeKind.ACTIVE_SKILL_RUNTIME
                else None
            )
            execution_outcome = await self.execution_service.execute_session(
                session_identifier=session_identifier,
                prompt_text=controller_result.execution_bridge.prompt_text,
                session_state=session_state,
                skill_service=skill_service,
                tool_executor=tool_executor,
                settings=settings,
                conversation_context=conversation_context,
                interaction_port=interaction_port,
                skill_name=skill_name,
            )
            final_text = execution_outcome.response
            if execution_outcome.is_completed:
                await interaction_port.emit_final_answer(final_text, conversation_context)
            else:
                message = execution_outcome.error or final_text
                await interaction_port.emit_interaction_error(message, conversation_context)
                return InteractionOutcome(
                    conversation_context=conversation_context,
                    controller_result=controller_result,
                    final_text=final_text,
                    error_message=message,
                )

        return InteractionOutcome(
            conversation_context=conversation_context,
            controller_result=controller_result,
            final_text=final_text,
        )
