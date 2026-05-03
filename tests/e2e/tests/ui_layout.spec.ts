import { test, expect, request } from "@playwright/test";

const BACKEND = "http://127.0.0.1:8084";

test.beforeEach(async ({ page }) => {
  const ctx = await request.newContext();
  await ctx.post(`${BACKEND}/api/test/reset`);
  await ctx.dispose();
  await page.goto("/");
});

test("page loads with sidebar and welcome screen", async ({ page }) => {
  await expect(page.getByTestId("sidebar")).toBeVisible();
  await expect(page.getByTestId("welcome-new-chat")).toBeVisible();
  await expect(page.getByRole("heading", { name: "SimpleChat" })).toBeVisible();
});

test("new chat button is in sidebar", async ({ page }) => {
  await expect(page.getByTestId("new-chat-button")).toBeVisible();
});

test("new chat dialog opens from sidebar button", async ({ page }) => {
  await page.getByTestId("new-chat-button").click();
  await expect(page.getByTestId("new-chat-dialog")).toBeVisible();
});

test("new chat dialog opens from welcome button", async ({ page }) => {
  await page.getByTestId("welcome-new-chat").click();
  await expect(page.getByTestId("new-chat-dialog")).toBeVisible();
});

test("new chat dialog has both provider options", async ({ page }) => {
  await page.getByTestId("new-chat-button").click();
  await expect(page.getByTestId("provider-openai")).toBeVisible();
  await expect(page.getByTestId("provider-anthropic")).toBeVisible();
});

test("dialog can be closed by clicking backdrop", async ({ page }) => {
  await page.getByTestId("new-chat-button").click();
  await expect(page.getByTestId("new-chat-dialog")).toBeVisible();
  await page.mouse.click(10, 10);
  await expect(page.getByTestId("new-chat-dialog")).not.toBeVisible({ timeout: 2000 });
});
