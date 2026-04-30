from pydantic import ValidationError

from tools import (
    build_tool_registry,
    get_runtime_tool_definitions,
    get_runtime_tools,
)
from tools.definitions import PortScanInput
from tools.executor import ToolExecutionEvent, ToolExecutor
from tools.factory import ToolResultEnvelope
from tools.policy import CapabilityTier


def test_factory_registry_matches_runtime_tool_definitions():
    definitions = get_runtime_tool_definitions()
    registry = build_tool_registry()

    assert set(registry) == {definition.name for definition in definitions}
    assert set(registry) == {tool.name for tool in get_runtime_tools()}
    assert registry["bash"].input_model.model_json_schema()["properties"]["command"]["type"] == "string"
    assert registry["bash"].build_langchain_tool().args_schema.model_json_schema()["properties"]["command"]["type"] == "string"


def test_tool_definition_metadata_uses_fail_closed_defaults():
    definition_by_name = {definition.name: definition for definition in get_runtime_tool_definitions()}

    write_file = definition_by_name["write_file"]
    read_file = definition_by_name["read_file"]

    assert write_file.capability == CapabilityTier.WRITE
    assert not write_file.is_concurrency_safe
    assert not write_file.is_read_only
    assert read_file.capability == CapabilityTier.READ
    assert read_file.is_concurrency_safe
    assert read_file.is_read_only


def test_pydantic_tool_input_validation_rejects_invalid_port_scan_ports():
    try:
        PortScanInput.model_validate({"target": "127.0.0.1", "ports": {"bad": "shape"}})
        assert False, "expected ValidationError"
    except ValidationError:
        pass


def test_tool_executor_emits_structured_tool_payload():
    events: list[ToolExecutionEvent] = []
    executor = ToolExecutor(build_tool_registry(), on_tool_event=events.append)

    result = executor.execute("list_dir", {"path": "."})

    assert isinstance(result, str)
    assert [event.event_type for event in events] == ["tool_invoked", "tool_completed"]
    assert events[0].input_payload == {"path": "."}
    assert events[1].output_payload["model_text"]
    assert events[1].output_payload["summary"]
    assert events[1].to_payload()["input"] == {"path": "."}


def test_tool_definition_run_returns_envelope_without_langchain_tool_wrapper():
    definition_by_name = {definition.name: definition for definition in get_runtime_tool_definitions()}

    envelope = definition_by_name["list_dir"].run({"path": "."})

    assert isinstance(envelope, ToolResultEnvelope)
    assert envelope.model_text
    assert envelope.summary
