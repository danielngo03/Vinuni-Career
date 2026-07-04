# Business Logic — VinUni Career Platform

> Phiên bản: 1.0 | Cập nhật: 26/06/2026
> File này document tất cả deep business rules, edge cases, proration logic, quota management, và financial flows.
> Mọi developer/agent PHẢI đọc file này trước khi implement bất kỳ feature liên quan đến billing, quota, pipeline, hoặc events.

---

## 1. Subscription & Billing (Proration)

### 1.1 Core Principle

> **Người dùng không bao giờ mất tiền khi nâng cấp.** Credit phần chưa dùng → trừ vào gói mới.

### 1.2 Upgrade Proration (Student & Partner)

```
Công thức:
  remaining_days = billing_end_date - today
  total_days = billing_end_date - billing_start_date
  credit = (remaining_days / total_days) × current_package_price
  amount_to_pay = new_package_price - credit

Ví dụ:
  Package A = 300,000₫/tháng (30 ngày)
  Đã dùng 10 ngày → còn 20 ngày
  Credit = (20/30) × 300,000 = 200,000₫
  Package B = 600,000₫/tháng
  Cần trả = 600,000 - 200,000 = 400,000₫
  → Chu kỳ mới bắt đầu từ hôm nay, hết hạn sau 30 ngày

Edge cases:
  - credit > new_package_price → user trả 0₫, và credit dư được store cho kỳ tiếp theo
  - credit < 0 không xảy ra (credit chỉ từ paid packages)
  - Same-day upgrade: credit = 0 (đã dùng đủ ngày đầu tiên)
  - Free plan → Paid: không có credit, trả full price
```

```python
# Backend implementation
def calculate_proration(
    current_package: Package,
    new_package: Package,
    subscription: Subscription,
    today: date
) -> ProrationResult:
    remaining_days = (subscription.billing_end - today).days
    total_days = (subscription.billing_end - subscription.billing_start).days
    credit = Decimal(remaining_days) / Decimal(total_days) * current_package.price
    amount_due = max(Decimal(0), new_package.price - credit)
    credit_balance = max(Decimal(0), credit - new_package.price)
    return ProrationResult(
        credit=credit,
        amount_due=amount_due,
        credit_balance=credit_balance,  # carry forward nếu credit > new price
        new_billing_start=today,
        new_billing_end=today + timedelta(days=30)
    )
```

**UI hiển thị cho user trước khi confirm:**
```
Gói hiện tại: Premium 300,000₫/tháng (còn 20 ngày)
Credit nhận được: 200,000₫

Gói mới: Pro 600,000₫/tháng
Bạn cần trả ngay: 400,000₫
Chu kỳ mới: 26/06/2026 → 26/07/2026

[Huỷ]  [Xác nhận nâng cấp & Thanh toán 400,000₫]
```

### 1.3 Downgrade Rules

- **Downgrade KHÔNG có refund ngay** — hiệu lực từ đầu chu kỳ tiếp theo
- User giữ toàn bộ quyền lợi gói cũ đến hết ngày `billing_end`
- Scheduled downgrade được lưu vào `pending_downgrade_to` field
- Ngày `billing_end`: trigger Celery task → switch package → send email "Gói của bạn đã được điều chỉnh"

```python
class Subscription(Base):
    id: UUID
    user_id: UUID
    package_id: UUID
    status: Literal["ACTIVE", "CANCELLED", "EXPIRED"]
    billing_start: date
    billing_end: date
    pending_downgrade_to: UUID | None    # scheduled downgrade
    cancelled_at: datetime | None        # set when user cancels
    cancel_at_period_end: bool = False   # True = active until billing_end, then cancel
```

### 1.4 Cancellation Policy

```
Trường hợp 1: Trong 7 ngày đầu VÀ chưa dùng quota
  → Hoàn tiền 100% (tự động sau khi verify)
  → Deactivate immediately

Trường hợp 2: Sau 7 ngày HOẶC đã dùng ≥ 1 quota unit
  → Không hoàn tiền
  → Access đến hết billing_end
  → cancel_at_period_end = True

Trường hợp 3: Admin-initiated cancellation (vi phạm TOS)
  → Không hoàn tiền
  → Immediate revocation
  → Email notification với lý do
```

### 1.5 Payment Failure & Grace Period

```
Day 0:  Payment fails (billing_end reached)
Day 0:  Retry immediately once
Day 1:  Retry + email warning "Thanh toán thất bại"
Day 3:  Retry + email "Tài khoản sẽ bị hạn chế sau 24h"
Day 4:  Downgrade to Free plan (Grace period expired)
        Preserve data (jobs, CVs, etc.) — only remove premium features
Day 30: If still unpaid → send final notice
Day 60: Archive account (configurable by admin)
```

### 1.6 Quota Management

**Quota được track độc lập với proration:**

```python
class QuotaUsage(Base):
    id: UUID
    subscription_id: UUID
    quota_type: str         # "job_post", "passive_search", "email_blast", "spotlight"
    used: int               # current usage this period
    limit: int              # from package definition
    period_start: date
    period_end: date        # resets at billing cycle
    carryover: int = 0      # unused quota from previous period (if policy allows)
```

**Quota reset rules:**
- `job_post`: resets monthly (không carry over — "use it or lose it")
- `passive_search`: resets monthly (không carry over)
- `spotlight_slots`: do NOT reset — consumed permanently when used
- `ai_credits` (student): KHÔNG reset — accumulated, carry over
- `email_blast`: resets monthly

**On upgrade:**
```
  job_post quota: reset đến new_package.job_post_quota (fresh start ngay lập tức)
  spotlight_slots: add new_package.spotlight_slots ON TOP of current remaining
  passive_search: reset đến new_package.passive_search_quota
  ai_credits: keep ALL existing + add new_package.ai_credits
```

**Quota enforcement:**
```python
# At service layer, before any quota-consuming action
async def check_and_consume_quota(
    org_id: UUID,
    quota_type: str,
    amount: int = 1
) -> None:
    usage = await quota_repo.get_current_usage(org_id, quota_type)
    if usage.used + amount > usage.limit + usage.carryover:
        raise QuotaExceededException(
            quota_type=quota_type,
            current=usage.used,
            limit=usage.limit,
            upgrade_url="/billing"
        )
    await quota_repo.increment(org_id, quota_type, amount)
```

**User-facing quota warning (at 80%):**
```
Email: "Bạn đã sử dụng 8/10 lượt đăng tin. Nâng cấp để không bị gián đoạn."
In-app: amber banner với progress bar + upgrade CTA
```

---

## 2. Partner Package & Job Posting Logic

### 2.1 Package-gated Features

```python
class PartnerPackage(Base):
    name: str
    price_monthly: Decimal
    price_annual: Decimal                # discount applied
    job_post_quota: int                  # per month (-1 = unlimited)
    featured_job_slots: int              # per month
    passive_search_quota: int            # profile views per month
    email_blast_quota: int               # sends per month
    spotlight_banner: bool               # homepage banner allowed
    analytics_level: str                 # "basic" | "advanced" | "enterprise"
    api_access: bool
    dedicated_support: bool
    pipeline_templates: int              # max saved templates (-1 = unlimited)
    max_team_members: int                # (-1 = unlimited)
    cv_download_watermark: bool = True   # ALWAYS True, non-configurable
```

### 2.2 Job Auto-close Logic

```
Triggers (ANY of these closes job automatically):
  - deadline_date reached AND no manual extension
  - application_quota reached (if set by partner)
  - Partner explicitly closes
  - University suspends partner
  - Job violates policy (moderation rejection after approval)

On auto-close:
  1. status = CLOSED
  2. Job removed from public listings
  3. Active applications continue through pipeline (not terminated)
  4. Email to partner: "Tin tuyển dụng [X] đã đóng"
  5. Students with saved job: notification "Tin đã đóng"
```

### 2.3 Annual Billing Discount

```
Annual pricing = monthly × 12 × (1 - discount_rate)
University admin sets discount_rate per package (e.g., 20%)

Proration for annual: same formula but total_days = 365
Downgrade from annual: no refund — keeps annual until expiry
```

---

## 3. Multi-round Pipeline Engine — Deep Logic

### 3.1 Required Action Enforcement

```python
class StageRequiredAction(str, Enum):
    SCORECARD = "scorecard"          # All assigned interviewers must submit scorecard
    SCORE_THRESHOLD = "score_threshold"  # Average score must reach threshold
    MANUAL = "manual"                # Manual advance only (no automation)

async def can_advance(application_id: UUID, current_stage_id: UUID) -> AdvanceCheck:
    stage = await get_stage(current_stage_id)

    if stage.required_action == StageRequiredAction.SCORECARD:
        submitted = await count_submitted_scorecards(application_id, current_stage_id)
        required = await count_required_evaluators(stage)
        return AdvanceCheck(allowed=submitted >= required, reason=f"{submitted}/{required} scorecards")

    elif stage.required_action == StageRequiredAction.SCORE_THRESHOLD:
        avg_score = await calc_average_score(application_id, current_stage_id)
        return AdvanceCheck(allowed=avg_score >= stage.score_threshold, reason=f"Score {avg_score}/{stage.score_threshold}")

    elif stage.required_action == StageRequiredAction.MANUAL:
        return AdvanceCheck(allowed=True, reason="Manual advance")
```

### 3.2 SLA Calculation

```
SLA được tính theo giờ làm việc (business hours) — mặc định 09:00-18:00 Thứ 2-6

Ví dụ:
  Candidate enters stage at Friday 17:00
  SLA = 24 business hours
  → 1 hour remaining Friday (17:00-18:00)
  → 8 hours Monday
  → 8 hours Tuesday
  → 7 hours Wednesday = 24 hours
  → SLA deadline = Wednesday 16:00

Nếu partner muốn calendar hours → toggle "Calendar hours" trong settings

SLA states:
  > 50% remaining time: NORMAL (gray)
  20-50% remaining:      WARNING (amber)
  < 20% remaining:       OVERDUE_SOON (amber bold)
  0% remaining (expired):OVERDUE (red, alert sent)
```

### 3.3 Auto-advance Rules

```
Auto-advance chỉ khi TẤT CẢ:
  1. required_action đã hoàn thành
  2. auto_advance = True trên stage config
  3. Candidate không ở trạng thái REJECTED/ROLLED_BACK
  4. Next stage tồn tại (không phải final stage)

Auto-advance KHÔNG kích hoạt khi:
  - Current stage là final stage → cần manual decision (offer/reject)
  - Required action = MANUAL (no auto for manual stages)
  - SLA expired nhưng action chưa done (alert instead)

Auto-advance Celery task: runs every 5 minutes
  → Query CandidateStages WHERE status=ACTIVE AND auto_advance=true
  → Check each if can_advance()
  → If yes: advance + send notifications
```

### 3.4 Parallel Scorecard (Multiple Interviewers)

```
Stage assignee mode = DEPARTMENT:
  → All members of department được assigned
  → can_advance khi: submitted scorecards / total_dept_members >= threshold_pct
  → Default threshold: 1.0 (100% phải submit)
  → Admin có thể set: "Chỉ cần 2/3 phỏng vấn viên"

Stage assignee mode = PERSON (specific):
  → Chỉ người được assign
  → can_advance khi người đó submit

Scorecard aggregation:
  → Individual scores stored per evaluator
  → Display: individual + average
  → Visibility: other interviewers see scores only AFTER submitting own scorecard
    (prevent anchoring bias)
```

### 3.5 Rollback Rules & Audit

```
Rules:
  - Rollback chỉ được về stages đã qua (không nhảy sang stage khác pipeline)
  - Reason minimum 20 characters (enforced at API + UI)
  - Rollback tạo CandidateStage record mới với status=ACTIVE tại target stage
  - Previous ACTIVE record → status=ROLLED_BACK

Limit:
  - Max 3 rollbacks cho cùng 1 candidate trong cùng 1 job (chống lạm dụng)
  - Lần thứ 4 cần university admin approval

Audit log per rollback:
  - actor_id, from_stage_id, to_stage_id, reason, timestamp
  - Visible trong pipeline audit trail (partner admin only)
```

### 3.6 Bulk Actions Limits

```
Max candidates per bulk action: 50
Bulk reject: requires single reason (applied to all)
Bulk advance: only if ALL candidates in selection have completed required_action
  → Partial: skip those who haven't, show warning "3/10 candidates cannot advance"
Rate limit: max 200 bulk actions per partner per day
```

---

## 4. Anonymous Apply — Deep Logic

### 4.1 What Gets Hidden

```python
# University admin configures globally (can be overridden per job level)
class AnonymousApplyConfig(Base):
    # Fields that CAN be configured as hidden
    hide_full_name: bool = True
    hide_email: bool = True
    hide_phone: bool = True
    hide_student_id: bool = True
    hide_photo: bool = True
    hide_date_of_birth: bool = False    # Usually keep for eligibility
    hide_address: bool = False
    hide_gender: bool = True
    hide_id_number: bool = True         # CCCD

# Fields that can NEVER be hidden (system-enforced)
ALWAYS_VISIBLE = [
    "skills",
    "education_level",
    "work_experience_summary",  # anonymized text
    "cv_content",               # full CV text MINUS PII
    "application_answers",      # custom questions
]
```

### 4.2 CV PII Stripping

```
Khi anonymous apply, trước khi partner xem CV:
  1. Extract CV text
  2. AI PII detection → identify name, phone, email, address, social links
  3. Replace with [REDACTED] or generalized text
  4. Partner sees: redacted CV preview (PDF view unavailable until reveal accepted)
  5. Partner can see: full-text CV content (stripped of PII)
```

### 4.3 Reveal Request Flow

```
Partner → click "Yêu cầu xem thông tin" → form:
  - Reason (required, min 20 chars)
  - [Gửi yêu cầu]

Student receives:
  Notification: "Công ty [X] muốn xem thông tin đầy đủ của bạn"
  Detail: show reason from partner
  Action: [Chấp nhận] [Từ chối]
  Deadline: student has 72h to respond
    → No response after 72h = auto-declined

On acceptance:
  - Partner sees full profile + can download CV (with watermark)
  - Student notified: "Bạn đã chấp nhận yêu cầu từ [Company X]"
  - Audit log: request_id, partner_id, student_id, reason, decision, timestamp

Rules:
  - Partner can only send 1 reveal request per application
  - Student cannot undo acceptance (design: show clear consequences before confirming)
  - Reveal is for THIS application only — not blanket across all jobs from that partner
```

### 4.4 Anti-gaming Rules

```
- Partner cannot filter applications by "anonymous" vs "named" in search
  (would defeat the purpose)
- Partner cannot see application timestamp distribution patterns to infer identity
- If only 1 application to a job → anonymous still preserved (no inference attack)
- Export: anonymous fields export as "[Ẩn danh]" (not blank — blank could be inferred)
```

---

## 4B. CV Studio — Deep Logic

### 4B.1 Creation Modes

```
Supported CV creation modes:
  blank_template:
    Student selects template and fills sections manually.

  confirmed_facts_import:
    System pre-fills only facts/preferences the student explicitly confirmed.
    This is optional; it must not become a required profile wizard.

  uploaded_import:
    Student uploads existing CV → extraction → review → import into selected template.

  duplicate_existing:
    Student duplicates an existing builder CV, optionally changes template and target role.

  ai_assisted_draft:
    AI fills/drafts template from permitted sources, but writes only a pending diff/draft.
```

Rules:

- Manual template creation is available to every student for at least one active CV.
- CV Studio is CV-first: students can upload a CV, choose a template, duplicate a
  CV, or ask AI to draft from raw notes without completing education/experience
  in a separate profile form first.
- Uploaded CV originals are retained as immutable documents; template CVs are structured editable records.
- Importing from uploaded CV extraction requires student review before content becomes part of a builder CV.
- Duplicate existing CV creates a new `cv_profiles` record and initial `cv_versions` snapshot; the source CV is never mutated.
- Changing a template re-renders the same structured content; it must not delete sections unless the student explicitly confirms hidden/unsupported sections.
- Profile data can support CVs only as confirmed facts, career preferences,
  privacy settings, and notification/security settings.

### 4B.2 Versioning, Snapshots, And Application Integrity

```
On meaningful CV save:
  1. Validate section schema.
  2. Update cv_sections.
  3. Create cv_versions snapshot.
  4. Emit audit event.

On application submit:
  1. Resolve selected uploaded CV or builder CV version.
  2. Create Application.
  3. Create application_cv_snapshots.
  4. Run anonymous redaction if needed.
```

Rules:

- Application CV snapshots are immutable.
- Later CV edits do not update submitted applications.
- Restoring a version creates a new version with `change_source = restore`; it does not reuse old version numbers.
- Setting primary CV is a write action and is audited.
- Archiving a CV is allowed even if it was used before, because applications retain snapshots.

### 4B.3 AI-Assisted CV Rules

- AI can fill a selected template from uploaded extraction, existing CV, student
  raw notes, and confirmed profile facts.
- AI output is a pending `cv_ai_suggestions` diff/draft until accepted.
- AI cannot silently overwrite manual text.
- AI cannot invent education, employer, GPA, certification, award, dates, or quantified outcomes.
- Unsupported claims are labeled `requires_fact_confirmation` and must be edited or confirmed by the student before acceptance.
- AI suggestions consume credits only after successful generation.
- Regenerating an AI suggestion replaces only the pending suggestion, never accepted CV content.
- Job-tailored optimization should suggest ordering, wording, and true evidence gaps; it must not fabricate missing skills.

### 4B.3B CV-To-Job Fit And CV Recommendation

When a student views a job or starts applying:

1. Load active eligible CV library items.
2. Exclude archived/deleted CVs and failed uploads.
3. Warn if a CV is stale (default: not updated in 60 days).
4. Score each CV 0-100 using deterministic skill/JD/category matching first.
5. Let AI add explanation and improvement suggestions only after base scoring is
   available and permission/safety checks pass.
6. Recommend the best CV, but allow the student to override.
7. Application submit stores the selected CV snapshot exactly as submitted.

Score categories:

- required skills;
- nice-to-have skills;
- education/eligibility;
- experience/project evidence;
- language/location/work-mode fit;
- CV quality/staleness.

User-facing score is a product score, not raw confidence/similarity. Internal
model confidence, embedding similarity, provider names, token counts, and prompt
details are never shown. Missing evidence is phrased as "if true, add evidence"
or as learning/job-search advice; the system never suggests fabricating facts.

### 4B.3A Upload Validation And Parse Failure Rules

```
Upload processing order:
  1. MIME/extension sniff
  2. checksum duplicate detection
  3. virus scan
  4. native text extraction
  5. OCR fallback only if native text is empty/low quality
  6. CV classifier
  7. minimum content validation
  8. review/import decision
```

Rules:

- Unsupported, infected, corrupt, password-protected, blank, non-CV, and low-quality files do not become import sources.
- Blank PDF = no extracted text and OCR text below threshold across inspected pages.
- Not-CV = document lacks CV signals such as education, skills, experience, projects, certifications, contact/header information.
- Low-quality scan = OCR returns noisy text or too little reliable content.
- Duplicate upload = same `checksum_sha256` for same user and non-deleted document; return existing document option.
- Validation failures before AI generation do not consume AI credits.
- AI structuring must not run for `NOT_A_CV`, `BLANK_DOCUMENT`, `FILE_REJECTED_SECURITY`, or `CORRUPT_FILE`.
- Low confidence extraction becomes `REVIEW_REQUIRED`; student must review field-by-field before import.
- Internal parser error/confidence is not exposed to end users.

### 4B.4 Quota Defaults

```
VinUni student default:
  active_cv_library_items: 5
  pdf_exports/month:  3
  ai_cv_actions:      credit-based

Suggested external/basic default:
  active_cv_library_items: 3
  pdf_exports/month:  1
  ai_cv_actions:      credit-based

Suggested premium/approved override:
  active_cv_library_items: 10
  pdf_exports/month:  50
  premium_templates:  enabled
```

Active CV library items include usable uploaded originals and builder/template
CVs selectable for applications. Archived CVs and immutable application
snapshots do not count. Quotas are enforced in the service layer, not only in UI.
University admin can tune limits per package/tier.

---

## 5. Job Visibility — Enforcement Matrix

```
Visibility Level     Guest   General  External  Alumni  VinUni Student  Invited
────────────────────────────────────────────────────────────────────────────────
1. Public            ✓       ✓        ✓         ✓       ✓               ✓
2. Authenticated     ✗       ✓        ✓         ✓       ✓               ✓
3. Students Only     ✗       ✗        ✓         ✓       ✓               ✓
4. VinUni Only       ✗       ✗        ✗         ✗       ✓               ✓
5. Invitation Only   ✗       ✗        ✗         ✗       ✗               ✓ (if invited)

Rules:
  - Visibility enforced at DB query level (NOT just frontend hide)
  - API returns 404 (not 403) for unauthorized job detail — to prevent enumeration
  - Job appears in search listing ONLY if user's tier qualifies
  - Pagination is tier-aware (job count reflects what user can see)
  - Invitation Only: partner manually adds user emails/IDs to allowed list
  - Invited user can still see even if their tier wouldn't normally qualify
```

---

## 6. Events System — Deep Logic

### 6.1 Ticket Pricing Rules

```python
class TicketType(Base):
    event_id: UUID
    name: str
    base_price: Decimal
    early_bird_price: Decimal | None
    early_bird_until: datetime | None
    capacity: int
    available: int               # maintained in real-time
    eligibility_tiers: list[str] # which user tiers can purchase
    min_purchase: int = 1
    max_purchase: int = 1        # per user per ticket type
    sale_start: datetime | None
    sale_end: datetime | None
    transfer_allowed: bool
    refund_policy: RefundPolicy

def get_effective_price(ticket_type: TicketType, now: datetime) -> Decimal:
    if (ticket_type.early_bird_price and
        ticket_type.early_bird_until and
        now < ticket_type.early_bird_until):
        return ticket_type.early_bird_price
    return ticket_type.base_price
```

### 6.2 Promo Code Logic

```python
class PromoCode(Base):
    code: str
    discount_type: Literal["PERCENT", "FIXED"]  # % or ₫
    discount_value: Decimal
    min_order_value: Decimal | None
    max_uses: int                 # total across all users
    max_uses_per_user: int = 1
    valid_from: datetime
    valid_until: datetime
    applicable_ticket_type_ids: list[UUID] | None  # None = all tickets

def apply_promo(subtotal: Decimal, promo: PromoCode) -> Decimal:
    if promo.discount_type == "PERCENT":
        discount = subtotal * (promo.discount_value / 100)
    else:
        discount = promo.discount_value
    return max(Decimal(0), subtotal - discount)  # never negative
```

### 6.3 Seat Lock Concurrency

```
Problem: 2 users click same seat simultaneously

Solution (Redis atomic NX):
  User A: SET seat_lock:{seat_id} {user_a_id} EX 600 NX
    → Returns OK (User A got the lock)
  User B: SET seat_lock:{seat_id} {user_b_id} EX 600 NX
    → Returns NIL (seat already locked)
    → UI: "Ghế này vừa được người khác chọn. Vui lòng chọn ghế khác."

Lock extension:
  Every 60s while user is in checkout, extend lock:
  EXPIRE seat_lock:{seat_id} 600
  If user loses connection → lock expires → seat released

Permanent booking:
  After payment confirmed:
  DEL seat_lock:{seat_id}
  UPDATE seats SET status='BOOKED', booked_by={user_id}, booked_at=NOW()

Database UNIQUE constraint as final safety net:
  UNIQUE (event_id, seat_id, registration_id) — prevents double-booking at DB level
```

### 6.4 Waitlist Promotion

```
Automatic promotion trigger: when registration is CANCELLED or EXPIRED

Priority order for promotion:
  1. Waitlist signup timestamp (FIFO — first come, first served)
  2. Exception: higher-tier users can be promoted ahead if event has "tier_priority" flag

Promotion process:
  1. Seat freed → Celery task triggered immediately
  2. Find next waitlisted registration (highest priority)
  3. Send email: "Có chỗ trống! Bạn có 2 giờ để xác nhận"
  4. If paid ticket: send payment link (2-hour expiry)
  5. After 2h: if not confirmed → promote next on waitlist
  6. On confirm: issue QR, send ticket email

Rules:
  - Waitlist notification expires in 2h (to prevent indefinite holds)
  - Max 3 promotion attempts per person (prevent gaming)
  - Waitlist position visible to user: "Bạn đang ở vị trí #15 trong danh sách chờ"
```

### 6.5 Online Link Security

```
Online link encrypted at rest (AES-256)
Access conditions (ALL must be true):
  1. Registration exists for this user + event
  2. Registration.status = CONFIRMED (not PENDING_PAYMENT)
  3. Event.start_time - 24h <= now <= Event.end_time + 2h
  4. User is the registered user (not shareable URL)

Link reveal mechanism:
  Client requests: GET /events/{id}/online-link
  Server: decrypt + generate time-limited signed URL (15 min expiry)
  URL contains: base_url + signature(user_id + event_id + timestamp)

Sharing prevention:
  Signed URL is non-transferable (bound to session IP, rough geolocation)
  Too many IP hops → revoke + flag for review
```

### 6.6 Refund Policy Enforcement

```python
class RefundPolicy(str, Enum):
    NO_REFUND = "no_refund"
    FULL_UNTIL = "full_until"        # full refund if cancelled before date
    PARTIAL_UNTIL = "partial_until"  # partial until date, then no refund

class RegistrationCancellation:
    def calculate_refund(self, registration: Registration, now: datetime) -> Decimal:
        policy = registration.ticket_type.refund_policy
        ticket_price = registration.amount_paid

        if policy.type == RefundPolicy.NO_REFUND:
            return Decimal(0)

        elif policy.type == RefundPolicy.FULL_UNTIL:
            if now <= policy.full_refund_until:
                return ticket_price
            return Decimal(0)

        elif policy.type == RefundPolicy.PARTIAL_UNTIL:
            if now <= policy.full_refund_until:
                return ticket_price
            elif now <= policy.partial_refund_until:
                partial_pct = policy.partial_refund_percentage / 100
                return (ticket_price * partial_pct).quantize(Decimal("0.01"))
            return Decimal(0)
```

---

## 7. Company Reviews — Deep Logic

### 7.1 Eligibility Verification

```
Eligible to review IF at least ONE of:
  a. application.status was ever "INTERVIEW" or further with this company
  b. application.status was "OFFER" or "ACCEPTED" with this company
  c. Student self-declares employment (low trust) → marked as "Tự khai báo"
  d. Partner confirms employment (high trust) → marked as "Đã xác minh"

Trust levels:
  "Ứng viên đã phỏng vấn": medium trust (system-verified)
  "Nhân viên tự khai báo": low trust (visible to readers)
  "Nhân viên đã xác minh": high trust (partner confirmed)
```

### 7.2 Review Rating Categories

```python
class ReviewRating(Base):
    review_id: UUID
    overall: int               # 1-5 stars
    work_life_balance: int     # 1-5
    culture_values: int        # 1-5
    compensation: int          # 1-5
    career_growth: int         # 1-5
    interview_experience: int  # 1-5 (for interview-only reviewers)

def calculate_company_score(reviews: list[ReviewRating]) -> CompanyScore:
    weights = {
        "work_life_balance": 0.20,
        "culture_values": 0.25,
        "compensation": 0.30,
        "career_growth": 0.25,
    }
    # Weighted average for each category
    # Overall = weighted sum of all categories
    # Bayesian average (avoids extreme scores with few reviews):
    # score = (n × avg + 3 × 3.0) / (n + 3)  where 3.0 = global prior mean
```

### 7.3 Review Moderation Pipeline

> **Phased transition (ADR-0013).** The auto-publish model below is the END state,
> and it is safe *only because the AI scan is the gate*. AI moderation (B-343) is
> Phase-3 and currently resource-BLOCKED (no AI provider key). The shipped slice-1
> therefore uses **PRE-moderation**: a new review is `pending` and is NOT public
> until a university moderator publishes it (no `publish_after`, no AI scan). When
> B-343 lands, the system flips to the auto-publish + AI-scan pipeline described
> here. Everything else below (report→flag, removal criteria, human final say,
> partners-report-not-remove) already holds in slice-1.

```
New review submitted (auto-publish model — activates with AI moderation B-343):
  1. AI scan: detect profanity, PII, discrimination → auto-flag
  2. If flagged: queue for human review (SLA: 24h)
  3. If clean: auto-publish after 2h delay (catch last-minute flags)

Slice-1 (shipped, pre-moderation, no AI yet):
  1. New review stored as `pending` — not public
  2. University moderator publishes (→ public) or removes (policy-gated)

After published:
  Partner can "report review" → queue for human review
  Human moderator: approve / remove / request edit from reviewer

Removal criteria (university policy):
  - Contains PII (names of individuals)
  - Factually verifiable false claims about specific people
  - Harassment, threats
  - Spam / competitor sabotage

Review cannot be removed for:
  - Negative (but genuine) opinions
  - Low star ratings without explanation
  - Criticism of company policies/culture
```

---

## 8. Passive Talent Search — Anti-spam & Privacy

### 8.1 Quota & Rate Limiting

```python
class PassiveSearchQuota(Base):
    partner_id: UUID
    date: date
    contact_requests_sent: int
    contact_requests_limit: int     # from university config (default: 10/day)
    week_start: date
    weekly_requests_sent: int
    weekly_requests_limit: int      # default: 30/week
    monthly_requests_sent: int
    monthly_requests_limit: int     # = package.passive_search_quota

def can_send_contact_request(partner_id: UUID) -> QuotaCheck:
    quota = get_quota(partner_id, today)
    return QuotaCheck(
        allowed=(
            quota.contact_requests_sent < quota.contact_requests_limit
            and quota.weekly_requests_sent < quota.weekly_requests_limit
            and quota.monthly_requests_sent < quota.monthly_requests_limit
        ),
        daily_remaining=quota.contact_requests_limit - quota.contact_requests_sent,
        weekly_remaining=quota.weekly_requests_limit - quota.weekly_requests_sent,
    )
```

### 8.2 Anonymization Spec

```python
def anonymize_profile(profile: StudentProfile, partner_id: UUID) -> AnonymizedProfile:
    # Check if contact request was accepted for this partner-student pair
    is_revealed = check_reveal_accepted(partner_id, profile.student_id)

    if is_revealed:
        return profile  # full profile

    return AnonymizedProfile(
        display_name=f"Sinh viên #{generate_anonymous_id(profile.student_id, partner_id)}",
        # Deterministic but unguessable — same partner always sees same ID for same student
        photo=AVATAR_PLACEHOLDER,
        email=None,
        phone=None,
        student_id=None,
        education=[{
            "institution": profile.education[0].institution,  # keep school name
            "degree": profile.education[0].degree,
            "major": profile.education[0].major,
            "graduation_year": profile.education[0].graduation_year,
            # No GPA unless partner package includes it
        }],
        skills=profile.skills,        # skills always visible (purpose of search)
        experience_summary=profile.experience_summary,  # anonymized: no company names
        availability=profile.availability,
    )
```

**Note:** Cùng 1 student sẽ có cùng anonymous ID với cùng partner (deterministic hash), nhưng khác partner thì khác ID. Điều này prevent cross-partner identity linking.

---

## 9. Advertising System — Business Rules

### 9.1 Ad Pricing Model

```python
class AdCampaign(Base):
    campaign_type: Literal["CPM", "CPC", "FIXED"]
    # CPM: cost per 1000 impressions
    # CPC: cost per click
    # FIXED: flat fee for time period

    bid_amount: Decimal             # per 1000 impressions or per click
    daily_budget: Decimal           # max spend per day
    total_budget: Decimal           # max total spend

    # Budget enforcement (real-time):
    # When daily_spent >= daily_budget → pause campaign for today
    # When total_spent >= total_budget → end campaign
```

### 9.2 Targeting Rules (STRICT — legal compliance)

```
ALLOWED targeting dimensions:
  ✓ user_tier (VinUni Student, Alumni, External, General)
  ✓ interest_tags (self-declared career interests)
  ✓ graduation_year (approximate cohort)
  ✓ industry_interest (self-declared)
  ✓ job_category_interest (inferred from browsing, aggregate only)
  ✓ event_attendance_history (has attended X types of events)
  ✓ device_type (mobile vs desktop)

FORBIDDEN targeting dimensions (system-enforced, UI blocks these):
  ✗ name, email, phone (PII)
  ✗ health data
  ✗ religious affiliation
  ✗ political views
  ✗ ethnicity or national origin
  ✗ gender or sexual orientation
  ✗ disability status
  ✗ pregnancy status
  ✗ financial status (beyond broad "student" category)
  ✗ exact location (only city-level allowed)

Implementation:
  Ad targeting form: forbidden dimensions not in select options at all
  API: TargetingValidator rejects requests with forbidden fields
  Audit: every targeting config saved for compliance review
```

### 9.3 Ad Approval Workflow

```
Partner submits campaign → PENDING_REVIEW
University moderator reviews:
  - Creative (image/copy) for TOS compliance
  - Targeting config for forbidden dimensions
  - Budget (minimum 500,000₫ campaign to reduce spam)
Approve → ACTIVE (starts on scheduled date)
Reject → REJECTED with reason (partner can revise + resubmit)
SLA: university review within 24h (business hours)

Post-approval monitoring:
  AI scans running ads weekly for policy drift
  User "Tại sao tôi thấy quảng cáo này?" → logs complaint
  >5 complaints per campaign → flag for re-review
```

---

## 10. AI Credit System (Student Subscriptions)

### 10.1 Credit-based AI Features

```python
class AICreditCost(int, Enum):
    CHAT_MESSAGE = 1           # basic AI chat message
    CV_ANALYSIS = 5            # full CV analysis
    CV_TEMPLATE_FILL = 6       # fill selected template from sources
    CV_BULLET_GENERATION = 2   # generate bullets for one section
    CV_SECTION_REWRITE = 2     # rewrite one section or bullet group
    CV_JOB_OPTIMIZATION = 5    # tailor suggestions for one job
    CV_FABRICATION_CHECK = 2   # claim/evidence consistency check
    JOB_MATCH_REPORT = 3       # detailed match report
    INTERVIEW_SIM_QUESTION = 2 # per question in simulator
    JD_INSIGHT = 2             # JD explanation
    CAREER_PATH_SIMULATION = 10 # full career simulation
    SALARY_BENCHMARKING = 3

class StudentAICredits(Base):
    student_id: UUID
    balance: int               # total credits available
    lifetime_earned: int       # cumulative
    last_refreshed: datetime   # when monthly grant was applied

# Monthly credit grants by tier (free):
TIER_MONTHLY_CREDITS = {
    "vinuni_student": 50,   # generous free for VinUni students
    "alumni": 20,
    "external": 10,
    "general": 5,
}
# Paid subscription packs: add to balance (carry over)
```

### 10.2 Credit Enforcement

```python
async def consume_credits(student_id: UUID, cost: AICreditCost) -> None:
    async with db.begin():
        credits = await db.get(StudentAICredits, student_id, with_lock=True)
        if credits.balance < cost:
            raise InsufficientCreditsError(
                current=credits.balance,
                required=cost,
                upgrade_url="/subscriptions"
            )
        credits.balance -= cost
        await db.flush()

# Never let balance go negative — "fail open" vs "fail closed" decision:
# We fail closed: no credits = no AI action (not silent failure)
```

---

## 11. Content Moderation SLA

```
Content Type          Auto-hold?  SLA (h)  Escalation
────────────────────────────────────────────────────────
Partner registration  Yes (review) 48      Legal team if flagged
Job posting           Yes          24      Admin lead if >24h
Event (partner)       Yes          24      Event team
Ad creative           Yes          24      Marketing team
Company review        No (live)    24*     *If reported
Content report        No (live)    6       Immediate if severity=HIGH
AI-flagged content    Yes          4       Auto-escalate if AI confidence > 0.85

SLA clock:
  Starts: submission timestamp
  Pauses: weekends + holidays (configurable)
  Business hours: 08:00-18:00 Mon-Fri

SLA breach:
  > 2h before breach: email to moderator + Slack alert
  At breach: escalate to admin lead
  > 2h after breach: escalate to university management
```

---

## 12. Fraud Detection Rules

### 12.1 Fake Company Detection

```
Signals (scored 0-100):
  + Domain age < 6 months: +20
  + No LinkedIn/social presence: +15
  + Tax code format invalid: +40
  + Duplicate tax code (already registered): +80
  + Logo reverse-image matches known scam: +60
  + Contact email is free provider (gmail/yahoo): +10
  + Description copied from legitimate company: +30

Score thresholds:
  0-30:  AUTO-APPROVE (low risk)
  31-60: FLAG for human review + enhanced monitoring
  61-80: HOLD + notify admin (escalated review)
  80+:   AUTO-REJECT + ban IP + notify admin immediately

Human moderator always has override ability.
```

### 12.2 Fake Application Detection

```
Signals:
  + Same CV content submitted to 50+ jobs in 24h: BOT flag
  + Application from account created < 1h ago: SUSPICIOUS flag
  + Multiple applications from same IP different accounts: SUSPICIOUS
  + CV content identical to other CVs (>90% similarity): REVIEW flag
  + Application timing perfectly regular (e.g., every 30s): BOT flag

Actions:
  BOT flag: captcha required + rate limit (1 apply/hour)
  SUSPICIOUS: require email verification before apply
  REVIEW flag: notify partner, allow partner to flag
```

---

## 13. Career Outcomes — Data Accuracy Rules

```
Placement data trustworthiness levels:
  LEVEL 1 (highest): partner confirms employment (verified hire)
  LEVEL 2: student self-reports + LinkedIn cross-reference
  LEVEL 3: student self-reports (survey response)
  LEVEL 4: estimated from application → offer accepted flow

KPI calculations use:
  Numerator: LEVEL 1 + LEVEL 2 placements
  Denominator: ALL graduates in cohort with consent
  Denominator excludes: students pursuing further education, students who opted out

Salary data:
  Only use LEVEL 1 + LEVEL 2 sources
  Anonymize individual salaries in aggregate reports
  Minimum 5 data points per department for aggregate display (privacy protection)
  Below 5 data points: show range instead of average

Survey response rate target: ≥ 40% per cohort
  Below 30%: notify career center to do follow-up manually
```

---

## 14. Messaging Business Rules

### 14.1 Who Can Message Whom

```
University Admin/Staff → Bất kỳ user nào: ✓
Partner (Admin or Member) → Ứng viên trong active pipeline: ✓ (unlimited)
Partner (Admin or Member) → Ứng viên không có application: ✓ (max 3 msg/day)
Partner (Admin or Member) → Team member cùng org: ✓ (unlimited)
Student → University: ✓ (unlimited)
Student → Partner: ✓ CHỈ reply (không được initiate mới)
Student → Student: ✗ TUYỆT ĐỐI KHÔNG
```

### 14.2 Anti-spam Enforcement

```python
async def can_send_message(sender_id: UUID, receiver_id: UUID) -> MessagePermission:
    sender = await user_repo.get(sender_id)
    receiver = await user_repo.get(receiver_id)

    # Student → Student: always blocked
    if sender.role == "student" and receiver.role == "student":
        raise MessagePermissionError("Student to student messaging not allowed")

    # Partner → Student outside active application
    if sender.role == "partner_member" and receiver.role == "student":
        has_active_app = await application_repo.has_active_application(
            partner_id=sender.org_id, student_id=receiver.id
        )
        if not has_active_app:
            today_count = await message_repo.count_today(sender_id, receiver_id)
            if today_count >= 3:
                raise RateLimitError(
                    "Đã gửi tối đa 3 tin nhắn hôm nay cho ứng viên này",
                    reset_at=tomorrow_midnight()
                )

    return MessagePermission(allowed=True)
```

### 14.3 Message Retention & Deletion

```
Retention policy:
  Active conversations: indefinite (không tự xóa)
  Deleted conversation: soft delete, data retained 30 days then purged
  Admin can export conversation for compliance (university admin only)

Message deletion rules:
  Sender can delete own message within 10 minutes → "Tin nhắn đã bị xóa"
  University admin can delete any message (moderation)
  Partner cannot delete messages sent to students (audit integrity)
  System messages cannot be deleted
```

### 14.4 Broadcast Rules

```
University admin broadcast:
  Segments: "All Students" | "VinUni Students" | "Alumni" | "External" |
            "All Partners" | "Custom list (import CSV)"

Rate limit for broadcast: max 1 broadcast/hour per admin
Broadcast delivery: queued Celery task (không block request)
Broadcast tracking: sent count, delivered count (WebSocket), open rate (không available for system notifications)
```

---

## 15. Bulk Apply Business Rules

### 15.1 Weekly Quota

```python
WEEKLY_APPLY_QUOTA = {
    "vinuni_student": 20,
    "alumni": 10,
    "external": 5,
    "general": 3,
}

PAID_WEEKLY_QUOTA = {
    "basic":    30,   # per add-on pack
    "standard": 50,
    "premium":  None,  # unlimited
}

def get_weekly_limit(student: User) -> int:
    base = WEEKLY_APPLY_QUOTA.get(student.tier, 3)
    if student.subscription:
        return PAID_WEEKLY_QUOTA.get(student.subscription.pack_name, base)
    return base

# Quota resets every Monday 00:00 (Asia/Ho_Chi_Minh timezone)
# Unused quota does NOT carry over
```

### 15.2 Cover Letter Generation Rules

```
AI cover letter:
  Input: student CV text + JD text + company description (from profile)
  Output: ~200-300 words, Vietnamese or English (match JD language)
  Cost: 3 AI credits per generation
  Each generation is unique (AI temperature high enough to avoid duplicates)
  Student can regenerate (costs another 3 credits)
  Student can edit freely before applying

Quality rules:
  Must mention: candidate's specific skill relevant to role
  Must not: copy-paste generic content across jobs
  Must not: hallucinate credentials student doesn't have
  Reviewer output guardrail: check if mentions skills actually in student CV

Cover letter storage:
  Stored per (application_id) after apply
  Cart draft: stored as cart_cover_letter (overwritten each regeneration)
```

### 15.3 Bulk Apply Confirmation

```
Before bulk apply, confirm modal shows:
  - List of jobs (title + company)
  - Quota check: "3 applies sẽ được dùng (còn 17 lượt tuần này)"
  - Warning nếu CV chưa update trong 60 ngày
  - [Huỷ] [Ứng tuyển {N} việc làm]

After confirm:
  Each job creates individual Application record
  If any fails (quota exceeded mid-apply): partial apply, show which succeeded/failed
  Success: cart items move to Applications, cart cleared of applied jobs
```

---

## 16. Workflow Engine Business Rules

### 16.1 Execution Rules

```
Flow triggers:
  system.student_registered      → payload: { user_id, email, tier }
  system.application_submitted   → payload: { application_id, job_id, student_id }
  system.payment_received        → payload: { payment_id, order_id, amount }
  system.file_uploaded           → payload: { file_id, file_type, uploader_id }
  system.partner_registered      → payload: { partner_id, company_name }
  scheduler.cron                 → payload: { cron_expression, timestamp }

Idempotency: each trigger event + flow_id = unique execution
  If same trigger event fires twice (e.g., webhook retry): check existing execution → skip if RUNNING/COMPLETED

Node SLA (Human Review nodes):
  If human doesn't act within SLA → escalate to next-level admin
  Escalation: email + in-app notification + activity feed alert

Max concurrent executions per flow: 100
  Above 100: queue (FIFO, max 10,000 queue depth)
```

### 16.2 Variable Passing Between Nodes

```python
class FlowContext:
    trigger: dict          # original trigger payload
    variables: dict        # accumulated from node outputs

# Example: AI Process node output
ai_node_output = {
    "fraud_score": 0.75,
    "fraud_reasons": ["new_domain", "no_social_presence"],
    "recommendation": "review"
}
# Variables available in next nodes:
# {{fraud_score}}, {{fraud_reasons}}, {{recommendation}}

# Condition node evaluates:
# "{{fraud_score}} > 0.70" → true/false branch
```

---

## 17. Activity Audit Rules

### 17.1 What Gets Audited (mandatory — no exceptions)

```
CREATE operations: all (job, application, user, etc.)
UPDATE operations: all write endpoints
DELETE operations: all (soft or hard)
AI tool calls: all confirmed (mutating) tool calls
CV downloads: every download by partner
File access: any signed URL generation
Auth events: login, logout, failed login, password change
Permission changes: role assignment, permission grant/revoke
Payment events: charge, refund, subscription change
Broadcast messages sent
Workflow flow activation/deactivation
AI provider identity views: ai_settings.provider_identity_viewed (routing
  canvas raw provider/model identity reveal — requires
  ai_settings:view_provider_identity; see API_CONTRACTS.md ADR-0011.1)
```

### 17.2 Privacy in Audit Logs

```
What to store:
  ✓ actor_id (UUID)
  ✓ action type
  ✓ target entity + ID
  ✓ before/after state (JSON diff)
  ✓ IP address as SHA-256 hash
  ✓ timestamp

What NEVER to store:
  ✗ Raw IP address
  ✗ PII fields in payload (name, email, phone — store IDs only)
  ✗ AI prompt content
  ✗ CV raw text
  ✗ Password or token data
```

---

## 18. Document Knowledge Base Rules (M33)

### 18.1 Upload Permissions

```
Who can upload:
  University Admin (role: UNIVERSITY_ADMIN or STAFF with kb_manage permission)
    → uploads to Platform KB (scope = 'platform')
  Partner Admin (role: PARTNER_ADMIN within their organization)
    → uploads to Partner KB (scope = 'partner', owner = their org_id)
    → uploads to Per-Job KB (scope = 'job', owner = a job_id they own)

Who CANNOT upload:
  Students (NEVER — read access only via chatbot)
  Partner Staff without PARTNER_ADMIN role
  University Staff without kb_manage permission
```

### 18.2 File Validation Rules

```
Allowed MIME types:
  application/pdf
  application/vnd.openxmlformats-officedocument.wordprocessingml.document  (DOCX)
  text/plain  (TXT, UTF-8 only)

Reject if:
  - File size > 50 MB
  - MIME type not in allowed list (even if extension matches)
  - Virus scan returns any threat
  - Total org storage would exceed quota after this upload:
      Partner KB: 500 MB per org
      Platform KB: 5 GB total
  - Document count would exceed limit:
      Platform KB: 200 docs
      Partner KB: 50 docs per org
      Per-Job KB: 10 docs per job

On rejection: return 400 with human-readable reason, do NOT store any bytes.
```

### 18.3 Storage Quota Enforcement

```
Check quota BEFORE starting upload (not after):
  1. Query current total_size_bytes for the knowledge_base
  2. If total_size_bytes + incoming_size > quota → reject immediately
  3. On successful ingest: update knowledge_bases.total_size_bytes atomically

Soft quota warning at 80%: show banner in admin UI "Bạn đã dùng 80% dung lượng"
Hard quota at 100%: reject upload with code KB_QUOTA_EXCEEDED
```

### 18.4 Chunking Rules

```
Target chunk size: 512 tokens (±20% tolerance)
Overlap between consecutive chunks: 64 tokens
Chunk boundary preference:
  1. Paragraph boundary (double newline)
  2. Sentence boundary (period + space)
  3. Word boundary (never cut mid-word)
  4. Hard cut at 640 tokens if no boundary found

Each chunk metadata:
  - document_id
  - chunk_index (0-based)
  - section_heading (nearest H1/H2/H3 above this chunk, if detectable)
  - token_count (actual)

Max chunks per document: 500
If document would exceed 500 chunks after chunking:
  → Truncate at 500 chunks, mark document with truncation_warning = true
  → Admin UI shows: "Tài liệu bị cắt bớt ở chunk 500. Hãy tách thành nhiều file nhỏ hơn."
```

### 18.5 Access Control for RAG Queries

```
Platform KB:
  - Accessible by: all authenticated users (student, partner, staff)
  - NOT accessible by: guests (unauthenticated)

Partner KB:
  - Accessible by student IF:
      student has submitted at least 1 application to any job of that org
      OR student is currently viewing the company profile page (browsing access)
  - NOT accessible by: other partner orgs, unrelated students

Per-Job KB:
  - Accessible by student IF:
      student has an application to that job with status IN
      (SUBMITTED, UNDER_REVIEW, SHORTLISTED, INTERVIEW_SCHEDULED, OFFER_EXTENDED)
  - NOT accessible by: students who were REJECTED or WITHDRAWN
  - NOT accessible by: students who have not applied

Partner/university staff:
  - Always have access to KBs within their organization scope
```

### 18.6 Chatbot Answer Quality Rules

```
Minimum relevance threshold for chunk inclusion: cosine similarity ≥ 0.60
If no chunk exceeds threshold:
  → Do NOT hallucinate an answer
  → Return: "Tôi không tìm thấy thông tin về vấn đề này trong tài liệu hiện có.
             Bạn có thể liên hệ [org_name] trực tiếp để được hỗ trợ."

Citation format (mandatory per answer):
  → Inline: "Theo [Tên tài liệu]..."
  → Footer: "Nguồn: [Tên tài liệu], phần [section_heading]"
  → If multiple chunks from same doc: cite once with multiple sections
  → Never cite internal IDs, file paths, storage keys, or chunk indexes

Max chunks per RAG answer: 10 (to stay within context limits)
AI answer must be marked as KB-sourced in chat history metadata
```

### 18.7 Document Deletion Rules

```
When a document is deleted by admin:
  1. Mark document status = 'DELETED' (soft delete)
  2. Delete all child knowledge_base_chunks (CASCADE or batch job)
  3. Delete from object storage (schedule async, not inline)
  4. Update knowledge_bases.total_size_bytes and doc_count
  5. Audit log: actor, document_id, kb_id, deletion timestamp

Future queries no longer return chunks from deleted documents.
Embeddings of deleted docs are NOT kept in the vector index.

Bulk delete: allowed, applied atomically within a transaction.
```

### 18.8 Ingestion Failure Handling

```
Extraction failure (corrupt PDF, password-protected file, unsupported encoding):
  → Status = FAILED, error_message = human-readable reason
  → Do NOT retry automatically (user must re-upload a corrected file)
  → Show in admin UI: red status badge + error detail

Embedding failure (AI provider down):
  → Retry up to 3 times with exponential backoff (60s, 120s, 240s)
  → After 3 failures: status = FAILED, error_message = "Dịch vụ AI tạm thời không khả dụng. Vui lòng thử lại sau."
  → Alert university admin if >5 docs in FAILED state simultaneously

Virus scan failure:
  → Treat as threat (fail-secure): reject upload, status = FAILED
  → Log as potential threat, notify university admin
```
