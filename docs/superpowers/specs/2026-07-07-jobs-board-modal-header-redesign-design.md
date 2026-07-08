# Jobs board + header redesign — design spec

Date: 2026-07-07
Owner decision session. Visual system: v9 Monochrome (DESIGN.md §1.1.2). Icons: Phosphor.

## Goal

Modernize the public `/jobs` list surface, replace the right-side preview panel
with a right-docked job detail drawer modal, and restructure the public + student
headers (relocating the floating quick-action rail functions into the header /
avatar menu and removing the rail).

## A. `/jobs` list page (`components/jobs/public-job-board.tsx`)

### Top filter bar (kept, trimmed)
- Keep: Industry (danh mục), Search, Location (địa điểm).
- Add a **Employment Type quick Select** ("Loại hình") in the top bar.
- Remove the `AdvancedFiltersMenu` trigger button and the standalone Clear button.

### Two-column body (`xl:grid-cols-[280px_minmax(0,1fr)]`)
- **Left — `JobFilterSidebar` (new):** sticky facet panel, filters rendered
  directly (not dropdowns) as radio-pill groups:
  - Hình thức làm việc (location_type / work mode)
  - Đăng trong (posted within: any / 7 / 30)
  - Mức lương (salary bands — existing SALARY_OPTIONS)
  - Kinh nghiệm (experience bands — existing EXPERIENCE_OPTIONS)
  - "Xóa lọc" clears all.
  - Mobile (<xl): collapses into a "Bộ lọc" button opening a `Sheet` with the
    same facets; active-filter count badge on the button.
- **Right — results:** header row (result count + `SortMenu` + view toggle),
  then the card grid.

### View modes
- List = **2 cards/row**: `grid-cols-1 md:grid-cols-2`.
- Grid = **4 cards/row**: `grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4`.
- Toggle icons change for correct semantics: List → `Rows`, Grid → `GridFour`.
- Page sizes: keep list 10 / grid 20 (or bump grid to a multiple of 4 — 20 is fine).

### Card interaction
- Card click (`onSelect`) opens `JobDetailModal` instead of setting the side panel.
- Keep the save button + external-link arrow on cards.
- Keep `PromotedInlineJob` at index 3 (sponsored disclosure compliance).
- **Remove** the right `<aside>` `JobPreviewPanel` + `PreviewAdStack`.

### `JobDetailModal` (new component)
Right-docked drawer: fixed overlay `bg-black/40` backdrop + right panel
`w-full sm:max-w-[560px]`, slide-in, internal scroll, Escape + backdrop close,
focus trap, `role="dialog"` `aria-modal`. Reuses the existing `detailQuery`
(`jobsApi.getPublic(selectedJobId)`).

Sections (adapted from the reference image, monochrome):
1. Top bar: "Chi tiết việc làm" + Report action + close (X).
2. AI Summary card (only if summary text available) — green AI accent, Sparkle.
3. Title + `% phù hợp` badge (students only) + meta row (employment · work mode ·
   location · posted).
4. Company row (avatar, name, verified, rating).
5. Description + Responsibilities (requirements) with "Xem thêm/Thu gọn".
6. Three stat cards (replace Budget/Duration/Proposals): **Mức lương · Hạn nộp ·
   Ứng viên** (privacy-safe count; hidden for guests).
7. Skills chips.
8. Company details box.
9. Sticky footer: **Lưu · Ứng tuyển · Xem chi tiết** (→ `/jobs/[id]`).
   No "credits" concept (not applicable to this product).

Guests never see personalized fit or competition claims (CLAUDE.md).

## B. Public header

- `public-nav-config.ts` `PUBLIC_PRIMARY_NAV` → order: `jobs`, `companies`,
  `events`, `createCv`. Remove `careerExplore`.
- `createCv`: plain link (no mega) to `/student/cv`; guests get login redirect
  with returnTo via the student shell guard.
- Rename `nav.jobs` label → "Việc làm" / "Jobs" in `messages/{vi,en}/shared/shell.json`
  (applies to student too — approved).
- Add `nav.createCv` = "Tạo CV" / "Create CV".
- Remove `<FloatingActionRail/>` mount from `public-shell.tsx`.

## C. Student header (`student-shell.tsx`)

- Remove `<FloatingActionRail/>` mount.
- Right side order: LanguageSwitcher · ThemeSwitcher · NotificationBell(href) ·
  MessagingBell(href) · **Saved** (`SavedButton variant="icon"` → /student/saved) ·
  **AI** (new `HeaderAiButton` opening `AiChatWindow`) · AccountMenu.
- `AccountMenu` extended with optional `dashboardHref` + `profileHref` and a
  **feedback** item that opens `FeedbackModal`. Student avatar menu items:
  **Tổng quan · Hồ sơ · Cài đặt · Thanh toán · Góp ý & hỗ trợ · Đăng xuất**.
  (Feedback/support relocated here, not to the header, to keep the header row calm.)

## D. Cleanup + docs

- `FloatingActionRail` + `FeedbackModal` become unused by shells; keep the files
  (FeedbackModal is still used by AccountMenu now) but remove the rail mounts.
  `FloatingActionRail` is left in place as dead code for easy restore.
- Update the "floating actions" rule in `CLAUDE.md` (and realism spec if it
  duplicates it) to reflect: quick actions now live in the header (student) /
  avatar menu, rail removed from public + student.

## Non-goals / preserved invariants
- Do not fake data; honest empty/permission states remain.
- Sponsored/promoted disclosure preserved.
- No provider/model/token leakage in the AI summary.
- Existing job detail page `/jobs/[jobId]` unchanged.

## Verification
- Typecheck + lint + build.
- Browser QA at 375 / 768 / 1024 / 1440, light + dark.
- Keyboard: modal focus trap, Escape, toggle, facet radios, avatar menu.
- Guest vs student: fit/competition hidden for guests; createCv login redirect.
