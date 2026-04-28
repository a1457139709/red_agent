from __future__ import annotations

import asyncio
from dataclasses import dataclass

from agent.settings import Settings
from agent.state import SessionState
from app.capability_service import CapabilityService
from app.dashboard_service import DashboardService
from app.interaction_port import InteractionPort
from app.report_flow_service import ReportFlowService, ReportFlowResult
from app.session_interaction_service import SessionInteractionService
from app.session_record_query_service import SessionRecordQueryService
from app.session_service import SessionService
from controller.contracts import (
    ConfirmationDecision,
    ConfirmationDecisionValue,
    ConfirmationRequest,
    SessionSummary,
)
from models.conversation_context import ConversationContext
from models.run import utc_now_iso
from tools.executor import ToolExecutor

from .contracts import (
    ConversationMessageResponseDto,
    ConversationSnapshotDto,
    WebEventKind,
)
from .conversation_store import InMemoryConversationStore
from .serialization import (
    serialize_confirmation_decision,
    serialize_confirmation_request,
    serialize_controller_result,
    serialize_dashboard,
    serialize_envelope,
    serialize_execution_progress_event,
    serialize_execution_step,
    serialize_finding,
    serialize_finding_explanation,
    serialize_history_summary,
    serialize_report,
    serialize_artifact,
    serialize_session_summary,
    serialize_conversation_snapshot,
    to_payload,
)


_STREAM_END = object()


@dataclass(slots=True)
class WebInteractionStream:
    conversation: ConversationSnapshotDto
    _queue: asyncio.Queue
    _task: asyncio.Task

    async def receive_event(self):
        event = await self._queue.get()
        if event is _STREAM_END:
            return None
        return event

    async def wait(self) -> ConversationMessageResponseDto:
        return await self._task


class _WebInteractionPort(InteractionPort):
    def __init__(
        self,
        *,
        context: ConversationContext,
        event_queue: asyncio.Queue,
        next_sequence,
        pending_confirmations: dict[str, asyncio.Future[ConfirmationDecision]],
    ) -> None:
        self.context = context
        self.event_queue = event_queue
        self.next_sequence = next_sequence
        self.pending_confirmations = pending_confirmations

    async def _append_event(
        self,
        *,
        event_kind: WebEventKind,
        payload: dict,
        timestamp: str,
        session_id: str | None = None,
        session_public_id: str | None = None,
    ) -> None:
        await self.event_queue.put(
            serialize_envelope(
                conversation_id=self.context.conversation_id,
                sequence=self.next_sequence(self.context.conversation_id),
                event_kind=event_kind.value,
                timestamp=timestamp,
                payload=payload,
                session_id=session_id or self.context.active_session_id,
                session_public_id=session_public_id or self.context.active_session_public_id,
            )
        )

    async def emit_controller_result(self, result, context: ConversationContext) -> None:
        event_kind = (
            WebEventKind.CLARIFICATION_REQUIRED
            if result.status.value == "clarification_required"
            else WebEventKind.CONTROLLER_RESULT
        )
        await self._append_event(
            event_kind=event_kind,
            payload=to_payload(serialize_controller_result(result)),
            timestamp=utc_now_iso(),
            session_id=result.session_summary.id if result.session_summary is not None else context.active_session_id,
            session_public_id=(
                result.session_summary.public_id
                if result.session_summary is not None
                else context.active_session_public_id
            ),
        )

    async def emit_execution_progress(self, event, context: ConversationContext) -> None:
        await self._append_event(
            event_kind=WebEventKind.EXECUTION_PROGRESS,
            payload=serialize_execution_progress_event(event),
            timestamp=event.timestamp,
            session_id=event.session_id,
            session_public_id=event.session_public_id,
        )

    async def emit_final_answer(self, text: str, context: ConversationContext) -> None:
        await self._append_event(
            event_kind=WebEventKind.FINAL_ANSWER,
            payload={"text": text},
            timestamp=utc_now_iso(),
        )

    async def emit_interaction_error(self, message: str, context: ConversationContext) -> None:
        await self._append_event(
            event_kind=WebEventKind.INTERACTION_ERROR,
            payload={"message": message},
            timestamp=utc_now_iso(),
        )

    async def request_confirmation(
        self,
        request: ConfirmationRequest,
        context: ConversationContext,
    ) -> ConfirmationDecision:
        pending = self.pending_confirmations.get(request.request_id)
        if pending is None:
            pending = asyncio.get_running_loop().create_future()
            self.pending_confirmations[request.request_id] = pending
        await self._append_event(
            event_kind=WebEventKind.CONFIRMATION_REQUIRED,
            payload=to_payload(serialize_confirmation_request(request)),
            timestamp=utc_now_iso(),
        )
        try:
            return await asyncio.wait_for(pending, timeout=30.0)
        except asyncio.TimeoutError:
            return ConfirmationDecision(
                request_id=request.request_id,
                decision=ConfirmationDecisionValue.DENY,
            )
        finally:
            self.pending_confirmations.pop(request.request_id, None)

    async def emit_confirmation_resolved(
        self,
        decision: ConfirmationDecision,
        context: ConversationContext,
    ) -> None:
        await self._append_event(
            event_kind=WebEventKind.CONFIRMATION_RESOLVED,
            payload=to_payload(serialize_confirmation_decision(decision)),
            timestamp=utc_now_iso(),
        )


class WebInteractionAdapter:
    def __init__(
        self,
        *,
        interaction_service: SessionInteractionService,
        session_service: SessionService,
        session_record_query_service: SessionRecordQueryService,
        report_flow_service: ReportFlowService,
        dashboard_service: DashboardService,
        conversation_store: InMemoryConversationStore | None = None,
    ) -> None:
        self.interaction_service = interaction_service
        self.session_service = session_service
        self.session_record_query_service = session_record_query_service
        self.report_flow_service = report_flow_service
        self.dashboard_service = dashboard_service
        self.conversation_store = conversation_store or InMemoryConversationStore()
        self._sequence_by_conversation: dict[str, int] = {}
        self._pending_confirmations: dict[str, dict[str, asyncio.Future[ConfirmationDecision]]] = {}

    def _next_sequence(self, conversation_id: str) -> int:
        next_value = self._sequence_by_conversation.get(conversation_id, 0) + 1
        self._sequence_by_conversation[conversation_id] = next_value
        return next_value

    def _confirmation_map(self, conversation_id: str) -> dict[str, asyncio.Future[ConfirmationDecision]]:
        return self._pending_confirmations.setdefault(conversation_id, {})

    def create_conversation(self):
        context = self.conversation_store.create_conversation()
        return serialize_conversation_snapshot(context)

    def get_conversation(self, conversation_id: str):
        return serialize_conversation_snapshot(self.conversation_store.get(conversation_id))

    async def start_message(
        self,
        *,
        conversation_id: str,
        raw_input: str,
        session_state: SessionState,
        tool_executor: ToolExecutor,
        settings: Settings,
        capability_service: CapabilityService,
    ) -> WebInteractionStream:
        context = self.conversation_store.get(conversation_id)
        event_queue: asyncio.Queue = asyncio.Queue()
        interaction_port = _WebInteractionPort(
            context=context,
            event_queue=event_queue,
            next_sequence=self._next_sequence,
            pending_confirmations=self._confirmation_map(conversation_id),
        )
        task = asyncio.create_task(
            self._run_message(
                raw_input=raw_input,
                context=context,
                session_state=session_state,
                capability_service=capability_service,
                tool_executor=tool_executor,
                settings=settings,
                interaction_port=interaction_port,
                event_queue=event_queue,
            )
        )
        return WebInteractionStream(
            conversation=serialize_conversation_snapshot(context),
            _queue=event_queue,
            _task=task,
        )

    async def _run_message(
        self,
        *,
        raw_input: str,
        context: ConversationContext,
        session_state: SessionState,
        capability_service: CapabilityService,
        tool_executor: ToolExecutor,
        settings: Settings,
        interaction_port: _WebInteractionPort,
        event_queue: asyncio.Queue,
    ) -> ConversationMessageResponseDto:
        try:
            outcome = await self.interaction_service.handle_message(
                question=raw_input,
                conversation_context=context,
                session_state=session_state,
                capability_service=capability_service,
                tool_executor=tool_executor,
                settings=settings,
                interaction_port=interaction_port,
            )
            self.conversation_store.save(outcome.conversation_context)
            return ConversationMessageResponseDto(
                conversation=serialize_conversation_snapshot(outcome.conversation_context),
                controller_result=(
                    serialize_controller_result(outcome.controller_result)
                    if outcome.controller_result is not None
                    else None
                ),
                events=[],
                final_text=outcome.final_text,
                error_message=outcome.error_message,
            )
        finally:
            await event_queue.put(_STREAM_END)

    async def handle_message(
        self,
        *,
        conversation_id: str,
        raw_input: str,
        session_state: SessionState,
        tool_executor: ToolExecutor,
        settings: Settings,
        capability_service: CapabilityService,
    ) -> ConversationMessageResponseDto:
        stream = await self.start_message(
            conversation_id=conversation_id,
            raw_input=raw_input,
            session_state=session_state,
            capability_service=capability_service,
            tool_executor=tool_executor,
            settings=settings,
        )
        response = await stream.wait()
        events = []
        while True:
            event = await stream.receive_event()
            if event is None:
                break
            events.append(event)
        return ConversationMessageResponseDto(
            conversation=response.conversation,
            controller_result=response.controller_result,
            events=events,
            final_text=response.final_text,
            error_message=response.error_message,
        )

    def submit_confirmation(
        self,
        *,
        conversation_id: str,
        request_id: str,
        decision: str,
    ):
        decision_model = ConfirmationDecision(
            request_id=request_id,
            decision=ConfirmationDecisionValue(decision),
        )
        pending = self._confirmation_map(conversation_id).get(request_id)
        if pending is None:
            raise ValueError(f"Confirmation request not found: {request_id}")
        if not pending.done():
            pending.set_result(decision_model)
        return serialize_confirmation_decision(decision_model)

    def get_session(self, session_identifier: str):
        session = self.session_service.require_session(session_identifier)
        return serialize_session_summary(
            SessionSummary(
                id=session.id,
                public_id=session.public_id,
                title=session.title,
                mode=session.mode,
                status=session.status,
                target_summary=session.target_summary,
                reused=True,
            )
        )

    def get_session_history(self, session_identifier: str):
        history = self.session_record_query_service.get_history_summary(session_identifier, limit=10)
        return serialize_history_summary(history, scope=session_identifier)

    def get_session_steps(self, session_identifier: str):
        return [
            to_payload(item)
            for item in (
                serialize_execution_step(step)
                for step in self.session_record_query_service.list_execution_steps(session_identifier, limit=50)
            )
        ]

    def get_session_artifacts(self, session_identifier: str):
        return [
            to_payload(serialize_artifact(item))
            for item in self.session_record_query_service.list_artifacts(session_identifier, limit=50)
        ]

    def get_session_findings(self, session_identifier: str):
        return [
            to_payload(serialize_finding(item))
            for item in self.session_record_query_service.list_findings(session_identifier, limit=50)
        ]

    def get_session_reports(self, session_identifier: str):
        return [
            to_payload(serialize_report(item))
            for item in self.session_record_query_service.list_reports(session_identifier, limit=50)
        ]

    def get_finding_explanation(self, session_identifier: str, finding_identifier: str):
        explanation = self.session_record_query_service.explain_finding(
            session_identifier,
            finding_identifier,
        )
        return serialize_finding_explanation(explanation)

    def generate_or_reuse_report(self, session_identifier: str, report_type: str):
        report_flow = {
            "session_summary": self.report_flow_service.get_or_create_session_summary,
            "findings_summary": self.report_flow_service.get_or_create_findings_summary,
            "operator_report": self.report_flow_service.get_or_create_operator_report,
        }
        try:
            builder = report_flow[report_type]
        except KeyError as exc:
            raise ValueError(f"Unsupported report type: {report_type}") from exc
        result: ReportFlowResult = builder(session_identifier)
        return {
            "report_type": report_type,
            "reused": result.reused,
            "report": to_payload(serialize_report(result.report)),
            "linked_artifact_ids": list(result.linked_artifact_ids),
            "linked_finding_ids": list(result.linked_finding_ids),
        }

    def get_session_dashboard(self, session_identifier: str):
        return serialize_dashboard(self.dashboard_service.build_dashboard(session_identifier))
