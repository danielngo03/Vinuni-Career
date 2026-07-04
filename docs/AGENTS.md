# Agents Guide — VinUni Career Platform

> Phiên bản: 5.0 | Cập nhật: 26/06/2026  
> Purpose: human-readable roster. Claude Code routing source is `CLAUDE.md` + `docs/TASK_ROUTING.md` + `.claude/agents/*.agent.md`.

---

## 1. Operating Model

- Build greenfield from Markdown specs. If `backend/`/`frontend/` are absent, scaffold them from docs.
- Ignore pre-reset git history, deleted code, remembered phase status, and legacy assumptions.
- Main Claude session is the orchestrator.
- Subagents work in isolated context and report back through a handoff packet.
- Subagents do not directly talk to each other by default.
- Agent Teams are optional and only used when explicitly enabled with `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`.
- Subagents should challenge weak, unsafe, or incoherent requests instead of
  blindly implementing them. Use `docs/SYSTEM_ACCEPTANCE_BAR.md` as the shared
  definition of done.

---

## 2. Agent Roster

| Agent | Slug | Writes Code? | Responsibility |
|---|---|---:|---|
| Product Owner & System Planner | `product-owner-system-planner` | Docs only | Scope, priority, PRD/backlog/roadmap, acceptance criteria |
| System Architect | `system-architect` | Docs/architecture | ADRs, module boundaries, contracts, trade-offs |
| Backend Developer | `backend-developer` | Yes | FastAPI, SQLAlchemy, Alembic, Celery, backend tests |
| Frontend Developer | `frontend-developer` | Yes | Next.js, React, Tailwind, UI, accessibility, frontend tests |
| AI Engineer | `ai-engineer` | Yes | AI gateway, prompts, tools, evals, extraction, safety |
| Data Engineer | `data-engineer` | Yes | Analytics events, projections, exports, outcomes data |
| University Domain Agent | `university-domain-agent` | No | Governance, moderation, university RBAC, AI settings policy |
| Employer Domain Agent | `employer-domain-agent` | No | Partner journey, job posting, pipeline, hiring UX |
| Student Domain Agent | `student-domain-agent` | No | Student journey, CV, applications, AI UX |
| Tester & QA | `tester-qa` | Test code only | Test plans, E2E scenarios, quality gates |

---

## 3. Routing Decision Tree

```text
Task received
  |
  +-- Product scope / priority / acceptance criteria
  |      -> product-owner-system-planner
  |
  +-- Architecture / data flow / module boundary / integration
  |      -> system-architect
  |
  +-- Backend API / service / DB / worker / migration
  |      -> backend-developer
  |
  +-- Frontend UI / page / component / accessibility / i18n
  |      -> frontend-developer
  |
  +-- AI prompt / tool / gateway / extraction / matching / eval / safety
  |      -> ai-engineer
  |
  +-- Analytics / projection / export / career outcomes
  |      -> data-engineer
  |
  +-- University governance / moderation / policy / staff RBAC
  |      -> university-domain-agent
  |
  +-- Employer journey / recruiter workflow / pipeline UX
  |      -> employer-domain-agent
  |
  +-- Student journey / CV / applications / AI student UX
  |      -> student-domain-agent
  |
  +-- Test strategy / QA gate / regression / E2E
         -> tester-qa
```

Use `docs/TASK_ROUTING.md` for exact workflow sequences.

---

## 4. Handoff Packet

Every non-trivial agent result must include:

```markdown
## Handoff

**Goal:** ...
**Source docs read:** ...
**Decisions:** ...
**Contracts:** API/schema/data/event changes.
**Owned files/modules:** ...
**Tests:** required/added commands.
**Risks:** ...
**Open questions:** ...
**Next agent:** ...
```

---

## 5. Sequential Gates

- Product scope before architecture for new features.
- Architecture before backend implementation for new modules or data changes.
- Domain review before UX-heavy implementation.
- API/data contract before frontend implementation.
- AI engineer review before prompt/tool changes ship.
- QA after implementation and before phase/release completion.

---

## 6. Parallel Work Rules

Parallel is allowed when:

- Backend and frontend work from a stable API contract.
- Multiple backend modules have no shared migration/file ownership.
- Review agents inspect separate concerns: security, performance, test coverage.

Parallel is not allowed when:

- Multiple agents would edit the same file.
- Architecture or data model is still undecided.
- AI prompt/tool behavior is not approved.
- RBAC/security boundary is ambiguous.

---

## 7. Non-Negotiables

- Do not deploy to production.
- Do not commit to main without human review.
- Do not change production env values.
- Do not expose AI provider names, model names, keys, token counts, latency, prompts, or raw confidence to end users.
- Do not auto-execute AI write actions without explicit confirmation.
- Do not remove `Được tài trợ` / `Quảng cáo` labels.
- Do not hardcode university staff roles.
- Do not treat deleted or pre-reset backend/frontend code as production foundation.
- Do not mark a slice complete unless product, backend, frontend, AI, data,
  security, and verification gates pass or documented gaps remain open.

---

## 8. Canonical Naming

- AI chat module: `ai_assistant`
- AI provider/model settings: `ai_settings`
- Shared organization/RBAC module: `organization`
- Public organization API: `/api/v1/organizations`
- Jobs/events: `opportunities`
- Applications/pipeline/interviews/offers: `recruitment`
- V1 payment: manual/bank transfer adapter. Payment gateways are later-phase adapters.
