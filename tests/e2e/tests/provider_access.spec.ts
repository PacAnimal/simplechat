import { test, expect, request } from "@playwright/test";
import { resetDB, loginWithAdminProfile, BACKEND } from "./stub-helpers";

async function openProviderAccessPanel(page: any) {
  await page.getByTestId("profile-settings-button").click();
  await page.getByTestId("provider-access-button").click();
  await expect(page.getByTestId("provider-access-panel")).toBeVisible({ timeout: 5000 });
}

test.beforeEach(async ({ page }) => {
  await resetDB();
  await page.goto("/");
  await loginWithAdminProfile(page);
});

test("admin can open provider access panel", async ({ page }) => {
  await openProviderAccessPanel(page);
});

test("panel stays open when clicking toggles", async ({ page }) => {
  await openProviderAccessPanel(page);

  // click the default OpenAI toggle — panel must remain open
  const toggle = page.getByTestId("toggle-default-openai");
  await toggle.click();
  await expect(page.getByTestId("provider-access-panel")).toBeVisible({ timeout: 2000 });
});

test("default toggle changes aria-checked state", async ({ page }) => {
  await openProviderAccessPanel(page);

  const toggle = page.getByTestId("toggle-default-openai");
  await expect(toggle).toHaveAttribute("aria-checked", "true");

  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-checked", "false");

  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-checked", "true");
});

test("user row toggle changes state", async ({ page }) => {
  // create a second user to appear in the table
  const ctx = await request.newContext();
  const r = await ctx.post(`${BACKEND}/api/profiles`, {
    data: { name: "RegularUser", password: "regPass1", avatar: 0 },
  });
  expect(r.ok()).toBeTruthy();
  const { id } = await r.json();
  await ctx.dispose();

  await openProviderAccessPanel(page);

  const toggle = page.getByTestId(`toggle-user-${id}-anthropic`);
  await expect(toggle).toHaveAttribute("aria-checked", "true");

  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-checked", "false");
  await expect(page.getByTestId("provider-access-panel")).toBeVisible();
});

test("reset button returns user to default", async ({ page }) => {
  const ctx = await request.newContext();
  const r = await ctx.post(`${BACKEND}/api/profiles`, {
    data: { name: "TargetUser", password: "targetPass1", avatar: 0 },
  });
  const { id } = await r.json();
  await ctx.dispose();

  await openProviderAccessPanel(page);

  // give user a custom override first
  const toggle = page.getByTestId(`toggle-user-${id}-openai`);
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-checked", "false");

  // reset button should now be visible
  const resetBtn = page.locator(`tr:has([data-testid="toggle-user-${id}-openai"]) button:has-text("reset")`);
  await expect(resetBtn).toBeVisible();
  await resetBtn.click();

  // user should be back on defaults — "default" badge visible, no reset button
  const defaultBadge = page.locator(`tr:has([data-testid="toggle-user-${id}-openai"]) span:has-text("default")`);
  await expect(defaultBadge).toBeVisible();
  await expect(resetBtn).not.toBeVisible();
});

test("panel closes via Close button", async ({ page }) => {
  await openProviderAccessPanel(page);
  await page.getByRole("button", { name: "Close" }).click();
  await expect(page.getByTestId("provider-access-panel")).not.toBeVisible({ timeout: 2000 });
});

test("provider access menu item not visible for non-admin", async ({ page }) => {
  // log out admin and log in as regular user
  await page.evaluate(() => {
    localStorage.removeItem("simplechat_token");
    localStorage.removeItem("simplechat_profile");
  });

  const ctx = await request.newContext();
  const r1 = await ctx.post(`${BACKEND}/api/profiles`, {
    data: { name: "PlainUser", password: "plainPass1", avatar: 0 },
  });
  const profile = await r1.json();
  const r2 = await ctx.post(`${BACKEND}/api/profiles/${profile.id}/login`, {
    data: { password: "plainPass1" },
  });
  const { token } = await r2.json();
  await ctx.dispose();

  await page.evaluate(
    ({ tok, prof }) => {
      localStorage.setItem("simplechat_token", tok);
      localStorage.setItem("simplechat_profile", JSON.stringify(prof));
    },
    { tok: token, prof: profile },
  );
  await page.reload();
  await page.waitForSelector('[data-testid="sidebar"]', { timeout: 10_000 });

  await page.getByTestId("profile-settings-button").click();
  await expect(page.getByTestId("provider-access-button")).not.toBeVisible();
});
