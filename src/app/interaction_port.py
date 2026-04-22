from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from controller.contracts import ConfirmationDecision, ConfirmationRequest, ControllerResult
from models.conversation_context import ConversationContext
from runtime.execution_events import ExecutionProgressEvent


class InteractionPort(Protocol):
    def emit_controller_result(
        self,
        result: ControllerResult,
        context: ConversationContext,
    ) -> None:
        ...

    def emit_execution_progress(
        self,
        event: ExecutionProgressEvent,
        context: ConversationContext,
    ) -> None:
        ...

    def emit_final_answer(
        self,
        text: str,
        context: ConversationContext,
    ) -> None:
        ...

    def emit_interaction_error(
        self,
        message: str,
        context: ConversationContext,
    ) -> None:
        ...

    def request_confirmation(
        self,
        request: ConfirmationRequest,
        context: ConversationContext,
    ) -> ConfirmationDecision:
        ...

    def emit_confirmation_resolved(
        self,
        decision: ConfirmationDecision,
        context: ConversationContext,
    ) -> None:
        ...


@dataclass(slots=True)
class InteractionOutcome:
    conversation_context: ConversationContext
    controller_result: ControllerResult | None = None
    advanced_command_delegated: bool = False
    final_text: str | None = None
    error_message: str | None = None
