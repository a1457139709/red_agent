from __future__ import annotations

import asyncio
import json
from typing import Awaitable, Callable

from agent.logger import ColoredOutput, reset_steps
from agent.loop import agent_loop
from agent.settings import Settings, get_settings
from agent.state import SessionState
from app.artifact_service import ArtifactService
from app.capability_service import CapabilityService
from app.dashboard_service import DashboardService
from app.execution_service import ExecutionService
from app.finding_service import FindingService
from app.interaction_port import InteractionPort
from app.module_service import ModuleService
from app.planner_service import PlannerService
from app.report_service import ReportService
from app.session_interaction_service import (
    SessionInteractionService,
    build_controller_request_from_context,
)
from app.session_service import SessionService
from capabilities.registry import CapabilityRegistry
from controller import (
    AgentController,
    ConfirmationDecision,
    ConfirmationDecisionValue,
    ConfirmationRequest,
    ControllerRequest,
    ControllerResult,
    ControllerResultStatus,
    SessionSummary,
)
from models.artifact import Artifact
from models.conversation_context import ConversationContext
from models.finding import Finding
from models.report import Report
from models.session import SessionMode
from runtime.task_runner import apply_result_to_session
from cli.input import CompletionContext, PromptToolkitInput
from cli.ui import CliPresenter, get_presenter
from tools import build_tool_registry
from tools.executor import ToolExecutor


OutputFn = Callable[[str], None]
InputFn = Callable[[str], str]
AsyncInputFn = Callable[[str], Awaitable[str]]
NONE_LABEL = "none"
RESOURCE_LIST_ACTIONS = {"list", "show", "confirm", "dismiss", "generate", "help"}
STARTUP_BANNER = r"""
 ____  _____ ____        ____ ___  ____  _____
|  _ \| ____|  _ \      / ___/ _ \|  _ \| ____|
| |_) |  _| | | | |____| |  | | | | | | |  _|
|  _ <| |___| |_| |____| |__| |_| | |_| | |___
|_| \_\_____|____/      \____\___/|____/|_____|
"""
STARTUP_INTRO = """RED-CODE 0.1.0
Command-driven local agent for development and bounded redteam workflows.
Use /help for commands.
Use /redteam to enter redteam mode, /normal to return.
Redteam mode: use AI-assisted automated testing, run scoped modules, then inspect findings, artifacts, and reports."""


class ShellState(ConversationContext):
    pass


def format_startup_banner() -> str:
    return f"{STARTUP_BANNER.strip()}\n\n{STARTUP_INTRO}"


def print_startup_banner(output: OutputFn = print) -> None:
    output(format_startup_banner())


def create_capability_service(
    settings: Settings | None = None,
) -> CapabilityService:
    settings = settings or get_settings()
    tool_names = list(build_tool_registry().keys())
    registry = CapabilityRegistry.built_in_and_local(
        known_tool_names=set(tool_names),
        local_root=settings.capabilities_dir,
    )
    return CapabilityService(
        registry,
        base_tool_names=tool_names,
        default_task_skill_name=None,
    )


def create_module_service(
    settings: Settings | None = None,
    *,
    capability_service: CapabilityService | None = None,
) -> ModuleService:
    return ModuleService(capability_service or create_capability_service(settings))


def build_prompt(shell_state: ShellState) -> str:
    mode_label = shell_state.requested_session_mode.value
    if shell_state.active_skill_name:
        session_label = shell_state.active_session_label()
        if session_label and shell_state.active_session_mode == shell_state.requested_session_mode:
            return f"\nskill:{shell_state.active_skill_name} {mode_label}:{session_label} > "
        return f"\nskill:{shell_state.active_skill_name} {mode_label} > "
    session_label = shell_state.active_session_label()
    if session_label and shell_state.active_session_mode == shell_state.requested_session_mode:
        return f"\n{mode_label}:{session_label} > "
    return f"\n{mode_label} > "


def _split_slash_command(command: str, command_name: str) -> list[str] | None:
    stripped = command.strip()
    if stripped != command_name and not stripped.startswith(f"{command_name} "):
        return None
    parts = stripped.split()
    return parts[1:]


def _is_slash_command(command: str, command_name: str) -> bool:
    return _split_slash_command(command, command_name) is not None


def parse_skill_command(command: str) -> tuple[str, list[str]] | None:
    args = _split_slash_command(command, "/skill")
    if args is None:
        return None

    parts = ["/skill", *args]
    if len(parts) == 1:
        return "", []
    return parts[1], parts[2:]


def parse_module_command(command: str) -> tuple[str, list[str]] | None:
    args = _split_slash_command(command, "/module")
    if args is None:
        return None

    parts = ["/module", *command.strip().split(maxsplit=4)[1:]]
    if len(parts) == 1:
        return "", []
    return parts[1], parts[2:]


def parse_job_command(command: str) -> tuple[str, list[str]] | None:
    args = _split_slash_command(command, "/job")
    if args is None:
        return None

    parts = ["/job", *args]
    if len(parts) == 1:
        return "", []
    return parts[1], parts[2:]


def parse_finding_command(command: str) -> tuple[str, list[str]] | None:
    args = _split_slash_command(command, "/findings")
    if args is None:
        return None

    parts = ["/findings", *args]
    if len(parts) == 1:
        return "", []
    return parts[1], parts[2:]


def parse_artifact_command(command: str) -> tuple[str, list[str]] | None:
    args = _split_slash_command(command, "/artifacts")
    if args is None:
        return None

    parts = ["/artifacts", *args]
    if len(parts) == 1:
        return "", []
    return parts[1], parts[2:]


def parse_report_command(command: str) -> tuple[str, list[str]] | None:
    args = _split_slash_command(command, "/reports")
    if args is None:
        return None

    parts = ["/reports", *args]
    if len(parts) == 1:
        return "", []
    return parts[1], parts[2:]


def parse_dashboard_command(command: str) -> list[str] | None:
    return _split_slash_command(command, "/dashboard")


def parse_planner_command(command: str) -> tuple[str, list[str]] | None:
    args = _split_slash_command(command, "/planner")
    if args is None:
        return None

    parts = ["/planner", *args]
    if len(parts) == 1:
        return "", []
    return parts[1], parts[2:]


def parse_help_command(command: str) -> list[str] | None:
    return _split_slash_command(command, "/help")


def parse_redteam_command(command: str) -> list[str] | None:
    return _split_slash_command(command, "/redteam")


def parse_normal_command(command: str) -> list[str] | None:
    return _split_slash_command(command, "/normal")


def parse_skill_shorthand(
    command: str,
    *,
    capability_service: CapabilityService,
) -> tuple[str, str] | None:
    stripped = command.strip()
    # Reserve the built-in slash commands first. Any other `/name ...` form can
    # become a shorthand skill invocation if `name` resolves to a known skill.
    if (
        not stripped.startswith("/")
        or _is_slash_command(stripped, "/skill")
        or _is_slash_command(stripped, "/module")
        or _is_slash_command(stripped, "/job")
        or _is_slash_command(stripped, "/findings")
        or _is_slash_command(stripped, "/artifacts")
        or _is_slash_command(stripped, "/reports")
        or _is_slash_command(stripped, "/dashboard")
        or _is_slash_command(stripped, "/planner")
        or _is_slash_command(stripped, "/redteam")
        or _is_slash_command(stripped, "/normal")
        or _is_slash_command(stripped, "/help")
    ):
        return None

    raw_parts = stripped[1:].split(maxsplit=1)
    if not raw_parts:
        return None

    skill_name = raw_parts[0]
    if capability_service.get_skill(skill_name) is None:
        return None

    prompt = raw_parts[1].strip() if len(raw_parts) > 1 else ""
    return skill_name, prompt


def _confirm_choice(input_func: InputFn, prompt: str) -> bool:
    try:
        response = input_func(prompt).strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    return response in {"y", "yes"}


def _confirm_exit_after_interrupt(input_func: InputFn) -> bool:
    try:
        response = input_func("Exit red-code? [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return True
    return response in {"y", "yes"}


async def _confirm_exit_after_interrupt_async(input_func: AsyncInputFn) -> bool:
    try:
        response = (await input_func("Exit red-code? [y/N]: ")).strip().lower()
    except (EOFError, KeyboardInterrupt):
        return True
    return response in {"y", "yes"}


def _build_callback_presenter(
    *,
    text_output: OutputFn | None = None,
    info_output: OutputFn | None = None,
    error_output: OutputFn | None = None,
    success_output: OutputFn | None = None,
) -> CliPresenter:
    return CliPresenter.for_callbacks(
        text_output=text_output,
        info_output=info_output,
        error_output=error_output,
        success_output=success_output,
    )


def _resolve_presenter(
    presenter: CliPresenter | None = None,
    *,
    text_output: OutputFn | None = None,
    info_output: OutputFn | None = None,
    error_output: OutputFn | None = None,
    success_output: OutputFn | None = None,
) -> CliPresenter:
    if presenter is not None:
        return presenter
    if any(output is not None for output in (text_output, info_output, error_output, success_output)):
        return _build_callback_presenter(
            text_output=text_output,
            info_output=info_output,
            error_output=error_output,
            success_output=success_output,
        )
    return get_presenter()


def print_help(
    output: OutputFn | None = None,
    presenter: CliPresenter | None = None,
    topic: str | None = None,
) -> None:
    ui = _resolve_presenter(presenter, text_output=output)
    ui.show_help(topic)


def handle_help_command(
    command: str,
    *,
    presenter: CliPresenter | None = None,
    text_output: OutputFn | None = None,
    error_output: OutputFn | None = None,
) -> bool:
    args = parse_help_command(command)
    if args is None:
        return False

    ui = _resolve_presenter(
        presenter,
        text_output=text_output,
        error_output=error_output,
    )
    if not args:
        ui.show_help()
        return True
    if len(args) != 1:
        ui.show_error(
            "Usage: /help <topic>\n"
            f"Available topics: {CliPresenter.supported_help_topics_text()}"
        )
        return True

    topic = args[0].lower()
    if not CliPresenter.is_supported_help_topic(topic):
        ui.show_error(
            f"Unknown help topic: {args[0]}.\n"
            f"Available topics: {CliPresenter.supported_help_topics_text()}"
        )
        return True
    ui.show_help(topic)
    return True


def handle_clear_command(
    command: str,
    *,
    shell_state: ShellState,
    session_state: SessionState,
    presenter: CliPresenter | None = None,
    text_output: OutputFn | None = None,
    info_output: OutputFn | None = None,
    error_output: OutputFn | None = None,
    success_output: OutputFn | None = None,
) -> bool:
    if command.strip() != "/clear":
        return False

    session_state.reset()
    if presenter is not None or any(
        output is not None for output in (text_output, info_output, error_output, success_output)
    ):
        _resolve_presenter(
            presenter,
            text_output=text_output,
            info_output=info_output,
            error_output=error_output,
            success_output=success_output,
        ).clear_screen()
    else:
        ColoredOutput.clear_screen()
    return True


def handle_redteam_command(
    command: str,
    *,
    shell_state: ShellState,
    presenter: CliPresenter | None = None,
    text_output: OutputFn | None = None,
    info_output: OutputFn | None = None,
    error_output: OutputFn | None = None,
    success_output: OutputFn | None = None,
) -> bool:
    args = parse_redteam_command(command)
    if args is None:
        return False

    ui = _resolve_presenter(
        presenter,
        text_output=text_output,
        info_output=info_output,
        error_output=error_output,
        success_output=success_output,
    )
    if args:
        ui.show_error("Usage: /redteam")
        return True

    shell_state.set_requested_session_mode(SessionMode.REDTEAM)
    ui.show_success("Switched to redteam mode.")
    return True


def handle_normal_command(
    command: str,
    *,
    shell_state: ShellState,
    presenter: CliPresenter | None = None,
    text_output: OutputFn | None = None,
    info_output: OutputFn | None = None,
    error_output: OutputFn | None = None,
    success_output: OutputFn | None = None,
) -> bool:
    args = parse_normal_command(command)
    if args is None:
        return False

    ui = _resolve_presenter(
        presenter,
        text_output=text_output,
        info_output=info_output,
        error_output=error_output,
        success_output=success_output,
    )
    if args:
        ui.show_error("Usage: /normal")
        return True

    shell_state.set_requested_session_mode(SessionMode.NORMAL)
    ui.show_success("Switched to normal mode.")
    return True


def handle_skill_command(
    command: str,
    *,
    shell_state: ShellState | None = None,
    capability_service: CapabilityService | None = None,
    presenter: CliPresenter | None = None,
    text_output: OutputFn | None = None,
    info_output: OutputFn | None = None,
    error_output: OutputFn | None = None,
    success_output: OutputFn | None = None,
    input_func: InputFn = input,
) -> bool:
    parsed = parse_skill_command(command)
    if parsed is None:
        return False

    shell_state = shell_state or ShellState()
    capability_service = capability_service or create_capability_service()
    ui = _resolve_presenter(
        presenter,
        text_output=text_output,
        info_output=info_output,
        error_output=error_output,
        success_output=success_output,
    )
    action, args = parsed

    try:
        if action in {"", "help"}:
            ui.show_help("skill")
            return True

        if action == "list":
            ui.show_skill_list(capability_service.list_skills())
            return True

        if action == "show":
            if len(args) != 1:
                ui.show_error("Usage: /skill show <name>")
                return True
            ui.show_skill_detail(capability_service.require_skill(args[0]))
            return True

        if action == "use":
            if len(args) != 1:
                ui.show_error("Usage: /skill use <name>")
                return True
            skill = capability_service.require_user_invocable_skill(args[0])
            shell_state.active_skill_name = skill.manifest.name
            ui.show_success(f"Activated skill {skill.manifest.name}.")
            return True

        if action == "clear":
            shell_state.active_skill_name = None
            ui.show_success("Cleared active skill.")
            return True

        if action == "current":
            current_skill = shell_state.active_skill_name or NONE_LABEL
            ui.show_info(f"Current skill: {current_skill}")
            return True

        if action == "reload":
            previous_skill = shell_state.active_skill_name
            capability_service.reload()
            ui.show_success("Reloaded skills from disk.")
            if previous_skill and capability_service.get_skill(previous_skill) is None:
                shell_state.active_skill_name = None
                ui.show_success(f"cleared missing active skill {previous_skill}")
            return True

        ui.show_error(f"Unknown skill command: {action}")
        return True
    except Exception as exc:
        ui.show_error(str(exc))
        return True


async def handle_module_command(
    command: str,
    *,
    shell_state: ShellState,
    session_service: SessionService,
    module_service: ModuleService,
    execution_service: ExecutionService,
    tool_executor: ToolExecutor,
    presenter: CliPresenter | None = None,
    text_output: OutputFn | None = None,
    info_output: OutputFn | None = None,
    error_output: OutputFn | None = None,
    success_output: OutputFn | None = None,
    input_func: InputFn = input,
) -> bool:
    parsed = parse_module_command(command)
    if parsed is None:
        return False

    ui = _resolve_presenter(
        presenter,
        text_output=text_output,
        info_output=info_output,
        error_output=error_output,
        success_output=success_output,
    )
    action, args = parsed

    try:
        if action in {"", "help"}:
            ui.show_help("module")
            return True

        if action == "list":
            ui.show_capability_list(module_service.list_modules(), title="Modules")
            return True

        if action == "show":
            if len(args) != 1:
                ui.show_error("Usage: /module show <name>")
                return True
            ui.show_capability_detail(module_service.require_module(args[0]))
            return True

        if action == "run":
            if len(args) < 2 or len(args) > 3:
                ui.show_error("Usage: /module run <name> <target> [json_overrides]")
                return True
            module_name = args[0]
            parameters = _parse_json_dict(args[2]) if len(args) == 3 else {}
            parameters["target"] = args[1]
            session = None
            one_shot = True
            if shell_state.active_session_public_id and shell_state.active_session_mode == SessionMode.REDTEAM:
                session = session_service.get_session(shell_state.active_session_public_id)
                if session is not None and not session.is_terminal:
                    one_shot = False
            invocation = module_service.prepare_invocation(
                module_name=module_name,
                parameters=parameters,
                mode=SessionMode.REDTEAM,
                one_shot=one_shot,
                session=session,
            )
            reset_steps()
            outcome = await execution_service.execute_module(
                invocation=invocation,
                tool_executor=tool_executor,
                conversation_context=shell_state,
                interaction_port=CliInteractionPort(
                    ui=ui,
                    input_func=input_func,
                ),
            )
            if outcome.is_completed:
                ColoredOutput.print_final_answer(outcome.response)
            else:
                ColoredOutput.print_error(outcome.error or outcome.response)
            return True

        ui.show_error(f"Unknown module command: {action}")
        return True
    except Exception as exc:
        ui.show_error(str(exc))
        return True


def _parse_limit(raw: str) -> int:
    try:
        limit = int(raw)
    except ValueError as exc:
        raise ValueError(f"Invalid limit: {raw}") from exc
    if limit <= 0:
        raise ValueError("Limit must be greater than 0.")
    return limit


def _parse_optional_positive_int(raw: str, *, field_name: str) -> int | None:
    if not raw.strip():
        return None
    value = _parse_limit(raw)
    return value


def _parse_non_negative_int(raw: str, *, field_name: str) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"Invalid {field_name}: {raw}") from exc
    if value < 0:
        raise ValueError(f"{field_name} must be greater than or equal to 0.")
    return value


def _parse_csv_list(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def _parse_ports(raw: str) -> list[int]:
    values: list[int] = []
    for item in _parse_csv_list(raw):
        values.append(_parse_limit(item))
    return values


def _parse_json_dict(raw: str) -> dict:
    text = raw.strip() or "{}"
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON arguments: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise ValueError("Arguments JSON must decode to an object.")
    return value


def _parse_optional_limit_arg(args: list[str], *, usage: str) -> int:
    if not args:
        return 20
    if len(args) == 1:
        return _parse_limit(args[0])
    raise ValueError(usage)


def _looks_like_positive_int(raw: str) -> bool:
    try:
        return int(raw) > 0
    except ValueError:
        return False


def _resolve_resource_scope(
    raw_scope: str | None,
    *,
    shell_state: ShellState,
    session_service: SessionService,
) -> str:
    normalized = raw_scope.strip() if raw_scope else ""
    if not normalized or normalized.lower() == "current":
        identifier = shell_state.active_session_public_id or shell_state.active_session_id
        if identifier is None:
            raise ValueError("No active session. Use current, latest, or a session id like S0001.")
        return identifier
    if normalized.lower() == "latest":
        session = session_service.get_latest_session()
        if session is None:
            raise ValueError("No sessions found.")
        return session.public_id or session.id
    return normalized


def _parse_resource_list_args(
    args: list[str],
    *,
    usage: str,
    shell_state: ShellState,
    session_service: SessionService,
) -> tuple[str, int]:
    if not args:
        return _resolve_resource_scope(None, shell_state=shell_state, session_service=session_service), 20
    if len(args) == 1:
        if _looks_like_positive_int(args[0]):
            return (
                _resolve_resource_scope(None, shell_state=shell_state, session_service=session_service),
                _parse_limit(args[0]),
            )
        return (
            _resolve_resource_scope(args[0], shell_state=shell_state, session_service=session_service),
            20,
        )
    if len(args) == 2:
        return (
            _resolve_resource_scope(args[0], shell_state=shell_state, session_service=session_service),
            _parse_limit(args[1]),
        )
    raise ValueError(usage)


def _parse_selection_indices(raw: str) -> list[int]:
    values: list[int] = []
    seen: set[int] = set()
    for item in _parse_csv_list(raw):
        index = _parse_limit(item)
        if index in seen:
            raise ValueError(f"Duplicate planner proposal index: {index}")
        seen.add(index)
        values.append(index)
    return values


def copy_session_state(target: SessionState, source: SessionState) -> None:
    target.history = list(source.history)
    target.compressed_summary = source.compressed_summary
    target.last_usage = dict(source.last_usage)


def clear_active_session(shell_state: ShellState) -> None:
    shell_state.clear_active_session()


def bind_session_summary(shell_state: ShellState, summary: SessionSummary) -> None:
    shell_state.bind_session(summary)


def build_controller_request(
    *,
    question: str,
    shell_state: ShellState,
) -> ControllerRequest:
    return build_controller_request_from_context(
        question=question,
        conversation_context=shell_state,
    )


def render_controller_result(
    result: ControllerResult,
    *,
    ui: CliPresenter,
) -> None:
    if result.status == ControllerResultStatus.MISSING_FIELDS:
        message = (
            result.missing_field_error.message
            if result.missing_field_error is not None
            else result.message
        )
        if message:
            ui.show_error(message)
        return
    if result.status == ControllerResultStatus.UNSUPPORTED:
        if result.message:
            ui.show_error(result.message)
        return
    if result.status == ControllerResultStatus.DELEGATED_TO_ADVANCED_COMMAND:
        if result.message:
            ui.show_info(result.message)
        return

    if result.generated_report_payload is not None:
        payload = result.generated_report_payload
        if payload.report is not None:
            ui.show_info(
                "\n".join(
                    [
                        f"{'Reused' if payload.reused else 'Generated'} report for session {payload.session_summary.public_id}",
                        f"Report type: {payload.report_type.value}",
                    ]
                )
            )
            ui.show_report_detail(
                payload.report,
                linked_artifact_ids=payload.linked_artifact_ids,
                linked_finding_ids=payload.linked_finding_ids,
            )
            return
        ui.show_info(
            "\n".join(
                [
                    f"Prepared report flow for session {payload.session_summary.public_id}",
                    f"Report type: {payload.report_type.value}",
                    f"Scope: {payload.resolved_scope}",
                ]
            )
        )
        return

    if result.finding_explanation_payload is not None:
        payload = result.finding_explanation_payload
        if payload.explanation is not None:
            explanation = payload.explanation
            lines = [
                f"Finding {explanation.finding.public_id}: {explanation.finding.title}",
                f"Target: {explanation.finding.target_ref}",
                f"Severity: {explanation.finding.severity}",
                f"Status: {explanation.finding.status.value}",
                f"Linked artifacts: {_join_public_ids(explanation.linked_artifacts)}",
                f"Source job: {explanation.source_job.public_id if explanation.source_job is not None else '-'}",
                f"Supporting jobs: {_join_public_ids(explanation.supporting_jobs)}",
                f"Related events: {', '.join(event.event_type.value for event in explanation.related_events) or '-'}",
                f"Related runs: {', '.join(explanation.related_run_ids) or '-'}",
            ]
            if explanation.missing_segments:
                lines.append(f"Incomplete trace: {', '.join(explanation.missing_segments)}")
            ui.show_info("\n".join(lines))
            return
        ui.show_info(
            "\n".join(
                [
                    f"Prepared finding explanation lookup for session {payload.session_summary.public_id}",
                    f"Finding: {payload.finding_identifier}",
                    f"Scope: {payload.resolved_scope}",
                ]
            )
        )
        return

    if result.record_lookup_payload is not None:
        payload = result.record_lookup_payload
        if payload.history_summary is not None:
            history = payload.history_summary
            layer_summary = history.layer_summary
            lines = [
                f"Session {payload.session_summary.public_id}: {payload.session_summary.title}",
                f"Mode: {payload.session_summary.mode.value}",
                f"Status: {payload.session_summary.status.value}",
                f"Scope: {payload.resolved_scope}",
                (
                    "Counts: "
                    f"runs={layer_summary.runs}, logs={layer_summary.logs}, checkpoints={layer_summary.checkpoints}, "
                    f"jobs={layer_summary.jobs}, events={layer_summary.events}, memory={layer_summary.memory_entries}, "
                    f"artifacts={layer_summary.artifacts}, findings={layer_summary.findings}, reports={layer_summary.reports}"
                ),
                f"Recent runs: {_join_public_ids(history.recent_runs)}",
                f"Recent jobs: {_join_public_ids(history.recent_jobs)}",
                f"Recent artifacts: {_join_public_ids(history.recent_artifacts)}",
                f"Recent findings: {_join_public_ids(history.recent_findings)}",
                f"Recent reports: {_join_public_ids(history.recent_reports)}",
            ]
            ui.show_info("\n".join(lines))
            return

        if payload.execution_steps:
            step_lines = [
                (
                    f"{step.occurred_at} | {step.source_type} | {step.title}"
                    + (f" | job={step.job_public_id}" if step.job_public_id else "")
                    + (f" | run={step.run_public_id}" if step.run_public_id else "")
                    + (f" | {step.detail}" if step.detail and step.detail != "-" else "")
                )
                for step in payload.execution_steps
            ]
            ui.show_info(
                "\n".join(
                    [f"Execution steps for session {payload.session_summary.public_id}:"] + step_lines
                )
            )
            return

        if payload.artifacts:
            ui.show_artifact_list(payload.artifacts, session_label=payload.session_summary.public_id)
            return

        if payload.findings:
            ui.show_finding_list(payload.findings, operation_label=payload.session_summary.public_id)
            return

        if payload.reports:
            ui.show_report_list(payload.reports, session_label=payload.session_summary.public_id)
            return

        lines = [
            f"Loaded record lookup for session {payload.session_summary.public_id}",
            f"Kind: {payload.query.kind.value}",
            f"Scope: {payload.resolved_scope}",
        ]
        if payload.query.lookup_identifier:
            lines.append(f"Lookup hint: {payload.query.lookup_identifier}")
        ui.show_info("\n".join(lines))
        return

    if result.session_summary is not None:
        summary = result.session_summary
        session_action = "Reused" if summary.reused else "Started"
        lines = [
            f"{session_action} session {summary.public_id}",
            f"Title: {summary.title}",
            f"Mode: {summary.mode.value}",
            f"Status: {summary.status.value}",
        ]
        if summary.target_summary:
            lines.append(f"Target: {summary.target_summary}")
        ui.show_info("\n".join(lines))
    elif result.message:
        ui.show_info(result.message)


def _join_public_ids(items: list[Artifact | Finding | Report | SessionSummary | object]) -> str:
    labels: list[str] = []
    for item in items:
        label = getattr(item, "public_id", None)
        if label:
            labels.append(str(label))
    return ", ".join(labels) if labels else "-"


async def execute_controller_bridge(
    *,
    result: ControllerResult,
    shell_state: ShellState,
    session_state: SessionState,
    capability_service: CapabilityService,
    module_service: ModuleService,
    tool_executor: ToolExecutor,
    settings: Settings,
    execution_service: ExecutionService,
    ui: CliPresenter,
    input_func: InputFn = input,
) -> None:
    if result.execution_bridge is None:
        return

    if result.execution_bridge.kind == ExecutionBridgeKind.MODULE_RUNTIME:
        if not result.execution_bridge.module_name:
            ui.show_error("Module execution bridge is missing a module name.")
            return
        session = None
        if not result.execution_bridge.module_one_shot:
            session_identifier = (
                result.session_summary.public_id
                if result.session_summary is not None
                else shell_state.active_session_public_id
            )
            if session_identifier is not None:
                session = execution_service.session_service.get_session(
                    session_identifier
                )
        try:
            invocation = module_service.prepare_invocation(
                module_name=result.execution_bridge.module_name,
                parameters=result.execution_bridge.module_parameters,
                mode=SessionMode.REDTEAM,
                one_shot=result.execution_bridge.module_one_shot,
                session=session,
            )
            reset_steps()
            outcome = await execution_service.execute_module(
                invocation=invocation,
                tool_executor=tool_executor,
                conversation_context=shell_state,
                interaction_port=CliInteractionPort(
                    ui=ui,
                    input_func=input_func,
                ),
            )
        except Exception as exc:
            ui.show_error(str(exc))
            return
        if outcome.is_completed:
            ColoredOutput.print_final_answer(outcome.response)
        else:
            ColoredOutput.print_error(outcome.error or outcome.response)
        return

    session_identifier = (
        result.session_summary.id
        if result.session_summary is not None
        else shell_state.active_session_id
    )
    if session_identifier is None:
        ui.show_error("Execution bridge is missing an active session binding.")
        return

    reset_steps()
    await execution_service.execute_session(
        session_identifier=session_identifier,
        prompt_text=result.execution_bridge.prompt_text,
        session_state=session_state,
        capability_service=capability_service,
        tool_executor=tool_executor,
        settings=settings,
        conversation_context=shell_state,
        interaction_port=CliInteractionPort(
            ui=ui,
            input_func=input_func,
        ),
        skill_name=(
            shell_state.active_skill_name
            if result.execution_bridge.kind.value == "active_skill_runtime"
            else None
        ),
        on_info=ColoredOutput.print_info,
        on_error=ColoredOutput.print_error,
    )


def prompt_execution_confirmation(
    *,
    request: ConfirmationRequest,
    input_func: InputFn,
    ui: CliPresenter,
) -> ConfirmationDecision:
    target_summary = request.target_summary or "-"
    prompt = (
        f"Approve action '{request.action_name}' "
        f"(risk: {request.risk_level}, target: {target_summary})? [y/N]: "
    )
    ui.show_info(
        f"Confirmation required: {request.action_name} | risk={request.risk_level} | "
        f"reason={request.reason}"
    )
    try:
        answer = input_func(prompt).strip().lower()
    except (EOFError, KeyboardInterrupt):
        answer = ""
    decision = (
        ConfirmationDecisionValue.APPROVE
        if answer in {"y", "yes"}
        else ConfirmationDecisionValue.DENY
    )
    return ConfirmationDecision(
        request_id=request.request_id,
        decision=decision,
    )


async def prompt_execution_confirmation_async(
    *,
    request: ConfirmationRequest,
    input_func: AsyncInputFn,
    ui: CliPresenter,
) -> ConfirmationDecision:
    target_summary = request.target_summary or "-"
    prompt = (
        f"Approve action '{request.action_name}' "
        f"(risk: {request.risk_level}, target: {target_summary})? [y/N]: "
    )
    ui.show_info(
        f"Confirmation required: {request.action_name} | risk={request.risk_level} | "
        f"reason={request.reason}"
    )
    try:
        answer = (await input_func(prompt)).strip().lower()
    except (EOFError, KeyboardInterrupt):
        answer = ""
    decision = (
        ConfirmationDecisionValue.APPROVE
        if answer in {"y", "yes"}
        else ConfirmationDecisionValue.DENY
    )
    return ConfirmationDecision(
        request_id=request.request_id,
        decision=decision,
    )


class CliInteractionPort(InteractionPort):
    def __init__(
        self,
        *,
        ui: CliPresenter,
        input_func: InputFn = input,
        async_input_func: AsyncInputFn | None = None,
    ) -> None:
        self.ui = ui
        self.input_func = input_func
        self.async_input_func = async_input_func

    async def emit_controller_result(
        self,
        result: ControllerResult,
        context: ConversationContext,
    ) -> None:
        render_controller_result(result, ui=self.ui)

    async def emit_execution_progress(
        self,
        event,
        context: ConversationContext,
    ) -> None:
        self.ui.show_execution_progress(event)

    async def emit_final_answer(
        self,
        text: str,
        context: ConversationContext,
    ) -> None:
        ColoredOutput.print_final_answer(text)

    async def emit_interaction_error(
        self,
        message: str,
        context: ConversationContext,
    ) -> None:
        ColoredOutput.print_error(message)

    async def request_confirmation(
        self,
        request: ConfirmationRequest,
        context: ConversationContext,
    ) -> ConfirmationDecision:
        if self.async_input_func is not None:
            return await prompt_execution_confirmation_async(
                request=request,
                input_func=self.async_input_func,
                ui=self.ui,
            )
        return prompt_execution_confirmation(
            request=request,
            input_func=self.input_func,
            ui=self.ui,
        )

    async def emit_confirmation_resolved(
        self,
        decision: ConfirmationDecision,
        context: ConversationContext,
    ) -> None:
        return None


async def run_prompt_with_runtime(
    *,
    question: str,
    runtime_config,
    session_state: SessionState,
    tool_executor: ToolExecutor,
    settings: Settings,
    on_info: OutputFn | None = None,
    on_error: OutputFn | None = None,
) -> dict:
    effective_settings = runtime_config.with_settings(settings)
    try:
        visible_executor = tool_executor.restricted_to(runtime_config.allowed_tools)
    except ValueError:
        # Some callers inject an executor that is already narrowed and does not
        # expose the runtime's symbolic tool list. If there is no overlap, keep
        # that executor instead of failing at this adapter layer.
        if tool_executor.tool_names.isdisjoint(runtime_config.allowed_tools):
            visible_executor = tool_executor
        else:
            raise

    runtime_executor = visible_executor.with_shell_preference(
        runtime_config.preferred_shell
    ).with_safety_policy(runtime_config.safety_policy)

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
        # Preserve compatibility with older `agent_loop` implementations that do
        # not yet accept the newer runtime injection parameters.
        if "unexpected keyword argument 'system_prompt'" not in str(exc):
            raise
        result = await agent_loop(question, session_state, runtime_executor, effective_settings)

    await apply_result_to_session(
        question=question,
        result=result,
        session_state=session_state,
        settings=settings,
        on_info=on_info,
        on_error=on_error,
    )
    return result


def handle_planner_command(
    command: str,
    *,
    planner_service: PlannerService,
    presenter: CliPresenter | None = None,
    text_output: OutputFn | None = None,
    info_output: OutputFn | None = None,
    error_output: OutputFn | None = None,
    success_output: OutputFn | None = None,
) -> bool:
    parsed = parse_planner_command(command)
    if parsed is None:
        return False

    ui = _resolve_presenter(
        presenter,
        text_output=text_output,
        info_output=info_output,
        error_output=error_output,
        success_output=success_output,
    )
    action, args = parsed

    try:
        if action in {"", "help"}:
            ui.show_help("planner")
            return True

        if action == "plan":
            if len(args) != 1:
                ui.show_error("Usage: /planner plan <session_id>")
                return True
            bundle = planner_service.create_plan(args[0])
            session = planner_service.session_service.require_session(bundle.plan.session_id)
            ui.show_planner_plan(
                plan=bundle.plan,
                operation_label=session.public_id or session.id,
                proposals=bundle.proposals,
                memory_writeback=bundle.memory_writeback,
            )
            return True

        if action == "apply":
            if not args or len(args) > 2:
                ui.show_error("Usage: /planner apply <plan_id> [1,3,...]")
                return True
            selected_indices = None if len(args) == 1 else _parse_selection_indices(args[1])
            result = planner_service.apply_plan(args[0], selected_indices=selected_indices)
            if result.applied_jobs:
                ui.show_success(
                    f"Applied {len(result.applied_jobs)} planner proposal(s) from {result.plan.public_id}."
                )
                session = planner_service.session_service.require_session(result.plan.session_id)
                ui.show_job_list(result.applied_jobs, operation_label=session.public_id or session.id)
            else:
                ui.show_info(f"No planner proposals were applied from {result.plan.public_id}.")
            for proposal in result.skipped_proposals:
                ui.show_info(
                    f"Skipped proposal {proposal.proposal_index or '-'} ({proposal.job_type} {proposal.target_ref}): "
                    f"{proposal.skip_reason or 'not applicable'}"
                )
            return True

        ui.show_error(f"Unknown planner command: {action}")
        return True
    except ValueError as exc:
        ui.show_error(str(exc))
        return True
    except Exception as exc:
        ui.show_error(f"Planner command failed: {exc}")
        return True


def handle_finding_command(
    command: str,
    *,
    finding_service: FindingService,
    shell_state: ShellState,
    presenter: CliPresenter | None = None,
    text_output: OutputFn | None = None,
    info_output: OutputFn | None = None,
    error_output: OutputFn | None = None,
    success_output: OutputFn | None = None,
    input_func: InputFn = input,
) -> bool:
    parsed = parse_finding_command(command)
    if parsed is None:
        return False

    ui = _resolve_presenter(
        presenter,
        text_output=text_output,
        info_output=info_output,
        error_output=error_output,
        success_output=success_output,
    )
    action, args = parsed

    try:
        if action == "help":
            ui.show_help("findings")
            return True

        if action == "" or action == "list" or action not in RESOURCE_LIST_ACTIONS:
            list_args = args if action in {"", "list"} else [action, *args]
            try:
                session_identifier, limit = _parse_resource_list_args(
                    list_args,
                    usage="Usage: /findings list [current|latest|S0001] [limit]",
                    shell_state=shell_state,
                    session_service=finding_service.session_service,
                )
            except ValueError as exc:
                ui.show_error(str(exc))
                return True
            findings = finding_service.list_findings(session_identifier, limit=limit)
            ui.show_finding_list(findings, operation_label=session_identifier)
            return True

        if action == "show":
            if len(args) != 1:
                ui.show_error("Usage: /findings show <finding_id>")
                return True
            finding = finding_service.require_finding(args[0])
            links = finding_service.list_artifact_links_for_finding(finding.id)
            artifact_service = ArtifactService.from_settings(finding_service.settings)
            linked_artifact_ids = [
                artifact_service.require_artifact(link.artifact_id).public_id
                for link in links
            ]
            ui.show_finding_detail(finding, linked_artifact_ids=linked_artifact_ids)
            return True

        if action == "confirm":
            if len(args) != 1:
                ui.show_error("Usage: /findings confirm <finding_id>")
                return True
            finding = finding_service.confirm_finding(args[0])
            ui.show_success(f"Confirmed finding {finding.public_id} ({finding.id})")
            return True

        if action == "dismiss":
            if len(args) != 1:
                ui.show_error("Usage: /findings dismiss <finding_id>")
                return True
            try:
                reason = input_func("Dismissal reason [blank=none]: ").strip()
            except (EOFError, KeyboardInterrupt):
                reason = ""
            finding = finding_service.dismiss_finding(args[0], reason=reason or None)
            ui.show_success(f"Dismissed finding {finding.public_id} ({finding.id})")
            return True

        ui.show_error(f"Unknown findings command: {action}")
        return True
    except ValueError as exc:
        ui.show_error(str(exc))
        return True
    except Exception as exc:
        ui.show_error(f"Finding command failed: {exc}")
        return True


def handle_artifact_command(
    command: str,
    *,
    artifact_service: ArtifactService,
    finding_service: FindingService,
    shell_state: ShellState,
    presenter: CliPresenter | None = None,
    text_output: OutputFn | None = None,
    info_output: OutputFn | None = None,
    error_output: OutputFn | None = None,
    success_output: OutputFn | None = None,
) -> bool:
    parsed = parse_artifact_command(command)
    if parsed is None:
        return False

    ui = _resolve_presenter(
        presenter,
        text_output=text_output,
        info_output=info_output,
        error_output=error_output,
        success_output=success_output,
    )
    action, args = parsed

    try:
        if action == "help":
            ui.show_help("artifacts")
            return True

        if action == "" or action == "list" or action not in RESOURCE_LIST_ACTIONS:
            list_args = args if action in {"", "list"} else [action, *args]
            try:
                session_identifier, limit = _parse_resource_list_args(
                    list_args,
                    usage="Usage: /artifacts list [current|latest|S0001] [limit]",
                    shell_state=shell_state,
                    session_service=artifact_service.session_service,
                )
            except ValueError as exc:
                ui.show_error(str(exc))
                return True
            artifacts = artifact_service.list_artifacts(session_identifier, limit=limit)
            ui.show_artifact_list(artifacts, session_label=session_identifier)
            return True

        if action == "show":
            if len(args) != 1:
                ui.show_error("Usage: /artifacts show <artifact_id>")
                return True
            artifact = artifact_service.require_artifact(args[0])
            links = finding_service.list_finding_links_for_artifact(artifact.id)
            linked_finding_ids = [
                finding_service.require_finding(link.finding_id).public_id
                for link in links
            ]
            ui.show_artifact_detail(artifact, linked_finding_ids=linked_finding_ids)
            return True

        ui.show_error(f"Unknown artifacts command: {action}")
        return True
    except ValueError as exc:
        ui.show_error(str(exc))
        return True
    except Exception as exc:
        ui.show_error(f"Artifact command failed: {exc}")
        return True


def handle_report_command(
    command: str,
    *,
    report_service: ReportService,
    artifact_service: ArtifactService,
    finding_service: FindingService,
    shell_state: ShellState,
    presenter: CliPresenter | None = None,
    text_output: OutputFn | None = None,
    info_output: OutputFn | None = None,
    error_output: OutputFn | None = None,
    success_output: OutputFn | None = None,
) -> bool:
    parsed = parse_report_command(command)
    if parsed is None:
        return False

    ui = _resolve_presenter(
        presenter,
        text_output=text_output,
        info_output=info_output,
        error_output=error_output,
        success_output=success_output,
    )
    action, args = parsed

    try:
        if action == "help":
            ui.show_help("reports")
            return True

        if action == "" or action == "list" or action not in RESOURCE_LIST_ACTIONS:
            list_args = args if action in {"", "list"} else [action, *args]
            try:
                session_identifier, limit = _parse_resource_list_args(
                    list_args,
                    usage="Usage: /reports list [current|latest|S0001] [limit]",
                    shell_state=shell_state,
                    session_service=report_service.session_service,
                )
            except ValueError as exc:
                ui.show_error(str(exc))
                return True
            reports = report_service.list_reports(session_identifier, limit=limit)
            ui.show_report_list(reports, session_label=session_identifier)
            return True

        if action == "show":
            if len(args) != 1:
                ui.show_error("Usage: /reports show <report_id>")
                return True
            report = report_service.require_report(args[0])
            artifact_links = report_service.list_artifact_links(report.id)
            finding_links = report_service.list_finding_links(report.id)
            linked_artifact_ids = [
                artifact_service.require_artifact(link.artifact_id).public_id
                for link in artifact_links
            ]
            linked_finding_ids = [
                finding_service.require_finding(link.finding_id).public_id
                for link in finding_links
            ]
            ui.show_report_detail(
                report,
                linked_artifact_ids=linked_artifact_ids,
                linked_finding_ids=linked_finding_ids,
            )
            return True

        if action == "generate":
            ui.show_error("Usage: /reports generate <session_summary|findings_summary|operator_report> [current|latest|S0001]")
            return True

        ui.show_error(f"Unknown reports command: {action}")
        return True
    except ValueError as exc:
        ui.show_error(str(exc))
        return True
    except Exception as exc:
        ui.show_error(f"Report command failed: {exc}")
        return True

def handle_dashboard_command(
    command: str,
    *,
    dashboard_service: DashboardService,
    presenter: CliPresenter | None = None,
    text_output: OutputFn | None = None,
    info_output: OutputFn | None = None,
    error_output: OutputFn | None = None,
    success_output: OutputFn | None = None,
) -> bool:
    args = parse_dashboard_command(command)
    if args is None:
        return False

    ui = _resolve_presenter(
        presenter,
        text_output=text_output,
        info_output=info_output,
        error_output=error_output,
        success_output=success_output,
    )

    try:
        if len(args) > 1:
            ui.show_error("Usage: /dashboard [session_id]")
            return True
        dashboard = dashboard_service.build_dashboard(args[0] if args else None)
        ui.show_dashboard(dashboard)
        return True
    except ValueError as exc:
        ui.show_error(str(exc))
        return True
    except Exception as exc:
        ui.show_error(f"Dashboard command failed: {exc}")
        return True


async def run_interactive_shell(
    *,
    settings: Settings,
    session_state: SessionState,
    shell_state: ShellState,
    tool_executor: ToolExecutor,
    session_service: SessionService | None = None,
    controller: AgentController | None = None,
    execution_service: ExecutionService | None = None,
    capability_service: CapabilityService | None = None,
    module_service: ModuleService | None = None,
    input_func: InputFn = input,
) -> None:
    session_service = session_service or SessionService.from_settings(settings)
    capability_service = capability_service or create_capability_service(settings)
    module_service = module_service or create_module_service(
        settings,
        capability_service=capability_service,
    )
    controller = controller or AgentController.from_session_service(
        session_service,
        module_names=tuple(capability.manifest.name for capability in module_service.list_modules()),
    )
    execution_service = execution_service or ExecutionService.from_settings(
        settings,
        session_service=session_service,
    )
    interaction_service = SessionInteractionService.from_services(
        controller=controller,
        execution_service=execution_service,
        module_service=module_service,
    )
    planner_service = PlannerService.from_settings(settings)
    finding_service = FindingService.from_settings(settings)
    artifact_service = ArtifactService.from_settings(settings)
    report_service = ReportService.from_settings(settings)
    dashboard_service = DashboardService.from_settings(settings)
    if input_func is input:
        shell_input = PromptToolkitInput(
            CompletionContext(
                settings=settings,
                shell_state=shell_state,
                capability_service=capability_service,
                module_service=module_service,
                session_service=session_service,
                artifact_service=artifact_service,
                finding_service=finding_service,
                report_service=report_service,
                planner_service=planner_service,
            )
        )
        async def command_input(prompt: str) -> str:
            return await shell_input.read_command_async(prompt)

        async def confirm_exit() -> bool:
            return await _confirm_exit_after_interrupt_async(shell_input.read_plain_async)

        plain_input_func = input
        async_plain_input_func = shell_input.read_plain_async
    else:
        async def command_input(prompt: str) -> str:
            return input_func(prompt)

        async def confirm_exit() -> bool:
            return _confirm_exit_after_interrupt(input_func)

        plain_input_func = input_func
        async_plain_input_func = None
    ui = get_presenter()
    interaction_port = CliInteractionPort(
        ui=ui,
        input_func=plain_input_func,
        async_input_func=async_plain_input_func,
    )
    while True:
        try:
            question = (await command_input(build_prompt(shell_state))).strip()
        except EOFError:
            ColoredOutput.print_header("Goodbye")
            break
        except KeyboardInterrupt:
            if await confirm_exit():
                ColoredOutput.print_header("Goodbye")
                break
            continue

        if question in ("/exit", "/quit"):
            ColoredOutput.print_header("Goodbye")
            break

        if question == "/reset":
            session_state.reset()
            shell_state.active_skill_name = None
            shell_state.set_requested_session_mode(SessionMode.NORMAL)
            clear_active_session(shell_state)
            ColoredOutput.print_header("Session reset")
            continue

        if handle_clear_command(
            question,
            shell_state=shell_state,
            session_state=session_state,
        ):
            continue

        if not question:
            continue

        if not question.startswith("/"):
            ui.show_error(f"Unknown command: {question}. Type /help for available commands.")
            continue

        try:
            interaction_outcome = await interaction_service.handle_message(
                question=question,
                conversation_context=shell_state,
                session_state=session_state,
                capability_service=capability_service,
                tool_executor=tool_executor,
                settings=settings,
                interaction_port=interaction_port,
            )

            if interaction_outcome.advanced_command_delegated:
                if handle_help_command(question):
                    continue

                if handle_redteam_command(
                    question,
                    shell_state=shell_state,
                ):
                    continue

                if handle_normal_command(
                    question,
                    shell_state=shell_state,
                ):
                    continue

                if handle_skill_command(
                    question,
                    shell_state=shell_state,
                    capability_service=capability_service,
                    input_func=plain_input_func,
                ):
                    continue

                if await handle_module_command(
                    question,
                    shell_state=shell_state,
                    session_service=session_service,
                    module_service=module_service,
                    execution_service=execution_service,
                    tool_executor=tool_executor,
                    input_func=plain_input_func,
                ):
                    continue

                skill_shorthand = parse_skill_shorthand(
                    question,
                    capability_service=capability_service,
                )
                if skill_shorthand is not None:
                    skill_name, shorthand_prompt = skill_shorthand
                    if not shorthand_prompt:
                        ColoredOutput.print_error(f"Usage: /{skill_name} <prompt>")
                        continue
                    reset_steps()
                    try:
                        runtime_config = await capability_service.build_skill_runtime_config(
                            skill_name=skill_name,
                            context_summary=session_state.context_summary,
                        )
                        result = await run_prompt_with_runtime(
                            question=shorthand_prompt,
                            runtime_config=runtime_config,
                            session_state=session_state,
                            tool_executor=tool_executor,
                            settings=settings,
                            on_info=ColoredOutput.print_info,
                            on_error=ColoredOutput.print_error,
                        )
                        text = result["response"]
                        status = result.get("status", "completed")
                        if status == "completed":
                            ColoredOutput.print_final_answer(text)
                        else:
                            ColoredOutput.print_error(text)
                    except Exception as exc:
                        ColoredOutput.print_error(str(exc))
                    continue

                if handle_finding_command(
                    question,
                    finding_service=finding_service,
                    shell_state=shell_state,
                    input_func=plain_input_func,
                ):
                    continue

                if handle_artifact_command(
                    question,
                    artifact_service=artifact_service,
                    finding_service=finding_service,
                    shell_state=shell_state,
                ):
                    continue

                if handle_report_command(
                    question,
                    report_service=report_service,
                    artifact_service=artifact_service,
                    finding_service=finding_service,
                    shell_state=shell_state,
                ):
                    continue

                if handle_dashboard_command(
                    question,
                    dashboard_service=dashboard_service,
                ):
                    continue

                if handle_planner_command(
                    question,
                    planner_service=planner_service,
                ):
                    continue

                ui.show_error(f"Unknown command: {question}")
                continue
        except Exception as exc:
            ColoredOutput.print_error(str(exc))


async def main() -> None:
    settings = get_settings()
    session_state = SessionState()
    shell_state = ShellState()
    session_service = SessionService.from_settings(settings)
    execution_service = ExecutionService.from_settings(
        settings,
        session_service=session_service,
    )
    capability_service = create_capability_service(settings)
    module_service = create_module_service(settings, capability_service=capability_service)
    controller = AgentController.from_session_service(
        session_service,
        module_names=tuple(capability.manifest.name for capability in module_service.list_modules()),
    )
    tool_executor = ToolExecutor(
        build_tool_registry(),
        on_info=ColoredOutput.print_info,
    )

    await run_interactive_shell(
        settings=settings,
        session_state=session_state,
        shell_state=shell_state,
        tool_executor=tool_executor,
        session_service=session_service,
        controller=controller,
        execution_service=execution_service,
        capability_service=capability_service,
        module_service=module_service,
    )


if __name__ == "__main__":
    print_startup_banner()
    asyncio.run(main())
