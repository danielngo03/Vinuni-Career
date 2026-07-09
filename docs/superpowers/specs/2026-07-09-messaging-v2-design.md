# Messaging V2 — Organization-as-Page, Message Requests, Shared Inbox, Realtime

Status: Design (owner-approved direction 2026-07-09)
Owner decisions this session supersede ADR-0012 where they conflict (documented in §11).
Codebase: **real running app** on `vinuni-main-submission` (NOT greenfield). Extends the
existing `backend/app/modules/messaging/` module (migration `0023_messaging_institutional`).

---

## 1. Goal

Turn the existing institutional messaging slice into a full, powerful, maintainable
messaging system that behaves like a large product:

- **Cross-persona reach with a message-request gate.** Student and partner may *initiate*
  to organizations, but a first contact is limited to **3 intro messages** and then waits
  for the recipient to **accept**. University is privileged and messages anyone instantly.
- **Organization-as-Page identity + shared team inbox.** A partner/university acts as a
  single "Page". Outsiders only ever see the org (name + logo), never which staff member
  replied. Internally, staff see each other and share one org inbox, can assign threads to
  a department/person.
- **Internal messaging.** Staff↔staff and staff↔department within the same org.
- **Realtime** (WebSocket) delivery + typing + read receipts, with polling fallback.
- **Attachments** (images + files) in messages.
- **RBAC:** messaging is a grantable capability; partner/university admin controls who may
  read/send/initiate/assign/moderate, scoped by user/role/department.

Non-negotiables preserved: student↔student is a hard, first-check block; persist-before-deliver;
PII-safe notifications/audit; recruitment blind-screening (student masked to partner until reveal)
is untouched; no provider/model internals leaked; every write audited.

---

## 2. Core domain model (the key shift)

The existing model is **user-centric** (participants are users). V2 introduces a **party**
abstraction so an organization can be a first-class conversational actor.

A **thread** has **1–2 parties**. A **party** is one of:
- **user party** — a single student/alumni user, representing themselves; or
- **org party** — a partner/university org, represented as a Page; many staff act for it,
  optionally scoped/assigned to a department.

Every **message** is still authored by a real user (`messages.sender_id`), but it is
*rendered* as the party (org name for outsiders; real name for same-side colleagues and
university moderators — see §5).

### 2.1 New / changed tables (migration `0085_messaging_v2`)

**`message_threads`** — extend existing:
- `+ thread_kind` VARCHAR(20) — `org_dm` | `org_to_org` | `internal` | `application` | `support` | `announcement`.
  (Derived, denormalized for indexing. Existing `kind` `direct|announcement` kept for back-compat;
  new `thread_kind` is the richer discriminator.)
- `+ request_state` VARCHAR(20) NOT NULL DEFAULT `'accepted'` — `pending` | `accepted` | `declined` | `blocked`.
- `+ request_message_count` INT NOT NULL DEFAULT 0 — intro messages sent while pending.
- `+ initiator_party_id` UUID NULL — FK→`message_thread_parties.id`.
- (keep `org_id`, `context_type`, `context_id`, `is_anonymous`, `status`, `subject`, `version`, soft delete)

**`message_thread_parties`** — NEW (the 1–2 sides):
- `id` UUID PK
- `thread_id` UUID FK→message_threads CASCADE, indexed
- `party_kind` VARCHAR(10) — `user` | `org`
- `user_id` UUID NULL FK→users (set when party_kind=user)
- `org_id` UUID NULL FK→organizations (set when party_kind=org)
- `identity_mode` VARCHAR(10) NOT NULL — `person` | `org` (how this party renders to the *other* side)
- `assigned_department_id` UUID NULL — org-side routing
- `assigned_user_id` UUID NULL — org-side owner/assignee
- `assignment_state` VARCHAR(12) NOT NULL DEFAULT `'unassigned'` — `unassigned` | `assigned` | `resolved`
- `last_read_at` TIMESTAMPTZ NULL — **party-level** read cursor (shared inbox); for user parties this is the user's cursor
- `muted` BOOLEAN DEFAULT false
- `created_at`
- Constraint: exactly one of user_id/org_id set (service-enforced; CHECK on PG).
- Indexes: `(thread_id)`, `(org_id, assignment_state)`, `(assigned_user_id)`, `(user_id)`.

**`message_thread_participants`** — extend existing (per-user membership, mainly for user parties
and for staff who have explicitly opened/claimed an org thread):
- `+ party_id` UUID NULL FK→message_thread_parties
- keep `last_read_at` (used for user parties; org read-state lives on the party)

> Org-side access is **computed via RBAC** (membership + `messaging` capability + department
> scope), NOT by enumerating every staff member as a participant row. Participant rows on the
> org side are created lazily when a staff member acts (claims/assigns/sends), for audit trail.

**`messages`** — extend existing:
- `+ sender_party_id` UUID NULL FK→message_thread_parties — which side sent it (fast render)
- `+ has_attachments` BOOLEAN DEFAULT false
- keep `sender_id` (real author; null=system), `body`, `reply_to_id`, `client_dedupe_key`, soft delete.

**`message_attachments`** — NEW:
- `id` UUID PK
- `message_id` UUID NULL FK→messages (null while pending pre-send), indexed
- `thread_id` UUID FK→message_threads (for access checks)
- `uploader_id` UUID FK→users
- `kind` VARCHAR(10) — `image` | `file`
- `file_name` VARCHAR(300), `content_type` VARCHAR(120), `size_bytes` BIGINT
- `storage_key` VARCHAR(500) — key in the file store (reuse documents storage adapter)
- `width` INT NULL, `height` INT NULL (images)
- `created_at`, `deleted_at`

### 2.2 Request-gate rules (pure, `domain/gate.py`)

A thread is created `pending` (gate ON) UNLESS any of:
- initiator party is a **university** org → `accepted` (privileged, instant);
- **internal** same-org thread → `accepted`;
- a prior **accepted** thread already exists between the same two parties → reuse/accepted;
- **application relationship** backs a partner↔student thread (student applied → consent) → `accepted`
  (keeps existing recruitment behavior + reveal masking).

While `pending`:
- only the **initiator** may post, capped at `messaging_request_message_limit` (default **3**);
- recipient sees an **accept / decline / block** prompt (no obligation to reply);
- exceeding the cap → `409 REQUEST_LIMIT_REACHED` (friendly vi/en, "waiting for acceptance").

Recipient actions: **accept** → `accepted` (both sides unlimited, subject to global rate limits);
**decline** → `declined` (initiator cannot send more; thread hidden from recipient inbox);
**block** → `blocked` (initiator blocked from initiating to this party again).

Hard block (unchanged, first check everywhere): **student/alumni ↔ student/alumni is NEVER allowed.**
Students cannot search for or select students. Enforced at create AND every send.

---

## 3. Permission matrix (V2)

Effective persona is institutional-first (a user who is staff is treated as staff).

| Initiator | Recipient | Allowed | Gate |
|---|---|---|---|
| university_staff (org party) | anyone | ✓ initiate | none (instant) |
| student/alumni | partner org | ✓ initiate | request-gate (3 + accept) |
| student/alumni | university org | ✓ initiate | request-gate (3 + accept) |
| student/alumni | student/alumni | ✗ NEVER | — |
| partner_member (org party) | university org | ✓ initiate | request-gate |
| partner_member (org party) | student (with active application) | ✓ initiate | none (recruitment consent) + reveal masking |
| partner_member (org party) | student (no application) | ✓ initiate | request-gate (cold) — student shown by name to org |
| partner_member (org party) | partner_member **same org** | ✓ internal | none |
| partner_member (org party) | **other** partner org | ✗ | blocked (404) — cross-partner not allowed |
| any staff | department (same org) | ✓ internal | none |

All checks are in the **service layer**, never the router/WS. Non-participant / cross-tenant /
unknown → **404** (anti-enumeration), not 403.

---

## 4. RBAC capability (new `messaging` resource)

Add to `organization/domain/catalog.py`:
- `messaging:read` — view the org shared inbox (scoped to the member's department(s) + unassigned + assigned-to-me; admins see all).
- `messaging:send` — reply/send in org threads the member can read.
- `messaging:initiate` — start new outbound org threads (as the Page).
- `messaging:assign` — assign/route/resolve threads, change assignee/department.
- `messaging:moderate` — (university) read/moderate/delete/export any thread for compliance.

Admin wildcard `*:*` grants all. **Default seeds:** partner & university admin → wildcard (already);
new orgs' default admin role keeps wildcard. Baseline non-admin members get **none** until granted
(matches owner decision). **Regression guard:** recruitment application threads remain authorized by the
recruitment relationship (existing behavior), so current recruiter→candidate messaging keeps working
even before a `messaging` grant is configured. The capability gates the NEW org-inbox / initiate /
internal / assign features.

Department scoping: a member with `messaging:read` sees threads whose org party is
assigned to one of their departments, or unassigned, or assigned to them; admins/moderators see all.

---

## 5. Identity rendering (asymmetric — owner decision)

Centralized in `application/thread_view.py` (single projection source). For a given **viewer**:

1. **University moderator / superadmin** → sees real identities everywhere.
2. Viewer is on the **same party** as the message author (colleague) → real name (internal visibility).
3. Message authored by an **org party**, viewer is an outsider → **org display name + logo** (Page).
   Never the staff member's name/email. Applies to ALL external threads (org_dm, org_to_org, support).
4. Message authored by a **student**, viewer is a **partner in a recruitment application thread**
   and `is_anonymous && not revealed` → **anonymous handle** (existing reveal handshake, unchanged).
5. Message authored by a **student initiating a general/support thread**, viewer is the org →
   **student real name** (asymmetric: student chose to reach out; org must be able to help).
6. Default → real name.

The frontend renders `counterpart_label` / `sender_label` **verbatim**; it never reconstructs names.
Notifications and audit carry only masked labels + ids (never body, never a masked student's identity).

---

## 6. Realtime (WebSocket)

Follows `.claude/rules/realtime.md`: persist-before-deliver, WS re-auth + tenant scope on connect
and per event, RBAC not bypassed, coarse/absent presence (never exposed to partners/students).

- **`application/realtime/bus.py`** — `MessageBus` interface: `publish(channel, event)`,
  `subscribe(channels) -> async iterator`. Default **in-process** asyncio implementation
  (works for single-worker local dev, no Docker/Redis). **Redis adapter** used automatically when
  `REDIS_URL`/`messaging_redis_url` is configured (multi-worker fan-out). Channels are per-user
  (`user:{id}`) and per-thread (`thread:{id}`).
- **`application/realtime/connection_manager.py`** — registry of live WS connections per user.
- **`api/ws.py`** — `GET /api/v1/messaging/ws?token=…` (token via query or `Sec-WebSocket-Protocol`).
  Authenticates, re-checks identity/tenant, subscribes the user to their authorized thread channels,
  forwards events: `message.created`, `message.deleted`, `thread.read`, `thread.updated`,
  `thread.request` (accept/decline), `typing`. Every outbound event re-checks `can_read_thread`.
- Send path: after commit, publish `message.created` to each recipient party channel + the thread
  channel. Typing is ephemeral (published, not persisted).
- **Frontend** `useMessagingSocket` hook: opens WS, on event patches TanStack Query caches
  (append message, bump unread, update thread). Polling (existing 12/30/45s) stays as fallback and
  auto-resumes on WS disconnect (graceful degradation, exponential-backoff reconnect).

Presence dots are **omitted** in V1 (rule: never to partners); typing + delivered/read only.

---

## 7. Attachments

- `POST /messaging/threads/{id}/attachments` (multipart) → membership check → type allowlist
  (images: png/jpg/webp/gif; files: pdf/doc/docx/xls/xlsx/ppt/pptx/txt/csv/zip) → size cap
  (`messaging_attachment_max_mb`, default 15) → store via the **documents storage adapter** →
  returns `{attachment_id, kind, preview_url}` (short-lived signed/gated URL). MIME sniffed, no execution.
- `sendMessage` accepts `attachment_ids: []`; on send they are bound to the message
  (`has_attachments=true`). Download/preview re-checks thread membership every time (gated endpoint
  or short-lived signed URL). Audited. Soft-deletable with the message.

---

## 8. API surface (all under `/api/v1/messaging`)

Existing (kept, extended): `GET/POST /threads`, `GET /threads/{id}`, `GET/POST /threads/{id}/messages`,
`POST /threads/{id}/read`, `POST /threads/{id}/mute`, `DELETE /threads/{id}/messages/{mid}`,
`POST /threads/{id}/report`, `GET /unread-count`.

New:
- `POST /threads/{id}/request/accept` · `/request/decline` · `/request/block`
- `POST /threads/{id}/assign` `{department_id?, assignee_id?}` · `POST /threads/{id}/resolve`
- `GET /inbox` — org shared inbox: filters `?scope=unassigned|mine|all|resolved&department_id=&q=`, cursor.
- `POST /threads/{id}/attachments` (multipart) · `GET /attachments/{id}` (gated download)
- `GET /recipients/search?q=` — recipient picker honoring the matrix (students see orgs only;
  staff see colleagues/departments + universities; NEVER returns students to a student).
- `POST /threads/{id}/typing` (or via WS) — ephemeral typing signal.
- `WS /ws` — realtime stream.

Coded errors: `STUDENT_TO_STUDENT_BLOCKED` (400), `REQUEST_LIMIT_REACHED` (409),
`REQUEST_NOT_PENDING` (409), `PERMISSION_DENIED` (403), `RESOURCE_NOT_FOUND` (404),
`THREAD_CLOSED` (409), `RATE_LIMITED` (429), `ATTACHMENT_TOO_LARGE`/`ATTACHMENT_TYPE_BLOCKED` (422).

---

## 9. Frontend

Personas: student (marketplace header), partner + university (workspace sidebar/topbar). Reuse
existing primitives (Button, Modal, Sheet, EmptyState, Skeleton, toasts, monochrome tokens).

- **Redesigned inbox** (`messaging/`): two-pane; org personas get a **shared-inbox** layout with
  a filter bar (Unassigned / Assigned to me / All / Resolved, department filter, search) and an
  **assignee/department picker** per thread.
- **Message-request UX**: pending banner for recipients (Accept / Decline / Block); for initiators an
  intro-limit indicator ("2 of 3 intro messages left — waiting for acceptance").
- **Org-Page identity**: counterpart shown as org (logo + name); staff see a "Replying as **{Org}**"
  affordance so they know they're masked; colleague names visible only within their own side.
- **New-message composer** with recipient picker per persona:
  - student → pick an **organization** (partner/university); students cannot appear/search students.
  - partner staff → internal colleague/department, a university, or an application-bound candidate.
  - university staff → anyone (ungated).
- **Attachments**: image/file picker in composer, thumbnails, upload progress, inline image render,
  file chips with download.
- **Realtime**: `useMessagingSocket` live append + typing indicator + read receipts; polling fallback.
- **Nav**: student Messages in header (exists); add partner Messages to sidebar; university has it.
  Unread badge from `/unread-count` (already wired to the bell).
- i18n: extend `messaging` namespace (`student/messaging.json` + vi), add request/inbox/attachment keys,
  keep en/vi parity (`scripts/check-message-parity.mjs`).

---

## 10. Module structure (backend, extend `messaging/`)

```
domain/
  models.py        + MessageThreadParty, MessageAttachment; extend Thread/Participant/Message
  rules.py         extend evaluate_open/evaluate_send (party + capability aware)
  gate.py          NEW — pure request-gate state machine
  parties.py       NEW — pure party/label resolution helpers
application/
  thread_service.py     extend create (build parties, gate, dedupe)
  message_service.py    extend send (party, request-limit, attachments, realtime publish)
  request_service.py    NEW — accept/decline/block
  assignment_service.py NEW — assign/resolve, department routing
  inbox_service.py      NEW — org shared inbox listing (RBAC + dept scope + filters)
  attachment_service.py NEW — upload/list/gated download
  recipient_service.py  NEW — matrix-honoring recipient search
  capability.py         NEW — messaging RBAC checks over principal.permissions
  thread_view.py        extend identity rendering (asymmetric org-page)
  realtime/
    bus.py              NEW — MessageBus (in-proc + redis)
    connection_manager.py NEW
    ws_auth.py          NEW
api/
  router.py        extend + new REST endpoints
  ws.py            NEW — WebSocket endpoint
  schemas.py, presenters.py  extend
```

Migration `0085_messaging_v2` (down_revision `0084_ai_provider_health_fields`).
Config knobs in `app/core/config.py`: `messaging_request_message_limit=3`,
`messaging_attachment_max_mb=15`, `messaging_redis_url` (optional), keep existing rate-limit knobs.

Cross-module boundaries respected: use read-model facades (users/org/recruitment), no cross-module ORM
imports; notifications via `feed_service`/`dispatch_service` only; audit via `write_audit`.

---

## 11. Divergences from ADR-0012 (owner decisions 2026-07-09 — update ADR)

1. Student **may initiate** to partner/university (was reply-only). Governed by the request-gate.
2. Student→university is **gated** (3 + accept), was unlimited. (University→student ungated.)
3. **Organization-as-Page + shared team inbox** across all external threads (was: only student masked).
4. **Messaging is a grantable RBAC capability**, department-scoped (was: derived only from relationship).
5. **Realtime (WebSocket) + attachments** are in scope now (were deferred).

Action: amend `docs/adr/ADR-0012-messaging-institutional.md` (or add ADR-0013) + update
`docs/API_CONTRACTS.md §Messaging`, `docs/BUSINESS_LOGIC.md §14`, `docs/DATA_MODEL.md`,
`docs/NOTIFICATIONS_COMMUNICATIONS_SPEC.md` to match. Preserve: student↔student hard block,
persist-before-deliver, PII-safe notif/audit, recruitment reveal masking, hidden AI internals.

---

## 12. Build phases (single worktree → one draft PR)

- **P0** base-fix sync (done in worktree setup).
- **P1 backend core**: migration + models + gate + parties + capability + services (thread/request/
  message/inbox/assignment/recipient) + thread_view + REST router + schemas/presenters. Verify import + tests.
- **P2 realtime**: bus + connection_manager + ws endpoint + publish hooks. Verify.
- **P3 attachments**: table + service + endpoints (reuse documents storage). Verify.
- **P4 frontend**: API client, inbox redesign, request UX, org-page identity, composer + attachments,
  recipient picker, nav, i18n. tsc + lint + parity.
- **P5 realtime FE**: `useMessagingSocket`, typing, live updates, fallback.
- **P6 tests + docs + polish**: backend unit/integration (gate, matrix, masking, capability, attachments),
  RBAC/security tests, update ADR/docs, browser QA. Full gates.

## 13. Test focus (security-critical)

student↔student blocked (create+send); request-gate limit + accept/decline/block transitions;
university privilege bypass; org-page masking (outsider never sees staff name; colleague does;
moderator does); recruitment reveal still masks student; capability + department scoping (member
without grant blocked; admin sees all; dept member sees only their dept's threads); attachment
type/size limits + download auth; cross-tenant/non-participant → 404; persist-before-deliver;
PII-safe notifications/audit.

## 14. Phase 6 — post-launch hardening (2026-07-09)

Follow-up pass after a full-surface audit. All backend-gated + tested; frontend
tsc/eslint green.

- **Request-lifecycle notification.** Accepting a message request now notifies the
  INITIATOR (in-app feed + preference-gated email) via `message_service.notify_request_accepted`,
  reusing the notifications module. PII-safe: a MASKED counterpart label as the
  initiator perceives it (org Page name for a student initiator; the now-revealed
  student for a partner initiator, since accept lifts the cold mask), never the body.
  Decline/block stay silent by design (no rejection/harassment signal). New catalog
  type `message.request_accepted` (vi/en).
- **Department scope is ACCESS CONTROL, not just a list filter** (security fix). The
  shared-inbox department scoping was enforced only in `inbox_service.list_org_inbox`.
  Added `capability.member_can_access_org_party` (admins/`assign` + superadmin see all;
  a member sees unassigned + assigned-to-me + my-department threads) and gate every
  non-participant org-access path with it: `thread_service._load_readable` (read),
  `attachment_service._can_read_thread`/`_send_party` (download/upload),
  `message_service.send_message` org lazy-participant branch (reply), and
  `request_service._actor_on_party` (accept/decline/block). Participant rows still imply
  legitimate prior engagement (unaffected). A deep link can no longer cross departments.
- **Org shared-inbox unread now drives the header badge.** `thread_view._org_inbox_unread`
  counts team unread (shared party cursor, department-scoped) for accessible org-Page
  threads the caller is NOT yet a participant of — so a brand-new inbound lead raises the
  whole team's badge even with no participant rows, and recruitment/application threads
  (which have participant rows) keep the personal-cursor accounting (no double count).
  `inbox_service.mark_org_read` also advances the caller's participant cursor so reading
  in the inbox clears the badge in lockstep.
- **Assignment notification.** Routing a thread to a specific member alerts that member
  (in-app, deep link, no body/counterpart identity) via a new `messaging.thread_assigned`
  catalog type; self-assign is silent.
- **Notification rendering.** Aligned the frontend NotifType union + icon/category maps to
  the real backend keys (`message.received`, `message.request_accepted`, `message.flagged`,
  `messaging.thread_assigned`) — previously keyed off a non-existent `messaging.message.received`,
  so all messaging notifications fell back to the neutral bell.
- **Dark mode.** Messaging surfaces converted hardcoded light-only backgrounds to the
  theme surface tokens (`--surface-card`/`--bg-subtle`) so the inbox, thread panel, and
  composer render correctly under `[data-theme="dark"]`; ink-bubble overlays and semantic
  green pills left intact.

Deferred (lower value / product-decision-heavy): dedicated "Requests" inbox scope +
hide declined from recipient; read receipts ("seen") + `thread.read`/`message.deleted`
realtime signals; unblock / block-list management; thread-fetch pagination on the client.

## 15. Rigorous verification pass (2026-07-09)

Full-suite tests + three adversarial reviews (correctness/edge-cases, security/RBAC/PII,
adjacent-flow/UX). Evidence: full backend suite = 12 pre-existing failures only (AI
billing/eval/jd/governance + the documented `documents`/`platform_admin` boundary),
ZERO messaging/notification regressions; messaging module boundary-clean; frontend
`tsc` + `eslint` + `next build` + i18n parity (51 files) green; migration `0085`
emits valid Postgres DDL. Confirmed strong defenses: student↔student block (create +
every send + recipient search), org-Page individual identity never leaks (incl. over
WS — signals carry only `{type, thread_id}`), cross-tenant 404 (no 403/404 seam),
attachment download hardening, notification/audit PII safety.

**Fixed (real defects the reviews surfaced):**
- Cold-requested student was UNMASKED to the partner on decline/block (mask now lifts
  only on accept). Partner could co-locate two students who'd read each other's names
  (rejected). Application/recruitment threads inflated every non-owner teammate's
  shared-inbox badge + list (excluded). Person-only assignment (no dept) was readable
  by the whole org (confined). Idempotent intro-retry at the cap wrongly 409'd (dedupe
  now precedes the gate). `respond` leaked 409-vs-404 to non-recipients (authorize
  first). Soft-deleted message attachments + unbound draft attachments were downloadable
  (gated). Org-Page initiate/send were persona-gated not capability-gated (now require
  `messaging:initiate`/`send`; application threads stay relationship-authorized). A
  teammate's outgoing Page reply inflated colleagues' unread + notified them (party-aware
  now). Messaging emails ignored the "message" email-mute preference (now gated). The
  `message.request_accepted` email had no template (added).

**Deferred with rationale (owner decisions / follow-ups, documented not silently
dropped):**
- **University-staff moderation is persona-gated** (`is_university_moderator` = any
  `university_staff`), not the grantable `messaging:moderate` — a scoped staffer is a
  global moderator who sees unmasked identities across all partner orgs. Pre-existing
  ADR-0012 design (university owns the platform); switching to capability-gated
  moderation is an owner decision + a larger change.
- **Department scope is bypassed by a pre-existing participant row** — a staffer who
  engaged a thread while it was unassigned keeps access after it's reassigned to another
  department. Genuine trade-off (cutting off an active handler mid-conversation is
  disruptive); owner decision. Person/dept assignment scoping IS now enforced for
  non-participants.
- **Concurrent-create TOCTOU** could produce duplicate pending org-Page threads (no
  backing unique index for inquiry/org kinds). Needs a unique index/advisory lock;
  deferred while this branch's migration numbering is rebased onto the live head.
- **WS `org:{id}` channel is not department-scoped** and grants aren't re-checked
  mid-connection — metadata/timing only (no body; HTTP re-checks on refetch). Low.
- `message.flagged` moderation alert rides the mutable "message" category (a muted
  moderator misses reports — consider a mandatory compliance category). `declined`
  threads still show in the recipient's org inbox. `validate_attachment_ids` is dead
  (the schema `max_length` already caps count). Frontend LOW polish: bell focus ring,
  silent deep-link-404, org request-bar flash before `detail` loads, no explicit
  "reconnecting" indicator.

**Deploy caveat (important):** the shared dev DB `vinuni_career` is at alembic head
`0089` (other parallel worktrees), while this branch's `0085_messaging_v2` branches from
`0084`. Before deploy, rebase this migration onto the real target head (down_revision →
current head) so it does not create a second Alembic head. A from-scratch DB is also
blocked by a PRE-EXISTING seed bug in `0005_documents.py` (`KeyError: 'is_premium'`),
unrelated to messaging.
