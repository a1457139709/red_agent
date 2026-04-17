from __future__ import annotations

from datetime import datetime
from pathlib import Path
import os
import re

from agent.settings import Settings


def session_root(settings: Settings, session_public_id: str) -> Path:
    return settings.sessions_dir / session_public_id


def memory_dir(settings: Settings, session_public_id: str) -> Path:
    return session_root(settings, session_public_id) / "memory"


def artifacts_dir(settings: Settings, session_public_id: str) -> Path:
    return session_root(settings, session_public_id) / "artifacts"


def findings_dir(settings: Settings, session_public_id: str) -> Path:
    return session_root(settings, session_public_id) / "findings"


def reports_dir(settings: Settings, session_public_id: str) -> Path:
    return session_root(settings, session_public_id) / "reports"


def checkpoint_blob_relative_path(*, checkpoint_id: str, created_at: str) -> str:
    created = datetime.fromisoformat(created_at)
    return (
        f"memory/checkpoints/{created.year:04d}/{created.month:02d}/"
        f"chk_{checkpoint_id}.json.gz"
    )


def _slugify(value: str, *, fallback: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_]+", "-", value.strip().lower()).strip("-")
    return slug or fallback


def artifact_payload_relative_path(
    *,
    source_job_label: str,
    ordinal: int,
    artifact_type: str,
    extension: str = ".json",
) -> str:
    suffix = extension if extension.startswith(".") else f".{extension}"
    return (
        "artifacts/"
        f"{_slugify(source_job_label, fallback='manual')}-{ordinal:02d}-"
        f"{_slugify(artifact_type, fallback='artifact')}{suffix}"
    )


def report_output_relative_path(
    *,
    report_public_id: str,
    report_type: str,
    extension: str = ".json",
) -> str:
    suffix = extension if extension.startswith(".") else f".{extension}"
    return (
        "reports/"
        f"{report_public_id.lower()}-{_slugify(report_type, fallback='report')}{suffix}"
    )


def resolve_session_relative_path(
    settings: Settings,
    *,
    session_public_id: str,
    relative_path: str,
) -> Path:
    root = session_root(settings, session_public_id).resolve()
    resolved = (root / relative_path).resolve()
    if os.path.commonpath([str(resolved), str(root)]) != str(root):
        raise ValueError(
            f"Session-scoped path escapes session directory: {session_public_id}:{relative_path}"
        )
    return resolved
