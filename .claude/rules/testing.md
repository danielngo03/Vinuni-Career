---
description: Test strategy, QA review, release gates, security/RBAC coverage, and test implementation rules.
paths:
  - backend/tests/**
  - frontend/**
  - docs/TEST_STRATEGY.md
  - docs/SECURITY_PRIVACY.md
---

# Testing Rules

Use for test plans, QA review, release gates, and test implementation.

## Must Read

- `CLAUDE.md`
- `docs/PRODUCT_REALITY_REBUILD_SPEC.md`
- `docs/TEST_STRATEGY.md`
- `docs/SECURITY_PRIVACY.md`
- `docs/API_CONTRACTS.md`
- `docs/SYSTEM_ACCEPTANCE_BAR.md`
- `docs/ENVIRONMENT.md`
- `docs/LOCAL_DEV_STACK.md`
- `docs/NOTIFICATIONS_COMMUNICATIONS_SPEC.md` when notification/account settings are touched
- `docs/EDGE_CASES_FAILURE_MODES.md`
- Feature-specific PRD/business logic sections

## Quality Priorities

1. Security and tenant isolation.
2. RBAC and permission boundaries.
3. User-visible workflow correctness.
4. Data integrity and idempotency.
5. AI safety and provider leakage.
6. Accessibility and responsive UI.
7. Performance and operational health.
8. System acceptance: product fit, persona workflow, backend/frontend/data/AI/security gates, and verified evidence.

## Required Coverage By Feature

- Unit tests for pure rules and validators.
- Integration tests for DB, services, permissions, and outbox.
- E2E/API tests for persona workflows.
- Frontend tests for critical forms, auth gates, confirmation flows, and sponsored labels.
- AI tests for tool confirmation, leakage, adversarial prompts, and fallback.
- Locale tests for vi/en detection and user override.
- Notification/template tests for preference filtering, variable validation, and no real outbound email in automated tests.
- Account/device tests for remote logout and safe device metadata.
- CV upload negative fixtures cover blank, non-CV, corrupt, password-protected, duplicate, low-quality, and rejected-security outcomes.
- CV Studio tests cover CV-first flows without mandatory profile completion,
  active CV quota, quota recovery, job-fit scoring, stale CV warning, no eligible
  CV, AI unavailable fallback, and immutable application snapshots.

## Release Gate

A feature is not done until:

- Acceptance criteria are testable.
- Permission and audit cases are covered.
- Failure states are covered.
- Regression risk is documented.
- Commands run are reported in the final handoff.
- `docs/SYSTEM_ACCEPTANCE_BAR.md` passes or the remaining gaps are explicitly recorded.

## Environment Hygiene

- Before backend tests, ensure inherited env vars match `docs/ENVIRONMENT.md`.
- `DEBUG` must be boolean. If the shell has `DEBUG=release`, `DEBUG=prod`, or
  any non-boolean value, override the test command with `DEBUG=false` and report
  the parent-shell misconfiguration in the handoff.
- AI/OCR/CV ingestion tests must pin relevant feature flags in the command or
  fixtures (`CV_LLM_STRUCTURING_ENABLED`, `CV_INGESTION_ASYNC`,
  `CV_OCR_ENGINE`, `AI_REAL_CALLS_ENABLED`) and reset runtime singletons after
  tests. Do not rely on whatever is currently in `backend/.env`.
- Test suites must be order-independent. If a module passes alone but fails when
  run after another module, treat it as a blocker/test-isolation bug and record
  it before continuing feature breadth.
- Tests must not require real AI keys. Real provider smoke tests are a separate,
  opt-in gate after offline evals pass.
- When real AI smoke is explicitly requested, use cheap internal aliases only,
  cap calls with `AI_MAX_REAL_CALLS_PER_TEST_RUN`, and never print API keys,
  provider/model names, raw prompts, or PII-bearing responses.
