# Security & Privacy — VinUni Career Platform

> Phiên bản: 1.0 | Cập nhật: 26/06/2026  
> Source of truth for RBAC, privacy, PII, AI safety, ads compliance, audit, and operational security.

## Core Rules

- RBAC is enforced in service/application layer.
- Tenant isolation is enforced in queries and service methods.
- Every write action is auditable.
- PII is minimized, encrypted where appropriate, and never logged.
- CV access uses signed URLs and partner downloads require watermark.
- AI internals are hidden from end users.
- Sponsored/ad labels are mandatory and cannot be removed by UI options.

## RBAC

Both Partner and University use configurable RBAC:

- `Organization`
- `Department`
- `Role`
- `Permission`
- `Membership`

No hardcoded university staff roles. Super Admin creates roles and permissions.

Permission checks must include:

- actor identity
- organization scope
- resource ownership
- action
- field-level visibility where needed

## PII And CV Data

- Never log names, emails, phone numbers, student IDs, government IDs, raw CV text, or prompt content containing PII.
- Use signed URLs with short expiry for files.
- Partners never see direct storage paths.
- CV download by partner adds watermark with partner identity and timestamp.
- Anonymous applications redact configured fields and PII in CV preview.

## CV Studio Privacy

- Uploaded CV originals, builder CV JSON, CV versions, AI suggestion diffs, and application CV snapshots are student-owned sensitive data.
- Raw CV text, `snapshot_json`, `diff_json`, and extraction text must never be sent to analytics or generic logs.
- AI may use only permitted sources: confirmed profile fields, reviewed upload extraction, owned builder CV versions, target job/JD, and user-provided notes.
- AI suggestions are owner-only until accepted; partners never see rejected or pending suggestions.
- Application CV snapshots are immutable and scoped to the application.
- Anonymous applications render redacted preview from the submitted snapshot, not from the student's current live CV.
- Partner downloads use watermarked rendered PDF and are audited.
- Template preview images are safe public assets; filled CV previews are signed/private.

## Public Media And Organization Assets

- Static VinUni-owned assets in `frontend/public` may be public and cacheable.
- Employer-uploaded logos, cover images, event covers, and campaign creatives are
  user-generated organization media and require validation before public display.
- Internal storage keys such as `logo_path`, object keys, bucket names, and local
  filesystem paths must never appear in public APIs, frontend state, logs,
  analytics, email templates, or error payloads.
- Public media URLs may be stable only after the owning organization is active
  and the media is validated. Suspended/deleted organizations lose public media
  delivery.
- Partner admins may upload/update their own organization media only through
  `organizations:update` or narrower media permissions. University admins may
  remove or replace media for moderation, authenticity, or brand-safety reasons.
- File validation must check size, MIME, magic bytes, unsupported/corrupt files,
  and suspicious content where a scanner is available. Reject with user-safe
  reasons only.
- Never use unrelated real-company logos as static decoration. Demo logos must be
  uploaded through the same local/demo pipeline and clearly treated as seed data.

## AI Safety

End users never see:

- provider names
- model names
- API keys
- token counts
- latency
- raw confidence
- prompt text
- OCR/embedding internals
- internal status codes

> **Narrow exception (routing canvas only):** University Admin holding the
> distinct `ai_settings:view_provider_identity` RBAC grant MAY see real
> provider/model identity (not API keys, not base URL) via the internal
> `ai_settings` routing canvas surface only. This never applies to end
> users, partners, or students, and never applies to any other admin surface.
> See `docs/API_CONTRACTS.md` ADR-0011.1 and `docs/AI_PRODUCT_SPEC.md` §5.5.

AI write actions:

1. AI proposes.
2. User sees confirmation summary.
3. User explicitly confirms.
4. Backend executes through normal service/RBAC path.
5. Audit log records action and tool call.

Moderation/fraud/approval:

- AI suggests only.
- Human final say.
- AI suggestion and human decision are both audited.

## Advertising Compliance

Forbidden targeting:

- name, email, phone
- health, religion, politics
- ethnicity/national origin
- gender/sexual orientation
- disability/pregnancy
- exact location
- sensitive financial status

Required:

- `Được tài trợ` / `Quảng cáo` label on sponsored content.
- "Why am I seeing this?" explanation using non-PII targeting.
- Audit trail for targeting configs.
- University approval before sponsored content goes live unless trusted-policy config explicitly allows otherwise.

## Authentication

- Secure refresh tokens and revocation.
- Browser refresh tokens are delivered via httpOnly cookies, not JSON body fields
  or frontend localStorage/sessionStorage.
- Account lockout after repeated failed login attempts.
- TOTP optional for users and configurable/required for university staff.
- TOTP secrets are encrypted at rest and login enforcement must be implemented
  before UI claims 2FA is active.
- VinUni SSO/OIDC/SAML for verified VinUni identities.
- Email/password fallback only where product scope allows.

## Account, Device, And Location Privacy

- Session/device pages show safe device hints, browser/OS family, and last activity time.
- Store IP hash only; raw IP is not persisted in application tables.
- City-level location is optional and used only for account security explanation.
- Exact GPS/location is never collected for core account security.
- Remote logout creates a security event and revokes refresh tokens for that session.
- Security alerts are mandatory notifications and cannot be disabled.

## Notification And Email Safety

- Email/push bodies must not contain sensitive CV text, raw scores, private notes, or hidden anonymous-apply fields.
- Push notifications must be PII-minimal because they may appear on lock screens.
- Template variables are allowlisted per event type.
- Unknown variables or missing required variables block template activation/send.
- Admin broadcasts require RBAC and audit.
- AI-generated communication drafts require human confirmation before activation or send.

## Export Security

- Field-level RBAC before export generation.
- Anonymous data stays redacted in exports.
- Download links expire.
- Large exports run asynchronously.
- Export creation and download are audited.

## Security Review Gate

Before merging sensitive features:

- RBAC tests pass.
- Cross-tenant access tests pass.
- Audit tests pass.
- PII logging reviewed.
- Rate limits defined.
- File access path reviewed.
- AI leakage tests pass if AI involved.
