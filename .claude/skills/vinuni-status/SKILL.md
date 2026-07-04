---
name: vinuni-status
description: Use to update docs/IMPLEMENTATION_STATUS.md using verified repository and Claude Code state only.
disable-model-invocation: true
---

# VinUni Status Update

Use this skill when updating `docs/IMPLEMENTATION_STATUS.md`.

## Rules

- Record verified facts only.
- Do not record plans, intentions, or installed plugins that are not confirmed.
- If `backend/` or `frontend/` are absent, record them as intentionally absent after reset.
- If they exist with only `.env` / `.env.example`, record them as env seeds, not implemented code.
- If they exist, record only verified implementation facts. Do not rely on pre-reset history or remembered phase status.
- Do not mark a phase/slice complete unless `docs/SYSTEM_ACCEPTANCE_BAR.md` is satisfied or explicitly records the remaining gaps.
- Status must distinguish "tests passed" from "product/UX/system accepted".

## Verification Sources

- Filesystem checks for `CLAUDE.md`, `.claude/agents/`, `.claude/rules/`, `.claude/commands/`, `.claude/skills/`, and `docs/`.
- `docs/SYSTEM_ACCEPTANCE_BAR.md` and the latest `/review-snapshot` findings when present.
- Claude Code CLI output for `/plugin list`, `/plugin marketplace list`, `/memory`, `/agents`, and `/hooks` when available.
- If Claude CLI is unavailable, say plugin/memory/hook status is unverified.

## Output

Update status with current date, verified instruction-layer inventory, verified plugin/marketplace state, known gaps, and next recommended work.
