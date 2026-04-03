import locale
import subprocess

from langchain.tools import tool

from utils.truncate import truncate_tool_output

from .registry import register_tool

DEFAULT_COMMAND_TIMEOUT_SECONDS = 30

tool_schema = {
    "type": "object",
    "properties": {
        "command": {
            "type": "string",
            "description": "Shell command to execute",
        },
    },
    "required": ["command"],
}


def _candidate_encodings() -> list[str]:
    encodings = ["utf-8", "utf-8-sig"]
    preferred = locale.getpreferredencoding(False)
    if preferred:
        encodings.append(preferred)
    encodings.extend(["gbk", "cp936"])

    seen: set[str] = set()
    ordered: list[str] = []
    for encoding in encodings:
        normalized = encoding.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(encoding)
    return ordered


def _decode_stream(data: bytes | str | None) -> str:
    if data is None:
        return ""
    if isinstance(data, str):
        return data
    if not data:
        return ""

    for encoding in _candidate_encodings():
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue

    return data.decode("utf-8", errors="replace")


def _format_shell_output(*, prefix: str | None = None, stdout: str = "", stderr: str = "") -> str:
    parts = []
    if prefix:
        parts.append(prefix)
    if stdout:
        parts.append(f"[stdout]:\n{stdout}")
    if stderr:
        parts.append(f"[stderr]:\n{stderr}")
    return truncate_tool_output("bash", "\n".join(parts))


def _format_timeout_seconds(timeout: float | int | None) -> str:
    if timeout is None:
        return str(DEFAULT_COMMAND_TIMEOUT_SECONDS)
    if isinstance(timeout, float) and timeout.is_integer():
        return str(int(timeout))
    return str(timeout)


@register_tool
@tool(
    "bash",
    description=(
        "Execute a shell command. Dangerous commands such as rm -rf pause for user "
        "confirmation. Long output is truncated automatically."
    ),
    args_schema=tool_schema,
)
def execute_command(command: str) -> str:
    """
    Executes a shell command and returns its output.

    Args:
        command (str): The shell command to execute.
    """
    try:
        result = subprocess.run(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=DEFAULT_COMMAND_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = _decode_stream(exc.output).strip()
        stderr = _decode_stream(exc.stderr).strip()
        timeout_seconds = _format_timeout_seconds(exc.timeout)
        return _format_shell_output(
            prefix=f"Command timed out after {timeout_seconds} seconds.",
            stdout=stdout,
            stderr=stderr,
        )
    except Exception as exc:
        return "Command execution failed: " + str(exc)

    stdout = _decode_stream(result.stdout).strip()
    stderr = _decode_stream(result.stderr).strip()
    if result.returncode != 0:
        return _format_shell_output(
            prefix=f"Command failed with exit code {result.returncode}.",
            stdout=stdout,
            stderr=stderr,
        )
    return _format_shell_output(stdout=stdout, stderr=stderr)
