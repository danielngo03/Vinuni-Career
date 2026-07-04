#!/usr/bin/env python3
"""Small project-local Claude Code hook logger.

Hooks must never block Claude. This logger silently exits on malformed input,
missing git metadata, or filesystem errors.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

VN_TZ = timezone(timedelta(hours=7))


def git(args: list[str], cwd: Path) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=cwd, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return ""


def main() -> None:
    project_root = Path(os.environ.get("CLAUDE_PROJECT_DIR", Path.cwd())).resolve()
    raw = sys.stdin.buffer.read().decode("utf-8", errors="replace").strip()
    if not raw:
        return

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return

    origin = git(["remote", "get-url", "origin"], project_root)
    repo = origin.rstrip("/").split("/")[-1].removesuffix(".git") if origin else project_root.name

    entry = {
        "ts": datetime.now(VN_TZ).isoformat(),
        "tool": "claude",
        "event": data.get("hook_event_name", ""),
        "session_id": data.get("session_id", ""),
        "model": data.get("model", ""),
        "repo": repo,
        "branch": git(["rev-parse", "--abbrev-ref", "HEAD"], project_root),
        "commit": git(["rev-parse", "--short", "HEAD"], project_root),
        "tool_name": data.get("tool_name", ""),
    }

    if data.get("hook_event_name") == "UserPromptSubmit":
        entry["prompt"] = data.get("prompt", "")[:1000]
    elif isinstance(data.get("tool_input"), dict):
        tool_input = dict(data["tool_input"])
        for secret_key in ("api_key", "token", "password", "secret"):
            if secret_key in tool_input:
                tool_input[secret_key] = "[redacted]"
        entry["tool_input"] = tool_input

    log_dir = project_root / ".ai-log"
    log_dir.mkdir(exist_ok=True)
    with (log_dir / "session.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(json.dumps({"status": "logged"}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)
