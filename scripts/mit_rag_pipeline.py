"""CLI wrapper for the YouTube transcript RAG pipeline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.src.services.youtube_rag_pipeline import DEFAULT_OUTPUT_DIR, PipelineConfig, run_youtube_rag_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Crawl YouTube transcripts and build RAG-ready chunks.")
    parser.add_argument("run", nargs="?", default="run", help="Pipeline command. Currently only 'run' is supported.")
    parser.add_argument("--source-url", required=True, help="YouTube video or playlist URL.")
    parser.add_argument("--teacher-user-id", default="teacher_demo", help="Teacher account/user id for metadata.")
    parser.add_argument("--category", default="Uncategorized", help="Course category metadata.")
    parser.add_argument("--course-title", default=None, help="Course or playlist title metadata.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Pipeline output directory.")
    parser.add_argument("--langs", nargs="+", default=["vi", "en"], help="Subtitle language priority.")
    parser.add_argument("--chunk-size-words", type=int, default=420, help="Chunk size in words.")
    parser.add_argument("--overlap-words", type=int, default=100, help="Chunk overlap in words.")
    parser.add_argument("--keep-vtt", action="store_true", help="Keep downloaded VTT subtitle files.")
    parser.add_argument("--force", action="store_true", help="Re-crawl/rewrite existing outputs.")
    parser.add_argument("--sleep-seconds", type=float, default=2.0, help="Sleep between videos.")
    args = parser.parse_args()

    if args.run != "run":
        raise SystemExit("Only the 'run' command is supported.")

    report = run_youtube_rag_pipeline(
        PipelineConfig(
            source_url=args.source_url,
            output_dir=Path(args.output_dir),
            teacher_user_id=args.teacher_user_id,
            category=args.category,
            course_title=args.course_title,
            languages=tuple(args.langs),
            chunk_size_words=args.chunk_size_words,
            overlap_words=args.overlap_words,
            keep_vtt=args.keep_vtt,
            force=args.force,
            sleep_seconds=args.sleep_seconds,
        )
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
