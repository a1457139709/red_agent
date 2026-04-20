import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from app.operation_service import OperationService
from app.redteam_session_service import RedteamSessionBundle, RedteamSessionService
from models.operation import Operation, OperationStatus


def create_redteam_bundle(
    settings,
    *,
    title: str,
    objective: str,
    workspace: str | None = None,
    allowed_hosts: list[str] | None = None,
    allowed_domains: list[str] | None = None,
    allowed_cidrs: list[str] | None = None,
    allowed_ports: list[int] | None = None,
    allowed_protocols: list[str] | None = None,
    denied_targets: list[str] | None = None,
    allowed_tool_categories: list[str] | None = None,
    max_concurrency: int = 1,
    rate_limit_per_minute: int | None = None,
    confirmation_required_actions: list[str] | None = None,
    status: OperationStatus = OperationStatus.DRAFT,
) -> RedteamSessionBundle:
    return RedteamSessionService.from_settings(settings).create_redteam_session(
        title=title,
        objective=objective,
        workspace=workspace,
        allowed_hosts=allowed_hosts,
        allowed_domains=allowed_domains,
        allowed_cidrs=allowed_cidrs,
        allowed_ports=allowed_ports,
        allowed_protocols=allowed_protocols,
        denied_targets=denied_targets,
        allowed_tool_categories=allowed_tool_categories,
        max_concurrency=max_concurrency,
        rate_limit_per_minute=rate_limit_per_minute,
        confirmation_required_actions=confirmation_required_actions,
        status=status,
    )


def create_redteam_operation(settings, **kwargs) -> Operation:
    bundle = create_redteam_bundle(settings, **kwargs)
    return OperationService.from_settings(settings).require_operation(bundle.session.id)
