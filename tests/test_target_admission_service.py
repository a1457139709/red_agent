from agent.settings import Settings
from app.project_service import ProjectService
from app.target_admission_service import TargetAdmissionService
from models.control_center import TargetPoolStatus, TargetType


def build_settings(tmp_path):
    return Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        working_directory=tmp_path,
    )


def test_initial_ip_target_does_not_allow_neighbor_ip(tmp_path):
    settings = build_settings(tmp_path)
    project = ProjectService.from_settings(settings).create_project(name="IP Scope")
    service = TargetAdmissionService.from_settings(settings)
    service.create_initial_target(
        project_identifier=project.id,
        value="10.10.10.5",
        target_type=TargetType.IP,
    )

    result = service.propose_target(project_identifier=project.id, value="10.10.10.6")

    assert result.status == "pending_review"
    assert result.target.status == TargetPoolStatus.PENDING


def test_initial_domain_target_allows_subdomains(tmp_path):
    settings = build_settings(tmp_path)
    project = ProjectService.from_settings(settings).create_project(name="Domain Scope")
    service = TargetAdmissionService.from_settings(settings)
    service.create_initial_target(
        project_identifier=project.id,
        value="forge.htb",
        target_type=TargetType.DOMAIN,
    )

    result = service.propose_target(project_identifier=project.id, value="dev.forge.htb")

    assert result.status == "accepted"
    assert result.target.status == TargetPoolStatus.ACTIVE


def test_rejected_domain_key_rejects_later_same_root_domain(tmp_path):
    settings = build_settings(tmp_path)
    project = ProjectService.from_settings(settings).create_project(name="Rejected Domain")
    service = TargetAdmissionService.from_settings(settings)
    pending = service.propose_target(project_identifier=project.id, value="admin.outside.test")

    rejected = service.reject_target(pending.target.id)
    repeated = service.propose_target(project_identifier=project.id, value="dev.outside.test")

    assert rejected.target.rejection_key == "outside.test"
    assert repeated.status == "rejected"
    assert repeated.target.scope_reason == "matched previous rejected scope key outside.test"
