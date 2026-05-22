from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from agent.settings import Settings
from app.attack_path_service import AttackPathService
from app.project_service import ProjectService
from app.scanner_service import ScannerService
from app.target_session_service import TargetSessionService
from models.control_center import TargetType
from scanners.process_runner import ProcessResult
from server.app import create_app
from storage.repositories.control_center import (
    AttackPathEvidenceLinkRepository,
    AttackPathNodeRepository,
    EvidenceRepository,
    FindingRepository,
)
from storage.sqlite import SQLiteStorage


NMAP_HTTP_XML = """<?xml version="1.0"?>
<nmaprun>
  <host>
    <address addr="10.10.10.5" addrtype="ipv4"/>
    <ports>
      <port protocol="tcp" portid="80">
        <state state="open"/>
        <service name="http" product="nginx" version="1.24"/>
      </port>
    </ports>
  </host>
</nmaprun>
"""


FFUF_JSON = """{"results": [{"url": "http://10.10.10.5/admin", "status": 200, "length": 120, "words": 8, "lines": 4}]}"""


NUCLEI_JSONL = (
    '{"template-id":"http/test","info":{"name":"HTTP Test","severity":"medium"},'
    '"matched-at":"http://10.10.10.5/admin"}\n'
)


class FakeRunner:
    def __init__(self, stdout: str) -> None:
        self.stdout = stdout

    def run(
        self,
        *,
        argv,
        cwd,
        timeout_seconds,
        stdout_path=None,
        stderr_path=None,
        on_output=None,
        cancel_requested=None,
    ):
        if stdout_path is not None:
            stdout_path.write_text(self.stdout, encoding="utf-8")
        if stderr_path is not None:
            stderr_path.write_text("", encoding="utf-8")
        if on_output is not None:
            on_output("stdout", self.stdout)
        return ProcessResult(argv=list(argv), return_code=0, stdout=self.stdout, stderr="")


def build_settings(tmp_path):
    return Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        working_directory=tmp_path,
    )


def prepare_session(settings):
    project = ProjectService.from_settings(settings).create_project(name="Phase 5")
    session = TargetSessionService.from_settings(settings).create_session(
        project_identifier=project.id,
        name="Target",
        target_value="10.10.10.5",
        target_type=TargetType.IP,
    )
    return project, session


def test_nmap_result_creates_service_and_web_entry_nodes(tmp_path):
    settings = build_settings(tmp_path)
    binary = tmp_path / "nmap"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    _project, session = prepare_session(settings)
    service = ScannerService(settings=settings, runner=FakeRunner(NMAP_HTTP_XML))
    service.update_config({"tools": {"nmap": {"binary_path": str(binary)}}})

    service.create_scan_task(
        session_identifier=session.id,
        task_type="port_scan",
        input_data={"target_host": "10.10.10.5"},
    )

    storage = SQLiteStorage(settings.sqlite_path)
    nodes = AttackPathNodeRepository(storage).list(session_id=session.id, limit=None)
    assert {node.stage for node in nodes} == {"enumeration", "web-enum"}
    assert any("Open tcp port 80" in node.title for node in nodes)
    for node in nodes:
        assert AttackPathEvidenceLinkRepository(storage).list_evidence_ids(node_id=node.id)


def test_ffuf_result_creates_web_enum_node(tmp_path):
    settings = build_settings(tmp_path)
    wordlist = tmp_path / "words.txt"
    wordlist.write_text("admin\n", encoding="utf-8")
    binary = tmp_path / "ffuf"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    _project, session = prepare_session(settings)
    service = ScannerService(settings=settings, runner=FakeRunner(FFUF_JSON))
    service.update_config({"tools": {"ffuf": {"binary_path": str(binary), "default_wordlist": str(wordlist)}}})

    service.create_scan_task(
        session_identifier=session.id,
        task_type="dir_scan",
        input_data={"base_url": "http://10.10.10.5"},
    )

    nodes = AttackPathNodeRepository(SQLiteStorage(settings.sqlite_path)).list(session_id=session.id, limit=None)
    assert nodes[0].stage == "web-enum"
    assert "http://10.10.10.5/admin" in nodes[0].title


def test_nuclei_result_creates_finding_and_verified_poc_node(tmp_path):
    settings = build_settings(tmp_path)
    templates = tmp_path / "templates"
    templates.mkdir()
    binary = tmp_path / "nuclei"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    _project, session = prepare_session(settings)
    service = ScannerService(settings=settings, runner=FakeRunner(NUCLEI_JSONL))
    service.update_config({"tools": {"nuclei": {"binary_path": str(binary), "templates_path": str(templates)}}})

    service.create_scan_task(
        session_identifier=session.id,
        task_type="poc_scan",
        input_data={"target_url": "http://10.10.10.5/admin"},
    )

    storage = SQLiteStorage(settings.sqlite_path)
    finding = FindingRepository(storage).list(session_id=session.id, limit=None)[0]
    node = AttackPathNodeRepository(storage).list(session_id=session.id, limit=None)[0]
    evidence = EvidenceRepository(storage).list(session_id=session.id, limit=None)[0]
    assert finding.severity == "medium"
    assert finding.status == "verified"
    assert finding.evidence_refs == [evidence.id]
    assert node.stage == "poc-verified"
    assert node.status == "verified"


def test_manual_evidence_can_link_to_node_and_flag_links_to_evidence(tmp_path):
    settings = build_settings(tmp_path)
    _project, session = prepare_session(settings)
    service = AttackPathService.from_settings(settings)

    evidence, note_node = service.create_evidence(
        session_identifier=session.id,
        evidence_type="note",
        title="Admin portal note",
        summary="Login page has default branding.",
    )
    flag, flag_node = service.create_flag(
        session_identifier=session.id,
        flag_type="loot",
        value="admin:admin",
        source_evidence_id=evidence.public_id,
    )

    storage = SQLiteStorage(settings.sqlite_path)
    assert note_node.node.stage == "note"
    assert note_node.evidence[0].id == evidence.id
    assert flag.source_evidence_id == evidence.id
    assert flag_node.node.stage == "flag"
    assert AttackPathEvidenceLinkRepository(storage).list_evidence_ids(node_id=flag_node.node.id) == [evidence.id]


def test_phase5_workspace_api_routes(tmp_path, monkeypatch):
    settings = build_settings(tmp_path)
    _project, session = prepare_session(settings)

    monkeypatch.setattr("server.lifecycle.get_settings", lambda: settings)
    monkeypatch.setattr("app.attack_path_service.get_settings", lambda: settings)

    with TestClient(create_app()) as client:
        created_evidence = client.post(
            f"/api/sessions/{session.public_id}/evidence",
            json={"evidence_type": "note", "title": "Manual note", "summary": "Check login."},
        )
        assert created_evidence.status_code == 201
        evidence = created_evidence.json()["evidence"]
        node = created_evidence.json()["node"]
        assert node["stage"] == "note"
        assert node["evidence"][0]["id"] == evidence["id"]

        created_node = client.post(
            f"/api/sessions/{session.id}/attack-path",
            json={
                "stage": "vulnerability-hypothesis",
                "title": "Try default credentials",
                "evidence_ids": [evidence["public_id"]],
            },
        )
        assert created_node.status_code == 201
        assert created_node.json()["node"]["evidence"][0]["id"] == evidence["id"]

        created_flag = client.post(
            f"/api/sessions/{session.id}/flags",
            json={"flag_type": "loot", "value": "admin:admin", "source_evidence_id": evidence["id"]},
        )
        assert created_flag.status_code == 201
        assert created_flag.json()["node"]["stage"] == "flag"

        assert client.get(f"/api/sessions/{session.id}/attack-path").json()["nodes"]
        assert client.get(f"/api/sessions/{session.id}/evidence").json()["evidence"][0]["title"] == "Manual note"
        assert client.get(f"/api/sessions/{session.id}/flags").json()["flags"][0]["value"] == "admin:admin"


def test_attack_path_creation_rolls_back_when_evidence_validation_fails(tmp_path):
    settings = build_settings(tmp_path)
    _project, session = prepare_session(settings)
    service = AttackPathService.from_settings(settings)

    with pytest.raises(ValueError, match="Evidence not found in session"):
        service.create_attack_path_node(
            session_identifier=session.id,
            stage="exploit",
            title="Try admin shell",
            evidence_ids=["EVID9999"],
        )

    storage = SQLiteStorage(settings.sqlite_path)
    assert AttackPathNodeRepository(storage).list(session_id=session.id, limit=None) == []


def test_evidence_creation_rolls_back_when_attack_path_node_is_missing(tmp_path):
    settings = build_settings(tmp_path)
    _project, session = prepare_session(settings)
    service = AttackPathService.from_settings(settings)

    with pytest.raises(ValueError, match="Attack path node not found in session"):
        service.create_evidence(
            session_identifier=session.id,
            evidence_type="note",
            title="Should not persist",
            attack_path_node_id="AP9999",
        )

    storage = SQLiteStorage(settings.sqlite_path)
    assert EvidenceRepository(storage).list(session_id=session.id, limit=None) == []
