# ADR-0012: Messaging — Institutional In-App Threads (Phase 2 Foundation)

> **PARTIALLY SUPERSEDED (owner decision 2026-07-10):** the thread
> `is_anonymous` denormalization and the "anonymous handle until the reveal
> handshake" projection (`§2 Anonymity handling`) are **retired**. Applicants are
> always identified, so a partner↔student application thread shows the identified
> student (CV access still gated by `candidate_access` RBAC). All other messaging
> invariants (persist-before-deliver, permission matrix, PII-safe
> notifications/audit) stand. Needs a formal amendment.

**Status:** Accepted (Proposed for implementation in the next backend slice)
**Date:** 2026-06-28
**Owner:** system-architect
**Related:** `CLAUDE.md` (naming default: module `messaging`, "in-app institutional
messages; never student-to-student"), `docs/PRODUCT_REQUIREMENTS.md` M25 (In-app
Institutional Messaging + the permission matrix) and the "Student → Student
messaging — KHÔNG BAO GIỜ" exclusion, `docs/BUSINESS_LOGIC.md` §14 (who-can-message
matrix, anti-spam, retention/deletion, broadcast), `.claude/rules/realtime.md`
(Non-Negotiables: no student↔student; partner→student needs recruitment context or
permitted outreach + service-layer rate limits; persist-before-deliver; WS re-checks
identity+tenant; partners never see raw online status; real-time never bypasses RBAC;
offline/retry/stale recovery; `/ws/` namespace; Redis fan-out *after* persistence;
reconnect backoff), `docs/ARCHITECTURE.md` §"WebSocket & Real-time Architecture"
(Redis pub/sub fan-out, message persistence, presence) + ADR-0003 scheduler,
`docs/API_CONTRACTS.md` §Messaging (endpoint/error/event contracts),
`docs/SECURITY_PRIVACY.md` (anonymity/reveal, PII-safe logs, no sensitive content in
email/push), `docs/NOTIFICATIONS_COMMUNICATIONS_SPEC.md` (outbox + in-app feed +
preferences). Builds directly on the **shipped** notifications module
(`notifications/application/{dispatch_service.enqueue_notification,
feed_service.create_in_app,message_catalog}.py` — in-app feed + outbox + preference
gating + dedupe), the **shipped** recruitment module
(`recruitment/domain/{models.Application,lifecycle.ACTIVE_STATUSES}`,
`application/{access,reveal_service}.py`, `application_reveal_requests`,
`Application.is_anonymous` + `reveal_approved_at`), the org/membership RBAC
(`shared/permissions.Principal{user_id,persona,org_id}`,
`auth/domain/personas.py` = `student|alumni|partner_member|university_staff|guest`),
the httpOnly-cookie/JWT auth principal, and the **ADR-0003** asyncio scheduler
(`automation/scheduler/jobs.py`).

## Context

Messaging **does not exist as a backend today.** It is the next roadmap slice. The
load-bearing constraint from CLAUDE.md is exact: **"Use module `messaging` for in-app
institutional messages; never student-to-student."** Messaging is a *governed
institutional channel* (university↔student, university↔partner, partner↔candidate),
**not** a peer social inbox.

The PRD M25 + DATA_MODEL/ARCHITECTURE describe a **large** end-state: real-time
WebSocket delivery, Redis pub/sub fan-out, presence, read receipts (sent/delivered/
read ticks), reactions, pin, in-conversation search, file attachments, group threads,
and a segmented university **broadcast** builder with CSV import + >50-recipient
approval. Shipping all of that now is a brittle mega-slice that also pulls in WS
infra that is **not yet built**. This ADR designs the **foundational core only** — the
permission matrix + persisted threads/messages + REST API + polling + notification
integration + anonymity-safe partner↔candidate messaging — on stable tables that the
deferred WS/presence/broadcast/attachment layers attach to without rework.

Constraints that bound the decision:

- **CLAUDE.md / realtime rules:** never student↔student; partner→student needs
  recruitment context (or permitted outreach) + service-layer rate limits; content
  **persisted before any delivery**; RBAC enforced in the service layer (not the
  router/WS); partners never see raw online status; local-first, lightweight, small
  reversible first slice; no business logic in routers; every write audited; no raw
  enum codes / no AI internals to users.
- **No WS infra is shipped.** ARCHITECTURE §WebSocket describes the *eventual*
  `/ws/` + Redis pub/sub design, but `ConnectionManager`, the per-worker subscriber,
  and the presence zset do not exist. The notification bell already ships a
  **polling** unread pattern (`GET /notifications/unread-count`) that messaging can
  mirror with zero new infra.
- **Recruitment anonymity is already enforced** on every partner projection
  (`is_anonymous` + the reveal handshake via `application_reveal_requests` /
  `reveal_approved_at`, TTL 72h). Messaging must **reuse** that handshake as the
  *only* identity path — it must never become a side-channel that leaks a student's
  name/email before reveal.
- **The notification outbox + in-app feed is the shipped delivery seam** for
  cross-surface alerts; a new message must notify *through it* (preference-gated,
  PII-safe), not invent a parallel dispatcher.

## Decision

### 1. Permission matrix — the core (enforced at THREE service-layer checkpoints)

**Decision: V1 binds every partner↔student thread to a recruitment relationship
(an application to a job owned by the partner's org).** This adopts the *stricter*
PRD M25 ("Partner → Ứng viên **trong context tuyển dụng**") and defers
BUSINESS_LOGIC §14.1's 3/day **cold-outreach to a non-applicant** until passive
search ships (a partner cannot even discover an arbitrary student in V1 — see Doc
conflicts §3). Personas are the shipped `auth/domain/personas.py` set.

| Sender | Recipient | Allowed? | Condition / kind |
| --- | --- | --- | --- |
| `university_staff` | any user (`student`/`alumni`/`partner_member`/`university_staff`) | ✓ | direct; may **initiate**. Also the only announcement author. |
| `partner_member` | `student`/`alumni` | ✓ | **only** if an `applications` row exists where `application.org_id == sender.org_id` AND `application.applicant_id == recipient`. Thread is **bound** to that `application_id`. Partner **initiates**; anonymity-masked until reveal (§2). |
| `partner_member` | `partner_member` **same org** | ✓ | team direct; `context_type='team'`, `org_id == sender.org_id`. |
| `partner_member` | `partner_member` **other org** | ✗ | cross-org partner↔partner blocked (404 on the thread). |
| `student`/`alumni` | `university_staff` | ✓ | support/inquiry; may **initiate** a `context_type='support'` thread. |
| `student`/`alumni` | `partner_member` | ✓ **reply only** | may post into an existing partner-initiated application thread; **cannot initiate** a new partner thread (`can_reply=true` participant, no create permission). |
| `student`/`alumni` | `student`/`alumni` | ✗ **NEVER** | hard block, first check, no condition can override. |
| `system` (announcement) | many recipients | ✓ | one-way; `kind='announcement'`, author = `university_staff`; recipients `can_reply=false`. |

**Three enforcement points — all in the application/service layer, never the router/WS:**

1. **On thread create** — `can_open_thread(principal, kind, context_type,
   context_id, recipient_ids)`: resolves personas + the recruitment relationship +
   org scope; the **first rule is the student↔student hard block**; partner→student
   requires the bound application to exist; student→partner create is refused.
2. **On every message send** — `can_send_in_thread(principal, thread)`
   **re-checked on each POST** (not cached at create): caller is an active
   participant with `can_reply=true` (or thread author), the thread is not
   `closed`/`archived`/deleted, **and** the relationship still authorizes it
   (e.g. partner sending into an application thread whose application was purged →
   blocked). This is the realtime-rule "permission enforced on every send."
3. **On read / subscribe** — `can_read_thread(principal, thread)`: caller is a
   participant (or `university_staff` moderator). The same predicate gates the
   future WS subscribe (§3) so real-time can never bypass RBAC.

**Rate limits (service layer, anti-spam):**

- **Global per-sender ceiling:** `messaging_max_messages_per_sender_per_day`
  (config, default 200) and `messaging_max_threads_per_sender_per_day` (default 30),
  counted from `messages`/`message_threads` (`sender_id`/`created_by`, `created_at >=
  start_of_day_utc`). No new table.
- **Inactive-application taper:** when the bound application is **terminal/inactive**
  (`status NOT IN recruitment.ACTIVE_STATUSES` = not `submitted`/`under_review`), a
  partner is capped at **3 messages/day into that thread** (the BUSINESS_LOGIC §14.1
  "max 3/day" intent, applied to a stale-but-existing relationship). Within an active
  application: unlimited (subject to the global ceiling).
- Exceeding a cap → coded `429 message_rate_limited` with a friendly vi/en message +
  `reset_at` (next UTC midnight), never a raw stack/limit internal.

### 2. Data model — persist-before-deliver, anonymity-safe

Three tables (ORM in `messaging/domain/models.py`; Postgres runtime + SQLite tests
via the shared `JsonType`). **No PII is stored on the thread/message rows beyond
`user_id` references** — identity rendering is a *projection-time* decision.

**`message_threads`**

| column | type | note |
| --- | --- | --- |
| `id` | uuid pk | |
| `kind` | varchar(20) | `direct` \| `announcement` |
| `context_type` | varchar(20) null | `application` \| `support` \| `team` \| null (announcement) |
| `context_id` | uuid null | e.g. `application_id` for `application` threads (FK-by-convention to `applications.id`; not a hard cross-module FK — referenced via id, no implementation import) |
| `org_id` | uuid fk organizations, indexed | tenant scope: partner org for `application`/`team`; university org for `support`/`announcement`. Cross-tenant isolation key. |
| `subject` | varchar(300) null | announcement/support title; null for partner↔student direct |
| `is_anonymous` | bool default false | **denormalized from the bound application at create**; drives partner-side identity masking (§projection) |
| `created_by` | uuid fk users | author/initiator |
| `last_message_at` | timestamptz null | sort key + unread basis; bumped on every send |
| `status` | varchar(20) default `active` | `active` \| `archived` \| `closed` |
| `created_at` / `updated_at` | timestamptz | |
| `deleted_at` | timestamptz null | soft delete (retention §BUSINESS_LOGIC 14.3: 30d then purge — purge sweep deferred) |
| `version` | int default 1 | optimistic concurrency |

Indexes: `idx_threads_org (org_id, status) WHERE deleted_at IS NULL`,
`idx_threads_context (context_type, context_id)`,
`idx_threads_last_msg (last_message_at DESC)`.

**`message_thread_participants`** (PK `(thread_id, user_id)`)

| column | type | note |
| --- | --- | --- |
| `thread_id` | uuid fk message_threads, indexed | |
| `user_id` | uuid fk users, indexed | participant (the delivery target — by id, even for anonymous threads) |
| `role_in_thread` | varchar(20) default `member` | `owner` \| `member` |
| `can_reply` | bool default true | `false` for announcement recipients |
| `last_read_at` | timestamptz null | read-state; **unread = COUNT(messages WHERE created_at > last_read_at AND sender_id <> user_id AND deleted_at IS NULL)** |
| `muted` | bool default false | student mute/"block" (§5); suppresses notifications |
| `joined_at` | timestamptz | |
| `removed_at` | timestamptz null | left/removed (soft) |

Index: `idx_participants_user (user_id) WHERE removed_at IS NULL` — backs `GET
/messaging/threads` (my threads) + unread fan-in.

**`messages`**

| column | type | note |
| --- | --- | --- |
| `id` | uuid pk | |
| `thread_id` | uuid fk message_threads, indexed | |
| `sender_id` | uuid fk users **null** | null = system message |
| `body` | text | markdown-lite (sanitized on render; no raw HTML) |
| `is_system` | bool default false | system/announcement-generated; **cannot be deleted** (§5) |
| `reply_to_id` | uuid fk messages null | thread-lite reply (no nesting); reactions/pin deferred |
| `client_dedupe_key` | varchar(120) null | idempotent send (retry-safe); unique per `(thread_id, sender_id, client_dedupe_key)` |
| `created_at` | timestamptz | |
| `edited_at` | timestamptz null | edit deferred; column reserved |
| `deleted_at` | timestamptz null | soft delete → rendered as "Tin nhắn đã bị xóa" |

Index: `idx_messages_thread (thread_id, created_at)`; unique
`uq_message_dedupe (thread_id, sender_id, client_dedupe_key) WHERE client_dedupe_key
IS NOT NULL` (PG-guarded; SQLite tests rely on the service guard).

**Persist-before-deliver (non-negotiable, honored by construction):** `POST
.../messages` runs **one transaction** — insert `messages` row → bump
`thread.last_message_at` + `version` → write audit → `feed_service.create_in_app(...)`
+ preference-gated `dispatch_service.enqueue_notification(...)` (outbox) for each
*other* participant → **commit** → return. **No delivery path exists before the
commit.** Polling (§3) reads only committed rows; the future WS publish (§3) fires
*after* commit.

**Anonymity handling (partner ↔ anonymous applicant) — the reveal handshake is the
ONLY identity path:**

- The thread stores `user_id`s (delivery needs them) **but never the student's name/
  email**. `message_threads.is_anonymous` is denormalized from the bound application
  at create.
- **Projection-time masking** (in `messaging/application/thread_view.py`, the single
  source): when the viewer is the **partner side** AND the bound application is
  `is_anonymous` AND reveal is **not** accepted (`application.reveal_approved_at IS
  NULL`), the student participant renders as an **anonymous handle** derived from the
  application (e.g. `"Ứng viên ẩn danh #<short-app-code>"`) — never name, never email,
  never CV linkage. The **student** always sees the partner's org name (org identity
  is not protected). University moderators see real identities.
- A partner **cannot create** an anonymous-applicant thread that bypasses reveal —
  messaging routes through the *existing* application relationship; sending PII-bearing
  content is the partner's own text (their risk), and the *system* never echoes
  student PII back to the partner.
- **On reveal accepted** (the shipped `reveal_service` sets `reveal_approved_at`), the
  same projection flips to the real display name on next read — no separate messaging
  reveal, no copy of identity into messaging tables.

### 3. Delivery architecture — V1 = REST + client polling (WS deferred to a follow-up ADR)

**Decision: V1 ships REST send/list + client polling for unread, mirroring the
shipped notification-bell polling. WebSocket `/ws/` + Redis pub/sub fan-out is a
documented follow-up ADR, NOT built in this slice.**

**Rationale (explicit):**

- **No WS infra is shipped** (`ConnectionManager`, per-worker Redis subscriber,
  presence zset are all absent). Institutional messaging is **low-volume and
  asynchronous** (university notices, recruiter↔candidate exchanges) — sub-second
  push is not a product requirement; "new message within a polling interval + a
  notification-bell badge" is sufficient and honest.
- **Persist-before-deliver is trivially satisfied:** a REST POST *is* the persist; a
  poll is a read of committed rows. There is no pre-persistence delivery path to get
  wrong.
- **Zero new infra, reuses a proven pattern:** the notification bell already polls
  `GET /notifications/unread-count`; messaging adds `GET /messaging/unread-count` on
  the same cadence. Local-first, single-instance (ADR-0003's stated assumption).
- **Forward-compatible:** WS attaches later to the *same* persisted tables and the
  *same* service-layer permission predicates (`can_read_thread`/`can_send_in_thread`)
  with no schema change.

**Polling contract:** the inbox foreground-polls `GET /messaging/threads` (cursor,
sorted `last_message_at DESC`, with per-thread unread); the global badge polls `GET
/messaging/unread-count` (sum of unread across my non-muted threads) at the
notification-bell cadence; an open thread re-fetches `GET .../messages?after=<cursor>`.
**Recovery UX (realtime rule):** offline → "Mất kết nối, đang thử lại"; send failure →
the optimistic row stays `pending` with a retry affordance (idempotent re-POST via
`client_dedupe_key`); stale → "Tải lại để xem tin mới."

**Deferred WS path (follow-up ADR, contract pre-committed so it is non-breaking):**
namespace `/ws/` (per ARCHITECTURE), **auth re-check on connect** (JWT/cookie →
re-resolve `Principal`, re-verify identity + tenant), subscribe gated by
`can_read_thread` (RBAC not bypassed). Order is **persist → commit → publish** to
Redis `ws:user:{recipient_id}` (the ARCHITECTURE fan-out), **never publish before
commit**. Reconnect = exponential backoff with capped retries; on reconnect the
client re-fetches missed messages by cursor (WS is an accelerator, the DB is truth).
**Presence is OMITTED in V1** and, when it lands, is **coarse activity buckets only
and never exposed to partners** (realtime non-negotiable) — partners never see raw
online status.

### 4. Notifications + presence — through the shipped feed/outbox, PII-safe

A new message creates a notification **in the same transaction as the message
write**, via the shipped seam — no parallel dispatcher:

- **In-app feed:** `feed_service.create_in_app(recipient_id=<other participant>,
  notif_type='message.received', action_url='/messages/{thread_id}', sender_id=<masked
  or real per §2>, variables={...})` for each other non-muted participant. The
  feed_service **dedupe (recipient + notif_type + action_url)** naturally **coalesces
  a burst into one unread feed row per thread** until read — no spam.
- **Email (optional, preference-gated):** `dispatch_service.enqueue_notification(
  channel='email', template_key='message.received', dedupe_key='message.received:
  {thread_id}:{recipient_id}', ...)` — drained by the ADR-0003 `outbox.drain` worker,
  honoring the preference center + mandatory-category rules. Push deferred.
- **Category `message`** (new, optional, default-on; not mandatory). Preference center
  gains a Messaging category.
- **PII / leakage safety (SECURITY_PRIVACY):** the notification carries a **sender
  label** (masked to the anonymous handle when §2 applies) + a neutral "Bạn có tin
  nhắn mới" + the thread deep link — **never the message body** (avoids leaking PII/
  content into email subjects, digests, or lock screens). The notification **to the
  partner** about an anonymous applicant's reply stays anonymous; the notification
  **to the student** names the partner org (allowed). Allowlisted template variables
  only.

**Presence:** none in V1 (no online status surfaced anywhere); the partner-never-sees-
raw-status rule is satisfied by omission and pre-committed for the WS ADR (coarse
buckets, never to partners).

### 5. RBAC + audit + anti-spam + cross-tenant isolation

- **RBAC:** all three checkpoints (§1) in the service layer; routers are HTTP-only.
  University moderators (`university_staff` in a `university`-type org, or superadmin)
  may read/moderate any thread for compliance; partners and students see only threads
  where they are an active participant.
- **Audit:** every **write** audited — `messaging.thread.create`, `messaging.message.
  send`, `messaging.message.delete`, `messaging.thread.archive`, `messaging.report`.
  Audit `after` snapshots are **PII-safe** — `thread_id`/`message_id`/`sender_id`/
  `recipient_id` + status, **never body text, name, or email** (SECURITY_PRIVACY
  PII-safe-logs). Reads are not audited.
- **Deletion (BUSINESS_LOGIC §14.3):** sender soft-deletes **own** message within
  **10 minutes** → body renders "Tin nhắn đã bị xóa"; `university_staff` may delete
  any message (moderation); **partner cannot delete** a message sent to a student
  (audit integrity); **system messages cannot be deleted**. Enforced in the service.
- **Report / block (V1 minimal, named):** a student may **mute** a thread
  (`participants.muted=true` — suppresses notifications, stops the partner-side cap
  from being refreshed) and **report** it via `POST /messaging/threads/{id}/report`,
  which writes an audit `messaging.report` row + enqueues a `message.flagged`
  notification to `university_staff` (the "block sender → reported to university admin"
  rule). A dedicated `message_reports` table + full moderation queue/export is
  **deferred** (§8) — V1 = mute + audit-flag + notify.
- **Cross-tenant isolation:** `message_threads.org_id` scopes every query; a caller
  outside the thread (wrong org, non-participant) gets **404** (enumeration-masking,
  mirroring jobs/recruitment), never 403. Partner↔partner across orgs is blocked at
  create.

### 6. Data model + migration `0023_messaging_institutional`

**One migration `0023_messaging_institutional`** (upgrade **and** downgrade),
`down_revision = "0022_ai_settings"`, three tables per §2 with the stated indexes
(partial/PG-guarded; SQLite tests rely on the service guard). ORM models in
`messaging/domain/models.py`. **No scheduler job is required for V1** (no
WS/presence, no digest-specific sweep — message emails ride the existing
`outbox.drain`; the 30-day soft-deleted-thread purge sweep is **deferred** with
retention). **Notifications integration seam:** add a `message.received` +
`message.flagged` entry to `notifications/application/message_catalog.py` (in-app,
vi+en) and `template_seed.py` (email, vi+en, allowlisted variables, category
`message`); messaging calls **only** `feed_service.create_in_app` /
`dispatch_service.enqueue_notification` (no cross-module ORM import).

### 7. API surface

All routers **HTTP-only** (validate → delegate to services for RBAC + rate limit +
audit + tenant isolation + transactions → shape the envelope). Public paths under
`/api/v1/messaging` (CLAUDE.md naming default; `/conversations` in API_CONTRACTS is
flagged stale — Doc conflicts §1). Presenters carry vi+en labels, the **masked or
real** identity per §2, never raw codes/paths/AI internals.

```
GET    /messaging/threads                 my threads (participant), cursor, sort last_message_at DESC,
                                          per-thread unread + masked counterpart label
POST   /messaging/threads                 create — permission-gated (§1); body: {kind, context_type,
                                          context_id, recipient_ids[], subject?, first_message?}.
                                          partner↔student REQUIRES context_type='application' + context_id.
GET    /messaging/threads/{id}            thread detail (participant/moderator only); 404 if not
GET    /messaging/threads/{id}/messages   messages, cursor (?after=); participant/moderator only
POST   /messaging/threads/{id}/messages   send — RE-CHECK permission (§1.2) + rate limit (§1) + persist
                                          + notify (§4); body {body, reply_to_id?, client_dedupe_key?}
POST   /messaging/threads/{id}/read       set my last_read_at = now (clears unread)
DELETE /messaging/threads/{id}/messages/{mid}  soft-delete own ≤10min | university any | system never
POST   /messaging/threads/{id}/report     report → audit + notify university (§5)
GET    /messaging/unread-count            badge sum across my non-muted threads (polling, §3)
```

**Coded errors (never raw):** `403/404` non-participant/cross-tenant (404-masked),
`409 thread_closed`, `429 message_rate_limited` (+`reset_at`), `422` blank body /
missing `context_id` for partner↔student, `400 student_to_student_blocked`
(friendly: "Không thể nhắn tin trực tiếp giữa sinh viên").

**Per-persona rendering (anonymity preserved):**

- **Student/alumni:** an institutional inbox (university notices, application threads
  with partner orgs named, reply-only into partner threads, initiate support to
  university). Slide-in panel per DESIGN/PRD M25; mute/report controls.
- **Partner:** application-bound candidate threads; counterpart shown as the
  **anonymous handle until reveal** (§2), real name after; team threads same-org;
  no presence, no online status.
- **University:** initiate to anyone, author announcements, moderation read of any
  thread, handle reports.

### 8. Scope boundary & first implementation slice

**THIS ADR (ADR-0012) covers:** the permission matrix (§1, three checkpoints +
rate limits + the student↔student hard block), `message_threads` /
`message_thread_participants` / `messages` (§2, persist-before-deliver, anonymity
masking via the reveal handshake), **REST API + client polling** delivery (§3, no
WS), notification integration through the shipped feed/outbox (§4, PII-safe,
preference-gated), RBAC + audit + 10-min/own + university-moderation deletion +
minimal mute/report (§5), migration `0023` (§6), and the standard invariants
(optimistic `version`, illegal-state `409`, cross-tenant `404`, per-write PII-safe
audit, no raw codes, idempotent send).

**Explicitly DEFERRED (named so the tables/contract stay forward-compatible; own
later ADRs/slices):**

- **WebSocket `/ws/` + Redis pub/sub fan-out + reconnect/backoff** (follow-up ADR —
  contract pre-committed in §3, attaches to the same tables/predicates).
- **Presence / coarse activity buckets** (with the WS ADR; never to partners).
- **Read receipts** beyond `last_read_at` (delivered/read ✓✓ ticks), **typing
  indicators**, **emoji reactions**, **pin**, **in-conversation search**.
- **File/voice attachments** (PRD M25; `messages.body`-only in V1).
- **Group threads** beyond one-way university **announcements**; the **segmented
  broadcast builder** (segments/CSV import/>50-recipient university approval,
  BUSINESS_LOGIC §14.4) — V1 ships university **direct** + a basic **announcement**
  thread only.
- **Cold-outreach 3/day to non-applicants** (BUSINESS_LOGIC §14.1) — passive-search-
  dependent; the rate-limit infra is in place for when it lands (Doc conflicts §3).
- **Message edit**, **dedicated `message_reports` table + moderation queue/export**,
  **30-day soft-delete purge sweep** (retention).

**First implementation slice (backend-first) — for `backend-developer`:**

1. **Migration `0023_messaging_institutional`** — `message_threads` +
   `message_thread_participants` + `messages` with the §2 indexes + partial uniques
   (PG-guarded), upgrade **and** downgrade. ORM models `messaging/domain/models.py`.
2. **Domain** — `messaging/domain/{rules,labels}.py`: the permission predicates as
   **pure functions** (`can_open_thread`, `can_send_in_thread`, `can_read_thread`,
   `student_to_student_blocked` first), thread `kind`/`context_type`/`status`
   vocabularies + vi+en labels, the 10-min-delete + system-undeletable rules, the
   anonymity-mask decision (`render_counterpart_label(viewer, thread, application)`).
   No I/O.
3. **Services** —
   `thread_service.py` (create with the matrix + recruitment-relationship check +
   `is_anonymous` denormalization + audit + version; list_mine; get; archive);
   `message_service.py` (send: re-check §1.2 + rate limit §1 + persist + bump thread
   + audit + notify in one tx; idempotent via `client_dedupe_key`; mark-read; delete
   with the ownership/10-min/system/university rules; report);
   `thread_view.py` (the **single** projection source: per-viewer masking,
   per-thread unread, my-threads/unread-count aggregation).
   Relationship lookup reads `recruitment` via an interface/read query
   (`applications.org_id` + `applicant_id` + `status`/`is_anonymous`/
   `reveal_approved_at`) — **no cross-module implementation import**.
4. **API** — `messaging/api/router.py` routes per §7 (HTTP-only) + Pydantic schemas +
   presenters (masked identity, vi+en, coded errors, never raw paths/codes).
5. **Notifications** — add `message.received` + `message.flagged` to
   `message_catalog.py` (in-app, vi+en) + `template_seed.py` (email, vi+en,
   allowlisted vars, category `message`); add the **Messaging** category to the
   preference center.
6. **Tests (SQLite, `tester-qa` gate):** student→student create **and** send both
   blocked (the hard first check); university→anyone ok; partner→student **with**
   application ok, **without** application → blocked; partner↔partner same-org ok,
   cross-org → 404; student→university initiate ok; student→partner initiate refused,
   reply-into-existing ok; **anonymity**: partner sees the masked handle (no
   name/email in the thread view, the message echo, **or** the partner's
   notification) before reveal, real name after `reveal_approved_at`; persist-before-
   deliver (a row exists/committed before any notification); notification dedupe
   coalesces a burst into one feed row; **rate limit** global ceiling + inactive-
   application 3/day taper → `429` + `reset_at`; idempotent re-send via
   `client_dedupe_key`; own-message delete ≤10min ok / >10min refused / system
   undeletable / university deletes any / partner cannot delete to-student; mark-read
   clears unread; unread-count aggregation; cross-tenant thread/message → `404`;
   mute suppresses notification; report audits + notifies university; audit row per
   write carries **no** body/name/email.

**Frontend slice (follows, after the contract is green) — `frontend-developer`:**
persona inboxes (student institutional inbox inheriting the marketplace shell;
partner candidate-thread panel with the anonymous handle until reveal; university
initiate + announcement + moderation read), the slide-in thread panel (PRD M25),
polling unread badge mirroring the notification bell, send/retry/optimistic + offline/
stale recovery states, mute/report, reply-to (thread-lite), markdown-lite render
(sanitized), and honest empty/permission/`429`/`409`-closed states (no `confirm()`).
Mark `API wired` → `browser verified` → `E2E verified` distinctly.

## Consequences

- **Positive:** institutional messaging ships on a small, doc-faithful slice that
  honors every non-negotiable — student↔student is impossible (first check, two
  layers), partner↔student is anonymity-safe and recruitment-bound, content is
  persisted before any delivery, RBAC is re-checked on create/send/read, and there is
  **zero new infra** (REST + the shipped polling + the shipped notification feed/
  outbox). The deferred WS/presence/broadcast/attachment/reactions layers attach to
  stable `message_threads` / `messages` / `message_thread_participants` and the same
  service-layer predicates without rework.
- **Cost / limits:** one migration (`0023`). V1 is **near-real-time via polling, not
  push** — no sub-second delivery, no presence, no read receipts/reactions/pin/search/
  attachments, no segmented broadcast, no cold outreach. Acceptable for institutional,
  low-volume, single-instance V1 (ADR-0003 assumption).
- **Reversibility:** the module is additive; dropping `0023` + the new routers/
  services + the two catalog entries removes messaging entirely. The WS/presence ADR
  is purely additive on top.

## Doc conflicts resolved (precedence: product > business > security > arch > API/data)

1. **Module + path naming.** `docs/API_CONTRACTS.md` §Messaging uses
   `/conversations`, `conversations`, `message_reads`; CLAUDE.md naming default +
   ARCHITECTURE intent is module **`messaging`**. **Resolved (CLAUDE.md precedence):**
   module `messaging`, public paths `/api/v1/messaging/threads`, tables
   `message_threads` / `messages` / `message_thread_participants`. **Flag
   API_CONTRACTS §Messaging** to rename `/conversations*` → `/messaging/threads*` and
   `message_reads` → `message_thread_participants.last_read_at`.
2. **Delivery: WS-first vs polling.** ARCHITECTURE §WebSocket presents `messages
   (conversation_id …)` + `message_reads` + a presence zset + WS-first delivery.
   **Resolved (no WS infra shipped; local-first):** V1 = REST + polling
   (persist-before-deliver still honored); WS + Redis fan-out + presence are a
   **follow-up ADR** with the contract pre-committed (§3). **Flag ARCHITECTURE
   §WebSocket** to note "V1 messaging is REST+polling per ADR-0012; the `/ws/` +
   Redis-fan-out + presence design here is the deferred follow-up," and to rename
   `conversation_id`→`thread_id` / `conversations`→`message_threads`.
3. **Partner→student cold outreach 3/day.** BUSINESS_LOGIC §14.1 allows a partner to
   message a **non-applicant** student at max 3/day; PRD M25 restricts partner→student
   to **recruitment context only**. **Resolved (product > business):** V1 =
   recruitment-context-only (a partner cannot discover an arbitrary student without
   passive search, which is deferred); the 3/day cold-outreach is **deferred to the
   passive-search slice**, and the 3/day cap is **repurposed** as the inactive-
   application taper (§1). **Flag BUSINESS_LOGIC §14.1** to note "cold-outreach to
   non-applicants deferred to passive search (ADR-0012); V1 partner↔student is
   application-bound; the 3/day cap applies to terminal-application threads."
4. **Read receipts / reactions / pin / search / attachments / groups / broadcast
   builder (PRD M25).** Not a contradiction — **scope cut to a later slice** (§8),
   recorded here so the V1 absence is intentional, not a gap.
