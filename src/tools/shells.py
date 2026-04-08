from __future__ import annotations

from dataclasses import dataclass
import os
import shutil


SUPPORTED_SHELL_NAMES = ("bash", "cmd", "powershell", "pwsh", "sh", "zsh")

_ALIAS_TO_CANONICAL = {
    "bash": "bash",
    "bash.exe": "bash",
    "cmd": "cmd",
    "cmd.exe": "cmd",
    "powershell": "powershell",
    "powershell.exe": "powershell",
    "pwsh": "powershell",
    "pwsh.exe": "powershell",
    "sh": "sh",
    "zsh": "zsh",
}


@dataclass(frozen=True, slots=True)
class ShellSpec:
    name: str
    executable: str
    args_prefix: tuple[str, ...]

    def build_command(self, command: str) -> list[str]:
        return [self.executable, *self.args_prefix, command]


class ShellResolutionError(ValueError):
    """Raised when a requested shell name is invalid or unavailable."""


_SHELL_CANDIDATES: dict[str, tuple[str, ...]] = {
    "bash": ("bash",),
    "cmd": ("cmd",),
    "powershell": ("powershell", "pwsh"),
    "sh": ("sh",),
    "zsh": ("zsh",),
}

_SHELL_ARGUMENTS: dict[str, tuple[str, ...]] = {
    "bash": ("-lc",),
    "cmd": ("/d", "/s", "/c"),
    "powershell": ("-NoLogo", "-NoProfile", "-NonInteractive", "-Command"),
    "sh": ("-lc",),
    "zsh": ("-lc",),
}


def normalize_shell_name(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if not normalized:
        return None
    canonical = _ALIAS_TO_CANONICAL.get(normalized)
    if canonical is None:
        supported = ", ".join(SUPPORTED_SHELL_NAMES)
        raise ShellResolutionError(
            f"Unsupported shell '{value.strip()}'. Supported shells: {supported}."
        )
    return canonical


def resolve_shell_spec(requested_shell: str | None = None) -> ShellSpec:
    if requested_shell is None:
        return _resolve_default_shell()

    shell_name = normalize_shell_name(requested_shell)
    if shell_name is None:
        return _resolve_default_shell()

    executable = _find_executable(_SHELL_CANDIDATES[shell_name])
    if executable is None:
        expected = ", ".join(_SHELL_CANDIDATES[shell_name])
        raise ShellResolutionError(
            f"Shell '{shell_name}' is not available on this host. Expected one of: {expected}."
        )
    return ShellSpec(
        name=shell_name,
        executable=executable,
        args_prefix=_SHELL_ARGUMENTS[shell_name],
    )


def ensure_shell_available(requested_shell: str) -> str:
    return resolve_shell_spec(requested_shell).name


def _resolve_default_shell() -> ShellSpec:
    candidates = ("powershell", "cmd") if os.name == "nt" else ("bash", "sh")
    for candidate in candidates:
        executable = _find_executable(_SHELL_CANDIDATES[candidate])
        if executable is None:
            continue
        return ShellSpec(
            name=candidate,
            executable=executable,
            args_prefix=_SHELL_ARGUMENTS[candidate],
        )

    supported = ", ".join(candidates)
    raise ShellResolutionError(
        f"No supported default shell is available on this host. Checked: {supported}."
    )


def _find_executable(candidates: tuple[str, ...]) -> str | None:
    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    return None
