"""YouTube transcript crawl, clean, and RAG chunk pipeline."""

from __future__ import annotations

import hashlib
import html
import json
import math
import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "youtube_rag"


@dataclass(frozen=True)
class PipelineConfig:
    source_url: str
    output_dir: Path = DEFAULT_OUTPUT_DIR
    teacher_user_id: str = "teacher_demo"
    category: str = "Uncategorized"
    course_title: str | None = None
    languages: tuple[str, ...] = ("vi", "en")
    chunk_size_words: int = 420
    overlap_words: int = 100
    keep_vtt: bool = False
    force: bool = False
    sleep_seconds: float = 2.0


def run_youtube_rag_pipeline(config: PipelineConfig) -> dict[str, Any]:
    _validate_config(config)
    config.output_dir.mkdir(parents=True, exist_ok=True)

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    source_type = detect_source_type(config.source_url)
    source_info = extract_source_info(config.source_url, source_type)
    source_title = config.course_title or source_info.get("title") or source_info.get("id") or "youtube-source"
    source_slug = slugify(source_title)

    raw_videos_dir = config.output_dir / "raw" / source_slug / "videos"
    clean_videos_dir = config.output_dir / "cleaned" / source_slug / "videos"
    chunks_dir = config.output_dir / "chunks"
    reports_dir = config.output_dir / "reports"
    raw_videos_dir.mkdir(parents=True, exist_ok=True)
    clean_videos_dir.mkdir(parents=True, exist_ok=True)
    chunks_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    video_entries = get_video_entries(source_info, source_type)
    chunks_path = chunks_dir / f"{source_slug}.jsonl"
    if config.force and chunks_path.exists():
        chunks_path.unlink()

    report: dict[str, Any] = {
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": config.teacher_user_id,
        "source_url": config.source_url,
        "source_type": source_type,
        "source_title": source_title,
        "source_slug": source_slug,
        "category": config.category,
        "course_title": config.course_title or source_title,
        "languages": list(config.languages),
        "chunk_size_words": config.chunk_size_words,
        "overlap_words": config.overlap_words,
        "videos_found": len(video_entries),
        "videos": [],
        "chunks_output": str(chunks_path),
        "chunks_created": 0,
    }

    with chunks_path.open("a", encoding="utf-8") as chunks_file:
        for entry in video_entries:
            video_id = entry.get("id")
            if not video_id:
                continue
            raw_output = raw_videos_dir / f"{video_id}.json"
            clean_output = clean_videos_dir / f"{video_id}.json"

            try:
                if raw_output.exists() and not config.force:
                    transcript = json.loads(raw_output.read_text(encoding="utf-8"))
                    video_status = "raw_exists"
                else:
                    transcript = crawl_video_transcript(entry, raw_videos_dir, config.languages, config.keep_vtt)
                    raw_output.write_text(json.dumps(transcript, ensure_ascii=False, indent=2), encoding="utf-8")
                    video_status = "crawled"

                cleaned = clean_transcript_payload(
                    transcript,
                    category=config.category,
                    course_title=config.course_title or source_title,
                    course_url=config.source_url if source_type == "playlist" else None,
                    teacher_user_id=config.teacher_user_id,
                )
                clean_output.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2), encoding="utf-8")

                chunks = build_chunks(cleaned, config.chunk_size_words, config.overlap_words)
                if config.force:
                    write_chunks = chunks
                else:
                    write_chunks = [chunk for chunk in chunks if not chunk_id_exists(chunks_path, chunk["id"])]
                for chunk in write_chunks:
                    chunks_file.write(json.dumps(chunk, ensure_ascii=False) + "\n")
                chunks_file.flush()

                report["chunks_created"] += len(write_chunks)
                report["videos"].append(
                    {
                        "video_id": video_id,
                        "title": cleaned["video"].get("title"),
                        "status": video_status,
                        "raw_output": str(raw_output),
                        "clean_output": str(clean_output),
                        "chunks": len(chunks),
                        "chunks_written": len(write_chunks),
                    }
                )
            except Exception as exc:
                report["videos"].append(
                    {
                        "video_id": video_id,
                        "title": entry.get("title"),
                        "status": "error",
                        "reason": str(exc),
                    }
                )
            time.sleep(config.sleep_seconds)

    report["videos_saved"] = sum(1 for item in report["videos"] if item.get("status") in {"crawled", "raw_exists"})
    report["videos_failed"] = sum(1 for item in report["videos"] if item.get("status") == "error")
    report_path = reports_dir / f"{run_id}.json"
    report["report_output"] = str(report_path)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def _validate_config(config: PipelineConfig) -> None:
    if not config.source_url.strip():
        raise ValueError("source_url is required.")
    if config.chunk_size_words <= 0:
        raise ValueError("chunk_size_words must be greater than zero.")
    if config.overlap_words < 0 or config.overlap_words >= config.chunk_size_words:
        raise ValueError("overlap_words must satisfy 0 <= overlap < chunk_size_words.")
    if not config.languages:
        raise ValueError("At least one subtitle language is required.")


def detect_source_type(url: str) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    if "youtube.com" in parsed.netloc.lower() and parsed.path == "/playlist":
        return "playlist"
    if "list" in query and "v" not in query:
        return "playlist"
    return "video"


def extract_source_info(url: str, source_type: str) -> dict[str, Any]:
    try:
        from yt_dlp import YoutubeDL
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError("Missing dependency 'yt_dlp'. Install it with: pip install yt-dlp") from exc

    opts = {
        "extract_flat": "in_playlist" if source_type == "playlist" else False,
        "ignoreerrors": True,
        "skip_download": True,
        "quiet": True,
        "http_headers": {"User-Agent": "Mozilla/5.0"},
    }
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if not info:
        raise RuntimeError("yt-dlp could not extract source information.")
    return info


def get_video_entries(source_info: dict[str, Any], source_type: str) -> list[dict[str, Any]]:
    if source_type == "playlist" or source_info.get("_type") == "playlist":
        return [entry for entry in source_info.get("entries", []) if entry and entry.get("id")]
    return [source_info]


def crawl_video_transcript(
    entry: dict[str, Any],
    work_dir: Path,
    languages: tuple[str, ...],
    keep_vtt: bool,
) -> dict[str, Any]:
    video_id = entry["id"]
    video_url = entry.get("webpage_url") or entry.get("url") or f"https://www.youtube.com/watch?v={video_id}"
    if not str(video_url).startswith("http"):
        video_url = f"https://www.youtube.com/watch?v={video_id}"

    info = download_subtitles(video_url, work_dir, languages)
    video_entry = get_video_entries(info, "video")[0]
    subtitle_file = choose_subtitle_file(video_id, work_dir, languages)
    if subtitle_file is None:
        raise RuntimeError("No subtitle file was downloaded.")

    payload = build_transcript_json(video_entry, subtitle_file)
    if not keep_vtt:
        for downloaded_subtitle in work_dir.glob(f"{video_id}*.vtt"):
            downloaded_subtitle.unlink(missing_ok=True)
    return payload


def download_subtitles(url: str, output_dir: Path, languages: tuple[str, ...]) -> dict[str, Any]:
    try:
        from yt_dlp import YoutubeDL
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError("Missing dependency 'yt_dlp'. Install it with: pip install yt-dlp") from exc

    output_dir.mkdir(parents=True, exist_ok=True)
    opts = {
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": list(languages),
        "subtitlesformat": "vtt",
        "outtmpl": str(output_dir / "%(id)s.%(ext)s"),
        "ignoreerrors": True,
        "sleep_interval": 3,
        "max_sleep_interval": 8,
        "http_headers": {"User-Agent": "Mozilla/5.0"},
    }
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
    if not info:
        raise RuntimeError("yt-dlp could not extract video information.")
    return info


def parse_timestamp(timestamp: str) -> float | None:
    parts = timestamp.strip().split(":")
    if len(parts) == 3:
        hours, minutes, seconds = parts
    elif len(parts) == 2:
        hours = 0
        minutes, seconds = parts
    else:
        return None
    seconds, _, milliseconds = seconds.partition(".")
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + (
        int(milliseconds.ljust(3, "0")[:3]) / 1000 if milliseconds else 0
    )


def clean_caption_text(text: str) -> str:
    text = re.sub(r"<\d{2}:\d{2}:\d{2}\.\d{3}>", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def parse_vtt(vtt_path: Path) -> list[dict[str, Any]]:
    raw_segments: list[dict[str, Any]] = []
    current_start = None
    current_end = None
    current_lines: list[str] = []

    def flush_segment() -> None:
        nonlocal current_start, current_end, current_lines
        if current_start is None or current_end is None or not current_lines:
            return
        text = clean_caption_text(" ".join(current_lines))
        if not text:
            return
        if raw_segments and raw_segments[-1]["text"] == text:
            return
        raw_segments.append(
            {
                "index": len(raw_segments),
                "start": current_start,
                "end": current_end,
                "duration": round(current_end - current_start, 3),
                "text": text,
            }
        )

    with vtt_path.open("r", encoding="utf-8-sig", errors="replace") as file:
        for raw_line in file:
            line = raw_line.strip()
            if not line or line == "WEBVTT" or line.startswith(("Kind:", "Language:", "NOTE")):
                flush_segment()
                current_start = None
                current_end = None
                current_lines = []
                continue
            if "-->" in line:
                flush_segment()
                start_raw, end_raw = line.split("-->", 1)
                end_raw = end_raw.split()[0]
                current_start = parse_timestamp(start_raw)
                current_end = parse_timestamp(end_raw)
                current_lines = []
                continue
            if current_start is not None:
                current_lines.append(line)
    flush_segment()
    return remove_rolling_caption_overlap(raw_segments)


def remove_rolling_caption_overlap(raw_segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cleaned_segments = []
    previous_raw_words: list[str] = []
    for raw_segment in raw_segments:
        current_words = raw_segment["text"].split()
        if not current_words:
            continue
        overlap = 0
        max_overlap = min(len(previous_raw_words), len(current_words))
        previous_lower = [word.lower() for word in previous_raw_words]
        current_lower = [word.lower() for word in current_words]
        for size in range(max_overlap, 0, -1):
            if previous_lower[-size:] == current_lower[:size]:
                overlap = size
                break
        unique_words = current_words[overlap:]
        if not unique_words:
            previous_raw_words = current_words
            continue
        segment = dict(raw_segment)
        segment["index"] = len(cleaned_segments)
        segment["text"] = " ".join(unique_words)
        cleaned_segments.append(segment)
        previous_raw_words = current_words
    return cleaned_segments


def choose_subtitle_file(video_id: str, output_dir: Path, languages: tuple[str, ...]) -> Path | None:
    subtitle_files = sorted(output_dir.glob(f"{video_id}*.vtt"))
    if not subtitle_files:
        return None
    language_rank = {language: index for index, language in enumerate(languages)}

    def sort_key(subtitle_file: Path) -> tuple[int, str]:
        language = get_subtitle_language(video_id, subtitle_file)
        return (language_rank.get(language, len(language_rank)), subtitle_file.name)

    return sorted(subtitle_files, key=sort_key)[0]


def get_subtitle_language(video_id: str, subtitle_file: Path) -> str | None:
    stem = subtitle_file.stem
    prefix = f"{video_id}."
    if stem.startswith(prefix):
        return stem[len(prefix):]
    return stem.split(".")[-1] if "." in stem else None


def build_transcript_json(info: dict[str, Any], subtitle_file: Path) -> dict[str, Any]:
    language = get_subtitle_language(info.get("id"), subtitle_file)
    segments = parse_vtt(subtitle_file)
    return {
        "video": {
            "id": info.get("id"),
            "title": info.get("title"),
            "url": info.get("webpage_url"),
            "channel": info.get("channel") or info.get("uploader"),
            "duration": info.get("duration"),
            "language": language,
        },
        "segment_count": len(segments),
        "segments": segments,
    }


def clean_transcript_payload(
    transcript: dict[str, Any],
    category: str,
    course_title: str,
    course_url: str | None,
    teacher_user_id: str,
) -> dict[str, Any]:
    cleaned_segments = []
    for segment in transcript.get("segments", []):
        text = normalize_transcript_text(str(segment.get("text", "")))
        if not text:
            continue
        if is_boilerplate_segment(text, float(segment.get("start") or 0)):
            continue
        cleaned_segment = dict(segment)
        cleaned_segment["index"] = len(cleaned_segments)
        cleaned_segment["text"] = text
        cleaned_segments.append(cleaned_segment)
    payload = dict(transcript)
    payload["segments"] = cleaned_segments
    payload["segment_count"] = len(cleaned_segments)
    payload["metadata"] = {
        "category": category,
        "course_title": course_title,
        "course_url": course_url,
        "created_by": teacher_user_id,
        "cleaned_at": datetime.now(timezone.utc).isoformat(),
    }
    return payload


def normalize_transcript_text(text: str) -> str:
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def is_boilerplate_segment(text: str, start: float) -> bool:
    if start > 35:
        return False
    lowered = text.lower()
    boilerplate_phrases = [
        "creative commons license",
        "your support will help mit",
        "open courseware continue",
        "visit mit opencourseware",
        "ocw.mit.edu",
    ]
    return any(phrase in lowered for phrase in boilerplate_phrases)


def build_chunks(cleaned: dict[str, Any], chunk_size_words: int, overlap_words: int) -> list[dict[str, Any]]:
    records = []
    for segment in cleaned.get("segments", []):
        for word in str(segment.get("text", "")).split():
            records.append(
                {
                    "word": word,
                    "segment_index": segment.get("index"),
                    "start": segment.get("start"),
                    "end": segment.get("end"),
                }
            )
    if not records:
        return []

    video = cleaned.get("video", {})
    metadata = cleaned.get("metadata", {})
    chunks = []
    step = chunk_size_words - overlap_words
    start = 0
    chunk_index = 0
    while start < len(records):
        end = min(start + chunk_size_words, len(records))
        window = records[start:end]
        text = " ".join(record["word"] for record in window)
        start_time = float(window[0].get("start") or 0)
        end_time = float(window[-1].get("end") or start_time)
        video_url = video.get("url") or f"https://www.youtube.com/watch?v={video.get('id')}"
        chunk = {
            "id": build_chunk_id(video.get("id"), chunk_index, text),
            "text": text,
            "metadata": {
                "source_type": "youtube_transcript",
                "category": metadata.get("category"),
                "course_title": metadata.get("course_title"),
                "course_url": metadata.get("course_url"),
                "video_id": video.get("id"),
                "video_title": video.get("title"),
                "video_url": video_url,
                "timestamp_url": build_timestamp_url(video_url, start_time),
                "channel": video.get("channel"),
                "language": video.get("language"),
                "chunk_index": chunk_index,
                "start_time": start_time,
                "end_time": end_time,
                "start_segment_index": window[0].get("segment_index"),
                "end_segment_index": window[-1].get("segment_index"),
            },
        }
        chunks.append(chunk)
        if end == len(records):
            break
        start += step
        chunk_index += 1
    return chunks


def build_chunk_id(video_id: str | None, chunk_index: int, text: str) -> str:
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]
    return f"{video_id or 'video'}_chunk_{chunk_index:04d}_{digest}"


def build_timestamp_url(video_url: str, start_time: float) -> str:
    parsed = urlparse(video_url)
    query = parse_qs(parsed.query)
    query["t"] = [str(max(0, math.floor(start_time)))]
    return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))


def chunk_id_exists(chunks_path: Path, chunk_id: str) -> bool:
    if not chunks_path.exists():
        return False
    with chunks_path.open("r", encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue
            try:
                if json.loads(line).get("id") == chunk_id:
                    return True
            except json.JSONDecodeError:
                continue
    return False


def slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "untitled"
