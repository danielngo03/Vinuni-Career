# ADR-0008: Events — Registration, Capacity/Waitlist & Check-in (Phase 2 Foundation)

**Status:** Accepted (Proposed for implementation in the next backend slice)
**Date:** 2026-06-28
**Owner:** system-architect
**Related:** `docs/PRODUCT_REQUIREMENTS.md` MODULE 14 (+ §2.10, §14.1–14.9),
`docs/BUSINESS_LOGIC.md` §6 (Events — Deep Logic), `docs/DATA_MODEL.md` §10
(`events` / `ticket_types` / `event_registrations`) + §26 (seats/promo),
`docs/SECURITY_PRIVACY.md` (PII, event covers, template variable allowlist),
`docs/NOTIFICATIONS_COMMUNICATIONS_SPEC.md` (§39 event registration/waitlist),
`docs/API_CONTRACTS.md` (jobs discovery + marketplace contracts to mirror),
`docs/SCREEN_SPECS.md` §1.1 (public event card / events teaser), `docs/DESIGN.md`
§6.5 (Event Pages), `docs/ARCHITECTURE.md` §4.2, `docs/EDGE_CASES_FAILURE_MODES.md`.
Builds directly on the **shipped jobs implementation** in the `opportunities`
module (`domain/{models,lifecycle}.py`,
`application/{job_service,public_read,visibility,moderation_service}.py`,
`api/router.py`), the `marketplace` overview aggregator, the notifications
outbox + in-app feed (`notifications/application/{dispatch_service,feed_service,
message_catalog}.py`), and the **ADR-0003** asyncio scheduler (`automation/
scheduler/jobs.py`) — the host for event reminders, no-show, auto-complete, and
the waitlist-backfill safety net.

## Context

Events **do not exist as a backend today.** The public marketplace renders an
honest "coming soon" events teaser, and `frontend/public/images/career-day-2026.jpg`
is an unused asset. Per CLAUDE.md naming defaults the `opportunities` module
"is for jobs/events discovery and creation," so events live **alongside jobs in
`opportunities`**, not in a new module.

Jobs already ship the exact pattern events need: a small explicit lifecycle state
machine (`opportunities/domain/lifecycle.py`), university moderation
(`/admin/jobs/{id}/approve|reject`, university-only gate in `moderation_service`),
RBAC-aware public discovery (`GET /jobs` + the `public_read`/`visibility` facade
the `marketplace` overview consumes), `is_sponsored`/`is_featured` flags, org
ownership + `posted_by`, optimistic `version`, soft delete, per-write audit, and
the outbox + in-app-feed notification pattern.

The PRD MODULE 14 + DATA_MODEL §10/§26 describe a **very large** end-state:
multiple paid ticket types, early-bird/promo pricing, numbered-seat selection with
Redis locks, encrypted online-link reveal, QR check-in, sponsor tiers, career-fair
booths, certificates, and post-event surveys. Shipping all of that now would be a
brittle mega-slice. This ADR designs the **foundational, free-admission core
only** — the part that makes the marketplace honest and lets students actually
register, get waitlisted, and be checked in — with stable FKs so ticketing /
payment / seats / QR attach later without rework.

Constraints that bound the decision:

- **CLAUDE.md scope:** V1 payment default is manual/bank-transfer; gateways are
  later-phase. Local-first, lightweight, small reversible first slice. No business
  logic in routers; RBAC at the service layer; every write audited; no raw enum
  codes to end users; no live heavy joins for the marketplace strip.
- **DATA_MODEL §10 already declares** `events`, `ticket_types`, `event_registrations`
  — but with a multi-ticket shape (`event_registrations.ticket_type_id NOT NULL`,
  `qr_code_hash NOT NULL`, `payment_status`) that presumes the deferred ticketing
  system. This ADR resolves those tables down to the free-admission V1 (see Doc
  conflicts).
- **The jobs surface is correct and must be mirrored, not duplicated by copy-paste
  drift:** events get their own `visibility.py` predicate + `public_read.py` facade
  (one source of truth per resource) following the jobs pattern exactly, and the
  university-moderator gate is the same shape as `moderation_service`.

## Decision

### 1. Event model — REUSE the jobs patterns (own table, own lifecycle)

**Decision: YES — `events` is a sibling of `jobs` inside `opportunities`, mirroring
the jobs state-machine + moderation + sponsored/featured + org-ownership shape, but
with an event-appropriate status vocabulary and time fields.** It is a separate
table (events are not jobs — different fields, different lifecycle end-states), not
a polymorphic merge.

**`events` lifecycle (`events/domain/event_lifecycle.py`, NOT shared with jobs):**

```
draft           -> creator editing; never publicly visible
pending_review  -> partner submitted; awaiting university moderation; edit-locked
published       -> approved + live; publicly discoverable (subject to dates/visibility)
cancelled       -> creator/university called the event off; notify registrants
completed       -> ends_at has passed (auto-set by scheduler); read-only/archival
rejected        -> university rejected; editable again, resubmittable
```

| event | from-states | to-state |
| --- | --- | --- |
| `submit` | `draft`, `rejected` | `pending_review` *(partner)* / `published` *(university auto-approve, §5)* |
| `approve` | `pending_review` | `published` |
| `reject` | `pending_review` | `rejected` |
| `cancel` | `published` | `cancelled` |
| *(auto)* `complete` | `published` | `completed` *(scheduler, `ends_at < now`)* |

- **Diverges from jobs deliberately:** jobs use `active`/`closed`/`expired`; events
  use `published`/`cancelled`/`completed`. Event semantics differ — an event is
  *published* (not "active"), and ends by *completing* (time passes) or being
  *cancelled*, never "closed." This is intentional and flagged below; the
  *machinery* (transition map, label tables, university-only moderation gate,
  optimistic `version`, audit) is the jobs machinery, mirrored.
- `EDITABLE_STATES = {draft, rejected}`; `DELETABLE_STATES = {draft, rejected,
  cancelled, completed}` (a `published` event must be cancelled before delete).
- Raw codes never reach users — every code has a vi+en label
  (`status_label`/`type_label`/`format_label`/`registration_state_label`), exactly
  like `lifecycle.py`.

**`events` columns** (canonical DATA_MODEL §10 shape + the same audit/moderation/
visibility columns the shipped `jobs` model added beyond its doc — flagged below):

| column | type | note |
| --- | --- | --- |
| `id` | uuid pk | |
| `org_id` | uuid fk organizations, indexed | owning organizer org |
| `created_by` | uuid fk users | author |
| `title` | varchar(500) | |
| `slug` | varchar(600) unique | discovery URL (mirrors `jobs.slug`) |
| `description` | text | |
| `event_type` | varchar(30) | `career_fair`\|`workshop`\|`info_session`\|`networking`\|`webinar` |
| `format` | varchar(20) | `onsite`\|`online`\|`hybrid` |
| `cover_image_path` | varchar(1000) null | stored path; **API exposes `cover_image_url` only** (never raw path — backend rule) |
| `venue_name` | varchar(300) null | onsite/hybrid |
| `venue_address` | text null | onsite/hybrid |
| `online_link` | varchar(1000) null | **omitted from V1 0016** — deferred with online-link reveal (§9) |
| `starts_at` / `ends_at` | timestamptz | |
| `timezone` | varchar(50) default `Asia/Ho_Chi_Minh` | |
| `registration_opens_at` | timestamptz null | null = open immediately on publish |
| `registration_closes_at` | timestamptz null | null = closes at `starts_at` |
| `capacity` | int **null** | **on the event** (V1 single admission); `NULL` = unlimited |
| `registration_count` | int default 0 | maintained counter of `confirmed` regs (cheap, denormalized; the lock-protected source of truth is the `COUNT`, this is a display mirror) |
| `visibility` | varchar(20) default `public` | reuses jobs §5 matrix (`public`/`authenticated`/`students_only`/`vinuni_only`/`invitation_only`) |
| `status` | varchar(20) default `draft` | lifecycle above |
| `moderation_status` | varchar(20) default `pending` | `pending`\|`approved`\|`rejected`\|`flagged` |
| `moderation_note` | text null | |
| `submitted_at` / `published_at` / `approved_at` | timestamptz null | audit-friendly transition stamps (mirror jobs) |
| `approved_by` | uuid fk users null | |
| `is_featured` / `is_sponsored` | bool default false | marketplace flags |
| `tags` | json (shared `JsonType`) default `[]` | `VARCHAR[]` in PG, JSON in SQLite tests |
| `settings` | json default `{}` | forward room (sponsor tier, booth config later) |
| `created_at` / `updated_at` | timestamptz | |
| `deleted_at` | timestamptz null | soft delete (never hard-deleted — DATA_MODEL §10 retention) |
| `version` | int default 1 | optimistic concurrency |

Indexes: `idx_events_org (org_id, status) WHERE deleted_at IS NULL`,
`idx_events_dates (starts_at, status) WHERE deleted_at IS NULL`,
`uq_events_slug (slug)`.

### 2. Registration + waitlist + capacity — free admission, atomic, no overbooking

**Decision: V1 collapses the multi-ticket model to ONE implicit free admission per
event.** Capacity lives on `events.capacity` (nullable = unlimited); a registration
references the **event**, not a ticket type. Paid tickets, ticket types, seat
selection, and promo codes are deferred (§9), and their FKs are stated so they
attach later.

**`event_registrations` states** (DATA_MODEL §10 set + `no_show`):

```
confirmed   -> holds a seat (counts against capacity); QR/check-in target
waitlisted  -> event was full at registration; FIFO queue for promotion
cancelled   -> user (or system, on event cancel) released the registration
attended    -> staff checked the user in (§3)
no_show     -> confirmed but never checked in; set by the post-event sweep
```

*(The task brief said state `registered`; we adopt DATA_MODEL §10's `confirmed`
because a waitlisted row is also "registered" — `confirmed` is unambiguous. Flagged.)*

**Who can register:** an **authenticated** principal whose persona may see the
event's visibility tier (the typical registrant is a `student`; `alumni` allowed).
Permission code `events:register`, default-granted to students/alumni. **Guests
must log in** — `GET /events/{id}` is public, but `POST /events/{id}/register`
returns `401` (→ login/register CTA), matching PRD §"Apply, …, register event …
requires login." One **active** registration per `(event, user)`.

**Capacity enforcement — atomic, no overbooking under concurrency.** The registration
service runs the count-check + insert under a **row lock on the event** (the same
`with_for_update()`-gated-on-Postgres pattern as `moderation_service._load_job`):

```
register(event_id, user):
  # one transaction
  event = SELECT * FROM events WHERE id=:id AND deleted_at IS NULL FOR UPDATE   # PG; SQLite tests rely on the service guard (single-writer)
  validate: status=published, moderation=approved, within [registration_opens_at, registration_closes_at|starts_at), visibility allows persona
  existing = active registration for (event, user)?  -> idempotent return (confirmed/waitlisted) | 409 if cancelled→re-register allowed
  if capacity IS NULL:                      -> insert status=confirmed
  else:
      confirmed_n = COUNT(*) WHERE event_id=:id AND status='confirmed'
      if confirmed_n < capacity:            -> insert status=confirmed; event.registration_count += 1
      else:                                 -> insert status=waitlisted
  bump event.version; audit; enqueue notification (confirmed | waitlisted)
```

The event row lock serializes all registrations for one event, so two concurrent
"last seat" requests cannot both confirm. The **DB safety net** is a partial unique
index `uq_event_reg_active (event_id, user_id) WHERE status <> 'cancelled'`
(PG-guarded; SQLite tests rely on the service guard) — guarantees one active
registration per user even if the lock path is bypassed, and lets a *cancelled*
user re-register (the cancelled row does not block).

**Automatic waitlist promotion — INLINE on cancel + a scheduler safety-net.**
Because V1 events are **free**, there is **no 2-hour payment hold** (PRD §6.4's
2h-confirm is a *paid-ticket* concern, deferred). On cancellation of a `confirmed`
registration, in the **same locked transaction**:

```
cancel_registration(event_id, user):
  event = SELECT ... FOR UPDATE
  reg.status = cancelled; reg.cancelled_at = now; event.registration_count -= 1; bump version; audit; notify (cancellation ack)
  if capacity IS NOT NULL and any waitlisted rows:
      head = SELECT ... WHERE event_id=:id AND status='waitlisted' ORDER BY created_at ASC LIMIT 1 FOR UPDATE SKIP LOCKED
      head.status = confirmed; event.registration_count += 1; audit; enqueue notification (promoted_from_waitlist)
```

A scheduler job `events.waitlist_backfill` (ADR-0003, 5-min) is the **idempotent
safety net**: for any published, capacitied event with `confirmed_n < capacity` and
a non-empty waitlist, promote FIFO heads until full — covering any promotion missed
by a crash mid-cancel. (Single source of truth: same promote routine, called inline
and by the sweep.) The PRD §6.4 "max 3 promotion attempts" / `tier_priority` rules
are **paid-flow concerns, deferred**; V1 promotes immediately and permanently.

**Registration deadline / closed states (coded errors, never raw):** registering
when `now ≥ registration_closes_at` (or `starts_at` if null) → `409
registration_closed`; event not `published` → `404` (not enumerable, mirrors jobs);
event `cancelled`/`completed` → `409 event_not_open`. **Waitlist position** is read
on demand: `1 + COUNT(waitlisted WHERE created_at < mine)`, surfaced as "vị trí #N".

### 3. Check-in & attendee-list PII

**Decision: V1 check-in is STAFF-MARKS-ATTENDED (no QR scanning).** QR digital
tickets + multi-entry-point scanning (PRD §14.8) are deferred (§9) — `qr_code_hash`
is **omitted from migration 0016** (it was `NOT NULL` in DATA_MODEL §10; flagged).

- **Who checks in:** a member of the **owning organizer org** holding `events:manage`
  (the organizer runs their own door) **OR** university staff with `events:moderate`.
  Endpoint marks one registration `confirmed → attended`, sets `check_in_at` +
  `check_in_by`, audits. Idempotent (re-check-in of an already-`attended` row is a
  no-op `200`). Late arrival is fine (no time gate on the manual mark in V1).
- **No-show:** the scheduler job `events.no_show_sweep` (runs with auto-complete)
  flips remaining `confirmed → no_show` once `ends_at + grace` has passed. Manual
  override stays possible while the event is live.

**Attendee-list visibility + PII rules (events are NOT recruitment-anonymous):**

- The attendee list is visible **only** to the owning org's members with
  `events:manage` and to university staff with `events:moderate`. It is **never**
  public, never shown to other registrants, and never to guests.
- **Why no anonymity here (unlike recruitment):** event registration is a *voluntary,
  contextual disclosure to the organizer the user chose to attend* — there is no
  hiring-bias surface to protect. Recruitment anonymity guards CV screening against
  bias; event check-in needs the organizer to know who is at the door. These are
  different contexts; the recruitment reveal handshake does **not** apply to events.
- **PII minimization still applies:** the attendee row exposes the registrant's
  display name + user tier badge + check-in state. **Email is shown only to the
  organizer** (for legitimate event comms), never to other roles, never in public
  responses. **Logs and audit `after` snapshots are PII-safe** — they carry
  `user_id` + `registration_id` + status, **never email or full name**
  (SECURITY_PRIVACY PII-safe-logs rule). Cross-org access to another org's event /
  attendee list → `404` (not `403`), mirroring jobs enumeration-masking.

### 4. Discovery — public `GET /events`, marketplace integration, hide-if-empty

Mirror the jobs discovery surface exactly, with events' own predicate + facade so
the rule lives in one place (the jobs anti-drift lesson in `visibility.py`):

- **`events/application/visibility.py`** — the single `apply_visible_filter`
  predicate: `deleted_at IS NULL`, `status = published`, `moderation_status =
  approved`, `published_at IS NOT NULL`, `visibility IN levels`, and **`ends_at >
  now`** (upcoming or in-progress — past events drop out of discovery, paralleling
  jobs' deadline cutoff). Reuses `lifecycle.visible_levels_for` for persona tiers.
- **`events/application/public_read.py`** — guest-tier facade returning enriched
  public summaries (batch-loaded organizer org block, `cover_image_url` only):
  `list_upcoming_summaries`, `list_sponsored_summaries`, `list_featured_summaries`,
  `count_visible_events`, `visible_event_count_subquery(org_id_col)` — the same
  function shapes `marketplace` and the org directory already consume for jobs.
- **`GET /events`** — public discovery (RBAC-aware; guests + any auth; visible only),
  cursor-paginated, filterable by `event_type` / `format` / `q` (mirror `GET /jobs`).
  **`GET /events/{id}`** — owner-full / public-visible / `404` (mirror `get_job`).
- **Marketplace overview integration (`marketplace/overview_service.get_overview`):**
  add `upcoming_events`, `sponsored_events`, `featured_events` by calling the new
  `events.public_read` facade — **only** the facade (the marketplace owns no event
  ORM, runs no migration). **Honesty:** each array is empty when nothing qualifies,
  so the homepage **hides the section** — the "coming soon" teaser is replaced by
  real events **only when present**, and naturally falls back to nothing/teaser when
  empty. Sponsored/featured come from the **real** `is_sponsored`/`is_featured`
  flags (never fabricated), exactly like `sponsored_jobs`.

### 5. Moderation — mirror jobs, with university auto-approve

Mirror `opportunities/application/moderation_service.py`:

- **`GET /admin/events`** — moderation queue (default `pending_review`),
  university-only.
- **`POST /admin/events/{id}/approve`** — `pending_review → published` + sets
  `moderation_status=approved`, `published_at`, `approved_by/at`; audits; notifies
  the organizer (outbox + in-app feed). Idempotent.
- **`POST /admin/events/{id}/reject`** — `pending_review → rejected`, coded reason
  required (`422` if blank), audits, notifies. Idempotent.
- **University-only gate is the SAME shape** as `_require_university_moderator`
  (superadmin OR member of a `university`-type org holding `events:moderate`) — a
  partner Admin's `*:*` cannot self-approve because the org-type gate is
  university-only. Permission code `events:moderate`.
- **PRD §14.9 auto-approve:** a **university-created** event (`submit` from a
  `university`-type org) transitions `draft → published` directly (auto-approved,
  live immediately); a **partner-created** event goes to `pending_review`. The
  PRD §2.10 "AI auto-approve events" toggle is **deferred** — V1 default is manual
  university review for partner events.

### 6. Notifications — identity/PII-safe, category `event`

New catalog entries (vi+en, category `event` per NOTIFICATIONS §39), each with an
outbox (email) entry and an in-app feed type, enqueued in the **same transaction**
as the domain write (no synchronous SMTP):

| trigger | recipient | template / feed key | body carries |
| --- | --- | --- | --- |
| register → confirmed | registrant | `event.registration_confirmed` | event title, start time, venue/format, "view my events" link |
| register → waitlisted | registrant | `event.registration_waitlisted` | event title, "you are #N on the waitlist" |
| promoted from waitlist | promoted user | `event.waitlist_promoted` | event title, "a seat opened — you're now registered", start time |
| reminder **T-24h** | each confirmed registrant | `event.reminder` | event title, start time, venue/online-access pointer |
| event cancelled | all confirmed + waitlisted | `event.cancelled` | event title, neutral "the organizer has cancelled this event" |

- **T-24h reminder** runs on the ADR-0003 scheduler via a new idempotent
  `events.reminder_sweep` job (mirrors `interview.reminder_sweep`): for published
  events with `starts_at` in the next 24h window, enqueue one reminder per confirmed
  registrant with a `dedupe_key = event.reminder:{event_id}:{user_id}` so a retry
  never double-sends.
- **PII / leakage safety:** bodies use **allowlisted template variables only**
  (SECURITY_PRIVACY §147) — event title, time, venue, the registrant's own name.
  For online/hybrid events the reminder carries a **pointer** ("access link will be
  available in-app"), **never the raw `online_link`** (link reveal is gated +
  deferred, §9). No other attendee's identity appears in any body. Recipient locale
  follows the user's preference (reuse `feed_service` locale resolution).

### 7. Data model + migration — `0016_events_registration_and_checkin`

**One migration `0016_events_registration_and_checkin`** (upgrade + downgrade),
two tables (Postgres runtime + SQLite tests via shared `JsonType`), ORM models in
`opportunities/domain/event_models.py`:

| table | key columns / FKs | notes |
| --- | --- | --- |
| `events` | per §1 | indexes `idx_events_org`, `idx_events_dates`, `uq_events_slug`. Soft delete. |
| `event_registrations` | `id`, `event_id → events`, `user_id → users`, `status`, `check_in_at`, `check_in_by → users null`, `cancelled_at null`, `created_at`, `version` | **`ticket_type_id` OMITTED** (no ticket types in V1); **`qr_code_hash` OMITTED** (no QR); **`payment_status` OMITTED** (all free). Partial unique `uq_event_reg_active (event_id, user_id) WHERE status <> 'cancelled'` (PG-guarded). Index `idx_event_reg_event_status (event_id, status)` for capacity counts + attendee list + FIFO waitlist. |

**Named-but-deferred tables** (FKs stated now so the later ticketing ADR is
forward-compatible, design deferred): `ticket_types(event_id, …)`,
`event_seats(event_id, ticket_type_id, …)`, `promo_codes(event_id, …)` — exactly as
DATA_MODEL §10/§26. When ticketing lands, `event_registrations` gains
`ticket_type_id` (nullable for legacy free regs) + `qr_code_hash` + `payment_status`.

**Capacity-concurrency mechanism (restated):** event-row `SELECT … FOR UPDATE`
(PG) serializes the count-check + insert; `uq_event_reg_active` partial unique index
is the duplicate safety net; `events.registration_count` is a denormalized display
mirror, while the **authoritative** capacity check is the live `COUNT(status=
'confirmed')` taken under the lock. SQLite unit tests rely on the service-layer
guard (single-writer), matching ADR-0004's stated approach.

### 8. API surface

```
Public discovery (RBAC-aware; guest + auth; visible only)
  GET  /events                         list, cursor, q/event_type/format
  GET  /events/{id}                    owner-full | public-visible | 404

Organizer management (owning org member, events:create / events:manage)
  GET    /events/mine                  caller-org events, any status
  POST   /events                       create draft
  PATCH  /events/{id}                  edit draft/rejected (version)
  POST   /events/{id}/submit           draft/rejected -> pending_review (or published if university)
  POST   /events/{id}/cancel           published -> cancelled (notifies registrants)
  DELETE /events/{id}                  soft-delete draft/rejected/cancelled/completed
  GET    /events/{id}/registrations    ATTENDEE LIST (organizer/university only; PII-min per §3)
  POST   /events/{id}/registrations/{rid}/check-in   confirmed -> attended

Student registration
  POST   /events/{id}/register         -> confirmed | waitlisted (401 guest; coded full/closed)
  DELETE /events/{id}/register         cancel my registration (inline waitlist promote)
  GET    /events/registrations/mine    "My Events" (my upcoming/past registrations + state + waitlist #)

University moderation (university-only, events:moderate)
  GET  /admin/events                   moderation queue (default pending_review)
  POST /admin/events/{id}/approve      pending_review -> published
  POST /admin/events/{id}/reject       pending_review -> rejected (coded reason)
```

- Routers are **HTTP-only**: validate → delegate to services (RBAC + audit + tenant
  isolation + transactions in the service layer) → shape the response envelope.
  Reuse `paginated`/`success`, the `GUEST`-fallback auth pattern from
  `opportunities/api/router.py`, and presenter-based projections (no raw codes; vi+en
  labels). New routers `events_router` (`/events`) + `admin_events_router`
  (`/admin/events`) registered alongside the jobs routers in the module.
- **Marketplace** surfaces `upcoming_events`/`sponsored_events`/`featured_events`
  (§4). The **student "My Events"** surface reads `GET /events/registrations/mine`.

### 9. Scope boundary & first implementation slice

**THIS ADR (ADR-0008) covers:** the `events` table + lifecycle (mirroring jobs +
event-appropriate states), **free single-capacity** registration, FIFO **waitlist**
with inline promotion + a scheduler backfill, **staff-marks-attended** check-in +
no-show sweep, public discovery + `public_read`/`visibility` facade + marketplace
integration (hide-if-empty), university **moderation** (+ university auto-approve),
the **5 notifications** (+ T-24h reminder + cancel fan-out), migration `0016`
(`events` + `event_registrations`), and the standard invariants (optimistic
`version`, illegal-transition `409`, cross-org `404`, per-write audit, PII-safe
logs, no raw codes, signed/safe media URLs).

**Explicitly DEFERRED (named so FKs/columns are stable; own later ADRs/slices):**

- **Ticketing & payment:** `ticket_types`, multiple tickets per event, paid
  admission, early-bird/promo (`promo_codes`), per-person limits, manual bank-transfer
  confirmation flow + `payment_status`, refunds (PRD §14.3/§14.6/§6.1/§6.2/§6.6,
  DATA_MODEL §26). *(V1 = free only; gateways stay later-phase per CLAUDE.md.)*
- **Seat selection:** `event_seats`, venue maps, Redis seat locks (PRD §14.4,
  BUSINESS_LOGIC §6.3, DATA_MODEL §26).
- **QR check-in:** `qr_code_hash`, digital-ticket QR, multi-entry-point scanning,
  real-time attendance count UI (PRD §14.8).
- **Online-link reveal:** encrypted `online_link`, gated time-boxed signed reveal,
  share-prevention (PRD §14.7, BUSINESS_LOGIC §6.5).
- **Career-fair sub-entities:** booths, booth QR auto-connect, sponsor tiers
  (PRD §14.9/§14.10).
- **Post-event:** certificates, recordings/materials distribution, surveys
  (PRD §14.11).
- **Paid-waitlist nuance:** 2h-confirm hold, max-3 attempts, `tier_priority`
  promotion (BUSINESS_LOGIC §6.4).
- **Calendar/ICS, recurring events, AI auto-approve toggle** (PRD §2.10).

**First implementation slice (backend-first) — for `backend-developer`:**

1. **Migration `0016`** — create `events` + `event_registrations` (+ partial unique
   active-registration index + `idx_event_reg_event_status`, PG-guarded) with upgrade
   **and** downgrade. Add ORM models `opportunities/domain/event_models.py`.
2. **Domain** — `opportunities/domain/event_lifecycle.py`: status/transition map,
   `event_type`/`format`/registration-state vocabularies, vi+en label tables,
   `EDITABLE_STATES`/`DELETABLE_STATES`, pure predicates (`can_transition`,
   `can_register(now, opens, closes, starts, status, mod)`), waitlist-position helper.
   No I/O. (`visibility` tiers reuse the shared `lifecycle.visible_levels_for`.)
3. **Services** —
   `event_service.py` (create/update/submit[+univ auto-approve]/cancel/delete/get/
   list_mine, RBAC + audit + version + slug);
   `event_moderation_service.py` (queue/approve/reject, university-only gate mirroring
   `_require_university_moderator`);
   `registration_service.py` (register/cancel with the `FOR UPDATE` capacity guard +
   inline waitlist promote, check_in, attendee-list with PII-min projection,
   my-registrations);
   `event_public_read.py` + `event_visibility.py` (discovery facade + predicate).
4. **API** — `events/api/router.py` routes per §8 (HTTP-only) + Pydantic schemas +
   presenters (vi+en labels, `cover_image_url`, never raw paths/codes).
5. **Marketplace** — extend `marketplace/overview_service.get_overview` with
   `upcoming_events`/`sponsored_events`/`featured_events` via the events facade
   (hide-if-empty); never import event ORM.
6. **Notifications** — add the 5 catalog/template entries (vi+en, category `event`,
   allowlisted variables) + in-app feed types.
7. **Scheduler** — register four idempotent ADR-0003 jobs in
   `automation/scheduler/jobs.py`, delegating to event services:
   `events.reminder_sweep` (T-24h, ~300s), `events.waitlist_backfill` (~300s),
   `events.no_show_sweep` + `events.auto_complete` (~600s, `ends_at < now`).
8. **Tests (SQLite, `tester-qa` gate):** create→submit→moderate→publish happy path;
   partner submit → `pending_review`, university submit → `published` (auto-approve);
   capacity full → waitlist; **concurrency** (two "last seat" registers — exactly one
   confirmed, no overbooking); duplicate register idempotent; cancelled→re-register
   allowed; cancel promotes FIFO waitlist head; waitlist position correct; register
   guest → `401`; register past `registration_closes_at` → `409`; cancelled/completed
   event register → `409`; cross-org event/attendee → `404`; check-in
   `confirmed→attended` (organizer + university) and unauthorized → `404`; no-show
   sweep; auto-complete sweep; reminder sweep dedupe (no double-send); event-cancel
   notifies all confirmed+waitlisted; **attendee-list PII** (email only to organizer,
   absent for others; audit/log carry no email); discovery hides past/unpublished;
   marketplace hides empty event sections; audit row per write.

**Frontend slice (follows, after the contract is green):** public `/events` list +
`/events/{id}` detail (DESIGN §6.5 event hero + format pill), register/cancel +
waitlist-position state, student "My Events", organizer create/submit/manage +
attendee-list + check-in surface, university moderation queue, and the marketplace
events strip replacing the coming-soon teaser. Honest empty/permission/`409`-full/
`409`-closed states; no `confirm()` dialogs. Mark `API wired` → `browser verified`
→ `E2E verified` distinctly.

## Consequences

- **Positive:** the marketplace becomes honest (real events replace the teaser);
  students can register/waitlist/check-in end-to-end on a small, doc-faithful slice.
  Events reuse every proven jobs invariant (lifecycle machine, university moderation
  gate, RBAC-`404` masking, optimistic `version`, audit, the
  `public_read`/`visibility` single-source facade, sponsored/featured flags, outbox +
  feed notifications) and the ADR-0003 scheduler — minimal new surface area. The
  deferred ticketing/seats/QR/payment system attaches to stable `events` /
  `event_registrations` FKs without rework.
- **Cost / limits:** one migration (`0016`). V1 is **free single-admission** — no
  paid tickets, no seats, no QR, no online-link reveal; capacity is one number on the
  event. The event-row `FOR UPDATE` serializes registrations per event (acceptable
  for V1 single-instance + single scheduler, ADR-0003's stated assumption). DATA_MODEL
  §10/§26 multi-ticket columns are intentionally not yet created.
- **Reversibility:** the module is additive within `opportunities`; dropping `0016`
  and the new routers/services removes events entirely and restores the jobs-only
  surface. Lifecycle/notification/scheduler additions are isolated to event-prefixed
  files and registry entries.

## Doc conflicts resolved (precedence: product > business > security > arch > API/data)

1. **`events.status` vocabulary.** The jobs pattern uses `active|closed|expired`;
   DATA_MODEL §10 uses `published|cancelled|completed`. **Resolved:** adopt
   DATA_MODEL §10's event-appropriate vocabulary (`draft|pending_review|published|
   cancelled|completed` + `rejected`) — events *publish*, *complete*, or *cancel*;
   they do not "close" like a job. The jobs *machinery* is mirrored, the *labels*
   diverge intentionally. No doc change needed (this ADR is the reconciliation).
2. **`event_registrations` ticketing columns.** DATA_MODEL §10 declares
   `ticket_type_id NOT NULL`, `qr_code_hash NOT NULL UNIQUE`, `payment_status` —
   all presuming the deferred ticketing/QR/payment system. **Resolved:** V1 migration
   `0016` **omits** all three (free single admission, no QR, no payment); they return
   (nullable for legacy) with the ticketing ADR. **Flag DATA_MODEL §10
   `event_registrations`** as "ticket_type_id/qr_code_hash/payment_status deferred to
   the ticketing ADR; V1 free-admission per ADR-0008."
3. **Registration state set.** DATA_MODEL §10 lists `confirmed|waitlisted|cancelled|
   attended`; the no-show requirement needs `no_show`. **Resolved:** add `no_show`.
   **Flag DATA_MODEL §10** to add `no_show` to the `event_registrations.status`
   comment.
4. **Capacity location.** DATA_MODEL §10 puts `capacity` on `ticket_types` (deferred);
   V1 has no ticket types. **Resolved:** add nullable `capacity` (+ display
   `registration_count`) directly to `events` for V1; per-ticket capacity returns with
   the ticketing ADR. **Flag DATA_MODEL §10 `events`** to note the V1 event-level
   `capacity` column.
5. **Audit/moderation/visibility columns absent from DATA_MODEL §10 `events`.**
   Just as the shipped `jobs` model added `visibility`/`submitted_at`/`approved_by/at`/
   `version` beyond its doc, `events` adds the same. **Resolved/flagged:** these are
   documented additions (this ADR + the model docstring), consistent with the jobs
   precedent — no conflict, recorded for the DATA_MODEL refresh.
