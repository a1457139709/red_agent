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
from models.checkpoint import CheckpointSummary
from models.run import Run, TaskLogEntry
from models.skill import LoadedSkill
from models.task import Task
from runtime.task_runner import TaskRunner, apply_result_to_session
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


def render_skill_name(skill_name: str | None) -> str:
    return skill_name or NONE_LABEL


def render_task_list(tasks: list[Task]) -> str:
    if not tasks:
        return "No tasks found."

    lines = ["TASK     STATUS      UPDATED                  SKILL                 TITLE"]
    for task in tasks:
        skill_name = render_skill_name(task.skill_profile)
        lines.append(
            f"{task.public_id:8} {task.status.value:11} {task.updated_at:24} {skill_name:21} {task.title}"
        )
    return "\n".join(lines)


def render_task_detail(task: Task) -> str:
    return "\n".join(
        [
            f"Task ID: {task.public_id}",
            f"Internal ID: {task.id}",
            f"Title: {task.title}",
            f"Goal: {task.goal}",
            f"Status: {task.status.value}",
            f"Skill: {render_skill_name(task.skill_profile)}",
            f"Workspace: {task.workspace}",
            f"Created At: {task.created_at}",
            f"Updated At: {task.updated_at}",
            f"Last Checkpoint: {task.last_checkpoint or '-'}",
            f"Last Error: {task.last_error or '-'}",
        ]
    )


def format_duration_ms(duration_ms: int | None) -> str:
    if duration_ms is None:
        return "-"
    if duration_ms < 1000:
        return f"{duration_ms}ms"
    return f"{duration_ms / 1000:.2f}s"


def format_size_bytes(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes}B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f}KB"
    return f"{size_bytes / (1024 * 1024):.1f}MB"


def summarize_log_payload(payload: dict | None) -> str:
    if not payload:
        return ""
    preferred_keys = [
        "tool_name",
        "capability",
        "failure_kind",
        "skill_name",
        "args_summary",
        "result_summary",
        "error",
        "reason",
    ]
    parts = []
    for key in preferred_keys:
        value = payload.get(key)
        if value in (None, "", []):
            continue
        text = str(value)
        if len(text) > 80:
            text = text[:77] + "..."
        parts.append(f"{key}={text}")
    return " | ".join(parts)


def render_task_logs(entries: list[TaskLogEntry], run_labels: dict[str, str] | None = None) -> str:
    if not entries:
        return "No task logs found."

    lines = []
    for entry in entries:
        run_part = "-"
        if entry.run_id:
            run_part = run_labels.get(entry.run_id, entry.run_id[:8]) if run_labels else entry.run_id[:8]
        payload_summary = summarize_log_payload(entry.payload)
        suffix = f" {payload_summary}" if payload_summary else ""
        lines.append(
            f"{entry.created_at} [{entry.level.value}] run={run_part} {entry.message}{suffix}"
        )
    return "\n".join(lines)


def render_run_list(runs: list[Run]) -> str:
    if not runs:
        return "No runs found."

    lines = ["RUN      STATUS      STARTED                  DURATION   SKILL                 FAILURE"]
    for run in runs:
        lines.append(
            f"{run.public_id:8} {run.status.value:11} {run.started_at:24} "
            f"{format_duration_ms(run.duration_ms):10} "
            f"{render_skill_name(run.effective_skill_name):21} {run.failure_kind or '-'}"
        )
    return "\n".join(lines)


def render_run_detail(run: Run, task: Task, entries: list[TaskLogEntry]) -> str:
    task_label = task.public_id or task.id
    lines = [
        f"Run ID: {run.public_id}",
        f"Internal ID: {run.id}",
        f"Task: {task_label}",
        f"Task Internal ID: {task.id}",
        f"Status: {run.status.value}",
        f"Started At: {run.started_at}",
        f"Finished At: {run.finished_at or '-'}",
        f"Duration: {format_duration_ms(run.duration_ms)}",
        f"Skill: {render_skill_name(run.effective_skill_name)}",
        f"Tools: {', '.join(run.effective_tools) if run.effective_tools else '-'}",
        f"Step Count: {run.step_count}",
        f"Usage: {run.last_usage or {}}",
        f"Failure Kind: {run.failure_kind or '-'}",
        f"Last Error: {run.last_error or '-'}",
        "",
        "Recent Run Logs:",
        render_task_logs(entries, {run.id: run.public_id}),
    ]
    return "\n".join(lines)


def render_checkpoint_list(
    summaries: list[CheckpointSummary],
    task: Task,
    run_service: RunService,
) -> str:
    if not summaries:
        return f"No checkpoints found for task {task.public_id}."

    lines = [
        f"Task: {task.public_id}",
        "CHECKPOINT                             CREATED                  STORAGE      SIZE      MSGS   SUMMARY  RUN",
    ]
    for summary in summaries:
        run_label = "-"
        if summary.run_id:
            run = run_service.get_run(summary.run_id)
            run_label = run.public_id if run is not None and run.public_id else summary.run_id[:8]
        lines.append(
            f"{summary.id:36} {summary.created_at:24} {summary.storage_kind:12} "
            f"{format_size_bytes(summary.payload_size_bytes):9} "
            f"{summary.history_message_count:6} "
            f"{'yes' if summary.has_compressed_summary else 'no':8} {run_label}"
        )
    return "\n".join(lines)


def render_checkpoint_detail(
    summary: CheckpointSummary,
    task_service: TaskService,
    run_service: RunService,
) -> str:
    task = task_service.require_task(summary.task_id)
    run = run_service.get_run(summary.run_id) if summary.run_id else None
    run_label = run.public_id if run is not None and run.public_id else "-"
    run_internal_id = run.id if run is not None else (summary.run_id or "-")
    return "\n".join(
        [
            f"Checkpoint ID: {summary.id}",
            f"Task: {task.public_id}",
            f"Task Internal ID: {task.id}",
            f"Run: {run_label}",
            f"Run Internal ID: {run_internal_id}",
            f"Created At: {summary.created_at}",
            f"Storage: {summary.storage_kind}",
            f"Payload Size: {format_size_bytes(summary.payload_size_bytes)}",
            f"History Message Count: {summary.history_message_count}",
            f"History Text Bytes: {summary.history_text_bytes}",
            f"Compressed Summary: {'yes' if summary.has_compressed_summary else 'no'}",
        ]
    )


def render_skill_list(skills: list[LoadedSkill]) -> str:
    if not skills:
        return "No skills found."

    lines = ["NAME                 SOURCE     DESCRIPTION"]
    for skill in skills:
        lines.append(f"{skill.manifest.name:20} {skill.source:10} {skill.manifest.description}")
    return "\n".join(lines)


def render_skill_detail(skill: LoadedSkill) -> str:
    metadata = skill.manifest.metadata or {}
    metadata_lines = (
        [f"  {key}: {value}" for key, value in sorted(metadata.items())]
        if metadata
        else ["  -"]
    )

    return "\n".join(
        [
            f"Name: {skill.manifest.name}",
            f"Description: {skill.manifest.description}",
            f"License: {skill.manifest.license}",
            f"Compatibility: {skill.manifest.compatibility}",
            f"Source: {skill.source}",
            f"Allowed Tools: {', '.join(skill.manifest.allowed_tools)}",
            f"Path: {skill.skill_file}",
            "Metadata:",
            *metadata_lines,
        ]
    )


def copy_session_state(target: SessionState, source: SessionState) -> None:
    target.history = list(source.history)
    target.compressed_summary = source.compressed_summary
    target.last_usage = dict(source.last_usage)


def print_help(output: OutputFn = print) -> None:
    output(
        "\n".join(
            [
                "mini-claude-code",
                "",
                "Base mode:",
                "Normal chat runs with the base prompt and built-in tools.",
                "",
                "Commands:",
                "/help                 Show help",
                "/reset                Reset the current in-memory session and clear the active skill",
                "/exit or /quit        Exit the CLI",
                "/task create          Create a persisted task",
                "/task list            List recent tasks",
                "/task show <id>       Show task details",
                "/task checkpoints <id> [n] Show recent checkpoints for a task",
                "/task checkpoint <id> Show one checkpoint in detail",
                "/task runs <id> [n]   Show recent runs for a task",
                "/task run <id>        Show one run in detail",
                "/task logs <id> [n]   Show recent task logs",
                "/task resume <id>     Resume and bind a task to this shell",
                "/task detach          Pause and detach the active task",
                "/task complete        Mark the active task as completed",
                "/skill list           List built-in and local skills",
                "/skill show <name>    Show skill details",
                "/skill use <name>     Activate a skill for this shell",
                "/skill reload         Reload skills from disk",
                "/skill clear          Clear the active shell skill",
                "/skill current        Show the active shell skill",
                "/skill-name <prompt>  Run one prompt with a skill without activating it",
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


def _build_run_label_map(entries: list[TaskLogEntry], run_service: RunService) -> dict[str, str]:
    labels: dict[str, str] = {}
    for entry in entries:
        if not entry.run_id or entry.run_id in labels:
            continue
        run = run_service.get_run(entry.run_id)
        labels[entry.run_id] = run.public_id if run is not None and run.public_id else entry.run_id[:8]
    return labels


def _select_visible_executor(
    tool_executor: ToolExecutor,
    allowed_tools: list[str],
) -> ToolExecutor:
    try:
        return tool_executor.restricted_to(allowed_tools)
    except ValueError:
        if tool_executor.tool_names.isdisjoint(allowed_tools):
            return tool_executor
        raise


async def run_prompt_with_runtime(
    *,
    question: str,
    runtime_config,
    session_state: SessionState,
    tool_executor: ToolExecutor,
    settings: Settings,
    on_info: OutputFn,
    on_error: OutputFn,
) -> dict:
    visible_executor = _select_visible_executor(tool_executor, runtime_config.allowed_tools)
    runtime_executor = visible_executor.with_safety_policy(runtime_config.safety_policy)
    result = await agent_loop(
        question,
        session_state,
        runtime_executor,
        settings,
        system_prompt=runtime_config.system_prompt,
        tools=runtime_executor.get_tools(),
    )
    await apply_result_to_session(
        question=question,
        result=result,
        session_state=session_state,
        settings=settings,
        on_info=on_info,
        on_error=on_error,
    )
    return result


def handle_skill_command(
    command: str,
    *,
    shell_state: ShellState | None = None,
    skill_service: SkillService | None = None,
    text_output: OutputFn = _default_text_output,
    error_output: OutputFn = ColoredOutput.print_error,
    success_output: OutputFn = ColoredOutput.print_success,
) -> bool:
    parsed = parse_skill_command(command)
    if parsed is None:
        return False

    shell_state = shell_state or ShellState()
    skill_service = skill_service or create_skill_service()
    action, args = parsed

    try:
        if action in {"", "help"}:
            text_output(
                "\n".join(
                    [
                        "Skill commands:",
                        "/skill list",
                        "/skill show <name>",
                        "/skill use <name>",
                        "/skill reload",
                        "/skill clear",
                        "/skill current",
                    ]
                )
            )
            return True

        if action == "list":
            text_output(render_skill_list(skill_service.list_skills()))
            return True

        if action == "show":
            if len(args) != 1:
                error_output("Usage: /skill show <name>")
                return True
            skill = skill_service.get_skill(args[0])
            if skill is None:
                error_output(f"Skill not found: {args[0]}")
                return True
            text_output(render_skill_detail(skill))
            return True

        if action == "use":
            if len(args) != 1:
                error_output("Usage: /skill use <name>")
                return True
            skill_service.resolve_skill(args[0])
            shell_state.active_skill_name = args[0]
            success_output(f"Activated skill {args[0]}.")
            return True

        if action == "reload":
            if args:
                error_output("Usage: /skill reload")
                return True
            skill_service.reload()
            if (
                shell_state.active_skill_name is not None
                and skill_service.get_skill(shell_state.active_skill_name) is None
            ):
                cleared = shell_state.active_skill_name
                shell_state.active_skill_name = None
                success_output(f"Reloaded skills and cleared missing active skill {cleared}.")
                return True
            success_output("Reloaded skills from disk.")
            return True

        if action == "clear":
            shell_state.active_skill_name = None
            success_output("Cleared active skill.")
            return True

        if action == "current":
            text_output(f"Current skill: {render_skill_name(shell_state.active_skill_name)}")
            return True

        error_output(f"Unknown skill command: {action}")
        return True
    except Exception as exc:
        error_output(f"Skill command failed: {exc}")
        return True


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
    text_output: OutputFn = _default_text_output,
    info_output: OutputFn = ColoredOutput.print_info,
    error_output: OutputFn = ColoredOutput.print_error,
    success_output: OutputFn = ColoredOutput.print_success,
    input_func: InputFn = input,
) -> bool:
    parsed = parse_task_command(command)
    if parsed is None:
        return False

    checkpoint_service = checkpoint_service or task_runner.checkpoint_service
    skill_service = skill_service or create_skill_service()
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
                        "/task checkpoints <id> [limit]",
                        "/task checkpoint <id>",
                        "/task runs <id> [limit]",
                        "/task run <id>",
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
            try:
                skill_raw = input_func(f"Skill [{NONE_LABEL}]: ").strip()
            except (EOFError, StopIteration):
                skill_raw = ""
            skill_name = skill_raw or skill_service.default_task_skill_name
            if not title or not goal:
                error_output("Task title and goal are required.")
                return True
            if skill_name is not None:
                skill_service.resolve_skill(skill_name)
            task = task_service.create_task(title=title, goal=goal, skill_profile=skill_name)
            success_output(f"Created task {task.public_id} ({task.id})")
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

        if action == "checkpoints":
            if not args or len(args) > 2:
                error_output("Usage: /task checkpoints <task_id> [limit]")
                return True
            task = task_service.get_task(args[0])
            if task is None:
                error_output(f"Task not found: {args[0]}")
                return True
            limit = 20 if len(args) == 1 else _parse_limit(args[1])
            summaries = checkpoint_service.list_checkpoints(task.id, limit=limit)
            text_output(render_checkpoint_list(summaries, task, run_service))
            return True

        if action == "checkpoint":
            if len(args) != 1:
                error_output("Usage: /task checkpoint <checkpoint_id>")
                return True
            summary = checkpoint_service.require_checkpoint_summary(args[0])
            text_output(render_checkpoint_detail(summary, task_service, run_service))
            return True

        if action == "runs":
            if not args or len(args) > 2:
                error_output("Usage: /task runs <task_id> [limit]")
                return True
            task = task_service.get_task(args[0])
            if task is None:
                error_output(f"Task not found: {args[0]}")
                return True
            limit = 20 if len(args) == 1 else _parse_limit(args[1])
            runs = run_service.list_runs(task.id, limit=limit)
            text_output(render_run_list(runs))
            return True

        if action == "run":
            if len(args) != 1:
                error_output("Usage: /task run <run_id>")
                return True
            run = run_service.require_run(args[0])
            task = task_service.require_task(run.task_id)
            entries = run_service.list_run_logs(run.id, limit=20)
            text_output(render_run_detail(run, task, entries))
            return True

        if action == "logs":
            if not args or len(args) > 2:
                error_output("Usage: /task logs <task_id> [limit]")
                return True
            task = task_service.get_task(args[0])
            if task is None:
                error_output(f"Task not found: {args[0]}")
                return True
            limit = 20 if len(args) == 1 else _parse_limit(args[1])
            entries = run_service.list_logs(task.id, limit=limit)
            text_output(render_task_logs(entries, _build_run_label_map(entries, run_service)))
            return True

        if action == "resume":
            if len(args) != 1:
                error_output("Usage: /task resume <task_id>")
                return True
            task, restored = task_runner.resume_task(args[0])
            copy_session_state(session_state, restored)
            shell_state.active_task_id = task.id
            shell_state.active_task_public_id = task.public_id
            success_output(f"Resumed task {task.public_id}: {task.title}")
            return True

        if action == "detach":
            if shell_state.active_task_id is None:
                error_output("No active task is bound to this shell.")
                return True
            task = task_runner.detach_task(shell_state.active_task_id, session_state)
            shell_state.active_task_id = None
            shell_state.active_task_public_id = None
            success_output(f"Detached task {task.public_id} and saved a checkpoint.")
            return True

        if action == "complete":
            if shell_state.active_task_id is None:
                error_output("No active task is bound to this shell.")
                return True
            task = task_runner.complete_task(shell_state.active_task_id, session_state)
            shell_state.active_task_id = None
            shell_state.active_task_public_id = None
            success_output(f"Completed task {task.public_id}.")
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

        if question == "/help":
            print_help()
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
    print("mini-claude-code 0.1.0 - type /help for available commands")
    asyncio.run(main())
