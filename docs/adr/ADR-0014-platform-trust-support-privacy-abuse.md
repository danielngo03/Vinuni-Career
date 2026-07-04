# ADR-0014: Platform Trust — Support Console, Privacy/Compliance, Abuse/Fraud (E36)

**Status:** Accepted (architecture scoping; implementation pending)
**Date:** 2026-07-04
**Modules:** new `platform_support` (backend/app/modules/platform_support/), new
`compliance` (backend/app/modules/compliance/), extends `moderation`
(backend/app/modules/moderation/)
**Backlog:** B-555 / B-556 / B-557 (B-550 is process-only, no schema/API)
**Product decision packet:** ratified verbatim by `product-owner-system-planner`
(pasted in full in the originating task); this ADR is the architecture layer only.

## Context

E36 adds a platform-operations layer (support console, privacy/compliance
requests, abuse/fraud triage) that must reuse existing infrastructure rather
than fork parallel systems:

- `human_review_queue` (moderation module) already exists as the single
  human-in-the-loop queue for AI-escalated findings (`bias_detection` |
  `content_moderation` | `fraud_detection` | `agent_loop` sources, plain
  `String(32)` column, no DB enum/CHECK constraint — confirmed in migration
  `0052_human_review_queue.py`).
- `audit_logs` (shared) already has `before_snapshot`/`after_snapshot` JSONB
  columns — no schema gap for support/abuse override audit entries.
- `notification_outbox` (notifications module) already tracks per-row
  `status ∈ {pending, sent, failed, skipped, dead}` + `attempts` +
  `next_attempt_at` — this is the real outbox table (the cross-cutting
  `shared.models.OutboxEvent` is the generic domain-event outbox, a different
  table; B-555's "outbox health" reads `notification_outbox`, not
  `OutboxEvent`).
- `org_reporting_facade` + `admin_users_service.list_platform_users` already
  provide the account/org lookup seam.
- `PERMISSION_CATALOG` (`organization/domain/catalog.py`) is the single legal
  vocabulary for grantable permission strings; RBAC is enforced by
  `permission_checker` in the application layer using free-form
  `"{resource}:{action}"` strings — no new mechanism needed, only new catalog
  entries.

## Decisions

1. **New module `platform_support`** owns support-console *read/orchestration*
   services only: account/org lookup presenter, outbox health read model,
   requeue action, support-case resolve, reveal-audit wrapper, package-override
   entry point. It has **no new ORM tables** — it calls existing facades
   (`org_reporting_facade`, `admin_users_service`, `notifications.dispatch_service`,
   `moderation.review_queue_service`, `billing` package-assignment service,
   `documents` reveal service) and writes only to `audit_logs`
   (`resource_type` prefixed `support_*`) and `human_review_queue`
   (`source="support_case"`). Naming matches the existing single-word
   `platform_*` convention (`platform_feedback`, `platform_settings`).

2. **New module `compliance`** owns `consents` and `privacy_requests` (new
   tables) plus the retention-constant read endpoint and the retention
   enforcement job hook. Kept separate from `platform_support` because privacy
   requests are a **student-facing** write surface (`/account/privacy`) with
   its own lifecycle, not a staff console; kept separate from `moderation`
   because consent/privacy has no relationship to abuse triage. `compliance`
   is a new leaf module with no existing home in the module map.

3. **`content_reports` lives in `moderation`**, not a new module. Moderation
   already owns the one converged human-decision queue and the university
   moderation RBAC gate; abuse/fraud triage is a moderation concern by
   definition, and the triage view *merges* `content_reports` with
   `human_review_queue` — colocating avoids a cross-module join for that
   merge. `moderation/domain/models.py` gains `ContentReport` beside
   `HumanReviewItem`; `moderation/application/` gains `report_service.py`
   (submit/rate-limit) and `triage_service.py` (merged list, escalate,
   override). `fraud_scan_service.py` and `review_queue_service.py` are
   otherwise unchanged in shape.

4. **`human_review_queue.source` vocabulary is extended in code only** — add
   `SOURCE_SUPPORT_CASE = "support_case"` and `SOURCE_USER_REPORT =
   "user_report"` constants to `moderation/domain/models.py`. No migration
   required (plain `String(32)`, no CHECK constraint, no DB enum type). This
   is safe for `review_queue_service.list_items` (already filters by
   arbitrary `source` string) and `fraud_scan_service` (writes literal
   `SOURCE_FRAUD`, unaffected). See "Risk" below for the information a bare
   `source` string loses.

5. **No new `support_audit_events`, `support_cases`, or `fraud_signals`
   tables.** `docs/DATA_MODEL.md` §0 previously anticipated these three names;
   this ADR supersedes that anticipation — see doc updates below.

6. **RBAC:** six new permission nouns are added to `PERMISSION_CATALOG`
   (`organization/domain/catalog.py`): `support: {read, act, escalate}`,
   `privacy: {read, process}`, `abuse: {read, triage, escalate, override}`.
   No new hardcoded role; any university-org role can be granted these like
   `jobs:moderate`. `principal.is_superadmin` bypasses as usual. Each service
   function calls `permission_checker.require(principal, "support", "act")`
   style checks — mirrors `_require_university` gates already in
   `review_queue_service`/`admin_users_service`, but **not** hardcoded to
   "university org" — the packet does not restrict these nouns to
   `org_type=university` the way `jobs:moderate` implicitly is today via
   `_require_university`'s extra `is_university_org` check. Architect note:
   `support:*`/`privacy:*`/`abuse:*` should still be granted only on
   university-org roles in practice (partner orgs have no legitimate reason to
   hold them), so services **must** additionally call
   `org_reporting_facade.is_university_org` exactly like the existing
   `_require_university` helper — copy the pattern, do not skip it, so a
   misconfigured partner role can never be granted platform-support powers.

## Consequences

- Support/abuse/privacy staff surfaces are additive: zero breaking changes to
  `HumanReviewItem`, `AuditLog`, or `NotificationOutbox` schemas.
- `review_queue_service.list_items(source=...)` and the
  `/moderation/review-queue` route's `source` query param now also accept
  `support_case` / `user_report` — this is backward compatible (existing
  filters by `bias_detection`/`content_moderation`/`fraud_detection`/
  `agent_loop` are untouched).
- The triage/merge view is a new read-only aggregation in `moderation`, not a
  new projection table (acceptable at V1 volume; revisit as a projection if
  the merged query becomes a dashboard hot path per the "no live heavy joins"
  rule — flag for `data-engineer` if report volume grows).
- Retention enforcement (soft-delete/anonymize `application_snapshots` past a
  hardcoded constant) is a new scheduler job registered in
  `automation/scheduler/jobs.py` (ADR-0003 pattern), owned by `compliance`,
  calling into `documents`' snapshot facade — no direct ORM cross-import.

## Risk Flagged To Product

Merging AI-detected (`fraud_detection`, already severity-scored via
`assess_fraud_signals`) and user-submitted (`user_report`, no confidence
score, just a `reason_code` a reporter picked) escalations into one
`human_review_queue.source` vocabulary without a distinct
confidence/severity-provenance field **does lose information** the queue
currently carries implicitly: today `findings_json` for a `fraud_detection`
row contains `risk_score`/signal codes from a deterministic detector; a
`user_report`-sourced row's `findings_json` will contain only the reporter's
`reason_code` + note + report count — structurally different payloads under
the same `source` value. This is workable (the moderator UI can branch
rendering on `source`), but the merged triage list's **default sort/priority**
must not silently treat a single unverified user report as equally urgent as
a 0.9-confidence fraud detector hit. Mitigation (no schema change): triage
list ranks by `severity` (already a column) — `report_service.py` must set
`severity` heuristically at escalation time (e.g., `low` for a single report,
`medium` at N reports on the same entity within a window, `high` only via
explicit `abuse:escalate` override or when a report corroborates an existing
`fraud_detection` pending item on the same `resource_id`). Documented here so
the missing severity-provenance distinction is a known, deliberate trade-off
rather than a silent gap.

## Docs Updated

- `docs/ARCHITECTURE.md` §3.3 module map + new ADR-0014 summary paragraph.
- `docs/DATA_MODEL.md` §0 (reconciled table-name anticipation) + new §
  documenting `consents` / `privacy_requests` / `content_reports`.
- `docs/API_CONTRACTS.md` new sections: Platform Support Console, Privacy &
  Compliance, Abuse & Content Reports; RBAC catalog note.
