import re
from pathlib import Path

BLOCK_PATTERNS = [
    re.compile(r"rm\s+-\S*r\S*f\s+(/|~|\$HOME)"),# rm -rf / 或 rm -rf ~
    re.compile(r"dd\s+if=.*of=\/dev\/"),# dd 写入磁盘设备
    re.compile(r"mkfs\."), # 格式化文件系统
    re.compile(r">\s*\/dev\/(sda|hda|nvme)"),# 重定向写入磁盘
    re.compile(r"shutdown|reboot|halt"), # 系统关机重启
    re.compile(r"(^|\s)(format)(\s|$)", re.IGNORECASE), # Windows 磁盘格式化
    re.compile(r"Remove-Item\s+.+-Recurse.+-Force", re.IGNORECASE), # PowerShell 强制递归删除
    re.compile(r"(^|\s)(del|erase)\s+.+(/[sp]|/f)", re.IGNORECASE), # cmd 删除
    re.compile(r"(^|\s)(rd|rmdir)\s+.+/s", re.IGNORECASE), # cmd 递归删除目录
]

CONFIRM_PATTERNS= [
    re.compile(r"rm\s+-\S*[rf]"), # rm -r 或 rm -f 类
    re.compile(r"sudo\s+"), # sudo 命令
    re.compile(r"curl\s+.*\|\s*(sh|bash|zsh)"), # curl pipe to shell
    re.compile(r"wget\s+.*\|\s*(sh|bash|zsh)"), # wget pipe to shell
    re.compile(r"npm\s+publish"), # 发包
    re.compile(r"git\s+push\s+.*--force"), # 强制推送
    re.compile(r"git\s+reset\s+--hard"), # 硬重置
    re.compile(r"Remove-Item\b", re.IGNORECASE), # PowerShell 删除
    re.compile(r"(^|\s)(del|erase)\b", re.IGNORECASE), # cmd 删除
    re.compile(r"(^|\s)(rd|rmdir)\b", re.IGNORECASE), # cmd 删除目录
    re.compile(r"Invoke-Expression\b", re.IGNORECASE), # PowerShell 动态执行
    re.compile(r"powershell.*-enc", re.IGNORECASE), # 编码后的 PowerShell 执行
]

SENSITIVE_PATTERNS = [
    re.compile(r"\.env(\.|$)"), # .env 文件
    re.compile(r"\.aws\/credentials"), # AWS 凭证
    re.compile(r"\.ssh\/(id_rsa|id_ed25519)$"), # SSH 私钥
    re.compile(r"secrets?\.(json|yaml|yml)$", re.IGNORECASE), # secrets 文件
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
    BASE_DIR = Path.cwd().resolve()
    p = Path(user_path)

    if p.is_absolute():
        raise ValueError("Absolute path not allowed")

    target = (BASE_DIR / p).resolve()

    if BASE_DIR not in target.parents and target != BASE_DIR:
        raise ValueError("Path traversal detected")
    
    return target


def is_sensitive_path(path: str) -> bool:
    for pattern in SENSITIVE_PATTERNS:
        if pattern.search(path):
            return True
    return False
