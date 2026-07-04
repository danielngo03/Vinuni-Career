---
description: Start a VinUni feature workflow using the project vinuni-feature skill
argument-hint: <feature description>
allowed-tools: Read, Edit, MultiEdit, Write, Bash, Glob, Grep, TodoWrite
---

# VinUni Feature Workflow

Feature request:

`$ARGUMENTS`

Use `.claude/skills/vinuni-feature/SKILL.md` as the primary workflow.

Tiny-patch redirect:

- If the request says `tiny`, `micro`, `small`, `quick`, `localized`, `only this
  file`, `1-3 files`, or names exact files and does not require new product/API/
  data/security scope, follow `.claude/commands/tiny-patch.md` behavior instead.
- In that case, do not read PRD/BACKLOG/ROADMAP, do not use subagents, do not
  update status/run-state, and run only the cheapest relevant check.

Minimum contract:

- Confirm scope against `docs/PRODUCT_REQUIREMENTS.md`, `docs/BACKLOG.md`, and `docs/ROADMAP.md`.
- Read relevant business/security/API/data/design/AI/test docs only as needed.
- Route through `docs/TASK_ROUTING.md`.
- If the feature request is broad or ambiguous, produce a product/architecture
  contract and slice plan first; do not edit app code until the feature has a
  clear persona, job-to-be-done, data contract, permission model, UI surface,
  AI safety class if relevant, and verification plan.
- Produce a plan before implementation for non-trivial work.
- Implement only after contracts are clear.
- Use targeted tests/checks first. Run full gates only when shared contracts,
  migrations, auth/RBAC, or major UI flows changed.
- Verify and report commands run, risks, open questions, and the next slice.
