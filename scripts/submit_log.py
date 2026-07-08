#!/usr/bin/env python3
"""Submit .ai-log/session.jsonl to the grading server, then archive on success."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

VN_TZ = timezone(timedelta(hours=7))
MAX_BATCH_BYTES = 700_000
MAX_BATCH_ENTRIES = 500
BATCH_PAUSE_SECONDS = 3
MAX_RETRIES = 5
RETRY_STATUSES = {429, 500, 502, 503, 504}


def git(args: list[str], cwd: Path) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=cwd, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return ""


def load_env(root: Path) -> dict[str, str]:
    values = dict(os.environ)
    env_path = root / ".env"
    if not env_path.exists():
        return values
    for raw in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    return values


def post_bytes(url: str, api_key: str, body: bytes, content_type: str) -> tuple[int, str]:
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": content_type,
            "Authorization": f"Bearer {api_key}",
            "X-API-Key": api_key,
            "User-Agent": "vinuni-ai-log-hook/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")


def chunk_lines(
    raw: bytes,
    max_bytes: int = MAX_BATCH_BYTES,
    max_entries: int = MAX_BATCH_ENTRIES,
) -> list[bytes]:
    chunks: list[bytes] = []
    current = bytearray()
    current_entries = 0
    for line in raw.splitlines(keepends=True):
        if not line.strip():
            continue
        if current and (len(current) + len(line) > max_bytes or current_entries >= max_entries):
            chunks.append(bytes(current))
            current.clear()
            current_entries = 0
        current.extend(line)
        current_entries += 1
    if current:
        chunks.append(bytes(current))
    return chunks


def submit_chunk(server: str, api_key: str, body: bytes, root: Path) -> tuple[int, str]:
    status, text = post_bytes(server, api_key, body, "application/x-ndjson")
    if status not in (400, 404, 415, 422):
        return status, text

    entries = []
    for line in body.decode("utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            entries.append({"raw": line})
    envelope = {
        "repo": git(["remote", "get-url", "vinuni"], root)
        or git(["remote", "get-url", "origin"], root)
        or root.name,
        "branch": git(["rev-parse", "--abbrev-ref", "HEAD"], root),
        "commit": git(["rev-parse", "--short", "HEAD"], root),
        "entries": entries,
    }
    return post_bytes(
        server,
        api_key,
        json.dumps(envelope, ensure_ascii=False).encode("utf-8"),
        "application/json",
    )


def load_completed_batches(progress_path: Path) -> int:
    try:
        data = json.loads(progress_path.read_text(encoding="utf-8"))
    except Exception:
        return 0
    try:
        return max(0, int(data.get("completed_batches", 0)))
    except Exception:
        return 0


def save_completed_batches(progress_path: Path, completed_batches: int) -> None:
    progress_path.write_text(
        json.dumps({"completed_batches": completed_batches}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def clear_progress(progress_path: Path) -> None:
    try:
        progress_path.unlink()
    except FileNotFoundError:
        pass


def submit_chunk_with_retry(server: str, api_key: str, body: bytes, root: Path, index: int) -> tuple[int, str]:
    for attempt in range(MAX_RETRIES + 1):
        status, text = submit_chunk(server, api_key, body, root)
        if status not in RETRY_STATUSES:
            return status, text
        if attempt >= MAX_RETRIES:
            return status, text
        delay = BATCH_PAUSE_SECONDS * (2**attempt)
        print(
            f"AI log submit hit HTTP {status} on batch {index}; retrying in {delay:.0f}s.",
            file=sys.stderr,
        )
        time.sleep(delay)
    return status, text


def archive_session(session_path: Path) -> Path:
    archive_dir = session_path.parent / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_path = archive_dir / f"{datetime.now(VN_TZ).date().isoformat()}.jsonl"
    with session_path.open("rb") as src, archive_path.open("ab") as dst:
        dst.write(src.read())
    session_path.write_text("", encoding="utf-8")
    return archive_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--keep-session", action="store_true", help="Submit without archiving session.jsonl")
    args = parser.parse_args()

    root_text = git(["rev-parse", "--show-toplevel"], Path.cwd())
    root = Path(root_text).resolve() if root_text else Path.cwd().resolve()
    env = load_env(root)

    log_dir = Path(env.get("AI_LOG_DIR", ".ai-log"))
    if not log_dir.is_absolute():
        log_dir = root / log_dir
    session_path = log_dir / "session.jsonl"
    progress_path = log_dir / "submit-progress.json"
    if not session_path.exists() or session_path.stat().st_size == 0:
        clear_progress(progress_path)
        print("AI log: no session log to submit.")
        return 0

    server = env.get("AI_LOG_SERVER", "").strip()
    api_key = env.get("AI_LOG_API_KEY", "").strip()
    if not server or not api_key or api_key.startswith("replace-with"):
        print("AI log submit failed: AI_LOG_SERVER/AI_LOG_API_KEY is missing in .env.", file=sys.stderr)
        return 1

    raw = session_path.read_bytes()
    line_count = sum(1 for line in raw.splitlines() if line.strip())
    batches = chunk_lines(raw)
    completed_batches = min(load_completed_batches(progress_path), len(batches))
    if args.dry_run:
        resume_text = f"; resume after {completed_batches} completed batch(es)" if completed_batches else ""
        print(
            f"AI log dry-run: {line_count} entries ready in {len(batches)} batch(es){resume_text} "
            f"from {session_path}."
        )
        return 0

    for index, batch in enumerate(batches, start=1):
        if index <= completed_batches:
            continue
        status, text = submit_chunk_with_retry(server, api_key, batch, root, index)
        if not 200 <= status < 300:
            print(
                f"AI log submit failed on batch {index}/{len(batches)} with HTTP {status}. "
                f"Logs remain in {session_path}.",
                file=sys.stderr,
            )
            if text:
                print(text[:500], file=sys.stderr)
            return 1
        save_completed_batches(progress_path, index)
        if index < len(batches):
            time.sleep(BATCH_PAUSE_SECONDS)

    if args.keep_session:
        print(f"AI log submitted {line_count} entries in {len(batches)} batch(es); session kept.")
    else:
        archive_path = archive_session(session_path)
        clear_progress(progress_path)
        print(f"AI log submitted {line_count} entries in {len(batches)} batch(es); archived to {archive_path}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
