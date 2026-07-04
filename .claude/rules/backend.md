---
description: Backend implementation, API design, migrations, workers, and backend security rules.
paths:
  - backend/**
  - docs/ARCHITECTURE.md
  - docs/API_CONTRACTS.md
  - docs/DATA_MODEL.md
  - docs/SECURITY_PRIVACY.md
---

# Backend Rules

Use for backend implementation, backend review, API design, migrations, workers, and security-sensitive services.

## Must Read

- `CLAUDE.md`
- `docs/PRODUCT_REALITY_REBUILD_SPEC.md` for broad feature realism and
  adjacent backend/data/workflow contracts
- `docs/ARCHITECTURE.md`
- `docs/BUSINESS_LOGIC.md` for touched domain rules
- `docs/CV_STUDIO_SPEC.md` for CV upload/builder/import/export tasks
- `docs/CV_INGESTION_EXTRACTION_SPEC.md` for uploaded-CV preview,
  OCR/layout extraction, ingestion jobs, LLM fallback, and import review
- `docs/DISCOVERY_RECOMMENDATION_ADS_SPEC.md` for discovery, recommendation,
  guest session, ad placement, and monetization contracts
- `docs/DATA_MODEL.md`
- `docs/API_CONTRACTS.md`
- `docs/SECURITY_PRIVACY.md`
- `docs/ENVIRONMENT.md`
- `docs/LOCAL_DEV_STACK.md`
- `docs/NOTIFICATIONS_COMMUNICATIONS_SPEC.md` for notification/email/account settings tasks
- `docs/EDGE_CASES_FAILURE_MODES.md`
- `docs/SYSTEM_ACCEPTANCE_BAR.md`
- `docs/TEST_STRATEGY.md`

## Greenfield Stack Defaults

- Python 3.12+
- FastAPI async
- SQLAlchemy 2.x async
- Pydantic v2
- Alembic
- PostgreSQL 16+
- Redis 7
- Celery 5
- uv
- Local-first app runtime; Docker is optional infrastructure only until explicitly regenerated.
- Lightweight OCR/parser defaults: PyMuPDF/PyMuPDF4LLM adapter when available,
  pdfplumber fallback, python-docx, and Tesseract `vie+eng` fallback.

## Module Shape

```text
backend/app/modules/{domain}/
  api/
  application/
  domain/
  infrastructure/
```

- Router: HTTP only.
- Application: use cases, permission checks, transactions.
- Domain: pure concepts and invariants.
- Infrastructure: ORM, external adapters, repositories.

## Non-Negotiables

- RBAC must be enforced in service/application layer, not only in routers.
- Partner Admin has wildcard organization control by default, but recruiter
  features must remain grantable by permission, role, user, and department. Do
  not hardcode analytics, click metrics, CV access, billing, exports, pipeline,
  or AI recruiting actions to a role name; follow
  `docs/PARTNER_RBAC_ANALYTICS_SPEC.md`.
- Every write action must create audit data.
- No raw enum codes in end-user responses.
- No AI provider/model/token internals in end-user responses.
- No business logic in routers.
- No direct cross-module implementation imports; communicate through interfaces/events/read models.
- No dashboard with heavy live multi-domain joins; use projections/read models.
- Do not call a list "recommended" unless the backend returns genuine reason
  codes, scoring/session/profile/CV signals, or an explicit fallback source such
  as `recent` or `popular`.
- Public discovery/ad APIs must separate organic, recommended, sponsored, and
  university-curated inventory. Sponsored selection can fill paid slots, but it
  must not silently override organic relevance.
- Guest discovery sessions store only privacy-safe coarse signals and must not
  include PII, exact location, raw IP, raw CV text, or third-party ad IDs.
- File access uses signed URLs, not direct storage paths.
- Organization logos/media use safe delivery URLs (`logo_url`/media URL) and
  never expose raw `logo_path`, object keys, local paths, bucket names, or
  document storage keys in public/company/job/dashboard responses.
- CV download by partner requires watermark.
- Sensitive candidate access by partners (application open where identity/CV is
  visible, CV preview/download, reveal request, revealed-identity view) must be
  auditable and scoped by RBAC.
- CV Studio writes are versioned; application CV snapshots are immutable.
- CV Studio template/canvas data is backend-owned. Templates need layout schema,
  content-binding schema, owner/version/status metadata, preview/render
  validation, and university publish/archive audit. Do not store CV templates as
  unversioned frontend-only JSON.
- Natural-language CV edits must create pending structured diffs/suggestions.
  They must not mutate `cv_profiles`, `cv_sections`, canvas data, or exports
  until the student accepts the change.
- CV Studio quota is enforced server-side. Default student active CV library
  limit is 5 unless tier config overrides it; UI-only quota checks are not
  enough.
- CV-to-job fit scoring is a backend/AI contract. Return user-facing 0-100
  product score, category explanation, stale/no-eligible/AI-unavailable states,
  and never expose raw confidence, provider/model, prompt, token, embedding, or
  storage internals.
- Student job competition intelligence is a backend/read-model contract, not a
  decorative frontend badge. It must use privacy-safe aggregate/bucketed data
  such as hiring target/seats, application volume, applicant quality buckets,
  selected CV fit bucket, deadline freshness, and source mix. Hide or mark
  `low_signal` when data is insufficient; never expose other applicants, exact
  ranks, raw CV text, raw model confidence, provider/model, prompt, token, or
  cost internals.
- CV upload/parse must handle blank, non-CV, corrupt, password-protected, duplicate, low-quality, and security-rejected files.
- CV ingestion must be backend-owned and adapter-based. Do not build product
  logic around one parser library. Native text, layout extraction, OCR fallback,
  and optional LLM structuring are separate interfaces with versioned outputs and
  user-safe statuses.
- CV ingestion should be asynchronous or resumable for non-trivial files. A
  request-path parser is acceptable only for the smallest first slice and must
  be documented as functional-only.
- Uploaded-CV import creates reviewable structured data and then a versioned CV
  draft after user confirmation; it must never silently overwrite accepted CV
  content.
- Never send raw PDF/image bytes to an LLM. Only extracted/redacted text or
  markdown may be sent, and only when AI settings/env allow it.
- Celery tasks must be idempotent.
- Notification dispatch uses an outbox and template renderer; no synchronous SMTP dependency in product writes.
- Device/session APIs must not expose raw IP, raw refresh tokens, or full user-agent strings.
- Browser refresh tokens must use httpOnly cookies; do not return refresh tokens
  in JSON responses or require frontend localStorage for session continuity.
- TOTP must be enforced at login and secrets encrypted at rest before the UI
  advertises 2FA as active.

## Naming Defaults

- Internal organization/RBAC module: `organization`
- Public org API paths: `/api/v1/organizations`
- AI chat module: `ai_assistant`
- AI admin config module: `ai_settings`
- Jobs/events module: `opportunities`
- Applications/pipeline/interviews/offers module: `recruitment`
- CV upload/builder/export module: `documents`

## Payment Default

V1 uses manual/bank transfer confirmation. Gateway adapters for VNPay/MoMo/ZaloPay are later-phase unless explicitly requested.

## Delivery Checklist

- API contract updated.
- Migration has upgrade and downgrade.
- Permission and tenant isolation tests added.
- Failure-mode tests added for invalid/empty/duplicate/concurrent/async cases.
- CV ingestion tests cover text PDF, Vietnamese CV, two-column PDF, scanned/image
  CV, canvas/vector-heavy or sparse-native-text PDF, DOCX, blank, not-CV,
  password/corrupt, duplicate, OCR unavailable, and LLM disabled/unavailable.
- Write operations audited.
- Errors follow `docs/API_CONTRACTS.md`.
- Tests run or explicit reason why not.
