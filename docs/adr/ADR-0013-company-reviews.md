# ADR-0013: Company Reviews — Moderation, Aggregate Strategy, Anonymity

**Status:** Accepted (scoping; implementation pending — Batch 24)
**Date:** 2026-06-29
**Module:** `reviews` (reserved in ARCHITECTURE §3.3) — backend/app/modules/reviews/
**Backlog:** E19 / ROADMAP M13 (PRD MODULE 15). Migration head at decision time: `0024_campaign_creatives`.

## Context

M13 lets eligible VinUni students review partner organizations; ratings must surface
as an aggregate + list on the high-read public company profile (`/vi/companies/{slug}`)
and directory; `university_staff` moderates; partners may report but not remove.
`DATA_MODEL §21` drafts `company_reviews` + `review_ratings` but lacks platform
conventions (soft-delete/version/audit/moderation-actor cols) and a read model.
Module-boundary rules (no cross-module ORM imports), "no live JOIN for public
surfaces", soft-delete/version/audit, and AI/privacy rules all apply.

Produced by `product-owner-system-planner` (scope) + `system-architect`
(data/API/boundaries) scoping passes.

## Decisions

1. **Reuse the reserved `reviews` module** (not `company_reviews`). Reconcile
   `DATA_MODEL §21` to add soft-delete/version/audit/moderation-actor columns, a
   `review_reports` table, and a `proj_company_rating` read model. Migration
   **`0025_company_reviews_and_ratings`** (next after `0024`).

2. **Moderation — first slice ships PRE-MODERATION (`pending` → human-published);
   flip to the BUSINESS_LOGIC §7.3 delayed-auto-publish + AI-gate model when AI
   moderation (B-343) lands.** This is the orchestrator-ratified resolution of the
   PO/architect divergence: the §7.3 live model is safe *only because the AI scan is
   the gate*, and AI moderation is Phase-3 and **resource-BLOCKED** (no
   `OPENROUTER_API_KEY`). Auto-publishing unscanned, potentially defamatory/PII-laden
   reviews on a VinUni-branded surface is unacceptable. Phase-2 review volume makes a
   human pre-moderation queue cheap. **AI, once available, is advisory only — it never
   auto-removes; humans have final say** (ARCHITECTURE constraint 12). `BUSINESS_LOGIC
   §7.3` must record this phased transition (pre-moderation → auto-publish+AI), not
   leave code/doc in silent conflict.

3. **Eligibility is interaction-gated (affirm BUSINESS_LOGIC §7.1).** Author must be a
   VinUni student with an application to that org that reached `INTERVIEW` or further
   (or `OFFER`/`ACCEPTED`). Eligibility is evaluated **at submit** and the resulting
   `eligibility_type` is **frozen on the row** (not re-derived on read), so a later
   withdrawn/deleted application does not retroactively invalidate a published review.
   `self_declared` low-trust reviews are an **open question** for V1 (see below).

4. **One review per student per company** via a plain `UNIQUE(org_id, reviewer_id)`
   (NOT partial) so a soft-deleted row still blocks a duplicate; re-review = edit/
   restore the existing row, never a second insert. Duplicate POST → `409
   {reason:"review_exists"}`, client routes to edit.

5. **Aggregate via projection (`proj_company_rating`), recompute-on-event** — not
   on-read `GROUP BY`. The public profile/directory is guest-heavy and Bayesian
   scoring (`(n·avg + 3·3.0)/(n+3)`, §7.2) needs `n` + per-category sums; a live join
   violates "no live JOIN for public". Recompute is full-per-org (idempotent,
   `INSERT … ON CONFLICT (org_id) DO UPDATE`), driven by `review.published/removed/
   restored` outbox materializer + a nightly `reviews.rating_reconcile` safety sweep
   (ADR-0003 scheduler). `n=0` → `overall_avg` NULL → "Chưa có đánh giá" empty state,
   never the 3.0 prior shown as a real score.

6. **Anonymity is display-only.** `is_anonymous` masks author identity to public
   readers/notifications but never weakens eligibility or the uniqueness constraint,
   and author identity stays visible to university moderation (accountability). The
   flag is reserved in the schema now; public anonymous display (B-342) is deferred.

7. **Boundaries via facades BOTH directions — no cross-module ORM imports.**
   - `organization → reviews`: `reviews.company_rating_facade.ratings_for(org_ids)`
     reads `proj_company_rating` only; `company_directory_service` batch-resolves
     ratings for the page's org_ids (no N+1), like it already batches job counts.
   - `reviews → organization`: new `org_lookup_facade.listable_id_for_slug` (slug→id,
     visibility predicate, id only) + existing `org_reporting_facade.display_names_for`.
   - `reviews → users`: new `student_directory_facade.display_for` (display name/avatar
     only, no PII).
   - `reviews → recruitment`: new `review_eligibility_facade.eligibility_for(user, org)`.
   The `organization↔reviews` facade modules must not import each other; resolve any
   app-wiring import cycle with function-local imports, never by widening a module.

8. **Partners report, never remove.** Removal is university-only and **policy-gated at
   the service layer**: the reason must map to §7.3 allowed criteria (PII / harassment
   / spam / false-claim); a genuinely negative opinion or low score with explanation
   is **non-removable**. V1: a flagged-but-not-removed review **stays published** and
   still counts toward the aggregate (only `removed` drops it) — so one bad-faith
   report cannot hide a genuine review.

## Consequences

+ Fast public reads, clean module boundaries, human-final-say moderation, truthful
trust badges, no unmoderated content public before AI exists.
− A second module↔module facade pair to keep ORM-local; the projection can briefly lag
a publish until the materializer runs (bounded by the nightly reconcile). When B-343
lands, a follow-up flips moderation to the §7.3 model and updates this ADR + §7.3.

## Alternatives rejected

- **Auto-publish live model in slice 1** — unsafe without the AI gate (defamation/PII
  exposure window); deferred to when B-343 exists.
- **On-read aggregate (`GROUP BY` per profile render)** — violates no-live-JOIN-for-
  public; slow at scale.
- **Denormalized aggregate on `organizations`** — couples org writes to review writes
  (cross-module write coupling).
- **Partial unique index excluding soft-deleted** — would let a soft-deleted review be
  bypassed by a second insert; the plain unique + edit/restore path is safer.

## First implementation slice (Batch 24)

submit → eligibility-gated store → university pre-moderate (publish/remove) → display
Bayesian aggregate + published list on the company profile; guest read + login-gated
CTA; author edit (30-day window, re-moderates) + soft-delete. Out of slice 1: anonymous
public display (B-342), AI moderation (B-343, blocked), partner public response (B-344),
verified-employee badge (B-347), helpfulness voting/sorting.

## Required doc updates at implementation time

`DATA_MODEL §21` (reconciled schema + `review_reports` + `proj_company_rating`);
`API_CONTRACTS.md` (M13 endpoint table + company-profile `rating` block + notification
types); `ARCHITECTURE.md` (reference this ADR; new facade seams); `BUSINESS_LOGIC §7.3`
(record the pre-moderation → auto-publish+AI phased transition);
`EDGE_CASES_FAILURE_MODES.md` (eligibility-loss, anonymity-leak, report-spam,
AI-scan-down).

## Open questions for implementation

1. V1 ships `self_declared` (low-trust) reviews, or system-verified only? (Affects the
   eligibility facade + trust-badge set.) Recommend **system-verified only** for slice 1.
2. `partner_verified` reviews — defer (no partner write path in V1). Recommend defer.
3. RBAC: new `reviews:moderate` permission on university roles vs. fold into an existing
   `moderation` resource — confirm with `product-owner-system-planner` for the seed.
   Must not hardcode staff roles.
