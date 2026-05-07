from __future__ import annotations

import sys

from fastapi.testclient import TestClient

from agent.settings import Settings
from app.project_service import ProjectService
from app.scanner_service import ScannerService
from app.target_session_service import TargetSessionService
from models.control_center import TargetType
from scanners.ffuf_adapter import FfufAdapter
from scanners.nmap_adapter import NmapAdapter
from scanners.nuclei_adapter import NucleiAdapter
from scanners.process_runner import ProcessResult, ProcessRunner
from server.app import create_app
from storage.repositories.control_center import (
    AttackPathNodeRepository,
    EventRepository,
    EvidenceRepository,
    TaskRepository,
)
from storage.sqlite import SQLiteStorage


NMAP_XML = """<?xml version="1.0"?>
<nmaprun>
  <host>
    <address addr="10.10.10.5" addrtype="ipv4"/>
    <ports>
      <port protocol="tcp" portid="22">
        <state state="open"/>
        <service name="ssh" product="OpenSSH" version="8.9"/>
      </port>
      <port protocol="tcp" portid="80">
        <state state="closed"/>
      </port>
    </ports>
  </host>
</nmaprun>
"""


FFUF_JSON = """{
  "results": [
    {"url": "http://target/admin", "status": 200, "length": 1234, "words": 40, "lines": 12,
     "redirectlocation": ""}
  ]
}
"""


NUCLEI_JSONL = (
    '{"template-id":"exposure/test","info":{"name":"Test Exposure","severity":"medium",'
    '"metadata":{"product":"demo"}},"matched-at":"http://target/admin","extracted-results":["demo"]}\n'
    '{"template-id":"tech/test","info":{"name":"Tech Match","severity":"info"},'
    '"matched-at":"http://target/"}\n'
)


class FakeRunner:
    def __init__(self, result: ProcessResult) -> None:
        self.result = result
        self.argv: list[str] | None = None

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
        self.argv = list(argv)
        if stdout_path is not None:
            stdout_path.write_text(self.result.stdout, encoding="utf-8")
        if stderr_path is not None:
            stderr_path.write_text(self.result.stderr, encoding="utf-8")
        if on_output is not None and self.result.stdout:
            on_output("stdout", self.result.stdout)
        if on_output is not None and self.result.stderr:
            on_output("stderr", self.result.stderr)
        return self.result


def build_settings(tmp_path):
    return Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        working_directory=tmp_path,
    )


def prepare_session(settings):
    project = ProjectService.from_settings(settings).create_project(name="Phase 3")
    session = TargetSessionService.from_settings(settings).create_session(
        project_identifier=project.id,
        name="Target",
        target_value="10.10.10.5",
        target_type=TargetType.IP,
    )
    return project, session


def test_nmap_argv_uses_list_and_parser_extracts_open_ports(tmp_path):
    output = tmp_path / "nmap.xml"
    argv = NmapAdapter().build_argv(
        binary_path="/usr/bin/nmap",
        input_data={"target_host": "10.10.10.5", "ports": [22, 80]},
        output_path=output,
    )
    parsed = NmapAdapter().parse_output(NMAP_XML)

    assert argv == ["/usr/bin/nmap", "-oX", str(output), "-sV", "-p", "22,80", "10.10.10.5"]
    assert parsed["open_ports"] == [
        {"port": 22, "protocol": "tcp", "service": "ssh", "product": "OpenSSH", "version": "8.9"}
    ]


def test_ffuf_argv_includes_fuzz_and_parser_extracts_paths(tmp_path):
    wordlist = tmp_path / "words.txt"
    wordlist.write_text("admin\n", encoding="utf-8")
    input_data = FfufAdapter().validate_input(
        {"base_url": "http://target", "wordlist": str(wordlist), "filters": {"status_codes": "404"}}
    )
    argv = FfufAdapter().build_argv(binary_path="/usr/bin/ffuf", input_data=input_data, output_path=tmp_path / "ffuf.json")
    parsed = FfufAdapter().parse_output(FFUF_JSON)

    assert "http://target/FUZZ" in argv
    assert "-fc" in argv
    assert input_data["filters"] == {"status_codes": "404"}
    assert parsed["results"][0]["url"] == "http://target/admin"


def test_ffuf_missing_wordlist_returns_validation_error(tmp_path):
    missing = tmp_path / "missing.txt"

    try:
        FfufAdapter().validate_input({"base_url": "http://target", "wordlist": str(missing)})
    except ValueError as exc:
        assert "wordlist does not exist" in str(exc)
    else:
        raise AssertionError("Expected missing wordlist validation error.")


def test_nuclei_jsonl_parser_preserves_multiple_matches_and_metadata():
    parsed = NucleiAdapter().parse_output(NUCLEI_JSONL)

    assert [item["template_id"] for item in parsed["matches"]] == ["exposure/test", "tech/test"]
    assert parsed["matches"][0]["severity"] == "medium"
    assert parsed["matches"][0]["metadata"] == {"product": "demo"}


def test_nuclei_empty_result_is_successful_no_finding_state():
    assert NucleiAdapter().parse_output("") == {"matches": []}


def test_missing_binary_creates_failed_diagnostic_task(tmp_path):
    settings = build_settings(tmp_path)
    _project, session = prepare_session(settings)
    service = ScannerService.from_settings(settings)
    service.update_config({"tools": {"nmap": {"binary_path": str(tmp_path / "missing-nmap")}}})

    task = service.create_scan_task(
        session_identifier=session.id,
        task_type="port_scan",
        input_data={"target_host": "10.10.10.5"},
    )

    assert task.status.value == "failed"
    assert "binary was not found" in task.error
    assert task.result_json["ok"] is False


def test_non_zero_exit_records_stderr_artifact(tmp_path):
    settings = build_settings(tmp_path)
    binary = tmp_path / "nmap"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    _project, session = prepare_session(settings)
    runner = FakeRunner(ProcessResult(argv=[str(binary)], return_code=2, stdout="", stderr="bad target"))
    service = ScannerService(settings=settings, runner=runner)
    service.update_config({"tools": {"nmap": {"binary_path": str(binary)}}})

    task = service.create_scan_task(
        session_identifier=session.id,
        task_type="port_scan",
        input_data={"target_host": "10.10.10.5"},
    )

    assert task.status.value == "failed"
    assert task.result_json["stderr_path"].endswith("stderr.txt")
    assert task.result_json["error"] == "bad target"


def test_successful_nmap_task_persists_structured_results_and_candidates(tmp_path):
    settings = build_settings(tmp_path)
    binary = tmp_path / "nmap"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    _project, session = prepare_session(settings)
    runner = FakeRunner(ProcessResult(argv=[str(binary)], return_code=0, stdout=NMAP_XML, stderr=""))
    service = ScannerService(settings=settings, runner=runner)
    service.update_config({"tools": {"nmap": {"binary_path": str(binary)}}})

    task = service.create_scan_task(
        session_identifier=session.id,
        task_type="port_scan",
        input_data={"target_host": "10.10.10.5", "ports": [22]},
    )

    storage = SQLiteStorage(settings.sqlite_path)
    assert runner.argv is not None
    assert task.status.value == "succeeded"
    assert task.result_json["structured"]["open_ports"][0]["service"] == "ssh"
    assert TaskRepository(storage).get(task.public_id).id == task.id
    assert EvidenceRepository(storage).list(session_id=session.id)[0].evidence_type == "service"
    assert AttackPathNodeRepository(storage).list(session_id=session.id)[0].stage == "enumeration"
    events = EventRepository(storage).list(session_id=session.id, limit=None, descending=False)
    assert [event.event_kind for event in events] == ["task.started", "scanner.output", "task.completed"]


def test_scan_task_rejects_target_outside_selected_session(tmp_path):
    settings = build_settings(tmp_path)
    _project, session = prepare_session(settings)
    service = ScannerService.from_settings(settings)

    try:
        service.create_scan_task(
            session_identifier=session.id,
            task_type="port_scan",
            input_data={"target_host": "10.10.10.6"},
        )
    except ValueError as exc:
        assert "outside the selected session target" in str(exc)
    else:
        raise AssertionError("Expected scanner target validation failure.")


def test_scan_task_rejects_bare_ipv6_target_outside_selected_session(tmp_path):
    settings = build_settings(tmp_path)
    project = ProjectService.from_settings(settings).create_project(name="IPv6")
    session = TargetSessionService.from_settings(settings).create_session(
        project_identifier=project.id,
        name="IPv6 target",
        target_value="2001:db8::1",
        target_type=TargetType.IP,
    )
    service = ScannerService.from_settings(settings)

    try:
        service.create_scan_task(
            session_identifier=session.id,
            task_type="port_scan",
            input_data={"target_host": "2001:dead::2"},
        )
    except ValueError as exc:
        assert "2001:dead::2" in str(exc)
        assert "2001:db8::1" in str(exc)
    else:
        raise AssertionError("Expected scanner target validation failure.")


def test_ffuf_uses_configured_default_wordlist_and_extra_args(tmp_path):
    settings = build_settings(tmp_path)
    wordlist = tmp_path / "words.txt"
    wordlist.write_text("admin\n", encoding="utf-8")
    binary = tmp_path / "ffuf"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    _project, session = prepare_session(settings)
    runner = FakeRunner(ProcessResult(argv=[str(binary)], return_code=0, stdout=FFUF_JSON, stderr=""))
    service = ScannerService(settings=settings, runner=runner)
    service.update_config(
        {
            "tools": {
                "ffuf": {
                    "binary_path": str(binary),
                    "default_wordlist": str(wordlist),
                    "extra_args": ["-rate", "25"],
                }
            }
        }
    )

    task = service.create_scan_task(
        session_identifier=session.id,
        task_type="dir_scan",
        input_data={"base_url": "http://10.10.10.5"},
    )

    assert task.status.value == "succeeded"
    assert task.input_json["wordlist"] == str(wordlist)
    assert runner.argv is not None
    assert runner.argv[-2:] == ["-rate", "25"]


def test_process_runner_streams_stdout_and_stderr_to_artifacts(tmp_path):
    stdout_path = tmp_path / "stdout.txt"
    stderr_path = tmp_path / "stderr.txt"
    observed: list[tuple[str, str, str]] = []

    result = ProcessRunner().run(
        argv=[
            sys.executable,
            "-c",
            (
                "import sys, time; "
                "print('first', flush=True); "
                "print('warn', file=sys.stderr, flush=True); "
                "time.sleep(0.1); "
                "print('second', flush=True)"
            ),
        ],
        cwd=tmp_path,
        timeout_seconds=5,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        on_output=lambda stream_name, chunk: observed.append(
            (stream_name, chunk, stdout_path.read_text(encoding="utf-8") if stdout_path.exists() else "")
        ),
    )

    assert result.return_code == 0
    assert result.stdout == "first\nsecond\n"
    assert result.stderr == "warn\n"
    assert stdout_path.read_text(encoding="utf-8") == "first\nsecond\n"
    assert stderr_path.read_text(encoding="utf-8") == "warn\n"
    assert ("stdout", "first\n", "first\n") in observed
    assert ("stderr", "warn\n", "first\n") in observed


def test_process_runner_terminates_when_cancel_requested(tmp_path):
    cancel = {"requested": False}

    result = ProcessRunner().run(
        argv=[
            sys.executable,
            "-c",
            "import time; print('ready', flush=True); time.sleep(10)",
        ],
        cwd=tmp_path,
        timeout_seconds=20,
        stdout_path=tmp_path / "stdout.txt",
        stderr_path=tmp_path / "stderr.txt",
        on_output=lambda _stream_name, _chunk: cancel.__setitem__("requested", True),
        cancel_requested=lambda: cancel["requested"],
    )

    assert result.cancelled is True
    assert "ready\n" == result.stdout
    assert "Process cancelled." in result.stderr


def test_enqueued_scan_task_executes_outside_creation_path(tmp_path):
    settings = build_settings(tmp_path)
    binary = tmp_path / "nmap"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    _project, session = prepare_session(settings)
    runner = FakeRunner(ProcessResult(argv=[str(binary)], return_code=0, stdout=NMAP_XML, stderr=""))
    service = ScannerService(settings=settings, runner=runner)
    service.update_config({"tools": {"nmap": {"binary_path": str(binary)}}})

    task = service.enqueue_scan_task(
        session_identifier=session.id,
        task_type="port_scan",
        input_data={"target_host": "10.10.10.5"},
    )

    assert task.status.value == "pending"
    assert runner.argv is None
    executed = service.execute_pending_task(task.id)
    assert executed.status.value == "succeeded"
    assert runner.argv is not None


def test_phase3_api_routes_expose_tools_and_tasks(tmp_path, monkeypatch):
    settings = build_settings(tmp_path)
    _project, session = prepare_session(settings)

    monkeypatch.setattr("server.lifecycle.get_settings", lambda: settings)
    monkeypatch.setattr("app.scanner_service.get_settings", lambda: settings)

    with TestClient(create_app()) as client:
        patch = client.patch(
            "/api/tools/config",
            json={"tools": {"nmap": {"binary_path": str(tmp_path / "missing-nmap")}}},
        )
        assert patch.status_code == 200

        status = client.get("/api/tools/status")
        assert status.status_code == 200
        assert any(item["name"] == "nmap" and item["available"] is False for item in status.json()["tools"])

        created = client.post(
            f"/api/sessions/{session.id}/tasks",
            json={"task_type": "port_scan", "input": {"target_host": "10.10.10.5"}},
        )
        assert created.status_code == 201
        task = created.json()["task"]
        assert task["status"] == "pending"

        listed = client.get(f"/api/sessions/{session.id}/tasks")
        assert listed.status_code == 200
        assert listed.json()["tasks"][0]["id"] == task["id"]
