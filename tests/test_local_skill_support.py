from pathlib import Path
import json

from agent.settings import Settings
from main import ShellState, create_capability_service, handle_skill_command


def build_settings(tmp_path: Path) -> Settings:
    return Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        working_directory=tmp_path,
    )


def write_local_skill(tmp_path: Path, name: str, *, description: str, tools: list[str]) -> Path:
    capability_dir = tmp_path / ".red-code" / "capabilities" / name
    capability_dir.mkdir(parents=True, exist_ok=True)
    (capability_dir / "capability.json").write_text(
        json.dumps(
            {
                "version": 1,
                "name": name,
                "kind": "skill",
                "display_name": name.title(),
                "description": description,
                "modes": ["normal"],
                "parameters": [],
                "metadata": {"category": "local"},
                "tools": {"allowed": tools},
                "risk": {"default": "safe", "actions": []},
                "execution": {"style": "prompt_assist", "profile": name},
                "user_invocable": True,
                "session": {
                    "supports_one_shot": True,
                    "supports_persistent": True,
                    "result_layers": [],
                },
            }
        ),
        encoding="utf-8",
    )
    prompt_file = capability_dir / "prompt.md"
    prompt_file.write_text(f"# {name}\n\nUse the local skill body.\n", encoding="utf-8")
    return prompt_file


def test_local_skill_is_discovered_after_reload(tmp_path):
    settings = build_settings(tmp_path)
    capability_service = create_capability_service(settings)

    assert capability_service.get_skill("local-demo") is None

    write_local_skill(
        tmp_path,
        "local-demo",
        description="Local test skill.",
        tools=["read_file", "search"],
    )

    capability_service.reload()
    skill = capability_service.require_skill("local-demo")

    assert skill.source == "local"
    assert skill.manifest_file.parent.parent == settings.capabilities_dir
    assert skill.manifest.tools.allowed == ("read_file", "search")


def test_local_skill_overrides_built_in_by_name(tmp_path):
    settings = build_settings(tmp_path)
    write_local_skill(
        tmp_path,
        "development-default",
        description="Local override for development.",
        tools=["read_file"],
    )

    capability_service = create_capability_service(settings)
    skill = capability_service.require_skill("development-default")

    assert skill.source == "local"
    assert skill.manifest.description == "Local override for development."
    assert skill.manifest.tools.allowed == ("read_file",)
    assert "Use the local skill body." in skill.prompt_body


def test_skill_reload_command_picks_up_local_skill_and_clears_missing_active_skill(tmp_path):
    settings = build_settings(tmp_path)
    capability_service = create_capability_service(settings)
    shell_state = ShellState(active_skill_name="security-audit")
    successes = []
    errors = []
    outputs = []

    prompt_file = write_local_skill(
        tmp_path,
        "local-demo",
        description="Local test skill.",
        tools=["read_file"],
    )

    assert handle_skill_command(
        "/skill reload",
        shell_state=shell_state,
        capability_service=capability_service,
        text_output=outputs.append,
        error_output=errors.append,
        success_output=successes.append,
    )
    assert capability_service.get_skill("local-demo") is not None
    assert shell_state.active_skill_name == "security-audit"

    capability_dir = prompt_file.parent
    for child in capability_dir.iterdir():
        child.unlink()
    capability_dir.rmdir()
    assert handle_skill_command(
        "/skill use local-demo",
        shell_state=shell_state,
        capability_service=capability_service,
        text_output=outputs.append,
        error_output=errors.append,
        success_output=successes.append,
    )

    assert handle_skill_command(
        "/skill reload",
        shell_state=shell_state,
        capability_service=capability_service,
        text_output=outputs.append,
        error_output=errors.append,
        success_output=successes.append,
    )

    assert shell_state.active_skill_name is None
    assert any("Reloaded skills from disk." in message for message in successes)
    assert any("cleared missing active skill local-demo" in message for message in successes)
    assert not errors


def test_skill_list_and_show_include_local_source(tmp_path):
    settings = build_settings(tmp_path)
    write_local_skill(
        tmp_path,
        "local-demo",
        description="Local test skill.",
        tools=["read_file"],
    )
    capability_service = create_capability_service(settings)
    outputs = []
    errors = []

    assert handle_skill_command(
        "/skill list",
        capability_service=capability_service,
        text_output=outputs.append,
        error_output=errors.append,
    )
    assert handle_skill_command(
        "/skill show local-demo",
        capability_service=capability_service,
        text_output=outputs.append,
        error_output=errors.append,
    )

    assert any("local-demo" in message and "local" in message for message in outputs)
    assert any("Source:" in message and "local" in message for message in outputs)
    assert not errors
