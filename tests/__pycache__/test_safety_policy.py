import asyncio

from langchain_core.messages import AIMessage

import runtime.task_runner as task_runner_module
from agent.settings import Settings
from app.run_service import RunService
from app.skill_service import SkillService
from app.task_service import TaskService
from runtime.task_runner import TaskRunner
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


def test_task_runner_persists_safety_audit_logs(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    settings = build_settings(tmp_path)
    task_service = TaskService.from_settings(settings)
    run_service = RunService.from_settings(settings)
    runner = TaskRunner(task_service, run_service, create_skill_service())
    tool_executor = ToolExecutor(
        build_tool_registry(),
        confirm_command=lambda prompt: False,
        on_info=lambda message: None,
    )
    task = task_service.create_task(title="Safety", goal="Exercise risky tools")
    task, session_state = runner.resume_task(task.id)
    (tmp_path / "deleteme.txt").write_text("x", encoding="utf-8")

    async def fake_agent_loop(
        question,
        state,
        runtime_executor,
        current_settings,
        *,
        system_prompt=None,
        tools=None,
    ):
        tool_result = runtime_executor.execute("delete_file", {"file_path": "deleteme.txt"})
        return {
            "status": "completed",
            "response": tool_result,
            "messages": [
                AIMessage(
                    content=tool_result,
                    tool_calls=[],
                    usage_metadata={"input_tokens": 4, "output_tokens": 4, "total_tokens": 8},
                )
            ],
            "usage": {"input_tokens": 4, "output_tokens": 4, "total_tokens": 8},
        }

    monkeypatch.setattr(task_runner_module, "agent_loop", fake_agent_loop)

    asyncio.run(
        runner.run_prompt(
            task_id=task.id,
            question="delete it",
            session_state=session_state,
            tool_executor=tool_executor,
            settings=settings,
        )
    )

    logs = run_service.list_logs(task.id, limit=20)
    log_messages = {entry.message for entry in logs}
    blocked_log = next(entry for entry in logs if entry.message == "safety_operation_blocked")

    assert "safety_confirmation_required" in log_messages
    assert "safety_operation_blocked" in log_messages
    assert blocked_log.payload["tool_name"] == "delete_file"
    assert blocked_log.payload["capability"] == CapabilityTier.DESTRUCTIVE.value
    assert (tmp_path / "deleteme.txt").exists()
