#!/usr/bin/env python3
"""Append a manual AI usage log entry for web tools."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

VN_TZ = timezone(timedelta(hours=7))


def git(args: list[str], cwd: Path) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=cwd, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return ""


def main() -> int:
    root_text = git(["rev-parse", "--show-toplevel"], Path.cwd())
    root = Path(root_text).resolve() if root_text else Path.cwd().resolve()

    parser = argparse.ArgumentParser()
    parser.add_argument("--tool", help="Tool name, e.g. chatgpt, claude-web, gemini-web")
    parser.add_argument("--prompt", help="Prompt text")
    args = parser.parse_args()

    tool = args.tool or input("Tool name: ").strip()
    prompt = args.prompt or input("Prompt: ").strip()
    origin = git(["remote", "get-url", "origin"], root)
    repo = origin.rstrip("/").split("/")[-1].removesuffix(".git") if origin else root.name

    entry = {
        "ts": datetime.now(VN_TZ).isoformat(),
        "tool": tool,
        "event": "ManualPrompt",
        "session_id": "",
        "model": "",
        "repo": repo,
        "branch": git(["rev-parse", "--abbrev-ref", "HEAD"], root),
        "commit": git(["rev-parse", "--short", "HEAD"], root),
        "student": "",
        "prompt": prompt[:8000],
        "tool_name": "",
    }

    log_dir = root / ".ai-log"
    log_dir.mkdir(exist_ok=True)
    with (log_dir / "session.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")
    print("Logged manual AI usage to .ai-log/session.jsonl")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
