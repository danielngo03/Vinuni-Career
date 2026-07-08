#!/usr/bin/env python3
"""Best-effort Antigravity transcript importer.

Antigravity stores transcripts outside the repo on some machines. To avoid
guessing global paths and accidentally importing unrelated projects, this script
only imports project-local transcript files from .antigravity/ when present.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

VN_TZ = timezone(timedelta(hours=7))


def git(args: list[str], cwd: Path) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=cwd, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return ""


def existing_ids(session_path: Path) -> set[str]:
    ids: set[str] = set()
    if not session_path.exists():
        return ids
    for line in session_path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        entry_id = entry.get("entry_id")
        if entry_id:
            ids.add(str(entry_id))
    return ids


def main() -> int:
    root_text = git(["rev-parse", "--show-toplevel"], Path.cwd())
    root = Path(root_text).resolve() if root_text else Path.cwd().resolve()
    transcript_root = root / ".antigravity"
    if not transcript_root.exists():
        return 0

    log_dir = root / ".ai-log"
    log_dir.mkdir(exist_ok=True)
    session_path = log_dir / "session.jsonl"
    seen = existing_ids(session_path)

    origin = git(["remote", "get-url", "origin"], root)
    repo = origin.rstrip("/").split("/")[-1].removesuffix(".git") if origin else root.name
    imported = 0

    with session_path.open("a", encoding="utf-8") as out:
        for path in sorted(transcript_root.rglob("*.jsonl")):
            for line_no, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
                try:
                    payload: dict[str, Any] = json.loads(line)
                except json.JSONDecodeError:
                    continue
                prompt = payload.get("prompt") or payload.get("user_prompt") or payload.get("message")
                if not prompt:
                    continue
                entry_id = str(payload.get("entry_id") or f"antigravity-{path.name}-{line_no}")
                if entry_id in seen:
                    continue
                seen.add(entry_id)
                entry = {
                    "ts": payload.get("ts") or datetime.now(VN_TZ).isoformat(),
                    "tool": "antigravity",
                    "event": payload.get("event") or "UserPrompt",
                    "entry_id": entry_id,
                    "session_id": payload.get("session_id") or "",
                    "model": payload.get("model") or "",
                    "repo": repo,
                    "branch": git(["rev-parse", "--abbrev-ref", "HEAD"], root),
                    "commit": git(["rev-parse", "--short", "HEAD"], root),
                    "student": payload.get("student") or "",
                    "prompt": str(prompt)[:8000],
                    "response_summary": str(payload.get("response_summary") or "")[:4000],
                }
                out.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")
                imported += 1

    if imported:
        print(f"Imported {imported} Antigravity log entries.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
