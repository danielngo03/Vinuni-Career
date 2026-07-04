---
description: Fast tiny patch mode for 1-3 localized files with minimal context and cheapest checks
argument-hint: <exact small change>
allowed-tools: Read, Edit, MultiEdit, Bash, Glob, Grep
---

# VinUni Tiny Patch Mode

Task:

`$ARGUMENTS`

Use this for small, localized edits where speed matters more than broad product
planning.

## Hard Scope

- Edit at most 1-3 files unless the user explicitly approves expansion.
- Read only directly touched files and nearby imports.
- Do not use subagents.
- Do not invoke `frontend-design`.
- Do not run `/feature-vinuni`, `/build-burst`, `/overnight-burst-loop`,
  `/autopilot-build`, `/review-snapshot`, or `/product-reality-audit` from inside
  this command.
- Do not read long docs such as PRD, BACKLOG, ROADMAP, IMPLEMENTATION_STATUS,
  DESIGN, API_CONTRACTS, DATA_MODEL, or ARCHITECTURE unless the user explicitly
  asks or the tiny patch cannot be completed safely without one exact section.
- Do not update docs, `.claude/run-state.md`, or `docs/IMPLEMENTATION_STATUS.md`.
- Do not touch backend unless the request explicitly says backend.

## Workflow

1. Identify the exact file(s) likely to change with `rg`/`Glob`.
2. Read the smallest useful snippets.
3. Apply the smallest safe patch.
4. Run only the cheapest relevant check:
   - frontend tiny UI/TS change: `pnpm --dir frontend run typecheck`;
   - backend tiny change: one focused pytest target for the touched module;
   - docs-only or copy-only: no tests unless requested.
5. Stop after the check. Do not opportunistically refactor adjacent code.

## Forbidden In Tiny Patch

- Full frontend build.
- Full backend suite.
- Browser screenshot matrix.
- E2E.
- Broad lint runs unless the edited file is lint-sensitive and typecheck cannot
  catch the risk.
- Status or run-state updates.
- Product/architecture contract writing.

## Output

Report only:

- files changed;
- check run or intentionally skipped;
- any small residual risk.
