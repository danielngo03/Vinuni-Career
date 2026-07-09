# Student Experience Completion — Design Spec (2026-07-09)

Branch: `feat/student-experience-real` (worktree, based on `vinuni-main-submission` @ ac2918a).
Scope: complete the student experience for the THREE student personas — **VinUni student**,
**external student**, **alumni** — in the REAL app (not the greenfield codebase).

Audit (5 parallel read-only agents) confirmed the codebase is mature: messaging (institutional-only,
unconditional student↔student block), offers (full state machine + deadline/expiry), AI graceful
degradation + honest organic/recommended/sponsored labeling, apply CV-snapshot immutability, truthful
append-only timeline, CV extraction (upload→confirm→name→done, structured, blank/not-CV rejection,
uploaded=read-only vs template=editable), and privacy entry points (consent + DSAR tracking) are all
implemented correctly. The real gaps cluster into 4 themes below.

## THEME A — Persona / affiliation (the headline gap)

**Problem:** All 3 personas collapse to `identity.persona="student"`. VinUni-vs-external is computed only
ephemerally inside `billing/limit_facade._student_segment_limits` from the email domain; it is never
persisted, surfaced, or used outside billing. `alumni` persona is defined (`auth/domain/personas.py`) but
**never assigned by any code path**. VinUni verification is fake: `student_email` is validated as a generic
email — `@vinuni.edu.vn` is never enforced — so "verified" is meaningless and cannot distinguish VinUni from
external. No verified-student badge, no persona badge, no in-app verify prompt.

**Design (minimal, clean, doc-aligned — DATA_MODEL.md:511 `student_profiles.tier`):**

1. **`student_profiles.affiliation`** — new column `VARCHAR(30) NOT NULL DEFAULT 'general'`, values
   `vinuni_student | alumni | external | general`. Plus **`student_verified_at TIMESTAMPTZ NULL`** (badge source).
   Migration with up+down; single alembic head (renumber-coordinate at merge).
2. **`student_profiles` owns an affiliation facade** (`application/affiliation_facade.py`):
   `set_affiliation(session, user_id, affiliation, *, verified_at)` and `get_affiliation(session, user_id)`.
   Other modules call the facade — no cross-module ORM import.
3. **Verification becomes meaningful.** Add `student_kind` to `StudentVerifyRequestBody`:
   `vinuni_student | vinuni_alumni | external`. Enforcement in the service (not just schema):
   - `vinuni_student` / `vinuni_alumni` → the OTP `student_email` MUST be an institution domain
     (reuse `core.config.institution_email_domains`, i.e. `@vinuni.edu.vn`); else 422 with a user-safe message.
   - `external` → any valid email (already the case).
   On `confirm_student_verify` success:
   - set `student_profiles.affiliation` via facade: vinuni_student→`vinuni_student`, external→`external`,
     vinuni_alumni→`alumni` **and** `update_identity_persona(..., persona="alumni")` (makes alumni assignable).
   - set `student_verified_at = now`.
   Remove the orphaned `ai_check_status="pending"` dead write (nothing consumes it) OR leave it but note it —
   prefer removing the misleading dead line.
4. **Resolver for the unverified/derived display** (`affiliation_facade.resolve_display`): if `affiliation`
   already set (verified) use it; else derive a *provisional* label from login-email domain (institution→
   vinuni_student) + onboarding `seeker_type` (professional→general, student/fresh_graduate→external) — but
   mark `verified=False`. This gives seeker_type (currently inert) a real purpose without over-persisting.
5. **Surface it:** add `affiliation` + `verified` to the `/me`/session payload (auth me presenter) and to the
   student profile presenter (`student_profiles/api/presenters.py`). Do NOT leak provider/model/internal codes.

**Entitlement note:** billing already differentiates vinuni vs external for AI energy via the email heuristic;
leave billing as-is this pass (it works). Affiliation is now the authoritative, surfaced fact. Aligning billing
to read the facade is a follow-up (documented, not done here).

## THEME B — Dashboard next-actions / todo completion

**Problem:** `dashboards/application/student_dashboard.py:76-92` emits only `build_cv` / `respond_reveal` /
`create_alert`. Missing the task-required todos: **respond to offer**, **respond to interview**,
**unread messages**, **verify account** (persona-aware). Frontend hero right-panel has a FAKE tile whose
"CVs" value is the literal string `"CV Studio"` + a decorative AI-accent filler card (`student-dashboard.tsx:100-117`).
Dead i18n key `dashboard.actions.complete_profile`.

**Design:**
- Extend `student_dashboard.py` next-actions (read-model, no heavy live joins — use existing read facades):
  - `verify_account` when affiliation is unverified/general and the student is eligible to verify (persona-aware:
    text differs for prospective VinUni vs external). Deep-link to onboarding student-verify.
  - `respond_to_interview` when a scheduled interview needs the student's confirmation (see Theme D state).
  - `respond_to_offer` when a `sent`/live offer awaits response (reuse `offer_service` read; offers were entirely
    absent from the dashboard).
  - `unread_messages` when unread thread count > 0 (via a messaging read facade — do NOT import messaging ORM;
    add/rely on a `unread_count` read facade). Also add an unread metric tile.
- Frontend: remove the fake hero tile / decorative filler; replace with a real signal (e.g. profile/verify status
  + real counts) or drop the panel. Add offer/interview/unread/verify next-action rows + icons + vi/en i18n.
  Prune the dead `complete_profile` key + icon.

## THEME C — Applications list status clarity (real bug)

**Problem:** `recruitment/application/apply_service.list_my_applications` builds items via
`presenters.applicant_application(...)` and never attaches `upcoming_interview` / `offer` / `next_action`
(only the detail path does). But `student-applications-screen.tsx` renders per-row `app.upcoming_interview`
and `app.offer` for the Interviews/Offers tiles, the interview/offer filter tabs, the 4-step progress bar,
and contextual badges → those tiles always read 0, tabs never appear, progress never advances.

**Design:**
- In `list_my_applications`, batch-attach the same **identity-safe** interview/offer cards used by the detail
  path (`student_interview_block` / `student_offer` projections — no assignees/scorecards/internal fields) and
  the server `next_action` per row. Batch the reads (no N+1); keep it a read-model shape.
- Frontend already consumes these optional fields; verify tiles/tabs/progress/badges now light up. Surface
  `next_action` per row for consistent "what to do next" at the list level.

## THEME D — Interview respond / confirm (student)

**Problem:** All interview mutations are partner-only (`recruitment/api/router.py:356-461`). The student is
purely passive — cannot confirm attendance or request a reschedule; the card has no actions. Task requires
"respond to interview".

**Design:**
- Add a student endpoint `POST /applications/{id}/interviews/{interview_id}/respond` (owner-only, 404 for
  non-owner, idempotent) with actions `confirm` | `decline` | `request_reschedule` (+ optional note).
  Service-layer RBAC, optimistic version guard, audit event, timeline event, and a notification to the partner
  (masked, PII-safe). New interview response state on the `Interview` (e.g. `candidate_response` +
  `candidate_responded_at`) via migration; only student-owned transitions; never expose partner internals.
- Frontend: add confirm/decline/request-reschedule actions to `upcoming-interview-card.tsx` (double-confirm
  for decline, like offers), with vi/en i18n and honest states.

## Cross-cutting honesty cleanups (cheap, in-scope)
- Relabel the cosmetic client-side "AI Insights" panels on saved/alerts/applications that are deterministic
  client math (not AI) — rename to non-AI ("Tổng quan"/"Insights" without "AI") or gate honestly.
- Prune dead `complete_profile` i18n key + icon.

## Deferred (documented, NOT done this pass)
- Screening-question **authoring** (needs partner/job-side schema + capture) — plumbing exists; answers always `{}`.
- DSAR **auto-purge/export engine** (V1 tracks only) — entry point works; full engine is a large compliance build.
- Dead ingestion manual-review flow removal (`INGEST_NEEDS_REVIEW`/`review_fields`/`_apply_overrides`) + legacy
  `/cvs/upload` + `/cvs/parse-runs` parser — risky to rip out; masked/working; separate cleanup pass.
- Job-alert frequency/edit/active-toggle; consolidated "My Offers" page; email-channel notification-pref
  enforcement; talent-pool consent logging.

## Verification plan
- Backend: targeted pytest for touched modules (onboarding, student_profiles, recruitment, dashboards).
- Frontend: `pnpm typecheck`, `pnpm check:messages`, `pnpm build`.
- Playwright smoke: login student → dashboard → CV → jobs → apply → applications detail.
- Persona proof: seed/verify a VinUni-email student (verified vinuni_student), an external student, an alumni;
  confirm badge + entitlement-visible + verify prompt differ.
