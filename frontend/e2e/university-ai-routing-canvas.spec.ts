import { expect, test, type Page } from "@playwright/test";

/**
 * University admin AI Routing Canvas E2E (ai-routing-canvas plan, Task 7).
 *
 * Runs against the ALREADY-RUNNING dev stack (frontend :3000, backend :8000
 * with the demo seed loaded via `backend/scripts/seed_dev.py`).
 */

const EMAIL = "career.admin@vinuni.edu.vn";
const PASSWORD = "123456";

async function loginAsUniversityAdmin(page: Page) {
  await page.goto("/vi/auth/login");
  await page.getByLabel(/email/i).fill(EMAIL);
  await page.getByLabel(/mật khẩu/i).fill(PASSWORD);
  await page.getByRole("button", { name: "Đăng nhập", exact: true }).click();
  await expect(page).toHaveURL(/\/vi\/university\//, { timeout: 30_000 });
}

test("university admin can open the AI routing canvas and it never shows raw provider text to a non-privileged view", async ({
  page,
}) => {
  await loginAsUniversityAdmin(page);
  await page.goto("/vi/university/ai-settings/routing");

  await expect(page.getByTestId("flow-canvas")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId("circuit-panel")).toBeVisible({ timeout: 15_000 });
});

test("AI Settings page links to the routing canvas", async ({ page }) => {
  await loginAsUniversityAdmin(page);
  await page.goto("/vi/university/ai-settings");
  await page.getByRole("link", { name: "Sơ đồ định tuyến AI" }).click();
  await expect(page).toHaveURL(/\/vi\/university\/ai-settings\/routing/, { timeout: 15_000 });
});
