import { test, expect, request } from "@playwright/test";

const BACKEND = "http://127.0.0.1:8084";

async function resetDB() {
  const ctx = await request.newContext();
  await ctx.post(`${BACKEND}/api/test/reset`);
  await ctx.dispose();
}

async function createChat(page: any, provider: "openai" | "anthropic") {
  await page.getByTestId("new-chat-button").click();
  await page.getByTestId(`provider-${provider}`).click();
  await page.getByTestId("create-chat-button").click();
  await expect(page.getByTestId("new-chat-dialog")).not.toBeVisible({ timeout: 5000 });
  await expect(page.getByTestId("chat-window")).toBeVisible({ timeout: 5000 });
}

test.beforeEach(async ({ page }) => {
  await resetDB();
  await page.goto("/");
});

test("create OpenAI chat and see chat window", async ({ page }) => {
  await createChat(page, "openai");
  await expect(page.getByTestId("chat-title")).toBeVisible();
  await expect(page.getByTestId("message-input")).toBeVisible();
});

test("create Anthropic chat and see chat window", async ({ page }) => {
  await createChat(page, "anthropic");
  await expect(page.getByTestId("chat-title")).toBeVisible();
  await expect(page.getByTestId("message-input")).toBeVisible();
});

test("created chat appears in sidebar", async ({ page }) => {
  await createChat(page, "openai");
  await expect(page.locator('[data-testid^="chat-item-"]').first()).toBeVisible({ timeout: 5000 });
});

test("switching provider updates model list", async ({ page }) => {
  await page.getByTestId("new-chat-button").click();

  await page.getByTestId("provider-openai").click();
  const opts1 = await page.getByTestId("model-select").locator("option").allTextContents();
  expect(opts1.some((o) => o.includes("GPT"))).toBe(true);

  await page.getByTestId("provider-anthropic").click();
  const opts2 = await page.getByTestId("model-select").locator("option").allTextContents();
  expect(opts2.some((o) => o.includes("Claude"))).toBe(true);
});

test("can create multiple chats and they all appear in sidebar", async ({ page }) => {
  // create first chat
  await createChat(page, "openai");

  // create second chat
  await page.getByTestId("new-chat-button").click();
  await page.getByTestId("provider-anthropic").click();
  await page.getByTestId("create-chat-button").click();
  await expect(page.getByTestId("new-chat-dialog")).not.toBeVisible({ timeout: 5000 });

  // sidebar must show exactly 2 chats (DB was cleared in beforeEach)
  const chatItems = page.locator('[data-testid^="chat-item-"]');
  await expect(chatItems).toHaveCount(2, { timeout: 8000 });
});
