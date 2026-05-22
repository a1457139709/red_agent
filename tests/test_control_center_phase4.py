from __future__ import annotations

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from agent.settings import Settings
from app.ctf_agent_service import CTFAgentService, EnumerationPlanner
from app.project_service import ProjectService
from app.scanner_service import ScannerService
from app.target_session_service import TargetSessionService
from models.control_center import Event, TargetType, Task
from scanners.process_runner import ProcessResult
from server.app import create_app
from storage.repositories.control_center import EventRepository, TaskRepository
from storage.sqlite import SQLiteStorage


NMAP_HTTP_XML = """<?xml version="1.0"?>
<nmaprun>
  <host>
    <address addr="10.10.10.5" addrtype="ipv4"/>
    <ports>
      <port protocol="tcp" portid="22">
        <state state="open"/>
        <service name="ssh" product="OpenSSH" version="8.9"/>
      </port>
      <port protocol="tcp" portid="80">
        <state state="open"/>
        <service name="http" product="nginx" version="1.24"/>
      </port>
    </ports>
  </host>
</nmaprun>
"""


NMAP_SSH_XML = """<?xml version="1.0"?>
<nmaprun>
  <host>
    <address addr="10.10.10.5" addrtype="ipv4"/>
    <ports>
      <port protocol="tcp" portid="22">
        <state state="open"/>
        <service name="ssh"/>
      </port>
    </ports>
  </host>
</nmaprun>
"""


FFUF_JSON = """{"results": [{"url": "http://10.10.10.5/admin", "status": 200, "length": 120, "words": 8, "lines": 4}]}"""


NUCLEI_JSONL = '{"template-id":"http/test","info":{"name":"HTTP Test","severity":"info"},"matched-at":"http://10.10.10.5/"}\n'


class RoutingRunner:
    def __init__(self) -> None:
        self.argvs: list[list[str]] = []

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
        self.argvs.append(list(argv))
        tool = str(argv[0])
        if tool.endswith("nmap"):
            stdout = NMAP_HTTP_XML
        elif tool.endswith("ffuf"):
            stdout = FFUF_JSON
        elif tool.endswith("nuclei"):
            stdout = NUCLEI_JSONL
        else:
            stdout = ""
        if stdout_path is not None:
            stdout_path.write_text(stdout, encoding="utf-8")
        if stderr_path is not None:
            stderr_path.write_text("", encoding="utf-8")
        if on_output is not None and stdout:
            on_output("stdout", stdout)
        return ProcessResult(argv=list(argv), return_code=0, stdout=stdout, stderr="")


class FakeToolCallingModel:
    def __init__(self, responses: list[AIMessage]) -> None:
        self.responses = list(responses)
        self.bound_tool_names: list[str] = []

    def bind_tools(self, tools):
        self.bound_tool_names = [tool.name for tool in tools]
        return self

    def invoke(self, _messages):
        return self.responses.pop(0)


def build_settings(tmp_path):
    return Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        working_directory=tmp_path,
    )


def prepare_session(settings):
    project = ProjectService.from_settings(settings).create_project(name="Phase 4")
    session = TargetSessionService.from_settings(settings).create_session(
        project_identifier=project.id,
        name="Target",
        target_value="10.10.10.5",
        target_type=TargetType.IP,
    )
    return project, session


def test_planner_selects_ffuf_only_for_http_services(tmp_path):
    settings = build_settings(tmp_path)
    _project, session = prepare_session(settings)
    port_task = Task.create(
        project_id=session.project_id,
        session_id=session.id,
        task_type="port_scan",
        executor="nmap",
        result_json={
            "structured": {
                "open_ports": [
                    {"port": 22, "protocol": "tcp", "service": "ssh"},
                    {"port": 80, "protocol": "tcp", "service": "http"},
                ]
            }
        },
    )

    plan = EnumerationPlanner().plan_after_port_scan(
        session=session,
        port_scan=port_task,
        default_wordlist=str(tmp_path / "words.txt"),
        nuclei_templates_path=None,
    )

    assert [item.task_type for item in plan.dir_scans] == ["dir_scan"]
    assert plan.dir_scans[0].input_data["base_url"] == "http://10.10.10.5"


def test_planner_does_not_start_nuclei_without_candidate_target(tmp_path):
    settings = build_settings(tmp_path)
    _project, session = prepare_session(settings)
    port_task = Task.create(
        project_id=session.project_id,
        session_id=session.id,
        task_type="port_scan",
        executor="nmap",
        result_json={"structured": {"open_ports": [{"port": 22, "protocol": "tcp", "service": "ssh"}]}},
    )

    plan = EnumerationPlanner().plan_after_port_scan(
        session=session,
        port_scan=port_task,
        default_wordlist=str(tmp_path / "words.txt"),
        nuclei_templates_path=str(tmp_path / "templates"),
    )

    assert plan.dir_scans == []
    assert plan.poc_scans == []
    assert "No HTTP/HTTPS services" in plan.next_actions[0]


def test_ctf_agent_service_runs_llm_selected_scan_tools_and_records_events(tmp_path):
    settings = build_settings(tmp_path)
    _project, session = prepare_session(settings)
    wordlist = tmp_path / "words.txt"
    wordlist.write_text("admin\n", encoding="utf-8")
    templates = tmp_path / "templates"
    templates.mkdir()
    for tool_name in ("nmap", "ffuf", "nuclei"):
        binary = tmp_path / tool_name
        binary.write_text("#!/bin/sh\n", encoding="utf-8")
    runner = RoutingRunner()
    scanner = ScannerService(settings=settings, runner=runner)
    scanner.update_config(
        {
            "tools": {
                "nmap": {"binary_path": str(tmp_path / "nmap")},
                "ffuf": {"binary_path": str(tmp_path / "ffuf"), "default_wordlist": str(wordlist)},
                "nuclei": {"binary_path": str(tmp_path / "nuclei"), "templates_path": str(templates)},
            }
        }
    )
    model = FakeToolCallingModel(
        [
            AIMessage(
                content="I will run the selected scan tools.",
                tool_calls=[
                    {"name": "start_port_scan", "args": {"reason": "Initial recon"}, "id": "call-1", "type": "tool_call"},
                    {
                        "name": "start_dir_scan",
                        "args": {"base_url": "http://10.10.10.5", "reason": "HTTP service discovered"},
                        "id": "call-2",
                        "type": "tool_call",
                    },
                    {
                        "name": "start_poc_scan",
                        "args": {"target_url": "http://10.10.10.5", "reason": "Validate web findings"},
                        "id": "call-3",
                        "type": "tool_call",
                    },
                    {
                        "name": "suggest_terminal_command",
                        "args": {"command": "curl -I http://10.10.10.5", "reason": "Inspect headers"},
                        "id": "call-4",
                        "type": "tool_call",
                    },
                ],
            ),
            AIMessage(content="Enumeration tools completed.", tool_calls=[]),
        ]
    )
    service = CTFAgentService(settings=settings, scanner_service=scanner, model_factory=lambda _settings: model)

    agent_task = service.create_agent_task(session_identifier=session.id, message="枚举这台靶机")
    completed = service.run_agent_task(agent_task.id)

    storage = SQLiteStorage(settings.sqlite_path)
    task_types = [task.task_type for task in TaskRepository(storage).list(session_id=session.id, limit=None)]
    event_kinds = [event.event_kind for event in EventRepository(storage).list(session_id=session.id, limit=None, descending=False)]
    assert completed.status.value == "succeeded"
    assert completed.result_json["ok"] is True
    assert {"agent_analysis", "port_scan", "dir_scan", "poc_scan"}.issubset(set(task_types))
    assert "agent.tool_call.started" in event_kinds
    assert "agent.tool_call.completed" in event_kinds
    assert "agent.terminal_command.suggested" in event_kinds
    assert event_kinds[-1] == "agent.workflow.completed"


def test_failed_port_scan_tool_call_records_diagnostic_event(tmp_path):
    settings = build_settings(tmp_path)
    _project, session = prepare_session(settings)
    scanner = ScannerService.from_settings(settings)
    scanner.update_config({"tools": {"nmap": {"binary_path": str(tmp_path / "missing-nmap")}}})
    model = FakeToolCallingModel(
        [
            AIMessage(
                content="I will try the port scan.",
                tool_calls=[{"name": "start_port_scan", "args": {"reason": "Initial recon"}, "id": "call-1", "type": "tool_call"}],
            ),
            AIMessage(content="Port scan could not run with the current scanner configuration.", tool_calls=[]),
        ]
    )
    service = CTFAgentService(settings=settings, scanner_service=scanner, model_factory=lambda _settings: model)

    agent_task = service.create_agent_task(session_identifier=session.id, message="enumerate target")
    completed = service.run_agent_task(agent_task.id)
    events = EventRepository(SQLiteStorage(settings.sqlite_path)).list(session_id=session.id, limit=None, descending=False)
    tool_events = [event for event in events if event.event_kind == "agent.tool_call.completed"]
    scan_tasks = [
        task
        for task in TaskRepository(SQLiteStorage(settings.sqlite_path)).list(session_id=session.id, limit=None)
        if task.task_type == "port_scan"
    ]

    assert completed.status.value == "succeeded"
    assert completed.result_json["summary"] == "Port scan could not run with the current scanner configuration."
    assert tool_events
    assert scan_tasks
    assert scan_tasks[0].status.value == "failed"


def test_llm_agent_answers_general_questions_without_phase4_fallback(tmp_path):
    settings = build_settings(tmp_path)
    _project, session = prepare_session(settings)
    model = FakeToolCallingModel([AIMessage(content="我是 red-code Control Center Agent。", tool_calls=[])])
    service = CTFAgentService(settings=settings, model_factory=lambda _settings: model)

    agent_task = service.create_agent_task(session_identifier=session.id, message="你是什么模型")
    completed = service.run_agent_task(agent_task.id)

    events = EventRepository(SQLiteStorage(settings.sqlite_path)).list(session_id=session.id, limit=None, descending=False)
    event_kinds = [event.event_kind for event in events]
    assert completed.status.value == "succeeded"
    assert completed.result_json["response"] == "我是 red-code Control Center Agent。"
    assert "Select a target Session" not in completed.result_json["summary"]
    assert "conversation.completed" in event_kinds
    assert "conversation.delta" not in event_kinds
    assert "agent.summary" not in event_kinds
    assert "start_port_scan" in model.bound_tool_names


def test_llm_agent_tool_call_creates_scan_task_and_tool_events(tmp_path):
    settings = build_settings(tmp_path)
    _project, session = prepare_session(settings)
    binary = tmp_path / "nmap"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    scanner = ScannerService(settings=settings, runner=RoutingRunner())
    scanner.update_config({"tools": {"nmap": {"binary_path": str(binary)}}})
    model = FakeToolCallingModel(
        [
            AIMessage(
                content="I will scan the target.",
                tool_calls=[{"name": "start_port_scan", "args": {"reason": "Initial recon"}, "id": "call-1", "type": "tool_call"}],
            ),
            AIMessage(content="Port scan completed.", tool_calls=[]),
        ]
    )
    service = CTFAgentService(settings=settings, scanner_service=scanner, model_factory=lambda _settings: model)

    agent_task = service.create_agent_task(session_identifier=session.id, message="Use the available tools for the target")
    completed = service.run_agent_task(agent_task.id)

    storage = SQLiteStorage(settings.sqlite_path)
    task_types = [task.task_type for task in TaskRepository(storage).list(session_id=session.id, limit=None)]
    event_kinds = [event.event_kind for event in EventRepository(storage).list(session_id=session.id, limit=None, descending=False)]
    assert completed.status.value == "succeeded"
    assert "port_scan" in task_types
    assert "agent.tool_call.started" in event_kinds
    assert "agent.tool_call.completed" in event_kinds
    assert completed.result_json["tool_calls"][0]["name"] == "start_port_scan"


def test_phase4_agent_api_accepts_enumeration_message(tmp_path, monkeypatch):
    settings = build_settings(tmp_path)
    _project, session = prepare_session(settings)

    monkeypatch.setattr("server.lifecycle.get_settings", lambda: settings)

    with TestClient(create_app()) as client:
        response = client.post(
            f"/api/sessions/{session.id}/agent/messages",
            json={"message": "枚举这台靶机"},
        )

    assert response.status_code == 202
    payload = response.json()
    assert payload["task"]["task_type"] == "agent_analysis"
    assert payload["task"]["status"] in {"pending", "running", "succeeded"}


def test_event_websocket_streams_new_persisted_events(tmp_path, monkeypatch):
    settings = build_settings(tmp_path)
    project, session = prepare_session(settings)
    storage = SQLiteStorage(settings.sqlite_path)

    monkeypatch.setattr("server.lifecycle.get_settings", lambda: settings)
    monkeypatch.setattr("server.ws.get_settings", lambda: settings)

    with TestClient(create_app()) as client:
        with client.websocket_connect(f"/ws/events?session_id={session.id}&replay=true") as websocket:
            connected = websocket.receive_json()
            created = EventRepository(storage).create(
                Event.create(
                    project_id=project.id,
                    session_id=session.id,
                    event_kind="agent.summary",
                    level="info",
                    payload={"summary": "ready"},
                )
            )
            streamed = websocket.receive_json()

    assert connected["event_kind"] == "connection.connected"
    assert connected["sequence"] == 0
    assert streamed["event_id"] == created.id
    assert streamed["event_kind"] == "agent.summary"
    assert streamed["sequence"] > connected["sequence"]
