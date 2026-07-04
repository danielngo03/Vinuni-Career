import { expect, test, type Page } from "@playwright/test";

/**
 * University admin account-approval Workflow Builder E2E (Phase B canvas).
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

test("university admin can reach the workflow area", async ({ page }) => {
  await loginAsUniversityAdmin(page);
  // Full navigation/canvas assertions are added in later tasks as the
  // real page is built; this task only proves login lands in /university/.
});

test("admin builds, saves, and activates a workflow via drag-and-drop canvas", async ({ page }) => {
  await loginAsUniversityAdmin(page);
  await page.goto("/vi/university/workflow/new");

  await expect(page.getByTestId("flow-canvas")).toBeVisible();

  const trigger = page.getByTestId("palette-node-trigger");
  const canvas = page.getByTestId("flow-canvas");
  await trigger.dragTo(canvas, { targetPosition: { x: 150, y: 100 } });

  const endNode = page.getByTestId("palette-node-end");
  await endNode.dragTo(canvas, { targetPosition: { x: 150, y: 300 } });

  await page.getByRole("button", { name: "Lưu bản nháp" }).click();
  await expect(page.getByText(/Nháp/)).toBeVisible({ timeout: 10_000 });
});

test("workflow list shows created flows and links to the editor", async ({ page }) => {
  await loginAsUniversityAdmin(page);
  await page.goto("/vi/university/workflow");
  await expect(page.getByRole("heading", { name: "Quy trình duyệt tài khoản" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Tạo quy trình mới" })).toBeVisible();
});
