# Design System — VinUni Career Platform

> Phiên bản: 5.0 | Cập nhật: 26/06/2026
> Nguồn sự thật duy nhất về visual design, UX patterns, component spec.
> Màu sắc dựa trên VinUniversity Visual Guideline (Bộ hướng dẫn sử dụng hình ảnh chính thức).

---

## 1. Design Philosophy

**4 nguyên tắc cốt lõi:**

1. **Clarity first** — Mỗi element phải có mục đích rõ. Không decoration thuần túy.
2. **Earned complexity** — Phức tạp chỉ xuất hiện khi người dùng cần. Wizard thay vì form dày đặc.
3. **Institutional warmth** — Chuyên nghiệp như VinUni, trẻ trung như startup. Không khô khan như HR software cũ.
4. **Motion with purpose** — Animation truyền đạt state, không phải trang trí.

**Cảm hứng:** Linear.app (precision), Notion (warmth), Vercel (dark/light quality), Luma (events), Superhuman (speed). Kết hợp với di sản hình ảnh của VinUniversity (xanh navy + đỏ + Montserrat).

### 1.1 Product Surface Quality Standard

Every screen must look and behave like part of a real, large career operating
system. Claude must not ship generic SaaS filler, empty shells, or pretty cards
that do not match the user's job-to-be-done.

Required qualities for every major surface:

- **Persona-specific:** Public, Student, Partner, and University screens have
  different goals, density, navigation, and primary actions.
- **Workflow-first:** The first screenful answers "what can I do now?" with
  queues, lists, next actions, filters, progress, or review tasks.
- **Data credible:** Use real API data, seeded local demo data clearly marked as
  demo, skeletons, or actionable empty states. Never use fake business metrics.
- **Operational density:** Dashboards and workspaces should be dense but calm:
  tables, split panes, filters, queue cards, charts, timelines, and editors
  where they help repeated work.
- **Modern but institutional:** Enterprise-grade polish, VinUni colors,
  restrained motion, strong spacing, high contrast, and clear visual hierarchy.
- **State-complete:** Loading, empty, error, permission, offline, conflict,
  disabled, success, and recovery states are designed, not bolted on later.
- **Actionable AI:** AI surfaces produce reviewable suggestions, diffs,
  citations, next actions, and confirmation cards; never decorative chat fluff.
- **Trust/compliance visible:** Sponsored labels, privacy notes, audit-relevant
  actions, security/device settings, and permission boundaries are visible when
  relevant.

Plugins or design helpers are advisory only. The final authority is this file,
`docs/UI_QUALITY_BAR.md`, `docs/SCREEN_SPECS.md`, browser screenshots, and the
actual product workflow.

### 1.1.1 Anti-Patterns (Visual Rescue Findings — 2026-07)

A partner/university visual audit found the shared workspace shell and many
dashboard/detail widgets had drifted into generic AI/SaaS decoration instead of
the calm, institutional, data-dense look this file specifies. These are now
explicitly banned on Partner and University operational surfaces (and should
not be reintroduced on Student/Public surfaces either):

- **No decorative gradient-blob canvases.** Page/app backgrounds must be the
  flat `--bg-subtle` (or `--bg-base`) token. Radial-gradient "blob" washes
  (pastel blue/purple/mint blurs) behind dense operational screens read as a
  marketing landing page, not a career operating system.
- **No pervasive glassmorphism on operational widgets.** `backdrop-blur-*`,
  translucent `bg-white/NN`, and translucent `border-white/NN` are reserved for
  the fixed topbar and slide-in panels (chat, drawers) per §5.4/§6.1.1 — not
  for stat tiles, queue rows, rail widgets, or AI-insight panels sitting next
  to flat `marketplace-card` siblings on the same screen. Mixing flat cards and
  frosted-glass cards on one screen is the single biggest cause of a "messy /
  linh tinh" surface; pick the flat `marketplace-card` treatment everywhere on
  ops screens.
- **No ad-hoc off-palette Tailwind hues.** Icon chips, badges, and gradients
  must use the six tokenized icon-chip roles in §5.6, not arbitrary Tailwind
  defaults (`violet-*`, `emerald-*`, `slate-*`, `rose-*`, `sky-*`, `purple-*`,
  raw `blue-700`, etc.) that are not part of the VinUni token system. Every
  color must carry meaning (primary action, info, success, warning, danger,
  neutral) — never decoration-only variety.
- **AI accents are blue/teal only**, never purple (§1.2). There is no
  `--brand-purple` token; any reference to it is a bug, not a design choice.
- **Sidebar/nav active states are one flat treatment**, not a stack of
  `backdrop-blur` + `ring` + inset-shadow + gradient layered together. See
  §5.4.

### 1.1.2 Token Drift Notice — v9 "Monochrome" (2026-07-02, current direction)

The active design system is **v9 "Monochrome"**: a minimalist, premium
black/white system in the Vercel tradition, implemented in
`frontend/src/app/globals.css`. Key rules:

- **Neutral-first.** A full gray ramp (`#fafafa → #0a0a0a`, never flat
  `#000`-on-`#fff`) carries all hierarchy: canvas `#fafafa`, cards `#ffffff`,
  borders `#e5e5e5`, ink text `#171717` in light; canvas `#0a0a0a`, cards
  `#111111`, borders `#262626`, text `#ededed` in dark. Dark is a designed
  near-black theme, not an inversion.
- **The single action color is ink** (`--brand-primary` = `#171717` light /
  `#ededed` dark). Primary buttons use `--btn-primary-bg/fg/hover` (black
  button in light theme, white button in dark theme). The old blue accent is
  retired; the `--blue-*` variables are remapped to the ink ramp so legacy
  call sites collapse into monochrome.
- **Color only where it carries meaning:** green `#059669` for
  verified/success/AI signal, VinUni red `#c83538` for destructive actions
  and small brand details, amber `#d97706` for sponsored/paid disclosure
  (compliance — never removed). These appear as small chips/labels/badges,
  never as large surfaces.
- **Brand lockup:** the V mark (`public/brand/logo-dark.png` for light
  surfaces, `logo-light.png` for dark, swapped in CSS via
  `.theme-logo-light/.theme-logo-dark`) + hairline divider + "VINUNI CAREER"
  wordmark. No "Career Platform" tagline text.

Sections 2.1–2.5 below describe the pre-v9 colored palettes and are kept for
brand-color reference only (the official VinUni blue/red still exist as
accents); `globals.css` is the source of truth for exact hex values. This
file remains the source of truth for which token plays which *role*,
component structure, and layout rules.

### 1.2 Interaction Semantics And Campaign Realism

Use `docs/PRODUCT_INTERACTION_VISUAL_REALISM_SPEC.md` for product-level
interaction details. Non-negotiables:

- Job favorite uses a heart icon and sits in the top-right of job cards/details.
  Bookmark is reserved for saved collections/resources.
- Public/student pages should provide a bottom-right floating action rail or
  launcher for saved jobs, career opportunity invitations, messages,
  feedback/help, and VinUni AI assistant when available. Desktop actions need
  hover/focus labels; AI may use restrained VinUni-blue/teal motion that respects
  `prefers-reduced-motion`.
- Campaign banners are university-reviewed surfaces with creative assets,
  responsive sizes, alt text, focal point, preview, and moderation. Do not ship
  only text-only sponsored cards as the final campaign product.
- Public wording separates `paid sponsored`, `strategic partner`, and
  `VinUni curated`. Paid disclosure remains visible, but do not make every
  promoted item feel like low-trust ad tech.
- Icon choices must match user intent. Avoid random decorative icon swaps.

### 1.3 Frontend-Design Skill Contract

Use `docs/FRONTEND_DESIGN_PLUGIN_USAGE.md` whenever a major UI surface or
`frontend/src/app/globals.css` is redesigned.

The official `frontend-design` skill must be used as a design-lead pass, not a
late polishing checklist. Before writing code, Claude must define:

- subject, audience, and the route's single job;
- screenshot diagnosis;
- a compact 4-6 color token system;
- typography roles;
- layout concept and ASCII wireframe;
- one signature element / justified aesthetic risk;
- motion plan with `prefers-reduced-motion`;
- self-critique against generic AI/SaaS defaults;
- `globals.css` light/dark/system theme audit.

VinUni colors are **brand anchors**, not a command to use every brand color on
every screen. A mature palette may add modern neutrals, blue action scales,
teal/cyan AI or success accents, restrained red CTAs, and amber disclosure/status
accents when they improve clarity and beauty.

---

## 2. Color System

### 2.1 VinUni Brand Colors (từ Visual Guideline chính thức)

```
PRIMARY BRAND:
  VinUni Blue:   #2e548a  — CMYK: C67% M39% Y0% K46%  | RGB(46, 84, 138)
  VinUni Red:    #c83538  — CMYK: C0% M74% Y72% K22%   | RGB(200, 53, 56)

B&W (từ guideline):
  #ffffff  #000000  #d2d3d5  #1e1d1d  #a6a6a6  #2f2424

EXTENDED PALETTE (từ guideline):
  Teal:          #5cc6d0   Mid Blue:   #4890bd
  Light Blue:    #78c2ff   Dark Navy:  #35426e
  Dark Teal:     #417865   Dark Red:   #3f071f
  Amber:         #e98300   Light Amber:#f9a44a
  Warm Orange:   #d1660f   Yellow:     #ffde59
  Olive:         #a6b168
```

### 2.2 System UI Palette (mở rộng cho web app)

```css
/* ─── VinUni Primary Blue Family ─── */
--blue-950: #0d1f3c;   /* dark hero backgrounds */
--blue-900: #1a3460;   /* darker hover state */
--blue-800: #1e3d72;
--blue-700: #254e8e;
--blue-600: #2e548a;   /* PRIMARY ← VinUni brand */
--blue-500: #3a6aaa;
--blue-400: #4890bd;   /* secondary interactive ← extended palette */
--blue-300: #78c2ff;   /* tags, highlights ← extended palette */
--blue-200: #b8d9f5;
--blue-100: #daeeff;
--blue-50:  #eef6ff;   /* tinted background */

/* ─── VinUni Red Family (CTA + Accent) ─── */
--red-900:  #6b0f10;
--red-800:  #881718;
--red-700:  #a02b2d;
--red-600:  #c83538;   /* PRIMARY RED ← VinUni brand */
--red-500:  #dc4a4c;
--red-400:  #e87375;
--red-100:  #fde8e8;
--red-50:   #fff5f5;

/* ─── Teal (Success + Fresh + Tech) ─── */
--teal-700: #2a6657;
--teal-600: #417865;   /* premium/verified ← extended */
--teal-500: #4aab96;
--teal-400: #5cc6d0;   /* success, online events ← extended */
--teal-100: #d6f5f5;
--teal-50:  #ecfbfb;

/* ─── Amber (Warning + Sponsored + Early Bird) ─── */
--amber-700: #b56200;
--amber-600: #e98300;  /* warnings, sponsorship ← extended */
--amber-500: #f9a44a;  /* light amber ← extended */
--amber-400: #ffde59;  /* yellow highlight ← extended */
--amber-100: #fff3d0;
--amber-50:  #fffbeb;

/* ─── Dark Navy (Partner, Premium, Dark Mode) ─── */
--navy-900: #0f1520;
--navy-800: #1c2540;
--navy-700: #253068;
--navy-600: #35426e;   /* dark navy ← extended */
--navy-500: #4b5a8a;

/* ─── Olive/Neutral (Skills, Tags, Content) ─── */
--olive-600: #7a8a42;
--olive-500: #a6b168;  /* neutral skill tags ← extended */
--olive-100: #edefdb;

/* ─── Grays (from VinUni B&W) ─── */
--gray-950: #0a0a0a;
--gray-900: #1e1d1d;   /* ← VinUni */
--gray-800: #2f2424;   /* ← VinUni */
--gray-700: #3f3f3f;
--gray-600: #555555;
--gray-500: #6b7280;
--gray-400: #a6a6a6;   /* ← VinUni */
--gray-300: #d2d3d5;   /* ← VinUni */
--gray-200: #e5e7eb;
--gray-100: #f3f4f6;
--gray-50:  #f8f9fa;
```

### 2.3 Gradient Tokens

```css
--gradient-brand:       linear-gradient(135deg, #2e548a 0%, #35426e 100%);
--gradient-brand-warm:  linear-gradient(135deg, #2e548a 0%, #4890bd 100%);
--gradient-cta:         linear-gradient(135deg, #c83538 0%, #d1660f 100%);
--gradient-hero:        linear-gradient(180deg, #0d1f3c 0%, #1a3460 45%, #080f1e 100%);
--gradient-card:        linear-gradient(135deg, rgba(46,84,138,0.06), rgba(53,66,110,0.03));
--gradient-premium:     linear-gradient(135deg, #417865 0%, #35426e 100%);
--gradient-teal:        linear-gradient(135deg, #417865 0%, #5cc6d0 100%);
```

### 2.4 Semantic Tokens

```css
/* ── Light Mode (default) ── */
:root {
  /* Backgrounds */
  --bg-base:        #ffffff;
  --bg-subtle:      #f8f9fa;
  --bg-muted:       #f1f3f6;
  --bg-hero:        #0d1f3c;     /* dark hero sections */

  /* Borders */
  --border-default: #e5e7eb;
  --border-subtle:  #f0f1f3;
  --border-strong:  #d2d3d5;
  --border-focus:   #2e548a;
  --border-error:   #c83538;

  /* Text */
  --text-primary:   #1e1d1d;     /* VinUni near-black */
  --text-secondary: #555555;
  --text-muted:     #a6a6a6;     /* VinUni gray */
  --text-inverted:  #ffffff;
  --text-brand:     #2e548a;     /* VinUni Blue */
  --text-cta:       #c83538;     /* VinUni Red */
  --text-link:      #2e548a;

  /* Surfaces */
  --surface-card:     #ffffff;
  --surface-overlay:  #ffffffcc;
  --surface-dropdown: #ffffff;

  /* Shadows */
  --shadow-xs:    0 1px 2px rgba(46,84,138,0.05);
  --shadow-sm:    0 1px 3px rgba(46,84,138,0.08), 0 1px 2px rgba(0,0,0,0.04);
  --shadow-md:    0 4px 16px rgba(46,84,138,0.10), 0 2px 4px rgba(0,0,0,0.04);
  --shadow-lg:    0 8px 32px rgba(46,84,138,0.14), 0 4px 8px rgba(0,0,0,0.05);
  --shadow-xl:    0 20px 60px rgba(46,84,138,0.18);
  --shadow-brand: 0 8px 24px rgba(46,84,138,0.28);
  --shadow-red:   0 8px 24px rgba(200,53,56,0.22);

  /* Semantic state */
  --color-success:   #417865;    /* dark teal — VinUni extended */
  --color-success-light: #5cc6d0;
  --color-warning:   #e98300;    /* amber — VinUni extended */
  --color-error:     #c83538;    /* VinUni Red */
  --color-info:      #4890bd;    /* mid blue — VinUni extended */

  /* Recruitment status */
  --status-pending:  #e98300;
  --status-active:   #417865;
  --status-rejected: #c83538;
  --status-draft:    #a6a6a6;
  --status-closed:   #555555;
  --status-offer:    #35426e;
}

/* ── Dark Mode ── */
[data-theme="dark"] {
  --bg-base:        #0d1520;
  --bg-subtle:      #131d2e;
  --bg-muted:       #1a2540;
  --bg-hero:        #060e1a;

  --border-default: #253050;
  --border-subtle:  #1a2440;
  --border-strong:  #304070;
  --border-focus:   #4890bd;

  --text-primary:   #f0f2f8;
  --text-secondary: #9ab0cc;
  --text-muted:     #5a7090;
  --text-inverted:  #1e1d1d;
  --text-brand:     #78c2ff;   /* light blue ← VinUni extended */
  --text-link:      #78c2ff;

  --surface-card:     #131d2e;
  --surface-dropdown: #1a2540;

  --shadow-md: 0 4px 16px rgba(0,0,0,0.5);
  --shadow-lg: 0 8px 32px rgba(0,0,0,0.6);
}
```

### 2.5 Tier Color Mapping

```
VinUni Student:  gradient-brand (blue → navy) — text-white  [Premium tier]
Alumni:          gradient-teal (teal → navy)   — text-white  [Trusted network]
External:        bg-blue-100  text-blue-700                  [Verified student]
General:         bg-gray-100  text-gray-600                  [Basic]
Partner:         bg-navy-600  text-white       [Business]
Verified Partner:gradient-brand + verified badge ✓
```

---

## 3. Typography

Platform sử dụng **Plus Jakarta Sans** làm typeface chính cho sản phẩm số. Đây
là lựa chọn hiện đại hơn cho marketplace/dashboard dày dữ liệu, đọc tốt ở kích
thước nhỏ, và vẫn giữ cảm giác premium khi kết hợp VinUni navy/red/teal.
Montserrat có thể chỉ xuất hiện trong asset/logo/brand collateral nếu tài sản
gốc đã dùng sẵn, nhưng UI app không dùng Montserrat làm font mặc định.

```css
/* Font stack */
--font-sans: 'Plus Jakarta Sans', system-ui, -apple-system, sans-serif;
--font-mono: 'JetBrains Mono', 'Fira Code', monospace;

/* Scale */
--text-xs:   0.75rem;    /* 12px — captions, badge labels */
--text-sm:   0.875rem;   /* 14px — body small */
--text-base: 1rem;       /* 16px — body default */
--text-lg:   1.125rem;   /* 18px — card titles */
--text-xl:   1.25rem;    /* 20px — section headings */
--text-2xl:  1.5rem;     /* 24px — page titles */
--text-3xl:  1.875rem;   /* 30px — hero headings */
--text-4xl:  2.25rem;    /* 36px — landing sections */
--text-5xl:  3rem;       /* 48px — marketing hero */
--text-6xl:  3.75rem;    /* 60px — display text */

/* Weights */
--font-light:    300;
--font-normal:   400;
--font-medium:   500;
--font-semibold: 600;
--font-bold:     700;
--font-extrabold:800;

/* Line heights */
--leading-tight:   1.25;
--leading-snug:    1.375;
--leading-normal:  1.5;
--leading-relaxed: 1.625;

/* Letter spacing */
--tracking-tighter:  0em;
--tracking-tight:    0em;
--tracking-normal:   0em;
--tracking-wide:     0.04em;
--tracking-wider:    0.08em;
```

**Rules Plus Jakarta Sans-specific:**
- Heading display text: `font-extrabold tracking-normal`
- Page titles: `font-bold tracking-normal text-[var(--text-primary)]`
- Section headings: `font-semibold`
- Body: `font-normal leading-relaxed`
- Badges/labels uppercase: `font-semibold tracking-wide uppercase`
- Numbers (stats): `font-bold tabular-nums`

---

## 4. Spacing & Layout Grid

```
Base: 4px = 1 Tailwind unit

Scale:
  0.5 = 2px      (dividers)
  1   = 4px      (icon gaps)
  2   = 8px      (tight spacing)
  3   = 12px     (compact)
  4   = 16px     (standard)
  5   = 20px
  6   = 24px     (card padding)
  8   = 32px     (section gap)
  10  = 40px
  12  = 48px
  16  = 64px
  20  = 80px
  24  = 96px     (hero padding)
  32  = 128px

Layout:
  Max content width:    1280px
  Main with sidebar:    max-w-5xl (1024px)
  Forms / modals:       max-w-2xl (672px)
  Narrow utility:       max-w-lg (512px)
  Sidebar expanded:     256px
  Sidebar collapsed:    64px
  Topbar height:        60px (fixed)
  Page padding:         px-6 py-6 (desktop) / px-4 py-4 (mobile)

Breakpoints:
  sm:  640px
  md:  768px
  lg:  1024px  (sidebar shows at this point)
  xl:  1280px
  2xl: 1536px
```

---

## 5. Component Library

### 5.1 Buttons

```
PRIMARY (main CTA — VinUni Blue):
  bg-[#2e548a] text-white font-semibold
  hover:bg-[#254e8e] active:bg-[#1a3460]
  shadow-[var(--shadow-brand)]
  focus:ring-2 ring-[#4890bd] ring-offset-2
  transition-all duration-150

PRIMARY RED (Apply Now, Register — VinUni Red):
  bg-[#c83538] text-white font-semibold
  hover:bg-[#a02b2d] active:bg-[#881718]
  shadow-[var(--shadow-red)]
  focus:ring-2 ring-[#e87375] ring-offset-2

SECONDARY:
  bg-transparent text-[#2e548a] border-2 border-[#2e548a]
  hover:bg-[var(--blue-50)]
  font-semibold

GHOST:
  bg-transparent text-[var(--text-secondary)]
  hover:bg-[var(--bg-subtle)] hover:text-[var(--text-primary)]

DANGER:
  bg-[#c83538] text-white  (same as PRIMARY RED)

SIZES:
  xs: px-2.5 py-1    text-xs  h-7   rounded-md
  sm: px-3   py-1.5  text-xs  h-8   rounded-md
  md: px-4   py-2    text-sm  h-9   rounded-lg   (default)
  lg: px-5   py-2.5  text-sm  h-10  rounded-lg
  xl: px-6   py-3    text-base h-12 rounded-xl

ICON BUTTON:
  p-2, same variant. Always aria-label.
  Icon 16px (sm), 20px (md), 24px (lg)

GRADIENT BUTTON (landing page, premium actions):
  background: var(--gradient-brand)
  text-white font-bold
  hover: opacity-90
  shadow: var(--shadow-brand)
```

### 5.2 Cards

```
BASE:
  bg-[var(--surface-card)] rounded-2xl border border-[var(--border-default)]
  shadow-[var(--shadow-sm)] p-6
  hover:shadow-[var(--shadow-md)] transition-shadow duration-200

INTERACTIVE (clickable):
  + cursor-pointer
  hover:border-[#4890bd]
  hover:shadow-[var(--shadow-brand)]
  active:scale-[0.99]

VinUni BRAND CARD (featured, hero cards):
  background: var(--gradient-card)
  border: border-[#4890bd]/30
  header: text-[#2e548a] font-bold

JOB CARD:
  ┌────────────────────────────────────────────────┐
  │ [Logo 44px rounded-xl]  Company · ✓ Verified  │
  │                          Software Engineer      │  ← font-semibold
  │                          📍 Hà Nội · Full-time │  ← text-sm text-secondary
  │                          🏷 React · Node · +3  │  ← skill badges
  │  ────────────────────────────────────────────  │
  │  Deadline: 30/06   Lương: Thỏa thuận          │
  │                    [Ứng tuyển →] (RED button)  │
  └────────────────────────────────────────────────┘

STAT CARD (dashboard):
  ┌─────────────────────────────────────┐
  │  [Icon 32px blue]    ▲ +12% green  │
  │                                     │
  │  1,234                              │  ← text-4xl font-extrabold
  │  Total Applications                 │  ← text-sm text-secondary
  └─────────────────────────────────────┘
  Number: text-[#2e548a] font-extrabold (VinUni Blue for numbers = trustworthy)
```

### 5.3 Badges & Status

```
STATUS BADGE:
  text-xs font-semibold px-2.5 py-0.5 rounded-full tracking-wide

  PENDING:   bg-amber-100    text-[#b56200]  border border-amber-200
  ACTIVE:    bg-teal-50      text-[#417865]  border border-teal-200
  REJECTED:  bg-red-50       text-[#c83538]  border border-red-200
  DRAFT:     bg-gray-100     text-gray-500   border border-gray-200
  CLOSED:    bg-gray-200     text-gray-600   border border-gray-300
  OFFER:     bg-[#eef2fb]    text-[#35426e]  border border-[#b0bce0]
  ACCEPTED:  bg-teal-50      text-[#417865]  border border-teal-200

TIER BADGE:
  VinUni Student:  background: var(--gradient-brand); text-white; font-semibold
  Alumni:          background: var(--gradient-teal);  text-white; font-semibold
  External:        bg-[var(--blue-100)] text-[#2e548a] font-semibold
  General:         bg-gray-100 text-gray-600

SKILL BADGE:
  bg-[var(--blue-50)] text-[#2e548a] rounded-md px-2 py-0.5 text-xs font-medium
  dark: bg-[var(--navy-700)] text-[var(--blue-300)]

FEATURED / HOT:
  bg-[#c83538] text-white text-xs font-bold (VinUni Red = attention)

VERIFIED:
  bg-[#417865] text-white (dark teal = trustworthy)

SPONSORED:
  bg-amber-50 text-[#b56200] border border-amber-200 (amber = attention but neutral)
  Text: "Được tài trợ" — NON-REMOVABLE
```

### 5.4 Icon-Chip System

A fixed set of six tokenized roles for icon-square backgrounds (stat tiles,
section headers, queue-row avatars, next-action rail icons). Implemented as
CSS classes in `globals.css`: `.icon-chip-primary`, `.icon-chip-info`,
`.icon-chip-success`, `.icon-chip-warning`, `.icon-chip-danger`,
`.icon-chip-neutral`. Never use a raw Tailwind gradient (`from-violet-500`,
`from-emerald-500`, `from-slate-500`, etc.) for this purpose — pick the role
that matches meaning:

```
primary   → brand-primary → blue-700     (default action, main entity count)
info      → brand-mid-blue → brand-navy  (secondary informational metric)
success   → teal-500 → teal-700          (healthy, verified, AI signal)
warning   → amber-500 → amber-700        (attention, pending, emphasize)
danger    → red-500 → red-700            (moderation, rejection, urgent)
neutral   → gray-500 → gray-700          (draft, inactive, low-priority)
```

`dashboard-kit.tsx` exposes this as a shared `tone?: IconTone` prop on
`MetricItem` and `DashboardSection` — reuse it instead of a free-form
className wherever a new stat tile or section header is added.

### 5.5 Navigation

```
SIDEBAR NAV ITEM:
  Default: text-[var(--text-secondary)] rounded-lg px-3 py-2
  hover: bg-[var(--blue-50)] text-[#2e548a]
  Active: bg-[#2e548a] text-white font-semibold
          + left indicator: before:absolute before:left-0 before:h-6 before:w-1
            before:bg-[#c83538] before:rounded-r-full  ← VinUni Red indicator

TOPBAR:
  bg-white/90 backdrop-blur border-b border-[var(--border-subtle)]
  Height: 60px, fixed, z-50
  Left: [VinUni Logo] + [Breadcrumb]
  Center: [⌘K Search]
  Right: [🔔 Bell] [Avatar]

VinUni LOGO in topbar:
  Primary blue logo + "VINUNIVERSITY" wordmark
  Career Platform sub-text below: "Career Center" text-xs text-[#c83538]
```

### 5.6 Forms

```
INPUT:
  bg-[var(--bg-subtle)] border border-[var(--border-default)] rounded-xl
  px-3.5 py-2.5 text-sm font-medium
  placeholder: text-[var(--text-muted)]
  focus: border-[#2e548a] ring-1 ring-[#2e548a]/30 bg-white
  error: border-[#c83538] ring-1 ring-[#c83538]/20
  Transition: 150ms colors

LABEL: text-sm font-semibold text-[var(--text-primary)] mb-1.5
REQUIRED: <span class="text-[#c83538]">*</span> next to label
ERROR MSG: text-xs text-[#c83538] mt-1 font-medium
HELP TEXT: text-xs text-[var(--text-secondary)] mt-1
```

---

## 6. Layout Patterns

### 6.1 Shell Archetypes

Do not use one shell for every persona. The platform has three navigation
archetypes:

- **Public guest shell:** enterprise marketplace top navigation with Jobs,
  Companies, Career Explore, Events, Employers, language, saved icon, login, and
  register.
- **Student signed-in shell:** inherits the public marketplace top navigation
  and becomes personalized: Jobs, Companies, Career Explore, Events, My Career
  (dashboard), CV Studio, Applications, Saved, notifications, avatar/settings.
  Remove or de-emphasize employer acquisition items such as Employers/Register
  as employer. Students should feel they are still in the career marketplace,
  not in an admin back office.
- **Partner / University ops shell:** dense operational workspace with sidebar,
  topbar, queues, filters, tables, and admin/recruiting controls.

Student routes may use contextual tabs, sticky subnav, command palette, and
mobile bottom navigation. A permanent dark sidebar is not the default student
desktop pattern unless a specific student tool needs it.

### 6.1.1 Partner / University Workspace Shell

```
┌──────────────────────────────────────────────────────────────────┐
│  TOPBAR (60px, fixed, white/90 blur)                             │
│  [VinUni Logo + "Career Center" red]  [⌘K]  [🔔] [Avatar ▼]   │
├────────────────────────┬─────────────────────────────────────────┤
│  SIDEBAR               │  PAGE CONTENT                           │
│  (256px, dark navy bg) │                                         │
│  bg-[#1c2540]          │  Page header + actions                  │
│                        │  ─────────────────────                  │
│  [Avatar]              │  Main content                           │
│  User Name (white)     │                                         │
│  [Tier badge]          │                                         │
│  ─────────────────     │                                         │
│  Nav items (white text)│                                         │
│  Active: bg-[#2e548a]  │                                         │
│  Red left indicator    │                                         │
│  ─────────────────     │                                         │
│  [⚙ Settings] white   │                                         │
└────────────────────────┴─────────────────────────────────────────┘

Note: Dark navy sidebar (#1c2540) với white text = VinUni institutional feel
      for Partner and University operations. Do not apply this admin-style
      shell to the default Student marketplace/career experience.
```

PAGE CANVAS (behind the sidebar, under the topbar): flat `--bg-subtle`. No
radial-gradient blobs, no decorative color washes — see §1.1.1. Content cards
are flat `.marketplace-card` (white, 1px `--border-default`, soft shadow), not
frosted glass. The sidebar itself is a solid `--brand-navy` fill; no
`backdrop-blur` on the sidebar container (blur is reserved for the topbar and
slide-in panels).

### 6.2 Dashboard Layouts

Dashboard layout is not one reusable card grid for every persona. Each persona
needs a different surface archetype:

- **Public marketplace:** search + discovery + public lists + sponsored slots.
- **Student command center:** readiness, next action, recommended jobs,
  applications/interviews, CV status, events, AI guidance, settings nudges.
- **Partner recruiting ops:** pipeline queues, candidate review, interview
  schedule, job health, team activity, package/quota/ad/event performance.
- **University operations center:** moderation queues, SLA risk, partner health,
  outcomes, AI/cost health, notification/template health, audit/security alerts.

Every dashboard must include at least:

- A primary work queue or next-action panel above the fold.
- Real filters or deep links into the full workflow.
- Live/read-model data or honest empty states.
- Status/alert treatment for risk, SLA, quota, moderation, or security.
- Browser-verified responsive layout at 375px and 1440px minimum.

**Student Dashboard:**
```
Row 1: [Welcome + VinUni Blue gradient banner] Profile completion bar
Row 2: 4 stat cards (VinUni Blue numbers, shadow-brand)
Row 3: [2/3] AI Recommended Jobs  |  [1/3] Upcoming Interviews
Row 4: [1/3] Skill Gap  |  [1/3] Events  |  [1/3] Career Score
```

**Partner Dashboard:**
```
Row 1: 4 stat cards
Row 2: [2/3] Hiring Pipeline (stage funnel, VinUni Blue bars)  |  [1/3] AI Insights
Row 3: [full] Recent applications table
Row 4: [1/2] Ad performance  |  [1/2] Today's interviews
```

**University Admin Dashboard:**
```
Row 1: 5 KPI cards (placement rate = VinUni Red if below target, Blue if on track)
Row 2: [2/3] Career outcomes chart  |  [1/3] Moderation queue (red urgency)
Row 3: System health  |  Top partners  |  Revenue
```

### 6.3 Public Career Gateway

The public homepage must feel like a real career marketplace, not a brochure.
Use an enterprise gateway + directory pattern: search first, public listings
immediately visible, clear persona paths, and sponsored inventory disclosed.

`docs/DESIGN_EXAMPLE.png` is the structural reference for this surface. It is
not a pixel-perfect template and its exact colors do not override VinUni brand
tokens, but the information architecture must match its rhythm: brand/nav,
mega-menu-capable company discovery, split hero with real campus/product media,
overlay search, metric strip, public job list, right rail, and trust/service
rail in the first public experience.

First viewport:

```text
Header: VinUni Career | Jobs | Companies | Career Explore | Events | Employers
        Language | Saved icon | Login | Register

Hero band:
  Left: VinUni navy panel, headline, short value copy, popular chips
  Right: real campus/product/employer visual from frontend/public
  Search overlay: keyword/title/skill + location/work mode + [Find jobs]
  Popular chips: Data Analyst, Software Engineer, Business Analyst, AI Engineer...

Below hero:
  Live metric strip only if backed by API; otherwise hide metrics. If trend
  deltas/sparklines are not backed by API, omit them instead of faking them.
```

Main public content:

- Public jobs list/table with company name, location, time, skills, sponsored
  disclosure, save/apply login gating.
- Employer spotlight card and company directory categories.
- Upcoming public events and career fair promotion.
- Sponsored banner/ad slots with fixed dimensions and visible `Được tài trợ` or
  `Quảng cáo` label.
- Trust/services rail: verified by VinUni, career support, skills learning,
  community.

Visual rules:

- Use VinUni navy/blue/red as primary identity; avoid purple/cream/generic SaaS
  palettes.
- Keep cards radius <= 8px unless an existing primitive requires otherwise.
- Use real committed assets where relevant: `frontend/public/brand/*`,
  `frontend/public/images/vinuni-campus.png`, and
  `frontend/public/images/career-day-2026.jpg`.
- No fake logos, fake counts, or fake "verified" claims. Use seeded dev data
  only when explicitly marked as local demo data.
- Public ad slots must never look like organic content without disclosure.
- Mobile first viewport still shows search + at least one public content entry
  point before decorative content.

Visual rescue acceptance:

- Public homepage screenshots at 375, 768, 1024, and 1440 px must be compared
  against `docs/DESIGN_EXAMPLE.png` for structure before status can say
  "visual/browser verified".
- Dashboard screenshots at the same widths must prove each persona has a
  distinct operating surface, not the same metric-card template.
- `docs/IMPLEMENTATION_STATUS.md` must distinguish functional browser
  verification from design-match verification.

### 6.4 Pipeline Kanban

```
Board header: white bg, shadow-sm
  Job title + [VinUni Blue button: Cài đặt pipeline] [Red button: Xuất]

Stage columns: bg-[var(--bg-subtle)] rounded-2xl
  Column header:
    Stage name (font-semibold)
    Count badge: bg-[#2e548a] text-white rounded-full px-2
    SLA overdue: bg-[#c83538] text-white (VinUni Red = urgent)

Candidate card: white card, shadow-sm
  Avatar + Name (or [Ẩn danh])
  AI match: number in VinUni Blue
  [Thông qua] = blue  [Từ chối] = red outline
```

### 6.5 Event Pages

```
Event hero: full-width image + gradient overlay (dark navy at bottom)
Event badge: HYBRID/ONLINE/ONSITE — teal filled pill

Ticket type cards:
  Free:    border-[#417865] bg-teal-50
  Paid:    border-[#2e548a] bg-blue-50
  VIP:     border-[#35426e] bg-[var(--gradient-card)]
  Selected: filled with brand gradient + white text + checkmark

[Đăng ký ngay] button: VinUni Red gradient (most important CTA on page)
```

---

## 7. Motion System

```css
--duration-instant: 50ms;
--duration-fast:    100ms;
--duration-normal:  150ms;
--duration-medium:  250ms;
--duration-slow:    350ms;

--ease-standard:  cubic-bezier(0.2, 0, 0, 1);
--ease-spring:    cubic-bezier(0.34, 1.56, 0.64, 1);
--ease-exit:      cubic-bezier(0.4, 0, 1, 1);
--ease-entrance:  cubic-bezier(0, 0, 0.2, 1);
```

| Interaction | Duration | Easing |
|-------------|----------|--------|
| Hover bg/color | 100ms | ease-standard |
| Dropdown open | 150ms | ease-entrance |
| Modal open | 200ms | ease-entrance |
| Modal close | 120ms | ease-exit |
| Toast slide-in | 250ms | ease-spring |
| Sidebar collapse | 200ms | ease-standard |
| Chart data enter | 50ms stagger | ease-entrance |
| Page fade | 200ms | ease-standard |
| Skeleton pulse | 1.5s infinite | ease-in-out |

`@media (prefers-reduced-motion)` → disable transforms, keep opacity ≤ 150ms.

---

## 8. Dark Mode

```
Toggle: user menu + settings page
Default: Light
System: reads prefers-color-scheme on first visit
Persist: localStorage + user.preferences DB field
Method: data-theme="dark" on <html>, CSS custom property swap

Dark sidebar: stays dark in BOTH modes (already dark navy by design)
Dark mode main area: --bg-base = #0d1520 (deep navy, VinUni-aligned)
```

---

## 9. Sponsorship & Ad Labels (BẮTBUỘC — không được bỏ)

```css
/* Sponsored job / event / content */
.sponsored-label {
  background: #fff3d0;
  color: #b56200;
  border: 1px solid #e98300;
  font-size: 0.65rem;
  font-weight: 700;
  padding: 2px 6px;
  border-radius: 4px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
/* VinUni Red left border on sponsored job card */
.sponsored-card {
  border-left: 3px solid #c83538;
}
```

Không thể override hay ẩn label qua user CSS/JS.

---

## 10. Mobile & PWA

- Minimum touch target: 44×44px
- Bottom tab navigation (max 5 icons) — background: dark navy sidebar color
- Active tab: VinUni Red indicator dot above icon
- Drawer: bottom sheet on mobile (not right drawer)
- Splash screen: VinUni Blue gradient + white logo + "Career Center" red tagline
- App icon: VinUni logo on blue background

---

## 11. Accessibility

| Requirement | Standard |
|-------------|---------|
| Color contrast | ≥ 4.5:1 text, ≥ 3:1 large/icons |
| Keyboard nav | Tab/Shift+Tab/Enter/Space/Arrow |
| Focus ring | 2px solid #2e548a, ring-offset-2 |
| Screen reader | ARIA labels, roles, live regions |
| Images | alt="" decorative, descriptive alt for content |
| Forms | linked label per input, aria-describedby for errors |
| Modal | focus trap, Escape to close |
| Motion | prefers-reduced-motion honored |
| Skip nav | "Bỏ qua đến nội dung" as first focusable |

---

## 12. Design Tokens Export (globals.css skeleton)

```css
@import url("https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:ital,wght@0,300;0,400;0,500;0,600;0,700;0,800;1,400;1,500&display=swap");

:root {
  /* Brand */
  --brand-primary:  #2e548a;
  --brand-red:      #c83538;
  --brand-teal:     #417865;
  --brand-navy:     #35426e;

  /* Extended */
  --brand-mid-blue: #4890bd;
  --brand-light-blue: #78c2ff;
  --brand-amber:    #e98300;
  --brand-teal-light: #5cc6d0;

  /* Plus Jakarta Sans */
  --font-sans: "Plus Jakarta Sans", system-ui, sans-serif;

  /* ... semantic tokens above ... */
}

/* Apply font globally */
body { font-family: var(--font-sans); }
```

---

## Drag-and-drop UX Patterns

Library: **@dnd-kit/core** + **@dnd-kit/sortable** (không dùng react-beautiful-dnd — deprecated)

### Kanban Pipeline (Partner)

```tsx
// Columns = stages, Cards = candidates
// Horizontal scroll on desktop (overflow-x: auto, min-width per column: 280px)
// Drag card between columns → API call on drop (optimistic update)

<DndContext onDragEnd={handleDragEnd} collisionDetection={closestCenter}>
  <div className="flex gap-4 overflow-x-auto pb-4">
    {stages.map(stage => (
      <SortableContext key={stage.id} items={stage.candidateIds} strategy={verticalListSortingStrategy}>
        <PipelineColumn stage={stage} />
      </SortableContext>
    ))}
  </div>
  <DragOverlay>
    {activeCandidate && <CandidateCard candidate={activeCandidate} isDragging />}
  </DragOverlay>
</DndContext>
```

Visual feedback khi drag:
- Card đang kéo: opacity 0.5, slight rotate 2deg, cursor: grabbing
- Drop target column: `border-2 border-[var(--brand-primary)] border-dashed bg-[var(--brand-primary)]/5`
- Invalid drop (không có permission): red dashed border + shake animation

### Partner Dashboard Widgets (Flexible Layout)

```tsx
// 12-column grid, widgets snap to S(4col)/M(6col)/L(12col)
// @dnd-kit sortable for widget reorder
// Widget resize: select S/M/L from widget menu (không free-form resize)

<SortableContext items={widgetOrder} strategy={rectSortingStrategy}>
  <div className="grid grid-cols-12 gap-4">
    {widgetOrder.map(widgetId => (
      <SortableWidget key={widgetId} id={widgetId} size={widgetSizes[widgetId]} />
    ))}
  </div>
</SortableContext>
```

Handle visibility:
- Widget drag handle: 6-dot icon (⠿), appears on hover
- Widget menu (3-dot): Resize S/M/L, Remove widget
- [+ Add widget] button ở cuối grid → modal chọn từ widget catalog
- [Reset layout] button trong dashboard settings

### Provider Priority Drag (AI Settings)

```tsx
// Vertical list, drag to reorder priority
<SortableContext items={providers.map(p => p.id)} strategy={verticalListSortingStrategy}>
  <div className="space-y-2">
    {providers.map((provider, index) => (
      <SortableProviderCard
        key={provider.id}
        provider={provider}
        priority={index + 1}  // 1 = primary, 2 = fallback-1, etc.
      />
    ))}
  </div>
</SortableContext>

// Provider card shows:
// [⠿ drag handle] [Provider Logo] Provider Name [🟢 healthy] [234ms] [$ 0.23 today]
// [Tasks: cv_extraction, chat] [Edit] [Test] [Remove]
```

---

## Visual Flow Builder UI (Workflow Engine)

Library: **@xyflow/react** (React Flow v12)

```tsx
// Full-screen canvas with sidebar node palette
<ReactFlow
  nodes={nodes}
  edges={edges}
  onNodesChange={onNodesChange}
  onEdgesChange={onEdgesChange}
  onConnect={onConnect}
  nodeTypes={customNodeTypes}
  fitView
  snapToGrid
  snapGrid={[16, 16]}
>
  <Background variant="dots" gap={16} size={1} />
  <Controls />
  <MiniMap />
  <Panel position="top-left">
    <NodePalette />  {/* drag nodes from here to canvas */}
  </Panel>
  <Panel position="top-right">
    <FlowToolbar />  {/* Save, Test, Activate, History */}
  </Panel>
</ReactFlow>
```

### Node Visual Design

```
Trigger node:        Purple border + ⚡ icon, rounded-xl
Condition node:      Diamond shape (rotated square), amber, 🔀
AI Process node:     Blue, 🤖, shows task_type selected
Human Review node:   Orange, 👤, shows SLA config
Action node:         Green, ⚙️, shows action type
Delay node:          Gray, ⏱, shows duration
End node:            Red circle, ×
```

Execution overlay (when viewing a run):
- Completed nodes: green glow border
- Current/running node: pulsing blue border
- Failed node: red border + error tooltip on hover
- Edges: animated stroke shows data flow direction

Node config sidebar (click node to open):
```
[← Back to canvas]
Configure: AI Process
────────────────────
Task Type:  [cv_extraction ▼]
Provider:   [Auto (recommended) ▼]
On success: connect to next node
On failure: [retry 3x ▼]  [then: Human Review]
────────────────────
[Save node]
```

### Flow Test Mode

Before activating:
1. Click [Test] → "Test mode: use sample data or paste real event"
2. Canvas shows: node highlights in real-time as flow executes
3. Result panel: step-by-step log of what each node did
4. If all passes → [Activate] button enabled

---

## Messaging UI

### Chat Panel

```tsx
// Slide-in panel from right edge (not full-page)
// Width: 380px desktop, full-screen mobile

<aside className={`fixed right-0 top-0 h-full w-[380px] bg-white border-l border-[var(--border-default)] 
                   shadow-xl z-30 flex flex-col transform transition-transform duration-200
                   ${isOpen ? 'translate-x-0' : 'translate-x-full'}`}>
  <ChatHeader />         {/* Avatar, name, presence dot, [×] close */}
  <ConversationList />   {/* OR: MessageThread if conversation selected */}
  <MessageComposer />    {/* Textarea + attachment + send */}
</aside>
```

### Message Bubble Design

```tsx
// Sent (right-aligned, brand blue bg)
<div className="flex justify-end mb-2">
  <div className="max-w-[75%] bg-[var(--brand-primary)] text-white rounded-2xl rounded-br-sm px-3 py-2">
    <p className="text-sm">{content}</p>
    <div className="flex items-center justify-end gap-1 mt-0.5">
      <span className="text-[10px] opacity-70">{formatTime(sentAt)}</span>
      <ReadReceiptIcon status={readStatus} />  {/* ✓ ✓✓ ✓✓blue */}
    </div>
  </div>
</div>

// Received (left-aligned, gray bg)
<div className="flex gap-2 mb-2">
  <Avatar size="xs" src={sender.avatar} />
  <div className="max-w-[75%] bg-[var(--surface-secondary)] rounded-2xl rounded-bl-sm px-3 py-2">
    <p className="text-xs font-semibold text-[var(--brand-primary)] mb-0.5">{sender.name}</p>
    <p className="text-sm text-[var(--text-primary)]">{content}</p>
    <span className="text-[10px] text-[var(--text-tertiary)] mt-0.5 block">{formatTime(sentAt)}</span>
  </div>
</div>

// System message (center, no avatar)
<div className="flex justify-center my-3">
  <span className="text-xs text-[var(--text-secondary)] bg-[var(--surface-secondary)] px-3 py-1 rounded-full">
    {systemContent}
  </span>
</div>
```

### Emoji Reaction Bar

```tsx
// Hover message → reaction bar appears (6 emojis + + button)
<div className="absolute -top-8 left-0 flex items-center gap-1 bg-white border border-[var(--border-default)]
                rounded-full px-2 py-1 shadow-md opacity-0 group-hover:opacity-100 transition-opacity">
  {['👍', '❤️', '😊', '🎉', '👏', '🙏'].map(emoji => (
    <button key={emoji} onClick={() => addReaction(emoji)}
            className="text-base hover:scale-125 transition-transform">
      {emoji}
    </button>
  ))}
</div>
```

---

## Job Cart UI

```tsx
// Cart button in student navbar header (right side)
<button className="relative p-2 hover:bg-[var(--surface-hover)] rounded-lg">
  <ShoppingCartIcon size={20} />
  {cartCount > 0 && (
    <span className="absolute -top-1 -right-1 bg-[var(--brand-red)] text-white text-[10px] font-bold
                     w-4 h-4 rounded-full flex items-center justify-center">
      {cartCount}
    </span>
  )}
</button>

// Cart page layout
<div className="max-w-5xl mx-auto px-4 py-8">
  <div className="flex items-center justify-between mb-6">
    <h1 className="text-2xl font-bold">Danh sách ứng tuyển ({cartCount})</h1>
    <div className="flex items-center gap-3">
      <span className="text-sm text-[var(--text-secondary)]">Còn {weeklyRemaining} lượt tuần này</span>
      <button className="btn-primary">Ứng tuyển tất cả ({selectedCount})</button>
    </div>
  </div>

  {/* Job list */}
  {cartJobs.map(job => (
    <CartJobCard key={job.id} job={job}>
      {/* AI cover letter preview/edit inline */}
      <CoverLetterEditor jobId={job.id} />
    </CartJobCard>
  ))}

  {/* Quota bar */}
  <QuotaBar used={weeklyUsed} total={weeklyTotal} />
</div>
```

---

## Activity Feed UI (Partner & University)

```tsx
// Real-time feed — new items appear at top with slide-in animation
// Virtual scroll for large histories

<div className="space-y-0 divide-y divide-[var(--border-default)]">
  {activities.map(activity => (
    <motion.div
      key={activity.id}
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex items-start gap-3 p-4 hover:bg-[var(--surface-hover)]"
    >
      <Avatar src={activity.actor.avatar} size="sm" />
      <div className="flex-1 min-w-0">
        <p className="text-sm">
          <span className="font-semibold">{activity.actor.name}</span>
          {' '}
          <span className="text-[var(--text-secondary)]">{activity.description}</span>
        </p>
        <time className="text-xs text-[var(--text-tertiary)] mt-0.5 block">
          {formatRelativeTime(activity.occurredAt)}
        </time>
      </div>
      <ActivityIcon type={activity.type} />
    </motion.div>
  ))}
</div>
```

Presence dots in team view:
```tsx
// Green pulsing dot = online
{status === 'online' && (
  <span className="absolute bottom-0 right-0 w-2.5 h-2.5 bg-emerald-500 rounded-full
                   ring-2 ring-white animate-pulse" />
)}
// Amber dot = away
// Gray dot = offline (no animation)
```

---

## Frontend Library Stack (Production)

### Core Framework

| Library | Version | Purpose |
|---|---|---|
| Next.js | 15 (App Router) | Framework — SSR, RSC, routing |
| TypeScript | 5.x strict | Type safety |
| Tailwind CSS | v4 | Utility-first styling (custom properties mode) |
| next-intl | 3.x | i18n — vi/en, locale routing |

### Component Foundation

| Library | Version | Purpose |
|---|---|---|
| **shadcn/ui** | latest | Headless, accessible components built on Radix UI. Use this as the component base — fully customizable with VinUni tokens. DO NOT use a pre-styled UI kit that overrides our design system. |
| **Radix UI** | — | Included via shadcn — Dialog, Dropdown, Select, Tooltip, etc. |
| **Phosphor Icons / lucide-react** | Current project packages | Use the existing icon family for the touched surface consistently. Do not mix styles inside one control group. |
| **Plus Jakarta Sans** | Google Fonts | Primary app UI typeface (load via `next/font/google`) |
| **JetBrains Mono** | Google Fonts | Code / monospace |

### State & Data Fetching

| Library | Version | Purpose |
|---|---|---|
| **TanStack Query** | v5 | Server state — API calls, caching, invalidation, optimistic updates |
| **Zustand** | 4.x | Client state — UI state, cart, filters, session context |
| **React Hook Form** | v7 | Form handling — uncontrolled, performant |
| **Zod** | 3.x | Schema validation — shared types with backend Pydantic schemas |

### Tables & Data Display

| Library | Version | Purpose |
|---|---|---|
| **TanStack Table** | v8 | Complex tables — candidate pipeline, application lists, export previews. Server-side sorting/pagination. |
| **Recharts** | 2.x | Dashboard charts — hiring funnel, market intelligence, ad performance |

### Drag & Drop

| Library | Version | Purpose |
|---|---|---|
| **@dnd-kit/core** | 6.x | Drag-and-drop runtime |
| **@dnd-kit/sortable** | 7.x | Sortable lists and grids — kanban pipeline, widget reorder, provider priority |

### Workflow Builder

| Library | Version | Purpose |
|---|---|---|
| **@xyflow/react** | 12.x | Visual workflow builder canvas — React Flow v12 |

### Animation

| Library | Version | Purpose |
|---|---|---|
| **Framer Motion** | 11.x | Page transitions, activity feed, chart enters, confirmation cards. Always respect `prefers-reduced-motion`. |

### Rich Text & Content

| Library | Version | Purpose |
|---|---|---|
| **Tiptap** | 2.x | Rich text editor — JD writing, KB document annotation, email templates |
| **react-pdf** | 7.x | PDF preview in-browser — CV viewer, offer letter preview |
| **react-dropzone** | 14.x | File upload zone — CV upload, document upload, ad creative upload |

### Date & Time

| Library | Version | Purpose |
|---|---|---|
| **date-fns** | 3.x | Date formatting, relative time (`formatDistanceToNow`), VN locale |
| **date-fns-tz** | 3.x | Timezone handling — VN+7 display, event timezone |

### Real-time

| Library | Version | Purpose |
|---|---|---|
| Native `WebSocket` | — | WebSocket client (no library needed — FastAPI WS on backend) |
| Native `EventSource` | — | SSE for AI streaming — no library needed |

### Command Palette & Search

| Library | Version | Purpose |
|---|---|---|
| **cmdk** | 1.x | ⌘K command palette — search jobs, navigate, quick actions |

### Utilities

| Library | Version | Purpose |
|---|---|---|
| **clsx** + **tailwind-merge** | latest | Conditional classname merging (already in shadcn) |
| **nuqs** | 2.x | URL search param state — filters, pagination, tab state in URL |
| **next/image** | built-in | Optimized images — company logos, avatars, event covers |

### Testing

| Library | Version | Purpose |
|---|---|---|
| **Playwright** | 1.x | E2E browser tests — auth flows, apply flow, pipeline drag |
| **Vitest** | 2.x | Unit tests — utility functions, Zod schemas, state logic |
| **Testing Library** | 16.x | Component tests — render + user interaction |

### `package.json` dependencies (abridged)

```json
{
  "dependencies": {
    "next": "^15.0.0",
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "typescript": "^5.0.0",
    "tailwindcss": "^4.0.0",
    "next-intl": "^3.0.0",
    "@tanstack/react-query": "^5.0.0",
    "@tanstack/react-table": "^8.0.0",
    "react-hook-form": "^7.0.0",
    "zod": "^3.0.0",
    "zustand": "^4.0.0",
    "framer-motion": "^11.0.0",
    "@dnd-kit/core": "^6.0.0",
    "@dnd-kit/sortable": "^7.0.0",
    "@xyflow/react": "^12.0.0",
    "@tiptap/react": "^2.0.0",
    "@tiptap/starter-kit": "^2.0.0",
    "react-pdf": "^7.0.0",
    "react-dropzone": "^14.0.0",
    "recharts": "^2.0.0",
    "date-fns": "^3.0.0",
    "date-fns-tz": "^3.0.0",
    "cmdk": "^1.0.0",
    "nuqs": "^2.0.0",
    "clsx": "^2.0.0",
    "tailwind-merge": "^2.0.0",
    "@phosphor-icons/react": "^2.0.0"
  },
  "devDependencies": {
    "@playwright/test": "^1.0.0",
    "vitest": "^2.0.0",
    "@testing-library/react": "^16.0.0",
    "@testing-library/user-event": "^14.0.0"
  }
}
```

### What NOT to use

| Avoid | Reason |
|---|---|
| `react-beautiful-dnd` | Deprecated — use `@dnd-kit` |
| `moment.js` | 65kb, unmaintained — use `date-fns` |
| `lodash` | Use native ES2024 + targeted imports |
| `axios` | Use `fetch` + TanStack Query; Next.js 15 has first-class fetch |
| `Material UI` / `Ant Design` / `Chakra` | Conflict with our custom Tailwind design system |
| `Next Auth` | Backend handles auth via JWT + httpOnly cookies |
| `Redux Toolkit` | Zustand is simpler for our state needs |
| `react-query v3/v4` | Use v5 only |
