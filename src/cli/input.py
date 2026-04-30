from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from agent.settings import Settings
from app.artifact_service import ArtifactService
from app.capability_service import CapabilityService
from app.finding_service import FindingService
from app.module_service import ModuleService
from app.planner_service import PlannerService
from app.report_service import ReportService
from app.session_service import SessionService
from models.conversation_context import ConversationContext


InputFn = Callable[[str], str]

TOP_LEVEL_SLASH_COMMANDS: tuple[str, ...] = (
    "/help",
    "/redteam",
    "/normal",
    "/module",
    "/skill",
    "/findings",
    "/artifacts",
    "/reports",
    "/dashboard",
    "/planner",
    "/status",
    "/history",
    "/steps",
    "/show",
    "/why",
    "/clear",
    "/reset",
    "/exit",
    "/quit",
)
HELP_TOPICS: tuple[str, ...] = (
    "findings",
    "artifacts",
    "reports",
    "dashboard",
    "planner",
    "skill",
    "module",
)
SCOPE_LABELS: tuple[str, ...] = ("current", "latest")
REPORT_TYPES: tuple[str, ...] = (
    "session_summary",
    "findings_summary",
    "operator_report",
)
SUBCOMMANDS: dict[str, tuple[str, ...]] = {
    "/skill": ("list", "show", "use", "reload", "clear", "current", "help"),
    "/module": ("list", "show", "run", "help"),
    "/findings": ("list", "show", "confirm", "dismiss", "help"),
    "/artifacts": ("list", "show", "help"),
    "/reports": ("list", "show", "generate", "help"),
    "/planner": ("plan", "apply", "help"),
}


@dataclass(slots=True)
class CompletionContext:
    settings: Settings
    shell_state: ConversationContext
    capability_service: CapabilityService
    module_service: ModuleService
    session_service: SessionService
    artifact_service: ArtifactService
    finding_service: FindingService
    report_service: ReportService
    planner_service: PlannerService
    limit: int = 50


@dataclass(frozen=True, slots=True)
class CompletionSuggestion:
    text: str
    start_position: int


def shell_history_path(settings: Settings) -> Path:
    return settings.app_data_dir / "history"


def suggest_command_completions(text: str, context: CompletionContext) -> list[CompletionSuggestion]:
    if not text.startswith("/"):
        return []

    tokens, current = _split_for_completion(text)
    if not tokens and current.startswith("/"):
        return _suggest(current, _top_level_commands(context))
    if not tokens:
        return []

    command = tokens[0]
    arg_index = len(tokens)
    args = tokens[1:]

    if command not in TOP_LEVEL_SLASH_COMMANDS and command not in _skill_shorthand_commands(context):
        if arg_index == 0:
            return _suggest(current, _top_level_commands(context))
        return []

    if arg_index == 0:
        return _suggest(current, _top_level_commands(context))
    if command == "/help":
        return _suggest(current, HELP_TOPICS)
    if command in {"/status", "/history", "/steps", "/dashboard"}:
        return _suggest(current, _session_scopes(context))
    if command == "/show":
        return _suggest(current, _show_identifiers(context))
    if command == "/why":
        return _suggest(current, _finding_ids(context))
    if command == "/skill":
        return _suggest_skill_command(current, args, context)
    if command == "/module":
        return _suggest_module_command(current, args, context)
    if command == "/findings":
        return _suggest_resource_command(
            command=command,
            current=current,
            args=args,
            context=context,
            resource_ids=_finding_ids(context),
        )
    if command == "/artifacts":
        return _suggest_resource_command(
            command=command,
            current=current,
            args=args,
            context=context,
            resource_ids=_artifact_ids(context),
        )
    if command == "/reports":
        return _suggest_reports_command(current, args, context)
    if command == "/planner":
        return _suggest_planner_command(current, args, context)
    return []


class SlashCommandCompleter:
    def __init__(self, context: CompletionContext) -> None:
        self.context = context

    def get_completions(self, document, complete_event):
        from prompt_toolkit.completion import Completion

        for suggestion in suggest_command_completions(document.text_before_cursor, self.context):
            yield Completion(suggestion.text, start_position=suggestion.start_position)

    async def get_completions_async(self, document, complete_event):
        for completion in self.get_completions(document, complete_event):
            yield completion


class PromptToolkitInput:
    def __init__(self, context: CompletionContext) -> None:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
        from prompt_toolkit.history import FileHistory

        history_path = shell_history_path(context.settings)
        history_path.parent.mkdir(parents=True, exist_ok=True)
        self._command_session = PromptSession(
            history=FileHistory(str(history_path)),
            completer=SlashCommandCompleter(context),
            auto_suggest=AutoSuggestFromHistory(),
            complete_while_typing=True,
        )
        self._plain_session = PromptSession()

    def read_command(self, prompt: str) -> str:
        return self._command_session.prompt(prompt)

    async def read_command_async(self, prompt: str) -> str:
        return await self._command_session.prompt_async(prompt)

    def read_plain(self, prompt: str) -> str:
        return self._plain_session.prompt(prompt)

    async def read_plain_async(self, prompt: str) -> str:
        return await self._plain_session.prompt_async(prompt)


def _split_for_completion(text: str) -> tuple[list[str], str]:
    if text.endswith(" "):
        return text.split(), ""
    parts = text.split()
    if not parts:
        return [], text
    return parts[:-1], parts[-1]


def _suggest(prefix: str, candidates: Iterable[str]) -> list[CompletionSuggestion]:
    seen: set[str] = set()
    results: list[CompletionSuggestion] = []
    normalized_prefix = prefix.lower()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        if candidate.lower().startswith(normalized_prefix):
            results.append(
                CompletionSuggestion(
                    text=candidate,
                    start_position=-len(prefix),
                )
            )
            seen.add(candidate)
    return results


def _top_level_commands(context: CompletionContext) -> tuple[str, ...]:
    return (*TOP_LEVEL_SLASH_COMMANDS, *_skill_shorthand_commands(context))


def _skill_shorthand_commands(context: CompletionContext) -> tuple[str, ...]:
    return tuple(f"/{skill.manifest.name}" for skill in context.capability_service.list_skills())


def _suggest_skill_command(
    current: str,
    args: list[str],
    context: CompletionContext,
) -> list[CompletionSuggestion]:
    if len(args) == 0:
        return _suggest(current, SUBCOMMANDS["/skill"])
    if len(args) == 1 and args[0] in {"show", "use"}:
        return _suggest(current, _skill_names(context))
    return []


def _suggest_module_command(
    current: str,
    args: list[str],
    context: CompletionContext,
) -> list[CompletionSuggestion]:
    if len(args) == 0:
        return _suggest(current, SUBCOMMANDS["/module"])
    if len(args) == 1 and args[0] in {"show", "run"}:
        return _suggest(current, _module_names(context))
    return []


def _suggest_resource_command(
    *,
    command: str,
    current: str,
    args: list[str],
    context: CompletionContext,
    resource_ids: tuple[str, ...],
) -> list[CompletionSuggestion]:
    if len(args) == 0:
        return _suggest(current, (*SUBCOMMANDS[command], *_session_scopes(context)))
    action = args[0]
    if len(args) == 1 and action in {"list"}:
        return _suggest(current, _session_scopes(context))
    if len(args) == 1 and action in {"show", "confirm", "dismiss"}:
        return _suggest(current, resource_ids)
    if len(args) == 1 and action not in SUBCOMMANDS[command]:
        return _suggest(current, _session_scopes(context))
    return []


def _suggest_reports_command(
    current: str,
    args: list[str],
    context: CompletionContext,
) -> list[CompletionSuggestion]:
    if len(args) == 0:
        return _suggest(current, (*SUBCOMMANDS["/reports"], *_session_scopes(context)))
    action = args[0]
    if len(args) == 1 and action == "generate":
        return _suggest(current, REPORT_TYPES)
    if len(args) == 2 and action == "generate":
        return _suggest(current, _session_scopes(context))
    if len(args) == 1 and action == "show":
        return _suggest(current, _report_ids(context))
    if len(args) == 1 and action == "list":
        return _suggest(current, _session_scopes(context))
    if len(args) == 1 and action not in SUBCOMMANDS["/reports"]:
        return _suggest(current, _session_scopes(context))
    return []


def _suggest_planner_command(
    current: str,
    args: list[str],
    context: CompletionContext,
) -> list[CompletionSuggestion]:
    if len(args) == 0:
        return _suggest(current, SUBCOMMANDS["/planner"])
    action = args[0]
    if len(args) == 1 and action == "plan":
        return _suggest(current, _session_scopes(context))
    if len(args) == 1 and action == "apply":
        return _suggest(current, _planner_plan_ids(context))
    if len(args) == 2 and action == "apply":
        return _suggest(current, _planner_proposal_indices(context, args[1]))
    return []


def _skill_names(context: CompletionContext) -> tuple[str, ...]:
    return tuple(skill.manifest.name for skill in context.capability_service.list_skills())


def _module_names(context: CompletionContext) -> tuple[str, ...]:
    return tuple(module.manifest.name for module in context.module_service.list_modules())


def _session_scopes(context: CompletionContext) -> tuple[str, ...]:
    return (*SCOPE_LABELS, *_session_ids(context))


def _session_ids(context: CompletionContext) -> tuple[str, ...]:
    sessions = context.session_service.list_sessions(limit=context.limit)
    return tuple(_public_or_internal_id(session) for session in sessions)


def _show_identifiers(context: CompletionContext) -> tuple[str, ...]:
    return (
        *_session_ids(context),
        *_artifact_ids(context),
        *_finding_ids(context),
        *_report_ids(context),
    )


def _artifact_ids(context: CompletionContext) -> tuple[str, ...]:
    values: list[str] = []
    for session_identifier in _completion_session_identifiers(context):
        try:
            values.extend(
                _public_or_internal_id(artifact)
                for artifact in context.artifact_service.list_artifacts(
                    session_identifier,
                    limit=context.limit,
                )
            )
        except ValueError:
            continue
    return tuple(values)


def _finding_ids(context: CompletionContext) -> tuple[str, ...]:
    values: list[str] = []
    for session_identifier in _completion_session_identifiers(context):
        try:
            values.extend(
                _public_or_internal_id(finding)
                for finding in context.finding_service.list_findings(
                    session_identifier,
                    limit=context.limit,
                )
            )
        except ValueError:
            continue
    return tuple(values)


def _report_ids(context: CompletionContext) -> tuple[str, ...]:
    values: list[str] = []
    for session_identifier in _completion_session_identifiers(context):
        try:
            values.extend(
                _public_or_internal_id(report)
                for report in context.report_service.list_reports(
                    session_identifier,
                    limit=context.limit,
                )
            )
        except ValueError:
            continue
    return tuple(values)


def _planner_plan_ids(context: CompletionContext) -> tuple[str, ...]:
    return tuple(
        _public_or_internal_id(plan)
        for plan in context.planner_service.list_plans(limit=context.limit)
    )


def _planner_proposal_indices(
    context: CompletionContext,
    plan_identifier: str,
) -> tuple[str, ...]:
    try:
        bundle = context.planner_service.get_plan_bundle(plan_identifier)
    except ValueError:
        return ()
    return tuple(
        str(proposal.proposal_index)
        for proposal in bundle.proposals
        if proposal.proposal_kind.value == "proposed"
        and proposal.apply_status.value == "pending"
        and proposal.proposal_index is not None
    )


def _completion_session_identifiers(context: CompletionContext) -> tuple[str, ...]:
    identifiers: list[str] = []
    if context.shell_state.active_session_public_id:
        identifiers.append(context.shell_state.active_session_public_id)
    elif context.shell_state.active_session_id:
        identifiers.append(context.shell_state.active_session_id)

    latest = context.session_service.get_latest_session()
    if latest is not None:
        identifiers.append(_public_or_internal_id(latest))

    identifiers.extend(_session_ids(context))
    return tuple(dict.fromkeys(identifiers))


def _public_or_internal_id(value: object) -> str:
    public_id = getattr(value, "public_id", None)
    if public_id:
        return str(public_id)
    return str(getattr(value, "id"))
