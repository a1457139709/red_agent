from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

from models.run import utc_now_iso

DEFAULT_JOB_LEASE_SECONDS = 15


def new_worker_id(*, prefix: str = "worker") -> str:
    return f"{prefix}-{uuid4().hex[:8]}"


def new_lease_token() -> str:
    return uuid4().hex


def lease_deadline(*, now: str | None = None, lease_seconds: int = DEFAULT_JOB_LEASE_SECONDS) -> str:
    started_at = datetime.fromisoformat(now or utc_now_iso())
    return (started_at + timedelta(seconds=lease_seconds)).isoformat()
