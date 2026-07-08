---
name: vinuni-security-review
description: Use for security, privacy, RBAC, audit, AI leakage, file access, and sponsored-content reviews.
---

# VinUni Security Review

Use this skill before shipping security-sensitive code or when the user asks for a security/RBAC/privacy audit.

## Must Read

- `CLAUDE.md`
- `docs/SECURITY_PRIVACY.md`
- Relevant `docs/BUSINESS_LOGIC.md`
- Feature-specific docs such as `docs/CV_STUDIO_SPEC.md` when CV/file/AI suggestion data is involved
- `docs/API_CONTRACTS.md`
- `docs/DATA_MODEL.md` if data shape changes
- `docs/SYSTEM_ACCEPTANCE_BAR.md`
- `.claude/rules/ai.md` if AI is involved

## Review Checklist

- Authentication: unauthenticated requests fail with 401.
- Browser refresh tokens are delivered only through httpOnly, Secure, SameSite cookies; never JSON response bodies, localStorage, or sessionStorage.
- TOTP/2FA is not advertised as protective unless login enforcement, recovery behavior, and encrypted secrets are implemented.
- Authorization: wrong persona/role/tenant fails with 403.
- RBAC is enforced in application/service layer, not only route/UI.
- Writes create audit data and do not log PII.
- CV/file access uses signed URLs; partner CV downloads require watermark.
- CV Studio never logs raw CV text, snapshot JSON, extraction text, or AI diff content.
- AI responses hide provider/model/token/prompt/internal details.
- AI write actions require explicit confirmation and audit.
- Sponsored/ad labels are visible and non-removable.
- Student-to-student messaging remains blocked.
- Partner-to-student messaging respects recruitment context and rate limits.
- Inputs are protected against injection, XSS, SSRF, shell injection, and unsafe file parsing.

## Output Format

```markdown
SECURITY REVIEW: <scope>

CRITICAL:
- ...

HIGH:
- ...

MEDIUM:
- ...

PASS:
- ...

Recommended tests:
- ...
```
