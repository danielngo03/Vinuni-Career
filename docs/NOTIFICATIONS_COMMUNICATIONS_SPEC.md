# Notifications & Communications Spec — VinUni Career Platform

> Purpose: source of truth for in-app notifications, email, push, digest, template builder, and communication preferences.

---

## 1. Product Principle

Notifications are career-critical, not marketing spam. Every notification must answer:

- Why am I receiving this?
- What changed?
- What should I do next?
- Can I control this category/channel?

---

## 2. Channels

| Channel | Use For | Default |
|---|---|---|
| In-app | All authenticated user notifications | On |
| Email | Critical lifecycle events, digests, admin alerts | On for critical, configurable for optional |
| Push/PWA | Urgent reminders only after explicit browser permission | Off until opted in |
| Admin broadcast | University-approved announcements | RBAC-restricted |

Critical/legal notifications may bypass opt-out when required for account/security/compliance, but must be labeled as mandatory in settings.

---

## 3. Notification Categories

Student:

- Application submitted/status changed/interview scheduled/offer received.
- Job deadline reminders and saved-job closure.
- Personalized job match digest.
- CV export complete / CV parsing needs review.
- Event registration, waitlist, ticket, certificate.
- Security alerts: new device, password change, remote logout.

Partner:

- New application, candidate stage SLA, interview response, offer response.
- Job moderation approved/rejected.
- Quota warning and package expiry.
- Suspicious account or policy review request.

University:

- Moderation queue SLA, partner approval, AI provider unhealthy.
- Failed KB ingestion, failed export, fraud/risk escalation.
- Weekly/monthly system digest.

---

## 4. Template Builder

University admins with permission `notifications.manage_templates` can manage templates.

Template fields:

- `key`: stable event key, e.g. `application.status_changed`.
- `channel`: `email`, `in_app`, or `push`.
- `locale`: `vi` or `en`.
- `subject`: email only.
- `title`: in-app/push.
- `body`: rich text for email, safe plain/limited markdown for in-app/push.
- `variables_schema`: allowed variables and required variables.
- `status`: `draft`, `active`, `archived`.
- `version`: immutable active versions.

Variable syntax:

```text
{{name}}
{{job_title}}
{{company_name}}
{{application_status}}
{{action_url}}
{{deadline_at}}
```

Rules:

- Unknown variables block activation.
- Missing required variables block dispatch.
- `action_url` must be internal or approved allowlist.
- Templates can be previewed with sample data before activation.
- Active template versions are immutable; edits create a draft version.
- Every send records template key/version, channel, recipient, and delivery status.

---

## 5. Preference Center

Route: `/settings/notifications`.

Users can configure:

- Category on/off where optional.
- Channel preference: in-app, email, push.
- Digest cadence: immediate, daily, weekly, off.
- Quiet hours.
- Language for notifications.

Mandatory categories:

- Security alerts.
- Legal/compliance notices.
- Application lifecycle confirmations.
- Payment/manual billing receipts where applicable.

---

## 6. Account And Device Settings

Route: `/settings/security`.

Required capabilities:

- View active sessions/devices.
- Remote logout a device.
- Change password.
- Enable/disable TOTP where allowed.
- View recent security events.
- Manage trusted browser/device labels.

Stored data must be privacy-safe:

- Store device hint, browser family, OS family, last seen city-level location if enabled.
- Store IP hash, not raw IP.
- Do not store exact GPS location for account security.

---

## 7. Dispatch Architecture

Use notification outbox:

1. Domain event occurs.
2. Service writes domain record + notification outbox event in same transaction.
3. Worker renders template with safe variables.
4. Worker checks preferences and mandatory category rules.
5. Worker sends channel messages idempotently.
6. Delivery status is recorded per channel.

No product workflow should synchronously wait for SMTP/push provider success.

### 7.1 Drain, retry, and dead-letter (ADR-0003)

The outbox is drained by the standalone scheduler (`outbox.drain`, every 15s — see
`docs/LOCAL_DEV_STACK.md`), never on the product write path. `process_outbox`
claims due rows with `status='pending' AND (next_attempt_at IS NULL OR
next_attempt_at <= now)` and (on PostgreSQL) `FOR UPDATE SKIP LOCKED` so multiple
drainers never double-send.

`notification_outbox.status` vocabulary: `pending | sent | failed | skipped | dead`.

- **Permanent errors → terminal `failed` (no retry):** `TEMPLATE_NOT_FOUND`,
  `TEMPLATE_VARIABLE_ERROR`. The row is never reclaimed.
- **Transient send failures → retry with backoff:** the adapter call is wrapped so
  one delivery failure never rolls back the batch. The row stays `pending`,
  `attempts` increments, `error_code='SEND_FAILED'`, and
  `next_attempt_at = now + min(60s · 2^(attempts-1), 1h)` defers the next attempt
  (exponential backoff, capped at 1 hour). NULL `next_attempt_at` = eligible now.
- **Dead-letter → terminal `dead`:** once `attempts >= outbox_max_attempts`
  (config, default 5) the row becomes `dead` and is never reclaimed. `dead` is a
  code-only status value — the column is `String(20)` with no DB enum, so no DDL.
- **Successful send** clears `error_code`/`next_attempt_at` and sets `sent` +
  `sent_at`. Re-running the drain is a no-op on any terminal row (idempotent).

The covering index `idx_outbox_due (status, next_attempt_at)` (migration
`0011_outbox_retry_backoff`) backs the claim.

---

## 8. AI-Assisted Communications

Allowed:

- Draft email copy for admin review.
- Suggest concise rejection/interview/offer wording.
- Generate bilingual template draft from a structured brief.
- Summarize weekly digest from aggregate data.

Not allowed:

- Auto-send AI-generated message without human/admin confirmation.
- Include sensitive student data beyond the approved template variables.
- Generate discriminatory or biased hiring language.
- Expose provider/model/token/prompt details.

---

## 9. UX Quality

- Bell center groups by Today / Yesterday / Older.
- Notification row has icon, title, concise body, timestamp, unread marker, and action.
- Email templates must preview desktop/mobile email width.
- Push messages must avoid PII in title/body because they can appear on lock screens.
- Admin template editor should use drag/drop sections plus variable chips, not raw HTML editing only.
