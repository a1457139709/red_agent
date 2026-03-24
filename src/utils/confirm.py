import os

def confirm_from_user(command: str) -> bool:
    response = input(f"命令 '{command}' 可能具有潜在风险。是否继续执行？(yes/y/no/n): ").strip().lower()
    return response in ("yes", "y")