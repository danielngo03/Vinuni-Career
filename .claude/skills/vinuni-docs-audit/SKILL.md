---
name: vinuni-docs-audit
description: Use to audit VinUni docs, agents, rules, commands, skills, and Claude Code setup for consistency and readiness.
---

# VinUni Docs Audit

Use this skill when reviewing the instruction layer itself.

## Audit Scope

- `CLAUDE.md`
- `.claude/agents/`
- `.claude/rules/`
- `.claude/commands/`
- `.claude/skills/`
- `.claude/settings.json`
- `docs/`
- `docs/PRODUCT_REALITY_REBUILD_SPEC.md`
- `docs/SYSTEM_ACCEPTANCE_BAR.md`

Audit `backend/` and `frontend/` when they exist and the task includes implementation readiness. If absent, verify docs clearly instruct Claude to scaffold them from scratch.

## Checks

- Root `CLAUDE.md` is canonical and under 200 lines.
- No stale doc paths such as root `ARCHITECTURE.md` when the real file is `docs/ARCHITECTURE.md`.
- Agents have strong `description`, correct `tools`, clear Must Read docs, hard constraints, and output contract.
- Agents share the same system acceptance bar and can challenge weak, unsafe, unrealistic, or product-incoherent requests.
- Domain agents are read-only.
- Implementation agents can write/edit/test.
- Commands are thin wrappers or intentionally standalone.
- Skills hold repeatable workflows and do not copy full PRD/business logic.
- `.claude/settings.json` does not depend on legacy scripts that may be deleted.
- `docs/IMPLEMENTATION_STATUS.md` records verified facts only.
- UI/product docs require persona-specific operating surfaces, not generic dashboards or placeholder marketing shells.
- Product docs require practical adjacent-flow checks so agents do not implement
  only the visible UI example while ignoring backend/data/AI/auth/notification/
  quota/workflow reality.
- AI docs require task matrix, permission class, eval, fallback, rollback, privacy, and cheap/offline test strategy.
- Backend/data docs define contracts for projections/read models, audit, RBAC, notification outbox, account/session security, and file/CV failure modes.
- Visual/product docs distinguish static VinUni-owned public assets from
  uploaded organization media, and define safe `logo_url` delivery without raw
  storage paths.

## Output

Lead with findings by severity, then list safe fixes and verification steps.
