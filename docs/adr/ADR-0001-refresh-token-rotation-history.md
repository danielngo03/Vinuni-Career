# ADR-0001: Refresh Token Rotation History Table

**Status:** Accepted (ratifies a Phase 1a implementation deviation)
**Date:** 2026-06-27
**Owner:** system-architect
**Supersedes:** `sessions.refresh_token` single-column design in `docs/DATA_MODEL.md` §4

## Context

`docs/DATA_MODEL.md` originally modeled the refresh secret as a single hashed
column on `sessions` (`refresh_token VARCHAR(512) NOT NULL UNIQUE`). The Phase 1a
auth slice instead implemented a dedicated `refresh_tokens` history table
(migration `0002_auth_identity_core`) with one row per issued refresh token, a
rotation chain (`replaced_by_id`), and `rotated_at` / `revoked_at` timestamps.

`docs/ARCHITECTURE.md` §5 and `docs/SECURITY_PRIVACY.md` require "secure refresh
tokens and revocation" and refresh-token **rotation**. A single mutable column on
`sessions` cannot represent a rotation chain and cannot distinguish "this token
was legitimately rotated" from "this token is being replayed," so it cannot
implement refresh-token **reuse detection** — a standard OAuth/OIDC hardening
control. The deviation is therefore a deliberate security improvement, not drift.

## Decision

The `refresh_tokens` history table is the **canonical** design.

- `sessions` is pure device/metadata: `device_hint`, `ip_hash` (hash only),
  `city_level_location` (coarse, optional), `expires_at`, `last_seen_at`,
  `revoked_at`, `revoked_reason`. It holds **no** refresh secret.
- `refresh_tokens` stores one row per issued token: `token_hash` (SHA-256, unique;
  raw token never persisted), `expires_at`, `created_at`, `rotated_at`,
  `revoked_at`, `replaced_by_id` (chain link to the successor token).
- On `POST /auth/refresh`: verify presented token by hash → if valid and not yet
  rotated/revoked, set `rotated_at`, insert a successor row, link `replaced_by_id`.
- **Reuse detection:** presenting an already-rotated or revoked token revokes the
  entire `session` (`revoked_reason = 'reuse_detected'`) and all of its tokens.
- `docs/DATA_MODEL.md` §4 has been updated to match (sessions table + new
  `refresh_tokens` table).

## Consequences

- Positive: rotation chains, reuse detection, and per-token revocation are
  expressible; device/session metadata is cleanly separated from secrets; aligns
  with the security docs and account/device privacy rules (raw IP/UA never stored).
- Cost: one extra table and a small amount of rotation bookkeeping per refresh.
  Expired/rotated rows accumulate; a later cleanup job (Celery) prunes
  `refresh_tokens` where `expires_at < now()` and `rotated_at IS NOT NULL`.
- No API contract change: `/auth/refresh` request/response are unchanged; the
  change is internal to persistence.
- Downstream specs (Phase 1b and later) must treat `sessions` as device/metadata
  only and never reintroduce a refresh secret column on `sessions`.
