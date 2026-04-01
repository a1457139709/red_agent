from pathlib import Path
import textwrap

from agent.settings import Settings
from app.skill_service import SkillService
from main import ShellState, create_skill_service, handle_skill_command


def build_settings(tmp_path: Path) -> Settings:
    return Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        working_directory=tmp_path,
    )


def write_local_skill(tmp_path: Path, name: str, content: str) -> Path:
    skill_dir = tmp_path / ".mini-claude-code" / "skills" / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")
    return skill_file


def test_local_skill_is_discovered_after_reload(tmp_path):
    settings = build_settings(tmp_path)
    skill_service = create_skill_service(settings)

    assert skill_service.get_skill("local-demo") is None

    write_local_skill(
        tmp_path,
        "local-demo",
        """
        ---
        name: local-demo
        description: Local test skill.
        license: Proprietary
        compatibility: Agent Skills baseline
        allowed-tools:
          - read_file
          - search
        metadata:
          category: local
        ---

        # Local Demo

        Use the local skill body.
        """,
    )

    skill_service.reload()
    skill = skill_service.require_skill("local-demo")

    assert skill.source == "local"
    assert skill.skill_file.parent.parent == settings.skills_dir
    assert skill.manifest.allowed_tools == ["read_file", "search"]


def test_local_skill_overrides_built_in_by_name(tmp_path):
    settings = build_settings(tmp_path)
    write_local_skill(
        tmp_path,
        "development-default",
        """
        ---
        name: development-default
        description: Local override for development.
        license: Proprietary
        compatibility: Agent Skills baseline
        allowed-tools:
          - read_file
        metadata:
          category: local
          override: true
        ---

        # Local Override

        This development skill is overridden locally.
        """,
    )

    skill_service = create_skill_service(settings)
    skill = skill_service.require_skill("development-default")

    assert skill.source == "local"
    assert skill.manifest.description == "Local override for development."
    assert skill.manifest.allowed_tools == ["read_file"]
    assert "Local Override" in skill.manifest.body


def test_skill_reload_command_picks_up_local_skill_and_clears_missing_active_skill(tmp_path):
    settings = build_settings(tmp_path)
    skill_service = create_skill_service(settings)
    shell_state = ShellState(active_skill_name="security-audit")
    successes = []
    errors = []
    outputs = []

    write_local_skill(
        tmp_path,
        "local-demo",
        """
        ---
        name: local-demo
        description: Local test skill.
        license: Proprietary
        compatibility: Agent Skills baseline
        allowed-tools:
          - read_file
        metadata:
          category: local
        ---

        # Local Demo

        Use the local skill body.
        """,
    )

    assert handle_skill_command(
        "/skill reload",
        shell_state=shell_state,
        skill_service=skill_service,
        text_output=outputs.append,
        error_output=errors.append,
        success_output=successes.append,
    )
    assert skill_service.get_skill("local-demo") is not None
    assert shell_state.active_skill_name == "security-audit"

    local_skill_file = settings.skills_dir / "local-demo" / "SKILL.md"
    local_skill_file.unlink()
    local_skill_file.parent.rmdir()
    assert handle_skill_command(
        "/skill use local-demo",
        shell_state=shell_state,
        skill_service=skill_service,
        text_output=outputs.append,
        error_output=errors.append,
        success_output=successes.append,
    )

    assert handle_skill_command(
        "/skill reload",
        shell_state=shell_state,
        skill_service=skill_service,
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
        """
        ---
        name: local-demo
        description: Local test skill.
        license: Proprietary
        compatibility: Agent Skills baseline
        allowed-tools:
          - read_file
        metadata:
          category: local
        ---

        # Local Demo

        Use the local skill body.
        """,
    )
    skill_service = create_skill_service(settings)
    outputs = []
    errors = []

    assert handle_skill_command(
        "/skill list",
        skill_service=skill_service,
        text_output=outputs.append,
        error_output=errors.append,
    )
    assert handle_skill_command(
        "/skill show local-demo",
        skill_service=skill_service,
        text_output=outputs.append,
        error_output=errors.append,
    )

    assert any("local-demo" in message and "local" in message for message in outputs)
    assert any("Source:" in message and "local" in message for message in outputs)
    assert not errors
