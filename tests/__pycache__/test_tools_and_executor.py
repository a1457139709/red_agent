from pathlib import Path

from tools import build_tool_registry, get_tools
from tools.executor import ToolExecutor
from tools.search import search


def test_build_tool_registry_matches_available_tools():
    registry = build_tool_registry()

    assert set(registry.keys()) == {tool.name for tool in get_tools()}


def test_tool_executor_handles_block_and_confirm():
    executor = ToolExecutor(
        build_tool_registry(),
        confirm_command=lambda command: False,
        on_info=lambda message: None,
    )

    block_result = executor.execute("bash", {"command": "format D:"})
    confirm_result = executor.execute("bash", {"command": "Remove-Item demo.txt -Force"})

    assert "拒绝执行" in block_result
    assert "用户拒绝" in confirm_result


def test_search_stays_within_workspace(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    sample = Path("sample.txt")
    sample.write_text("needle\n", encoding="utf-8")

    found = search.invoke({"query": "needle", "file_path": "."})
    escaped = search.invoke({"query": "needle", "file_path": ".."})

    assert "sample.txt:1 needle" in found
    assert "Path traversal detected" in escaped
