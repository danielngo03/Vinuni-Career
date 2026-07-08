---
description: Run repeated VinUni build bursts overnight with checkpoint gates between batches
argument-hint: [focus, e.g. finish CV-first student flow then Visual/Product Rescue then next roadmap slices]
allowed-tools: Read, Edit, MultiEdit, Write, Bash, Glob, Grep, TodoWrite, Task
---

# VinUni Overnight Burst Loop

Focus:

`$ARGUMENTS`

Use this when the user wants Claude to keep building for a long session with
better throughput than normal autopilot.

## Operating Mode

- Run repeated Build Burst cycles:
  1. choose the highest-priority coherent batch;
  2. implement 2-4 related slices;
  3. run cheap checks after each slice;
  4. run checkpoint gates for the batch;
  5. fix checkpoint failures;
  6. update `docs/IMPLEMENTATION_STATUS.md`;
  7. continue to the next coherent batch.
- Maintain `.claude/run-state.md` as the short working cache for the whole night.
- Prefer main-conversation implementation when context reuse matters. Use
  subagents only for independent review/spec risks or when tool restrictions
  improve safety.
- Do not reread long docs wholesale when `.claude/run-state.md` already records
  the relevant section and the file has not changed. Use `Grep` and targeted
  section reads.
- Optimize for throughput: build 3-6 related small slices per checkpoint when
  they are in the same product area and do not need separate product decisions.
- Do not update `docs/IMPLEMENTATION_STATUS.md` after every tiny slice. Update it
  once per checkpoint with verified facts only.

## Required Startup

Read:

- `CLAUDE.md`
- `.claude/run-state.md` if it exists
- `docs/CLAUDE_BUILD_OPTIMIZATION.md`
- The minimum feature-specific docs for the first batch.

Do not read all of `docs/IMPLEMENTATION_STATUS.md`, `docs/IMPLEMENTATION_PLAN.md`,
`docs/ROADMAP.md`, or `docs/BACKLOG.md` at startup unless `.claude/run-state.md`
is missing, stale, or the next-batch choice depends on those exact sections. Use
targeted `Grep`/section reads instead.

## Batch Selection

Priority order:

1. Human review blockers or explicit user focus.
2. Product/UI drift that blocks credible use.
3. Broken tests/build/runtime.
4. Core student/partner/university loops from `docs/IMPLEMENTATION_PLAN.md`.
5. Next roadmap slice.

Default tie-breakers after the explicit user focus is complete:

1. CV Ingestion & CV Studio Product Rescue when uploaded-CV preview,
   extraction/OCR/layout/vision-LLM fallback, upload-and-name import (no manual
   field-review step — owner decision 2026-07-05), or document-builder UX is
   functional-only. This is a core student workflow and outranks admin AI
   settings or broad roadmap expansion unless a hard blocker exists.
2. Product Interaction / Visual Realism Rescue when icon semantics, saved-job
   affordances, header quick actions, campaign/banner creative, disclosure
   wording, or marketplace/dashboard visual quality still feel demo-like.
3. Visual marketplace/product maturity rescue when the public/student surfaces
   still lack real recruiting-marketplace merchandising: banner/carousel/right
   rail, saved/invitation/feedback/AI quick actions, stronger VinUni visual
   rhythm, dense job inventory, and polished paid-vs-curated labels.
4. Verification debt that blocks truthful status claims, especially browser/E2E
   evidence for already-built core flows.
5. Recruitment pipeline and interview/scorecard/offers, because it extends the
   shipped application decision loop.
6. Events module, because public marketplace already exposes events as an honest
   coming-soon surface.
7. Advertising/sponsored discovery contracts.
8. AI cost infra and real-provider enablement only when required env keys exist
   or the user explicitly asks to spend real API credits.
9. RAG/semantic features that require pgvector only after local pgvector is
   available or an alternative local fallback is chosen.

If multiple next batches are valid and unblocked, do **not** stop to ask the
user. Choose the highest item from this order, record the reason in
`.claude/run-state.md`, and continue. Asking for steering is allowed only when
the choice would materially change product scope/security posture, require a
paid/external resource, or conflict with source-of-truth docs.

Never open a multi-choice steering prompt for ordinary next-batch selection.
The user explicitly wants unattended progress. If a higher-priority batch is
blocked only by a non-critical external resource, skip that batch for now, record
the reason, and continue with the next unblocked tie-breaker.

For browser/E2E verification:

- First try already-available local browser tooling: Chrome DevTools MCP,
  installed Chrome/Chromium, or an existing Playwright browser cache.
- If a new browser download would require user approval/network access, record
  "browser matrix blocked by missing browser install" and continue to the next
  unblocked batch. Do not stop the overnight loop solely for the download.
- Return to the browser matrix at the next checkpoint after the resource exists.

For each batch, write to `.claude/run-state.md`:

- batch goal;
- selected slices;
- docs/sections read;
- contracts/decisions;
- files expected to change;
- cheap checks;
- checkpoint gates;
- deferred risks.

Keep `.claude/run-state.md` under 250 lines. It is a cache, not a second status
document. Archive only checkpoint summaries to `docs/IMPLEMENTATION_STATUS.md`.

## Fast Overnight Constraints

- Prefer main conversation; no subagents for ordinary implementation slices.
- Use at most one reviewer subagent when the risk is independent and meaningful.
- Reuse run-state; avoid rereading long docs.
- Use `rg`/targeted reads before opening whole files.
- Cheap checks per slice; full gates only at checkpoint.
- Browser screenshots only when visual QA is the batch goal or before claiming
  browser verification.
- Do not invoke `frontend-design` unless the current batch is explicitly a major
  visual redesign or `globals.css` theme work.
- If a slice is actually 1-3 localized files, switch to Tiny Patch behavior:
  no broad docs, no subagents, no status update, cheapest check only.

For any major frontend redesign or `globals.css` theme work:

- invoke the official `frontend-design` skill first;
- read `docs/FRONTEND_DESIGN_PLUGIN_USAGE.md`;
- do not write app code until the design plan covers subject/audience/job,
  screenshot diagnosis, compact color/type/layout system, signature element,
  motion plan, self-critique, `globals.css` light/dark/system theme audit, and
  implementation plan;
- after building, critique screenshots against that plan and revise before
  marking visual-design verified.

## Checkpoint Gates

Run checkpoint gates after each burst batch, not after every tiny edit.

Minimum checkpoint:

- focused backend tests for touched modules;
- focused frontend type/lint/build check for touched package/surface;
- wider backend/frontend gates when shared contracts, migrations, auth/RBAC,
  data models, or major UI shells changed;
- browser screenshots only for affected major UI surfaces;
- status update with exact verification level.

Never claim `browser verified`, `E2E verified`, or phase complete unless those
checkpoint gates actually passed.

Clean checkpoints are continuation points, not stopping points. After a green
checkpoint, update status/run-state, choose the next batch with the tie-breakers,
and continue automatically.

If context is getting deep:

- compress the current state into `.claude/run-state.md`;
- write the next exact batch goal and first slice;
- continue with targeted reads from the run-state and relevant docs;
- do not stop merely to "start fresh" unless the tool/runtime itself cannot
  continue.

## Continue Rules

Continue automatically after a successful checkpoint. Stop only for:

- missing secret/account/external system;
- repeated checkpoint failure that needs user/product decision;
- destructive action, production deploy, production data mutation, or force push;
- source-of-truth conflict that changes security/product scope.

Do not stop merely because there are several reasonable Phase 2 modules to pick
from. Apply the default tie-breakers above and keep working.

Do not stop solely because browser automation needs a download. Try existing
local browser tooling first; if unavailable, record the verification debt and
continue to the next unblocked product batch.

Do not stop solely because a new sub-epic should start "cleanly" or because the
current context is long. The run-state file is the clean handoff; keep going.

## Output

At every checkpoint, append a short status note:

- batch completed;
- files changed;
- cheap checks;
- checkpoint gates;
- failures fixed;
- next batch chosen.
