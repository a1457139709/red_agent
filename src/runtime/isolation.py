from __future__ import annotations

from collections.abc import Callable
from time import monotonic
import multiprocessing
import os
import pickle
import tempfile

from orchestration.scope_validator import TargetDescriptor
from runtime.timeouts import ExecutionTimedOutError
from tools import build_security_tool_registry
from tools.contracts import SecurityToolInvocation, SecurityToolResult
from tools.executor import SecurityToolExecutionError, SecurityToolExecutor


CancelProbe = Callable[[], bool] | None
_POLL_INTERVAL_SECONDS = 0.05
_PROCESS_JOIN_TIMEOUT_SECONDS = 1.0


class ExecutionCancelledError(RuntimeError):
    pass


def execute_security_tool_in_subprocess(
    *,
    tool_name: str,
    invocation: SecurityToolInvocation,
    target: TargetDescriptor,
    timeout_seconds: int | None,
    cancel_requested: CancelProbe = None,
) -> SecurityToolResult:
    ctx = multiprocessing.get_context("spawn")
    fd, result_path = tempfile.mkstemp(prefix="red-code-isolation-", suffix=".bin")
    os.close(fd)
    process = ctx.Process(
        target=_execute_security_tool,
        args=(result_path, tool_name, invocation, target),
        daemon=True,
    )
    process.start()

    deadline = None if timeout_seconds is None else monotonic() + timeout_seconds
    try:
        while True:
            if cancel_requested is not None and cancel_requested():
                _terminate_process(process)
                raise ExecutionCancelledError("Execution cancelled by operator.")
            if deadline is not None and monotonic() >= deadline:
                _terminate_process(process)
                raise ExecutionTimedOutError(f"Execution timed out after {timeout_seconds} seconds.")
            if not process.is_alive():
                break
            process.join(timeout=_POLL_INTERVAL_SECONDS)

        if os.path.exists(result_path) and os.path.getsize(result_path) > 0:
            return _receive_result(result_path, tool_name)
        raise SecurityToolExecutionError(
            tool_name,
            f"Security tool process exited with code {process.exitcode} before returning a result.",
        )
    finally:
        if process.is_alive():
            _terminate_process(process)
        process.join(timeout=_PROCESS_JOIN_TIMEOUT_SECONDS)
        if os.path.exists(result_path):
            os.remove(result_path)


def _execute_security_tool(
    result_path: str,
    tool_name: str,
    invocation: SecurityToolInvocation,
    target: TargetDescriptor,
) -> None:
    try:
        executor = SecurityToolExecutor(build_security_tool_registry())
        result = executor.execute(tool_name, invocation=invocation, target=target)
        payload = ("result", result)
    except Exception as exc:
        payload = ("error", str(exc))

    with open(result_path, "wb") as handle:
        pickle.dump(payload, handle)


def _receive_result(result_path: str, tool_name: str) -> SecurityToolResult:
    with open(result_path, "rb") as handle:
        status, payload = pickle.load(handle)
    if status == "result":
        return payload
    raise SecurityToolExecutionError(tool_name, str(payload))


def _terminate_process(process: multiprocessing.Process) -> None:
    process.terminate()
    process.join(timeout=_PROCESS_JOIN_TIMEOUT_SECONDS)
    if process.is_alive() and hasattr(process, "kill"):
        process.kill()
        process.join(timeout=_PROCESS_JOIN_TIMEOUT_SECONDS)
