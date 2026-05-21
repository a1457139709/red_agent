from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from threading import Lock

from agent.settings import Settings
from app.scanner_service import ScannerService


class ScannerTaskRuntime:
    def __init__(self, *, settings: Settings, max_workers: int = 2) -> None:
        self.settings = settings
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="scanner-task")
        self._lock = Lock()
        self._futures: dict[str, Future[object]] = {}

    def submit(self, task_identifier: str) -> None:
        with self._lock:
            current = self._futures.get(task_identifier)
            if current is not None and not current.done():
                return
            future = self.executor.submit(self._execute, task_identifier)
            self._futures[task_identifier] = future
        future.add_done_callback(lambda _future: self._forget(task_identifier))

    def cancel_pending(self, task_identifier: str) -> bool:
        with self._lock:
            future = self._futures.get(task_identifier)
            if future is None or future.running() or future.done():
                return False
        cancelled = future.cancel()
        if cancelled:
            with self._lock:
                self._futures.pop(task_identifier, None)
        return cancelled

    def shutdown(self) -> None:
        self.executor.shutdown(wait=False, cancel_futures=True)

    def _execute(self, task_identifier: str) -> None:
        ScannerService.from_settings(self.settings).execute_pending_task(task_identifier)

    def _forget(self, task_identifier: str) -> None:
        with self._lock:
            self._futures.pop(task_identifier, None)
