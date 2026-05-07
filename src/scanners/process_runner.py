from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import queue
import shutil
import subprocess
from threading import Thread
import time


OutputCallback = Callable[[str, str], None]
CancelProbe = Callable[[], bool]


@dataclass(frozen=True, slots=True)
class ProcessResult:
    argv: list[str]
    return_code: int | None
    stdout: str
    stderr: str
    timed_out: bool = False
    cancelled: bool = False


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
        stdout_path: Path | None = None,
        stderr_path: Path | None = None,
        on_output: OutputCallback | None = None,
        cancel_requested: CancelProbe | None = None,
    ) -> ProcessResult:
        if stdout_path is None and stderr_path is None and on_output is None and cancel_requested is None:
            return self._run_captured(argv=argv, cwd=cwd, timeout_seconds=timeout_seconds)

        cwd.mkdir(parents=True, exist_ok=True)
        stdout_chunks: list[str] = []
        stderr_chunks: list[str] = []
        output_queue: queue.Queue[tuple[str, str]] = queue.Queue()

        try:
            process = subprocess.Popen(
                argv,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
        except Exception as exc:
            message = str(exc)
            if stderr_path is not None:
                stderr_path.write_text(message, encoding="utf-8")
            return ProcessResult(argv=list(argv), return_code=None, stdout="", stderr=message)

        readers = [
            Thread(target=_read_stream, args=("stdout", process.stdout, output_queue), daemon=True),
            Thread(target=_read_stream, args=("stderr", process.stderr, output_queue), daemon=True),
        ]
        for reader in readers:
            reader.start()

        deadline = time.monotonic() + timeout_seconds
        timed_out = False
        cancelled = False

        with _optional_text_writer(stdout_path) as stdout_file, _optional_text_writer(stderr_path) as stderr_file:
            while process.poll() is None:
                _drain_output_queue(
                    output_queue,
                    stdout_chunks=stdout_chunks,
                    stderr_chunks=stderr_chunks,
                    stdout_file=stdout_file,
                    stderr_file=stderr_file,
                    on_output=on_output,
                )
                if cancel_requested is not None and cancel_requested():
                    cancelled = True
                    _stop_process(process)
                    break
                if time.monotonic() >= deadline:
                    timed_out = True
                    _stop_process(process)
                    break
                time.sleep(0.05)

            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()

            for reader in readers:
                reader.join(timeout=1)
            _drain_output_queue(
                output_queue,
                stdout_chunks=stdout_chunks,
                stderr_chunks=stderr_chunks,
                stdout_file=stdout_file,
                stderr_file=stderr_file,
                on_output=on_output,
            )

            if timed_out:
                _append_output(
                    "stderr",
                    f"Process timed out after {timeout_seconds} seconds.",
                    stdout_chunks=stdout_chunks,
                    stderr_chunks=stderr_chunks,
                    stdout_file=stdout_file,
                    stderr_file=stderr_file,
                    on_output=on_output,
                )
            if cancelled:
                _append_output(
                    "stderr",
                    "Process cancelled.",
                    stdout_chunks=stdout_chunks,
                    stderr_chunks=stderr_chunks,
                    stdout_file=stdout_file,
                    stderr_file=stderr_file,
                    on_output=on_output,
                )

        return ProcessResult(
            argv=list(argv),
            return_code=process.returncode,
            stdout="".join(stdout_chunks),
            stderr="".join(stderr_chunks),
            timed_out=timed_out,
            cancelled=cancelled,
        )

    def _run_captured(
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


def _read_stream(
    stream_name: str,
    stream: object,
    output_queue: queue.Queue[tuple[str, str]],
) -> None:
    if stream is None:
        return
    for chunk in iter(stream.readline, ""):
        if chunk:
            output_queue.put((stream_name, chunk))


def _stop_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()


def _optional_text_writer(path: Path | None):
    if path is None:
        return _NullTextWriter()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path.open("w", encoding="utf-8")


class _NullTextWriter:
    def __enter__(self) -> "_NullTextWriter":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def write(self, _text: str) -> int:
        return 0

    def flush(self) -> None:
        return None


def _drain_output_queue(
    output_queue: queue.Queue[tuple[str, str]],
    *,
    stdout_chunks: list[str],
    stderr_chunks: list[str],
    stdout_file: object,
    stderr_file: object,
    on_output: OutputCallback | None,
) -> None:
    while True:
        try:
            stream_name, chunk = output_queue.get_nowait()
        except queue.Empty:
            return
        _append_output(
            stream_name,
            chunk,
            stdout_chunks=stdout_chunks,
            stderr_chunks=stderr_chunks,
            stdout_file=stdout_file,
            stderr_file=stderr_file,
            on_output=on_output,
        )


def _append_output(
    stream_name: str,
    chunk: str,
    *,
    stdout_chunks: list[str],
    stderr_chunks: list[str],
    stdout_file: object,
    stderr_file: object,
    on_output: OutputCallback | None,
) -> None:
    if stream_name == "stdout":
        stdout_chunks.append(chunk)
        stdout_file.write(chunk)
        stdout_file.flush()
    else:
        stderr_chunks.append(chunk)
        stderr_file.write(chunk)
        stderr_file.flush()
    if on_output is not None:
        on_output(stream_name, chunk)
