import { test, expect, type Page } from "@playwright/test";

/**
 * Student core-loop E2E (committed CI artifact).
 *
 * Runs against the ALREADY-RUNNING dev stack (frontend :3000, backend :8000
 * with the demo seed loaded). Resilient to pre-existing seeded data: the seeded
 * student already has >=1 CV and >=1 application, so this spec is read-only by
 * default (it never submits an application) and tolerates a non-empty library.
 *
 * Covers, end to end:
 *  - login via /vi/auth/login with the seeded student;
 *  - landing on a STUDENT surface with the marketplace top-nav shell
 *    (CV Studio link present, no admin/partner sidebar item);
 *  - CV Studio: ensure >=1 CV exists (create from raw notes if empty), and the
 *    active-CV quota counter renders when CVs exist;
 *  - a seeded job detail: the CV-to-job fit panel renders a numeric /100 score
 *    and leaks NO AI-provider internals;
 *  - the apply CV picker option is score-annotated ("phù hợp …/100").
 */

// NOTE (verified 2026-07-01): swapped from a non-existent ephemeral account
// (browser_smoke_001@vinuni.edu.vn — not produced by any committed seed) to
// the real `scripts/seed_dev.py` student account.
const EMAIL = "student@vinuni.edu.vn";
const PASSWORD = "123456";

// Substrings that would betray AI-provider/model internals in user-facing copy.
// NOTE: "ai" is intentionally NOT checked — the panel legitimately tells the
// student this is a product fit score, "không phải mức độ tự tin của AI".
const AI_INTERNALS = ["openai", "gpt", "token", "model", "prompt", "anthropic"];

async function login(page: Page) {
  await page.goto("/vi/auth/login");
  await page.getByLabel(/email/i).fill(EMAIL);
  await page.getByLabel(/mật khẩu/i).fill(PASSWORD);
  await page.getByRole("button", { name: "Đăng nhập", exact: true }).click();
  // router.replace -> /vi/student/dashboard (a student surface).
  await expect(page).toHaveURL(/\/vi\/student\//, { timeout: 30_000 });
}

test("student core loop: login -> shell -> CV quota -> job fit -> apply picker", async ({
  page,
}) => {
  await test.step("log in as the seeded student", async () => {
    await login(page);
  });

  await test.step("lands on the student marketplace top-nav shell (no admin sidebar)", async () => {
    // CV Studio is a student-shell nav item -> proves the inherited top nav.
    // The same link also legitimately appears in the page's main content and
    // the marketing footer, so scope to the FIRST match (the persistent top
    // nav) rather than an unscoped strict-mode query across the whole page.
    await expect(
      page.getByRole("link", { name: "CV Studio" }).first(),
    ).toBeVisible();
    // Partner/university-only nav items must NOT be present for a student.
    // `exact: true` because Playwright's default name match is a
    // case-insensitive SUBSTRING match, and the marketing footer's
    // "candidates" link ("Hồ sơ ứng viên") legitimately contains "Ứng viên"
    // as a substring without being the partner-only nav item.
    await expect(
      page.getByRole("link", { name: "Ứng viên", exact: true }),
    ).toHaveCount(0);
    await expect(
      page.getByRole("link", { name: "Kiểm duyệt", exact: true }),
    ).toHaveCount(0);
  });

  await test.step("CV Studio shows the active-CV quota (creates a CV from notes if empty)", async () => {
    await page.getByRole("link", { name: "CV Studio" }).first().click();
    await expect(page).toHaveURL(/\/vi\/student\/cv(\/)?$/);

    const counter = page.getByText(/CV đang hoạt động:/);
    const emptyTitle = page.getByText("Bạn chưa có CV nào");

    // Library settles into either the populated (counter) or empty state.
    await expect(counter.or(emptyTitle).first()).toBeVisible({
      timeout: 20_000,
    });

    if (await emptyTitle.isVisible().catch(() => false)) {
      // CV-first creation via raw notes (no AI) — must land in the builder.
      await page
        .getByRole("button", { name: /Tạo CV mới/ })
        .first()
        .click();
      const createDialog = page.getByRole("dialog", { name: "Tạo CV mới" });
      await createDialog
        .getByRole("button", { name: /Tạo từ ghi chú/ })
        .click();
      await createDialog
        .getByLabel(/Tên CV/)
        .fill("E2E CV thực tập Backend");
      await createDialog
        .getByLabel(/Ghi chú của bạn/)
        .fill(
          "Tóm tắt: Sinh viên CNTT năm cuối, muốn làm backend\nKỹ năng: Python, FastAPI, PostgreSQL",
        );
      await createDialog
        .getByRole("button", { name: "Tạo CV", exact: true })
        .click();
      // Raw-notes path routes straight into the CV builder.
      await expect(page).toHaveURL(/\/vi\/student\/cv\/[^/]+$/, {
        timeout: 30_000,
      });
      // Back to the library so the quota counter is in view.
      await page.getByRole("link", { name: "CV Studio" }).first().click();
      await expect(page).toHaveURL(/\/vi\/student\/cv(\/)?$/);
    }

    // CVs now exist -> the active-CV quota counter must render.
    await expect(page.getByText(/CV đang hoạt động:/).first()).toBeVisible({
      timeout: 20_000,
    });
  });

  await test.step("open a seeded job detail", async () => {
    await page.getByRole("link", { name: "Việc làm" }).first().click();
    await expect(page).toHaveURL(/\/vi\/jobs(\?.*)?$/);
    // Job cards/rows link to /vi/jobs/{id}. NOTE (verified 2026-07-01): a
    // page-wide `a[href*="/jobs/"]` selector is NOT precise enough — the
    // footer's "Đăng tin tuyển dụng" (post a job) link targets
    // `/partner/jobs/new`, which also contains the substring "/jobs/", and
    // under real fetch/hydration timing `.first()` can resolve to that footer
    // link before the job cards finish rendering (flaky false match, not a
    // product bug). Anchoring the href to start with `/vi/jobs/` (trailing
    // slash + segment) unambiguously matches only a job detail card/row: it
    // excludes both the exact board URL (`/vi/jobs`, no trailing segment) and
    // `/partner/jobs/new` (doesn't start with `/vi/jobs/`).
    const firstJob = page.locator('a[href^="/vi/jobs/"]').first();
    await expect(firstJob).toBeVisible({ timeout: 20_000 });
    await firstJob.click();
    await expect(page).toHaveURL(/\/vi\/jobs\/[^/]+$/, { timeout: 20_000 });
  });

  await test.step("CV-to-job fit panel renders a numeric /100 score with no AI leakage", async () => {
    const fitPanel = page.locator('section[aria-labelledby="cv-fit-title"]');
    await expect(
      fitPanel.getByRole("heading", { name: "Mức độ phù hợp CV" }),
    ).toBeVisible({ timeout: 20_000 });

    // Client query: wait for the scored recommended CV (aria-label carries the
    // numeric score) and the /100 unit.
    await expect(
      fitPanel.getByLabel(/Điểm phù hợp \d+ trên 100/),
    ).toBeVisible({ timeout: 25_000 });
    await expect(fitPanel).toContainText("/100");

    // No provider/model/token internals anywhere in the fit panel.
    const fitText = (await fitPanel.innerText()).toLowerCase();
    for (const bad of AI_INTERNALS) {
      expect(fitText, `fit panel must not leak "${bad}"`).not.toContain(bad);
    }
  });

  await test.step("apply CV picker option is score-annotated (phù hợp …/100)", async () => {
    await page
      .getByRole("button", { name: "Ứng tuyển ngay", exact: true })
      .click();
    const dialog = page.getByRole("dialog", { name: "Ứng tuyển vị trí này" });
    await expect(dialog).toBeVisible({ timeout: 15_000 });

    const cvSelect = dialog.getByLabel("Chọn CV");
    await expect(cvSelect).toBeVisible();

    // The recommended/annotated option label is "{title} · phù hợp {n}/100 · …",
    // populated once the owner-scoped fit query resolves.
    await expect(cvSelect).toContainText("phù hợp", { timeout: 25_000 });
    await expect(cvSelect).toContainText("/100");

    // Submitting is intentionally skipped to keep the spec idempotent.
  });
});
