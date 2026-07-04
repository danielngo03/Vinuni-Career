---
name: vinuni-test-gate
description: Use to design or execute quality gates, acceptance criteria, regression coverage, and release-readiness checks.
---

# VinUni Test Gate

Use this skill for test plans, QA reviews, and final feature verification.

## Must Read

- `CLAUDE.md`
- `docs/TEST_STRATEGY.md`
- `docs/SECURITY_PRIVACY.md`
- `docs/API_CONTRACTS.md`
- `docs/SYSTEM_ACCEPTANCE_BAR.md`
- Feature-specific product and business docs.
- `docs/CV_STUDIO_SPEC.md` and `docs/SCREEN_SPECS.md` when CV/UI workflows are involved.

## Gate Priorities

1. Security, RBAC, tenant isolation.
2. User-visible workflow correctness.
3. Data integrity, idempotency, audit.
4. AI safety, provider leakage, confirmation.
5. Accessibility and responsive UI.
6. Performance and operational health.
7. Product/business fit and persona-surface completeness.

## Required Cases

- Happy path.
- Unauthenticated.
- Wrong role/persona.
- Cross-tenant access.
- Validation failure.
- Concurrency/idempotency if the workflow writes or reserves resources.
- Loading, empty, error, and permission UI states.
- AI fallback/leakage/adversarial cases if AI is involved.

## Output

Return a test matrix, commands to run, blockers, residual risk, and whether the feature passes the release gate.
Explicitly state whether `docs/SYSTEM_ACCEPTANCE_BAR.md` passes, partially
passes, or fails.
