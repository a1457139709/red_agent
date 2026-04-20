from agent.settings import Settings
from app.redteam_session_service import RedteamSessionService
from app.scope_policy_service import ScopePolicyService
from app.session_service import SessionService
from models.operation import OperationStatus
from models.session import SessionMode, SessionPersistenceMode, SessionStatus


def build_settings(tmp_path):
    return Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        working_directory=tmp_path,
    )


def test_redteam_session_service_bootstraps_session_and_scope_policy(tmp_path):
    settings = build_settings(tmp_path)
    service = RedteamSessionService.from_settings(settings)
    session_service = SessionService.from_settings(settings)
    scope_policy_service = ScopePolicyService.from_settings(settings)

    bundle = service.create_redteam_session(
        title="Web recon",
        objective="Inspect attack surface",
        allowed_hosts=["example.com"],
        allowed_domains=["example.com"],
        allowed_cidrs=["10.0.0.0/24"],
        allowed_ports=[80, 443],
        allowed_protocols=["http", "https"],
        denied_targets=["admin.example.com"],
        allowed_tool_categories=["recon"],
        max_concurrency=2,
        rate_limit_per_minute=30,
        confirmation_required_actions=["port_scan"],
        status=OperationStatus.READY,
    )

    session = session_service.require_session(bundle.session.id)
    policy = scope_policy_service.require_scope_policy(bundle.scope_policy.id)

    assert session.id == bundle.session.id
    assert session.mode == SessionMode.REDTEAM
    assert session.persistence_mode == SessionPersistenceMode.PERSISTENT
    assert session.status == SessionStatus.ACTIVE
    assert policy.session_id == bundle.session.id
    assert policy.allowed_ports == [80, 443]
    assert policy.max_concurrency == 2
