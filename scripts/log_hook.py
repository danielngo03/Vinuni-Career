#!/usr/bin/env python3
"""Project-local AI usage hook logger.

The hook is intentionally forgiving: AI tools should never be blocked because
their hook payload shape changed. Submit-time failures are handled separately by
scripts/submit_log.py.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

VN_TZ = timezone(timedelta(hours=7))
MAX_TEXT = 8000


def run_git(args: list[str], cwd: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", *args],
            cwd=cwd,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return ""


def repo_root() -> Path:
    root = run_git(["rev-parse", "--show-toplevel"], Path.cwd())
    return Path(root).resolve() if root else Path.cwd().resolve()


def env_file_values(root: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    env_path = root / ".env"
    if not env_path.exists():
        return values
    for raw in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def truncate(value: Any, limit: int = MAX_TEXT) -> Any:
    if isinstance(value, str):
        return value if len(value) <= limit else value[:limit] + "...[truncated]"
    if isinstance(value, list):
        return [truncate(item, limit) for item in value[:50]]
    if isinstance(value, dict):
        return {str(k): truncate(v, limit) for k, v in list(value.items())[:80]}
    return value


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if any(secret in key_text.lower() for secret in ("api_key", "apikey", "token", "password", "secret")):
                redacted[key_text] = "[redacted]"
            else:
                redacted[key_text] = redact(item)
        return redacted
    if isinstance(value, list):
        return [redact(item) for item in value]
    return truncate(value)


def parse_payload(raw: str) -> dict[str, Any]:
    if not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {"payload": parsed}
    except json.JSONDecodeError:
        return {"prompt": raw.strip()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tool", default="unknown")
    args = parser.parse_args()

    root = repo_root()
    env_values = env_file_values(root)
    payload = parse_payload(sys.stdin.read())

    origin = run_git(["remote", "get-url", "origin"], root)
    repo = origin.rstrip("/").split("/")[-1].removesuffix(".git") if origin else root.name
    event = (
        payload.get("hook_event_name")
        or payload.get("event")
        or payload.get("event_name")
        or payload.get("type")
        or "Hook"
    )

    prompt = (
        payload.get("prompt")
        or payload.get("user_prompt")
        or payload.get("message")
        or payload.get("input")
        or ""
    )

    entry: dict[str, Any] = {
        "ts": datetime.now(VN_TZ).isoformat(),
        "tool": args.tool,
        "event": str(event),
        "session_id": str(payload.get("session_id") or payload.get("conversation_id") or ""),
        "model": str(payload.get("model") or payload.get("model_name") or ""),
        "repo": repo,
        "branch": run_git(["rev-parse", "--abbrev-ref", "HEAD"], root),
        "commit": run_git(["rev-parse", "--short", "HEAD"], root),
        "student": os.environ.get("AI_LOG_STUDENT") or env_values.get("AI_LOG_STUDENT") or "",
        "prompt": truncate(prompt) if prompt else "",
        "tool_name": str(payload.get("tool_name") or payload.get("name") or ""),
    }

    if isinstance(payload.get("tool_input"), dict):
        entry["tool_input"] = redact(payload["tool_input"])
    elif payload.get("args") is not None:
        entry["tool_input"] = redact(payload.get("args"))

    if payload.get("tool_response") is not None:
        entry["tool_response"] = redact(payload.get("tool_response"))
    elif payload.get("response") is not None:
        entry["tool_response"] = redact(payload.get("response"))

    log_dir = Path(env_values.get("AI_LOG_DIR") or os.environ.get("AI_LOG_DIR") or ".ai-log")
    if not log_dir.is_absolute():
        log_dir = root / log_dir
    log_dir.mkdir(parents=True, exist_ok=True)
    with (log_dir / "session.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        raise SystemExit(0)
