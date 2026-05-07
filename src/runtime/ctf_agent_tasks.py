from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from threading import Lock

from agent.settings import Settings
from app.ctf_agent_service import CTFAgentService


class CTFAgentTaskRuntime:
    def __init__(self, *, settings: Settings, max_workers: int = 1) -> None:
        self.settings = settings
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="ctf-agent")
        self._lock = Lock()
        self._futures: dict[str, Future[object]] = {}

    def submit(self, task_identifier: str) -> None:
        future = self.executor.submit(self._execute, task_identifier)
        with self._lock:
            self._futures[task_identifier] = future
        future.add_done_callback(lambda _future: self._forget(task_identifier))

    def shutdown(self) -> None:
        self.executor.shutdown(wait=False, cancel_futures=True)

    def _execute(self, task_identifier: str) -> None:
        CTFAgentService.from_settings(self.settings).run_agent_task(task_identifier)

    def _forget(self, task_identifier: str) -> None:
        with self._lock:
            self._futures.pop(task_identifier, None)
