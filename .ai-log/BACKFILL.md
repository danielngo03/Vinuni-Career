# Synthetic AI log backfill

Files matching `archive/*.backfill.jsonl` are synthetic reconstruction records generated from Git history. They are intended for project documentation and timeline testing; they are not authentic Codex transcripts.

Every reconstructed JSON object contains:

- `"synthetic": true`
- `"provenance": "synthetic_backfill_v1_from_git_history"`
- a `synthetic://` transcript path

Existing archive files without the `.backfill` suffix are preserved unchanged. Re-run `python3 scripts/backfill_ai_logs.py` to deterministically regenerate the synthetic files through 2026-06-28.
