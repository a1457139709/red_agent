import asyncio

import main as main_module
from agent.settings import Settings
from app.session_service import SessionService
from main import ShellState, handle_module_command
from runtime.execution_events import ExecutionOutcome
from tools import build_tool_registry
from tools.executor import ToolExecutor


class FakeExecutionService:
    def __init__(self) -> None:
        self.module_calls = []
        self.outcome = ExecutionOutcome(status="completed", response="module done")

    async def execute_module(
        self,
        *,
        invocation,
        tool_executor,
        conversation_context=None,
        interaction_port=None,
    ) -> ExecutionOutcome:
        self.module_calls.append(
            {
                "module_name": invocation.module.manifest.name,
                "parameters": dict(invocation.parameters),
                "one_shot": invocation.one_shot,
            }
        )
        return self.outcome


def build_settings(tmp_path):
    return Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        working_directory=tmp_path,
    )


def test_handle_module_command_lists_and_shows_modules(tmp_path):
    settings = build_settings(tmp_path)
    skill_service = main_module.create_skill_service(settings)
    module_service = main_module.create_module_service(settings, skill_service=skill_service)
    session_service = SessionService.from_settings(settings)
    execution_service = FakeExecutionService()
    outputs = []
    errors = []

    assert asyncio.run(
        handle_module_command(
            "/module list",
            shell_state=ShellState(),
            session_service=session_service,
            module_service=module_service,
            execution_service=execution_service,
            tool_executor=ToolExecutor(build_tool_registry()),
            text_output=outputs.append,
            error_output=errors.append,
        )
    )
    assert asyncio.run(
        handle_module_command(
            "/module show surface-recon",
            shell_state=ShellState(),
            session_service=session_service,
            module_service=module_service,
            execution_service=execution_service,
            tool_executor=ToolExecutor(build_tool_registry()),
            text_output=outputs.append,
            error_output=errors.append,
        )
    )

    merged = "\n\n".join(outputs)
    assert "Modules" in merged
    assert "surface-recon" in merged
    assert "Capability Detail" in merged
    assert errors == []


def test_handle_module_command_runs_one_shot_module(tmp_path, monkeypatch):
    settings = build_settings(tmp_path)
    skill_service = main_module.create_skill_service(settings)
    module_service = main_module.create_module_service(settings, skill_service=skill_service)
    session_service = SessionService.from_settings(settings)
    execution_service = FakeExecutionService()
    answers = []
    monkeypatch.setattr(main_module.ColoredOutput, "print_final_answer", answers.append)

    assert asyncio.run(
        handle_module_command(
            "/module run surface-recon example.com {\"include_dns\": false}",
            shell_state=ShellState(),
            session_service=session_service,
            module_service=module_service,
            execution_service=execution_service,
            tool_executor=ToolExecutor(build_tool_registry()),
        )
    )

    assert execution_service.module_calls == [
        {
            "module_name": "surface-recon",
            "parameters": {
                "target": "example.com",
                "include_dns": False,
                "include_http": True,
                "include_tls": True,
            },
            "one_shot": True,
        }
    ]
    assert answers == ["module done"]
