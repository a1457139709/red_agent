from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess


@dataclass(frozen=True, slots=True)
class ProcessResult:
    argv: list[str]
    return_code: int | None
    stdout: str
    stderr: str
    timed_out: bool = False


def resolve_binary(name: str, configured_path: str | None = None) -> str | None:
    if configured_path:
        path = Path(configured_path).expanduser()
        if path.is_file():
            return str(path)
        return shutil.which(configured_path)
    return shutil.which(name)


def read_version(binary_path: str, args: list[str] | None = None, *, timeout_seconds: int = 10) -> str:
    command = [binary_path, *(args or ["--version"])]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout_seconds,
        )
    except Exception as exc:
        return f"version check failed: {exc}"
    output = (completed.stdout or completed.stderr).strip()
    return output.splitlines()[0] if output else f"exit {completed.returncode}"


class ProcessRunner:
    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: int,
    ) -> ProcessResult:
        try:
            completed = subprocess.run(
                argv,
                cwd=cwd,
                capture_output=True,
                check=False,
                text=True,
                timeout=timeout_seconds,
            )
            return ProcessResult(
                argv=list(argv),
                return_code=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
            )
        except subprocess.TimeoutExpired as exc:
            return ProcessResult(
                argv=list(argv),
                return_code=None,
                stdout=exc.stdout or "",
                stderr=exc.stderr or f"Process timed out after {timeout_seconds} seconds.",
                timed_out=True,
            )
