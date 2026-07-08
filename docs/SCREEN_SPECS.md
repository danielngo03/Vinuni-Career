# Screen Specs — VinUni Career Platform

> Screen-level UX source of truth for high-value workflows. Use with `docs/DESIGN.md`.

## 1. Global App Principles

- Build work surfaces first, not marketing filler.
- Use real data, skeletons, empty states, permission states, and disabled TODO panels only when a backend contract is not ready.
- Keep dashboards dense but scannable.
- Tables must work on mobile via horizontal scroll wrapper or card layout.
- Forms validate on blur, show required indicators, support browser autofill, and show submit feedback.
- Every critical workflow has loading, empty, error, success, permission, and offline/retry states.
- No text or controls may overlap at 320, 375, 414, 768, 1024, and 1440 px.
- Use the project icon set; no emoji icons.
- Job save/favorite uses a heart icon. Bookmark is reserved for saved
  collections/resources, not the primary job-favorite action.
- Public/student routes expose quick actions in the top header (owner decision
  2026-07-07; the bottom-right floating launcher was removed): saved jobs,
  notifications, messages, and VinUni AI assistant when those actions are
  available or honestly disabled live in the header cluster, while feedback/help
  lives in the account (avatar) menu. On mobile these collapse into the top
  header/nav and must avoid overlap with sticky apply bars, footer, and mobile
  navigation. Header actions need hover/focus labels; AI may use restrained
  attention motion that respects `prefers-reduced-motion`.
- Campaign/banner surfaces distinguish paid sponsored, strategic partner, and
  VinUni-curated content. Labels must be truthful but polished.

## 1.1 Public Career Gateway

Routes: `/`, `/jobs`, `/companies`, `/events`, `/career-explore`.

> Structural reference: `docs/DESIGN_EXAMPLE.png` is the canonical composition for
> this gateway (the layout block below mirrors it). Copy its structure and
> density; apply VinUni brand tokens, real `frontend/public` assets, and
> organization `logo_url` media — never fake logos.

Purpose:

- Let guests immediately browse public opportunities, employers, and events.
- Convert students/alumni to login only when they try to apply, save, register,
  create alerts, use AI, or view restricted content.
- Support the advertising business model without hiding sponsored disclosure.
- Support guest/session-based recommendations and authenticated student
  personalization from `docs/DISCOVERY_RECOMMENDATION_ADS_SPEC.md`.

Desktop layout:

```text
Sticky header: brand, Jobs, Companies, Career Explore, Events, Employers, language, login/register
Companies nav: mega-menu with top employers, industry categories, company-size filters, strategic partner/trust card
Hero/search band: VinUni navy copy panel + real campus/product image panel
Overlay search: keyword/skill + location/work mode + primary find button
Metric strip: live aggregate only; hidden if API unavailable
Main left: public jobs list with sponsored labels and company names
Main right: employer spotlight, public event card, sponsored banner slot
Personalized rail: "Recommended for you" when guest/session or student signals exist; otherwise new/popular fallback
Lower rail: verified by VinUni, career support, skills learning, community
```

Mobile layout:

- Search appears before long copy.
- Jobs/events/company entry points are visible within the first screenful.
- Filters collapse into a sheet; no horizontal text clipping.
- Sponsored disclosure remains visible on every ad/card.

States:

- Loading: skeleton rows/cards, not blank screens.
- Empty: useful next actions such as browse events, create alert after login, or
  check companies.
- Error/offline: retry and non-blocking public navigation.
- Guest gated action: login modal preserves intent and target URL.
- Authenticated but wrong persona: explain required persona and next action.
- No active campaign: ad slot is hidden or replaced by organic content; do not
  render fake ads.

Public content rules:

- Public job rows/cards include company display name, role, location/work mode,
  key skills, posted/deadline state, and sponsored/featured labels.
- Public company/job rows use `logo_url` only when returned by backend safe
  public asset endpoints; never render raw storage paths.
- Public events show date, format/location, registration gate, and sponsor label
  when applicable.
- Company cards show verified status only if the backend says verified.
- Ad impression/click/apply-start hooks are added when advertising APIs exist.
- Guest/search/view signals update recommendations without requiring login,
  using only privacy-safe coarse session data.
- Recommended, sponsored, organic, and university-curated inventory must be
  visually distinguishable and traceable in the API payload.

## 1.2 Persona Workspace Experience Standard

Applies to every authenticated student, partner, and university screen.

Before building a screen, define:

- Persona and primary job-to-be-done.
- Data needed above the fold.
- Primary queue/list/editor/pipeline surface.
- Primary action and secondary actions.
- Permission boundaries and hidden/disabled states.
- Empty, loading, error, offline, conflict, and success states.
- Mobile layout and keyboard path.

Student workspace must prioritize:

- Navigation: signed-in marketplace top nav inherited from the public gateway,
  with student-specific items (`My Career`, `CV Studio`, `Applications`,
  `Saved`, notifications, avatar/settings). Do not default to an admin-style
  sidebar for student desktop.
- CV readiness, active CV quota, and job-fit next actions. Profile readiness is
  secondary and means preferences/confirmed facts/settings, not a mandatory
  education/experience form.
- Recommended jobs and saved/search history.
- Application status, interviews, offers, deadlines.
- Events and mentorship/community opportunities.
- AI suggestions with reviewable diffs/actions.
- Account, notification, security, and device settings.
- Above the fold: a readiness/context band, not only stat cards.

Partner workspace must prioritize:

- Navigation: operations sidebar + topbar is appropriate because recruiters need
  repeated access to jobs, candidates, pipeline, team, company profile, ads, and
  analytics.
- Jobs needing action, moderation status, and quota/package usage.
- Candidate pipeline, new applications, interviews, scorecards, offers.
- Team/RBAC, company profile, knowledge base, ads, and events.
- Recent activity and SLA/response-time warnings.
- Clear cross-tenant privacy boundaries.
- Above the fold: company identity/logo/trust/package state, post-job CTA, and
  hiring ops queues.

University workspace must prioritize:

- Navigation: operations sidebar + topbar is appropriate because university
  staff need dense moderation/governance tools.
- Moderation queues for partners, jobs, events, ads, content, and reports.
- SLA risk, security/audit alerts, AI/cost/provider health for admins only.
- Career outcomes, partner health, program/faculty insights, exports.
- Notification/email template governance and broadcast controls.
- RBAC by role/department and staff auditability.
- Above the fold: operations-center risk/readiness band plus real moderation
  queues; AI/provider/cost details are admin-only and must be honest if not wired.

Release gate:

- A workspace surface needs browser evidence, not just passing build.
- Screenshot/browser review must confirm no overlapping text, clipped controls,
  fake stats, generic placeholder panels, or unreachable mobile actions.
- Persona dashboards must read from `/dashboards/{student|partner|university}`
  contracts or documented projection equivalents; do not assemble dashboards
  through ad hoc client-side joins.

## 2. Student CV Studio

Routes: `/student/cv` and `/student/cv/builder`.

Principle: CV Studio is CV-first. Do not make students complete a long profile
form for education, experience, projects, or skills before they can create a CV.
The profile can provide confirmed facts and preferences, but upload/template/AI
paths must work without profile completion.

### CV Library / Template Marketplace

Route: `/student/cv`.

Desktop layout:

```text
Top band: active CV quota (default 5), primary CV, last updated, next best action
Left/main: active CV library with upload/import/template/duplicate actions
Right rail: job-fit recommendations, recent parse status, AI credits/export quota
Template shelf: university-approved templates with previews, category filters, locked labels
```

Mobile layout:

- Tabs: My CVs | Templates | Uploads | Job Fit.
- Sticky action: Upload CV / Create CV.

Required first actions:

- Upload existing CV.
- Choose template and start manual editor.
- Ask AI to draft from raw notes + selected template.
- Duplicate existing CV and target a job.

Quota states:

- Default active CV limit: 5 per student tier unless admin config changes it.
- Active items include usable uploaded CV originals and builder/template CVs
  selectable for applications.
- Archived CVs and immutable submitted snapshots do not count.
- At limit, show archive/delete/request-more/upgrade actions before creation.
- Do not hide the create buttons without explaining the quota state.

### Desktop Layout

```text
Topbar: breadcrumb, autosave status, template name, Job target, Export, Set Primary
Left: templates/sections/elements/versions
Center: live A4 canvas with inline text/photo/block editing and drag/drop sections
Right: inspector + AI/job-fit drawer; export preview uses the same render pipeline
```

### Key Interactions

- Create from blank template.
- Create from raw notes and a selected template.
- Import only confirmed profile facts when the student explicitly chooses it.
- Import uploaded CV extraction.
- Duplicate an existing CV and change template.
- Ask AI to draft first CV.
- Ask AI to fill a selected template from uploaded CV extraction, another CV,
  raw notes, and confirmed profile facts.
- Add/reorder/delete sections.
- Select blocks/elements on the canvas and edit text inline.
- Replace/crop/remove portrait photo placeholders.
- Switch templates with a preservation preview before applying.
- Use natural-language AI commands that return visible canvas/content diffs.
- Inline bullet rewrite.
- Job-tailor mode from job detail or builder:
  - rank eligible CVs for the JD;
  - show recommended CV;
  - show 0-100 match score with category explanation;
  - suggest true improvements and missing evidence;
  - never invent missing facts.
- Export PDF.
- Restore version.

### Upload Preview / Ingestion

> **Updated 2026-07-05 (owner decision):** The uploaded-CV flow is
> **upload → confirm file → name the CV → done**. Backend extraction is
> authoritative and creates the versioned draft directly; there is NO manual
> field-review step. The "extracted fields / review rows / Check this" layout and
> behavior below are historical. Extraction accuracy is a backend responsibility
> (it feeds CV-JD matching). The cascade also gains a cheap vision-LLM tier that
> may receive DOWNSCALED document images for images and styled/scanned PDFs.

This is the required product flow for uploaded CVs. A bare upload modal with a
spinner is functional-only; the student should see the original, confirm it, and
name the resulting CV.

Desktop layout (upload-and-name):

```text
Left: original document preview      Right: name the CV + confirm
      pages / zoom / file summary            "Save this CV" / choose template
                                     Sticky: Use original / Save this CV / Upload another
```

Mobile layout:

- Tabs: Original | Name & Save.
- Sticky bottom actions.

Behavior:

- Show PDF/image preview before the student confirms the file.
- For DOC/DOCX, show file summary and rendered preview when available.
- After the student names and confirms, backend handles extraction, layout/OCR
  fallback, vision-LLM and optional text-LLM structuring, and creates the draft;
  UI shows user-friendly progress, not engine names. (Updated 2026-07-05: no
  student field-review step.)
- Student lands on the resulting draft; they can also keep the uploaded original
  as a selectable CV if allowed by quota/business rules.
- Quota reached, blank, not-CV, low-quality, password-protected, corrupt,
  duplicate, OCR-unavailable, and AI-unavailable states must all have a next
  action.

### States

- No CV: start wizard with three choices.
- Existing CVs: show upload, import, duplicate, template switch, and tailor paths without forcing a new blank CV.
- Active CV limit reached: explain quota and offer archive/delete/request-more/upgrade.
- Upload processing: scanning, extracting, OCR/vision-LLM fallback, then draft ready. (Updated 2026-07-05: no student review-required state — backend-authoritative extraction.)
- Upload failure: unsupported type, too large, security rejection, password-protected, corrupt, blank document, not a CV, low-quality scan, duplicate file.
- Empty section: guided examples.
- Autosaving: subtle status; never block typing.
- Pending AI diff: accept/reject/edit.
- Job-fit score loading/empty/failure: deterministic keyword/skills diff fallback
  before hiding the surface.
- Credit exhausted: show upgrade/request guidance.
- Export running: progress card with notification fallback.
- Export failed: retry and friendly reason.

Upload failure UI:

- Show a concise reason, not technical parser details.
- Always offer at least one next action: upload another file, create from template, or enter manually.
- Duplicate upload offers "Use existing CV" instead of failing hard.
- Low-confidence extraction is resolved backend-side into the best draft; the
  student refines it later in the editor. (Updated 2026-07-05: no student
  field-review screen — backend-authoritative extraction.)

### Accessibility

- Keyboard reorder fallback.
- Diff viewer uses text labels, not color only.
- Preview has accessible text equivalent in editor.

## 2A. Student Job Detail Intelligence

Route: `/jobs/[jobId]` for public detail; authenticated students receive
additional intelligence in the same detail surface.

Desktop layout:

```text
Left/main: job description, requirements, benefits, company context, tabs
Right rail: selected CV, fit score, evidence gaps, competition guidance,
            learning gaps, apply/save actions, similar roles
```

Rules:

- Guests see public job detail, company context, similar jobs, and login-gated
  actions only.
- Logged-in students see recommended CV, alternate CVs, CV-JD fit score,
  matched evidence, truthful improvement suggestions, learning gaps, and apply
  readiness.
- Competition intelligence is login-only and low-signal aware. If aggregate
  inputs are insufficient, hide precise scoring and show softer guidance.
- Never expose other applicants, exact rank, raw AI/model confidence, provider
  identity, prompts, token/cost internals, or private partner analytics.
- Actions must be direct: choose CV, improve CV, apply, save, ask AI about JD,
  view similar jobs, or close/reset preview.

## 3. AI Career Assistant

Route: `/student/ai-assistant`.

Layout:

- Conversation list.
- Main streaming chat.
- Tool cards inline.
- Confirmation cards for mutating tools.
- Source cards for RAG answers.

Rules:

- Provider/model/token/latency/prompt internals never visible.
- Mutating tool card shows action summary, affected record, rollback possibility, and confirm/cancel.
- If AI is unavailable, show deterministic next steps, not blank failure.
- Guest sees login modal and preserved intent.

## 4. Student Application Tracker

Route: `/student/applications`.

Layout:

- Filter tabs: All, Submitted, Interview, Offer, Rejected, Withdrawn.
- Application cards/table with stage, next action, deadline, selected CV snapshot.
- Detail drawer with timeline, messages, interview schedule, documents, withdrawal action.

Rules:

- Show friendly labels, not raw status codes.
- For anonymous applications, show what is hidden from the partner.
- Withdrawal requires reason and confirmation.

## 5. Partner Pipeline

Route: `/partner/jobs/[jobId]/pipeline`.

Layout:

- Header: job status, candidates count, SLA warnings, export.
- Kanban columns from configured pipeline stages.
- Candidate cards show permitted fields only.
- Right drawer: candidate detail, CV preview, scorecards, notes, timeline.

Rules:

- Drag move opens confirmation if required action is incomplete.
- Rollback requires target stage and reason.
- Bulk actions use selection bar and limit warnings.
- Anonymous candidates cannot be deanonymized through filters, exports, or visible metadata.

## 6. University Moderation Queue

Route: `/admin/moderation`.

Layout:

- Queue table with type, submitter, SLA, risk flags, assigned reviewer.
- Detail panel with content preview, policy checklist, AI suggestion, decision controls.

Rules:

- AI suggestion is advisory and visually secondary to policy checklist.
- Reject requires reason.
- Bulk approve is disabled for high-risk or AI-flagged items.
- Sponsored/ad labels are previewed before approval.

## 7. AI Provider Hub

Route: `/admin/ai-settings`.

Layout:

- Provider cards with alias, health, budget, routing status.
- Routing matrix per task type.
- Drag priority list.
- Test panel for admin-only test prompts.

Rules:

- Provider names and model aliases are admin-only.
- End-user labels use generic "AI service".
- Cost spikes and unhealthy providers show alerts.
- Changing routing requires confirmation and audit.

## 8. Document Knowledge Base

Routes:

- `/admin/knowledge-base`
- `/partner/knowledge-base`

Layout:

- Document list with status, scope, owner, chunk count, last ingestion error.
- Upload dropzone.
- Preview extracted text for permitted admins.
- Test query panel.

Rules:

- Failed ingestion has retry.
- Deleting a document removes chunks from future retrieval.
- Test query never leaks storage keys, chunk IDs, provider names, or similarity scores.

## 9. Visual Workflow Builder

Route: `/admin/workflows`.

Layout:

- Left node palette.
- Full canvas.
- Right inspector.
- Bottom execution log/test console.

Rules:

- DAG validation in frontend and backend.
- Active versions are immutable.
- Test mode shows simulated run without touching production records.
- Every node has accessible non-canvas inspector fields.

---

## 10. Student Subscriptions & AI Credits

Route: `/student/subscriptions`.

Layout:

- Current tier badge + credit balance (always visible top bar widget).
- Plan comparison table: Free / Basic / Standard / Premium rows × features columns.
- Upgrade CTA opens payment modal (bank transfer in v1).
- Credit history: list of credit deductions with task type and date.
- AI credit pack purchase: one-click add-on packs.

Rules:

- Current plan is highlighted, cannot be "upgraded to same tier".
- Free plan always visible — student cannot be left without a plan.
- Quota bars (applies/week, CV exports/month, AI credits) show progress.
- Bank transfer modal shows account number, reference code, and pending status.
- No credit card UI in v1.

---

## 11. Student Bulk Apply Cart

Route: `/student/jobs/cart`.

Layout:

```
Header: "Giỏ ứng tuyển ({N} việc làm)"
Quota display: "X/Y lượt còn lại tuần này"

Job list (scrollable):
  ┌────────────────────────────────────────────────────────┐
  │ [Logo] Software Engineer — Vingroup          [Xóa]    │
  │ CV: Backend Internship CV v3 ▾               [Đổi CV] │
  │ Cover letter: [AI viết] | [Tự viết]          [Xem]    │
  │ CV chưa cập nhật trong 60 ngày ⚠            [Cập nhật]│
  └────────────────────────────────────────────────────────┘

Sticky bottom bar:
  [Huỷ] [Ứng tuyển {N} việc làm →]
```

Rules:

- Max 20 jobs in cart; show error when attempting to add beyond limit.
- Show cover letter word count if entered.
- AI cover letter: generates per job (costs 3 credits each); student can edit before apply.
- Confirm modal before bulk submit: quota summary, stale-CV warning, job list.
- Partial apply success: show per-job outcome clearly.
- Cart persists in DB; surviving page reload and device switch.

---

## 12. Interview Simulator (Active Session)

Route: `/student/interview-sim/{sessionId}`.

Layout:

```
Left column: Question panel
  - Round/total badge (e.g. "Câu 3/8")
  - Question text (animated appear)
  - Timer (optional per question)
  - [Bỏ qua]

Center: Answer area
  - Text editor (Tiptap rich text) OR
  - Voice recording button (if voice mode)
  - [Gửi câu trả lời]

Right column: AI Feedback (appears after submit)
  - Score bar (Strong / Good / Needs Work)
  - Specific improvement tips
  - Model answer (expandable)
  - [Câu tiếp theo →]

Footer: progress dots | [Kết thúc phiên]
```

Rules:

- AI feedback never shows confidence score, provider name, or token counts.
- Per-question cost: 2 credits. Show running credit total.
- Voice mode transcribes locally (not sent to AI directly); transcript sent to AI.
- Session can be paused and resumed (in-progress state persisted).
- End of session: full evaluation report (aggregate score per category, top 3 improvements).
- Reports shareable as PDF export.

---

## 13. Partner Passive Search / Talent Pool

Route: `/partner/passive-search`.

Layout:

```
Left filter panel:
  Skills (multi-select, autocomplete)
  Graduation year range
  Industry interests
  Availability (open to work toggle)
  [Tìm kiếm]

Right result list:
  ┌────────────────────────────────────────────────────────┐
  │ 🙂 Sinh viên #A347 (anonymous)                        │
  │ Major: Computer Science | Tốt nghiệp 2025             │
  │ Skills: Python, FastAPI, React                        │
  │ Experience: 2 internships (no company names)           │
  │ [Thêm vào danh sách] [Gửi yêu cầu liên hệ]           │
  └────────────────────────────────────────────────────────┘

Quota indicator: "18/30 lượt liên hệ còn lại tuần này"
```

Rules:

- Profile cards are always anonymized until reveal is accepted.
- "Gửi yêu cầu liên hệ" requires reason input (min 20 chars).
- Quota warning at 80% usage: amber banner.
- Quota exhausted: button disabled with "Nâng cấp gói" CTA.
- Student response (accept/decline) notified in real-time via WebSocket.
- Partners cannot see if a student has also applied to competitor jobs.

Route: `/partner/talent-pool`.

- List of saved profiles from passive search.
- Internal label and notes per entry.
- Bulk action: send outreach message (rate-limited).

---

## 14. Partner Advertising Campaign Builder

Route: `/partner/advertising/new` and `/partner/advertising/{id}`.

Layout:

```
Step 1 — Campaign basics:
  Name, type (CPM/CPC/Fixed), placement (dropdown), budget, dates

Step 2 — Creative:
  Headline (max 60 chars counter), description, image upload (drag-drop)
  Preview: how ad looks on job feed / homepage / email

Step 3 — Targeting:
  Allowed dimensions only (UI never shows forbidden dimensions)
  "Tại sao tôi thấy quảng cáo này?" preview based on targeting

Step 4 — Review & Submit:
  Full summary
  Required checkbox: "Tôi xác nhận quảng cáo này sẽ hiển thị nhãn 'Được tài trợ'"
  [Gửi duyệt]
```

Rules:

- Forbidden targeting dimensions are not shown in UI at all (not disabled — absent).
- Sponsored label checkbox is mandatory and cannot be unchecked.
- University review SLA: 24h. Status visible in campaign list.
- Budget remaining shown in real-time on active campaigns.
- Paused campaigns retain all stats.

---

## 15. Partner Billing

Route: `/partner/billing`.

Layout:

- Current package card (name, renewal date, quota summary).
- Upgrade/downgrade package grid.
- Payment history: date, amount, status, reference code.
- Pending payment: bank transfer instructions + reference + upload proof button.
- Invoice download per payment record.

Rules:

- Downgrade shows effective date (next billing cycle, not immediate).
- University must confirm bank transfer manually; status shows "Đang xác nhận".
- No gateway payment UI in v1 (VNPay/MoMo are future phase).

---

## 16. University Career Outcomes Dashboard

Route: `/admin/career-outcomes`.

Layout:

```
KPI row (4 cards):
  Tỉ lệ có việc làm | Mức lương trung bình | Thời gian có việc | Survey response rate

Filters: Cohort year | Department | Trust level

Charts:
  - Placement rate trend (line chart, by cohort)
  - Salary distribution by major (box plot or bar)
  - Top hiring companies (bar chart — requires ≥5 students for privacy)
  - Time-to-employment histogram

Tables:
  - Cohort breakdown: N graduated | N employed | N self-reported | N partner-confirmed
  - Data quality: trust_level distribution
```

Rules:

- Never display individual salary; aggregate only (min 5 data points).
- Below 5 data points: show range (min–max) instead of average.
- Faculty role: aggregate view only — cannot drill into individual records.
- Export button: RBAC-gated, generates async Excel with anonymized fields.

Route: `/admin/career-outcomes/surveys`.

- Survey list with response rates.
- Create new survey with drag-and-drop question builder.
- Send survey to cohort segment.
- Response analytics per question.

---

## 17. University Partner Approval Queue

Route: `/admin/partners` (list) + `/admin/partners/{id}` (detail).

Layout:

```
List view:
  Status tabs: Pending Review | Approved | Suspended | Rejected

Partner detail (approval workflow):
  ┌────────────────────────────────────────────────┐
  │ [Logo] Acme Corp                               │
  │ Tax code: 0123456789  Website: acme.com        │
  │ Contact: Nguyen Van A — hr@acme.com            │
  │ Description: ...                               │
  │                                                │
  │ AI Fraud Score: 15/100 (Low risk) [details ▾] │
  │                                                │
  │ Assign package: [Select ▾]                     │
  │ Trust level: Standard ▾                        │
  │ Note (optional): _______________               │
  │                                                │
  │ [Từ chối] [Phê duyệt & Thông báo]             │
  └────────────────────────────────────────────────┘
```

Rules:

- AI fraud score shown to admin (advisory only). Admin always has final say.
- Fraud score never shown to partner.
- Approval triggers: email to partner, subscription activation, first login invite.
- Rejection requires reason (mandatory).
- Suspended partners: all active jobs hidden from listings; active applications continue.

---

## 18. Student Mentorship

Route: `/student/mentorship`.

Layout:

```
Mentor discovery:
  Filter: expertise tags | industry | availability
  Cards: photo | name | headline | rating | session count | [Gửi yêu cầu]

My requests:
  - Pending / Accepted / Declined requests
  - Upcoming sessions

Session history:
  - Past sessions with feedback given/received
```

Rules:

- Mentor profiles only show verified alumni/experts (is_verified = true).
- Request requires goal statement.
- Session booking is async: mentor accepts → calendar link sent.
- Student can rate session only after completion.

---

## 19. Company Reviews (Student-facing)

Route: `/companies/{slug}` (integrated review section).

Layout:

```
Company overview header
...
Review summary:
  Overall score (Bayesian avg) + stars
  Category breakdown: 5 bars
  Trust level legend: "Đã xác minh" | "Đã phỏng vấn" | "Tự khai báo"

Review list (paginated):
  ┌───────────────────────────────────────────────────────┐
  │ ★★★★☆  "Môi trường tốt nhưng OT nhiều"              │
  │ Pros: ... | Cons: ...                                 │
  │ Nguyen V.A. • Đã xác minh • Backend Engineer Intern  │
  │ 3 tháng trước | [Báo cáo]                            │
  └───────────────────────────────────────────────────────┘

[Viết đánh giá] — only shown to eligible students
```

Rules:

- Minimum eligibility verification before write form is shown.
- Anonymous review hides name, shows "Người dùng ẩn danh".
- Reviews below 3 stars still show — never filtered for partner.
- "Báo cáo" triggers flagging flow, not removal.

---

## 20. Alumni Network

Route: `/student/alumni` (student view) + `/admin/alumni` (admin view).

Layout:

```
Student view:
  Search: name / company / major / graduation year
  Cards: graduation year | current company | headline | [Kết nối]

Connection requests:
  - Pending | Connected | Sent

My network:
  - List of connections with messaging capability
```

Rules:

- Alumni must set `is_open_to_connect = true` to appear in directory.
- Connections require mutual accept (no direct contact without connection).
- Students cannot access alumni profiles until logged in.
- Mentors in mentorship module are a subset of alumni network.
