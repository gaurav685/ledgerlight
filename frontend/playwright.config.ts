import { defineConfig, devices } from "@playwright/test";

// Phase 5 §7: the real build-smoke suite -- checks the real built
// pages render with their real expected elements, against a real
// `next start` server. Deliberately shallow (no backend calls) --
// the full real e2e suite against a real live backend (login,
// cross-tenant denial, CSRF, etc.) is §9's own scope, not this one.
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:3000",
  },
  webServer: {
    command: "pnpm start",
    url: "http://127.0.0.1:3000/login",
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
