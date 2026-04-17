import re
from pathlib import Path

BLOCK_PATTERNS = [
    re.compile(r"rm\s+-\S*r\S*f\s+(/|~|\$HOME)"),  # Direct recursive deletion of system/home roots.
    re.compile(r"dd\s+if=.*of=\/dev\/"),  # Raw writes to block devices are treated as destructive.
    re.compile(r"mkfs\."),  # Filesystem formatting commands should never run unattended.
    re.compile(r">\s*\/dev\/(sda|hda|nvme)"),  # Shell redirection into disk devices is equally destructive.
    re.compile(r"shutdown|reboot|halt"),  # Prevent host shutdown or reboot commands.
    re.compile(r"(^|\s)(format)(\s|$)", re.IGNORECASE),  # Windows disk format commands.
    re.compile(r"Remove-Item\s+.+-Recurse.+-Force", re.IGNORECASE),  # Forced recursive deletion in PowerShell.
    re.compile(r"(^|\s)(del|erase)\s+.+(/[sp]|/f)", re.IGNORECASE),  # High-risk delete forms in cmd.exe.
    re.compile(r"(^|\s)(rd|rmdir)\s+.+/s", re.IGNORECASE),  # Recursive directory deletion in cmd.exe.
]

CONFIRM_PATTERNS = [
    re.compile(r"rm\s+-\S*[rf]"),  # Other recursive/forced deletes still require confirmation.
    re.compile(r"sudo\s+"),  # Escalation attempts should always be operator-approved.
    re.compile(r"curl\s+.*\|\s*(sh|bash|zsh)"),  # Piping downloaded content into a shell is risky.
    re.compile(r"wget\s+.*\|\s*(sh|bash|zsh)"),  # Same risk profile as curl | sh.
    re.compile(r"npm\s+publish"),  # Publishing affects external systems and should be explicit.
    re.compile(r"git\s+push\s+.*--force"),  # Force-push can rewrite shared history.
    re.compile(r"git\s+reset\s+--hard"),  # Hard reset discards work tree state.
    re.compile(r"Remove-Item\b", re.IGNORECASE),  # Any PowerShell delete command needs review.
    re.compile(r"(^|\s)(del|erase)\b", re.IGNORECASE),  # cmd.exe delete commands need confirmation.
    re.compile(r"(^|\s)(rd|rmdir)\b", re.IGNORECASE),  # Directory removal in cmd.exe needs confirmation.
    re.compile(r"Invoke-Expression\b", re.IGNORECASE),  # Dynamic PowerShell execution hides intent.
    re.compile(r"powershell.*-enc", re.IGNORECASE),  # Encoded PowerShell commands are harder to audit.
]

SENSITIVE_PATTERNS = [
    re.compile(r"\.env(\.|$)"),  # Environment files often contain credentials.
    re.compile(r"\.aws\/credentials"),  # AWS credential store.
    re.compile(r"\.ssh\/(id_rsa|id_ed25519)$"),  # Common private SSH key paths.
    re.compile(r"secrets?\.(json|yaml|yml)$", re.IGNORECASE),  # Secret material in common config formats.
]


def detect_danger(command: str) -> str:
    for pattern in BLOCK_PATTERNS:
        if pattern.search(command):
            return "BLOCK"
    for pattern in CONFIRM_PATTERNS:
        if pattern.search(command):
            return "CONFIRM"
    return "SAFE"


def resolve_safe_path(user_path: str) -> Path:
    base_dir = Path.cwd().resolve()
    path = Path(user_path)

    if path.is_absolute():
        raise ValueError("Absolute path not allowed")

    # Resolve relative paths against the current workspace and reject any attempt
    # to escape that root through `..` traversal.
    target = (base_dir / path).resolve()

    if base_dir not in target.parents and target != base_dir:
        raise ValueError("Path traversal detected")

    return target


def is_sensitive_path(path: str) -> bool:
    for pattern in SENSITIVE_PATTERNS:
        if pattern.search(path):
            return True
    return False
