#!/usr/bin/env python3
"""Deny obviously dangerous Claude Code tool calls."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


DANGEROUS_BASH = [
    (re.compile(r"\brm\s+-[^&|;]*r[^&|;]*f\b"), "Blocks recursive force delete."),
    (re.compile(r"\bgit\s+reset\s+--hard\b"), "Blocks destructive git reset."),
    (re.compile(r"\bgit\s+clean\s+-[^&|;]*[fd][^&|;]*\b"), "Blocks destructive git clean."),
    (re.compile(r"\bgit\s+push\b.*\s--force\b"), "Blocks force push."),
    (re.compile(r"\bchmod\s+-R\s+777\b"), "Blocks overly broad chmod."),
    (re.compile(r"\b(curl|wget)\b.+\|\s*(sh|bash)\b"), "Blocks piping remote scripts to shell."),
    (re.compile(r"\bdocker\s+compose\b.+\bdown\b.+\s-v\b"), "Blocks deleting compose volumes."),
    (re.compile(r"\bkubectl\s+delete\b"), "Blocks Kubernetes delete."),
    (re.compile(r"\bterraform\s+destroy\b"), "Blocks Terraform destroy."),
    (re.compile(r"\bDROP\s+DATABASE\b", re.IGNORECASE), "Blocks database drop."),
]

SAFE_ENV_NAMES = {
    ".env",
    ".env.local",
    ".env.development",
    ".env.example", 
    ".env.sample", 
    ".env.template"
}


SENSITIVE_PATH_PARTS = {
    ".env.production",
    ".env.prod",
    "secrets",
    ".secrets",
}


def deny(reason: str) -> None:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))


def is_sensitive_path(value: str) -> bool:
    if not value:
        return False
    path = Path(value)
    parts = set(path.parts)
    name = path.name
    if name in SAFE_ENV_NAMES:
        return False
    return name.startswith((".env.production", ".env.prod")) or bool(parts & SENSITIVE_PATH_PARTS)


def main() -> None:
    raw = sys.stdin.buffer.read().decode("utf-8", errors="replace").strip()
    if not raw:
        return
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return

    tool = data.get("tool_name", "")
    tool_input = data.get("tool_input") or {}

    if tool == "Bash":
        command = str(tool_input.get("command", ""))
        for pattern, reason in DANGEROUS_BASH:
            if pattern.search(command):
                deny(reason)
                return

    if tool in {"Read", "Edit", "Write", "MultiEdit"}:
        path = str(tool_input.get("file_path") or tool_input.get("path") or "")
        if is_sensitive_path(path):
            deny(f"Blocks access to sensitive path: {path}")
            return


if __name__ == "__main__":
    main()
