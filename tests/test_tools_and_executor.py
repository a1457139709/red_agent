import subprocess
from pathlib import Path

import tools.bash as bash_module
import tools.webFetch as web_fetch_module
import tools.webSearch as web_search_module
from tools import build_tool_registry, get_tools
from tools.executor import ToolExecutionError, ToolExecutor
from tools.policy import CapabilityTier
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

    assert "classified as high risk" in block_result
    assert "user declined confirmation" in confirm_result


def test_tool_executor_unknown_tool_is_audited_and_classified():
    audits = []
    tool_events = []
    executor = ToolExecutor(
        build_tool_registry(),
        on_audit=audits.append,
        on_tool_event=tool_events.append,
    )

    try:
        executor.execute("missing_tool", {"value": 1})
        assert False, "expected ToolExecutionError"
    except ToolExecutionError as exc:
        assert exc.tool_name == "missing_tool"
        assert exc.capability == CapabilityTier.READ
        assert exc.error == "Unknown tool requested: missing_tool"

    assert [event.event_type for event in tool_events] == ["tool_invoked", "tool_failed"]
    assert tool_events[1].error == "Unknown tool requested: missing_tool"
    assert [event.event_type for event in audits] == ["operation_failed"]
    assert audits[0].reason == "unknown_tool"
    assert audits[0].tool_name == "missing_tool"


def test_bash_decodes_utf8_stdout(monkeypatch):
    seen_timeout = None

    def fake_run(*args, **kwargs):
        nonlocal seen_timeout
        seen_timeout = kwargs.get("timeout")
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout="\u4e2d\u6587\u8f93\u51fa".encode("utf-8"),
            stderr=b"",
        )

    monkeypatch.setattr(bash_module.subprocess, "run", fake_run)

    result = bash_module.execute_command.invoke({"command": "echo demo"})

    assert seen_timeout == bash_module.DEFAULT_COMMAND_TIMEOUT_SECONDS
    assert "[stdout]:" in result
    assert "\u4e2d\u6587\u8f93\u51fa" in result


def test_bash_decodes_gbk_stdout(monkeypatch):
    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout="\u4e2d\u6587\u8f93\u51fa".encode("gbk"),
            stderr=b"",
        )

    monkeypatch.setattr(bash_module.subprocess, "run", fake_run)

    result = bash_module.execute_command.invoke({"command": "echo demo"})

    assert "[stdout]:" in result
    assert "\u4e2d\u6587\u8f93\u51fa" in result


def test_bash_preserves_stdout_and_stderr_envelope(monkeypatch):
    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout="\u6807\u51c6\u8f93\u51fa".encode("utf-8"),
            stderr="\u9519\u8bef\u8f93\u51fa".encode("utf-8"),
        )

    monkeypatch.setattr(bash_module.subprocess, "run", fake_run)

    result = bash_module.execute_command.invoke({"command": "echo demo"})

    assert "[stdout]:" in result
    assert "\u6807\u51c6\u8f93\u51fa" in result
    assert "[stderr]:" in result
    assert "\u9519\u8bef\u8f93\u51fa" in result


def test_bash_reports_non_zero_exit_code(monkeypatch):
    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=7,
            stdout="\u547d\u4ee4\u5931\u8d25".encode("utf-8"),
            stderr="\u8be6\u7ec6\u9519\u8bef".encode("utf-8"),
        )

    monkeypatch.setattr(bash_module.subprocess, "run", fake_run)

    result = bash_module.execute_command.invoke({"command": "exit 7"})

    assert "Command failed with exit code 7." in result
    assert "[stdout]:" in result
    assert "\u547d\u4ee4\u5931\u8d25" in result
    assert "[stderr]:" in result
    assert "\u8be6\u7ec6\u9519\u8bef" in result


def test_bash_reports_timeout(monkeypatch):
    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(
            cmd=args[0],
            timeout=kwargs["timeout"],
            output="\u90e8\u5206\u8f93\u51fa".encode("utf-8"),
            stderr="\u4ecd\u5728\u8fd0\u884c".encode("utf-8"),
        )

    monkeypatch.setattr(bash_module.subprocess, "run", fake_run)

    result = bash_module.execute_command.invoke({"command": "sleep 999"})

    assert (
        f"Command timed out after {bash_module.DEFAULT_COMMAND_TIMEOUT_SECONDS} seconds."
        in result
    )
    assert "[stdout]:" in result
    assert "\u90e8\u5206\u8f93\u51fa" in result
    assert "[stderr]:" in result
    assert "\u4ecd\u5728\u8fd0\u884c" in result


def test_search_stays_within_workspace(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    sample = Path("sample.txt")
    sample.write_text("needle\n", encoding="utf-8")

    found = search.invoke({"query": "needle", "file_path": "."})
    escaped = search.invoke({"query": "needle", "file_path": ".."})

    assert "sample.txt:1 needle" in found
    assert "Path traversal detected" in escaped


class FakeHTTPResponse:
    def __init__(
        self,
        *,
        body: bytes,
        url: str,
        content_type: str = "text/html; charset=utf-8",
        status: int = 200,
    ) -> None:
        self._body = body
        self._url = url
        self.status = status
        self.code = status
        self.headers = {"Content-Type": content_type}

    def read(self):
        return self._body

    def geturl(self):
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_web_fetch_extracts_readable_text(monkeypatch):
    def fake_urlopen(request, timeout):
        assert request.full_url == "https://example.com/page"
        assert timeout == web_fetch_module.DEFAULT_TIMEOUT_SECONDS
        return FakeHTTPResponse(
            url="https://example.com/page",
            body=(
                b"<html><head><title>Example Page</title><style>.x{}</style></head>"
                b"<body><h1>Hello</h1><p>World</p><script>alert(1)</script></body></html>"
            ),
        )

    monkeypatch.setattr(web_fetch_module, "urlopen", fake_urlopen)

    result = web_fetch_module.web_fetch.invoke({"url": "https://example.com/page"})

    assert 'type="web_fetch"' in result
    assert "Title: Example Page" in result
    assert "Hello" in result
    assert "World" in result
    assert "alert(1)" not in result


def test_web_fetch_rejects_non_http_urls():
    result = web_fetch_module.web_fetch.invoke({"url": "file:///tmp/demo.txt"})

    assert "only absolute http(s) URLs are supported" in result


def test_web_search_formats_duckduckgo_results(monkeypatch):
    def fake_urlopen(request, timeout):
        assert "q=example+query" in request.full_url
        assert timeout == web_search_module.DEFAULT_TIMEOUT_SECONDS
        return FakeHTTPResponse(
            url=request.full_url,
            body=(
                b'<html><body>'
                b'<a class="result__a" href="https://example.com/a">Result A</a>'
                b'<div class="result__snippet">Snippet A</div>'
                b'<a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fb">'
                b'Result B</a>'
                b'<div class="result__snippet">Snippet B</div>'
                b'</body></html>'
            ),
        )

    monkeypatch.setattr(web_search_module, "urlopen", fake_urlopen)

    result = web_search_module.web_search.invoke(
        {"query": "example query", "max_results": 2}
    )

    assert 'type="web_search"' in result
    assert "1. Result A" in result
    assert "URL: https://example.com/a" in result
    assert "Snippet: Snippet A" in result
    assert "2. Result B" in result
    assert "URL: https://example.com/b" in result


