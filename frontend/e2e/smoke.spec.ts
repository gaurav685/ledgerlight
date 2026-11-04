import { test, expect } from "@playwright/test";

// Phase 5 §7: a real, minimal build-smoke check -- the real login
// page renders with its real form fields, against a real
// `next start` production build. Never calls the real backend (the
// full real e2e suite, including a real login, is §9's own scope).

test("login page renders with its real form fields", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByRole("heading", { name: "Log in" })).toBeVisible();
  await expect(page.locator("#tenant_slug")).toBeVisible();
  await expect(page.locator("#email")).toBeVisible();
  await expect(page.locator("#password")).toBeVisible();
  await expect(page.getByRole("button", { name: "Log in" })).toBeVisible();
});

test("the real security headers are present on every response", async ({ page }) => {
  const response = await page.goto("/login");
  expect(response).not.toBeNull();
  const headers = response!.headers();
  expect(headers["x-frame-options"]).toBe("DENY");
  expect(headers["x-content-type-options"]).toBe("nosniff");
  expect(headers["content-security-policy"]).toContain("default-src 'self'");
});
