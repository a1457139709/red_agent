from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from tools import bash as bash_module
from tools import deleteFile as delete_module
from tools import editFile as edit_module
from tools import listDir as list_module
from tools import readFile as read_module
from tools import search as search_module
from tools import webFetch as web_fetch_module
from tools import webSearch as web_search_module
from tools import writeFile as write_module
from tools.factory import ToolDefinition, ToolPresentation, ToolResultEnvelope, build_tool
from tools.policy import CapabilityTier
from tools import session_security_tools as security_module


def _invoke_tool(tool):
    def invoke(**kwargs):
        return tool.invoke(kwargs)

    return invoke


def _security_tool_handler(tool, presentation: ToolPresentation):
    def invoke(**kwargs):
        model_text = tool.invoke(kwargs)
        data = _extract_security_tool_data(str(model_text))
        summary = data.get("summary") or (str(model_text).splitlines()[0] if str(model_text) else "")
        return ToolResultEnvelope(
            summary=str(summary),
            model_text=str(model_text),
            data=data,
            presentation=presentation,
        )

    return invoke


def _extract_security_tool_data(text: str) -> dict[str, Any]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in reversed(lines[-3:]):
        if not line.startswith("{"):
            continue
        try:
            decoded = json.loads(line)
        except Exception:
            continue
        if isinstance(decoded, dict):
            return decoded
    return {"text": text}


class BashInput(BaseModel):
    command: str = Field(description="Shell command to execute.")
    shell: str | None = Field(
        default=None,
        description="Optional shell name such as powershell, bash, zsh, sh, or cmd.",
    )


class FilePathInput(BaseModel):
    file_path: str = Field(description="File path relative to the current working directory.")


class ReadFileInput(FilePathInput):
    offset: int | None = Field(default=None, description="Zero-based starting line offset.")
    limit: int | None = Field(default=None, description="Maximum number of lines to read.")


class WriteFileInput(FilePathInput):
    content: str = Field(description="Content to write.")


class EditFileInput(FilePathInput):
    old_string: str = Field(description="Existing string to replace; must appear exactly once.")
    new_string: str = Field(description="Replacement string.")


class ListDirInput(BaseModel):
    path: str = Field(default=".", description="Directory path to list.")


class SearchInput(BaseModel):
    query: str = Field(description="Text to search for.")
    file_path: str = Field(default=".", description="File or directory path to search.")


class WebFetchInput(BaseModel):
    url: str = Field(description="Absolute http(s) URL to fetch.")
    max_chars: int = Field(default=web_fetch_module.DEFAULT_MAX_CHARS, description="Maximum characters.")
    timeout_seconds: int = Field(
        default=web_fetch_module.DEFAULT_TIMEOUT_SECONDS,
        description="Network timeout in seconds.",
    )


class WebSearchInput(BaseModel):
    query: str = Field(description="Natural-language web search query.")
    max_results: int = Field(
        default=web_search_module.DEFAULT_MAX_RESULTS,
        description="Maximum number of results to return.",
    )
    timeout_seconds: int = Field(
        default=web_fetch_module.DEFAULT_TIMEOUT_SECONDS,
        description="Network timeout in seconds.",
    )


class DnsLookupInput(BaseModel):
    target: str = Field(description="Domain or hostname to query.")
    record_type: str = Field(default="A", description="DNS record type such as A, AAAA, CNAME, TXT, MX.")
    nameserver: str = Field(default="8.8.8.8", description="Resolver IP address.")
    timeout_seconds: int | None = Field(default=None, description="Request timeout in seconds.")


class HttpProbeInput(BaseModel):
    target: str = Field(description="Absolute URL target.")
    method: str = Field(default="GET", description="HTTP method.")
    max_body_chars: int | None = Field(default=None, description="Maximum response body characters.")
    timeout_seconds: int | None = Field(default=None, description="Request timeout in seconds.")
    headers: dict[str, Any] | None = Field(default=None, description="Optional request headers.")


class TlsInspectInput(BaseModel):
    target: str = Field(description="Host, host:port, or URL target.")
    port: int | None = Field(default=None, description="Optional TLS port override.")
    timeout_seconds: int | None = Field(default=None, description="Connection timeout in seconds.")


class BannerGrabInput(BaseModel):
    target: str = Field(description="Host or host:port target.")
    port: int | None = Field(default=None, description="Optional port override.")
    probe: str = Field(default="none", description="Probe mode such as none, http, or redis.")
    max_read_bytes: int | None = Field(default=None, description="Maximum bytes to read.")
    timeout_seconds: int | None = Field(default=None, description="Connection timeout in seconds.")


class PortScanInput(BaseModel):
    target: str = Field(description="Host, host:port, or URL target.")
    ports: list[int] | str | None = Field(default=None, description="Port list, e.g. [80,443] or '80,443'.")
    timeout_seconds: int | None = Field(default=None, description="Connection timeout in seconds.")


BASE_TOOL_DEFINITIONS: tuple[ToolDefinition, ...] = (
    build_tool(
        name="bash",
        description=(
            "Execute a shell command. Dangerous commands such as rm -rf pause for user "
            "confirmation. Long output is truncated automatically."
        ),
        input_model=BashInput,
        handler=_invoke_tool(bash_module.execute_command),
        capability=CapabilityTier.EXECUTE,
        presentation=ToolPresentation(title="BASH", group="shell", accent="yellow"),
    ),
    build_tool(
        name="delete_file",
        description="Delete the specified file.",
        input_model=FilePathInput,
        handler=_invoke_tool(delete_module.delete_file),
        capability=CapabilityTier.DESTRUCTIVE,
        is_destructive=True,
        presentation=ToolPresentation(title="DELETE FILE", group="file", accent="red"),
    ),
    build_tool(
        name="edit_file",
        description=(
            "Replace a specific string in a file. old_string must appear exactly once, "
            "or the edit is rejected. Use read_file first to confirm the target text."
        ),
        input_model=EditFileInput,
        handler=_invoke_tool(edit_module.edit_file),
        capability=CapabilityTier.WRITE,
        presentation=ToolPresentation(title="EDIT FILE", group="file", accent="magenta"),
    ),
    build_tool(
        name="list_dir",
        description="List files and directories in the target folder without recursion.",
        input_model=ListDirInput,
        handler=_invoke_tool(list_module.list_dir),
        capability=CapabilityTier.READ,
        is_concurrency_safe=True,
        is_read_only=True,
        presentation=ToolPresentation(title="LIST DIR", group="file", accent="cyan"),
    ),
    build_tool(
        name="read_file",
        description=(
            "Read a local file. For large files, prefer offset + limit to read in chunks. "
            "Output includes line numbers for easier navigation."
        ),
        input_model=ReadFileInput,
        handler=_invoke_tool(read_module.read_file),
        capability=CapabilityTier.READ,
        is_concurrency_safe=True,
        is_read_only=True,
        presentation=ToolPresentation(title="READ FILE", group="file", accent="cyan"),
    ),
    build_tool(
        name="search",
        description="Search file contents and return complete matching lines.",
        input_model=SearchInput,
        handler=_invoke_tool(search_module.search),
        capability=CapabilityTier.READ,
        is_concurrency_safe=True,
        is_read_only=True,
        presentation=ToolPresentation(title="SEARCH", group="file", accent="cyan"),
    ),
    build_tool(
        name="web_fetch",
        description="Fetch an http(s) page and extract readable text.",
        input_model=WebFetchInput,
        handler=_invoke_tool(web_fetch_module.web_fetch),
        capability=CapabilityTier.READ,
        is_concurrency_safe=True,
        is_read_only=True,
        presentation=ToolPresentation(title="WEB FETCH", group="web", accent="blue"),
    ),
    build_tool(
        name="web_search",
        description="Search the public web for a query and return a compact result list.",
        input_model=WebSearchInput,
        handler=_invoke_tool(web_search_module.web_search),
        capability=CapabilityTier.READ,
        is_concurrency_safe=True,
        is_read_only=True,
        presentation=ToolPresentation(title="WEB SEARCH", group="web", accent="blue"),
    ),
    build_tool(
        name="write_file",
        description="Write content to a file, creating or overwriting it.",
        input_model=WriteFileInput,
        handler=_invoke_tool(write_module.write_file),
        capability=CapabilityTier.WRITE,
        presentation=ToolPresentation(title="WRITE FILE", group="file", accent="magenta"),
    ),
)


SESSION_SECURITY_TOOL_DEFINITIONS: tuple[ToolDefinition, ...] = (
    build_tool(
        name="dns_lookup",
        description="Run a DNS lookup using the typed security runtime and return a structured summary.",
        input_model=DnsLookupInput,
        handler=_security_tool_handler(
            security_module.dns_lookup,
            ToolPresentation(title="DNS LOOKUP", group="security", accent="green"),
        ),
        capability=CapabilityTier.EXECUTE,
        presentation=ToolPresentation(title="DNS LOOKUP", group="security", accent="green"),
    ),
    build_tool(
        name="http_probe",
        description="Probe an HTTP(S) target with the typed security runtime and return structured metadata.",
        input_model=HttpProbeInput,
        handler=_security_tool_handler(
            security_module.http_probe,
            ToolPresentation(title="HTTP PROBE", group="security", accent="green"),
        ),
        capability=CapabilityTier.EXECUTE,
        presentation=ToolPresentation(title="HTTP PROBE", group="security", accent="green"),
    ),
    build_tool(
        name="tls_inspect",
        description="Inspect TLS certificate and negotiated ciphers for a host or host:port target.",
        input_model=TlsInspectInput,
        handler=_security_tool_handler(
            security_module.tls_inspect,
            ToolPresentation(title="TLS INSPECT", group="security", accent="green"),
        ),
        capability=CapabilityTier.EXECUTE,
        presentation=ToolPresentation(title="TLS INSPECT", group="security", accent="green"),
    ),
    build_tool(
        name="banner_grab",
        description="Grab a service banner from a host:port target using the typed security runtime.",
        input_model=BannerGrabInput,
        handler=_security_tool_handler(
            security_module.banner_grab,
            ToolPresentation(title="BANNER GRAB", group="security", accent="green"),
        ),
        capability=CapabilityTier.EXECUTE,
        presentation=ToolPresentation(title="BANNER GRAB", group="security", accent="green"),
    ),
    build_tool(
        name="port_scan",
        description="Run a typed TCP port scan and return open/closed status for requested ports.",
        input_model=PortScanInput,
        handler=_security_tool_handler(
            security_module.port_scan,
            ToolPresentation(title="PORT SCAN", group="security", accent="green"),
        ),
        capability=CapabilityTier.EXECUTE,
        presentation=ToolPresentation(title="PORT SCAN", group="security", accent="green"),
    ),
)


RUNTIME_TOOL_DEFINITIONS: tuple[ToolDefinition, ...] = (
    *BASE_TOOL_DEFINITIONS,
    *SESSION_SECURITY_TOOL_DEFINITIONS,
)
