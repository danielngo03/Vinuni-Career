import { defineConfig, devices } from "@playwright/test";

/**
 * E2E config for the VinUni Career Platform frontend.
 *
 * Assumes the dev/prod servers are ALREADY running:
 *   - frontend: http://localhost:3000 (this baseURL)
 *   - backend:  http://localhost:8000 (with the demo seed loaded)
 *
 * No `webServer` block: we do NOT rebuild or boot servers from the test runner.
 * Uses the locally cached Playwright chromium (default cache:
 * ~/Library/Caches/ms-playwright). Do not configure a custom browsers path.
 */
export default defineConfig({
  testDir: "e2e",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [["list"]],
  timeout: 60_000,
  expect: { timeout: 15_000 },
  use: {
    baseURL: "http://localhost:3000",
    locale: "vi-VN",
    actionTimeout: 15_000,
    navigationTimeout: 30_000,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"], channel: undefined },
    },
  ],
});
