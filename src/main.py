from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Callable

from agent.logger import ColoredOutput, reset_steps
from agent.loop import agent_loop
from agent.settings import Settings, get_settings
from agent.state import SessionState
from app.run_service import RunService
from app.task_service import TaskService
from models.run import TaskLogEntry
from models.task import Task
from runtime.task_runner import TaskRunner, apply_result_to_session
from tools import build_tool_registry, get_tools
from tools.executor import ToolExecutor
from utils.confirm import confirm_from_user


OutputFn = Callable[[str], None]
InputFn = Callable[[str], str]


@dataclass
class ShellState:
    active_task_id: str | None = None

    @property
    def active_task_short_id(self) -> str | None:
        if self.active_task_id is None:
            return None
        return self.active_task_id[:8]


def build_prompt(shell_state: ShellState) -> str:
    if shell_state.active_task_short_id:
        return f"\ntask:{shell_state.active_task_short_id} > "
    return "\n> "


def parse_task_command(command: str) -> tuple[str, list[str]] | None:
    stripped = command.strip()
    if not stripped.startswith("/task"):
        return None

    parts = stripped.split()
    if len(parts) == 1:
        return "", []
    return parts[1], parts[2:]


def render_task_list(tasks: list[Task]) -> str:
    if not tasks:
        return "No tasks found."

    lines = ["ID       STATUS      UPDATED                  TITLE"]
    for task in tasks:
        lines.append(
            f"{task.id[:8]:8} {task.status.value:11} {task.updated_at:24} {task.title}"
        )
    return "\n".join(lines)


def render_task_detail(task: Task) -> str:
    return "\n".join(
        [
            f"ID: {task.id}",
            f"Title: {task.title}",
            f"Goal: {task.goal}",
            f"Status: {task.status.value}",
            f"Workspace: {task.workspace}",
            f"Created At: {task.created_at}",
            f"Updated At: {task.updated_at}",
            f"Last Checkpoint: {task.last_checkpoint or '-'}",
            f"Last Error: {task.last_error or '-'}",
        ]
    )


def render_task_logs(entries: list[TaskLogEntry]) -> str:
    if not entries:
        return "No task logs found."

    lines = []
    for entry in entries:
        run_part = entry.run_id[:8] if entry.run_id else "-"
        lines.append(
            f"{entry.created_at} [{entry.level.value}] run={run_part} {entry.message}"
        )
    return "\n".join(lines)


def copy_session_state(target: SessionState, source: SessionState) -> None:
    target.history = list(source.history)
    target.compressed_summary = source.compressed_summary
    target.last_usage = dict(source.last_usage)


def print_help(output: OutputFn = print) -> None:
    tools = get_tools()
    output(
        "\n".join(
            [
                "mini-claude-code",
                "",
                "Commands:",
                "/help                 Show help",
                "/reset                Reset the current in-memory session",
                "/exit or /quit        Exit the CLI",
                "/task create          Create a persisted task",
                "/task list            List recent tasks",
                "/task show <id>       Show task details",
                "/task logs <id> [n]   Show recent task logs",
                "/task resume <id>     Resume and bind a task to this shell",
                "/task detach          Pause and detach the active task",
                "/task complete        Mark the active task as completed",
                "",
                "Available tools:",
                str(tools),
            ]
        )
    )


def _default_text_output(text: str) -> None:
    print(text)


def _parse_limit(raw: str) -> int:
    limit = int(raw)
    if limit <= 0:
        raise ValueError("Limit must be greater than 0")
    return limit


def handle_task_command(
    command: str,
    *,
    shell_state: ShellState,
    session_state: SessionState,
    task_service: TaskService,
    run_service: RunService,
    task_runner: TaskRunner,
    text_output: OutputFn = _default_text_output,
    info_output: OutputFn = ColoredOutput.print_info,
    error_output: OutputFn = ColoredOutput.print_error,
    success_output: OutputFn = ColoredOutput.print_success,
    input_func: InputFn = input,
) -> bool:
    parsed = parse_task_command(command)
    if parsed is None:
        return False

    action, args = parsed

    try:
        if action in {"", "help"}:
            text_output(
                "\n".join(
                    [
                        "Task commands:",
                        "/task create",
                        "/task list",
                        "/task show <id>",
                        "/task logs <id> [limit]",
                        "/task resume <id>",
                        "/task detach",
                        "/task complete",
                    ]
                )
            )
            return True

        if action == "create":
            title = input_func("Title: ").strip()
            goal = input_func("Goal: ").strip()
            if not title or not goal:
                error_output("Task title and goal are required.")
                return True
            task = task_service.create_task(title=title, goal=goal)
            success_output(f"Created task {task.id[:8]} ({task.id})")
            return True

        if action == "list":
            tasks = task_service.list_tasks()
            text_output(render_task_list(tasks))
            return True

        if action == "show":
            if len(args) != 1:
                error_output("Usage: /task show <task_id>")
                return True
            task = task_service.get_task(args[0])
            if task is None:
                error_output(f"Task not found: {args[0]}")
                return True
            text_output(render_task_detail(task))
            return True

        if action == "logs":
            if not args or len(args) > 2:
                error_output("Usage: /task logs <task_id> [limit]")
                return True
            limit = 20 if len(args) == 1 else _parse_limit(args[1])
            entries = run_service.list_logs(args[0], limit=limit)
            text_output(render_task_logs(entries))
            return True

        if action == "resume":
            if len(args) != 1:
                error_output("Usage: /task resume <task_id>")
                return True
            task, restored = task_runner.resume_task(args[0])
            copy_session_state(session_state, restored)
            shell_state.active_task_id = task.id
            success_output(f"Resumed task {task.id[:8]}: {task.title}")
            return True

        if action == "detach":
            if shell_state.active_task_id is None:
                error_output("No active task is bound to this shell.")
                return True
            task = task_runner.detach_task(shell_state.active_task_id, session_state)
            shell_state.active_task_id = None
            success_output(f"Detached task {task.id[:8]} and saved a checkpoint.")
            return True

        if action == "complete":
            if shell_state.active_task_id is None:
                error_output("No active task is bound to this shell.")
                return True
            task = task_runner.complete_task(shell_state.active_task_id, session_state)
            shell_state.active_task_id = None
            success_output(f"Completed task {task.id[:8]}.")
            return True

        error_output(f"Unknown task command: {action}")
        return True
    except ValueError as exc:
        error_output(str(exc))
        return True
    except Exception as exc:
        error_output(f"Task command failed: {exc}")
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
        info_output(f"Paused task {task.id[:8]} before leaving the current session.")
        shell_state.active_task_id = None
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
    task_runner: TaskRunner,
    input_func: InputFn = input,
) -> None:
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
            ColoredOutput.print_header("Session reset")
            continue

        if question == "/help":
            print_help()
            continue

        if handle_task_command(
            question,
            shell_state=shell_state,
            session_state=session_state,
            task_service=task_service,
            run_service=run_service,
            task_runner=task_runner,
        ):
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
                result = await agent_loop(
                    question,
                    session_state,
                    tool_executor,
                    settings,
                )
                await apply_result_to_session(
                    question=question,
                    result=result,
                    session_state=session_state,
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
    task_runner = TaskRunner(task_service, run_service)
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
        task_runner=task_runner,
    )


if __name__ == "__main__":
    print("mini-claude-code 0.1.0 - type /help for available commands")
    asyncio.run(main())
