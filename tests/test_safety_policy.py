import asyncio

from agent.settings import Settings
from app.skill_service import SkillService
from skills.registry import SkillRegistry
from tools import build_tool_registry
from tools.executor import ToolExecutor
from tools.policy import CapabilityTier, RuntimeSafetyPolicy


def build_settings(tmp_path):
    return Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        working_directory=tmp_path,
    )


def create_skill_service() -> SkillService:
    tool_names = list(build_tool_registry().keys())
    return SkillService(
        SkillRegistry.built_in(known_tool_names=set(tool_names)),
        base_tool_names=tool_names,
        default_task_skill_name=None,
    )


def test_skill_runtime_policies_match_base_and_security_skill():
    service = create_skill_service()

    base_runtime = asyncio.run(service.build_base_runtime_config(context_summary="summary"))
    security_runtime = asyncio.run(
        service.build_skill_runtime_config(
            skill_name="security-audit",
            context_summary="summary",
        )
    )

    assert base_runtime.skill is None
    assert base_runtime.safety_policy.allows(CapabilityTier.READ)
    assert base_runtime.safety_policy.allows(CapabilityTier.WRITE)
    assert base_runtime.safety_policy.allows(CapabilityTier.EXECUTE)
    assert base_runtime.safety_policy.allows(CapabilityTier.DESTRUCTIVE)
    assert security_runtime.safety_policy.allows(CapabilityTier.READ)
    assert security_runtime.safety_policy.allows(CapabilityTier.EXECUTE)
    assert not security_runtime.safety_policy.allows(CapabilityTier.WRITE)
    assert not security_runtime.safety_policy.allows(CapabilityTier.DESTRUCTIVE)
    assert "Security Audit" in security_runtime.system_prompt


def test_policy_denies_visible_tool_when_runtime_is_narrowed(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    events = []
    executor = ToolExecutor(
        build_tool_registry(),
        on_audit=events.append,
    ).with_safety_policy(
        RuntimeSafetyPolicy.for_tool_names(["list_dir", "read_file", "search"])
    )

    result = executor.execute("write_file", {"file_path": "notes.txt", "content": "hello"})

    assert "capability 'write' is not allowed" in result
    assert events[0].event_type == "policy_denied"
    assert events[0].capability == CapabilityTier.WRITE


def test_sensitive_write_emits_confirmation_and_block_events(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    events = []
    executor = ToolExecutor(
        build_tool_registry(),
        confirm_command=lambda prompt: False,
        on_info=lambda message: None,
        on_audit=events.append,
    )

    result = executor.execute("write_file", {"file_path": ".env", "content": "token=1"})

    assert "user declined confirmation" in result
    assert [event.event_type for event in events] == [
        "confirmation_required",
        "operation_blocked",
    ]
    assert not (tmp_path / ".env").exists()
