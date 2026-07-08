# ADR-0009: Advertising — Sponsored / Featured Placements (V1 Manual-Billed)

**Status:** Accepted (Proposed for implementation in the next backend slice)
**Date:** 2026-06-28
**Owner:** system-architect
**Related:** `docs/PRODUCT_REQUIREMENTS.md` MODULE 13 (Advertising System) + §"Sponsored
content label bắt buộc" + the partner-package/permission tables (lines 34–35, 91, 131,
216–220), `docs/BUSINESS_LOGIC.md` §9 (Advertising — Business Rules) + §2.1
(`PartnerPackage`), `docs/DATA_MODEL.md` §20 (`ad_campaigns` / `ad_campaign_targeting`)
+ §"jobs/events `is_sponsored`/`is_featured`" (lines 737–738, 948–949),
`docs/SECURITY_PRIVACY.md` §"Advertising Compliance" (lines 14, 103–120), `docs/DESIGN.md`
§sponsored (label rules), `docs/API_CONTRACTS.md` (jobs/events + marketplace contracts to
mirror), `docs/EDGE_CASES_FAILURE_MODES.md`. Builds on the **shipped `opportunities`
module** (`domain/{models,event_models,lifecycle}.py`,
`application/{moderation_service,public_read,event_public_read,visibility}.py`,
`api/router.py`), the **shipped `marketplace` overview aggregator**
(`marketplace/application/overview_service.py`), the **shipped non-removable disclosure
infra** (`frontend/.../status-badge.tsx` + `globals.css` rendering `Được tài trợ` / `Nổi
bật` from the real flags, asserted in tests), **ADR-0003** (the asyncio scheduler — host
for the date-window activation/completion sweeps), and the jobs moderation/notification
pattern (**ADR-0008** mirrored events the same way).

## Context

The **sponsored infrastructure is shipped**: `jobs` and `events` carry
`is_sponsored` + `is_featured` booleans; `public_read.list_sponsored_summaries` /
`list_featured_summaries` (+ the event equivalents) read those **real** flags; the
`marketplace` overview renders sponsored/featured strips (hide-if-empty, never
fabricated); and the disclosure labels are **non-removable** in `status-badge.tsx` +
`globals.css` and asserted in tests. What does **not** exist is any way to *get* a flag
set: today `is_sponsored`/`is_featured` are only flipped by the demo seed or by hand.
There is **no** partner request-to-sponsor flow, **no** placement/campaign entity, **no**
approval or billing workflow, **no** date-windowed activation, and **no** university
oversight of ad spend or disclosure. This ADR designs that missing layer — the next
roadmap epic.

Constraints that bound the decision:

- **CLAUDE.md scope:** V1 payment default is **manual/bank-transfer** (no gateway); local-
  first; lightweight; a **small reversible** first slice; no business logic in routers;
  RBAC at the service layer; every write audited; no raw enum codes / no provider internals
  to end users; no live heavy joins for the marketplace strip.
- **Disclosure is non-negotiable (CLAUDE.md + SECURITY_PRIVACY §Advertising Compliance):**
  `Được tài trợ` / `Quảng cáo` / `Nổi bật` labels are mandatory and cannot be hidden by any
  UI/API option. Advertising must keep disclosure mandatory and **drive** the existing
  label, never bypass it.
- **The shipped flags are the rendered signal and must stay the only render path.** The
  marketplace must keep reading `is_sponsored`/`is_featured`; this module decides *why* and
  *when* they are set, without the marketplace learning anything about campaigns.
- **Cross-module law (ARCHITECTURE §8):** `advertising` owns placements; `opportunities`
  owns the `jobs`/`events` flag columns. Dependency is **one-way** `advertising →
  opportunities` through a thin facade; `opportunities` never imports `advertising`.

The DATA_MODEL §20 `ad_campaigns` + `ad_campaign_targeting` and BUSINESS_LOGIC §9 describe
a **very large end-state**: CPM/CPC bidding, daily/total budget pacing, banner/video/email-
blast/featured-employer creatives, audience targeting dimensions, impression/click
analytics, AI brand-safety scans, complaint flows. Shipping that now would be a brittle
mega-slice and would contradict the manual-billing default. This ADR designs the
**foundational manual-billed core only** — a partner *requests to sponsor/feature one of
their own jobs or events* for a paid, date-windowed, university-approved period — with
stable FKs so the bidding/analytics/creative system attaches later without rework.

## Decision

### 1. New `advertising` module; `sponsored_placements` is the placement entity (not `ad_campaigns`)

**Decision: a new module `backend/app/modules/advertising/`** (DDD shape:
`api/application/domain/infrastructure`), public API under **`/api/v1/advertising`** +
**`/api/v1/admin/advertising`**. The placement entity is **`sponsored_placements`**, a
partner's request to sponsor/feature **one target the partner already owns** (a `job` or an
`event`). The DATA_MODEL §20 `ad_campaigns`/`ad_campaign_targeting` tables (CPM/CPC/banner/
targeting/impressions) are the **deferred end-state** advertising system and are **not
created** by this ADR (see Doc conflicts) — `sponsored_placements` is the V1 entity that
actually drives the shipped flags.

**Polymorphic target reference (clean, validated, no leaky FK):** `target_type ∈ {job,
event}` + `target_id uuid`. **No DB foreign key** on `target_id` (it points at two tables);
instead a CHECK constrains `target_type`, and the **service layer validates** at create
time that the target exists, is not soft-deleted, and **belongs to the caller's org** (load
via the `opportunities` owner facade — cross-org or unknown target → `404`, mirroring jobs
enumeration-masking). A partial-unique index prevents two in-flight placements on the same
target (§6). This keeps the polymorphism honest without inventing a target-supertable.

### 2. `sponsored_placements` columns

| column | type | note |
| --- | --- | --- |
| `id` | uuid pk | |
| `org_id` | uuid fk organizations, indexed | owning partner org (the advertiser) |
| `created_by` | uuid fk users | partner author |
| `target_type` | varchar(10) | `job` \| `event` (CHECK) |
| `target_id` | uuid | **no FK** (polymorphic); service-validated to own org |
| `placement_type` | varchar(10) | `sponsored` \| `featured` \| `both` |
| `package_id` | uuid fk ad_packages | chosen tier (§5) |
| `price_amount` | numeric(12,2) | **frozen snapshot** from the package at `submit` (price freeze, like ADR-0007 comp) |
| `currency` | varchar(5) default `VND` | |
| `start_at` / `end_at` | timestamptz | the date window; `end_at > start_at` (CHECK) |
| `status` | varchar(20) default `draft` | state machine (§3) |
| `disclosure_confirmed` | bool not null default false | partner must acknowledge the non-removable label before `submit` (maps DATA_MODEL §20 `is_sponsored_label_confirmed`); `submit` with `false` → `422 disclosure_required` |
| `moderation_note` | text null | rejection reason / oversight note |
| `approved_by` | uuid fk users null | university approver |
| `paid_at` | timestamptz null | set by admin `mark_paid` (manual/bank-transfer) |
| `payment_reference` | varchar(120) null | bank-transfer ref the admin records |
| `paid_by` | uuid fk users null | admin who recorded payment |
| `submitted_at` / `approved_at` / `activated_at` / `completed_at` / `cancelled_at` | timestamptz null | transition stamps (audit-friendly, mirror jobs/events) |
| `settings` | json default `{}` | forward room (future creative/targeting refs) |
| `created_at` / `updated_at` | timestamptz | |
| `deleted_at` | timestamptz null | soft delete |
| `version` | int default 1 | optimistic concurrency |

Indexes (§6): `idx_placements_org (org_id, status) WHERE deleted_at IS NULL`,
`idx_placements_window (status, start_at, end_at) WHERE deleted_at IS NULL` (drives the
activation/completion sweeps), `idx_placements_target (target_type, target_id) WHERE
deleted_at IS NULL` (drives flag recompute), partial unique
`uq_placement_inflight (target_type, target_id) WHERE status IN ('pending_approval',
'approved','active')`.

### 3. Lifecycle, approval & manual payment

**`advertising/domain/lifecycle.py` state machine** (vi+en labels, never raw codes):

```
draft            -> partner editing the placement request
pending_approval -> partner submitted; university reviews disclosure + creative + spend
approved         -> university approved (content/disclosure/spend OK); awaiting payment + window
active           -> paid AND inside [start_at, end_at]; target flag(s) ON (§4)
completed        -> end_at passed (or window fully elapsed); target flag(s) OFF (§4)  [terminal]
rejected         -> university rejected; editable again, resubmittable                [terminal-ish]
cancelled        -> partner (pre/active) or university (anytime) stopped it; flag(s) OFF [terminal]
```

| event | from-states | to-state | actor |
| --- | --- | --- | --- |
| `submit` | `draft`, `rejected` | `pending_approval` | partner (requires `disclosure_confirmed=true`) |
| `approve` | `pending_approval` | `approved` | **university** |
| `reject` | `pending_approval` | `rejected` (coded reason) | **university** |
| `mark_paid` | `pending_approval`, `approved` | *(no status change; sets `paid_at`/`ref`/`paid_by`)* | **university/admin** |
| *(auto/inline)* `activate` | `approved` | `active` **iff** `paid_at IS NOT NULL AND start_at ≤ now < end_at` | scheduler **+ inline** |
| *(auto)* `complete` | `active`, `approved` | `completed` when `end_at ≤ now` | scheduler |
| `cancel` | `draft`,`pending_approval`,`approved`,`active` | `cancelled` | partner (own, pre-`completed`) **or** university (anytime — PRD §13.6 "University disable bất kỳ lúc") |

- `EDITABLE_STATES = {draft, rejected}`; `DELETABLE_STATES = {draft, rejected}` (soft
  delete). An `approved`/`active` placement must be `cancel`led, not deleted.
- **Approval = oversight of disclosure + spend** (university), distinct from **payment =
  money received** (admin `mark_paid`, manual/bank-transfer per CLAUDE.md). **Both are
  preconditions to `active`** — activation is gated on `status=approved AND paid_at IS NOT
  NULL AND window-open`. We deliberately keep payment as **fields + a separate admin action**
  rather than a `awaiting_payment` state, so the brief's state set stays small; an approved-
  but-unpaid placement whose window opens simply **stays `approved`** (flags OFF) until paid.
  *(Alternative `awaiting_payment` state rejected as redundant — the `paid_at` gate is
  unambiguous and one fewer transition.)*
- Idempotent transitions (re-approve/re-activate/re-complete are no-ops), optimistic
  `version`, illegal transition → `409`, cross-org → `404` — all mirroring
  `moderation_service`.

### 4. Flag source-of-truth: the placement is authoritative; the flag is a projection

**Decision: `sponsored_placements` is the SOURCE OF TRUTH for sponsorship; the shipped
`jobs/events.is_sponsored`/`is_featured` columns are a RENDERED PROJECTION recomputed from
active placements** — resolving the "free booleans" tension. The flag is **never** toggled
ad-hoc by advertising; it is **recomputed** so multiple/overlapping placements on one target
behave correctly:

```
desired_is_sponsored(target) = EXISTS active placement on target with placement_type IN (sponsored, both)
desired_is_featured(target)  = EXISTS active placement on target with placement_type IN (featured, both)
```

- **The only place flags change in production is one `opportunities` facade setter**
  (new `opportunities/application/sponsorship_facade.set_target_flags(session, target_type,
  target_id, *, is_sponsored, is_featured, reason)`): it loads the `job`/`event` row
  `FOR UPDATE`, sets the two booleans, bumps `version`, and writes an audit row
  (`job.sponsorship_changed` / `event.sponsorship_changed`, `after={is_sponsored,
  is_featured, reason}`). `advertising` **computes** the desired booleans from its own active
  placements and **calls** this setter — `opportunities` stays the owner+auditor of its
  columns; `advertising` is the decider. One-way dependency, no reverse import.
- **Activation** (`approved → active`): recompute → push flags ON. **Completion / cancel**
  (`→ completed`/`cancelled`): recompute → if **another** active placement still covers the
  target the relevant flag **stays ON**, else OFF. This makes two concurrent placements (e.g.
  a `featured` and a `sponsored` from the same org, or a renewal overlapping an expiry)
  correct by construction.
- **Drift guard:** a nightly idempotent `advertising.flag_reconcile` sweep recomputes flags
  for **every target that has ≥1 placement**, so manual/seed drift self-corrects. Targets
  with **no** placement row are left untouched (transitional — see below).
- **Demo seed reconciliation:** the demo seed currently sets `is_sponsored`/`is_featured`
  directly. Update the seed to instead create **`sponsored_placements` rows** (status
  `active`, open window) so the source-of-truth is uniform and the homepage strips are
  placement-backed. Bare seeded flags without a placement remain *real flags* (honest) but
  are explicitly transitional and slated to be replaced by seeded placements.

### 5. Packages, limits & fairness (V1 simple)

**`ad_packages`** — a small **seeded reference table** of named, fixed-price tiers (no
bidding, no budget pacing): `id`, `code` (unique), `name`, `price_amount`, `currency`
(`VND`), `duration_days`, `grants_sponsored bool`, `grants_featured bool`, `is_active`,
`created_at/updated_at`. Seed three: `featured_7d` (Nổi bật, 7d, featured-only),
`sponsored_14d` (Được tài trợ, 14d, sponsored-only), `premium_30d` (30d, both). The chosen
package constrains `placement_type` (a `featured`-only package can't request `sponsored`)
and `price_amount` is **frozen onto the placement** at submit. University admin tunes
package prices/durations (BUSINESS_LOGIC §2.1 "University admin sets limits per package").

**Limits (V1, config-driven):**

- **Marketplace display caps already shipped** stay: `_SPONSORED_CAP=3`, `_FEATURED_CAP=3`
  rendered slots (`overview_service`).
- **Fairness (don't let one org dominate):** when active inventory exceeds the display cap,
  the `public_read` sponsored/featured facades render **at most 1 slot per org** (dedupe by
  `org_id`), ordering by `activated_at` to rotate. True round-robin rotation is a minor
  later refinement.
- **Per-org concurrency cap:** `ADVERTISING_MAX_ACTIVE_PER_ORG` (default **3**) — `submit`
  is rejected `409 active_placement_limit` if it would exceed the org's concurrent in-flight
  (`pending_approval`/`approved`/`active`) placements.
- **One in-flight placement per target** (the partial-unique index) → re-requesting on a
  target that already has a live placement → `409 placement_exists`; a new placement is
  allowed only after the prior one is terminal.
- **Pricing display:** `GET /advertising/packages` returns name + price + duration + what
  each grants; the partner sees the frozen `price_amount` on their placement.

### 6. Data model + migration `0017_advertising_sponsored_placements`

**One migration `0017`** (upgrade **and** downgrade), two tables (Postgres runtime + SQLite
tests via the shared `JsonType`), ORM in `advertising/domain/models.py`:

| table | key columns / FKs | notes |
| --- | --- | --- |
| `ad_packages` | per §5 | seeded (3 rows) in the migration data step; reference data |
| `sponsored_placements` | per §2 | indexes `idx_placements_org`, `idx_placements_window`, `idx_placements_target`, partial unique `uq_placement_inflight`. Soft delete. CHECKs: `target_type IN ('job','event')`, `end_at > start_at`. |

**No FK on `target_id`** (polymorphic; service-validated). **No `ad_campaigns` /
`ad_campaign_targeting` / `ad_invoices` tables** (deferred — §8). The **flag-activation
mechanism** is the `opportunities.sponsorship_facade.set_target_flags` setter (§4); the
**scheduler jobs** (ADR-0003 registry, delegating to `advertising` services, idempotent,
status/time-gated):

| job | cadence | action | idempotency |
| --- | --- | --- | --- |
| `advertising.activation_sweep` | ~5 min | `status=approved AND paid_at IS NOT NULL AND start_at ≤ now < end_at` → `active`, set `activated_at`, recompute+push flags ON | status/`paid_at`/window gate; re-run is a no-op |
| `advertising.completion_sweep` | ~5 min | `status IN (active, approved) AND end_at ≤ now` → `completed`, set `completed_at`, recompute flags (OFF unless another active placement covers target) | status/`end_at` gate; idempotent |
| `advertising.flag_reconcile` | nightly | recompute flags for all targets with ≥1 placement (drift guard) | pure recompute; idempotent |

**Inline (not only swept):** `activate` also fires **inline** at `mark_paid`/`approve` when
the window is already open (instant go-live, not up-to-5-min lag); `cancel` of an `active`
placement recomputes flags **inline** in the same transaction. The sweeps are the safety net
for window-start/window-end crossings, exactly the ADR-0008 inline-plus-sweep pattern.
*(V1 single-scheduler assumption per ADR-0003; the status/window gates are idempotent so a
second runner is safe-but-wasteful.)*

### 7. API surface

```
Partner (org member; permissions advertising:view / :create / :edit / :submit)
  GET    /advertising/packages                       pricing tiers (name, price, duration, grants)
  GET    /advertising/placements                     my org placements, any status (advertiser surface)
  POST   /advertising/placements                     create draft (target_type, target_id, placement_type,
                                                       package_id, start_at) — validates target ownership (404 cross-org)
  GET    /advertising/placements/{id}                owner-full | 404
  PATCH  /advertising/placements/{id}                edit draft/rejected (version)
  POST   /advertising/placements/{id}/submit         draft|rejected -> pending_approval
                                                       (422 disclosure_required if not confirmed; 409 limit/exists)
  POST   /advertising/placements/{id}/cancel         own placement pre-completed -> cancelled (flags OFF if active)
  DELETE /advertising/placements/{id}                soft-delete draft/rejected

University / admin (permission advertising:moderate — oversight of disclosure + spend)
  GET    /admin/advertising/placements               ALL placements, filter by status/org (active + spend oversight)
  POST   /admin/advertising/placements/{id}/approve  pending_approval -> approved
  POST   /admin/advertising/placements/{id}/reject   pending_approval -> rejected (coded reason; 422 blank)
  POST   /admin/advertising/placements/{id}/mark-paid records manual/bank-transfer payment_reference (sets paid_at/paid_by)
  POST   /admin/advertising/placements/{id}/cancel   disable any placement immediately (flags OFF)
```

- **Routers are HTTP-only** (validate → service → envelope); RBAC + audit + tenant isolation
  + transactions live in the services, mirroring `opportunities/api/router.py` +
  `moderation_service`. The **university-only gate** for `/admin/advertising/*` is the
  **same shape** as `_require_university_moderator` (superadmin OR member of a `university`-
  type org holding `advertising:moderate`); a partner Admin's `*:*` cannot self-approve.
- **Permission mapping** (BUSINESS_LOGIC lines 91/131): partner verbs `view/create/edit/
  submit` → `advertising:view|create|edit|submit`; university `view/approve_campaign/
  reject_campaign` (+ mark-paid/disable) → `advertising:moderate`.
- **Presenters** emit vi+en labels (`status_label`, `placement_type_label`,
  `package_label`), the frozen price, and the target's public title/link — **never raw enum
  codes, never internal status of the target beyond what the partner already owns.**
- **Public NEVER sees campaign internals.** The `marketplace` overview contract is
  **unchanged** — it keeps reading the real `is_sponsored`/`is_featured` flags (now placement-
  driven) via the existing facades; it learns nothing about placements, prices, or approval.
  The **partner advertiser surface** reads `GET /advertising/placements`; the **university
  oversight surface** reads `GET /admin/advertising/placements` (all active placements + a
  spend roll-up). The only thing the public ever sees is the **non-removable label**.

### 8. Disclosure guarantee (non-negotiable)

- The **only** mechanism that turns on `is_sponsored`/`is_featured` in production is the
  placement activation in §4 → which flips the exact flags the shipped non-removable label
  infra (`status-badge.tsx` + `globals.css`) renders. **Campaign-driven sponsorship therefore
  automatically carries the mandatory `Được tài trợ` / `Nổi bật` label** — there is **no
  field, endpoint, or state** in this module that can render sponsored content without the
  label.
- `disclosure_confirmed` is a **submit precondition** (partner acknowledges the label).
- University can **see all active placements** (`GET /admin/advertising/placements`) and
  **disable any of them immediately** (`/cancel`) → flags OFF (PRD §13.6, SECURITY_PRIVACY
  §"University approval before sponsored content goes live").
- A regression test asserts: an `active` placement's target renders the non-removable label,
  and **no** advertising path can produce a sponsored target without it.

### 9. Scope boundary & first implementation slice

**THIS ADR (ADR-0009) covers:** the `advertising` module + `sponsored_placements` +
`ad_packages` (migration `0017`), the `draft → pending_approval → approved → active →
completed | rejected | cancelled` lifecycle with university approval + admin manual
`mark_paid`, **date-windowed activation** (inline + `activation_sweep`/`completion_sweep`/
`flag_reconcile` on the ADR-0003 scheduler), the **placement-as-source-of-truth /
flag-as-projection** model via the one `opportunities.sponsorship_facade` setter (audited,
recompute-based), the **disclosure guarantee**, simple **caps/fairness** (display cap,
per-org concurrency cap, 1-per-org strip dedupe, one in-flight per target), the partner
advertiser + university oversight API surfaces, **manual/bank-transfer billing** (fields +
`mark_paid`, frozen `price_amount`), notifications, the demo-seed reconciliation, and the
standard invariants (optimistic `version`, illegal-transition `409`, cross-org `404`,
per-write audit, PII-safe logs, no raw codes).

**Explicitly DEFERRED (named so FKs/columns stay stable; later ADRs):**

- **Payment gateways** (VNPay/MoMo/ZaloPay/Stripe), wallet/credit, self-serve checkout,
  refunds, an `ad_invoices`/receipt entity (V1 = fields on the placement + manual `mark_paid`
  per CLAUDE.md).
- **The DATA_MODEL §20 `ad_campaigns` end-state:** CPM/CPC **bidding**, `daily_budget`/
  `total_budget` **spend pacing**, real-time budget pause (BUSINESS_LOGIC §9.1).
- **Audience targeting** (`ad_campaign_targeting`, the §9.2 dimensions) — V1 sponsorship
  boosts placement of an *existing* job/event to all eligible viewers, no audience targeting.
- **Creative ad types** beyond sponsoring an existing target: banner / video / email-blast /
  featured-employer / homepage-hero / sidebar (PRD §13.1, DATA_MODEL §20 `ad_placement`).
- **Impression/click/CTR/apply-start analytics**, A/B testing, budget alerts, campaign
  dashboard metrics (PRD §13.5).
- **AI brand-safety / auto-approve** (PRD §13.4), the §9.3 **min-budget anti-spam** + 24h
  SLA enforcement + **complaint/report-ad** flow (>5 complaints re-review).

**First implementation slice (backend-first) — for `backend-developer`:**

1. **Migration `0017`** — create `ad_packages` (+ seed 3 rows) and `sponsored_placements`
   (+ the three indexes, the partial-unique `uq_placement_inflight`, the two CHECKs) with
   upgrade **and** downgrade. ORM models `advertising/domain/models.py`.
2. **`opportunities` facade** — add `opportunities/application/sponsorship_facade.py`:
   `set_target_flags(session, target_type, target_id, *, is_sponsored, is_featured, reason)`
   (loads job/event `FOR UPDATE`, sets flags, bumps `version`, audits) — **the only prod
   writer of the flags**.
3. **Domain** — `advertising/domain/lifecycle.py`: status/transition map, `placement_type`/
   `target_type` vocab, vi+en label tables, `EDITABLE_STATES`/`DELETABLE_STATES`, pure
   predicates (`can_transition`, `can_activate(now, start, end, paid, status)`,
   `compute_target_flags(active_placements)`). No I/O.
4. **Services** —
   `placement_service.py` (create/edit/submit[disclosure + caps gate]/cancel/delete/get/
   list_mine, **target-ownership validation via the `opportunities` owner facade**, RBAC +
   audit + version, **inline activate-if-window-open**);
   `moderation_service.py` (queue/approve/reject/mark_paid/admin-cancel, **university-only
   gate** mirroring `_require_university_moderator`, spend oversight list);
   `activation_service.py` (`activate`/`complete`/`recompute_target_flags` shared by the
   scheduler **and** inline callers — single source).
5. **API** — `advertising/api/router.py` (`/advertising`) + `admin_router.py`
   (`/admin/advertising`) per §7, HTTP-only + Pydantic schemas + presenters (vi+en labels,
   frozen price, never raw codes/target internals).
6. **Scheduler** — register `advertising.activation_sweep` (~300s), `advertising.
   completion_sweep` (~300s), `advertising.flag_reconcile` (nightly) in
   `automation/scheduler/jobs.py`, delegating to `activation_service`.
7. **Notifications** — add catalog/template entries (vi+en, category `advertising`, outbox +
   in-app feed, allowlisted variables): to university — `advertising.submitted` (new request
   to review); to partner — `advertising.approved`, `advertising.rejected` (reason),
   `advertising.payment_recorded`, `advertising.live`, `advertising.ending` (T-24h before
   `end_at`, deduped) — matching PRD §"campaign live/ending" partner notifications. No
   provider internals, no spend leakage to non-admins.
8. **Demo seed** — replace direct `is_sponsored`/`is_featured` sets with seeded `active`
   `sponsored_placements` (uniform source-of-truth).
9. **Tests (SQLite, `tester-qa` gate):** create→submit (disclosure gate `422`)→approve→
   mark_paid→activation (window open) → flags ON; completion sweep → flags OFF; reject (coded
   reason); cancel active → flags OFF + recompute; **target ownership cross-org → 404**;
   **double in-flight on same target → 409**; **activation requires paid** (approved + in-
   window + unpaid stays `approved`, flags OFF); **two active placements on one target** →
   recompute keeps the relevant flag ON until both complete; **per-org concurrency cap →
   409**; **disclosure label rendered** for an activated target (and no path produces
   sponsored without it); university sees all + can disable any (flags OFF); marketplace
   contract unchanged (still reads real flags); scheduler `tick` activation/completion
   idempotent; audit row per write; PII-safe logs (no payment/PII in feed bodies).

**Frontend slice (follows, after the contract is green) — for `frontend-developer`:** the
partner **advertiser surface** (request a placement on one of my jobs/events: pick target +
package + window, mandatory disclosure checkbox, see status + frozen price + `live/ending`),
the university **ad oversight surface** (all placements, approve/reject/mark-paid/disable,
spend roll-up), honest empty/permission/`409`-limit/`409`-exists/`422`-disclosure states (no
`confirm()` dialogs), and **no change to the public marketplace** (it already renders the
non-removable label from the now-placement-driven flags). Mark `API wired` → `browser
verified` → `E2E verified` distinctly.

## Consequences

- **Positive:** the shipped flags + non-removable disclosure infra become a **real, earned**
  signal — a partner requests, the university approves disclosure + spend, an admin records
  manual payment, and the placement drives the exact flags the marketplace already renders,
  inside a date window, with university power to disable instantly. The placement-as-source-
  of-truth / flag-as-projection model kills the "free boolean" drift while keeping the
  marketplace contract untouched. Reuses every proven invariant (lifecycle machine, university
  moderation gate, RBAC-`404` masking, optimistic `version`, audit, outbox+feed
  notifications) and the ADR-0003 scheduler; the cross-module rule holds (one-way
  `advertising → opportunities` via one audited setter).
- **Cost / limits:** one migration (`0017`), two tables, one new module, three scheduler
  jobs. V1 is **manual fixed-price** — no bidding, no budget pacing, no targeting, no
  analytics, no banner/video/email creatives, no payment gateway. Fairness is coarse (per-org
  concurrency cap + 1-per-org strip dedupe); true rotation/auction is later. Single-scheduler
  assumption inherited from ADR-0003.
- **Reversibility:** the module is additive; dropping `0017` + the new routers/services + the
  scheduler registrations + the `sponsorship_facade` reverts to seed/manual flag-setting with
  the marketplace and disclosure infra fully intact. The deferred bidding/analytics/creative
  system attaches to stable `sponsored_placements`/`ad_packages` FKs (or arrives as the §20
  `ad_campaigns` end-state alongside) without rework.

## Doc conflicts resolved (precedence: product > business > security > arch > API/data)

1. **`ad_campaigns` (DATA_MODEL §20) vs `sponsored_placements`.** §20 declares a CPM/CPC/
   banner/targeting/impression `ad_campaigns` + `ad_campaign_targeting`. **Resolved (CLAUDE.md
   manual-billing precedence):** that is the **deferred end-state**; V1 ships
   `sponsored_placements` + `ad_packages` which actually drive the shipped flags. **Flag
   DATA_MODEL §20** as "deferred bidding/analytics end-state; V1 ships `sponsored_placements`
   per ADR-0009; `ad_campaigns`/`ad_campaign_targeting` not created yet. `is_sponsored_label_
   confirmed` → `sponsored_placements.disclosure_confirmed`."
2. **Pricing model — CPM/CPC/FIXED + budgets + real-time pause (BUSINESS_LOGIC §9.1).**
   **Resolved:** V1 is **FIXED-equivalent named packages, manual `mark_paid`, no bidding/
   budget pacing** (CLAUDE.md "V1 payment default is manual/bank-transfer"). **Flag §9.1** as
   "bidding/budget pacing deferred; V1 = fixed-price `ad_packages` per ADR-0009."
3. **Targeting dimensions (BUSINESS_LOGIC §9.2 / PRD §13.2).** **Resolved:** **no audience
   targeting in V1** — sponsorship boosts an existing job/event to all eligible viewers.
   **Flag §9.2** as "targeting deferred with `ad_campaign_targeting`."
4. **Approval workflow (BUSINESS_LOGIC §9.3): PENDING_REVIEW, 24h SLA, min-500k anti-spam, AI
   scan, complaint re-review.** **Resolved:** V1 keeps **manual university approval** +
   disclosure/spend review; **min-budget** is expressed via package price (not a separate
   rule), **24h SLA / AI scan / complaint flow deferred**. **Flag §9.3** accordingly.
5. **Ad types (PRD §13.1: banner/video/email-blast/featured-employer/event sponsorship).**
   **Resolved:** V1 covers **Sponsored Job + Featured + (job/event) sponsorship** via
   `target_type`; **banner/video/email-blast/featured-employer creatives deferred.** **Flag
   PRD §13.1.**
6. **Flag ownership.** DATA_MODEL puts `is_sponsored`/`is_featured` on `jobs`/`events`
   (`opportunities`). **Resolved:** columns stay in `opportunities` (owner+auditor); their
   **value is owned by `advertising`** via the one-way `sponsorship_facade` setter
   (recompute-based). Recorded here; no DDL change to `jobs`/`events`.

## Implementation checklist (next backend slice)

1. Migration `0017_advertising_sponsored_placements`: `ad_packages` (+ seed) +
   `sponsored_placements` (+ indexes + `uq_placement_inflight` + CHECKs); upgrade **and**
   downgrade. ORM `advertising/domain/models.py`.
2. `opportunities/application/sponsorship_facade.py`: `set_target_flags(...)` (load
   job/event `FOR UPDATE`, set flags, bump `version`, audit) — sole prod flag writer.
3. `advertising/domain/lifecycle.py`: states/transitions/labels/predicates (pure).
4. `advertising/application/{placement_service,moderation_service,activation_service}.py`
   per §9.4 (RBAC at service layer, audit per write, target-ownership validation, disclosure
   + caps gates, inline activate, recompute flags).
5. `advertising/api/{router.py,admin_router.py}` + schemas + presenters per §7; register
   alongside the module routers; mount under `/api/v1/advertising` + `/api/v1/admin/advertising`.
6. `automation/scheduler/jobs.py`: register `advertising.activation_sweep`,
   `advertising.completion_sweep`, `advertising.flag_reconcile`.
7. Notifications catalog/template + feed entries (category `advertising`, vi+en, allowlisted
   vars) per §9.7.
8. Demo seed: create `active` `sponsored_placements` instead of bare flag sets.
9. Tests per §9.9 (SQLite).
10. Docs: this ADR; ARCHITECTURE §4 pointer (added); flag DATA_MODEL §20 + BUSINESS_LOGIC
    §9.1/§9.2/§9.3 + PRD §13.1 per Doc conflicts; add the `advertising` module to the
    ARCHITECTURE §3.3 module map; API_CONTRACTS entries for the new endpoints.
