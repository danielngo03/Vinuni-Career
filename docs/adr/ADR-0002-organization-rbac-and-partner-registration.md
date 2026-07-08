# ADR-0002: Phase 1b — Organization RBAC + Partner Registration

**Status:** Accepted (implementation-ready design)
**Date:** 2026-06-27
**Owner:** system-architect
**Implements:** `docs/ARCHITECTURE.md` §4.4 (RBAC), §8 constraints; `docs/DATA_MODEL.md` §5;
`docs/API_CONTRACTS.md` (Organizations, Partner Registration); `docs/BUSINESS_LOGIC.md` §2;
`docs/SECURITY_PRIVACY.md` (RBAC, tenant isolation, audit); `docs/EDGE_CASES_FAILURE_MODES.md`
**Builds on:** Phase 1a (auth/users/account, migration head `0002_auth_identity_core`), ADR-0001
**Next implementer:** `backend-developer` (backend + migration), then `frontend-developer`

---

## 1. Goal & Decision

Replace Phase 1a's static persona-baseline grants (`auth/domain/personas.py`) with
**DB-backed, org-scoped RBAC**, and ship **partner self-registration → university
approval** that bootstraps the partner organization with a first-registrant admin.

Decision summary:

- New internal module `organization` owns organizations, departments, roles,
  permissions, memberships, invitations, and partner-registration requests. Public
  API under `/api/v1/organizations`, `/api/v1/partner-registration`,
  `/api/v1/admin/partners/...`.
- `Principal.permissions` is resolved from `memberships → membership_roles → roles →
  permissions` for the active identity's org. Students/alumni (no org) keep the
  persona baseline. `users.is_superadmin` remains a platform-wide bypass.
- Partner orgs are created **only on approval** (anti-spam). University orgs are
  created by a platform superadmin (bootstrap), then super-admin creates roles.
- One new Alembic migration `0003_organization_rbac` (after `0002`), adding the RBAC
  tables and wiring the three deferred FKs to `organizations`.

This ADR is the contract; no application code is written here.

---

## 2. Module Boundaries & Ownership

```
backend/app/modules/organization/
├── api/
│   ├── router.py                 # /organizations, /partner-registration, /admin/partners
│   ├── schemas.py                # Pydantic request/response
│   └── presenters.py             # ORM -> friendly response (no raw enum codes)
├── application/
│   ├── organization_service.py   # org profile read/update
│   ├── rbac_service.py           # roles, permissions, departments
│   ├── membership_service.py     # members, role/dept assignment, invitations
│   ├── partner_registration_service.py  # register / approve / reject + bootstrap
│   ├── grant_resolver.py         # memberships->roles->permissions -> frozenset[str]
│   └── errors.py
├── domain/
│   ├── models.py                 # ORM: Organization, Department, Role, Permission,
│   │                             #      Membership, MembershipRole, MembershipDepartment,
│   │                             #      Invitation, PartnerRegistrationRequest
│   ├── catalog.py                # PERMISSION_CATALOG, ADMIN_WILDCARD, validators
│   └── repository.py             # abstract repo interfaces
└── infrastructure/
    └── repository.py             # SQLAlchemy implementations
```

Sub-structure for partner vs university orgs is **data-driven via `organizations.org_type`**
(`'partner' | 'university'`), not separate table trees. Both share the identical RBAC
model (ARCHITECTURE §4.4). Behavioral differences live in services:

- `org_type='partner'`: created by approval flow; profile carries company fields
  (`industry`, `company_size`, `founded_year`, `headquarters_city`); `trust_level`
  and `subscription_tier` set at approval.
- `org_type='university'`: created by platform superadmin bootstrap; company fields
  unused; holds the partner-review permissions (`partners:*`).

Cross-module rules (ARCHITECTURE §8): no cross-module implementation imports.
`organization` exposes a read interface (`grant_resolver`) consumed by the auth
dependency to build `Principal`; everything else communicates via the outbox
(`outbox_events`) and the notification outbox (`notification_outbox`). The auth
module imports the `organization` grant resolver only — a one-way, read-only
dependency from auth → organization (auth already owns `Principal` shape).

---

## 3. Entities (reconciled with `docs/DATA_MODEL.md` §5)

All entities follow §3 shared conventions (UUID PK, timestamps, `deleted_at` where
soft delete applies, `version` for optimistic locking). DATA_MODEL.md §5 has been
updated in this batch; the table below is the authoritative column set for the
migration.

### 3.1 Already in DATA_MODEL.md (unchanged structure, build as-is)

- **`organizations`** — PK `id`; `slug` UNIQUE; `display_name`; `org_type`
  (`partner|university`); company fields; `is_verified`, `verified_at`,
  `verified_by → users(id)`; `status` (`pending|active|suspended`);
  `subscription_tier`; **`trust_level`** (added this batch: `standard|verified|strategic`);
  `settings JSONB`; timestamps; `deleted_at` (org soft delete — **Never** hard-deleted,
  per §1267); `version`. Indexes: `idx_orgs_slug` (partial `deleted_at IS NULL`),
  `idx_orgs_type` on `(org_type, status)` partial `deleted_at IS NULL`.
- **`departments`** — `id`; `org_id → organizations(id) ON DELETE CASCADE`; `name`;
  `parent_id → departments(id)` (hierarchical, nullable); `created_at`;
  UNIQUE `(org_id, name)`.
- **`roles`** — `id`; `org_id → organizations(id) ON DELETE CASCADE`; `name`;
  `description`; `is_system BOOLEAN` (system roles cannot be deleted/renamed);
  timestamps; UNIQUE `(org_id, name)`. Add `updated_at` trigger.
- **`permissions`** — `id`; `role_id → roles(id) ON DELETE CASCADE`;
  `resource_type VARCHAR(100)`; `action VARCHAR(50)`; UNIQUE
  `(role_id, resource_type, action)`. (Permission catalog approach: see §4 — rows are
  role-scoped grant tuples, not a global catalog table; the catalog is enforced in
  code via `domain/catalog.py`.)
- **`memberships`** — `id`; `user_id → users(id) ON DELETE CASCADE`;
  `org_id → organizations(id) ON DELETE CASCADE`; `identity_id → identities(id)`;
  `status` (`active|suspended|left`); `joined_at`; `left_at`; **`version`** (added);
  `created_at`; UNIQUE `(user_id, org_id)`. Index `idx_memberships_org` partial
  `status='active'`.
- **`membership_roles`** — composite PK `(membership_id, role_id)`, both
  `ON DELETE CASCADE`; `assigned_at`; `assigned_by → users(id)`.
- **`invitations`** — `id`; `org_id ON DELETE CASCADE`; `email`;
  `role_id → roles(id)`; **`department_id → departments(id)`** (added, optional);
  `token_hash` UNIQUE; **`status`** (`pending|accepted|revoked|expired`, added);
  `invited_by → users(id)`; `expires_at`; `accepted_at`; `created_at`. Partial UNIQUE
  `(org_id, lower(email)) WHERE status='pending'`.

### 3.2 Added this batch (new tables, written into DATA_MODEL.md §5)

- **`membership_departments`** (M2M) — composite PK `(membership_id, department_id)`,
  both `ON DELETE CASCADE`; `assigned_at`; `assigned_by → users(id)`. Implements
  ARCHITECTURE §4.4 `Member (n) ── (m) Departments`.
- **`partner_registration_requests`** — pending partner self-registration; org is
  created only on approval. Columns per DATA_MODEL.md §5: company + contact fields,
  `status` (`pending_review|approved|rejected`), `review_note`, `reviewed_by`,
  `reviewed_at`, `created_org_id → organizations(id)` (set on approval), `version`,
  timestamps. Partial UNIQUE on `tax_code WHERE status='pending_review' AND tax_code
  IS NOT NULL` and on `lower(contact_email) WHERE status='pending_review'`.

### 3.3 Deferred FKs added now (organizations table now exists)

| Column | New FK | ON DELETE | Rationale |
|---|---|---|---|
| `identities.org_id` | `→ organizations(id)` | `RESTRICT` | Orgs are never hard-deleted (§1267); an identity must not be orphaned of its org context. |
| `audit_logs.actor_org_id` | `→ organizations(id)` | `SET NULL` | Audit is append-only and must survive any future org removal; never block a write or lose the row. |
| `notification_templates.owner_org_id` | `→ organizations(id)` | `RESTRICT` | Org-owned templates; orgs never hard-deleted, so RESTRICT is safe and prevents accidental dangling. |

These match DATA_MODEL.md (which already declared `REFERENCES organizations(id)` for
all three); only the live FK constraints were deferred in `0002`.

---

## 4. Permission Catalog & Grant Resolution

### 4.1 Catalog (`backend/app/modules/organization/domain/catalog.py`)

Permission strings are `"{resource}:{action}"`, matched by the existing
`PermissionChecker._matches` (`app/shared/permissions.py`), which supports `*`
wildcards. Resource nouns are **plural**, to stay consistent with the live matcher
and `personas.py` (`jobs:read`, `applications:*`). The DATA_MODEL `permissions` rows
store `resource_type` + `action`; the resolver renders each row to `f"{resource_type}:{action}"`.

Phase 1b catalog (the set a role may be granted; enforced as the legal vocabulary):

| Resource | Actions | Scope notes |
|---|---|---|
| `organizations` | `read`, `update` | View / edit own org profile & settings (partner company profile). |
| `roles` | `read`, `create`, `update`, `delete` | Manage org roles + their permission rows. |
| `departments` | `read`, `create`, `update`, `delete` | Manage org departments. |
| `members` | `read`, `invite`, `update`, `remove` | List members; send/revoke invitations; assign roles/depts; remove member. |
| `jobs` | `read`, `create` | `create` = job posting submission (enforced when `opportunities` lands). |
| `applications` | `read` | Application list view (enforced when `recruitment` lands). |
| `partners` | `read`, `approve`, `reject` | **University-org roles only**: review partner registrations. |

`ADMIN_WILDCARD = "*:*"` — a single `permissions` row `(resource_type='*', action='*')`.
`_matches("*:*", any, any)` returns true, so it grants everything **within the
member's org** (tenant isolation in `PermissionChecker.can` still applies).

### 4.2 First-registrant admin & system roles

On partner approval (and on university bootstrap), create a `roles` row
`name='Admin', is_system=true`, plus one `permissions` row `('*','*')`. The first
registrant's membership is assigned this role. `is_system` roles cannot be deleted or
renamed and cannot have their `('*','*')` grant removed (service guard, §6.4).

### 4.3 Grant resolution (replaces `personas.py` for org personas)

New `grant_resolver.resolve_grants(session, *, user_id, identity) -> frozenset[str]`:

```
if identity.org_id is None:                      # student / alumni / guest
    return personas.permissions_for(identity.persona)   # keep Phase 1a baseline
membership = active membership for (user_id, identity.org_id)   # status='active'
if membership is None or membership.status != 'active':
    return personas.permissions_for(identity.persona)   # org context but no live grant
rows = permissions for all roles linked via membership_roles
return frozenset(f"{r.resource_type}:{r.action}" for r in rows) | _COMMON_ORG_BASELINE
```

- `_COMMON_ORG_BASELINE = {"account:*", "notifications:read", "notifications:write"}`
  (same self-service baseline every authenticated persona keeps).
- `auth/api/deps.py` change: replace `permissions=permissions_for(identity.persona)`
  with `permissions=await grant_resolver.resolve_grants(session, user_id=user.id,
  identity=identity)`. `personas.py` stays as the **no-org fallback** only.
- Safe default: students (org_id NULL) are unchanged. A partner member whose
  membership is suspended/left silently drops to the persona baseline (no org powers)
  rather than erroring.
- Caching: resolve per request for Phase 1b (single indexed query). A Redis cache
  keyed by `(user_id, org_id)` with invalidation on role/membership writes is a
  documented later optimization, not required now.

Tenant isolation is unchanged and authoritative: `PermissionChecker.can` already
returns false when `resource_org_id != principal.org_id` (unless `is_superadmin`).
Every org-scoped service call MUST pass `resource_org_id=principal.org_id`.

---

## 5. Flows

### 5.1 Partner self-registration — `POST /api/v1/partner-registration` (unauthenticated)

1. Validate body (company + contact). Normalize `tax_code`, lowercase
   `contact_email`.
2. Duplicate check: if a `pending_review` request exists with same `tax_code` or
   `contact_email` → `409 CONFLICT` `details.reason='duplicate_registration'`.
   (DB partial-unique indexes are the race backstop → caught and mapped to the same
   409.) If an **active** organization already exists for that contact/tax_code →
   same 409. Optional `Idempotency-Key` returns the existing request instead of 409.
3. Insert `partner_registration_requests` (`status='pending_review'`). **No org, no
   user created yet.**
4. Audit: `partner_registration.submitted` (actor_id NULL — anonymous; resource_type
   `partner_registration_request`).
5. Enqueue notifications (outbox, never synchronous SMTP):
   `partner.registration_received` (ack to contact email).
6. Response `201`: `{ "data": { "registration_id": uuid, "status": "pending_review" } }`
   (friendly status string, not raw enum).

### 5.2 University approval — `POST /api/v1/admin/partners/{partner_id}/approve`

`{partner_id}` = `partner_registration_requests.id` while `pending_review`.
Authz: `permission_checker.require(principal, "partners", "approve")` (university-org
role) OR `is_superadmin`. Body: `{ package_id?: uuid, trust_level: "standard"|"verified"|"strategic", note?: string }`.

Single transaction:

1. Load request `FOR UPDATE` (optimistic `version` guard). If `status='approved'` →
   **idempotent**: return existing `created_org_id`. If `status='rejected'` →
   `409 CONFLICT` `reason='already_rejected'`.
2. Create `organizations` (`org_type='partner'`, `status='active'`,
   `is_verified=true`, `verified_by=principal.user_id`, `verified_at=now`,
   `trust_level=body.trust_level`, `subscription_tier` from `package_id` mapping or
   `'free'`; `slug` = unique slugify(company_name) with numeric suffix on collision).
3. Create system `Admin` role (`is_system=true`) + `('*','*')` permission row.
4. Resolve the first admin **user**: find by `lower(contact_email)`; if absent,
   create a `users` row (no password; `is_active=true`, unverified). Create
   `identities` row (`persona='partner_member'`, `org_id=new_org`). Create
   `memberships` (`status='active'`, link `identity_id`). Assign `Admin` via
   `membership_roles`.
5. Update request: `status='approved'`, `created_org_id`, `reviewed_by`,
   `reviewed_at`, `review_note=note`, bump `version`.
6. Audit (all in-tx): `partner_registration.approved`, `organization.created`,
   `role.created` (Admin), `membership.created` (first admin).
7. Outbox/notifications: `partner.registration_approved` to the admin contact with a
   **frontend activation link** (reuse `account.email_verification` / set-password
   flow so the admin sets a password and logs in). If a brand-new user was created,
   issue an `email_verifications` token (`purpose='register'`).
8. Response `200`: `{ "data": { "organization_id": uuid, "status": "approved" } }`.

`package_id`: full subscription record creation belongs to the later `subscriptions`
module. Phase 1b stores the chosen tier on `organizations.subscription_tier` and
records `package_id` in the approval audit `after` snapshot. **Open question O-1.**

### 5.3 University rejection — `POST /api/v1/admin/partners/{partner_id}/reject`

Authz `partners:reject` or superadmin. Body `{ reason: string (required, non-empty) }`.

1. Load request; if not `pending_review` → idempotent (already rejected) or
   `409` (already approved).
2. Set `status='rejected'`, `review_note=reason`, `reviewed_by/at`, bump `version`.
   No org/user is created.
3. Audit `partner_registration.rejected`. Outbox `partner.registration_rejected`
   (friendly reason, no internal codes).
4. Response `200`: `{ "data": { "registration_id": uuid, "status": "rejected" } }`.

### 5.4 University RBAC bootstrap

- `POST /api/v1/organizations` (create) — restricted to `is_superadmin` and
  `org_type='university'` only. Partner orgs are **never** created here (only via
  approval). Creates the university org + `Admin` system role (`*:*`) + the
  superadmin's `university_staff` identity + admin membership. Audited.
- Thereafter the university super-admin uses the standard org endpoints (§6) to
  create custom roles/permissions (no predefined roles) and assign staff. This is
  the same RBAC surface partners use.

---

## 6. API Contracts (`/api/v1`, error envelope + pagination per API_CONTRACTS.md)

Org is **implicit** from `principal.org_id` for `/organizations/*` paths (matches
the API_CONTRACTS path table: `/organizations/roles`, `/organizations/departments`,
`/organizations/members`). A resource id that resolves to a different org returns
`404 RESOURCE_NOT_FOUND` (cross-tenant hiding), never `403`. Unauthenticated →
`401 AUTH_REQUIRED`; authenticated-but-unpermitted → `403 PERMISSION_DENIED`.

| Method & Path | Permission | Notes |
|---|---|---|
| `GET /organizations` | `organizations:read` | Current org profile (from `principal.org_id`). |
| `PATCH /organizations` | `organizations:update` | Update profile/settings; optimistic `version`. |
| `GET /organizations/roles` | `roles:read` | Offset pagination (small admin list). |
| `POST /organizations/roles` | `roles:create` | Body `{name, description?, permissions: [{resource,action}]}`. Subset-ceiling check (§6.4). |
| `GET /organizations/roles/{role_id}` | `roles:read` | 404 if other org. |
| `PATCH /organizations/roles/{role_id}` | `roles:update` | Cannot rename `is_system`; subset-ceiling check. |
| `DELETE /organizations/roles/{role_id}` | `roles:delete` | Block if `is_system` or last admin role (409). |
| `GET /organizations/departments` | `departments:read` | |
| `POST /organizations/departments` | `departments:create` | `{name, parent_id?}`; UNIQUE(org,name). |
| `PATCH /organizations/departments/{id}` | `departments:update` | No cyclic `parent_id`. |
| `DELETE /organizations/departments/{id}` | `departments:delete` | Reassign/clear member dept links. |
| `GET /organizations/members` | `members:read` | Cursor pagination; filter `?status=`, `?role_id=`. Org-scoped. |
| `PATCH /organizations/members/{membership_id}` | `members:update` | Set roles/departments; optimistic `version`; escalation + last-admin guards. |
| `DELETE /organizations/members/{membership_id}` | `members:remove` | Soft `status='left'`; last-admin guard. |
| `POST /organizations/invitations` | `members:invite` | `{email, role_id?, department_id?}`; partial-unique pending. |
| `GET /organizations/invitations` | `members:read` | List pending/expired. |
| `DELETE /organizations/invitations/{id}` | `members:invite` | Revoke (`status='revoked'`). |
| `POST /organizations/invitations/{token}/accept` | authenticated user | Creates identity+membership+role for accepting user; token single-use, expiry-checked. |
| `POST /partner-registration` | public | §5.1. |
| `GET /admin/partners` | `partners:read` or superadmin | List registration requests; filter `?status=`. |
| `POST /admin/partners/{partner_id}/approve` | `partners:approve` or superadmin | §5.2. |
| `POST /admin/partners/{partner_id}/reject` | `partners:reject` or superadmin | §5.3. |
| `POST /organizations` | superadmin only | University bootstrap (§5.4). |

Response presenters map enum columns to friendly labels (no raw enum codes to end
users). List responses use the `{data, page:{next_cursor,limit}}` shape (cursor) or
`{data, meta}` for small offset lists.

### 6.4 Invariants enforced in services

- **Escalation ceiling:** when creating/updating a role's permission set or assigning
  roles to a member, the actor may only grant permissions that are a **subset of the
  actor's own effective grants** — unless the actor holds `*:*`. Prevents a member
  with `roles:create` from minting an `*:*` role and self-assigning it.
- **Last-admin protection:** the org must always retain ≥1 active membership holding
  an effective `*:*`. Block (409 `reason='last_admin'`) on: removing/suspending the
  last admin membership, stripping the admin role from the last admin, or deleting
  the last admin role.
- **System-role immutability:** `is_system` roles cannot be deleted or renamed; their
  `*:*` grant cannot be removed.
- **Tenant isolation:** every read/write filters by `principal.org_id`; id lookups
  verify ownership → 404 on mismatch.
- **Optimistic concurrency:** `memberships.version`, `roles.updated_at`/version, and
  `partner_registration_requests.version` guard concurrent edits → `409 CONFLICT`
  `reason='version_conflict'` on stale write.

---

## 7. Edge Cases (map to `docs/EDGE_CASES_FAILURE_MODES.md` §4)

| Case | Behavior | Code |
|---|---|---|
| Duplicate partner registration (same tax_code/email) | Reject pending duplicate; idempotency-key returns existing | `409 CONFLICT` `duplicate_registration` |
| Approve an already-approved request | Idempotent: return existing org | `200` |
| Approve an already-rejected request | Conflict | `409` `already_rejected` |
| Concurrent approve by two reviewers | `version` guard; one wins, other gets conflict | `409` `version_conflict` |
| Remove / suspend last admin | Blocked | `409` `last_admin` |
| Non-admin tries to mint `*:*` role | Blocked by subset-ceiling | `403` `permission_escalation` |
| Assign role from another org | Not found in actor's org | `404` |
| Cross-tenant read of role/member/dept | Hidden | `404` |
| Two recruiters edit same membership | Optimistic conflict, reload | `409` `version_conflict` |
| Invitation token expired / reused | Rejected | `400` `VALIDATION_FAILED` `invite_expired`/`invite_used` |
| Accept invitation for email mismatch | Block (token bound to invited email) | `403` |
| Remove member with active assignments | Allowed in 1b (soft `left`); reassignment hooks owned by `recruitment`/`opportunities` later | `200` + note |
| SMTP down during register/approve | Product write succeeds; outbox retries | `2xx` |

---

## 8. Migration Plan — `0003_organization_rbac`

`down_revision = "0002_auth_identity_core"`. File:
`backend/alembic/versions/0003_organization_rbac.py`.

**upgrade():**
1. `create_table` in FK order: `organizations`, `departments`, `roles`,
   `permissions`, `memberships`, `membership_roles`, `membership_departments`,
   `invitations`, `partner_registration_requests`.
2. Indexes: `idx_orgs_slug`, `idx_orgs_type`, `idx_memberships_org`,
   `idx_departments_org`, `idx_roles_org`, partial-unique invitation index, two
   partial-unique partner-registration indexes (Postgres only — guard with
   `is_postgres` like `0002`; SQLite test path skips partial/lower() indexes).
3. Add deferred FKs (Postgres-only block): `identities.org_id → organizations` (RESTRICT),
   `audit_logs.actor_org_id → organizations` (SET NULL),
   `notification_templates.owner_org_id → organizations` (RESTRICT).
4. Attach `set_updated_at` trigger to `organizations`, `roles`,
   `partner_registration_requests` (mirror `0002` helper).

**downgrade():** reverse order — drop triggers, drop the three FKs, drop tables
(children first), drop indexes.

Follow `0002` conventions exactly: `postgresql.UUID(as_uuid=True)`,
`server_default=gen_random_uuid()` on Postgres, `is_postgres` guards for
Postgres-only constructs, `sa.text("NOW()")` defaults.

---

## 9. Test Plan (implementer must add; `tests/unit`, `tests/integration`)

Per `docs/EDGE_CASES_FAILURE_MODES.md` §4 and `docs/TEST_STRATEGY.md`:

- **Grant resolution (unit):** student/no-org → persona baseline unchanged; partner
  member → DB grants; suspended membership → baseline drop; `*:*` admin → all-access;
  superadmin bypass.
- **Tenant isolation (integration):** org A member cannot read/patch org B
  role/dept/member → 404; list endpoints never leak other orgs.
- **RBAC boundaries:** each endpoint 401 (no auth), 403 (authed no perm), 200 (perm).
- **Escalation prevention:** non-admin cannot create/assign `*:*`; subset-ceiling on
  role create/update and member role assignment.
- **Last-admin protection:** remove/suspend/strip-role/delete-admin-role all blocked.
- **Partner registration:** happy path; duplicate (tax_code & email); idempotency-key;
  approve creates org+admin+identity+membership; approve idempotency; reject;
  approve-after-reject conflict; concurrent approve `version` conflict.
- **Invitations:** create, accept (creates membership), expired, reused, email
  mismatch, revoke.
- **Concurrency:** stale `version` on membership/role/registration → 409.
- **Audit:** every write (register/approve/reject, role/dept/member CRUD, invite)
  writes an `audit_logs` row with correct `actor_id`, `actor_org_id`,
  `resource_type`; no PII/secrets in snapshots.
- **Notifications:** register/approve/reject enqueue outbox rows; no real SMTP in
  tests; SMTP-down does not fail the product write.
- **Migration:** `upgrade` then `downgrade` round-trips; deferred FKs present;
  OpenAPI contract check for new routes.

---

## 10. Implementation Slicing & Order

Backend first (contract owner), then frontend. Suggested order:

1. **Migration `0003` + ORM models + `domain/catalog.py`** (no behavior change yet).
2. **`grant_resolver` + wire into `auth/api/deps.py`** (replace persona-only grants;
   keep persona fallback). Ship with grant-resolution unit tests — unblocks all
   org-scoped enforcement.
3. **`organization_service` + `rbac_service` (roles/departments) endpoints** with
   escalation/last-admin/system-role guards + tests.
4. **`membership_service` (members + invitations)** endpoints + guards + tests.
5. **`partner_registration_service` (register/approve/reject) + outbox notifications
   + university bootstrap** + tests. Add notification templates
   (`partner.registration_received|approved|rejected`) to the seed.
6. **Frontend** (after contracts stable, parallelizable from step 3):
   partner public registration form (`(public)/auth/register` partner variant) →
   pending state; university `(university)/partners` review/approve/reject;
   partner `(partner)/team` members/roles/departments management (real APIs, empty +
   permission states, no placeholder dashboards). Mark status `API wired` →
   `browser verified` → `E2E verified`.

Steps 1–2 are the critical path; 3–5 can pipeline; frontend trails by one step.

---

## 11. Risks & Open Questions

**Risks**
- R-1 Escalation ceiling logic is subtle; a wrong subset check is a privilege-
  escalation hole. Mitigation: dedicated unit tests + service-layer enforcement,
  never router.
- R-2 Per-request grant resolution adds one query per authed request. Acceptable
  now; Redis cache + invalidation documented as later optimization.
- R-3 `{partner_id}` in the admin path meaning "registration request id" diverges
  from a literal reading of API_CONTRACTS. Documented in DATA_MODEL.md §5 and §5.2
  here; approve returns `organization_id`.
- R-4 Creating a `users` row for an approved partner contact who never activates
  leaves a dormant account; mitigated by it being unverified + passwordless until the
  activation link is used.

**Open questions (need product/security decision)**
- O-1 `package_id` at approval: Phase 1b only sets `subscription_tier` + audits
  `package_id`; full subscription record + payment is later-phase. Confirm this is
  acceptable for v1, or whether approval must create a subscription now.
- O-2 `trust_level` vocabulary: this spec uses `standard|verified|strategic`
  (API_CONTRACTS example shows `"standard"`). Confirm the canonical enum and its
  effect on partner capabilities/quotas (BUSINESS_LOGIC §2 ties capabilities to
  packages, not trust_level).
- O-3 Should an approved partner admin be auto-`email_verified` (trusted because a
  university staffer approved them), or always go through email verification?
  Security default in this spec: always verify. Confirm.
- O-4 University org bootstrap: is a superadmin-only `POST /organizations` acceptable,
  or should the first university org be a seed/migration fixture? This spec supports
  the endpoint; product may prefer a one-time seed.
