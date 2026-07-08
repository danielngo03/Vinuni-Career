# ADR-0010: Subscriptions & Manual Billing (V1) — Tiered Plans + Limit Resolution

**Status:** Accepted (Proposed for implementation in the next backend slice)
**Date:** 2026-06-28
**Owner:** system-architect
**Related:** `docs/PRODUCT_REQUIREMENTS.md` §1.3 (Nguồn thu: partner packages + student
subscriptions), §2.1 (student tiers), §2.2 (partner `Billing` resource: view/purchase),
§2.3 (Admin "Subscription Packages": tên/giá/thời hạn/limits override/tier nào mua được),
§18.6 (Revenue & Billing), §"subscription expiring" notifications (lines 1486, 1964),
`docs/BUSINESS_LOGIC.md` §1 (Subscription & Billing — proration/downgrade/cancellation/
grace/quota — the **deferred** end-state), §1.6 (Quota Management), §2.1 (`PartnerPackage`
limits), §4B.4 (CV quota defaults + "University admin can tune limits per package/tier"),
`docs/DATA_MODEL.md` §19 (`partner_packages` / `partner_subscriptions` / `quota_usage` /
`payment_records` / `student_subscriptions` — the **reference end-state**), `docs/
API_CONTRACTS.md` §"Subscriptions & Packages" + §"Quota", `docs/SECURITY_PRIVACY.md`
(billing PII / who confirms payment), `docs/EDGE_CASES_FAILURE_MODES.md`. **Mirrors the
shipped ADR-0009 advertising pattern** (`ad_packages` seeded fixed-price tiers +
`sponsored_placements` lifecycle + manual `mark_paid` + university-only oversight gate +
frozen price + ADR-0003 scheduler sweeps + revenue/`meta.spend` roll-up). Wires the
**shipped CV-quota tier-override hook** (`documents/application/cv_service.py`
`_active_cv_limit()` reading `STUDENT_ACTIVE_CV_QUOTA`, default 5, explicitly noted as a
"future per-tier override hook"). Builds on **ADR-0003** (the asyncio scheduler) and the
`organization`/membership + `Principal` model.

## Context

Quotas exist as a **concept** across the docs (BUSINESS_LOGIC §1.6/§4B.4, DATA_MODEL §19,
PRD §2.2/§2.3) but are **enforced for exactly one thing today: the CV active-library cap**.
That cap is already server-side and was built with an explicit seam for this epic —
`cv_service._active_cv_limit()` returns `get_settings().student_active_cv_quota` (default
5) and documents in-code that "FUTURE HOOK: resolve a per-tier / per-university override
here … falling back to the platform default." The CV-library quota presenter even emits
`quota_source: "student_tier"` in anticipation. **Nothing sets a tier.** There is no plan
entity, no subscription entity, no manual-billing flow, no expiry, and no way for the CV
cap (or any future quota) to read a paid tier. This ADR designs that missing monetization
layer — the next roadmap slice — and **wires the CV cap as the first real consumer** of it.

The parallel **advertising manual-billing pattern is already shipped (ADR-0009)** and is the
template to mirror: a seeded fixed-price reference table (`ad_packages`), a lifecycle entity
with a state machine + frozen price snapshot + `paid_at`/`payment_reference`/`paid_by`
fields, a **university-only oversight gate** (`_require_advertising_moderator`: superadmin OR
member of a `university` org holding the resource's `moderate` action), an admin `mark_paid`
that activates, **idempotent status/time-gated scheduler sweeps** for date-window crossings,
a revenue/`meta.spend` roll-up, optimistic `version`, per-write audit, and `404` cross-org
masking. We reuse all of it.

Constraints that bound the decision (CLAUDE.md):

- **V1 payment default is manual/bank-transfer** — no VNPay/MoMo/ZaloPay/Stripe gateway.
- **Local-first, lightweight, small reversible first slice.** No business logic in routers;
  RBAC at the service layer; every write audited; no raw enum codes / no provider internals
  to end users; no live heavy joins for read surfaces.
- **No direct cross-module implementation imports** — the documents module must read tier
  limits through a thin facade, never by importing subscription ORM (mirrors how
  `advertising` drives `opportunities` flags through one one-way facade).

BUSINESS_LOGIC §1 and DATA_MODEL §19 describe a **very large billing end-state**: upgrade
**proration** with credit carry-forward, scheduled **downgrade**, a 7-day refund window,
**payment-failure grace/dunning**, auto-renew, period-reset **metered quota** tracking
(`quota_usage`) with carryover, AI credits, and a per-persona split into
`partner_packages`/`student_subscriptions`/`payment_records`. Shipping that now would be a
brittle mega-slice and contradicts the manual-billing default. This ADR designs the
**foundational manual-billed core only** — a student or partner **requests a paid plan**,
an admin records a **bank transfer** to activate it for a **fixed window**, the plan's
**limits override the defaults** (CV cap first) — with stable FKs so proration / metered
quotas / gateways attach later without rework.

## Decision

### 1. New `billing` module; unified audience-typed `subscription_plans` (not split per-persona)

**Decision: a new module `backend/app/modules/billing/`** (DDD shape:
`api/application/domain/infrastructure`), public API under **`/api/v1/billing`** + admin
under **`/api/v1/admin/billing`**. The plan entity is **`subscription_plans`** — a single
**audience-typed** seeded reference table serving **both** a student tier set **and** a
partner tier set, with the granted **limits as a structured JSON map** rather than a wide
column-per-quota schema. This mirrors `ad_packages` (one small seeded reference table) and
keeps **one** lifecycle, **one** `mark_paid` path, and **one** limit-resolution facade
instead of two parallel per-persona stacks. The DATA_MODEL §19 split
(`partner_packages`/`student_subscriptions` + per-column `job_post_quota`/… + `quota_usage`
+ `payment_records`) is the **deferred reference end-state** (see Doc conflicts) and is
**not created** by this ADR.

#### `subscription_plans` columns

| column | type | note |
| --- | --- | --- |
| `id` | uuid pk | |
| `code` | varchar(40) unique | stable seed key (`student_free`, `student_pro`, `partner_basic`, `partner_pro`) |
| `name` / `name_en` | varchar(120) | vi + en display |
| `audience` | varchar(10) | `student` \| `partner` (CHECK) — who may subscribe |
| `billing_period` | varchar(10) | `monthly` \| `annual` (CHECK); `duration_days` derives the window |
| `duration_days` | int | window length set onto the subscription at `mark_paid` (monthly=30, annual=365) |
| `price_amount` | numeric(12,2) | `0` for the default/free plan |
| `currency` | varchar(5) default `VND` | |
| `limits` | json default `{}` | **structured limits map** the facade resolves (§3) |
| `is_default` | bool default false | the free baseline plan for the audience (no subscription row needed to get it) |
| `is_visible` | bool default true | hide retired plans without deleting |
| `sort_order` | smallint default 0 | |
| `created_at` / `updated_at` | timestamptz | |

**`limits` map (structured, forward-compatible).** Keys are the union of the per-tier knobs
the docs already name (BUSINESS_LOGIC §1.6/§4B.4, PRD §2.2/§2.3, §2.1); **V1 only
*resolves* and *enforces* `cv_active_quota`** — the rest are stored on the seeded plans so
the surfaces can *display* what a tier grants, and so later slices enforce them through the
*same* facade without a schema change:

```jsonc
// student plan limits (free vs pro)
{ "cv_active_quota": 5,  "pdf_exports_per_month": 3,  "premium_templates": false, "mass_apply_limit": 0 }  // student_free (is_default)
{ "cv_active_quota": 10, "pdf_exports_per_month": 50, "premium_templates": true,  "mass_apply_limit": 10 } // student_pro
// partner plan limits (basic vs pro)
{ "job_post_quota": 5,  "featured_job_slots": 0, "passive_search_quota": 0,  "email_blast_quota": 0  } // partner_basic (is_default)
{ "job_post_quota": 20, "featured_job_slots": 3, "passive_search_quota": 50, "email_blast_quota": 10 } // partner_pro
```

**Seed (migration `0019`, 4 rows):** `student_free` (default, price 0, `cv_active_quota=5`
== the shipped `STUDENT_ACTIVE_CV_QUOTA` default), `student_pro` (`cv_active_quota=10`,
matching BUSINESS_LOGIC §4B.4 "premium override"), `partner_basic` (default, price 0),
`partner_pro`. University admin tunes plan prices/durations/limits later via the same table
(PRD §2.3 "Admin set limits per package via UI") — V1 ships the seed; an admin plan editor
is deferred.

### 2. `subscriptions` entity + lifecycle (mirrors the advertising placement machine)

**Decision: one polymorphic `subscriptions` table** keyed to a **principal that is either a
user (student) or an org (partner)** — mirroring `sponsored_placements`' polymorphic target.
A **subscription row exists only for a PAID plan**: the free/default plan needs **no row**
(absence of an active paid subscription == default-plan limits), so there is no backfill and
the facade's "no subscription → default" path *is* the free tier.

#### `subscriptions` columns

| column | type | note |
| --- | --- | --- |
| `id` | uuid pk | |
| `principal_type` | varchar(10) | `user` \| `org` (CHECK) |
| `principal_id` | uuid | **no FK** (polymorphic: users OR organizations); service-validated to the caller |
| `plan_id` | uuid fk subscription_plans | chosen paid plan; `plan.audience` must match the principal kind (CHECK-by-service) |
| `billing_period` | varchar(10) | frozen from the plan at request |
| `price_amount` | numeric(12,2) | **frozen snapshot** of `plan.price_amount` at request (price freeze, like ADR-0009/0007) |
| `currency` | varchar(5) default `VND` | |
| `status` | varchar(20) default `pending` | state machine below |
| `start_at` / `end_at` | timestamptz null | the active window; **set at `mark_paid`** (`end_at = paid_at + plan.duration_days`); null while `pending` |
| `requested_by` | uuid fk users | who created the request (partner Admin or the student) |
| `paid_at` | timestamptz null | set by admin `mark_paid` (manual/bank-transfer) |
| `payment_reference` | varchar(120) null | bank-transfer ref the admin records |
| `paid_by` | uuid fk users null | admin who confirmed payment |
| `cancel_reason` | text null | admin reject / requester cancel note |
| `expiring_notified_at` | timestamptz null | T-7d "expiring soon" dedupe stamp |
| `requested_at` / `activated_at` / `expired_at` / `cancelled_at` | timestamptz null | transition stamps (audit-friendly) |
| `settings` | json default `{}` | forward room (renewal-of ref, proration credit, gateway txn) |
| `created_at` / `updated_at` | timestamptz | |
| `deleted_at` | timestamptz null | soft delete |
| `version` | int default 1 | optimistic concurrency |

#### Lifecycle — `billing/domain/lifecycle.py` (vi+en labels, never raw codes)

```
pending   -> requester chose a paid plan; awaiting manual bank-transfer confirmation
active    -> admin recorded payment (mark_paid); inside [start_at, end_at]; plan limits apply
expired   -> end_at passed (scheduler); reverts to default-plan limits          [terminal]
cancelled -> requester or admin stopped it (pre/active); reverts to default      [terminal]
```

| event | from-states | to-state | actor |
| --- | --- | --- | --- |
| `request` (create) | — | `pending` | **student (own user)** or **partner Admin (own org)** |
| `mark_paid` | `pending` | `active` (sets `start_at=now`, `end_at=now+duration_days`, paid fields) | **university/admin** |
| `cancel` | `pending`, `active` | `cancelled` | **requester (own)** or **university/admin** (reject pending / revoke active) |
| *(auto)* `expire` | `active` | `expired` when `end_at ≤ now` | **scheduler** (`billing.expiry_sweep`) |

- **No `approved` intermediate state** (the key simplification vs ADR-0009): a subscription
  has **no disclosure/creative to moderate** — payment *is* the only activation gate. So
  `mark_paid` (`pending → active`) is the single manual gate, one fewer transition than the
  advertising machine. *(An `approved` state was considered and rejected as redundant —
  there is nothing for the university to approve before payment.)*
- **No `awaiting_payment` state** — same rationale as ADR-0009: `pending` *is* awaiting
  payment; the `paid_at` write is the unambiguous activation signal.
- `EDITABLE_STATES = {pending}` (a requester may change the chosen plan only while pending —
  V1 keeps it simpler: cancel + re-request instead of edit). `DELETABLE_STATES = {pending}`
  (soft delete a never-paid request). An `active` subscription is `cancel`led, never deleted.
- **Renewal = a new `request`** once the prior window is terminal (no auto-renew in V1).
- **One in-flight subscription per principal** (partial-unique index, §6) — re-requesting
  while a `pending`/`active` row exists → `409 subscription_exists`. A new request is allowed
  only after the prior one is `expired`/`cancelled`.
- Idempotent transitions (re-mark_paid / re-cancel are no-ops), optimistic `version`,
  illegal transition → `409`, cross-principal → `404` — all mirroring
  `advertising/application/moderation_service.py`.

### 3. Limit resolution — the load-bearing integration seam

**Decision: a thin one-way facade `billing/application/limit_facade.py` is the ONLY way any
module reads tier limits; the documents module calls it WITHOUT importing subscription
ORM** — exactly mirroring how `advertising` drives `opportunities` through one
`sponsorship_facade` (dependency `documents → billing`, never reverse; `billing` never
imports `documents`).

```python
# billing/application/limit_facade.py  (the seam)
async def resolve_limits(session, principal) -> dict:
    """Return the active paid subscription's `plan.limits` map for this principal,
    or {} when there is no active paid subscription (== default/free tier).
    Chooses the org subscription when principal.org_id is set (partner), else the
    user subscription (student). Only status='active' AND end_at > now() counts."""

async def resolve_limit(session, principal, *, key: str, default):
    """Single-key convenience: resolve_limits(...).get(key, default)."""
```

**Wiring the CV cap (the first real consumer).** `cv_service._active_cv_limit()` becomes
async and resolves through the facade instead of reading the platform setting directly:

```python
# documents/application/cv_service.py  (BEFORE)
def _active_cv_limit() -> int:
    return get_settings().student_active_cv_quota          # always 5

# documents/application/cv_service.py  (AFTER — fills the documented FUTURE HOOK)
async def _active_cv_limit(session, principal) -> int:
    from app.modules.billing.application import limit_facade   # lazy: one-way seam
    return await limit_facade.resolve_limit(
        session, principal,
        key="cv_active_quota",
        default=get_settings().student_active_cv_quota,        # 5 when no paid sub
    )
```

- Callers `_enforce_active_cv_quota(session, principal)` and `cv_library_quota(session,
  principal)` pass the principal through; the quota presenter's `quota_source` becomes
  **`"subscription"`** when an override is applied, else **`"student_tier"`** (today's value)
  — so the UI can honestly say "10 active CVs (Pro plan)" vs the default 5.
- **Same seam for every other quota later.** `pdf_exports_per_month`, `job_post_quota`,
  `passive_search_quota`, etc. resolve through `resolve_limit(...)` with their own key and
  platform default — but their **enforcement** (usage counting + period reset) is **deferred**
  (§8): the CV cap is a *standing* cap (count of active rows), so it needs **no** `quota_usage`
  period-reset machinery, which is why it is the correct first slice.
- The facade runs **one** indexed query per check (no N+1, no heavy join), tolerable on the
  CV create/list hot path; a request-scoped memoization is a trivial later optimization.

### 4. Manual billing record — fields on the subscription (mirror ADR-0009 exactly)

**Decision: the manual payment lives as fields on the `subscriptions` row**
(`paid_at`, `payment_reference`, `paid_by`, frozen `price_amount`) — **not** a separate
table — mirroring `sponsored_placements.mark_paid` precisely. Each subscription window is
one row and (V1) one payment, so a row *is* the billing record. **No gateway, no
`payment_records` ledger** in V1. A multi-payment ledger (`subscription_payments`) and
gateway transactions are the deferred end-state (§8); `settings` json holds forward room for
a gateway txn id / proration credit without a migration.

`mark_paid` (university/admin) records the bank-transfer reference, sets `paid_at`/`paid_by`,
opens the window (`start_at=now`, `end_at=now+duration_days`), and transitions `pending →
active` — the exact shape of `advertising` `mark_paid`, minus the separate approval gate.

### 5. Disclosure / oversight — university sees all + a revenue roll-up

Mirror the advertising oversight `meta.spend` exactly as **`meta.revenue`**:

- **`GET /admin/billing/subscriptions`** (university/admin only) lists **all** subscriptions
  (filter by `status`/`audience`/`principal`) plus a **revenue roll-up**:
  `{ active_revenue_amount, currency, active_count, pending_count }` (sum of frozen
  `price_amount` over `active` rows) — the §18.6 "Revenue & Billing" surface.
- The **university-only gate** is the **same shape** as `_require_advertising_moderator`
  (superadmin OR member of a `university`-type org holding `billing:moderate`) — a partner
  Admin's `*:*` cannot self-confirm payment.
- **Self-service principals see only their own** subscription (`GET /billing/subscription`)
  and their own plan options. **Public sees nothing** (plans are auth-gated — see Doc
  conflict #6).
- **Billing data is PII-sensitive (SECURITY_PRIVACY):** revenue/`payment_reference` appear
  only in admin responses and audit `after` (intentional, like ADR-0009); **never** in
  notification feed bodies, never in non-admin responses, never in logs. Partners/students
  see their frozen `price_amount` and `payment_instructions` only.

### 6. Data model + migration `0019_subscriptions_and_manual_billing`

**One migration `0019`** (upgrade **and** downgrade; latest is `0018`), two tables (Postgres
runtime + SQLite tests via shared `JsonType`), ORM in `billing/domain/models.py`:

| table | key columns / FKs | notes |
| --- | --- | --- |
| `subscription_plans` | per §1 | seeded (4 rows) in the migration data step; reference data. CHECK `audience IN ('student','partner')`, `billing_period IN ('monthly','annual')`. |
| `subscriptions` | per §2 | **no FK** on `principal_id` (polymorphic; service-validated). Soft delete. CHECK `principal_type IN ('user','org')`, `status IN ('pending','active','expired','cancelled')`. |

Indexes: `idx_subscriptions_principal (principal_type, principal_id, status) WHERE
deleted_at IS NULL` (drives the facade lookup), `idx_subscriptions_window (status, end_at)
WHERE deleted_at IS NULL` (drives the expiry sweep), partial unique
`uq_subscription_inflight (principal_type, principal_id) WHERE status IN ('pending','active')`
(one in-flight subscription per principal). Postgres-only partial/CHECK constructs live in
the migration; the SQLite test path enforces the same invariants in the service layer
(same convention as ADR-0009 `0017`).

**Scheduler jobs (ADR-0003 registry, delegating to `billing` services, idempotent,
status/time-gated):**

| job | cadence | action | idempotency |
| --- | --- | --- | --- |
| `billing.expiry_sweep` | ~10 min (600s) | `status='active' AND end_at ≤ now` → `expired`, set `expired_at`, notify owner | status/`end_at` gate; re-run is a no-op |
| `billing.expiring_notice` | nightly | `status='active' AND end_at ≤ now+7d AND expiring_notified_at IS NULL` → enqueue "expiring soon" + set stamp | `expiring_notified_at` dedupe stamp (PRD §subscription-expiring) |

No inline expiry needed (expiry is purely time-based); `mark_paid`/`cancel` flip status
inline in their own transaction. Single-scheduler assumption inherited from ADR-0003 (the
status/time gates make a second runner safe-but-wasteful).

### 7. API surface

```
Self-service (student own-user OR partner Admin own-org; permissions billing:view / billing:purchase)
  GET   /billing/plans?audience=student|partner   visible plans for my audience (name, price, period,
                                                    limits summary of what each grants). Auth-gated.
  GET   /billing/subscription                      my current subscription (active|pending) + resolved
                                                    limits + default-tier fallback; null-safe when none
  POST  /billing/subscription                      request a paid plan -> pending; freezes price; returns
                                                    `payment_instructions` (bank-transfer details);
                                                    409 subscription_exists if a pending/active row exists;
                                                    422 plan_audience_mismatch if plan.audience != principal
  POST  /billing/subscription/cancel               cancel my pending|active subscription (reverts to default)

University / admin (permission billing:moderate — revenue + payment oversight)
  GET   /admin/billing/subscriptions               ALL subscriptions, filter status/audience/principal;
                                                    + meta.revenue roll-up (active spend, counts)
  POST  /admin/billing/subscriptions/{id}/mark-paid records manual bank-transfer payment_reference -> active
                                                    (sets window + paid fields); 422 reference_required
  POST  /admin/billing/subscriptions/{id}/cancel   admin revoke/reject (reason) -> cancelled
```

- **Routers are HTTP-only** (validate → service → envelope); RBAC + audit + principal
  isolation + transactions live in the services, mirroring `advertising/api/router.py` +
  `moderation_service`. The **university-only gate** for `/admin/billing/*` reuses the
  `_require_*_moderator` shape.
- **Permission mapping** (PRD §2.2 partner `Billing: view, purchase`): partner verbs →
  `billing:view|purchase`; cancel → `billing:purchase` (own). Student self-service maps to
  the same `billing:view|purchase` granted to the student role (a student manages **only**
  their own user-scoped subscription — ownership check like CV ownership). University
  oversight → `billing:moderate`.
- **Presenters** emit vi+en labels (`status_label`, `plan_name`, `billing_period_label`),
  the frozen price + currency, the window, and the plan's human-readable grants — **never raw
  enum codes, never another principal's data, never `payment_reference` to a non-admin.**
- **The student/partner "billing/plan" surface** reads `GET /billing/plans` +
  `GET /billing/subscription` (current tier, what it grants, expiry, request/cancel). The
  **admin oversight surface** reads `GET /admin/billing/subscriptions` (all + revenue).
  **Public sees nothing.**

### 8. Scope boundary & first implementation slice

**THIS ADR (ADR-0010) covers:** the `billing` module + `subscription_plans` (audience-typed,
limits-map, 4 seeded plans) + `subscriptions` (polymorphic user/org principal) (migration
`0019`), the `pending → active → expired | cancelled` lifecycle with admin manual
`mark_paid` (bank-transfer, frozen `price_amount`, fields-on-row), **date-windowed expiry**
(`billing.expiry_sweep` + `expiring_notice` on the ADR-0003 scheduler), the
**limit-resolution facade** (`billing/application/limit_facade.py`) and its **first wiring —
the CV active-library quota** (`cv_service._active_cv_limit` → facade, default 5), the
university **all-subscriptions + revenue roll-up** oversight, notifications, and the standard
invariants (optimistic `version`, illegal-transition `409`, cross-principal `404`, one
in-flight per principal `409`, per-write audit, PII-safe logs, no raw codes).

**Explicitly DEFERRED (named so FKs/columns/keys stay stable; later ADRs):**

- **Payment gateways** (VNPay/MoMo/ZaloPay/Stripe), self-serve checkout, a multi-payment
  `subscription_payments` / `payment_records` ledger, invoice/receipt PDF (V1 = fields on
  the subscription + manual `mark_paid` per CLAUDE.md).
- **Upgrade proration + credit carry-forward** (BUSINESS_LOGIC §1.2), **scheduled downgrade**
  (`pending_downgrade_to`, §1.3), **refund/7-day cancellation window** (§1.4),
  **payment-failure grace + dunning/retry** (§1.5), **auto-renew** — V1 expiry simply reverts
  to the default plan; renewal is a fresh request.
- **Metered-quota *enforcement*** for `job_post_quota` / `passive_search_quota` /
  `email_blast_quota` / `pdf_exports_per_month` + the `quota_usage` period-reset/carryover
  machinery (BUSINESS_LOGIC §1.6, DATA_MODEL §19) — V1 *resolves* these limits through the
  facade and *displays* them, but only **enforces** `cv_active_quota` (a standing cap needing
  no period reset). Each later quota plugs into the **same** facade.
- **`student_ai_credits`** / credit-based AI metering (separate concern).
- **Admin plan editor UI** (PRD §2.3) — V1 ships the seeded plans; tuning is via the table.
- The **DATA_MODEL §19 per-persona split** (`partner_packages` + `student_subscriptions` +
  per-column quota schema) — superseded for V1 by the unified `subscription_plans` (Doc
  conflict #1).

**First implementation slice (backend-first) — for `backend-developer`:**

1. **Migration `0019`** — create `subscription_plans` (+ seed 4 rows: `student_free`,
   `student_pro`, `partner_basic`, `partner_pro` with the §1 limits maps) and `subscriptions`
   (+ the two indexes, the partial-unique `uq_subscription_inflight`, the CHECKs) with upgrade
   **and** downgrade. ORM models `billing/domain/models.py`.
2. **Domain** — `billing/domain/lifecycle.py`: status/transition map, `audience`/
   `billing_period` vocab, vi+en label tables, `EDITABLE_STATES`/`DELETABLE_STATES`,
   `TERMINAL_STATES`, pure predicates (`can_transition`, `is_active_now(status, end_at, now)`).
   No I/O.
3. **Facade (the seam)** — `billing/application/limit_facade.py`: `resolve_limits(session,
   principal)` + `resolve_limit(session, principal, *, key, default)` (one indexed query;
   org-sub when `principal.org_id` set else user-sub; only `active` + `end_at > now`).
4. **Services** —
   `subscription_service.py` (list_plans / get_mine / request[freeze price + audience-match +
   one-inflight gate + `payment_instructions`] / cancel; RBAC `billing:view|purchase`, audit,
   `version`, principal-ownership `404`);
   `moderation_service.py` (list_all + revenue roll-up / `mark_paid` / admin_cancel;
   **university-only gate** mirroring `_require_advertising_moderator`);
   `expiry_service.py` (`expiry_sweep` / `expiring_notice` shared by the scheduler).
5. **documents integration** — make `cv_service._active_cv_limit(session, principal)` async,
   resolve via `limit_facade`; thread `principal` through `_enforce_active_cv_quota` and
   `cv_library_quota`; set `quota_source` to `"subscription"` when overridden else
   `"student_tier"`. **The one-way `documents → billing` lazy import is the only new
   cross-module edge.**
6. **API** — `billing/api/router.py` (`/billing`) + `admin_router.py` (`/admin/billing`)
   per §7, HTTP-only + Pydantic schemas + presenters (vi+en labels, frozen price, grants
   summary, never raw codes / other-principal data / `payment_reference` to non-admins);
   mount under `/api/v1/billing` + `/api/v1/admin/billing`.
7. **Scheduler** — register `billing.expiry_sweep` (~600s) + `billing.expiring_notice`
   (nightly) in `automation/scheduler/jobs.py`, delegating to `expiry_service`.
8. **Notifications** — catalog/template entries (vi+en, category `billing`, outbox + in-app
   feed, allowlisted variables): `subscription.payment_recorded` / `subscription.active`
   (to owner), `subscription.expiring` (T-7d, deduped), `subscription.expired`,
   `subscription.cancelled`. **No `payment_reference`/revenue in feed bodies.**
9. **Tests (SQLite, `tester-qa` gate):** request → `pending` (409 on duplicate in-flight;
   422 on audience mismatch) → admin `mark_paid` → `active` (window set, price frozen,
   bank-ref recorded); **CV-quota override resolves** (student on `student_pro` may create a
   6th active CV; `cv_library_quota.quota_source == "subscription"`, `active_cv_limit == 10`);
   **facade default** (no subscription → `_active_cv_limit == 5`); **expiry sweep** → `expired`
   → CV cap reverts to 5; cancel (requester + admin) → reverts; **cross-principal → 404**;
   **mark_paid/list-all university-only → 403** for a partner Admin; **revenue roll-up** sums
   active frozen prices; scheduler `tick` expiry idempotent; audit row per write; **PII-safe**
   (no `payment_reference` in feed bodies/logs).

**Frontend slice (follows, after the contract is green) — for `frontend-developer`:** a
student **plan/billing surface** (current tier + what it grants + expiry + "Upgrade" →
choose plan → bank-transfer instructions + pending state) and a partner equivalent under
their ops shell; the university **billing oversight surface** (all subscriptions,
mark-paid/cancel, revenue roll-up — §18.6); honest empty/permission/`409`-exists/`422`-
mismatch/`pending-awaiting-payment` states (no `confirm()` dialogs). The **CV library quota
counter** should now read `quota_source` and show the tier name when overridden. Mark
`API wired` → `browser verified` → `E2E verified` distinctly.

## Consequences

- **Positive:** the documented CV tier-override hook becomes **real** — a student/partner
  requests a paid plan, an admin records a bank transfer, and the plan's `limits` map flows
  through one facade to override the CV cap (and, later, every other quota) — with university
  revenue oversight, expiry, and instant admin revoke. Reuses every proven ADR-0009 invariant
  (lifecycle machine, university gate, frozen price, manual `mark_paid`, `404` masking,
  optimistic `version`, audit, outbox+feed notifications, ADR-0003 scheduler) and the
  cross-module law (one-way `documents → billing` via one facade, no reverse import). The
  limits-map + single polymorphic subscription keeps V1 to **one** lifecycle and **one**
  resolution seam instead of two per-persona stacks.
- **Cost / limits:** one migration (`0019`), two tables, one new module, two scheduler jobs,
  one new cross-module facade edge, and a signature change to `cv_service._active_cv_limit`
  (sync→async, now session/principal-aware — its three callers update). V1 is **manual
  fixed-window** — no proration, no downgrade scheduling, no refund window, no grace/dunning,
  no auto-renew, no metered-quota enforcement beyond the CV cap, no gateway. Single-scheduler
  assumption inherited from ADR-0003.
- **Reversibility:** the module is additive; dropping `0019` + the new routers/services +
  the scheduler registrations + reverting `_active_cv_limit` to the settings read restores
  the current default-5 behavior with the CV slice intact. Proration / metered quotas /
  gateways / the §19 `quota_usage` ledger attach to stable `subscription_plans` /
  `subscriptions` FKs (or arrive as the §19 end-state alongside) without rework.

## Doc conflicts resolved (precedence: product > business > security > arch > API/data)

1. **Unified `subscription_plans` vs DATA_MODEL §19 per-persona split.** §19 declares
   separate `partner_packages` (wide per-column quotas) + `student_subscriptions` +
   `quota_usage` + `payment_records`. **Resolved (architecture-simplicity + manual-billing
   precedence, mirroring shipped `ad_packages`):** V1 ships a single **audience-typed
   `subscription_plans`** with a **`limits` JSON map** + one polymorphic `subscriptions` +
   fields-on-row payment. **Flag DATA_MODEL §19** as "deferred reference end-state; V1 ships
   the unified `subscription_plans`/`subscriptions` per ADR-0010; `quota_usage`/
   `payment_records`/`partner_packages` per-column model not created yet."
2. **Proration / downgrade / refund / grace (BUSINESS_LOGIC §1.2–§1.5).** **Resolved:**
   **all deferred** — V1 is manual fixed-window, expiry reverts to default, renewal is a fresh
   request (CLAUDE.md "V1 payment default is manual/bank-transfer", small reversible slice).
   **Flag §1.2–§1.5** as "deferred; V1 = manual fixed-window per ADR-0010."
3. **Metered quota tracking (BUSINESS_LOGIC §1.6 + DATA_MODEL `quota_usage`).** **Resolved:**
   V1 **resolves+displays** all limit keys through the facade but **enforces only
   `cv_active_quota`** (a standing cap, no period reset). `job_post`/`passive_search`/
   `email_blast`/`pdf_exports` enforcement + `quota_usage` reset/carryover **deferred**.
   **Flag §1.6** accordingly.
4. **AI credits (DATA_MODEL `student_ai_credits`, §4B.4 "ai_cv_actions: credit-based").**
   **Resolved:** **deferred** — out of scope for this billing slice; the limits map carries a
   placeholder only.
5. **RBAC actor for payment confirmation.** API_CONTRACTS §"Subscriptions" lists
   `POST /billing/payment-records | University Admin (confirm)`. **Resolved:** consistent —
   **university/admin `billing:moderate` confirms** via `mark_paid` (mirrors ADR-0009).
6. **Plans public vs auth-gated.** API_CONTRACTS lists `/packages/partner | GET | Public`.
   **Resolved (brief: "Public sees nothing"):** V1 plans are **auth-gated, scoped by
   audience** (`GET /billing/plans?audience=…`). **Flag the API_CONTRACTS row** as reconciled
   to auth-gated; a public marketing pricing page is a later, separate read-only surface if
   product wants it.
7. **Endpoint shape.** API_CONTRACTS §"Subscriptions & Packages" lists per-persona paths
   (`/subscriptions/partner`, `/subscriptions/student`, `/packages/student`). **Resolved:**
   reconciled to the **unified** `/billing/plans` + `/billing/subscription` (+ `/admin/billing
   /subscriptions`) surface per §7; **flag** API_CONTRACTS to the ADR-0010 surface.

## Implementation checklist (next backend slice)

1. Migration `0019_subscriptions_and_manual_billing`: `subscription_plans` (+ seed 4) +
   `subscriptions` (+ indexes + `uq_subscription_inflight` + CHECKs); upgrade **and**
   downgrade. ORM `billing/domain/models.py`.
2. `billing/domain/lifecycle.py`: states/transitions/labels/predicates (pure).
3. `billing/application/limit_facade.py`: `resolve_limits` / `resolve_limit` (the seam).
4. `billing/application/{subscription_service,moderation_service,expiry_service}.py` per §8
   (RBAC at service layer, audit per write, principal-ownership `404`, frozen price,
   one-inflight gate, university-only gate, revenue roll-up).
5. `documents/application/cv_service.py`: `_active_cv_limit(session, principal)` async via
   facade; thread `principal` through `_enforce_active_cv_quota` + `cv_library_quota`;
   `quota_source` = `subscription` when overridden.
6. `billing/api/{router.py,admin_router.py}` + schemas + presenters per §7; mount under
   `/api/v1/billing` + `/api/v1/admin/billing`.
7. `automation/scheduler/jobs.py`: register `billing.expiry_sweep` (600s),
   `billing.expiring_notice` (nightly).
8. Notifications catalog/template + feed entries (category `billing`, vi+en, allowlisted
   vars) per §8.8 (no payment ref / revenue in bodies).
9. Tests per §8.9 (SQLite).
10. Docs: this ADR; ARCHITECTURE §4 pointer (added); flag DATA_MODEL §19 + BUSINESS_LOGIC
    §1.2–§1.6 + API_CONTRACTS §"Subscriptions & Packages"/§"Quota" per Doc conflicts; add the
    `billing` module to the ARCHITECTURE §3.3 module map; reconcile the `cv_service`
    `quota_source`/`_active_cv_limit` notes.
```
