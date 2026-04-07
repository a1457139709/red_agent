from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Callable, TypeVar


ResultT = TypeVar("ResultT")


class ExecutionTimedOutError(RuntimeError):
    pass


def run_with_timeout(
    operation: Callable[[], ResultT],
    *,
    timeout_seconds: int | None,
) -> ResultT:
    if timeout_seconds is None:
        return operation()

    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(operation)
    try:
        return future.result(timeout=timeout_seconds)
    except FuturesTimeoutError as exc:
        future.cancel()
        raise ExecutionTimedOutError(
            f"Execution timed out after {timeout_seconds} seconds."
        ) from exc
    finally:
        # Timed-out tool work may still finish in the background. Typed tools are
        # short-lived and timeout-bounded, so we release the worker immediately.
        executor.shutdown(wait=False, cancel_futures=True)
