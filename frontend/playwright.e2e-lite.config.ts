import { defineConfig, devices } from "@playwright/test";

// Phase 6A §2.3: the real full e2e suite against the real, already-
// running e2e-lite Docker stack (postgres/garage/api/web, brought up
// separately via `docker compose -f infra/docker-compose.yml -f
// infra/docker-compose.e2e-lite.yml up -d`) -- no webServer entry
// here on purpose; this config never starts its own server, it only
// points at the one already up. Distinct from playwright.config.ts
// (§7's own minimal build-smoke suite against a bare `next start`).
export default defineConfig({
  testDir: "./e2e",
  testMatch: /full-e2e-lite\.spec\.ts/,
  fullyParallel: false,
  workers: 1,
  reporter: "list",
  outputDir: "../docs/phase-6/evidence/playwright-output",
  use: {
    baseURL: "http://127.0.0.1:3000",
    trace: "on",
    screenshot: "on",
    video: "on",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
