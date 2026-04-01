from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Callable

from agent.logger import ColoredOutput, reset_steps
from agent.loop import agent_loop
from agent.settings import Settings, get_settings
from agent.state import SessionState
from app.checkpoint_service import CheckpointService
from app.run_service import RunService
from app.skill_service import SkillService
from app.task_service import TaskService
from models.run import TaskLogEntry
from models.task import Task, TaskStatus
from runtime.task_runner import TaskRunner, apply_result_to_session
from cli.ui import CliPresenter, get_presenter
from skills.registry import SkillRegistry
from tools import build_tool_registry
from tools.executor import ToolExecutor
from utils.confirm import confirm_from_user


OutputFn = Callable[[str], None]
InputFn = Callable[[str], str]
NONE_LABEL = "none"


@dataclass
class ShellState:
    active_task_id: str | None = None
    active_task_public_id: str | None = None
    active_skill_name: str | None = None

    @property
    def active_task_label(self) -> str | None:
        if self.active_task_public_id:
            return self.active_task_public_id
        if self.active_task_id is None:
            return None
        return self.active_task_id[:8]


def create_skill_service(settings: Settings | None = None) -> SkillService:
    settings = settings or get_settings()
    tool_names = list(build_tool_registry().keys())
    registry = SkillRegistry.built_in_and_local(
        known_tool_names=set(tool_names),
        local_root=settings.skills_dir,
    )
    return SkillService(
        registry,
        base_tool_names=tool_names,
        default_task_skill_name=None,
    )


def build_prompt(shell_state: ShellState) -> str:
    if shell_state.active_task_label:
        return f"\ntask:{shell_state.active_task_label} > "
    if shell_state.active_skill_name:
        return f"\nskill:{shell_state.active_skill_name} > "
    return "\n> "


def parse_task_command(command: str) -> tuple[str, list[str]] | None:
    stripped = command.strip()
    if not stripped.startswith("/task"):
        return None

    parts = stripped.split()
    if len(parts) == 1:
        return "", []
    return parts[1], parts[2:]


def parse_skill_command(command: str) -> tuple[str, list[str]] | None:
    stripped = command.strip()
    if not stripped.startswith("/skill"):
        return None

    parts = stripped.split()
    if len(parts) == 1:
        return "", []
    return parts[1], parts[2:]


def parse_help_command(command: str) -> list[str] | None:
    stripped = command.strip()
    if not stripped.startswith("/help"):
        return None

    parts = stripped.split()
    return parts[1:]


def parse_skill_shorthand(
    command: str,
    *,
    skill_service: SkillService,
) -> tuple[str, str] | None:
    stripped = command.strip()
    if not stripped.startswith("/") or stripped.startswith("/skill") or stripped.startswith("/task"):
        return None

    raw_parts = stripped[1:].split(maxsplit=1)
    if not raw_parts:
        return None

    skill_name = raw_parts[0]
    if skill_service.get_skill(skill_name) is None:
        return None

    prompt = raw_parts[1].strip() if len(raw_parts) > 1 else ""
    return skill_name, prompt


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
        ui.show_error("Usage: /help [task|skill]")
        return True

    topic = args[0].lower()
    if topic not in {"task", "skill"}:
        ui.show_error(f"Unknown help topic: {args[0]}. Available topics: task, skill")
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


def handle_skill_command(
    command: str,
    *,
    shell_state: ShellState | None = None,
    skill_service: SkillService | None = None,
    presenter: CliPresenter | None = None,
    text_output: OutputFn | None = None,
    info_output: OutputFn | None = None,
    error_output: OutputFn | None = None,
    success_output: OutputFn | None = None,
) -> bool:
    parsed = parse_skill_command(command)
    if parsed is None:
        return False

    shell_state = shell_state or ShellState()
    skill_service = skill_service or create_skill_service()
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
            ui.show_skill_list(skill_service.list_skills())
            return True

        if action == "show":
            if len(args) != 1:
                ui.show_error("Usage: /skill show <name>")
                return True
            ui.show_skill_detail(skill_service.require_skill(args[0]))
            return True

        if action == "use":
            if len(args) != 1:
                ui.show_error("Usage: /skill use <name>")
                return True
            skill = skill_service.resolve_skill(args[0])
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
            skill_service.reload()
            ui.show_success("Reloaded skills from disk.")
            if previous_skill and skill_service.get_skill(previous_skill) is None:
                shell_state.active_skill_name = None
                ui.show_success(f"cleared missing active skill {previous_skill}")
            return True

        ui.show_error(f"Unknown skill command: {action}")
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


def _parse_task_list_args(args: list[str]) -> tuple[TaskStatus | None, int]:
    if not args:
        return None, 20
    if len(args) == 1:
        try:
            return TaskStatus(args[0].lower()), 20
        except ValueError:
            return None, _parse_limit(args[0])
    if len(args) == 2:
        return TaskStatus(args[0].lower()), _parse_limit(args[1])
    raise ValueError("Usage: /task list [status] [limit]")


def _parse_task_recent_args(args: list[str]) -> int:
    if not args:
        return 20
    if len(args) == 1:
        return _parse_limit(args[0])
    raise ValueError("Usage: /task recent [limit]")


def _parse_task_find_args(args: list[str]) -> tuple[str, int]:
    if not args:
        raise ValueError("Usage: /task find <query> [limit]")
    if len(args) == 1:
        return args[0], 20
    if len(args) == 2:
        return args[0], _parse_limit(args[1])
    raise ValueError("Usage: /task find <query> [limit]")


def _resolve_task_reference(task_service: TaskService, task_ref: str) -> Task | None:
    if task_ref in {"latest", "last"}:
        return task_service.get_latest_task()
    return task_service.get_task(task_ref)


def _build_run_label_map(entries: list[TaskLogEntry], run_service: RunService) -> dict[str, str]:
    labels: dict[str, str] = {}
    for entry in entries:
        if not entry.run_id or entry.run_id in labels:
            continue
        run = run_service.get_run(entry.run_id)
        labels[entry.run_id] = run.public_id if run is not None and run.public_id else entry.run_id[:8]
    return labels


def copy_session_state(target: SessionState, source: SessionState) -> None:
    target.history = list(source.history)
    target.compressed_summary = source.compressed_summary
    target.last_usage = dict(source.last_usage)


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
    try:
        visible_executor = tool_executor.restricted_to(runtime_config.allowed_tools)
    except ValueError:
        if tool_executor.tool_names.isdisjoint(runtime_config.allowed_tools):
            visible_executor = tool_executor
        else:
            raise

    runtime_executor = visible_executor.with_safety_policy(runtime_config.safety_policy)

    try:
        result = await agent_loop(
            question,
            session_state,
            runtime_executor,
            settings,
            system_prompt=runtime_config.system_prompt,
            tools=runtime_executor.get_tools(),
        )
    except TypeError as exc:
        if "unexpected keyword argument 'system_prompt'" not in str(exc):
            raise
        result = await agent_loop(question, session_state, runtime_executor, settings)

    await apply_result_to_session(
        question=question,
        result=result,
        session_state=session_state,
        settings=settings,
        on_info=on_info,
        on_error=on_error,
    )
    return result


def handle_task_command(
    command: str,
    *,
    shell_state: ShellState,
    session_state: SessionState,
    task_service: TaskService,
    run_service: RunService,
    checkpoint_service: CheckpointService | None = None,
    task_runner: TaskRunner,
    skill_service: SkillService | None = None,
    presenter: CliPresenter | None = None,
    text_output: OutputFn | None = None,
    info_output: OutputFn | None = None,
    error_output: OutputFn | None = None,
    success_output: OutputFn | None = None,
    input_func: InputFn = input,
) -> bool:
    parsed = parse_task_command(command)
    if parsed is None:
        return False

    checkpoint_service = checkpoint_service or task_runner.checkpoint_service
    skill_service = skill_service or create_skill_service()
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
            ui.show_help("task")
            return True

        if action == "create":
            title = input_func("Title: ").strip()
            goal = input_func("Goal: ").strip()
            try:
                skill_raw = input_func(f"Skill [{NONE_LABEL}]: ").strip()
            except (EOFError, StopIteration):
                skill_raw = ""
            skill_name = skill_raw or skill_service.default_task_skill_name
            if not title or not goal:
                ui.show_error("Task title and goal are required.")
                return True
            if skill_name is not None:
                skill_service.resolve_skill(skill_name)
            task = task_service.create_task(title=title, goal=goal, skill_profile=skill_name)
            ui.show_success(f"Created task {task.public_id} ({task.id})")
            return True

        if action == "list":
            status, limit = _parse_task_list_args(args)
            tasks = task_service.list_tasks(status=status, limit=limit)
            filter_label = f"Tasks (status: {status.value})" if status is not None else "Tasks"
            ui.show_task_list(tasks, filter_label=filter_label)
            return True

        if action == "recent":
            limit = _parse_task_recent_args(args)
            tasks = task_service.list_tasks(limit=limit)
            ui.show_task_list(tasks, filter_label=f"Recent Tasks ({limit})")
            return True

        if action == "find":
            query, limit = _parse_task_find_args(args)
            tasks = task_service.list_tasks(title_query=query, limit=limit)
            ui.show_task_list(tasks, filter_label=f"Task Search: {query}")
            return True

        if action == "show":
            if len(args) != 1:
                ui.show_error("Usage: /task show <task_id>")
                return True
            task = _resolve_task_reference(task_service, args[0])
            if task is None:
                ui.show_error(f"Task not found: {args[0]}")
                return True
            ui.show_task_detail(task)
            return True

        if action == "status":
            if len(args) != 1:
                ui.show_error("Usage: /task status <task_id>")
                return True
            task = _resolve_task_reference(task_service, args[0])
            if task is None:
                ui.show_error(f"Task not found: {args[0]}")
                return True
            ui.show_task_status(task)
            return True

        if action == "checkpoints":
            if not args or len(args) > 2:
                ui.show_error("Usage: /task checkpoints <task_id> [limit]")
                return True
            task = _resolve_task_reference(task_service, args[0])
            if task is None:
                ui.show_error(f"Task not found: {args[0]}")
                return True
            limit = 20 if len(args) == 1 else _parse_limit(args[1])
            summaries = checkpoint_service.list_checkpoints(task.id, limit=limit)
            run_labels = {}
            for summary in summaries:
                if not summary.run_id or summary.run_id in run_labels:
                    continue
                run = run_service.get_run(summary.run_id)
                run_labels[summary.run_id] = run.public_id if run is not None and run.public_id else summary.run_id[:8]
            ui.show_checkpoint_list(summaries, task, run_labels)
            return True

        if action == "checkpoint":
            if len(args) != 1:
                ui.show_error("Usage: /task checkpoint <checkpoint_id>")
                return True
            summary = checkpoint_service.require_checkpoint_summary(args[0])
            task = task_service.require_task(summary.task_id)
            run = run_service.get_run(summary.run_id) if summary.run_id else None
            run_label = run.public_id if run is not None and run.public_id else None
            ui.show_checkpoint_detail(summary, task, run_label)
            return True

        if action == "runs":
            if not args or len(args) > 2:
                ui.show_error("Usage: /task runs <task_id> [limit]")
                return True
            task = _resolve_task_reference(task_service, args[0])
            if task is None:
                ui.show_error(f"Task not found: {args[0]}")
                return True
            limit = 20 if len(args) == 1 else _parse_limit(args[1])
            runs = run_service.list_runs(task.id, limit=limit)
            ui.show_run_list(runs, task=task)
            return True

        if action == "run":
            if len(args) != 1:
                ui.show_error("Usage: /task run <run_id>")
                return True
            run = run_service.require_run(args[0])
            task = task_service.require_task(run.task_id)
            entries = run_service.list_run_logs(run.id, limit=20)
            ui.show_run_detail(run, task, entries)
            return True

        if action == "logs":
            if not args or len(args) > 2:
                ui.show_error("Usage: /task logs <task_id> [limit]")
                return True
            task = _resolve_task_reference(task_service, args[0])
            if task is None:
                ui.show_error(f"Task not found: {args[0]}")
                return True
            limit = 20 if len(args) == 1 else _parse_limit(args[1])
            entries = run_service.list_logs(task.id, limit=limit)
            ui.show_task_logs(entries, _build_run_label_map(entries, run_service))
            return True

        if action == "resume":
            if len(args) != 1:
                ui.show_error("Usage: /task resume <task_id>")
                return True
            task_ref = args[0]
            if task_ref in {"latest", "last"}:
                latest_task = task_service.get_latest_task()
                if latest_task is None:
                    ui.show_error(f"Task not found: {task_ref}")
                    return True
                task_ref = latest_task.id
            task, restored = task_runner.resume_task(task_ref)
            copy_session_state(session_state, restored)
            shell_state.active_task_id = task.id
            shell_state.active_task_public_id = task.public_id
            ui.show_success(f"Resumed task {task.public_id}: {task.title}")
            return True

        if action == "detach":
            if shell_state.active_task_id is None:
                ui.show_error("No active task is bound to this shell.")
                return True
            task = task_runner.detach_task(shell_state.active_task_id, session_state)
            shell_state.active_task_id = None
            shell_state.active_task_public_id = None
            ui.show_success(f"Detached task {task.public_id} and saved a checkpoint.")
            return True

        if action == "complete":
            if shell_state.active_task_id is None:
                ui.show_error("No active task is bound to this shell.")
                return True
            task = task_runner.complete_task(shell_state.active_task_id, session_state)
            shell_state.active_task_id = None
            shell_state.active_task_public_id = None
            ui.show_success(f"Completed task {task.public_id}.")
            return True

        ui.show_error(f"Unknown task command: {action}")
        return True
    except ValueError as exc:
        ui.show_error(str(exc))
        return True
    except Exception as exc:
        ui.show_error(f"Task command failed: {exc}")
        return True


def pause_active_task_if_needed(
    *,
    shell_state: ShellState,
    session_state: SessionState,
    task_runner: TaskRunner,
    info_output: OutputFn = ColoredOutput.print_info,
    error_output: OutputFn = ColoredOutput.print_error,
) -> None:
    if shell_state.active_task_id is None:
        return

    try:
        task = task_runner.detach_task(shell_state.active_task_id, session_state)
        info_output(f"Paused task {task.public_id} before leaving the current session.")
        shell_state.active_task_id = None
        shell_state.active_task_public_id = None
    except Exception as exc:
        error_output(str(exc))


async def run_interactive_shell(
    *,
    settings: Settings,
    session_state: SessionState,
    shell_state: ShellState,
    tool_executor: ToolExecutor,
    task_service: TaskService,
    run_service: RunService,
    checkpoint_service: CheckpointService | None = None,
    task_runner: TaskRunner,
    skill_service: SkillService,
    input_func: InputFn = input,
) -> None:
    checkpoint_service = checkpoint_service or task_runner.checkpoint_service
    while True:
        try:
            question = input_func(build_prompt(shell_state)).strip()
        except EOFError:
            pause_active_task_if_needed(
                shell_state=shell_state,
                session_state=session_state,
                task_runner=task_runner,
            )
            break

        if question in ("/exit", "/quit"):
            pause_active_task_if_needed(
                shell_state=shell_state,
                session_state=session_state,
                task_runner=task_runner,
            )
            ColoredOutput.print_header("Goodbye")
            break

        if question == "/reset":
            pause_active_task_if_needed(
                shell_state=shell_state,
                session_state=session_state,
                task_runner=task_runner,
            )
            session_state.reset()
            shell_state.active_skill_name = None
            ColoredOutput.print_header("Session reset")
            continue

        if handle_clear_command(
            question,
            shell_state=shell_state,
            session_state=session_state,
        ):
            continue

        if handle_help_command(question):
            continue

        if handle_skill_command(
            question,
            shell_state=shell_state,
            skill_service=skill_service,
        ):
            continue

        if handle_task_command(
            question,
            shell_state=shell_state,
            session_state=session_state,
            task_service=task_service,
            run_service=run_service,
            checkpoint_service=checkpoint_service,
            task_runner=task_runner,
            skill_service=skill_service,
        ):
            continue

        skill_shorthand = parse_skill_shorthand(question, skill_service=skill_service)
        if skill_shorthand is not None:
            skill_name, shorthand_prompt = skill_shorthand
            if not shorthand_prompt:
                ColoredOutput.print_error(f"Usage: /{skill_name} <prompt>")
                continue
            reset_steps()
            try:
                runtime_config = await skill_service.build_skill_runtime_config(
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

        if not question:
            continue

        reset_steps()
        try:
            if shell_state.active_task_id is not None:
                result = await task_runner.run_prompt(
                    task_id=shell_state.active_task_id,
                    question=question,
                    session_state=session_state,
                    tool_executor=tool_executor,
                    settings=settings,
                    on_info=ColoredOutput.print_info,
                    on_error=ColoredOutput.print_error,
                )
            else:
                if shell_state.active_skill_name is None:
                    runtime_config = await skill_service.build_base_runtime_config(
                        context_summary=session_state.context_summary,
                    )
                else:
                    runtime_config = await skill_service.build_skill_runtime_config(
                        skill_name=shell_state.active_skill_name,
                        context_summary=session_state.context_summary,
                    )
                result = await run_prompt_with_runtime(
                    question=question,
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


async def main() -> None:
    settings = get_settings()
    session_state = SessionState()
    shell_state = ShellState()
    task_service = TaskService.from_settings(settings)
    run_service = RunService.from_settings(settings)
    checkpoint_service = CheckpointService.from_settings(settings)
    skill_service = create_skill_service(settings)
    task_runner = TaskRunner(
        task_service,
        run_service,
        skill_service,
        checkpoint_service,
    )
    tool_executor = ToolExecutor(
        build_tool_registry(),
        confirm_command=confirm_from_user,
        on_info=ColoredOutput.print_info,
    )

    await run_interactive_shell(
        settings=settings,
        session_state=session_state,
        shell_state=shell_state,
        tool_executor=tool_executor,
        task_service=task_service,
        run_service=run_service,
        checkpoint_service=checkpoint_service,
        task_runner=task_runner,
        skill_service=skill_service,
    )


if __name__ == "__main__":
    print("red-code 0.1.0 - type /help for available commands")
    asyncio.run(main())
