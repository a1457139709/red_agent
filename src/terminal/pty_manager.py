from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import os
import platform
import select
import signal
import struct
import subprocess
import threading
import uuid


OutputCallback = Callable[[str], None]
ExitCallback = Callable[[int | None], None]


@dataclass(frozen=True, slots=True)
class PtyTerminal:
    terminal_id: str
    pid: int
    cwd: Path
    rows: int
    cols: int


@dataclass(slots=True)
class _PtySession:
    terminal: PtyTerminal
    process: subprocess.Popen[bytes]
    master_fd: int
    reader: threading.Thread
    closed: bool = False


class PtyManager:
    def __init__(self) -> None:
        self._sessions: dict[str, _PtySession] = {}
        self._lock = threading.RLock()

    def open(
        self,
        *,
        cwd: Path,
        terminal_id: str | None = None,
        rows: int = 24,
        cols: int = 80,
        on_output: OutputCallback,
        on_exit: ExitCallback,
    ) -> PtyTerminal:
        if platform.system().lower().startswith("win"):
            raise RuntimeError("Embedded PTY terminals are not supported on this platform yet.")
        cwd = cwd.resolve()
        if not cwd.is_dir():
            raise ValueError(f"Terminal working directory does not exist: {cwd}")
        master_fd, slave_fd = os.openpty()
        shell = os.environ.get("SHELL") or "/bin/sh"
        process = subprocess.Popen(
            [shell],
            cwd=str(cwd),
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            close_fds=True,
            start_new_session=True,
        )
        os.close(slave_fd)
        terminal = PtyTerminal(
            terminal_id=terminal_id or f"term-{uuid.uuid4()}",
            pid=process.pid,
            cwd=cwd,
            rows=rows,
            cols=cols,
        )
        self.resize(terminal.terminal_id, rows=rows, cols=cols, allow_missing=True, master_fd=master_fd)
        reader = threading.Thread(
            target=self._read_loop,
            args=(terminal.terminal_id, master_fd, process, on_output, on_exit),
            name=f"pty-reader-{terminal.terminal_id}",
            daemon=True,
        )
        session = _PtySession(terminal=terminal, process=process, master_fd=master_fd, reader=reader)
        with self._lock:
            self._sessions[terminal.terminal_id] = session
        reader.start()
        return terminal

    def write(self, terminal_id: str, data: str) -> None:
        session = self._require(terminal_id)
        os.write(session.master_fd, data.encode("utf-8", errors="replace"))

    def resize(
        self,
        terminal_id: str,
        *,
        rows: int,
        cols: int,
        allow_missing: bool = False,
        master_fd: int | None = None,
    ) -> None:
        if rows <= 0 or cols <= 0:
            raise ValueError("Terminal rows and cols must be greater than zero.")
        fd = master_fd
        if fd is None:
            if allow_missing:
                return
            fd = self._require(terminal_id).master_fd
        try:
            import fcntl
            import termios

            fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
        except OSError:
            if not allow_missing:
                raise

    def close(self, terminal_id: str) -> None:
        with self._lock:
            session = self._sessions.get(terminal_id)
            if session is None:
                return
            session.closed = True
        if session.process.poll() is None:
            try:
                os.killpg(session.process.pid, signal.SIGHUP)
            except OSError:
                session.process.terminate()
        try:
            os.close(session.master_fd)
        except OSError:
            pass

    def shutdown(self) -> None:
        for terminal_id in list(self._sessions):
            self.close(terminal_id)

    def has(self, terminal_id: str) -> bool:
        with self._lock:
            return terminal_id in self._sessions

    def _require(self, terminal_id: str) -> _PtySession:
        with self._lock:
            session = self._sessions.get(terminal_id)
        if session is None:
            raise ValueError(f"Terminal not found: {terminal_id}")
        return session

    def _read_loop(
        self,
        terminal_id: str,
        master_fd: int,
        process: subprocess.Popen[bytes],
        on_output: OutputCallback,
        on_exit: ExitCallback,
    ) -> None:
        while True:
            if process.poll() is not None:
                break
            try:
                readable, _, _ = select.select([master_fd], [], [], 0.1)
            except OSError:
                break
            if not readable:
                continue
            try:
                chunk = os.read(master_fd, 4096)
            except OSError:
                break
            if not chunk:
                break
            on_output(chunk.decode("utf-8", errors="replace"))
        return_code = process.poll()
        if return_code is None:
            try:
                return_code = process.wait(timeout=0.2)
            except subprocess.TimeoutExpired:
                return_code = None
        with self._lock:
            self._sessions.pop(terminal_id, None)
        on_exit(return_code)
