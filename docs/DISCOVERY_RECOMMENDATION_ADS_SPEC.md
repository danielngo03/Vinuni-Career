# Discovery, Recommendations, And Advertising Spec — VinUni Career Platform

> Purpose: source of truth for public/job discovery, personalization, ranking,
> recommendation rails, sponsored inventory, and monetization UX.

---

## 1. Product Intent

VinUni Career Platform must feel like a live recruiting marketplace, not a
static demo board. Public and student surfaces should continuously answer:

- What opportunities are relevant to me right now?
- Which CV should I use, and why?
- What employers/events are important in the VinUni ecosystem?
- Which content is organic, recommended, sponsored, or university-curated?

The system may start with deterministic scoring and session signals. AI is an
enhancement, not a dependency for v1 discovery.

---

## 2. Content Types

Public discovery surfaces can show:

- Organic jobs and events.
- Recommended jobs/events based on search, viewed items, saved intent, or
  authenticated student profile/CV signals.
- Paid sponsored jobs/events/companies/campaign banners with mandatory
  disclosure.
- University-curated employer spotlights, career fairs, role guides, skill
  tracks, and strategic partner showcases.
- Trust modules: verified by VinUni, career support, employer quality, event
  credibility, and student success/outcomes.

Do not fake inventory. If a rail has no eligible items, hide it or replace it
with honest organic content.

---

## 3. Public Guest Personalization

Guests can receive lightweight recommendations without login, but only from
privacy-safe first-party signals.

Allowed guest signals:

- Current search query, selected filters, locale, coarse city/work-mode filter.
- Viewed job categories, industries, role families, companies, and events.
- Apply/save/register intent clicks before login.
- Recent public page views within the current browser/session.
- Device type for layout and allowed ad targeting only.

Forbidden guest signals:

- Name, email, phone, exact location, raw IP, GPS, health, ethnicity, gender,
  religion, politics, disability, pregnancy, financial status, or any sensitive
  category from `docs/SECURITY_PRIVACY.md`.
- Cross-site tracking or third-party ad identifiers.

Implementation options:

- Preferred: first-party anonymous discovery session cookie with random ID,
  short TTL, and server-side coarse signal store.
- Acceptable local-only fallback: browser storage containing only coarse tags,
  timestamps, and viewed public IDs; no PII or raw CV text.
- Always provide clear privacy language and respect reset/clear preference.

Guest recommendation examples:

- "Because you searched Data Analyst"
- "Similar roles in Finance"
- "Companies hiring interns this week"
- "Career events related to AI and Data"

---

## 4. Authenticated Student Personalization

After login, recommendations can use stronger first-party signals:

- Active CV library and CV-to-job fit scores.
- Confirmed preferences: industries, locations, work mode, job type, graduation
  year, degree/major, language, availability.
- Application history, saves, viewed jobs, event registrations, interview/offer
  status.
- Subscription/tier limits and AI credit availability.

Student rails must explain why items appear:

- "Recommended for CV: Backend Internship CV — 82/100"
- "Matches your preferred industry: Finance"
- "You viewed similar AI roles"
- "Deadline in 3 days"
- "Partner-sponsored" / "Đối tác tài trợ" only when it is paid inventory, with
  disclosure.
- "Curated by VinUni" / "VinUni tuyển chọn" for university editorial content.
- "Strategic partner" / "Đối tác chiến lược" for approved relationship-based
  partner spotlights.

AI may generate explanations only after deterministic ranking is available and
offline evals pass. The score is a product fit score, not model confidence.

Logged-in job detail may also show job intelligence:

- recommended CV to apply with;
- fit score and evidence gaps;
- truthful CV improvement actions;
- learning gaps mapped to skills/resources;
- competition guidance when privacy-safe aggregate data is sufficient.

Competition guidance must be hidden or softened to `low_signal` when the system
does not have enough real data. Never show it to guests, and never expose other
applicants, exact ranks, raw CV text, raw model confidence, prompts, provider
identity, or internal scoring internals.

---

## 5. Ranking Policy

Ranking must separate organic relevance from paid placement.

Required ranking layers:

1. Eligibility filter: visibility, deadline, moderation state, persona access,
   event capacity/registration state, organization status.
2. Organic relevance score: query match, skills/JD overlap, location/work mode,
   recency, employer quality, event topic, student preferences/CV fit.
3. Sponsored slot selection: paid campaigns compete only for defined sponsored
   slots, never silently override organic relevance.
4. Diversity and freshness: avoid showing the same company/industry repeatedly.
5. Explanation: every recommended item has a user-safe reason.

Sponsored content can be prominent, but it must be visibly labelled and must not
claim to be "best match" unless it also wins organic relevance.

---

## 6. Public Layout Contract

The public homepage should include practical marketplace inventory above and
near the fold:

- Search hero with public jobs visible or one click away.
- Metric strip with honest aggregate/trend data.
- Left/main: organic or personalized job list.
- Right rail: employer spotlight, sponsored banner slot, event card, career fair
  promotion, or university-curated career content.
- Dedicated sponsored rail when active campaigns exist.
- Recommended-for-you rail for guests with enough session signal; otherwise
  "Popular with VinUni students" or "New this week" from real data.
- Trust rail and career-support modules.

Job detail pages should show:

- Apply/save login gate with preserved intent.
- Similar jobs.
- Company card with logo and verified status.
- Sponsored/featured disclosure if paid.
- For logged-in students: best CV recommendation, improve-CV action, fit
  evidence/gaps, learning gaps, and competition guidance if signal quality is
  sufficient.

---

## 7. Advertising Business Contract

V1 `sponsored_placements` is useful but not the end-state monetization system.
The product must evolve toward campaign-grade advertising without losing trust.

Placement types:

- Sponsored job row/card.
- Featured job.
- Employer spotlight.
- Public homepage right-rail banner.
- Event sponsorship card.
- Career-explore/content banner.
- Email/newsletter placement when email campaigns exist.

Campaign creative slots:

- Homepage hero campaign: desktop 1440x360 or 4:1, mobile 720x720 or 1:1.
- Right rail banner: desktop 640x800 or 4:5, mobile 720x720 or 1:1.
- Inline card banner: desktop 1200x630 or 1.91:1, mobile 720x900 or 4:5.
- Event/career-day banner: desktop 1440x480 or 3:1, mobile 720x900 or 4:5.

Each creative requires image type/size validation, alt text, focal point,
safe-area guidance, preview, approval status, click target, source surface, and
analytics tracking. If no partner creative exists, use a VinUni-curated fallback
asset and label it as university-curated rather than paid sponsored inventory.

Partner campaign workflow:

- Pick target: job, event, company profile, or approved content placement.
- Pick package/placement, dates, budget/price, creative, and disclosure.
- Preview exactly where the ad appears.
- Submit for university approval.
- University approves/rejects, records manual payment, can pause/disable.

Analytics:

- Impression, click, apply-start, save-intent, event-register-intent.
- CTR, apply-start rate, cost per apply-start, conversion by source.
- Partner sees their own campaign analytics.
- University sees all campaign health, spend, complaints, and policy risk.

Mandatory rules:

- Disclosure label is non-removable.
- Disclosure copy should be truthful and polished. Avoid blunt, repetitive
  "Sponsored opportunity" wording across normal marketplace lists. Paid content
  can say "Partner-sponsored"; university/editorial content should use curated
  or strategic-partner labels.
- Sponsored content cannot use forbidden targeting dimensions.
- Organic/recommended/sponsored sources are tracked separately.
- No campaign can expose private student/CV/application data.

---

## 8. API And Data Contracts To Add

Recommended future contracts:

- `POST /api/v1/discovery/events` records impression/click/view/apply-start with
  idempotency key, source surface, target type/id, placement id when sponsored,
  and anonymous/session/user scope.
- `GET /api/v1/marketplace/overview` returns explicit rails:
  `hero_campaign`, `recommended_jobs`, `recommended_events`,
  `sponsored_banner`, `employer_spotlight`, `recent_jobs`, `popular_roles`,
  `trust_modules`.
- `GET /api/v1/jobs/recommendations` returns personalized jobs with
  `reason_codes`, `score`, `recommended_cv_id`, `sponsored_disclosure`, and
  `source`.
- `GET /api/v1/jobs/{id}/similar` returns similar public jobs.
- `GET /api/v1/admin/discovery/health` returns ad/recommendation inventory
  health, empty rails, broken logos, CTR outliers, and policy flags.

Candidate entities:

- `discovery_sessions`: anonymous ID, created/last seen, locale, coarse tags,
  opt-out/reset state, TTL.
- `discovery_events`: impression/click/view/apply-start events, source surface,
  target, placement id, user or anonymous session, no raw PII.
- `recommendation_snapshots`: optional cached ranked results for audit/debug,
  storing reason codes and product scores, not raw model prompts.
- `ad_impressions` / `ad_clicks`: can initially share `discovery_events`, then
  split when billing/analytics requires.

---

## 9. AI Use

AI is useful for:

- Explaining why a job fits a CV.
- Suggesting how to improve a CV for a specific JD.
- Generating career-explore content summaries.
- Helping partners write better ad/job copy.
- Admin-only policy review for ad creative and targeting risk.

AI should not be required for:

- Basic public ranking.
- Sponsored placement disclosure.
- Session-based guest recommendations.
- CV-to-job base score.

Real-provider calls stay capped by `docs/AI_PRODUCT_SPEC.md` and must not expose
provider/model/token/prompt details.

---

## 10. Acceptance Gates

A discovery/ads/recommendation slice is not complete until:

- Public homepage has visible organic inventory and, when eligible, sponsored
  inventory in a realistic placement.
- Guest recommendations improve after search/view interactions or honestly show
  "new/popular" fallback.
- Logged-in student recommendations include fit score, recommended CV, and
  user-safe reason codes.
- Sponsored and recommended labels are visually distinct.
- Impression/click/apply-start hooks exist for ad-funded surfaces.
- University can inspect active placements and disable campaigns.
- Partner can see campaign status and basic performance.
- Tests cover privacy, forbidden targeting, disclosure, ranking source labels,
  guest/session fallback, and no fake metrics.
- Browser verification covers 375, 768, 1024, and 1440 px.
