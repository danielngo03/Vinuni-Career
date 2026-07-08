# Product Requirements Document
# VinUni Career Platform — AI-Powered Recruitment Ecosystem

**Phiên bản:** 5.0  
**Ngày:** 26/06/2026  
**Trạng thái:** Draft — chờ duyệt  
**Tác giả:** Product Team

---

## 1. Tầm nhìn & Định vị sản phẩm

### 1.1 Tầm nhìn

VinUni Career Platform là **hệ điều hành tuyển dụng chính thức của Trường Đại học VinUni** — xây dựng dành riêng cho hệ sinh thái VinUni, không phải sản phẩm bán cho trường khác.

Hệ thống kết nối sinh viên, doanh nghiệp đối tác và nhà trường trong một nền tảng thống nhất — nơi AI hỗ trợ thực chất ở mọi bước: tạo CV từ đầu, phân tích CV, khớp việc làm, pipeline tuyển dụng tự động, sự kiện, quảng cáo, và dự báo chiến lược.

**Không chỉ là job board.** Đây là hệ thống quản lý toàn bộ vòng đời tuyển dụng của VinUni: xác minh danh tính, pipeline tuyển dụng linh hoạt, sự kiện phức tạp, theo dõi đầu ra sau tốt nghiệp, và vòng phản hồi cải tiến chương trình đào tạo.

### 1.2 Định vị cạnh tranh

| Đối thủ | Điểm mạnh | VinUni Career làm tốt hơn |
|---------|-----------|--------------------------|
| LinkedIn | Network toàn cầu | AI cá nhân hóa + verified talent + pipeline ATS |
| TopCV / VietnamWorks | Job board VN quen thuộc | Multi-round pipeline + interview sim + alumni net |
| Handshake (US) | Campus-focused | AI matching sâu hơn + ads system + event management |
| Greenhouse / Workday | ATS enterprise | Nhẹ hơn, campus-native, AI-first |

### 1.3 Nguồn thu

| Nguồn | Mô tả |
|-------|-------|
| Partner packages | Gói đăng tin (số lượng job, spotlight, featured) |
| Partner advertising | Banner, sponsored jobs, email ads, event sponsorship |
| Student subscriptions | External/General users mua gói AI + features nâng cao |
| Event packages | Partner mua vé/slot sponsorship sự kiện |

### 1.4 Product Reality Rule

Before building or marking any feature complete, apply
`docs/PRODUCT_REALITY_REBUILD_SPEC.md`.

VinUni Career features must be practical workflows, not isolated demo screens.
If a user-visible change requires backend/data/AI/auth/notification/quota/
workflow/seed improvements to be truthful, those contracts must be designed or
implemented as part of the slice. Examples:

- CV creation is visual/template/upload/AI-first, not profile-form-first.
- Job fit and competition are calculated from real CV/JD/application signals,
  not decorative badges.
- Partner/university operations use RBAC, audit, queues, workflow versions, and
  recovery states, not static admin forms.
- Public/student discovery separates organic, recommended, sponsored, and
  university-curated inventory with real tracking and disclosure.
- Auth, onboarding, OTP/reset, email templates, and duplicate-account handling
  must behave like a production identity system.

---

## 2. Người dùng & RBAC

### 2.1 Sinh viên / Người tìm việc

**University Admin định nghĩa tier và giới hạn qua UI — không hardcode.**

| Tier | Mô tả | Default |
|------|-------|---------|
| **VinUni Student** | Sinh viên đang học tại VinUni | Full access |
| **VinUni Alumni** | Cựu sinh viên VinUni | Moderate + alumni network |
| **External Student** | Sinh viên trường khác | Restricted, mua thêm được |
| **General User** | Người đi làm / chưa tốt nghiệp | Basic, mua thêm được |

> Admin đổi tên tier, thêm tier mới, set limits mọi thứ qua UI.

---

### 2.2 Partner (Employer)

**Bootstrap:** Người đăng ký đầu tiên = Admin mặc định.

**RBAC Partner — do Admin tự tạo hoàn toàn:**

```
Organization
├── Departments (tự tạo tùy ý)
│   ├── HR Department
│   ├── Engineering
│   ├── Marketing
│   └── [Bất kỳ phòng ban nào]
└── Roles (tự đặt tên, assign permissions tùy ý)
    ├── "Trưởng phòng tuyển dụng"
    ├── "Chuyên viên HR"
    ├── "Technical Interviewer"
    └── [Bất kỳ role nào]
```

**Permission resources Partner:**

| Resource | Actions |
|----------|---------|
| Jobs | view, create, edit, delete, publish, manage_pipeline |
| Candidates | view, view_contact, shortlist, move_stage, rollback_stage, reject, note, compare |
| Interviews | view, schedule, edit, cancel, score |
| Offers | view, create, send, withdraw, counter |
| Talent Pool | view, add, remove, contact_request |
| Passive Search | search, view_profile, send_contact |
| Analytics | view_basic, view_full, export |
| Team | view, invite, edit_role, remove |
| Billing | view, purchase |
| Advertising | view, create, edit, submit |
| Events | view, create, edit, manage_tickets |
| Company Profile | view, edit |
| Assessments | view, create, edit, assign |
| Settings | view, edit_pipeline_templates, edit_notification_templates |

**Job Posting Permission (org-level setting):**
- Admin cấu hình: ai được phép tạo job? → Options:
  - "Tất cả thành viên"
  - "Chỉ roles cụ thể" (multi-select role list)
  - "Chỉ departments cụ thể" (multi-select dept list)
- Có yêu cầu internal approval không? (job đi qua manager trước khi gửi university)

---

### 2.3 University Admin (System Admin tối cao)

**RBAC University — do Super Admin tự tạo hoàn toàn (không hardcode roles):**

```
VinUni Organization
├── Departments (tự tạo)
│   ├── Trung tâm Hỗ trợ Sinh viên & Việc làm
│   ├── Phòng Quan hệ Doanh nghiệp
│   └── [Bất kỳ phòng ban nào]
└── Roles (tự đặt tên)
    ├── "Quản trị viên hệ thống" → full access
    ├── "Trưởng phòng kiểm duyệt"
    └── [Bất kỳ role nào]
```

**Permission resources University:**

| Resource | Actions |
|----------|---------|
| User Management | view, edit_tier, grant_subscription, suspend, restore, export |
| Partner Management | view, approve, suspend, set_package, set_trust_level, export |
| Moderation Queue | view, approve, reject, escalate, bulk_action |
| System Configuration | view, edit_theme, edit_flags, edit_policies, edit_tiers |
| AI Settings | view, manage_providers, manage_models, view_costs |
| Marketplace & Ads | view, approve_campaign, reject_campaign |
| Events | view, create, edit, approve_partner_event, manage_all |
| Student Data | view_aggregate, view_individual, export |
| Career Outcomes | view, export, manage_surveys |
| Alumni Network | view, manage |
| Financial Reports | view, export |
| Audit Logs | view, export |
| Notifications | view, broadcast, manage_templates |
| Legal Documents | view, publish |
| VinUni Integrations | view, configure |

---

## 3. Trải nghiệm khách (Guest / Unauthenticated)

### 3.1 Nội dung xem được khi chưa đăng nhập

Chỉ thấy những gì được đánh dấu **Public**:
- Jobs có visibility = "Public"
- Events có visibility = "Public"
- Company pages (read-only)
- Trang giới thiệu platform
- Salary Explorer ở mức aggregated (không chi tiết)

**Không thấy:**
- Jobs với visibility "VinUni Student only", "Authenticated only"
- Events invitation-only
- Talent pool, messaging, AI features
- Analytics bất kỳ

### 3.2 Gating — Yêu cầu đăng nhập

Khi guest thực hiện action cần login:

| Action | Trigger |
|--------|---------|
| Bấm "Ứng tuyển" | Modal: "Đăng nhập để ứng tuyển" |
| Bấm "Đăng ký sự kiện" | Modal: "Đăng nhập để đăng ký" |
| Bấm "Mua vé sự kiện" | Modal: "Đăng nhập để mua vé" |
| Mở AI chatbot | Modal: "Đăng nhập để dùng trợ lý AI" |
| Bookmark job | Modal: "Đăng nhập để lưu việc làm" |
| Xem salary chi tiết | Modal: "Đăng nhập để xem thông tin chi tiết" |
| Xem company reviews | Modal: "Đăng nhập để xem đánh giá" |

**Modal design:** Có option login + register, không chuyển trang, sau khi login tiếp tục action ban đầu (không lose state).

### 3.3 Public Career Gateway

Guest homepage is not a generic marketing landing page. It is the public career
marketplace gateway for VinUni.

First viewport must show:

- Public navigation: Jobs, Companies, Career Explore, Events, Employers.
- Strong search: keyword/skill/title + city/work mode, with popular searches.
- Real public jobs immediately visible or one click away.
- Public events and employer discovery visible in the same experience.
- Default VinUni-owned visuals from `frontend/public` for the brand/campus/event
  atmosphere, while employer logos and campaign creatives come from the real
  upload/media pipeline.
- Clear login/register actions, but browsing public content must not require auth.
- Sponsored/ad inventory where active, always labelled `Được tài trợ` or
  `Quảng cáo`.

Primary public modules:

- Featured/public jobs.
- Sponsored jobs with non-removable disclosure.
- Public events and career fairs.
- Featured employers / strategic partners.
- Company directory categories: industry, hiring size, strategic partners.
- Career exploration content: industries, role guides, skill tracks.
- Search result entry points for jobs, companies, events, and learning content.
- Trust strip: verified by VinUni, career support, skill learning, community.

Guest gating:

- View public job/event/company detail: allowed.
- Apply, save/bookmark, create job alert, register event, buy ticket, message
  employer, use AI, view detailed salary/reviews: login modal with preserved
  intent.
- If action is student-only, login first then show persona/permission guidance.

Public ads/business rules:

- Placements: hero banner, sponsored job row/card, employer spotlight, event
  sponsorship card, email/newsletter placement, content/learning banner.
- Every placement records impression/click/apply-start when analytics exists.
- Ads can use only allowed targeting dimensions from `SECURITY_PRIVACY.md`.
- University admin can disable any campaign or placement immediately.
- No fake metrics. If aggregate counts are unavailable, hide the metric or show a
  real empty/loading state.

Public and student recommendations:

- Guest users receive privacy-safe recommendations from search/view/session
  signals only; no PII, exact location, third-party tracking, or CV content.
- Logged-in students receive recommendations from active CV fit, preferences,
  saves/views, applications, events, and deadlines.
- If a list is merely recent/new/popular, label it as recent/new/popular. Do not
  call it "recommended" unless a recommendation contract with reason codes or
  scoring exists.
- Sponsored jobs/events/employers can appear in paid slots, but must stay
  visually distinct from organic/recommended results and always show disclosure.
- See `docs/DISCOVERY_RECOMMENDATION_ADS_SPEC.md` for ranking, session,
  analytics, and advertising placement contracts.

---

## 4. Dashboard theo persona

**Dashboards phải show dữ liệu thực, không placeholder. Đẹp, rõ ràng, actionable.**

Dashboard không phải trang chào mừng. Mỗi persona dashboard là một operating
surface cho công việc hằng ngày:

- Public: discovery marketplace để tìm jobs/events/companies trước khi đăng nhập.
- Student: signed-in career marketplace + command center để biết nên làm gì tiếp
  theo. Student navigation kế thừa public top nav/search/discovery, cá nhân hóa
  bằng My Career, CV Studio, Applications, Saved, notifications, avatar/settings;
  bỏ hoặc giảm các mục dành cho nhà tuyển dụng. Không mặc định dùng sidebar kiểu
  admin cho student desktop.
- Partner: recruiting operations center để xử lý pipeline, ứng viên, team, ads,
  events, và quota.
- University: platform operations center để xử lý moderation, partner governance,
  outcomes, AI/cost, templates, security, và audit.

Implementation rules:

- Không dùng icon emoji trong UI thật; các diagram dưới đây chỉ là mô tả ý tưởng.
  Implement bằng Phosphor icons và design tokens.
- Không copy số mẫu trong spec thành fake metrics. Số phải đến từ API/read model
  hoặc hiển thị skeleton/empty state.
- Mỗi dashboard phải có: primary queue, next actions, filters, critical alerts,
  recent activity, and at least one deep link to the full workflow.
- Mỗi dashboard phải có loading/empty/error/permission/offline states.
- UI phải browser-verified ở mobile và desktop trước khi ghi status
  `browser verified`.

### 4.1 Student Dashboard

```
┌─────────────────────────────────────────────────┐
│ HEADER: Avatar + Tên + Tier badge + Readiness Score Circle │
└─────────────────────────────────────────────────┘

Row 1 — Stats nhanh (4 cards)
┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│Đơn đang  │ │Phỏng vấn │ │Jobs mới  │ │Hồ sơ    │
│ứng tuyển │ │sắp tới   │ │match hôm │ │được xem  │
│    5     │ │    2     │ │    12    │ │    48    │
└──────────┘ └──────────┘ └──────────┘ └──────────┘

Row 2
┌─────────────────────────┐ ┌──────────────────────┐
│ NEXT ACTION             │ │ RECOMMENDED JOBS     │
│ ┌───────────────────┐   │ │ ┌──────────────────┐ │
│ │🕐 Phỏng vấn ngày │   │ │ │ Software Engineer│ │
│ │mai 10:00 — Vingroup│  │ │ │ Vingroup • 89%  │ │
│ │[Chuẩn bị ngay]    │  │ │ │ [Xem]           │ │
│ └───────────────────┘  │ │ └──────────────────┘ │
│ ┌───────────────────┐   │ │ ┌──────────────────┐ │
│ │📋 Offer deadline  │   │ │ │ Data Analyst...  │ │
│ │còn 2 ngày — FPT   │  │ │ └──────────────────┘ │
│ └───────────────────┘   │ └──────────────────────┘
└─────────────────────────┘

Row 3
┌──────────────────────────┐ ┌─────────────────────┐
│ APPLICATION PIPELINE     │ │ UPCOMING EVENTS     │
│ Funnel chart:            │ │ • Career Fair VinUni│
│ Applied 12 → SL 5 →      │ │   Thứ 6, 10:00      │
│ Interview 2 → Offer 1    │ │ • AI Workshop FPT   │
│ [Xem tất cả]             │ │   Thứ 7, 14:00      │
└──────────────────────────┘ └─────────────────────┘

Row 4
┌──────────────────────────────────────────────────┐
│ SKILL GAPS (dựa trên jobs đang match)             │
│ "Jobs match bạn thường yêu cầu: Docker (+34%),   │
│ TypeScript (+28%), System Design (+22%)"          │
│ [Xem learning paths]                              │
└──────────────────────────────────────────────────┘
```

**Quick actions từ dashboard:** Chat với AI, Upload CV, Browse jobs, Xem lịch phỏng vấn.

Student dashboard acceptance:

- First viewport shows career readiness, CV readiness, active CV quota, next
  best action, and at least one real recommended
  job/application/interview/event surface.
- If no data exists, show CV-first onboarding tasks: upload CV, choose a CV
  template, ask AI to draft from notes, browse public jobs, set job
  preferences, and enable notifications. Do **not** force a long
  education/experience/profile form before the student can use the product.
- Student profile completion is secondary: it covers preferences, privacy,
  notifications, verified VinUni facts, and facts explicitly confirmed from a
  CV. It is not the canonical place where students must manually maintain
  resume content.
- Recommended jobs should explain which CV is best for the JD when possible:
  recommended CV, 0-100 fit score, main gaps, and "improve this CV" action.
- AI suggestions must be explainable and lead to reviewable actions, not hidden
  auto-writes.

---

### 4.2 Partner Dashboard

```
┌─────────────────────────────────────────────────────┐
│ HEADER: Company Logo + Name + Package badge + Quota usage │
└─────────────────────────────────────────────────────┘

Row 1 — Stats (5 cards)
┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐
│Active  │ │New apps│ │Scheduled│ │Offers  │ │Ad     │
│Jobs    │ │today   │ │today   │ │pending │ │budget │
│  8     │ │  23    │ │  4     │ │  2     │ │70%    │
└────────┘ └────────┘ └────────┘ └────────┘ └────────┘

Row 2
┌───────────────────────────┐ ┌──────────────────────┐
│ HIRING PIPELINE OVERVIEW  │ │ TODAY'S SCHEDULE     │
│ Per job, mini funnel:     │ │ 10:00 - John Doe     │
│ "Software Eng: 45→12→5→2"│ │        Tech Interview│
│ "Data Analyst: 23→8→3→1" │ │ 14:00 - Jane Smith   │
│ [Xem tất cả jobs]         │ │        HR Screen     │
└───────────────────────────┘ └──────────────────────┘

Row 3
┌───────────────────────────┐ ┌──────────────────────┐
│ RECENT APPLICATIONS       │ │ TEAM ACTIVITY        │
│ • Nguyen Van A — SE       │ │ Recruiter B: moved   │
│   Vòng 2 — 2h trước       │ │ 3 candidates to      │
│ • Tran Thi B — DA         │ │ interview stage      │
│   Mới ứng tuyển — 4h      │ │ Recruiter C: sent    │
│ [Xem pipeline]            │ │ 2 offers             │
└───────────────────────────┘ └──────────────────────┘

Row 4
┌──────────────────────────────────────────────────────┐
│ HIRING FUNNEL CHART (7 ngày gần nhất)                │
│ Stacked bar: Applied | Shortlisted | Interview | Offer│
└──────────────────────────────────────────────────────┘
```

Partner dashboard acceptance:

- First viewport shows open hiring work: jobs needing action, new candidates,
  interviews today, offers pending, package/quota/ad status.
- Recruiter can jump directly into pipeline, candidate review, job edit,
  team/RBAC, advertising, or event management.
- Recent applications must show enough context to act without opening every
  record: job, stage, freshness, missing CV/reveal state, owner/recruiter.
- Empty state guides partner to complete company profile, invite team, create
  job, submit campaign, or request university support.

---

### 4.3 University Admin Dashboard

```
Row 1 — Platform health (6 cards)
┌───────┐ ┌───────┐ ┌───────┐ ┌───────┐ ┌───────┐ ┌───────┐
│DAU    │ │New    │ │Jobs   │ │Queue  │ │AI     │ │Revenue│
│       │ │Reg    │ │Active │ │Pending│ │Status │ │Today  │
│ 1,247 │ │  34   │ │ 156   │ │ 12 ⚠️ │ │ ✅ OK │ │2.3M₫  │
└───────┘ └───────┘ └───────┘ └───────┘ └───────┘ └───────┘

Row 2
┌─────────────────────────────┐ ┌────────────────────────┐
│ MODERATION QUEUE             │ │ AI PROVIDER STATUS     │
│ Partner reg: 3 (1 🔴 SLA)   │ │ Primary: ✅ 145ms avg  │
│ Job posts: 7 (2 🟡 SLA)     │ │ Backup: ✅ 280ms avg   │
│ Ads: 2 pending               │ │ Local: ✅ 890ms avg    │
│ Reviews: 5 pending           │ │ Cost today: $4.23     │
│ [Vào queue]                  │ │ Budget: 72% used       │
└─────────────────────────────┘ └────────────────────────┘

Row 3
┌─────────────────────────────┐ ┌────────────────────────┐
│ STUDENT PLACEMENT KPIs       │ │ PARTNER HEALTH         │
│ Placement rate: 87% (↑3%)   │ │ Active: 124            │
│ Avg salary: 18.5M₫ (↑8%)   │ │ Pending approval: 8    │
│ Time-to-hire: 34 days (↓5d) │ │ Suspended: 2           │
│ [Xem chi tiết]               │ │ Avg health score: 8.2  │
└─────────────────────────────┘ └────────────────────────┘

Row 4
┌──────────────────────────────────────────────────────┐
│ PLATFORM ACTIVITY (30 ngày) — Line chart             │
│ Active users | Jobs posted | Applications | Hires    │
└──────────────────────────────────────────────────────┘
```

University dashboard acceptance:

- First viewport shows operational risk and queues: pending partner approvals,
  job/event/ad moderation, SLA breaches, AI/cost health, security alerts, and
  notification delivery issues.
- Admin can jump directly to the exact queue item; no KPI-only dashboard without
  actions.
- Career outcomes and partner health are read models with filters by cohort,
  school/major, industry, and time range.
- AI/cost/provider health is visible to admins only and must never leak provider
  details to end users.
- Empty state guides setup: invite staff, configure roles, approve partners,
  seed templates, configure notification channels, and connect integrations.

---

## 5. Tính năng chi tiết

---

### MODULE 1: Xác thực & Phiên làm việc

#### 1.1 Đăng ký & Login
- **VinUni SSO:** OIDC/SAML với VinUni IdP → auto-verify, auto-fill profile từ SIS
- Email/mật khẩu + email verification
- Google SSO, Microsoft SSO
- Magic link (passwordless)
- Chọn loại tài khoản khi đăng ký nếu không qua SSO
- **2FA:** TOTP optional cho user, bắt buộc có thể config cho university staff

#### 1.2 Đa danh tính
- Một account, nhiều danh tính (vừa là sinh viên vừa là nhân viên partner)
- Switch identity từ header dropdown
- Permissions áp dụng đúng per identity đang active
- Audit log ghi rõ identity nào thực hiện action

#### 1.3 Security
- JWT (15 phút) + Refresh token (7 ngày)
- Session revocation toàn devices
- Rate limiting: per IP + per user + per endpoint
- Brute force lockout sau 5 lần sai
- Account recovery qua email

---

### MODULE 2: Cấu hình hệ thống (University Admin)

#### 2.1 Brand & Theme
Config qua UI → lưu DB → inject CSS variables → real-time preview:
- Logo, Favicon, Brand name
- Primary/Secondary/Sidebar colors
- Font family, Border radius
- Custom CSS block (Super Admin only, sandbox validation)

#### 2.2 User Tier Configuration
Admin cấu hình limits qua UI:

| Limit key | Mô tả |
|-----------|-------|
| `apply_per_month` | Số đơn ứng tuyển/tháng (-1 = unlimited) |
| `cv_storage_count` | Số CV lưu được |
| `ai_messages_per_day` | AI chatbot messages/ngày |
| `ai_messages_per_month` | AI chatbot messages/tháng |
| `interview_sim_sessions_per_month` | Luyện phỏng vấn AI |
| `job_alerts_count` | Số job alert |
| `match_score_visible` | Xem match score |
| `career_advisor_enabled` | Career path advisor |
| `salary_insights_enabled` | Salary benchmark |
| `interview_simulator_enabled` | AI interview practice |
| `passive_profile_visible` | Profile hiển thị với partner search |
| `mass_apply_limit` | Số jobs mass apply cùng lúc |
| `priority_in_search` | Ưu tiên trong passive search |
| `mentorship_access` | Tham gia mentorship |
| `alumni_network_access` | Truy cập alumni network |
| `event_ticket_max_per_event` | Số vé tối đa mỗi event |

#### 2.3 Subscription Packages
Admin tạo gói nâng cấp cho External/General users:
- Tên, giá, thời hạn
- Limits override khi mua gói
- Badge đặc biệt
- Tier nào được phép mua

#### 2.4 AI Provider Management
Superadmin-only. Ordinary university staff may see masked AI status/budget/alias
controls when granted, but cannot see or edit the real provider/model registry.

- Thêm/sửa/xóa provider: alias, type, encrypted API key reference, base URL
  reference, active state
- Provider types: OpenAI-compatible, Gemini native, Anthropic, Ollama, OpenRouter
- Test kết nối + latency trong superadmin UI only
- Model per task type (chat, extraction, matching, embedding, moderation, interview-sim...)
- Fallback chain (A → B → C local)
- Health monitoring: latency, error rate, cost per day
- Budget alerts + auto-disable nếu error rate > threshold
- **Không expose với non-superadmin:** tên provider, concrete model id/model
  name, key, base URL, cost internals, token counts, latency, prompt text

#### 2.5 University RBAC (Fully Configurable)
Super Admin tự tạo: roles (tên tùy ý) + departments + permissions matrix. Invite staff qua email. Staff có nhiều roles.

#### 2.6 Verification Policy
Per registration type: tài liệu yêu cầu, auto-approve conditions, SLA, AI assist level.

#### 2.7 Feature Flags
Bật/tắt global hoặc per tier: AI chat, interview simulator, salary explorer, passive search, mentorship, alumni network, events, subscriptions, ads, mass apply...

#### 2.8 Notification Templates
Chỉnh nội dung vi/en, biến động, preview, test send.

#### 2.9 Legal Documents
Versioning, consent tracking, re-accept khi có version mới.

#### 2.10 Event Approval Policy
- Sự kiện do Partner tạo → cần university duyệt hoặc không?
- **Toggle:** AI auto-approve events / Manual review
- AI kiểm tra: nội dung phù hợp, không sai lệch, creative chất lượng
- Trusted partners: có thể auto-approve không cần AI check

---

### MODULE 3: Hồ sơ sinh viên

Profile is not the main CV editor. It stores identity, preferences, privacy,
verified VinUni facts, notification/security settings, and optional public
portfolio information. Resume content should primarily live in CV Studio and may
feed confirmed facts back into the profile only after student review.

#### 3.1 Thông tin cơ bản
Tên, ảnh, ngày sinh, giới tính (optional), quốc tịch, tỉnh/thành, điện thoại (OTP), ngành, khoa, năm học, GPA (optional), degree level, bio 500 ký tự, trạng thái tìm việc.

#### 3.2 Social & Portfolio
LinkedIn, GitHub, GitLab, Portfolio, Behance, Dribbble, Medium, YouTube.

#### 3.3 Skills
Proficiency levels, phân loại (Technical/Soft/Languages/Tools), gợi ý từ CV, endorsed by partner sau phỏng vấn.

#### 3.4 Video Introduction (optional)
Upload 30-60 giây. AI transcript + sentiment check. Hiển thị với partner nếu student bật.

#### 3.5 Profile Completion & Readiness Score (0-100)
Profile completion is secondary and must not block CV creation. Career readiness
combines: preferences/settings readiness, CV quality, activity, and job-match
quality. AI gợi ý cải thiện cụ thể nhưng không ép student nhập lại toàn bộ
education/experience trong profile nếu CV Studio đã xử lý được.

#### 3.6 Career Interests & Preferences
Ngành quan tâm, loại hình (full-time/part-time/intern/remote/hybrid), địa điểm, lương kỳ vọng (private).

#### 3.7 Privacy Controls
- Default: ẩn tên, ảnh, điện thoại với partner
- Reveal chỉ khi student apply hoặc opt-in passive search
- Blacklist companies: "Ẩn hồ sơ với công ty X"
- Xem ai đã xem profile (theo công ty)

---

### MODULE 4: CV Studio & Quản lý CV

> Chi tiết source-of-truth: `docs/CV_STUDIO_SPEC.md`.

#### 4.1 Upload & AI Extraction
- PDF/DOCX/DOC, tối đa 10MB
- Ảnh chụp/scan dùng local OCR nhẹ trước (`vie+eng`); AI vision chỉ là fallback
  opt-in/capped khi local extraction không đủ và cấu hình cho phép.
- Extract: tên, contact, education, experience, skills, projects, certs, awards, ngôn ngữ
- Review + confirm trước khi save
- Trạng thái thân thiện, không hiện technical details

#### 4.2 CV Analysis
- Strength indicators + improvement hints
- ATS compatibility check
- Completion score

#### 4.3 CV Studio — Template Builder không cần AI
- Tạo CV trực tiếp trên hệ thống bằng template, áp dụng cho cả người chưa có CV và người đã có CV nhưng muốn chuẩn hóa theo mẫu.
- First screen là CV library + template marketplace giống công cụ tạo tài liệu:
  upload CV, chọn template, duplicate CV, hoặc nhập raw notes để AI hỗ trợ.
- Template library do university duyệt: classic, modern, technical, business, research, one-page internship.
- Primary editor là canvas tài liệu A4: chọn block, sửa text inline, kéo thả
  section/bullet, đổi style/token, thay ảnh/crop ảnh, cảnh báo page-break,
  preview/export cùng một render pipeline. Không làm trải nghiệm chính thành
  form nhập từng trường giống profile.
- Section/block model: summary, education, experience, projects, skills,
  certifications, awards, languages, activities, custom sections. Inspector
  chỉ là công cụ phụ cho block đang chọn, không thay thế canvas.
- Tạo từ blank template, import confirmed profile facts khi student chọn, import
  từ uploaded CV extraction, hoặc duplicate CV hiện có rồi đổi template/nội dung.
- Không bắt student hoàn thành form profile education/experience trước khi tạo CV.
- Uploaded CV gốc vẫn được giữ như original document; builder CV là bản structured editable riêng.
- Autosave, undo/redo, preview A4, page-break warning, version history, restore.
- Export PDF v1; DOCX export phase sau trừ khi user yêu cầu rõ.

#### 4.4 CV Studio — AI-Assisted
- AI tạo draft CV đầu tiên từ raw notes, uploaded CV extraction, selected
  template, short questionnaire, và confirmed profile facts.
- AI điền một template đã chọn từ uploaded CV extraction, CV hiện có, raw notes,
  và confirmed profile facts.
- AI tạo bullet points từ raw notes của sinh viên.
- AI rewrite từng bullet/section theo yêu cầu tự nhiên: "ngắn hơn", "chuyên nghiệp hơn", "bằng tiếng Anh", "nhấn mạnh backend".
- AI natural-language edit cho canvas: ví dụ "0324xx0898 là số điện thoại của
  tôi" hoặc "đưa projects lên trước experience" -> AI tạo patch/diff trên CV,
  student accept/edit/reject trước khi áp dụng.
- AI optimize CV theo job cụ thể nhưng không được bịa thông tin.
- AI khuyến nghị CV nào phù hợp nhất với JD, score 0-100, breakdown theo
  categories, và gợi ý cải thiện dựa trên sự thật student đã cung cấp.
- AI output luôn ở dạng diff/suggestion. Student accept/edit/reject trước khi save.
- Accept AI suggestion tạo version mới + audit event.

#### 4.5 Multiple CV Management
Nhiều CV, set primary, archive, giới hạn theo tier. Default: 5 active CV library
items/student tier trừ khi university admin cấu hình khác. Khi đạt limit, show
archive/delete/request-more/upgrade path.

#### 4.6 AI CV Review per Job
"CV của bạn phù hợp 78/100 với job này" + breakdown + recommended CV + one-click
optimize suggestions. Score là product score giải thích được, không phải raw
model confidence/similarity.

---

### MODULE 5: Tìm việc & Job Marketplace

#### 5.1 Job Visibility / Privacy Settings (per job — do partner set khi đăng)

| Visibility | Ai xem được |
|-----------|------------|
| **Public** | Tất cả, kể cả chưa đăng nhập |
| **Authenticated** | Phải đăng nhập mới xem |
| **Students Only** | Chỉ các tiers là sinh viên (VinUni + External) |
| **VinUni Students Only** | Chỉ sinh viên đang học tại VinUni |
| **Invitation Only** | Partner gửi link trực tiếp cho người được mời |

> Guest users: chỉ thấy Public jobs. Các jobs khác không xuất hiện trong kết quả tìm kiếm khi chưa đăng nhập.

#### 5.2 Public Job Board
- Filter: ngành, loại hình, địa điểm, kinh nghiệm, lương, remote/onsite, visibility (guest chỉ thấy public)
- Sort: mới nhất, phù hợp nhất, nổi bật
- Semantic search AI
- Sponsored jobs label "Được tài trợ" rõ ràng

#### 5.3 Personalized Discovery (khi đã đăng nhập)
- Match score 0-100 + explanation per job and recommended CV to apply with
- Competition intelligence login-only: mức cạnh tranh phải dựa trên dữ liệu thật
  như số vị trí/tuyển mục tiêu, volume ứng tuyển theo bucket, chất lượng pool
  ứng viên ở mức aggregate, fit bucket của CV đang chọn, deadline và source mix.
  Không hiển thị cho guest, không lộ PII/điểm nội bộ của ứng viên khác.
- Recommended jobs (profile + behavior)
- Deadline countdown: "Còn 3 ngày — 47 đã apply"
- Early bird signal: "Tin mới 2h trước"
- Bookmark + job alerts

#### 5.4 AI-Powered Semantic Search
- Hiểu intent, correct typos, Vietnamese variants
- Search by description: "việc remote, lương tốt, có mentor"
- Suggest related searches, search history, saved searches

#### 5.5 Job Detail
- Full description + skills breakdown
- Company preview + apply/bookmark/share
- Nếu đã đăng nhập: hiển thị recommended CV, CV-JD fit, missing evidence, CV
  improvement actions, learning gaps, apply readiness, và competition guidance
  nếu đủ dữ liệu. Nếu thiếu dữ liệu, show low-signal state thay vì bịa điểm.
- **Q&A Section:** Sinh viên hỏi → partner trả lời công khai (hoặc AI trả lời từ JD)
- **AI JD Analyzer:** Detect red flags (vague, unrealistic, discriminatory) → warn sinh viên
- **AI Q&A:** "Kinh nghiệm phân tán hệ thống trong JD này nghĩa là gì?" → AI explain từ context JD
- Similar jobs
- **Pipeline preview:** "Job này có 3 vòng phỏng vấn" (nếu partner cho hiển thị)
- **Position counter:** "3/5 vị trí còn trống" (nếu partner bật)

#### 5.6 Company Pages

Logo, tên, ngành, quy mô, địa điểm, verified badge, open positions, reviews,
**Interview Q&A Bank**, media.

Company media rules:

- Partner admins can upload and update their own logo, cover image, and media
  gallery when they have company-profile permission.
- University admins can review/remove media, replace unsafe default imagery, and
  set strategic-partner spotlight media.
- Public pages never show raw storage paths. They show `logo_url`/media URLs only
  after validation and public-delivery policy.
- If no logo exists, use a polished initials fallback; do not fake real-company
  logos.
- Local/demo seed data may use clearly marked demo partner logos uploaded through
  the same pipeline. Do not commit unrelated real-company brand files as static
  decoration.

#### 5.7 Salary Explorer
Benchmark lương theo vị trí + ngành + địa điểm + kinh nghiệm. "VinUni grads ngành này nhận X triệu." Hiển thị per tier.

---

### MODULE 6: Ứng tuyển

#### 6.1 Apply Flow
1. "Ứng tuyển" → chọn CV (hoặc dùng primary)
2. Viết cover letter (optional, AI assist)
3. **Nếu job bật Anonymous Apply:** student chọn "Ẩn danh" hoặc "Không ẩn danh"
   - Ẩn danh: partner thấy nội dung CV nhưng KHÔNG thấy: tên, ảnh, điện thoại, email, tên trường, năm tốt nghiệp
   - Mức độ ẩn danh do university admin cấu hình
4. Trả lời screening questions của employer
5. Nhập referral code (nếu có)
6. **Auto-save draft:** Nếu user thoát giữa chừng, draft được lưu 48h
7. Review trước khi submit
8. **Confirm dialog:** Rõ ràng với tóm tắt job + CV được dùng
9. Submit → tạo immutable CV snapshot từ uploaded CV hoặc builder CV version đã chọn
10. **Application Receipt Email** với reference number (VCP-2026-XXXXX)

#### 6.2 Mass Apply
Chọn nhiều jobs → apply cùng lúc với primary CV. Premium feature.

#### 6.3 Anonymous Application — Chi tiết

**Partner side khi nhận anonymous application:**
- Thấy: skills, experience, education (masked — "Đại học tại Hà Nội"), projects
- Không thấy: tên, ảnh, phone, email, tên trường chính xác, GPA
- Có nút "Yêu cầu reveal danh tính" → student nhận notification → decide accept/decline
- Nếu student accept reveal → partner thấy full info
- Nếu partner shortlist anonymous candidate → student tự quyết định có reveal không

**University policy:** Admin cấu hình chính xác những field nào bị ẩn trong anonymous mode.

#### 6.4 Application Tracking
- Timeline per application
- Status thân thiện (không hiện enum codes):
  - Đã ứng tuyển → Qua sơ tuyển → Vòng 2 / 3... → Nhận đề nghị / Chưa phù hợp lần này
- **Vòng phỏng vấn hiển thị:** "Bạn đang ở Vòng 2 / 4 vòng" (nếu partner cho hiện)
- Notification mọi thay đổi
- Notes cá nhân
- **Insight:** "Trung bình 4 ngày để nhận phản hồi từ công ty này"
- **Offer Comparison Tool:** Khi có nhiều offers → so sánh side-by-side (lương, phúc lợi, rating công ty)
- **Re-apply:** Nếu partner cho phép, hiện nút sau X ngày bị reject

#### 6.5 Withdrawal
Với confirm + reason (required). Tự động notify partner.

#### 6.6 Self-Scheduling Interview
Partner setup availability. Student tự chọn slot. Confirm hai chiều. Google Calendar / Outlook invite tự động.

---

### MODULE 7: Multi-round Interview Pipeline (Partner — Per Job Configuration)

**Đây là tính năng ATS cốt lõi cho hệ thống — Pipeline Engine mạnh mẽ, linh hoạt.**

#### 7.1 Cấu hình Pipeline khi đăng job

Khi tạo job, Partner cấu hình số vòng và chi tiết từng vòng. Có thể dùng **template** có sẵn hoặc tạo mới.

**Cấu trúc một vòng (Stage):**

```
Stage:
  ├── Order: 1, 2, 3... (thứ tự trong pipeline)
  ├── Name: "Vòng 1 — Sàng lọc CV" (đặt tên tự do)
  ├── Type: CV_REVIEW | WRITTEN_TEST | PHONE_SCREEN | VIDEO_INTERVIEW
  │         | ONSITE_INTERVIEW | GROUP_ASSESSMENT | BACKGROUND_CHECK
  │         | REFERENCE_CHECK | OFFER
  ├── Assignee:
  │   ├── Mode: "Department" hoặc "Specific Person"
  │   ├── If Department: chọn department (mọi member trong dept đều thấy)
  │   └── If Person: chọn 1 hoặc nhiều thành viên cụ thể
  ├── Required Action:
  │   ├── "Complete scorecard trước khi advance"
  │   ├── "Assessment score >= X% trước khi advance"
  │   └── "Manual approval" (recruiter click confirm)
  ├── SLA: Tùy chọn deadline (VD: 3 ngày để complete stage này)
  ├── Auto-advance: Khi Required Action done → tự động move sang vòng tiếp?
  ├── Notification to Candidate:
  │   └── Custom email template khi candidate vào vòng này
  └── Candidate visibility: Stage này có show tên vòng cho candidate không?
```

**Ví dụ pipeline thực tế:**

```
Job: Software Engineer tại Vingroup
───────────────────────────────────
Vòng 1: Sàng lọc CV
  → Assignee: HR Department
  → Required: Manual approval
  → SLA: 3 ngày
  → Notify candidate: "Hồ sơ của bạn đang được xem xét"

Vòng 2: Bài test kỹ thuật
  → Assignee: Engineering Department
  → Type: Written Test (link bài test gửi tự động)
  → Required: Score >= 70%
  → Auto-advance nếu pass
  → Notify: "Bạn đã qua sơ tuyển! Mời làm bài test"

Vòng 3: Phỏng vấn kỹ thuật
  → Assignee: CTO (cụ thể)
  → Type: Video Interview
  → Required: Scorecard completed
  → SLA: 5 ngày

Vòng 4: Phỏng vấn văn hóa
  → Assignee: HR Manager (cụ thể)
  → Required: Scorecard completed

Vòng 5: Offer
  → Assignee: HR Department
  → Auto-generate offer form
```

**Job chỉ có 1 vòng (startup nhỏ):**
```
Vòng 1: Xem xét hồ sơ → Offer
  → Assignee: Hiring Manager
  → Required: Manual approval
```

#### 7.2 Candidate Movement

**Advance (chuyển sang vòng tiếp):**
- Assignee current stage mark "Pass" → hệ thống tự chuyển sang assignee vòng tiếp
- Notification đến: candidate (nếu stage visible) + assignee vòng tiếp
- Auto-advance nếu configured

**Rollback (yêu cầu xét lại):**
- Bất kỳ assignee nào ở stage hiện tại có thể request rollback
- Chọn rollback về vòng nào (dropdown danh sách vòng trước)
- Bắt buộc ghi lý do rollback
- Notification đến: assignee vòng đó + partner admin
- Candidate: thấy "Đang xem xét lại hồ sơ" (không hiện rollback chi tiết)

**Reject:**
- Reject ở bất kỳ vòng nào
- Required: reason category + text (min 20 ký tự)
- Auto-send rejection email theo template của stage đó
- Candidate nhận: thông báo thân thiện "Chưa phù hợp lần này"

**Escalate:**
- Assignee có thể escalate lên Partner Admin nếu cần quyết định cấp cao

#### 7.3 Scorecard per Stage

Mỗi stage có scorecard riêng, partner cấu hình:
- Danh sách tiêu chí tự đặt (VD: "Kỹ năng coding", "Giao tiếp", "Fit văn hóa")
- Rating per tiêu chí: 1-5 sao
- Text comment tự do
- Overall recommendation: Strongly Recommend / Recommend / No / Strongly No
- Submitted by + timestamp

**AI assist scorecard:**
- Nếu interview được ghi chú → AI suggest scores + tóm tắt điểm nổi bật
- Human confirm/edit trước khi submit

#### 7.4 Pipeline Templates

- Partner lưu pipeline configuration thành template
- Đặt tên: "Template Tech Role", "Template Intern", "Template Finance"
- Khi tạo job mới → choose template → customize thêm nếu cần
- University cung cấp global templates cho partner mới (best practices)

#### 7.5 Pipeline Modification After Go-live

- Nếu job đã live và có candidates → cẩn thận khi sửa pipeline
- Chỉ Partner Admin được sửa live pipeline
- Warning rõ: "Candidates đang ở Vòng 2 sẽ bị ảnh hưởng như thế nào"
- Audit log ghi lại mọi thay đổi pipeline

#### 7.6 Candidate View (Student)

- "Bạn đang ở Vòng 2 / 4 vòng" (nếu partner cho hiển thị stage count)
- Tên vòng: hiện hoặc ẩn theo config của partner
- Không hiện: assignee, rollback history, scorecard nội dung
- Hiện: estimated timeline nếu partner set SLA

#### 7.7 Partner Candidate Pipeline View

**Kanban view:**
- Mỗi column = 1 vòng trong pipeline
- Card per candidate: avatar (nếu không ẩn danh), tên, match score, ngày apply, tags
- Drag-drop để move (với confirmation + required action check)
- Màu card theo status: active / SLA at risk (vàng) / SLA overdue (đỏ) / blocked (cần action)

**List view:**
- Tất cả candidates, filter theo stage/status/assignee/date
- Bulk actions: move stage, reject nhiều người, assign

**Candidate detail panel:**
- CV preview (với watermark nếu đã download)
- Timeline of all stages passed
- All scorecards từ các vòng
- Notes & tags
- Communication history
- AI match explanation

#### 7.8 Candidate Comparison View

- Chọn 2-4 candidates → "So sánh"
- Side-by-side: education, skills, experience, match score, scorecard ratings
- Highlight: ai mạnh hơn ở từng tiêu chí

---

### MODULE 8: Job Posting Advanced (Partner)

#### 8.1 Job Configuration

**Basic info:** Tiêu đề, department, level, loại hình, địa điểm (remote/onsite/hybrid), lương range, skills required, skills nice-to-have, description, responsibilities, requirements, benefits.

**Advanced settings:**

| Setting | Mô tả |
|---------|-------|
| Visibility | Public / Authenticated / Students Only / VinUni Only / Invitation |
| Allow anonymous apply | On/Off |
| Application deadline | Date/time hoặc "Khi đủ vị trí" |
| Number of positions | VD: 3 → hiện "3 vị trí còn trống" |
| Show position count | Hiện/ẩn số vị trí với ứng viên |
| Rolling review | Review as they come in (không đợi deadline) |
| Re-apply after rejection | Allow sau X ngày / Never |
| Internal approval | Job cần manager approve trước khi gửi university |
| Auto-close | Tự đóng khi đủ số vị trí |
| Referral enabled | Cho phép referral code cho job này |
| Pipeline configuration | Chọn hoặc tạo pipeline (xem Module 7) |
| Anonymous apply fields | Nếu bật, student có thể ẩn những gì |
| Stage visibility | Hiện tên vòng cho candidate không |

**Screening questions:** Text, MCQ, Yes/No, Rating 1-5, File upload.

**AI JD Writer:** Nhập bullet points → AI viết JD đầy đủ.

**AI Bias Checker:** Scan JD, flag ngôn ngữ discriminatory, suggest alternatives.

**AI Job Quality Predictor:** "JD này dự báo sẽ nhận ứng viên chất lượng X% dựa trên tính rõ ràng của yêu cầu."

#### 8.2 Internal Approval Workflow (nếu bật)

```
Recruiter tạo job (Draft) → Submit for internal review
→ Manager nhận notification → Review → Approve / Reject
→ Nếu Approve → Job được gửi lên University
→ University duyệt → Job live
```

#### 8.3 Job Management

- List với filter: active/draft/pending/closed/expired
- Job analytics per posting: views, apply starts, applications, conversion rate, source breakdown
- Duplicate job (tạo nhanh vị trí tương tự)
- Re-post job đã hết hạn (với 1-click, giữ pipeline config)
- Export job list to Excel (chọn fields)

---

### MODULE 9: AI Career Assistant (Chatbot)

**Yêu cầu đăng nhập để dùng. Guest thấy chatbot nhưng khi click → login modal.**

#### 9.1 Interface
- Conversational UI, streaming response, typing indicator
- Lịch sử chat persist theo tier
- Quick chips khi idle
- Multi-language: vi/en

#### 9.2 Tool Registry

**Read tools (không cần confirm):**

| Tool | Mô tả |
|------|-------|
| `search_jobs` | Tìm việc theo tiêu chí |
| `get_job_detail` | Chi tiết job |
| `get_match_explanation` | Giải thích match score |
| `get_application_status` | Trạng thái đơn |
| `get_interview_schedule` | Lịch phỏng vấn |
| `analyze_cv` | Phân tích CV |
| `analyze_cv_for_job` | CV phù hợp bao nhiêu % với job X |
| `suggest_cv_improvements` | Gợi ý cải thiện CV |
| `ats_keyword_suggestions` | Gợi ý keyword ATS từ JD |
| `cv_fabrication_check` | Cảnh báo claim thiếu bằng chứng |
| `check_skill_gaps` | Kỹ năng thiếu so với target |
| `get_skill_learning_path` | Lộ trình học kỹ năng với resources + timeline |
| `get_career_path_options` | Lộ trình nghề nghiệp từ profile |
| `simulate_career_path` | "Nếu học X trong 6 tháng, tôi có thể làm gì?" |
| `get_salary_benchmark` | Benchmark lương |
| `get_salary_negotiation_tips` | Tips đàm phán cho offer cụ thể |
| `prepare_interview` | Câu hỏi dự đoán cho job cụ thể |
| `generate_cover_letter` | Tạo draft cover letter |
| `review_cover_letter` | Review cover letter user viết |
| `draft_professional_email` | Viết email gửi employer |
| `get_company_insights` | Thông tin + reviews công ty |
| `get_interview_questions_bank` | Câu hỏi từ sinh viên đã interview |
| `get_market_trends` | Xu hướng thị trường, skills hot |
| `get_peer_benchmark` | So sánh anonymous với cohort VinUni |
| `get_jd_red_flags` | Phân tích JD có dấu hiệu đáng lo không |
| `get_offer_comparison` | So sánh nhiều offers |
| `estimate_application_success` | "Cơ hội shortlisted của bạn ở job này" (Cao/Trung bình/Thấp) |

**Write tools (cần confirm):**

| Tool | Mô tả |
|------|-------|
| `apply_job` | Ứng tuyển |
| `bookmark_job` | Lưu job |
| `set_primary_cv` | Đặt CV chính |
| `draft_cv_from_sources` | Tạo draft CV builder từ raw notes, CV upload, selected template, short questionnaire, confirmed facts |
| `fill_cv_template_from_sources` | Điền template từ CV upload/CV hiện có/raw notes/confirmed facts |
| `generate_cv_bullets` | Tạo bullet points từ raw notes |
| `rewrite_cv_section` | Rewrite section/bullet theo yêu cầu |
| `optimize_cv_for_job` | Tạo pending diff để tailor CV theo job |
| `recommend_cv_for_job` | Gợi ý CV phù hợp nhất với JD + score 0-100 |
| `withdraw_application` | Rút đơn |
| `update_job_preferences` | Cập nhật preferences |
| `set_job_alert` | Tạo job alert |
| `accept_offer` | Chấp nhận offer (double confirm) |

#### 9.3 AI Intelligence
- Context-aware: biết user đang ở đâu trong hành trình
- Proactive nudges: "Bạn có phỏng vấn ngày mai — muốn luyện tập?"
- Memory trong session (không hỏi lại thông tin đã biết)
- Vietnamese-native (hiểu ngữ cảnh tuyển dụng VN)
- Actionable: mọi recommendation đi kèm next step

#### 9.4 Safety
- Không expose với non-superadmin: provider names, concrete model ids/model
  names, tokens, latency, confidence raw, prompt text
- Write actions: propose → confirm → execute → audit log
- AI advisory only — không autonomous

---

### MODULE 10: AI Interview Simulator

**Yêu cầu đăng nhập. Tier/subscription có quyền mới dùng được.**

#### 10.1 Mock Interview
- Chọn job để luyện → AI tạo câu hỏi từ JD + Q&A bank thực tế
- Hoặc chọn loại: HR / Technical / Behavioral (STAR) / Case Study
- AI đóng vai interviewer, hỏi turn-by-turn
- User trả lời text
- AI hỏi follow-up realistic dựa trên câu trả lời

#### 10.2 Instant Feedback per Answer
- Clarity, Structure (STAR / logic flow), Content quality, Confidence signals
- Suggested better version

#### 10.3 Session Summary
- Overall score per category
- Top 3 điểm mạnh / Top 3 cần cải thiện
- Câu nào tốt, câu nào cần rework
- Gợi ý ôn luyện

#### 10.4 Progress Tracking
- Xem lại sessions lịch sử
- Progress over time per category
- "Lần này bạn cải thiện về cấu trúc câu trả lời (+18%)"

---

### MODULE 11: Partner — Talent Management

#### 11.1 Talent Pool
- Save ứng viên hay dù họ không apply job hiện tại
- Tag, note, categorize
- Khi job mới → AI suggest từ Talent Pool trước khi đăng tin công khai
- Contact request: gửi "Mời bạn xem cơ hội" → student accept/decline

#### 11.2 Reference Check
- Partner gửi reference check form cho candidate
- Candidate nhập thông tin người tham chiếu
- System gửi form cho người tham chiếu (email)
- Phản hồi tập hợp trong hồ sơ candidate

#### 11.3 Background Check Request
Partner request candidate nộp thêm tài liệu (certificate, transcript...) ở bất kỳ giai đoạn nào.

#### 11.4 Offer Management
- Tạo offer: vị trí, lương gross/net, bonus, benefits, ngày bắt đầu, deadline
- Upload offer letter template (system điền thông tin candidate)
- Student: Accept / Decline / Request extension / **Counter-offer** (nếu partner bật)
- Counter-offer flow: student propose ngược → partner accept/reject/counter lại
- Offer accepted → trigger placement record tự động

#### 11.5 Email Templates per Stage
- Partner customise email gửi candidate khi họ vào từng stage
- Variables: `{{candidate_name}}`, `{{job_title}}`, `{{company_name}}`, `{{interview_link}}`
- Preview, test send
- Default templates từ system, partner override

#### 11.6 Auto-notification Stakeholders
Khi candidate move stage → notify: candidate (nếu applicable) + assignee vòng tiếp + partner admin.

#### 11.7 Analytics
- Pipeline funnel, hiring velocity, drop-off rates
- Source analysis (organic / sponsored / passive search / referral)
- Recruiter performance (candidates handled, time-to-respond)
- Job performance
- **Benchmark:** "Bạn chậm hơn 40% so với trung bình ngành"
- Offer acceptance rate
- **Export tất cả reports → Excel**

---

### MODULE 12: Passive Talent Discovery (Partner)

#### 12.1 Profile Search
- Tìm theo: ngành, năm học, skills, location, trạng thái tìm việc, tier
- AI suggest: "Cho job Data Engineer này, đây là 10 sinh viên phù hợp nhất"
- Consent-first: chỉ hiện profile students bật passive visibility
- Anonymized: tên ẩn đến khi contact accepted
- Quota: per package (prevent spam)

#### 12.2 Contact Request
- Send message + job suggestion → student notification
- Student: view partner profile → Accept / Decline
- Accept → partner thấy full contact info
- Anti-spam: nhiều Decline liên tiếp → giảm quota partner

#### 12.3 Student Controls
- Bật/tắt passive visibility
- Blacklist companies
- Xem ai đã xem profile (theo company)
- Manage contact requests

---

### MODULE 13: Advertising System

#### 13.1 Loại quảng cáo
Sponsored Job, Banner Ad, Video Ad (15-30s), Featured Employer, Email Blast, Event Sponsorship.

#### 13.2 Targeting
Ngành học, năm học, khu vực, trạng thái tìm việc, tier user, behavior signals anonymized.  
**KHÔNG:** PII, sức khỏe, tôn giáo, chính trị, giới tính, dân tộc.

#### 13.3 Campaign Flow
Chọn loại → Targeting → Upload creative → Budget (daily cap + total) → Duration → Bid (CPM/CPC) → Preview → Submit.

#### 13.4 Approval (University cấu hình)
- Thủ công / AI-assist auto-approve / Auto (trusted partners)
- AI kiểm tra: nội dung, targeting, creative quality, brand safety

#### 13.5 Campaign Management
Dashboard: impressions, clicks, CTR, apply starts, CPJ. Pause/resume/stop, A/B testing, budget alerts. **Export → Excel.**

#### 13.6 Bắt buộc
Label "Được tài trợ" / "Quảng cáo" trên mọi sponsored content. User report ad. University disable bất kỳ lúc.

---

### MODULE 14: Events (Toàn diện & Thực tế)

**Sự kiện có rất nhiều kịch bản khác nhau — hệ thống phải cover tất cả.**

#### 14.1 Loại sự kiện

| Loại | Ví dụ thực tế |
|------|--------------|
| **Career Fair** | VinUni Spring Career Fair — nhiều công ty, nhiều gian hàng, onsite |
| **Company Day** | FPT Company Day — 1 công ty present, limit 100 người, free |
| **Workshop** | AI Workshop — 30 người, paid 200k, chọn ca sáng/chiều |
| **Webinar** | Online talk — unlimited slots, link Zoom sau khi đăng ký |
| **Networking Dinner** | Invitation-only, VIP, partner pays sponsorship |
| **Hackathon** | 48h, team registration, prize pool |
| **Mentorship Session** | 1-on-1, booking individual slot |
| **Info Session** | Company presentation + Q&A, free registration |

#### 14.2 Event Creation (University hoặc Partner)

**Creator:** University admin HOẶC Partner (cần university duyệt — hoặc AI auto-approve nếu bật).

**Basic info:**
- Title, description (rich text), type
- Organizer (university / partner / co-organized)
- Tags (AI, Tech, Finance, Marketing...)
- Cover image + gallery photos
- Agenda: time slots với speakers

**Format:**
- Onsite only: địa điểm cụ thể (building, room, address), capacity tổng
- Online only: platform (Zoom / Meet / Teams / other), link phân phối sau khi đăng ký
- Hybrid: vừa onsite vừa online, capacity riêng mỗi loại

**Visibility:**
- Public (hiển thị kể cả guest chưa đăng nhập)
- Authenticated only
- VinUni Students only
- Invitation only (partner gửi link trực tiếp)

#### 14.3 Ticket Configuration

**Multiple ticket types per event:**

```
Event: FPT AI Workshop
├── Ticket "Standard — Sáng (9:00-12:00)"
│   ├── Giá: 200,000₫
│   ├── Capacity: 30
│   ├── Available: [22 slots còn lại]
│   └── Sale period: đến 20/07 23:59
├── Ticket "Standard — Chiều (14:00-17:00)"
│   ├── Giá: 200,000₫
│   ├── Capacity: 30
│   └── Available: [8 slots còn lại]
├── Ticket "VIP (cả ngày + networking dinner)"
│   ├── Giá: 500,000₫
│   ├── Capacity: 10
│   └── Available: [3 slots còn lại]
└── Ticket "VinUni Students — Free" (chỉ Verified Student tier)
    ├── Giá: 0₫
    ├── Capacity: 20
    └── Require: VinUni Student tier
```

**Ticket settings per type:**
| Setting | Mô tả |
|---------|-------|
| Price | 0 (free) hoặc số tiền cụ thể |
| Capacity | Số lượng tối đa |
| Eligibility | Tất cả / Tier cụ thể / Invitation only |
| Sale period | Ngày mở bán + ngày kết thúc |
| Per-person limit | Tối đa X vé mỗi người (thường 1-2) |
| Early bird price | Giá ưu đãi đến ngày X, sau đó normal price |
| Promo code | Code giảm giá (%, fixed amount, hoặc free) |
| Transfer allowed | Có thể cho người khác vé không |
| Refund policy | No refund / Full refund đến X ngày / Partial |

#### 14.4 Seat Selection (Onsite Events)

Với event có ghế ngồi được đánh số:
- Partner/University upload sơ đồ chỗ ngồi (venue map)
- Đánh dấu từng ghế: available / blocked / VIP section
- Khi đăng ký: student chọn ghế trực tiếp trên map
- Ghế đã chọn → lock 10 phút trong lúc thanh toán
- Confirmed → ghế được đặt tên người

**Với event không có ghế đánh số (standing/theater):**
- Chỉ chọn ticket type, không cần chọn ghế

#### 14.5 Waitlist Management

Khi ticket type đã hết:
- Student đăng ký waitlist cho ticket type đó
- Nếu ai cancel → slot tự động offer cho người đầu waitlist
- Người đầu waitlist có 24h để confirm, không confirm → next person
- Student xem vị trí trong waitlist: "Bạn đang ở vị trí #3"

#### 14.6 Registration Flow (Paid)

```
1. Chọn ticket type + số lượng
2. Chọn ghế (nếu seat map enabled)
3. Review đơn hàng: ticket × số lượng = tổng
4. Áp dụng promo code (nếu có)
5. V1 chọn Bank transfer / Manual confirmation. VNPay / MoMo là gateway adapter sau này.
6. Thanh toán hoặc gửi bằng chứng chuyển khoản → Confirmation sau khi được xác nhận
7. Nhận email: QR code ticket + event details + thêm vào calendar
```

**Free ticket:**
```
1. Chọn ticket type (free)
2. Confirm đăng ký
3. Nhận email: QR code + event details + add to calendar
```

**Bank transfer (manual confirm):**
- Student nhận thông tin chuyển khoản + order ID
- Admin university/partner xác nhận receipt manually
- Sau confirm → QR ticket được gửi

#### 14.7 Online Event — Link Management

- Link Zoom/Meet **chỉ gửi cho người đã đăng ký và được confirmed**
- Link gửi qua email: 1 ngày trước + 1 giờ trước
- Link không public trong event page
- Partner/University có thể regenerate link nếu bị leak
- Giới hạn: mỗi link chỉ dùng được từ 1 device / 1 account (nếu cần, tuỳ chọn)

#### 14.8 Check-in Management (Onsite)

- **QR code digital ticket** trong email + in-app
- Staff scan QR tại cửa → tick attendance
- Multiple entry points: nhiều staff scan cùng lúc
- Real-time attendance count: organizer thấy "78/100 đã vào"
- Late arrival: vẫn scan được
- No-show tracking: sau event, xem ai đăng ký nhưng không đến

#### 14.9 Partner Event — Registration & Roles

**Ai tạo event:**
- University → auto-approved, live ngay
- Partner → pending university review (hoặc AI auto-approve nếu bật)

**Partner roles trong event:**
- **Organizer:** Company Day, Workshop (partner chủ trì)
- **Sponsor:** Logo placement theo tier tại event của university
- **Exhibitor:** Gian hàng tại Career Fair

**Career Fair specifics:**
- University tạo fair event
- Partner đăng ký booth: submit request → university approve
- Mỗi booth có: company name, description, available positions, QR code riêng
- Student visit booth → scan QR → auto-connect (thấy job listings của company đó)
- Student "bookmark" company tại fair → nhận notification về job mới từ company đó

#### 14.10 Sponsor Tiers

| Tier | Benefits |
|------|---------|
| Platinum | Logo lớn nhất, announcement 3 lần, booth vị trí prime |
| Gold | Logo lớn, announcement 2 lần, booth vị trí tốt |
| Silver | Logo vừa, announcement 1 lần, booth standard |
| Bronze | Logo nhỏ, không announcement |

#### 14.11 Post-Event

- **Recording/Materials:** Upload video recording + presentation files → send link đến attendees
- **Certificate:** Auto-generate PDF certificate of attendance (tên, tên event, ngày, ký tên organizer)
- **Post-event survey:** Auto-send form rating event (1-5 sao + text)
- **Recap page:** Event page chuyển sang "Đã diễn ra" với summary + media

#### 14.12 Event Analytics

| Metric | Mô tả |
|--------|-------|
| Registered | Tổng đã đăng ký per ticket type |
| Attended | Đã check-in |
| No-show rate | % đăng ký nhưng không đến |
| Revenue | Tổng thu từ paid tickets |
| Satisfaction score | Từ post-event survey |
| Waitlist size | Còn bao nhiêu người chờ |
| Source | Từ đâu biết event (referral, email, platform...) |

**Export:** Danh sách attendees → Excel (chọn fields: tên/tier/ticket type/payment status/attendance).

#### 14.13 Event Approval Flow (University Setting)

```
Toggle: "Duyệt sự kiện của Partner"
  ├── OFF: Partner events auto-approved (không cần review)
  ├── AI-assist: AI kiểm tra nội dung → auto-approve nếu pass / human review nếu flag
  └── Manual: Mọi partner event cần moderator duyệt

AI kiểm tra event:
  ├── Nội dung phù hợp (không spam, không misleading)
  ├── Thông tin đầy đủ (có venue/link, có agenda)
  ├── Giá vé hợp lý (so sánh với lịch sử)
  └── Targeting phù hợp (không vi phạm policy)
```

---

### MODULE 15: Company Reviews & Reputation

- Ai được review: đã apply / đã phỏng vấn / đã làm intern
- Components: Overall + Culture + Interview + Work-life + Learning (1-5 sao), Title, Pros, Cons, Advice, Anonymous option
- AI sentiment analysis: detect fake/spam reviews
- Moderation: AI flag → human final decision
- Partner request xem xét lại (không tự xóa)
- **Export reviews → Excel** (University admin)

---

### MODULE 16: Interview Q&A Community Bank

- Sau phỏng vấn → sinh viên được invite đóng góp câu hỏi
- Anonymous, moderated
- Upvote, filter theo level/thời gian
- AI Interview Simulator dùng bank này để realistic hơn
- Export per company (University admin)

---

### MODULE 17: Mentorship & Alumni Network

#### 17.1 Alumni Network
- Auto-upgrade sang Alumni tier sau graduation date
- Browse jobs (limited), alumni events, alumni directory
- Return as mentor

#### 17.2 Mentorship Program
- Mentor registration: ngành, experience, expertise areas, availability
- Verified bởi university
- Mentee browse + send request với context
- Session: video link tự động, 30-60 phút
- Post-session: rate cả hai chiều
- University: số sessions, matching rate, satisfaction score

---

### MODULE 18: University Admin — Quản trị

#### 18.1 Moderation Queue
- Partner reg, job posts, reviews, ad campaigns, events (nếu cần duyệt), flagged content
- SLA countdown (xanh → vàng → đỏ)
- AI suggestion (human final say, audit cả AI suggestion + human decision)
- Bulk actions, required rejection reason

#### 18.2 AI Fraud Detection
- Flag CV fabricated (dates overlap, unknown institution)
- Flag documents chỉnh sửa (metadata)
- Flag behavior anomaly (apply hàng trăm jobs/phút)
- Flag duplicate accounts
- Không auto-block — flag để moderator review
- Confidence chỉ hiện trong admin panel

#### 18.3 AI Bias Detection trong JD
- Scan khi partner submit
- Flag discriminatory language, suggest alternatives
- Partner có thể ignore hoặc fix
- University policy: bắt buộc fix / chỉ warning

#### 18.4 Partner Management
- Trust levels: Standard / Trusted
- Partner health score (job quality + candidate feedback + report rate + payment)
- Activity log
- **Export → Excel (chọn fields)**

#### 18.5 User Management
- Filter theo tier, status, date
- Change tier, grant subscription, suspend/restore, merge duplicates
- **Export → Excel (chọn fields)**

#### 18.6 Revenue & Billing
- Monthly dashboard
- Invoices per partner
- Subscription tracking
- **Export financial reports → Excel**

---

### MODULE 19: Excel Export System

**Nguyên tắc:** Mọi danh sách dữ liệu quan trọng đều có thể export. User chọn fields trước khi export.

#### 19.1 Field Selection UI

Khi bấm "Xuất Excel" → Modal hiện:
```
Chọn các trường muốn xuất:
[✓] Tên ứng viên        [✓] Email
[✓] Trạng thái          [ ] Số điện thoại
[✓] Vòng hiện tại       [✓] Ngày ứng tuyển
[✓] Match score         [ ] Scorecard chi tiết
[✓] Nguồn              [✓] Tags
[ ] Notes nội bộ        [✓] CV link

[Lưu preset này]  [Xuất Excel]
```

- Preset: lưu cấu hình export để dùng lại
- Max 50,000 rows per export
- Format: .xlsx với header, auto-width columns, header bold

#### 19.2 Export per Module

| Module | Data | Available to |
|--------|------|-------------|
| Applications | Candidate info, status, stage, scorecard, notes, source | Partner |
| Job Listings | Title, dept, status, apps count, dates, pipeline | Partner |
| Talent Pool | Profile, skills, match scores, tags | Partner |
| Ad Campaigns | Name, type, targeting, metrics, spend | Partner |
| Events - Attendees | Name, tier, ticket type, payment, check-in | Partner + University |
| Partners | Name, status, package, health score, activity | University |
| Users | Name, tier, email, date, subscription, status | University |
| AI Usage | Task type, cost, provider, date | University |
| Financial Reports | Revenue by source, date, partner | University |
| Placement Records | Student, company, role, salary, date | University |
| Scorecards | Candidate, job, round, scores, recommendation | Partner |
| Review Data | Company, rating, text (anonymized) | University |
| Audit Logs | Actor, action, resource, timestamp, IP | University |

---

### MODULE 20: Career Outcomes & University Intelligence

#### 20.1 Placement Tracking
Offer accepted → placement record. University confirm sau khi student start việc.

#### 20.2 Post-Graduation Surveys
Auto-send: 3 tháng, 6 tháng, 1 năm sau tốt nghiệp. Nội dung: có việc, loại công việc, lương, satisfaction, skills used.

#### 20.3 University KPI Dashboard
Placement rate, avg salary, time-to-hire, field alignment, satisfaction. Breakdown per khoa/ngành/cohort. **Export → Excel.**

#### 20.4 Accreditation Reports
Auto-generate theo chuẩn kiểm định. Export PDF / Excel.

#### 20.5 Curriculum Intelligence
AI tổng hợp: skill demand trends từ JDs, skill gaps từ match scores, department comparison. "83% job rejections ngành CS cite thiếu cloud skills." Chỉ visible university + faculty.

---

### MODULE 21: Notifications & Communications

#### 21.1 Events per persona

**Student:** Application status, interview (schedule/reminder/cancel), offer received, contact request từ partner, event reminder (1 tuần/1 ngày/1 giờ), ticket confirmation, job alert, waitlist promoted, mentor request, survey invitation, subscription expiring, proactive AI nudges.

**Partner:** New application, interview confirmed/declined, offer response, job approved/rejected, campaign live/ending/budget alert, event registration update, contact request accepted, SLA warnings per pipeline stage.

**University:** Registration pending, SLA alerts, AI provider issues, budget alerts, flagged content, event pending approval.

#### 21.2 Channels
- In-app notification bell + badge
- Email (transactional)
- Browser push (opt-in)
- Weekly digest email
- SMS (optional, critical only: interview confirmed, offer received)

#### 21.3 User Preferences
Per notification type: on/off. Per channel: email/in-app/push/SMS. Do not disturb hours.

---

### MODULE 22: Phỏng vấn (Interview Management)

#### 22.1 Student
- Lịch phỏng vấn upcoming với countdown
- Confirm / Đề xuất lịch khác (self-scheduling)
- Info: loại, địa điểm/link, interviewer (nếu partner share)
- Nhắc nhở: 1 ngày + 1 giờ trước
- Post-interview feedback: cảm nhận
- **AI Pre-Interview Brief:** Brief ngay trước: company overview, likely questions per JD, tips per role type

#### 22.2 Partner
- Schedule với self-scheduling hoặc partner pick
- Google Meet / Zoom link tự động
- Calendar invite tự động
- **AI Interview Guide:** Generate câu hỏi per candidate dựa trên CV gap vs JD
- Scorecard per stage (cấu hình sẵn từ pipeline)
- Bulk schedule

---

### MODULE 23: Analytics & Intelligence

#### 23.1 Market Intelligence (University, AI-powered)
- Trending skills từ JDs (rolling 90 ngày)
- Salary trends per industry
- Hiring momentum per industry
- Early warning: "React Native jobs giảm 30% trong 2 tháng"
- Chỉ visible cho university admin + career counselors

#### 23.2 AI Predictions (Research/Advisory)
- Time-to-fill prediction per job type
- Interview no-show risk (behavior signals)
- Offer acceptance probability (anonymized patterns)
- Application quality forecast (từ JD clarity score)

---

### MODULE 24: VinUni Integrations

#### 24.1 Student Information System (SIS)
- Auto-sync enrollment status
- Auto-sync graduation date → trigger Alumni tier upgrade
- Pull: major, faculty, year, student ID
- Push: placement records → SIS
- Daily sync hoặc event-driven
- Manual override bởi admin

#### 24.2 VinUni Identity Provider (SSO)
- OIDC / SAML 2.0 với VinUni IdP
- Auto-verify + auto-fill profile
- No separate registration cho VinUni students
- Token refresh aligned với VinUni policy

#### 24.3 Academic Calendar
- Import academic calendar
- Job alerts: không push spam trong tuần thi cuối kỳ
- Internship suggestions: 2 tháng trước nghỉ hè
- Event scheduling: tránh conflict lịch thi

#### 24.4 Faculty Dashboard (Read-only)
- Giảng viên, trưởng khoa: xem placement stats ngành mình
- Curriculum intelligence insights
- Aggregate only (không thấy individual data)

---

## 6. AI System — Thiết kế chi tiết

### 6.1 Triết lý

AI phải: giải quyết pain point thực sự, output actionable, không tạo thêm việc, transparent về limitations, private-by-default. **Không phải decoration.**

### 6.2 AI Features Map

| Feature | Persona | Mô tả |
|---------|---------|-------|
| CV Extraction (multi-modal) | Student | Parse mọi format kể cả ảnh |
| CV Studio Drafting | Student | Tạo CV từ profile/template/raw notes |
| CV Template Fill | Student | Điền template đã chọn từ profile, uploaded CV extraction, CV hiện có |
| CV Bullet Generation | Student | Biến raw notes thành bullet chuyên nghiệp |
| CV Section Rewrite | Student | Rewrite theo instruction tự nhiên |
| CV Quality Analysis | Student | Strengths + improvement hints |
| CV Optimization per Job | Student | Tailored suggestions cho job cụ thể |
| ATS Compatibility Check | Student | Có pass ATS không |
| CV Fabrication Check | Student/University | Cảnh báo claim thiếu bằng chứng hoặc mâu thuẫn |
| Semantic Job Search | Student | Intent-based search |
| Job Match Scoring + Explanation | Student | CV ↔ JD match |
| JD Red Flag Detection | Student | Warn về JD đáng lo |
| AI Q&A on JD | Student | Giải thích nội dung JD |
| Application Success Estimate | Student | Cao/Trung bình/Thấp (không raw %) |
| Career Path Advisor | Student | Lộ trình từ profile |
| Career Path Simulation | Student | "Nếu học X, tôi có thể làm gì?" |
| Skill Gap Analysis | Student | Thiếu gì so với target |
| Skill Learning Path | Student | Lộ trình học với resources + timeline |
| Cover Letter Generator | Student | Draft từ CV + JD |
| Cover Letter Reviewer | Student | Review bản user viết |
| Professional Email Drafter | Student | Email gửi employer |
| Salary Negotiation Tips | Student | Tips cụ thể cho offer |
| Pre-Interview Brief | Student | Brief trước phỏng vấn |
| Interview Simulation | Student | Mock interview AI |
| Peer Benchmarking (anonymous) | Student | So sánh với cohort VinUni |
| Proactive Nudges | Student | Context-aware reminders |
| JD Writer | Partner | Viết JD chuyên nghiệp |
| JD Bias Checker | Partner | Detect discriminatory language |
| JD Quality Predictor | Partner | Dự báo chất lượng ứng viên từ JD |
| Candidate Ranking | Partner | Rank ứng viên theo fit |
| Interview Guide Generator | Partner | Câu hỏi per candidate per gaps |
| Scorecard Assistant | Partner | Suggest scores từ interview notes |
| Talent Suggestions | Partner | Gợi ý từ passive pool |
| Offer Acceptance Probability | Partner | Advisory, không raw % |
| Time-to-fill Prediction | Partner | Advisory |
| Stage Transition Email Drafter | Partner | Draft email thay đổi stage |
| Ad Creative Checker | Partner | Check trước submit |
| Event Content Checker | Partner | Check event content trước submit |
| Fraud Detection | University | Flag suspicious profiles/docs |
| Content Moderation | University | Flag reviews, ads, profiles |
| Bias Detection in JDs | University | Systematic check |
| Market Intelligence | University | Skill trends, hiring momentum |
| Curriculum Intelligence | University | Skill gap → curriculum feedback |
| Placement Prediction | University | Forecast per cohort |
| No-show Risk Detection | University/Partner | Behavior signal-based |

### 6.3 AI Safety Rules (bất biến)

- **Không expose với non-superadmin:** provider names (OpenAI, Gemini...),
  concrete model ids/model names, API keys, base URLs, token counts, latency,
  confidence scores raw, OCR/embedding internals, prompt text, internal status
  codes
- **Write actions:** AI propose → user explicit confirm → execute → audit log
- **Human final say:** Mọi AI recommendation là advisory
- **Moderation:** AI suggest, human approve/reject
- **Fraud detection:** AI flag, human decide
- **Sponsored content:** Label bắt buộc, không bỏ được
- **Privacy:** Không cross-contaminate data giữa organizations

---

## 7. Yêu cầu phi chức năng

### 7.1 Performance
- Homepage (cold): < 2.0s FCP
- API: p50 < 200ms, p95 < 500ms
- AI chat first token: < 3s (streaming)
- Semantic search: < 800ms
- Export Excel < 30s (với 10k rows)

### 7.2 Reliability
- Uptime: 99.5% monthly
- Database: daily backup, PITR 7 ngày
- AI failover: < 5s khi primary down
- Graceful degradation: core features hoạt động khi AI down

### 7.3 Scalability
- Target: 5,000 concurrent users
- Design capacity: 20,000
- Storage: 500,000+ CVs + assets

### 7.4 Security
- JWT + secure refresh
- API key encryption AES-256
- CV data: encrypted at rest
- RBAC enforcement ở service layer
- Rate limiting per IP + user + endpoint
- OWASP Top 10
- CV download watermark: tên partner + timestamp

### 7.5 Accessibility
- WCAG 2.1 AA minimum
- Keyboard navigation complete
- Screen reader compatible
- Color contrast ≥ 4.5:1

### 7.6 Internationalization
- Vietnamese primary, English secondary
- Date/time per locale
- Currency: VND

### 7.7 Privacy
- Data minimization
- CV anonymization per policy
- Behavior tracking: consent-based
- Ad targeting: không PII, không sensitive categories
- Right to erasure
- Consent versioning

---

## 8. Kiến trúc kỹ thuật

### Frontend
- Next.js 15 App Router, TypeScript strict
- Tailwind CSS v4 + CSS custom properties (theme từ server config)
- Phosphor Icons (duotone)
- RSC/server fetch cho initial read; TanStack Query cho client-interactive surfaces (CV Studio, pipeline, chat, workflow builder, filters)
- vi/en server-side i18n
- PWA: installable web app

### Backend
- FastAPI, Python 3.12+
- SQLAlchemy async 2.x, Pydantic v2
- PostgreSQL 16+
- Redis 7 + Celery 5
- JWT + OIDC
- uv package manager

### AI Infrastructure
- Provider-agnostic gateway
- Per-task model config từ DB
- Load balancing + fallback chain
- Cost tracking per provider per task
- Local model (Ollama)
- Streaming SSE cho chat
- pgvector hoặc dedicated vector store

### Integrations
- VinUni IdP: OIDC / SAML 2.0
- VinUni SIS: REST API / DB sync
- Calendar: Google Calendar API, Microsoft Graph
- Video: Google Meet / Zoom link gen
- Payment: VNPay, MoMo, ZaloPay (sau này)
- Email: transactional email service

### Infrastructure
- Frontend: Vercel hoặc Docker + Nginx
- Backend: Docker + Gunicorn/Uvicorn
- Database: Managed PostgreSQL
- Redis: Managed Redis
- File storage: S3-compatible
- CDN: Cloudflare

---

## 9. Design System

### Brand (Default — University Admin thay được)
- Visual source of truth is `docs/DESIGN.md`.
- Default VinUni tokens: VinUni Blue `#2e548a`, VinUni Red `#c83538`,
  official extended palette, Plus Jakarta Sans app typography. Montserrat is
  legacy/brand-collateral-only when embedded in original assets.
- University admin may configure tenant branding later, but the initial platform
  must use the canonical VinUni design tokens from `docs/DESIGN.md`.

### Visual Principles
- Dark sidebar, light content area
- Dashboard: số liệu thực, không placeholder, không marketing copy
- Clean, professional, trustworthy
- Mobile-responsive + PWA
- AI output = action driver, không decoration

### Dashboard Design Rules
- **Cards:** icon màu + số lớn + label nhỏ + trend arrow (↑/↓ so với kỳ trước)
- **Charts:** Line charts cho time-series, Funnel cho pipeline, Bar cho comparison
- **Tables:** Sort + filter inline, action buttons right-aligned, row hover highlight
- **Status badges:** Color-coded nhất quán (xanh = active, vàng = pending, đỏ = alert)
- **Empty states:** Có illustration + CTA, không để trống blank
- **Loading states:** Skeleton loaders, không spinner fullscreen

---

---

## M25 — In-app Institutional Messaging

**Mục tiêu:** Giao tiếp real-time giữa nhà trường, partner và sinh viên — không phải peer-to-peer student chat.

### Ma trận quyền nhắn tin

| Người gửi | Người nhận | Loại |
|-----------|-----------|------|
| University Admin/Staff | Bất kỳ user | Direct + Broadcast + Group |
| Partner Admin/Member | Ứng viên (trong context tuyển dụng) | Direct |
| Partner Admin/Member | Team nội bộ | Group + Direct |
| Student | Partner (chỉ reply application context) | Reply only |
| Student | University | Direct (support/inquiry) |
| Student → Student | **KHÔNG BAO GIỜ** | ✗ |

### Tính năng

**Conversation types:**
- Direct message: 1-1 giữa hai người
- Group: University tạo nhóm ("Sinh viên K2024", "Ứng viên Job X")
- Broadcast: University gửi một chiều → tất cả students / all alumni / segment tùy chỉnh

**Message types:**
- Text (markdown lite: bold, italic, link)
- File attachment (PDF, DOCX, image — max 20MB)
- System message (auto-generated: "Bạn được mời vào vòng phỏng vấn")
- Voice note (Phase sau)

**UX:**
- Chat panel slide-in từ phải (không mở tab mới)
- Unread count badge trên avatar/header
- Read receipts (sent ✓, delivered ✓✓, read ✓✓ blue)
- Message search trong conversation
- Pin important messages
- Emoji reactions (basic: 👍 ❤️ 😊 🎉)
- Reply-to message (thread-lite, không nested)
- Message edit/delete (within 10 mins)

**Anti-spam:**
- Partner → Student: max 3 messages/day nếu không có application đang active
- Student có thể block sender → reported to university admin
- Bulk message by partner (>50 students at once): cần university approval

---

## M26 — Visual Workflow Builder (Automation Rule Engine)

**Mục tiêu:** University admin kéo-thả để tạo luồng xử lý tự động — thay thế việc bật/tắt switch lẻ tẻ.

### Canvas (React Flow)

**Node types:**
| Node | Icon | Mô tả |
|------|------|--------|
| Trigger | ⚡ | Điểm vào: "Student registers", "Application submitted", "Payment received", "File uploaded", "Scheduled (cron)" |
| Condition | 🔀 | If/else: "AI fraud score > 80", "Tier == VinUni Student", "Email domain @vinuni.edu.vn" |
| AI Process | 🤖 | Chạy AI task: fraud check, CV extraction, moderation, scoring |
| Human Review | 👤 | Đưa vào queue với SLA, assign đến role |
| Action | ⚙️ | Gửi email, đổi status, webhook, gán role, tạo notification |
| Delay | ⏱ | Wait N hours/days |
| Merge | ⊕ | Gộp parallel paths (AND = tất cả xong, OR = một trong hai) |
| End | 🔴 | Kết thúc flow |

**Preconfigured flow templates:**
- Student registration verification (email → fraud AI → condition → human review hoặc auto-approve)
- Application auto-screening (submit → AI score → high: auto-advance, low: human review)
- Payment failure recovery (fail → retry 3x → downgrade → notify)
- Content moderation pipeline (submit → AI moderate → if flagged → human → approve/reject)
- Partner onboarding (register → verify documents → AI check → approve → welcome email)

**Rules:**
- Max 50 nodes per flow
- DAG only (no cycles) — enforced frontend + backend
- Chỉ university admin create/edit flows
- DRAFT → TEST (dry-run) → ACTIVE
- Running flows immutable: edit → tạo version mới
- Full execution log per run: từng node, decision, timestamp
- Failed executions: admin có thể inspect + replay

---

## M27 — Bulk Apply / Job Cart

**Mục tiêu:** Sinh viên chọn nhiều jobs, AI tự viết cover letter riêng cho từng job, apply hàng loạt.

### Job Cart

- Cart icon ở navigation (badge hiển thị số job đã chọn)
- Thêm job vào cart: button "Thêm vào danh sách" trên job card/detail
- Cart max: 20 jobs tại một thời điểm
- Cart view: list jobs đã chọn + AI match % + AI-generated cover letter preview

### AI Cover Letter Generation

- AI đọc: CV của student + JD của job + company description
- Output: cover letter ~200-300 words, tiếng Việt hoặc tiếng Anh (theo ngôn ngữ JD)
- Student xem preview → có thể edit → confirm
- Mỗi cover letter khác nhau (không copy-paste giữa các job)
- AI cost: 3 credits per cover letter generation

### Apply flow

1. Chọn CV muốn dùng (nếu nhiều CV)
2. Review cover letters (edit từng cái nếu muốn)
3. [Apply All Selected] → confirmation modal hiển thị danh sách
4. Apply → jobs bị xóa khỏi cart → vào Applications

### Quota (anti-spam)

| Tier | Free Weekly Apply | Paid Pack |
|------|-------------------|-----------|
| VinUni Student | 20 applies/week | 50/week (mua thêm) |
| Alumni | 10 applies/week | 30/week |
| External | 5 applies/week | 20/week |
| General | 3 applies/week | 10/week |

- Quota reset mỗi Thứ Hai 00:00 (không carry over)
- Unused quota không mang sang tuần sau
- User thấy "Bạn còn X lượt apply tuần này" trên cart page

---

## M28 — Real-time Presence & Activity Audit

**Mục tiêu:** Partner admin biết team đang làm gì; University admin có system-wide audit trail.

### Partner Admin View

**Team Presence:**
- Xanh = online ngay bây giờ
- Vàng = away (không có action >5 min)
- Xám = offline (last seen: "Hôm nay lúc 14:30" hoặc "Active hôm nay")
- Không show exact timestamp với student (privacy) — chỉ buckets

**Live Activity Feed (partner internal):**
```
Nguyễn Văn A       viewed [Trần Thị B]'s profile    2 mins ago
Lê Hoàng C         advanced [Phạm Văn D] → Technical Interview    5 mins ago
System             5 new applications received for [Data Analyst]  1 hour ago
Nguyễn Văn A       downloaded CV of [Ứng viên #1234]              2 hours ago
```

**Audit filter:** by member, by date range, by action type, exportable to Excel

### University Admin View

**System Activity Feed:**
- New partner registrations (waiting review)
- New jobs posted (waiting moderation)
- AI cost spikes
- Failed payments
- Flagged content (high confidence)
- SIS sync results

**Full Audit Search:**
- Actor (any user) + Action + Date range + IP (hashed)
- Export to Excel
- Retention: 2 years

### Student Self-view

- Xem lịch sử hành động của bản thân: applications, AI chat sessions, events đã đăng ký
- KHÔNG xem được activity của người khác

---

## M29 — Video Interview Integration

**Mục tiêu:** Lên lịch và tham gia phỏng vấn video trực tiếp từ platform.

### Tính năng

- Khi schedule interview → chọn "Video Interview" → platform tự generate meeting link
- Providers cấu hình qua university AI Settings: Google Meet API / Zoom API / Built-in WebRTC
- Link tự động gắn vào interview record + email invite
- Cả interviewer + candidate thấy "Tham gia phỏng vấn" button từ interview detail page
- One-click join: không cần copy link thủ công

**Recording (optional, dual consent):**
- Interviewer bật "Ghi lại buổi phỏng vấn" khi tạo interview
- Candidate thấy thông báo "Buổi phỏng vấn sẽ được ghi hình" + phải click [Đồng ý] trước khi tham gia
- Nếu không đồng ý → vẫn vào được interview, nhưng recording không bật
- Recording link gắn vào scorecard sau buổi
- Retention: 30 ngày, sau đó tự xóa

---

## M30 — Smart Reminders & Enhanced Push

**Mục tiêu:** Push notifications đến trình duyệt ngay cả khi user không mở app.

### Reminder types

**Student:**
- Application deadline in 3 days / 1 day
- Interview starts in 24h / 1h
- New job matches your profile (weekly, Tuesday 9am)
- Event starts in 1h
- Profile completion nudge (30 days after register if < 70%)

**Partner:**
- New applications received (batch: immediate / hourly / daily)
- SLA overdue: immediately khi stage vượt SLA
- Subscription expiring in 7 days / 3 days / 1 day
- Ad campaign budget at 80%

**University:**
- Moderation queue items > SLA (4h for high priority)
- Partner registration waiting > 48h
- AI cost > 80% daily budget

### Settings

- User chọn per-category: Push / Email / In-app / Off
- Digest frequency: immediate / daily / weekly
- Do not disturb: set quiet hours (e.g., 22:00 - 08:00)
- Web Push cần explicit permission click — không auto-request

---

## M31 — Partner Flexible Dashboard

**Mục tiêu:** Partner customize dashboard giống Notion blocks — kéo thả, resize.

### Available Widgets

| Widget | Sizes | Mô tả |
|--------|-------|--------|
| Pipeline Summary | M, L | Kanban mini view by job |
| Recent Applications | S, M | Latest N applications |
| Active Jobs | S, M | Jobs đang mở + applicant count |
| Upcoming Interviews | M | Calendar view next 7 days |
| Team Activity | M | Live feed (nếu có permission) |
| AI Match Scores | M, L | Distribution chart |
| Quota Usage | S | Job posts, passive search, etc. |
| Company Profile Completion | S | Checklist với % |
| Quick Stats | S | Today's numbers |
| Event Summary | M | Upcoming events partner đang host |

- Grid: 12 columns, widgets snap to grid
- Drag to reorder, drag to resize (S/M/L presets, không free-form)
- Layout saved per user (Zustand persist → backend sync)
- [Reset to default] button
- Mobile: single column, widgets stack vertically, order preserved

---

## M32 — AI Provider Hub (Visual Management)

**Mục tiêu:** University admin quản lý nhiều AI providers qua giao diện visual — không phải form settings khô khan.

### Provider Card UI

Mỗi provider = 1 card hiển thị:
- Provider name + logo (chỉ trong admin panel)
- Status indicator (🟢 healthy / 🟡 degraded / 🔴 down)
- Real-time response time (last 5 calls avg)
- Cost this month
- Models available
- Tasks assigned
- "Test" button → gửi test prompt, hiển thị response time + sample output

### Routing Configuration

**Priority mode:** Drag thứ tự → Provider 1 là primary, 2 là fallback, 3 là fallback của fallback
```
[Provider A ↕] [Provider B ↕] [Provider C ↕]
Primary         Fallback-1      Fallback-2
```

**Round-robin mode:** Slider weight cho từng provider
```
Provider A: ████████ 60%
Provider B: ████ 30%
Provider C: ██ 10%
[Save weights]
```

**Task-based routing:** Table view — chọn provider khác nhau cho từng task type
```
cv_extraction    → [Provider A  ▼]
chat             → [Provider B  ▼]
embedding        → [Provider C  ▼]
moderation       → [Provider A  ▼]
```

- Health check auto-runs every 60s
- On unhealthy: auto-skip to next in fallback chain (với alert email)
- Cost cap per provider per day (configurable)

---

## M33 — Document Knowledge Base (RAG)

**Mục tiêu:** University admin và partner có thể upload tài liệu nội bộ (PDF/DOCX) → hệ thống chunk + embed → lưu pgvector → chatbot trả lời câu hỏi từ tài liệu đó với source citation rõ ràng.

### Personas & Quyền upload

| Persona | Loại knowledge base | Ví dụ tài liệu | Ai được truy cập |
|---------|-------------------|----------------|-----------------|
| University Admin | **Platform KB** | FAQs, hướng dẫn đăng ký, chính sách sử dụng, học bổng | Tất cả authenticated users |
| Partner Admin | **Partner KB** | Company handbook, culture deck, quy trình onboarding, hướng dẫn phỏng vấn | Students browse company profile + đang/đã apply vào jobs của partner |
| Partner Admin | **Per-Job KB** | Job-specific guide, tech stack doc, case study | Students có active application vào job đó |

### File Types & Limits

- Định dạng: `PDF`, `DOCX`, `TXT`
- Kích thước tối đa/file: **50 MB**
- Tổng dung lượng per partner organization: **500 MB**
- Tổng dung lượng platform KB (university): **5 GB**
- Tối đa documents: **200** (university platform KB), **50** (per partner), **10** (per-job)

### RAG Pipeline

```
Upload File
    ↓
1. Virus scan
    ↓
2. Text extraction:
   PDF → pdfplumber (OCR fallback: Tesseract for scanned PDFs)
   DOCX → python-docx  |  TXT → direct read
    ↓
3. Chunking: paragraph-aware + sliding window
   ~512 tokens/chunk, 64-token overlap
   Each chunk carries: text + document_id + chunk_index + section_heading
    ↓
4. Embedding via university-configured AI provider (text-embedding model)
    ↓
5. Storage: chunks → knowledge_base_chunks (pgvector)
             original file → object storage (signed URL access only)
    ↓
6. Status: PROCESSING → READY / FAILED
```

### Query Flow (RAG)

```
User question (chatbot)
    ↓
1. Scope resolution by context:
   - Always: Platform KB (platform policy questions)
   - Company profile page: + Partner KB
   - Job detail page (with active application): + Per-Job KB
    ↓
2. Embed question → query vector
    ↓
3. pgvector cosine similarity → top-K chunks (K=5, max 10), filtered by permitted KB IDs
    ↓
4. Inject chunks as context into AI prompt
    ↓
5. Answer with citations: "Theo [Tên tài liệu] — [Phần X]..."
    ↓
6. Return answer + cited source list
```

### Source Citation (bắt buộc)

- Mỗi câu trả lời phải liệt kê: tên tài liệu + section (không bao giờ expose file path/storage URL)
- Nếu không tìm thấy chunk phù hợp: "Tôi không tìm thấy thông tin về vấn đề này trong tài liệu của [Tổ chức]. Bạn có thể liên hệ trực tiếp để được hỗ trợ."

### Admin Management UI

- University: `/admin/knowledge-base` — list, upload, delete, view chunk count, preview extracted text
- Partner: `/partner/knowledge-base` — 2 tabs: Company Docs | Per-Job Docs
- Doc status badge: `PROCESSING` / `READY` / `FAILED` (hiển thị error reason)

---

## 10. Không nằm trong scope (v1)

- Native iOS / Android app (web responsive + PWA)
- Payment gateway tích hợp (invoice thủ công trước)
- Multi-institution (chỉ VinUni)
- External job board syndication
- HRIS / post-hire management
- ATS API import (Greenhouse, Workday)
- **Student → Student messaging** (KHÔNG BAO GIỜ — institutional messaging only)
- Live poll / Q&A tương tác trong event stream
- Built-in WebRTC recording (dùng external provider recording API)
- Voice notes trong messaging (phase sau)
- DOCX export từ CV Studio (PDF v1 trước; DOCX phase sau trừ khi được yêu cầu rõ)

---

## 11. Addendum — Account, Locale, Notifications, And Local AI/OCR

### 11.1 Locale And Location-Aware UX

- Product languages for v1: Vietnamese and English.
- First visit language defaults:
  - Browser language starts with `vi` OR coarse country is Vietnam → `vi`.
  - Otherwise → `en`.
- Logged-in user preference overrides detection.
- Do not require exact location for job search, security, or personalization.
- Job/event recommendations may use city-level career preference, not raw GPS.

### 11.2 Account And Device Management

Every authenticated user should have settings for:

- Profile language and timezone.
- Notification preferences by category/channel.
- Active devices/sessions with remote logout.
- Password change and security event history.
- TOTP when enabled; university staff can be required by admin policy.

Security UX must be understandable for non-technical users: "Thiết bị này", "Đăng xuất thiết bị", "Hoạt động gần đây", not raw token/session jargon.

### 11.3 Notification And Email Template Builder

University admins can manage communication templates:

- In-app, email, push templates.
- Versioned drafts and active versions.
- Locale-specific `vi` and `en` content.
- Drag/drop or block editor for email body.
- Variable chips such as `{{name}}`, `{{job_title}}`, `{{company_name}}`, `{{deadline_at}}`, `{{action_url}}`.
- Preview with sample data before activation.
- Required-variable validation before sending.

Partner admins may manage selected templates for their own pipeline stage transitions only when university policy allows it.

### 11.4 Notification Categories

Must support:

- Application lifecycle.
- Interview and offer.
- Job deadline and saved-job closure.
- CV parsing/export completion.
- AI suggestions requiring review.
- Event ticket/waitlist/certificate.
- Partner quota/package warnings.
- University moderation/SLA/admin alerts.
- Security alerts.
- Personalized job match digest.

### 11.5 Lightweight Local AI/OCR

Default local stack:

- PDF text extraction first, OCR fallback only when text extraction fails.
- OCR language: Vietnamese + English.
- Heavy OCR and large local models are disabled by default.
- AI model calls use low-cost/free aliases only for manual smoke tests.
- Unit tests and CI use offline/fake providers.

### 11.6 Additional Practical AI Features

Add as roadmap candidates, gated by eval/safety:

- Student: skill gap map from target role, learning plan, weekly opportunity digest.
- Student: CV claim checker that flags unsupported or vague claims.
- Partner: JD bias/compliance detector and interview question generator.
- Partner: candidate comparison summary with explicit non-discrimination guardrails.
- University: moderation triage, market trend summaries, accreditation report draft, failed-workflow explanation.
- Admin: notification template draft assistant, but never auto-send without confirmation.

---

## 12. Câu hỏi cần xác nhận

1. **VinUni SSO:** IdP dùng gì? (Azure AD, Google Workspace, custom LDAP?)
2. **VinUni SIS:** Hệ thống SIS là gì? Có REST API không hay cần DB-level sync?
3. **Alumni:** Sau tốt nghiệp, alumni có thể apply jobs không hay chỉ browse + mentor?
4. **External students:** Có cho phép không? Có cần verify danh tính chặt không?
5. **Payment gateway timing:** Default v1 là bank transfer/manual confirmation. Khi nào cần bật gateway thật?
6. **Seat map:** Event nào cần seat selection? VinUni có venue cố định nào không?
7. **Partner event auto-approve:** Mặc định AI-assist hay manual?
8. **Referral code:** Partner tạo referral link cho job cụ thể → student nhập → track source. Có cần không?
9. **Certificate of attendance:** Auto-generate PDF có cần chữ ký số hay chỉ digital image?
10. **Passive search quota:** Default bao nhiêu contact requests/tháng per package?
