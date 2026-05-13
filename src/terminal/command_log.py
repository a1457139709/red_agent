from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from models.control_center import CommandRun
from models.run import utc_now_iso
from storage.project_paths import project_session_root
from storage.repositories.control_center import CommandRunRepository
from agent.settings import Settings


@dataclass(slots=True)
class _ActiveCommand:
    command: CommandRun
    output_path: Path
    output_length: int = 0


class TerminalCommandLogger:
    def __init__(self, *, settings: Settings, repository: CommandRunRepository) -> None:
        self.settings = settings
        self.repository = repository
        self._line_buffers: dict[str, str] = {}
        self._active: dict[str, _ActiveCommand] = {}

    def observe_input(
        self,
        *,
        terminal_id: str,
        project_id: str,
        session_id: str,
        working_directory: str,
        data: str,
    ) -> CommandRun | None:
        buffer = self._line_buffers.get(terminal_id, "") + data
        created: CommandRun | None = None
        while "\n" in buffer or "\r" in buffer:
            newline_indexes = [index for index in (buffer.find("\n"), buffer.find("\r")) if index >= 0]
            split_at = min(newline_indexes)
            raw_line = buffer[:split_at]
            buffer = buffer[split_at + 1 :]
            command_text = raw_line.strip()
            if not command_text:
                continue
            self.finalize_active(terminal_id=terminal_id, exit_code=None)
            command = CommandRun.create(
                project_id=project_id,
                session_id=session_id,
                terminal_id=terminal_id,
                command=command_text,
                output_ref=self._output_ref(terminal_id=terminal_id),
                working_directory=working_directory,
                started_at=utc_now_iso(),
            )
            created = self.repository.create(command)
            output_path = self._output_path(
                project_id=project_id,
                session_id=session_id,
                output_ref=created.output_ref or self._output_ref(terminal_id=terminal_id),
            )
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text("", encoding="utf-8")
            self._active[terminal_id] = _ActiveCommand(command=created, output_path=output_path)
        self._line_buffers[terminal_id] = buffer
        return created

    def observe_output(self, *, terminal_id: str, data: str) -> None:
        active = self._active.get(terminal_id)
        if active is None:
            return
        with active.output_path.open("a", encoding="utf-8") as handle:
            handle.write(data)
        active.output_length += len(data)

    def finalize_active(self, *, terminal_id: str, exit_code: int | None) -> CommandRun | None:
        active = self._active.pop(terminal_id, None)
        if active is None:
            return None
        active.command.ended_at = utc_now_iso()
        active.command.exit_code = exit_code
        active.command.output_summary = _summarize_output(active.output_path)
        return self.repository.update(active.command)

    def _output_ref(self, *, terminal_id: str) -> str:
        # The command id is known only after public id allocation; the private id is stable before insert.
        return f"artifacts/terminal/{terminal_id}/{utc_now_iso().replace(':', '').replace('+', 'Z')}.txt"

    def _output_path(self, *, project_id: str, session_id: str, output_ref: str) -> Path:
        return project_session_root(self.settings, project_id=project_id, session_id=session_id) / output_ref


def _summarize_output(path: Path) -> str | None:
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    if not text:
        return None
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    summary = " ".join(lines[-3:]) if lines else text
    return summary[:500]
